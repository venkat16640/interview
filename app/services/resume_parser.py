"""
Resume Parser Service
Extracts skills, education, and experience from PDF/DOCX resumes
"""
import PyPDF2
import docx
import re
import spacy

# Load spaCy model (requires: python -m spacy download en_core_web_sm)
try:
    nlp = spacy.load('en_core_web_sm')
except:
    print("Warning: spaCy model not loaded. Run: python -m spacy download en_core_web_sm")
    nlp = None


def extract_text_from_pdf(filepath):
    """Extract text from PDF file"""
    text = ""
    try:
        with open(filepath, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text()
    except Exception as e:
        raise Exception(f"Error reading PDF: {str(e)}")
    return text


def extract_text_from_docx(filepath):
    """Extract text from DOCX file"""
    text = ""
    try:
        doc = docx.Document(filepath)
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
    except Exception as e:
        raise Exception(f"Error reading DOCX: {str(e)}")
    return text


def extract_email(text):
    """Extract email from text"""
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text)
    return emails[0] if emails else None


def extract_phone(text):
    """Extract phone number from text"""
    phone_pattern = r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]'
    phones = re.findall(phone_pattern, text)
    return phones[0] if phones else None


def extract_skills(text):
    """Extract technical skills from resume"""
    # Common technical skills (can be expanded)
    skill_keywords = [
        'python', 'java', 'javascript', 'c++', 'c#', 'ruby', 'php', 'swift', 'kotlin',
        'react', 'angular', 'vue', 'node.js', 'django', 'flask', 'spring', 'express',
        'sql', 'mysql', 'postgresql', 'mongodb', 'oracle', 'redis',
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'jenkins', 'git',
        'machine learning', 'deep learning', 'tensorflow', 'pytorch', 'scikit-learn',
        'data analysis', 'pandas', 'numpy', 'matplotlib',
        'html', 'css', 'bootstrap', 'tailwind',
        'rest api', 'graphql', 'microservices',
        'agile', 'scrum', 'jira'
    ]
    
    text_lower = text.lower()
    found_skills = []
    
    for skill in skill_keywords:
        if skill in text_lower:
            found_skills.append(skill.title())
    
    return list(set(found_skills))  # Remove duplicates


def extract_education(text):
    """Extract education information"""
    education_keywords = ['bachelor', 'master', 'phd', 'b.tech', 'm.tech', 'b.e', 'm.e', 
                         'bsc', 'msc', 'mba', 'degree', 'university', 'college', 'institute']
    
    education = []
    lines = text.split('\n')
    
    for line in lines:
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in education_keywords):
            education.append(line.strip())
    
    return education[:5]  # Return top 5 education entries


def extract_experience(text):
    """Extract work experience"""
    # Look for common experience indicators
    experience_patterns = [
        r'(\d+)[\+]?\s*years?\s*of\s*experience',
        r'experience:\s*(\d+)[\+]?\s*years?'
    ]
    
    years_exp = 0
    for pattern in experience_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            years_exp = int(match.group(1))
            break
    
    # Extract company names using NLP if available
    companies = []
    if nlp:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ == 'ORG':
                companies.append(ent.text)
    
    return {
        'years': years_exp,
        'companies': list(set(companies))[:5]  # Top 5 unique companies
    }


def parse_resume(filepath):
    """
    Main function to parse resume
    Returns structured data
    """
    # Determine file type and extract text
    if filepath.endswith('.pdf'):
        text = extract_text_from_pdf(filepath)
    elif filepath.endswith('.docx'):
        text = extract_text_from_docx(filepath)
    else:
        raise Exception("Unsupported file format")
    
    # Extract information
    parsed_data = {
        'raw_text': text,
        'email': extract_email(text),
        'phone': extract_phone(text),
        'skills': extract_skills(text),
        'education': extract_education(text),
        'experience': extract_experience(text)
    }
    
    return parsed_data
