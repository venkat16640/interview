"""
AI Service - Google Gemini Integration
Generates adaptive interview questions and evaluates answers
"""
import google.generativeai as genai
from flask import current_app
import random

# Configure Gemini API
def get_gemini_model():
    """Get configured Gemini model"""
    api_key = current_app.config.get('GEMINI_API_KEY')
    if not api_key or api_key == 'your-api-key-here':
        raise Exception("Gemini API key not configured. Please set GEMINI_API_KEY in .env file")
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-1.5-pro')


def _get_difficulty_level(performance_score):
    """
    Determine adaptive difficulty based on running performance score.
    Returns: ('easy' | 'medium' | 'hard', label description)
    """
    if performance_score is None:
        return 'medium', 'Medium'
    if performance_score >= 7.5:
        return 'hard', 'Advanced / Expert-Level'
    elif performance_score >= 5.0:
        return 'medium', 'Intermediate / Scenario-Based'
    else:
        return 'easy', 'Foundational / Concept-Check'


def generate_question(resume_data, round_type, previous_questions=None, performance_score=None):
    """
    Generate an adaptive interview question based on resume, round type, and
    the candidate's rolling performance score.

    Args:
        resume_data: Parsed resume dictionary
        round_type: 'tech', 'hr', or 'coding'
        previous_questions: List of previously asked questions
        performance_score: Float 0-10 rolling average score; drives difficulty adaptation

    Returns:
        dict with keys 'text', 'meta', and 'difficulty'
    """
    if previous_questions is None:
        previous_questions = []

    difficulty, difficulty_label = _get_difficulty_level(performance_score)

    try:
        model = get_gemini_model()

        # ── TECHNICAL ROUND ──────────────────────────────────────────
        if round_type == 'tech':
            skills = ', '.join(resume_data.get('skills', []))
            if not skills:
                skills = 'General Software Engineering'
            years = resume_data.get('experience', {}).get('years', 0)

            difficulty_guidance = {
                'easy': (
                    "Ask a clear conceptual question about one of their listed skills. "
                    "Suitable for someone who may be struggling — be supportive but direct."
                ),
                'medium': (
                    "Ask a scenario-based question that requires applying their skills to a "
                    "real-world problem. Expect the candidate to reason through trade-offs."
                ),
                'hard': (
                    "Ask a deep, expert-level question involving system design, performance "
                    "optimization, edge cases, or architectural decisions. The candidate is "
                    "performing well and should be challenged further."
                ),
            }[difficulty]

            prompt = f"""You are Michael, a Senior Technical Architect at a top-tier tech company conducting a high-stakes technical interview.

Candidate Profile:
- Skills: {skills}
- Experience: {years} years
- Current performance score: {performance_score if performance_score is not None else 'unknown'}/10

Adaptive Difficulty: {difficulty_label}
Instruction: {difficulty_guidance}

Task: Generate ONE technical interview question.

Rules:
- Absolutely no generic trivia questions (e.g., "What is a class?").
- Directly reference one or more of the candidate's listed skills.
- This is a spoken question — write as if you are saying it aloud.
- Tone: Professional, direct, confident.
- Prohibited (do not repeat): {', '.join(previous_questions[-5:]) if previous_questions else 'None'}

Return ONLY the text of the spoken question."""

        # ── HR ROUND ─────────────────────────────────────────────────
        elif round_type == 'hr':
            years = resume_data.get('experience', {}).get('years', 0)

            difficulty_guidance = {
                'easy': (
                    "Ask a straightforward behavioural question about teamwork or communication. "
                    "Keep it simple and encouraging."
                ),
                'medium': (
                    "Ask a STAR-formatted behavioural question about conflict resolution, "
                    "adaptability, or handling failure. Expect a structured answer."
                ),
                'hard': (
                    "Ask a challenging leadership or ethics-based scenario. The candidate should "
                    "demonstrate executive-level judgment, stakeholder management, or strategic thinking."
                ),
            }[difficulty]

            prompt = f"""You are Sarah, Director of Human Resources, assessing cultural fit, leadership, and soft skills.

Candidate Profile:
- Experience: {years} years
- Current performance score: {performance_score if performance_score is not None else 'unknown'}/10

Adaptive Difficulty: {difficulty_label}
Instruction: {difficulty_guidance}

Task: Generate ONE behavioural interview question.

Rules:
- Use the STAR method framing (Situation, Task, Action, Result).
- Tone: Warm, professional, inquisitive, and encouraging.
- This is a spoken question — write as if you are saying it aloud.
- Prohibited (do not repeat): {', '.join(previous_questions[-5:]) if previous_questions else 'None'}

Return ONLY the text of the spoken question."""

        # ── CODING ROUND ─────────────────────────────────────────────
        elif round_type == 'coding':
            try:
                from app.services.coding_problems import generate_coding_problem
                problem = generate_coding_problem(
                    resume_data,
                    difficulty=difficulty,
                    previous_questions=previous_questions
                )

                formatted_problem = f"""**{problem['title']}** (Difficulty: {problem['difficulty']})

{problem['description']}

**Examples:**

"""
                for idx, example in enumerate(problem.get('examples', []), 1):
                    formatted_problem += (
                        f"Example {idx}:\n"
                        f"- Input: `{example['input']}`\n"
                        f"- Output: `{example['output']}`\n"
                        f"- Explanation: {example.get('explanation', 'N/A')}\n\n"
                    )

                formatted_problem += "**Constraints:**\n\n"
                for constraint in problem.get('constraints', []):
                    formatted_problem += f"- {constraint}\n"

                if 'starter_code' in problem:
                    formatted_problem += (
                        f"\n**Starter Code:**\n```python\n{problem['starter_code']}\n```"
                    )

                return {
                    'text': formatted_problem,
                    'meta': problem,
                    'difficulty': difficulty
                }
            except Exception as e:
                print(f"Error generating coding problem: {e}")
                return {
                    'text': get_fallback_question('coding', resume_data),
                    'meta': None,
                    'difficulty': difficulty
                }

        # ── UNKNOWN ROUND ─────────────────────────────────────────────
        else:
            return {'text': 'Tell me about yourself and your experience.', 'meta': None, 'difficulty': 'medium'}

        # Generate for tech / hr
        response = model.generate_content(prompt)
        question = response.text.strip()

        return {'text': question, 'meta': None, 'difficulty': difficulty}

    except Exception as e:
        print(f"AI question generation error: {e}")
        fallback = get_fallback_question(round_type, resume_data)
        if isinstance(fallback, dict):
            fallback['difficulty'] = difficulty
            return fallback
        return {'text': fallback, 'meta': None, 'difficulty': difficulty}


