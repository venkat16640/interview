from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, send_file
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from app import db
from app.models import User, Interview, Question
from app.routes.main import login_required
from app.services.resume_parser import parse_resume
from app.services.ai_service import generate_question
from app.services.report_service import generate_pdf_report

bp = Blueprint('interview', __name__, url_prefix='/interview')

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


@bp.route('/start', methods=['GET', 'POST'])
@login_required
def start():
    """Start new interview - Resume upload"""
    if request.method == 'POST':
        # Check if file was uploaded
        if 'resume' not in request.files:
            flash('No resume file uploaded!', 'danger')
            return redirect(request.url)
        
        file = request.files['resume']
        
        if file.filename == '':
            flash('No file selected!', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{session['user_id']}_{timestamp}_{filename}"
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Parse resume
            try:
                parsed_data = parse_resume(filepath)
            except Exception as e:
                flash(f'Error parsing resume: {str(e)}', 'danger')
                return redirect(request.url)
            
            # Create new interview session
            interview = Interview(user_id=session['user_id'], resume_path=filepath)
            interview.set_parsed_resume(parsed_data)
            db.session.add(interview)
            db.session.commit()
            
            session['interview_id'] = interview.id
            flash('Resume uploaded successfully! Preparing your interview...', 'success')
            return redirect(url_for('interview.welcome_lobby'))
        else:
            flash('Invalid file type! Please upload PDF or DOCX.', 'danger')
            return redirect(request.url)
    
    return render_template('interview/start.html')


@bp.route('/welcome-lobby')
@login_required
def welcome_lobby():
    """Professional welcome lobby with company branding and countdown"""
    if 'interview_id' not in session:
        flash('Please start an interview first!', 'warning')
        return redirect(url_for('interview.start'))
    
    user = User.query.get(session['user_id'])
    return render_template('interview/welcome_lobby.html', user=user)



@bp.route('/system-check')
@login_required
def system_check():
    """Perform system checks before interview"""
    if 'interview_id' not in session:
        flash('Please start an interview first!', 'warning')
        return redirect(url_for('interview.start'))
    return render_template('interview/system_check.html')


@bp.route('/conduct')
@login_required
def conduct():
    """Main interview interface"""
    if 'interview_id' not in session:
        flash('Please start an interview first!', 'warning')
        return redirect(url_for('interview.start'))
    
    interview = Interview.query.get(session['interview_id'])
    if not interview or interview.user_id != session['user_id']:
        flash('Invalid interview session!', 'danger')
        return redirect(url_for('main.dashboard'))
    
    return render_template('interview/conduct.html', interview=interview)


@bp.route('/complete')
@login_required
def complete():
    """Complete interview and show results"""
    if 'interview_id' not in session:
        flash('No interview session found!', 'warning')
        return redirect(url_for('main.dashboard'))
    
    interview = Interview.query.get(session['interview_id'])
    if not interview:
        flash('Interview not found!', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Calculate scores if not set (simple aggregation)
    if interview.overall_score == 0:
        questions = Question.query.filter_by(interview_id=interview.id).all()
        if questions:
            tech_q = [q for q in questions if q.round_type == 'tech']
            hr_q = [q for q in questions if q.round_type == 'hr']
            coding_q = [q for q in questions if q.round_type == 'coding']
            
            interview.tech_score = sum(q.answer_score for q in tech_q) / len(tech_q) if tech_q else 0
            interview.hr_score = sum(q.answer_score for q in hr_q) / len(hr_q) if hr_q else 0
            interview.coding_score = sum(q.answer_score for q in coding_q) / len(coding_q) if coding_q else 0
            
            interview.overall_score = (interview.tech_score + interview.hr_score + interview.coding_score) / 3

    # Award Gamification Rewards
    user = User.query.get(session['user_id'])
    xp_earned = int(interview.overall_score * 10) # 10 xp per point
    user.add_xp(xp_earned)
    
    # Check for Badges
    if interview.tech_score >= 8:
        user.add_badge('Tech Wizard')
    if interview.coding_score >= 9:
        user.add_badge('Code Master')
    if interview.hr_score >= 8:
        user.add_badge('People Person')
    if interview.overall_score >= 7:
        user.add_badge('Interview Pro')
        
    flash(f"You earned {xp_earned} XP!", "success")

    # Mark as completed
    interview.status = 'completed'
    interview.completed_at = datetime.utcnow()
    
    # Generate Report
    reports_dir = os.path.join(current_app.static_folder, 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    report_filename = f"report_{interview.id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    report_path = os.path.join(reports_dir, report_filename)
    
    try:
        generate_pdf_report(interview, user, report_path)
        interview.report_path = report_filename 
    except Exception as e:
        print(f"Error generating report: {e}")

    db.session.commit()
    
    # Clear session
    session.pop('interview_id', None)
    
    return render_template('interview/complete.html', interview=interview, current_user=user)

@bp.route('/download_report/<int:interview_id>')
@login_required
def download_report(interview_id):
    interview = Interview.query.get_or_404(interview_id)
    
    # Security check
    if interview.user_id != session['user_id']:
        flash("You do not have permission to view this report.", "danger")
        return redirect(url_for('main.dashboard'))
        
    if not interview.report_path:
        flash("Report not found.", "warning")
        return redirect(url_for('main.dashboard'))
        
    reports_dir = os.path.join(current_app.static_folder, 'reports')
    file_path = os.path.join(reports_dir, interview.report_path)
    
    if not os.path.exists(file_path):
        # Try to regenerate
        try:
            generate_pdf_report(interview, interview.user, file_path)
        except Exception as e:
            flash("Error generating report file.", "danger")
            return redirect(url_for('main.dashboard'))

    return send_file(file_path, as_attachment=True)
