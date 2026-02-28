from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
import os
from datetime import datetime
import html

def safe_text(text):
    if not text:
        return "N/A"
    return html.escape(str(text)).replace('\n', '<br/>')

def generate_pdf_report(interview, user, output_path):
    """
    Generate comprehensive interview performance report
    """
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        textColor=colors.HexColor('#0d6efd')
    )
    story.append(Paragraph("Interview Performance Report", title_style))
    story.append(Spacer(1, 12))

    # Candidate Info
    info_data = [
        ["Candidate Name:", user.username],
        ["Date:", interview.started_at.strftime("%Y-%m-%d")],
        ["Interview ID:", str(interview.id)],
        ["Security Violations:", f"{interview.violations} (FLAGGED)" if interview.violations > 0 else "0 (Secure)"],
        ["Status:", interview.status.upper()]
    ]
    t = Table(info_data, colWidths=[2*inch, 4*inch])
    t.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(t)
    story.append(Spacer(1, 24))

    # Scores Summary
    story.append(Paragraph("Performance Summary", styles['Heading2']))
    
    score_data = [
        ['Metric', 'Score (0-10)'],
        ['Technical Skills', f"{interview.tech_score:.1f}"],
        ['Coding Ability', f"{interview.coding_score:.1f}"],
        ['HR & Behavioral', f"{interview.hr_score:.1f}"],
        ['Overall Rating', f"{interview.overall_score:.1f}"]
    ]
    
    t_scores = Table(score_data, colWidths=[3*inch, 2*inch])
    t_scores.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (1,0), colors.HexColor('#0d6efd')),
        ('TEXTCOLOR', (0,0), (1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 12),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))
    story.append(t_scores)
    story.append(Spacer(1, 24))

    # Chart
    story.append(Paragraph("Score Visualization", styles['Heading3']))
    
    drawing = Drawing(400, 200)
    data = [
        (interview.tech_score, interview.coding_score, interview.hr_score, interview.overall_score)
    ]
    bc = VerticalBarChart()
    bc.x = 50
    bc.y = 50
    bc.height = 125
    bc.width = 300
    bc.data = data
    bc.strokeColor = colors.white
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = 10
    bc.valueAxis.valueStep = 2
    bc.categoryAxis.labels.boxAnchor = 'ne'
    bc.categoryAxis.labels.dx = 8
    bc.categoryAxis.labels.dy = -2
    bc.categoryAxis.labels.angle = 30
    bc.categoryAxis.categoryNames = ['Technical', 'Coding', 'HR', 'Overall']
    bc.bars[0].fillColor = colors.HexColor('#0d6efd')
    
    drawing.add(bc)
    story.append(drawing)
    story.append(Spacer(1, 24))

    # Behavioral Analysis
    story.append(Paragraph("Behavioral & Emotion Analysis", styles['Heading2']))
    
    # Calculate dominant emotion
    emotions = [log.emotion for log in interview.emotions]
    dominant_emotion = max(set(emotions), key=emotions.count) if emotions else "Neutral"
    
    story.append(Paragraph(f"<b>Dominant Emotion:</b> {dominant_emotion.title()}", styles['Normal']))
    story.append(Paragraph(f"<b>Security Violations Detected:</b> {interview.violations}", styles['Normal']))
    
    story.append(Spacer(1, 12))
    
    story.append(Spacer(1, 12))

    # Detailed Analysis
    story.append(Paragraph("Detailed Question Analysis", styles['Heading2']))
    
    q_style = ParagraphStyle('QStyle', parent=styles['Normal'], spaceAfter=6, textColor=colors.HexColor('#2c3e50'), fontName='Helvetica-Bold')
    a_style = ParagraphStyle('AStyle', parent=styles['Normal'], leftIndent=10, textColor=colors.HexColor('#333333'), spaceAfter=4)
    f_style = ParagraphStyle('FStyle', parent=styles['Normal'], leftIndent=10, textColor=colors.HexColor('#0d6efd'), fontName='Helvetica-Oblique', spaceAfter=12)
    s_style = ParagraphStyle('ScoreStyle', parent=styles['Normal'], leftIndent=10, textColor=colors.HexColor('#198754'), fontName='Helvetica-Bold', spaceAfter=4)

    for i, q in enumerate(interview.questions):
        block = []
        # Question
        block.append(Paragraph(f"<b>Q{i+1}:</b> {safe_text(q.question_text)}", q_style))
        
        # Answer (Full Answer, no truncation)
        ans_full = safe_text(q.answer_text if q.answer_text else "No response provided for this question.")
        block.append(Paragraph(f"<b>Candidate's Answer:</b> {ans_full}", a_style))
        
        # Exact Score
        block.append(Paragraph(f"<b>Assessed Score: {q.answer_score:.1f}/10</b>", s_style))
        
        # Accurate Feedback
        if hasattr(q, 'feedback') and q.feedback:
            feedback_raw = q.feedback
        else:
            feedback_raw = "No personalized AI feedback could be generated because no answer was submitted for this question. A complete and accurate response is required to trigger the AI grading module."
            
        feedback_text = safe_text(feedback_raw)
        block.append(Paragraph(f"<b>AI Feedback &amp; Insights:</b> {feedback_text}", f_style))
        
        block.append(Spacer(1, 10))
        # Keep question/answer together if possible so it doesn't break across pages uglily
        story.append(KeepTogether(block))

    # Actionable Suggestions to Improve
    story.append(Spacer(1, 12))
    story.append(Paragraph("Actionable Suggestions to Improve", styles['Heading2']))
    
    # Calculate Areas
    rounds_scores = {'Technical': interview.tech_score, 'Coding': interview.coding_score, 'HR & Behavioral': interview.hr_score}
    sorted_rounds = sorted(rounds_scores.items(), key=lambda x: x[1])
    worst_round = sorted_rounds[0][0]
    best_round = sorted_rounds[-1][0]
    
    sugg_style = ParagraphStyle('SuggStyle', parent=styles['Normal'], spaceAfter=10, leading=14)
    story.append(Paragraph(f"<b>Key Strength:</b> {best_round} (Score: {sorted_rounds[-1][1]:.1f}/10)", sugg_style))
    story.append(Paragraph(f"<b>Primary Area for Improvement:</b> {worst_round} (Score: {sorted_rounds[0][1]:.1f}/10)", sugg_style))
    story.append(Spacer(1, 10))
    
    suggestions = []
    if worst_round == 'Coding':
        suggestions.append("• <b>Data Structures & Algorithms:</b> Focus on optimizing your code's time and space complexity. The AI metrics indicate logical correctness can be improved.")
        suggestions.append("• <b>Mock Coding Assessments:</b> Practice on platforms like LeetCode or HackerRank under strictly timed conditions.")
    elif worst_round == 'Technical':
        suggestions.append("• <b>Core Theory Review:</b> Brush up on the fundamental theoretical concepts specific to your declared tech stack.")
        suggestions.append("• <b>System Design Clarity:</b> Practice explaining your technical decisions and architectural scaling patterns more deeply.")
    else:
        suggestions.append("• <b>Behavioral Structure:</b> Use the S.T.A.R. method (Situation, Task, Action, Result) to give your answers more professional structure.")
        suggestions.append("• <b>Non-Verbal Cues:</b> Emphasize steady pacing and maintain a confident, positive delivery during extended explanations.")
        
    for sugg in suggestions:
        story.append(Paragraph(sugg, sugg_style))
        
    story.append(Spacer(1, 24))

    # Conclusion
    story.append(Paragraph("Final Determination", styles['Heading2']))
    
    rec_text = "Based on the comprehensive interview performance, the candidate shows "
    if interview.overall_score >= 8:
        rec_text += "<b>exceptional potential</b> and is highly recommended for the position."
    elif interview.overall_score >= 6:
        rec_text += "<b>good potential</b> but may require some specific mentorship during onboarding."
    else:
        rec_text += "<b>fundamental gaps</b> that significantly affect suitability for this role at this time."
        
    story.append(Paragraph(rec_text, styles['Normal']))

    # Build PDF
    doc.build(story)
    return output_path
