from flask import Blueprint, request, jsonify, session, current_app
from app import db
from app.models import Interview, Question, EmotionLog
from app.routes.main import login_required
from app.services.ai_service import generate_question, evaluate_answer, evaluate_code
from app.services.emotion_detection import detect_emotion, verify_face
from app.services.audio_analysis import analyze_audio, transcribe_audio
from app.services.report_generator import generate_report
from datetime import datetime
import base64
import os

bp = Blueprint('api', __name__, url_prefix='/api')


@bp.route('/next-question', methods=['POST'])
@login_required
def next_question():
    """Generate next interview question with automatic round progression"""
    try:
        data = request.get_json()
        interview_id = data.get('interview_id')
        
        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid interview'}), 403
        
        # Check if interview is already completed
        if interview.status == 'completed':
            return jsonify({
                'success': False,
                'completed': True,
                'message': 'Interview has been completed'
            })
        
        # Define round order and questions per round
        ROUND_ORDER = ['tech', 'coding', 'hr']
        
        # Determine questions per round based on round type
        if interview.current_round == 'coding':
            QUESTIONS_PER_ROUND = 3
        else:
            QUESTIONS_PER_ROUND = 5
        
        # Count questions in current round
        current_round_questions = Question.query.filter_by(
            interview_id=interview.id,
            round_type=interview.current_round
        ).count()
        
        skip_round = data.get('skip_round', False)
        
        # Check if current round is complete
        if current_round_questions >= QUESTIONS_PER_ROUND or skip_round:
            # Move to next round
            try:
                current_index = ROUND_ORDER.index(interview.current_round)
                next_index = current_index + 1
                
                if next_index >= len(ROUND_ORDER):
                    # All rounds completed - finish interview
                    interview.status = 'completed'
                    interview.completed_at = datetime.utcnow()
                    db.session.commit()
                    
                    return jsonify({
                        'success': False,
                        'completed': True,
                        'message': 'Interview completed! All rounds finished.'
                    })
                else:
                    # Move to next round
                    completed_round = ROUND_ORDER[current_index]
                    interview.current_round = ROUND_ORDER[next_index]
                    interview.current_question_index = 0
                    db.session.commit()
                    
                    # Return round transition info
                    round_names = {
                        'tech': 'Technical Round',
                        'coding': 'Coding Round',
                        'hr': 'HR Round'
                    }

                    # Calculate score for the round just finished (for gamification)
                    completed_qs = Question.query.filter(
                        Question.interview_id == interview.id,
                        Question.round_type == completed_round,
                        Question.answer_score != None  # noqa: E711
                    ).all()
                    completed_round_score = (
                        sum(q.answer_score for q in completed_qs) / len(completed_qs)
                        if completed_qs else 0
                    )

                    return jsonify({
                        'success': True,
                        'round_transition': True,
                        'new_round': interview.current_round,
                        'round_name': round_names.get(interview.current_round, interview.current_round.upper()),
                        'completed_round': completed_round,
                        'completed_round_score': round(completed_round_score, 2),
                        'message': f"Moving to {round_names.get(interview.current_round, interview.current_round)} (Question {current_round_questions}/{QUESTIONS_PER_ROUND} completed)"
                    })
            except ValueError:
                pass
        
        # Calculate rolling performance score for adaptive difficulty
        answered_qs = Question.query.filter(
            Question.interview_id == interview.id,
            Question.round_type == interview.current_round,
            Question.answer_score != None  # noqa: E711
        ).all()
        if answered_qs:
            performance_score = sum(q.answer_score for q in answered_qs) / len(answered_qs)
        else:
            performance_score = None  # No data yet → default to medium difficulty

        # Generate question based on resume, current round and adaptive difficulty
        generated = generate_question(
            resume_data=interview.get_parsed_resume(),
            round_type=interview.current_round,
            previous_questions=[q.question_text for q in interview.questions],
            performance_score=performance_score
        )
        
        question_text = ""
        meta = None
        question_difficulty = 'medium'

        if isinstance(generated, dict):
            question_text = generated.get('text', '')
            meta = generated.get('meta')
            question_difficulty = generated.get('difficulty', 'medium')
        else:
            question_text = str(generated)

        # Save question to database
        question = Question(
            interview_id=interview.id,
            round_type=interview.current_round,
            question_text=question_text
        )
        db.session.add(question)

        # Increment question index
        interview.current_question_index = current_round_questions + 1

        db.session.commit()

        # Calculate progress
        total_questions = 13  # 5 tech + 3 coding + 5 hr
        answered_questions = Question.query.filter_by(interview_id=interview.id).count()
        progress_percentage = int((answered_questions / total_questions) * 100)

        response = {
            'success': True,
            'question_id': question.id,
            'question': question_text,
            'round': interview.current_round,
            'round_progress': f"{current_round_questions + 1}/{QUESTIONS_PER_ROUND}",
            'overall_progress': progress_percentage,
            'round_number': ROUND_ORDER.index(interview.current_round) + 1,
            'total_rounds': len(ROUND_ORDER),
            'total_questions': QUESTIONS_PER_ROUND,
            'difficulty': question_difficulty,
            'performance_score': round(performance_score, 1) if performance_score is not None else None
        }
        
        # Add metadata for coding round
        if meta:
            if 'test_cases' in meta:
                response['test_cases'] = meta['test_cases']
            if 'function_name' in meta:
                response['function_name'] = meta['function_name']
            if 'starter_code' in meta:
                response['starter_code'] = meta.get('starter_code', '')
            # Pass full meta so the frontend can render title, description, examples, constraints
            response['meta'] = meta
                
        return jsonify(response)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/submit-answer', methods=['POST'])
