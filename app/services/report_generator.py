"""
Report Generation Service
Generates comprehensive PDF reports with emotion timeline, scores, and feedback
"""
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas
import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime
import os
from flask import current_app
from app.services.emotion_detection import analyze_emotion_sequence


def create_emotion_timeline_chart(emotion_logs, output_path):
    """Create emotion timeline visualization"""
    if not emotion_logs:
        return None
    
    # Prepare data
    timestamps = [log.timestamp for log in emotion_logs]
    emotions = [log.emotion for log in emotion_logs]
    
    # Create emotion encoding
    emotion_map = {
        'happy': 5, 'neutral': 3, 'sad': 1,
        'angry': 0, 'surprise': 4, 'fear': 2, 'disgust': 1
    }
    emotion_values = [emotion_map.get(e, 3) for e in emotions]
    
    # Create plot
    plt.figure(figsize=(10, 4))
    plt.plot(timestamps, emotion_values, marker='o', linestyle='-', linewidth=2)
    plt.xlabel('Time')
    plt.ylabel('Emotion State')
    plt.title('Emotion Timeline During Interview')
    plt.yticks([0, 1, 2, 3, 4, 5], ['Angry', 'Sad/Disgust', 'Fear', 'Neutral', 'Surprise', 'Happy'])
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    return output_path


def create_emotion_distribution_chart(emotion_stats, output_path):
    """Create emotion distribution pie chart"""
    distribution = emotion_stats.get('emotion_distribution', {})
    
    if not distribution:
        return None
    
    emotions = list(distribution.keys())
    percentages = list(distribution.values())
    
    colors_map = {
        'happy': '#4CAF50',
        'neutral': '#9E9E9E',
        'sad': '#2196F3',
        'angry': '#F44336',
        'surprise': '#FF9800',
        'fear': '#9C27B0',
        'disgust': '#795548'
    }
    
    chart_colors = [colors_map.get(e, '#607D8B') for e in emotions]
    
    plt.figure(figsize=(8, 6))
    plt.pie(percentages, labels=emotions, autopct='%1.1f%%', colors=chart_colors, startangle=90)
    plt.title('Emotion Distribution')
    plt.tight_layout()
    
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    return output_path


def calculate_overall_score(interview):
    """Calculate overall interview score"""
    tech_count = len([q for q in interview.questions if q.round_type == 'tech'])
    hr_count = len([q for q in interview.questions if q.round_type == 'hr'])
    coding_count = len([q for q in interview.questions if q.round_type == 'coding'])
    
    # Calculate average scores per round
    tech_scores = [q.answer_score for q in interview.questions if q.round_type == 'tech' and q.answer_score]
    hr_scores = [q.answer_score for q in interview.questions if q.round_type == 'hr' and q.answer_score]
    coding_scores = [q.answer_score for q in interview.questions if q.round_type == 'coding' and q.answer_score]
    
    tech_avg = sum(tech_scores) / len(tech_scores) if tech_scores else 0
    hr_avg = sum(hr_scores) / len(hr_scores) if hr_scores else 0
    coding_avg = sum(coding_scores) / len(coding_scores) if coding_scores else 0
    
    # Weighted average (40% tech, 30% coding, 30% hr)
    overall = (tech_avg * 0.4 + coding_avg * 0.3 + hr_avg * 0.3) * 10
    
    # Update interview scores
    interview.tech_score = tech_avg
    interview.hr_score = hr_avg
    interview.coding_score = coding_avg
    interview.overall_score = overall
    
    return {
        'tech': tech_avg,
        'hr': hr_avg,
        'coding': coding_avg,
        'overall': overall
    }


def generate_feedback(interview, scores, emotion_stats):
    """Generate personalized feedback"""
    feedback = []
    
    # Performance feedback
    if scores['overall'] >= 70:
        feedback.append("Excellent performance! You demonstrated strong technical and communication skills.")
    elif scores['overall'] >= 50:
        feedback.append("Good performance overall. There are areas for improvement.")
    else:
        feedback.append("You showed potential, but there's significant room for growth.")
    
    # Technical feedback
    if scores['tech'] < 5:
        feedback.append("Technical Round: Focus on strengthening your core technical concepts.")
    elif scores['tech'] < 7:
        feedback.append("Technical Round: Good foundation, but practice more complex problems.")
    else:
        feedback.append("Technical Round: Strong technical knowledge demonstrated.")
    
    # HR feedback
    if scores['hr'] < 5:
        feedback.append("HR Round: Work on communication and presenting experiences clearly.")
    else:
        feedback.append("HR Round: Good communication and behavioral responses.")
    
    # Emotional feedback
    dominant_emotion = emotion_stats.get('dominant_overall', 'neutral')
    if dominant_emotion == 'happy' or dominant_emotion == 'neutral':
        feedback.append("Emotional State: You maintained composure throughout the interview.")
    elif dominant_emotion == 'sad' or dominant_emotion == 'fear':
        feedback.append("Emotional State: Practice relaxation techniques to manage interview anxiety.")
    
    # Security violations
    if interview.violations > 0:
        feedback.append(f"Security: {interview.violations} violation(s) detected. Ensure you're alone during interviews.")
    
    return feedback