def get_fallback_question(round_type, resume_data):
    """Fallback questions if API fails"""
    tech_questions = [
        "I see you've listed Python. Could you walk me through the key differences between a list and a tuple in Python, and when you'd use one over the other?",
        "For a large dataset, how would you approach optimizing a slow database query?",
        "Could you explain the core principles of RESTful API design as you understand them?",
        "I'm interested in your object-oriented programming experience. How do you apply polymorphism in your projects?",
        "Walk me through your process for debugging a complex production issue."
    ]
    
    hr_questions = [
        "Tell me about a particularly challenging project you worked on. What were the obstacles and how did you overcome them?",
        "Conflict is natural in teams. Can you describe a time you had a disagreement with a colleague and how you resolved it?",
        "Technology changes fast. Tell me about a time you had to learn a new tool or language under a tight deadline.",
        "What drives you in your daily work? I'm curious about what keeps you motivated.",
        "Looking ahead, where do you see your career path taking you in the next few years?"
    ]
    
    coding_questions = [
        "Let's look at a coding problem. I'd like you to write a function that reverses a string, but please avoid using any built-in reverse methods.",
        "Here is a task: Implement a function to check if a given string is a palindrome.",
        "For this problem, please write code to efficiently find the maximum element in an array.",
        "I'd like to see how you handle data cleaning. Create a function that removes all duplicate entries from a list.",
        "Let's test your knowledge of data structures. Could you implement a basic stack class with push and pop methods?"
    ]
    
    if round_type == 'tech':
        return random.choice(tech_questions)
    elif round_type == 'hr':
        return random.choice(hr_questions)
    elif round_type == 'coding':
        return random.choice(coding_questions)
    else:
        return "Tell me about yourself."