@login_required
def submit_answer():
    """Submit answer to a question"""
    try:
        data = request.get_json()
        question_id = data.get('question_id')
        answer_text = data.get('answer')
        
        question = Question.query.get(question_id)
        if not question or question.interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid question'}), 403
        
        # Save answer
        question.answer_text = answer_text
        question.answered_at = datetime.utcnow()
        
        # Analyze answer using Gemini
        evaluation = evaluate_answer(question.question_text, answer_text)
        
        question.answer_score = evaluation.get('score', 0)
        question.feedback = evaluation.get('feedback', '')
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'score': evaluation.get('score', 0),
            'feedback': evaluation.get('feedback', ''),
            'feedback_summary': evaluation.get('feedback_summary', ''),
            'key_strength': evaluation.get('key_strength', ''),
            'improvement_area': evaluation.get('improvement_area', ''),
            'ideal_answer': evaluation.get('ideal_answer', evaluation.get('suggested_answer', 'Not available.'))
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/analyze-emotion', methods=['POST'])
@login_required
def analyze_emotion():
    """Analyze emotion from video frame and verify identity"""
    try:
        data = request.get_json()
        interview_id = data.get('interview_id')
        image_data = data.get('image')  # Base64 encoded
        
        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid interview'}), 403
        
        # Decode image
        image_bytes = base64.b64decode(image_data.split(',')[1])
        
        # Detect emotion
        result = detect_emotion(image_bytes)
        
        # Verify Identity if baseline photo is available
        identity_verified = True
        identity_distance = 0.0
        identity_msg = 'Checked'
        if interview.baseline_photo_path:
            import os
            from app.services.emotion_detection import verify_face
            baseline_full_path = os.path.join(current_app.root_path, 'static', interview.baseline_photo_path)
            if os.path.exists(baseline_full_path):
                v_res = verify_face(image_bytes, baseline_full_path)
                if 'verified' in v_res:
                    identity_verified = v_res['verified']
                    identity_distance = v_res.get('distance', 1.0)
                    if not identity_verified:
                        identity_msg = 'Mismatch'
                        interview.violations += 1
                        # We could log this via the security log if we want
        
        # Log emotion
        emotion_log = EmotionLog(
            interview_id=interview.id,
            emotion=result['dominant_emotion'],
            confidence=result['confidence'],
            faces_detected=result['faces_count'],
            is_violation=(result['faces_count'] != 1 or not identity_verified)
        )
        db.session.add(emotion_log)
        
        # Update violations if multiple faces
        if result['faces_count'] != 1:
            interview.violations += 1
        
        db.session.commit()
        
        is_violation = (result['faces_count'] != 1 or not identity_verified)
        return jsonify({
            'success': True,
            'emotion': result['dominant_emotion'],
            'confidence': result['confidence'],
            'faces_count': result['faces_count'],
            'emotions': result.get('emotions', {}),  # All 7 scores 0-100
            'warning': is_violation,
            'is_violation': is_violation,
            'total_violations': interview.violations,
            'identity': {
                'verified': identity_verified,
                'distance': identity_distance,
                'msg': identity_msg
            }
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/set-baseline-photo', methods=['POST'])
@login_required
def set_baseline_photo():
    """Capture starting baseline photo of candidate for identity verification"""
    try:
        data = request.get_json()
        interview_id = session.get('interview_id') or data.get('interview_id')
        image_data = data.get('image')  # Base64 encoded snapshot
        
        if not interview_id or not image_data:
            return jsonify({'success': False, 'error': 'Missing parameters'}), 400
            
        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'success': False, 'error': 'Invalid interview'}), 403
            
        import os, uuid
        from werkzeug.utils import secure_filename
        from flask import current_app
        import base64
        
        image_bytes = base64.b64decode(image_data.split(',')[1])
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'baselines')
        os.makedirs(upload_dir, exist_ok=True)
        
        filename = f"baseline_{interview.id}_{uuid.uuid4().hex[:8]}.jpg"
        file_path = os.path.join(upload_dir, filename)
        
        with open(file_path, 'wb') as f:
            f.write(image_bytes)
            
        interview.baseline_photo_path = f"uploads/baselines/{filename}"
        db.session.commit()
        
        return jsonify({'success': True, 'path': interview.baseline_photo_path})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/log-violation', methods=['POST'])