def generate_report(interview):
    """
    Generate comprehensive PDF report
    
    Args:
        interview: Interview model object
    
    Returns:
        Path to generated PDF report
    """
    # Create reports directory if not exists
    reports_dir = current_app.config['REPORTS_FOLDER']
    os.makedirs(reports_dir, exist_ok=True)
    
    # Generate filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"interview_report_{interview.id}_{timestamp}.pdf"
    filepath = os.path.join(reports_dir, filename)
    
    # Create PDF
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1976D2'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#424242'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Title
    story.append(Paragraph("Interview Performance Report", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Candidate Info
    story.append(Paragraph("Candidate Information", heading_style))
    candidate_data = [
        ['Candidate', interview.user.username],
        ['Email', interview.user.email],
        ['Interview Date', interview.started_at.strftime('%Y-%m-%d %H:%M')],
        ['Duration', f"{(interview.completed_at - interview.started_at).seconds // 60} minutes" if interview.completed_at else "N/A"],
        ['Status', interview.status.upper()]
    ]
    
    candidate_table = Table(candidate_data, colWidths=[2*inch, 4*inch])
    candidate_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#E3F2FD')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    story.append(candidate_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Calculate scores
    scores = calculate_overall_score(interview)
    
    # Performance Scores
    story.append(Paragraph("Performance Scores", heading_style))
    score_data = [
        ['Round', 'Score (out of 10)'],
        ['Technical Round', f"{scores['tech']:.1f}"],
        ['HR Round', f"{scores['hr']:.1f}"],
        ['Coding Round', f"{scores['coding']:.1f}"],
        ['Overall Score', f"{scores['overall']:.1f}/100"]
    ]
    
    score_table = Table(score_data, colWidths=[3*inch, 3*inch])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1976D2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(score_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Emotion Analysis
    emotion_stats = analyze_emotion_sequence(interview.emotions)
    
    story.append(Paragraph("Emotional Analysis", heading_style))
    
    # Create emotion charts
    timeline_chart_path = os.path.join(reports_dir, f'emotion_timeline_{interview.id}.png')
    distribution_chart_path = os.path.join(reports_dir, f'emotion_dist_{interview.id}.png')
    
    create_emotion_timeline_chart(interview.emotions, timeline_chart_path)
    create_emotion_distribution_chart(emotion_stats, distribution_chart_path)
    
    if os.path.exists(timeline_chart_path):
        story.append(Image(timeline_chart_path, width=6*inch, height=2.4*inch))
        story.append(Spacer(1, 0.2*inch))
    
    if os.path.exists(distribution_chart_path):
        story.append(Image(distribution_chart_path, width=5*inch, height=3.75*inch))
        story.append(Spacer(1, 0.3*inch))
    
    # Feedback and Recommendations
    story.append(PageBreak())
    story.append(Paragraph("Feedback & Recommendations", heading_style))
    
    feedback_items = generate_feedback(interview, scores, emotion_stats)
    for item in feedback_items:
        story.append(Paragraph(f"• {item}", styles['Normal']))
        story.append(Spacer(1, 0.1*inch))
    
    story.append(Spacer(1, 0.3*inch))
    
    # Question Summary
    story.append(Paragraph("Question & Answer Summary", heading_style))
    
    for idx, question in enumerate(interview.questions, 1):
        story.append(Paragraph(f"<b>Q{idx} ({question.round_type.upper()}):</b> {question.question_text}", styles['Normal']))
        story.append(Paragraph(f"<b>Answer:</b> {question.answer_text or 'No answer provided'}", styles['Normal']))
        story.append(Paragraph(f"<b>Score:</b> {question.answer_score:.1f}/10", styles['Normal']))
        story.append(Spacer(1, 0.15*inch))
    
    # Build PDF
    doc.build(story)
    
    # Clean up temporary chart files
    for chart_path in [timeline_chart_path, distribution_chart_path]:
        if os.path.exists(chart_path):
            try:
                os.remove(chart_path)
            except:
                pass
    
    return filepath