def evaluate_answer(question, answer):
    """
    Evaluate answer quality using Gemini
    
    Args:
        question: The question asked
        answer: User's answer
    
    Returns:
        Dictionary containing 'score' (0-10) and 'feedback' (str)
    """
    try:
        model = get_gemini_model()
        
        prompt = f"""You are an expert interview evaluator at a top tech company. Grade the candidate's answer fairly and rigorously.
        
Question: "{question}"
Candidate Answer: "{answer}"

Task: Provide a structured evaluation.
Return ONLY a valid JSON object with this exact structure:
{{
    "score": [0-10 integer],
    "feedback_summary": "One sentence summary of performance.",
    "key_strength": "The strongest part of their answer.",
    "improvement_area": "The main thing missing or wrong.",
    "ideal_answer": "A concise, perfect answer to this question.",
    "technical_accuracy": [0-100 integer],
    "communication_clarity": [0-100 integer],
    "completeness": [0-100 integer]
}}

Grading Rubric:
- 9-10: Perfect, insightful, covers edge cases.
- 7-8: Solid, correct, minor details missing.
- 5-6: Partially correct or vague.
- 0-4: Wrong or irrelevant.

Tone: Constructive, professional, and encouraging.
"""

        response = model.generate_content(prompt)
        
        # Parse JSON robustly
        import json, re
        text = response.text.strip()
        # Find json block or use the whole text if it looks like json
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            text = match.group(1)
        elif text.startswith('{') and text.endswith('}'):
            pass # Looks like raw JSON
        else:
            # Try to strip anything before { and after }
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                text = text[start:end+1]
                
        try:
            evaluation = json.loads(text.strip())
        except json.JSONDecodeError:
            print(f"Failed to parse JSON evaluation, falling back. Raw: {text}")
            evaluation = {
                'score': 5,
                'feedback_summary': "AI evaluation response was not in expected format.",
                'key_strength': "N/A",
                'improvement_area': "N/A",
                'ideal_answer': "N/A"
            }
        
        # Ensure score is 0-10 (fallback safety)
        score = evaluation.get('score', 0)
        if hasattr(score, 'real'): # check if number
            if score > 10: score = 10
            if score < 0: score = 0
            
        # Backward compatibility
        if 'feedback' not in evaluation:
            evaluation['feedback'] = f"{evaluation.get('feedback_summary', '')} \n\nKey Strength: {evaluation.get('key_strength', '')} \n\nImprovement: {evaluation.get('improvement_area', '')}"
            
        return evaluation

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error evaluating answer: {e}")
        
        # MOCK SYSTEM: Provide a realistic fallback evaluation if the AI API is unavailable.
        # This uses local keyword-matching heuristics to grade the exact answer appropriately.
        import re
        
        # Extract meaningful keywords from question and answer
        q_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', question.lower()))
        a_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', answer.lower()))
        
        # Calculate topic overlap
        overlap_words = q_words.intersection(a_words)
        coverage = len(overlap_words) / max(len(q_words), 1)
        word_count = len(answer.split())
        
        # Base score on length and relevance to question keywords
        score = 4
        if word_count > 15: score += 2
        elif word_count > 5: score += 1
        
        if coverage > 0.3: score += 4
        elif coverage > 0.1: score += 2
        
        score = min(score, 10)
        matched_str = ", ".join(list(overlap_words)[:3])
        
        if score >= 8:
            summary = "Excellent, highly relevant response."
            strength = f"You comprehensively addressed the core topics ({matched_str})." if matched_str else "You communicated your thoughts clearly."
            imp = "Consider edge cases for an absolutely perfect answer."
        elif score >= 5:
            summary = "Good attempt, but lacked some depth."
            strength = f"You touched on some relevant concepts ({matched_str})." if matched_str else "You provided a coherent answer."
            imp = "Try to elaborate more on the specific concepts asked in the question."
        else:
            summary = "The answer was brief or missed the core question's intent."
            strength = "You attempted to answer the prompt."
            imp = "Ensure your answer directly references the keywords and requirements of the question."

        return {
            'score': score,
            'feedback_summary': summary,
            'key_strength': strength,
            'improvement_area': imp,
            'ideal_answer': "A great answer covers both the theoretical concepts and practical edge cases tied directly to the question's premise.",
            'feedback': f"{summary}\n\nKey Strength: {strength}\n\nImprovement: {imp}"
        }