@login_required
def log_violation():
    """Log a browser-level security violation (e.g., tab switch, copy/paste)"""
    try:
        data = request.get_json()
        interview_id = data.get('interview_id')
        reason = data.get('reason', 'Security violation')
        
        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid interview'}), 403
            
        interview.violations += 1
        db.session.commit()
        
        return jsonify({
            'success': True,
            'total_violations': interview.violations
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/analyze-audio', methods=['POST'])
@login_required
def analyze_audio():
    """Analyze audio for sentiment and transcription"""
    try:
        data = request.get_json()
        question_id = data.get('question_id')
        audio_data = data.get('audio')  # Base64 encoded
        
        question = Question.query.get(question_id)
        if not question or question.interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid question'}), 403
        
        # Decode audio
        audio_bytes = base64.b64decode(audio_data.split(',')[1])
        
        # Save temporarily
        temp_audio_path = os.path.join(current_app.config['UPLOAD_FOLDER'], f'temp_audio_{question_id}.wav')
        with open(temp_audio_path, 'wb') as f:
            f.write(audio_bytes)
        
        # Transcribe
        transcript = transcribe_audio(temp_audio_path)
        
        # Analyze sentiment
        analysis = analyze_audio(temp_audio_path, transcript)
        
        # Clean up
        os.remove(temp_audio_path)
        
        # Update question
        question.audio_transcript = transcript
        question.sentiment_score = analysis['sentiment']
        question.confidence_score = analysis['confidence']
        db.session.commit()
        
        return jsonify({
            'success': True,
            'transcript': transcript,
            'sentiment': analysis['sentiment'],
            'confidence': analysis['confidence']
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/generate-report', methods=['POST'])
@login_required
def create_report():
    """Generate PDF report for interview"""
    try:
        data = request.get_json()
        interview_id = data.get('interview_id')
        
        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid interview'}), 403
        
        # Generate report
        report_path = generate_report(interview)
        
        # Update interview
        interview.report_path = report_path
        db.session.commit()
        
        return jsonify({
            'success': True,
            'report_url': f'/static/reports/{os.path.basename(report_path)}'
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/update-round', methods=['POST'])
@login_required
def update_round():
    """Update interview round"""
    try:
        data = request.get_json()
        interview_id = data.get('interview_id')
        new_round = data.get('round')
        
        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid interview'}), 403
        
        interview.current_round = new_round
        interview.current_question_index = 0
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/verify-identity', methods=['POST'])
@login_required
def verify_identity():
    """Verify user identity against reference photo"""
    try:
        data = request.get_json()
        interview_id = data.get('interview_id')
        image_data = data.get('image')  # Base64 encoded
        
        from app.models import User
        user = User.query.get(session['user_id'])
        
        if not user.reference_photo_path:
            return jsonify({'success': True, 'verified': True, 'message': 'No reference photo set (Verification skipped)'})
        
        # Decode image
        image_bytes = base64.b64decode(image_data.split(',')[1])
        
        # Verify
        result = verify_face(image_bytes, user.reference_photo_path)
        
        if not result['verified']:
            # Log violation if verification fails
            interview = Interview.query.get(interview_id)
            if interview:
                interview.violations += 1
                db.session.commit()
        
        return jsonify({
            'success': True,
            'verified': result['verified'],
            'distance': result.get('distance', 0)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/run-code', methods=['POST'])
@login_required
def run_code():
    """Execute user code (for testing only, not submission)"""
    try:
        data = request.get_json()
        code = data.get('code')
        language = data.get('language', 'python')
        test_cases = data.get('test_cases', [])
        function_name = data.get('function_name')
        
        if not code:
            return jsonify({'error': 'No code provided'}), 400
        
        # Normalise test case keys: executor reads 'expected', but AI service writes 'output'
        for tc in test_cases:
            if 'expected' not in tc and 'output' in tc:
                tc['expected'] = tc['output']
        
        # Import the new code executor
        from app.services.code_executor import executor
        
        # Execute based on language
        if language == 'python':
            result = executor.execute_python(code, test_cases, function_name)
        elif language == 'javascript':
            result = executor.execute_javascript(code, test_cases, function_name)
        elif language == 'cpp':
            result = executor.execute_cpp(code, test_cases, function_name)
        elif language == 'java':
            result = executor.execute_java(code, test_cases, function_name)
        else:
            return jsonify({'error': f'Unsupported language: {language}'}), 400
        
        # Add complexity analysis
        if result['success']:
            complexity = executor.get_complexity_estimate(code)
            result['complexity'] = complexity
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/submit-code', methods=['POST'])
@login_required
def submit_code():
    """Submit code solution with full test case evaluation"""
    try:
        data = request.get_json()
        question_id = data.get('question_id')
        code = data.get('code')
        language = data.get('language', 'python')
        test_cases = data.get('test_cases', [])
        function_name = data.get('function_name')
        
        question = Question.query.get(question_id)
        if not question or question.interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid question'}), 403
        
        # Normalise test case keys: executor reads 'expected', but AI service writes 'output'
        for tc in test_cases:
            if 'expected' not in tc and 'output' in tc:
                tc['expected'] = tc['output']
        
        # Execute code with test cases
        from app.services.code_executor import executor
        
        if language == 'python':
            result = executor.execute_python(code, test_cases, function_name)
        elif language == 'javascript':
            result = executor.execute_javascript(code, test_cases, function_name)
        elif language == 'cpp':
            result = executor.execute_cpp(code, test_cases, function_name)
        elif language == 'java':
            result = executor.execute_java(code, test_cases, function_name)
        else:
            return jsonify({'error': f'Unsupported language: {language}'}), 400
        
        if not result.get('success') and not result.get('error'):
            result['error'] = 'Execution failed with no error message'
        
        # Save submission to database
        from app.models import CodeSubmission
        
        submission = CodeSubmission(
            question_id=question_id,
            interview_id=question.interview_id,
            code=code,
            language=language,
            test_cases_passed=result.get('passed_tests', 0),
            test_cases_total=result.get('total_tests', 0),
            execution_time=result.get('execution_time', 0),
            memory_used=result.get('memory_used', 0),
            score=0,
            is_correct=False,
            status='pending'
        )
        
        # Set test results
        submission.set_test_results(result.get('test_results', []))
        
        # Calculate score
        if result['success']:
            pass_rate = result['passed_tests'] / result['total_tests'] if result['total_tests'] > 0 else 0
            submission.score = pass_rate * 10  # 0-10 scale
            submission.is_correct = (pass_rate == 1.0)
            submission.status = 'passed' if submission.is_correct else 'failed'
        else:
            submission.error_message = result.get('error')
            submission.status = 'error'
        
        db.session.add(submission)
        
        # Get AI Feedback & Insights
        pass_rate = result['passed_tests'] / result['total_tests'] if result['total_tests'] > 0 else 0
        code_evaluation = evaluate_code(question.question_text, code, language, pass_rate)
        
        # Update question with best score
        if submission.score > question.answer_score or question.answer_score == 0:
            question.answer_text = f"```{language}\n{code}\n```"
            question.answer_score = submission.score
            question.answered_at = datetime.utcnow()
            
            feedback_str = f"Code evaluated against our automated test suite. Passed {submission.test_cases_passed} out of {submission.test_cases_total} test cases."
            if submission.error_message:
                feedback_str += f" Encountered error: {submission.error_message}"
            else:
                feedback_str += f" Estimated Runtime: {submission.execution_time:.2f}ms."
            
            feedback_str += f"\n\nAI Insights: {code_evaluation.get('feedback_summary', '')}"
            question.feedback = feedback_str
        
        db.session.commit()
        
        # Get complexity
        complexity = executor.get_complexity_estimate(code)
        
        return jsonify({
            'success': True,
            'submission_id': submission.id,
            'score': submission.score,
            'is_correct': submission.is_correct,
            'test_results': result.get('test_results', []),
            'passed_tests': result.get('passed_tests', 0),
            'total_tests': result.get('total_tests', 0),
            'execution_time': result.get('execution_time', 0),
            'memory_used': result.get('memory_used', 0),
            'complexity': complexity,
            'error': result.get('error'),
            
            # Additional AI Evaluation fields for Feedback Modal
            'feedback_summary': code_evaluation.get('feedback_summary', ''),
            'key_strength': code_evaluation.get('key_strength', ''),
            'improvement_area': code_evaluation.get('improvement_area', ''),
            'ideal_answer': code_evaluation.get('ideal_answer', '')
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/get-submissions/<int:question_id>', methods=['GET'])
@login_required
def get_submissions(question_id):
    """Get all submissions for a question"""
    try:
        question = Question.query.get(question_id)
        if not question or question.interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid question'}), 403
        
        from app.models import CodeSubmission
        
        submissions = CodeSubmission.query.filter_by(question_id=question_id)\
            .order_by(CodeSubmission.submitted_at.desc()).all()
        
        submissions_data = []
        for sub in submissions:
            submissions_data.append({
                'id': sub.id,
                'code': sub.code,
                'language': sub.language,
                'score': sub.score,
                'is_correct': sub.is_correct,
                'test_cases_passed': sub.test_cases_passed,
                'test_cases_total': sub.test_cases_total,
                'execution_time': sub.execution_time,
                'memory_used': sub.memory_used,
                'status': sub.status,
                'error_message': sub.error_message,
                'submitted_at': sub.submitted_at.isoformat(),
                'test_results': sub.get_test_results()
            })
        
        return jsonify({
            'success': True,
            'submissions': submissions_data,
            'total': len(submissions_data)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/get-hints/<int:question_id>', methods=['GET'])
@login_required
def get_hints(question_id):
    """Get available hints for a question"""
    try:
        question = Question.query.get(question_id)
        if not question or question.interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid question'}), 403
        
        from app.models import Hint, HintUsage
        
        # Get all hints for this question
        hints = Hint.query.filter_by(question_id=question_id)\
            .order_by(Hint.hint_level).all()
        
        # Get hints already used
        used_hints = HintUsage.query.filter_by(
            interview_id=question.interview_id,
            question_id=question_id
        ).all()
        used_hint_ids = {h.hint_id for h in used_hints}
        
        hints_data = []
        for hint in hints:
            hints_data.append({
                'id': hint.id,
                'level': hint.hint_level,
                'level_name': ['Approach', 'Pseudocode', 'Solution'][hint.hint_level - 1] if hint.hint_level <= 3 else 'Hint',
                'text': hint.hint_text if hint.id in used_hint_ids else None,  # Only show if used
                'point_deduction': hint.point_deduction,
                'is_used': hint.id in used_hint_ids
            })
        
        return jsonify({
            'success': True,
            'hints': hints_data,
            'total_hints': len(hints_data),
            'used_hints': len(used_hint_ids)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/use-hint', methods=['POST'])
@login_required
def use_hint():
    """Use a hint (unlocks it and deducts points)"""
    try:
        data = request.get_json()
        hint_id = data.get('hint_id')
        question_id = data.get('question_id')
        
        from app.models import Hint, HintUsage
        
        hint = Hint.query.get(hint_id)
        question = Question.query.get(question_id)
        
        if not hint or not question:
            return jsonify({'error': 'Invalid hint or question'}), 404
        
        if question.interview.user_id != session['user_id']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Check if already used
        existing = HintUsage.query.filter_by(
            interview_id=question.interview_id,
            hint_id=hint_id,
            question_id=question_id
        ).first()
        
        if existing:
            return jsonify({'error': 'Hint already used'}), 400
        
        # Record usage
        usage = HintUsage(
            interview_id=question.interview_id,
            hint_id=hint_id,
            question_id=question_id
        )
        db.session.add(usage)
        
        # Deduct points from question score
        question.answer_score = max(0, question.answer_score - hint.point_deduction)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'hint_text': hint.hint_text,
            'point_deduction': hint.point_deduction,
            'new_score': question.answer_score
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/leaderboard', methods=['GET'])
@login_required
def get_leaderboard():
    """Get global leaderboard"""
    try:
        from app.models import Leaderboard, User
        
        # Get top 100 entries
        entries = Leaderboard.query.join(User)\
            .order_by(Leaderboard.overall_score.desc())\
            .limit(100).all()
        
        leaderboard_data = []
        for idx, entry in enumerate(entries, 1):
            entry.global_rank = idx
            db.session.add(entry)
            
            leaderboard_data.append({
                'rank': idx,
                'username': entry.user.username,
                'overall_score': entry.overall_score,
                'tech_score': entry.tech_score,
                'coding_score': entry.coding_score,
                'hr_score': entry.hr_score,
                'is_current_user': entry.user_id == session['user_id']
            })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'leaderboard': leaderboard_data
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/emotion-summary/<int:interview_id>', methods=['GET'])
@login_required
def emotion_summary(interview_id):
    """Get aggregated emotion summary for an interview"""
    try:
        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid interview'}), 403

        logs = EmotionLog.query.filter_by(interview_id=interview_id)\
            .order_by(EmotionLog.timestamp.asc()).all()

        if not logs:
            return jsonify({
                'success': True,
                'total_samples': 0,
                'emotion_distribution': {},
                'dominant_emotion': 'neutral',
                'average_confidence': 0,
                'violations': 0,
                'timeline': []
            })

        emotion_counts = {}
        total_confidence = 0
        violations = 0
        timeline = []

        for log in logs:
            emo = log.emotion.lower()
            emotion_counts[emo] = emotion_counts.get(emo, 0) + 1
            total_confidence += log.confidence
            if log.is_violation:
                violations += 1
            timeline.append({
                'time': log.timestamp.isoformat(),
                'emotion': emo,
                'confidence': round(log.confidence * 100, 1)
            })

        total = len(logs)
        distribution = {k: round((v / total) * 100, 1) for k, v in emotion_counts.items()}
        dominant = max(emotion_counts, key=emotion_counts.get)

        # Behavioral scores derived from emotions
        positive_pct = distribution.get('happy', 0)
        negative_pct = distribution.get('angry', 0) + distribution.get('fear', 0) + distribution.get('disgust', 0)
        neutral_pct = distribution.get('neutral', 0)

        engagement_score = min(100, round(100 - neutral_pct * 0.5))
        confidence_score = min(100, round(positive_pct * 1.2 + neutral_pct * 0.5))
        stress_score = min(100, round(negative_pct * 1.5))

        return jsonify({
            'success': True,
            'total_samples': total,
            'emotion_distribution': distribution,
            'dominant_emotion': dominant,
            'average_confidence': round((total_confidence / total) * 100, 1),
            'violations': interview.violations,  # Now pulling total violations directly from the model
            'timeline': timeline,
            'behavioral': {
                'engagement': engagement_score,
                'confidence': confidence_score,
                'stress': stress_score
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/streaming-transcribe', methods=['POST'])
@login_required
def streaming_transcribe():
    """Real-time transcription streaming endpoint"""
    try:
        data = request.get_json()
        audio_data = data.get('audio')
        question_id = data.get('question_id')
        
        if not audio_data:
            return jsonify({'error': 'No audio data'}), 400
        
        # Decode audio
        audio_bytes = base64.b64decode(audio_data.split(',')[1])
        
        # Save temporarily
        temp_audio_path = os.path.join(current_app.config['UPLOAD_FOLDER'], f'stream_{question_id}_{datetime.utcnow().timestamp()}.wav')
        with open(temp_audio_path, 'wb') as f:
            f.write(audio_bytes)
        
        # Transcribe
        transcript = transcribe_audio(temp_audio_path)
        
        # Clean up
        os.remove(temp_audio_path)
        
        return jsonify({
            'success': True,
            'transcript': transcript,
            'timestamp': datetime.utcnow().isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/gamification-status', methods=['GET'])
@login_required
def gamification_status():
    """Return the current user's XP, level, and earned badges"""
    try:
        from app.models import User
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify({
            'success': True,
            'xp': user.xp or 0,
            'level': user.level or 1,
            'badges': user.get_badges()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/award-milestone', methods=['POST'])
@login_required
def award_milestone():
    """Award XP + badges for completing a round mid-interview"""
    try:
        from app.models import User
        data = request.get_json()
        interview_id = data.get('interview_id')
        round_type = data.get('round')      # 'tech' | 'coding' | 'hr'
        round_score = data.get('score', 0)  # 0-10 float

        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid interview'}), 403

        user = User.query.get(session['user_id'])

        # XP per question answered in that round (5 questions)
        xp_gain = max(5, int(round_score * 5))   # 5-50 XP per round
        user.add_xp(xp_gain)

        new_badges = []

        # Round-specific milestone badges
        if round_type == 'tech' and round_score >= 8:
            b = 'Tech Wizard'
            if b not in user.get_badges():
                user.add_badge(b)
                new_badges.append({'name': b, 'icon': '🧙', 'desc': 'Scored 8+/10 in Technical Round'})

        if round_type == 'coding' and round_score >= 9:
            b = 'Code Master'
            if b not in user.get_badges():
                user.add_badge(b)
                new_badges.append({'name': b, 'icon': '💻', 'desc': 'Near-perfect score in Coding Round'})

        if round_type == 'hr' and round_score >= 8:
            b = 'People Person'
            if b not in user.get_badges():
                user.add_badge(b)
                new_badges.append({'name': b, 'icon': '🤝', 'desc': 'Excellent interpersonal skills in HR Round'})

        if round_type == 'tech' and round_score >= 5:
            b = 'Problem Solver'
            if b not in user.get_badges():
                user.add_badge(b)
                new_badges.append({'name': b, 'icon': '🧩', 'desc': 'Completed the Technical Round'})

        if round_type == 'coding' and round_score >= 5:
            b = 'Algorithm Ace'
            if b not in user.get_badges():
                user.add_badge(b)
                new_badges.append({'name': b, 'icon': '⚡', 'desc': 'Completed the Coding Round'})

        if round_type == 'hr' and round_score >= 5:
            b = 'Communicator'
            if b not in user.get_badges():
                user.add_badge(b)
                new_badges.append({'name': b, 'icon': '🗣️', 'desc': 'Completed the HR Round'})

        db.session.commit()

        return jsonify({
            'success': True,
            'xp_gained': xp_gain,
            'total_xp': user.xp,
            'level': user.level,
            'new_badges': new_badges,
            'all_badges': user.get_badges()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