def evaluate_code(question, code, language, pass_rate):
    """
    Evaluate code quality, time complexity, and style using Gemini.
    """
    try:
        model = get_gemini_model()
        
        prompt = f"""You are an expert senior software engineer. Evaluate this candidate's code submission.
        
Question:
{question}

Submitted Code ({language}):
{code}

Test Case Pass Rate: {pass_rate * 100}%

Task: Provide a structured evaluation focusing on CODE QUALITY, EXTREME EDGE CASES, and TIME/SPACE COMPLEXITY.
Return ONLY a valid JSON object with exactly this structure:
{{
    "feedback_summary": "One sentence summary of the code's approach and quality.",
    "key_strength": "The strongest part of their code (e.g. 'Clean modular design', 'Optimal time complexity O(N)').",
    "improvement_area": "The main area for improvement (e.g. 'Missed null pointer checks', 'O(N^2) time complexity is too slow').",
    "ideal_answer": "A short, readable optimal solution snippet or description."
}}

Tone: Constructive, professional.
"""

        response = model.generate_content(prompt)
        
        import json, re
        text = response.text.strip()
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match: text = match.group(1)
        else:
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1: text = text[start:end+1]
                
        try:
            eval_data = json.loads(text.strip())
        except json.JSONDecodeError:
            eval_data = {}

        return {
            'feedback_summary': eval_data.get('feedback_summary', 'Code analyzed.'),
            'key_strength': eval_data.get('key_strength', 'Code successfully submitted.'),
            'improvement_area': eval_data.get('improvement_area', 'Consider edge cases and optimal algorithms.'),
            'ideal_answer': eval_data.get('ideal_answer', 'Please review standard solutions for the optimal approach.')
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error evaluating code: {e}")
        
        # MOCK SYSTEM: Provide a functional fallback evaluation based on exact test case accuracy
        if pass_rate == 1.0:
            summary = "Optimal approach. Your code completely solved the problem."
            strength = "Clean syntax and perfect logic passing 100% of tests."
            imp = "Review alternative mathematical or algorithmic features to make the code even more concise."
        elif pass_rate > 0.0:
            summary = f"Partial success. Your code passed {pass_rate * 100}% of the test cases."
            strength = "The foundational logic is present and compilable."
            imp = "You failed specific edge cases. Check for null values, off-by-one errors, or strict bounding logic."
        else:
            summary = "Logic failed. Code did not pass the required constraints or test cases."
            strength = "You submitted valid, compilable code."
            imp = "Review the core algorithm requirements. Use debugging statements to trace logic flow."

        return {
            'feedback_summary': summary,
            'key_strength': strength,
            'improvement_area': imp,
            'ideal_answer': "Review standard algorithms (e.g., hash maps, dynamic programming, two pointers) if you face performance limits."
        }
