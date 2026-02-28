# Intelligent Interview Platform

> **Final Year Engineering Project** - AI-Powered Interview Platform with Real-time Emotion & Voice Analysis

## 🎯 Overview

An intelligent web-based interview platform that conducts technical, coding, and HR interviews while analyzing candidates' emotions, voice sentiment, and providing comprehensive AI-driven feedback. Built using Flask, Google Gemini API, DeepFace, and advanced NLP libraries.

## 🆕 What's New - All Features Now Visible!

### ✨ Live Feature Status Panel
- **Real-time monitoring** of all active features during interview
- **Live emotion display** with emoji, confidence %, and color coding
- **Security status** updates (violations counter, alerts)
- **Voice analysis** status (Standby → Recording → Analyzed)
- **Fixed position panel** (top-right) with smooth animations

### 🚨 Enhanced Security Alerts  
- **Visual flash** (red screen overlay) when violations detected
- **Audio beep** alerts for immediate feedback
- **Specific messages** for different violation types
- **Auto-dismiss** alerts with shake animation
- **Live violation counter** in feature panel

### 🎨 Professional UI Enhancements
- **Real-time emotion updates** with 7 emotion types (😊😔😠😐😨😮🤢)
- **Color-coded backgrounds** matching current emotion
- **Pulsing animations** for active monitoring
- **Status badge updates** as features activate/deactivate
- **Fully responsive** design (desktop, tablet, mobile)

**See:** `FINAL_SUMMARY.md` for complete details on what was added!

---

## ✨ Complete Feature List

- **🤖 AI-Powered Question Generation** - Adaptive questions based on resume using Google Gemini
- **📹 Real-time Emotion Detection** - Facial emotion analysis using DeepFace and OpenCV
- **🎤 Voice Sentiment Analysis** - Speech-to-text with confidence and sentiment scoring (librosa, TextBlob)
- **👨‍💻 Monaco Code Editor** - Integrated coding round with syntax highlighting
- **🔒 Security Monitoring** - Face detection, multi-person alerts, violation tracking
- **📊 Comprehensive Reports** - PDF reports with emotion timelines, scores, and personalized feedback
- **🎮 Gamification** - XP system, levels, and achievement badges (NEW! Visible on dashboard)
- **🚨 Visual/Audio Alerts** - NEW! Screen flash + beep for security violations
- **📊 Live Monitoring Panel** - NEW! See all features working in real-time

## 🛠️ Technology Stack

### Backend
- **Framework**: Flask 2.3.2
- **Database**: SQLite with SQLAlchemy
- **AI/ML**: DeepFace, OpenCV, MediaPipe, TensorFlow
- **NLP**: spaCy, NLTK, TextBlob
- **Audio**: librosa, SpeechRecognition
- **Generative AI**: Google Gemini API

### Frontend
- **UI**: HTML5, CSS3, JavaScript
- **Framework**: Bootstrap 5
- **Editor**: Monaco Editor
- **Media**: WebRTC for camera/mic access
- **Charts**: Matplotlib (backend), Chart.js (optional)

## 📋 Prerequisites

- Python 3.8 or higher
- Webcam and microphone
- Google Gemini API Key ([Get one here](https://makersuite.google.com/app/apikey))
- Internet connection (for DeepFace model downloads on first run)

## 🚀 Installation & Setup

### 1. Clone or Navigate to Project Directory

```bash
cd "c:\Users\venka\OneDrive\Desktop\final year project source cod e"
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

### 3. Activate Virtual Environment

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Download spaCy Model

```bash
python -m spacy download en_core_web_sm
```

### 6. Configure Environment Variables

Create a `.env` file in the project root:

```env
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
GEMINI_API_KEY=your-gemini-api-key-here
```

**⚠️ Important:** Replace `your-gemini-api-key-here` with your actual Google Gemini API key.

### 7. Initialize Database

```bash
python run.py
```

The database will be created automatically on first run.

## 🎮 Running the Application

```bash
python run.py
```

The application will be available at: **http://localhost:5000**

## 📖 User Guide

### 1. Register & Login
- Navigate to the homepage
- Click "Register" and create an account
- Login with your credentials

### 2. Start Interview
- Click "Start New Interview" from dashboard
- Upload your resume (PDF or DOCX)
- Grant camera and microphone permissions when prompted

### 3. Interview Process
- **Technical Round**: 5 AI-generated questions based on your skills
- **Coding Round**: 2 coding problems with Monaco editor
- **HR Round**: 4 behavioral/situational questions

### 4. During Interview
- Your emotions are analyzed every 5 seconds
- Use voice recording for audio analysis
- Type or speak your answers
- Submit each answer to proceed

### 5. View Results
- After completion, view your scores
- Generate detailed PDF report with:
  - Emotion timeline graphs
  - Sentiment & confidence scores
  - Question-answer summary
  - Personalized improvement suggestions

## 📁 Project Structure

```
final year project source cod e/
├── app/
│   ├── __init__.py              # Flask app factory
│   ├── models.py                # Database models
│   ├── routes/                  # Route blueprints
│   │   ├── auth.py              # Authentication
│   │   ├── main.py              # Main pages
│   │   ├── interview.py         # Interview flow
│   │   └── api.py               # API endpoints
│   ├── services/                # Business logic
│   │   ├── ai_service.py        # Google Gemini integration
│   │   ├── resume_parser.py    # Resume parsing
│   │   ├── emotion_detection.py # Emotion analysis
│   │   ├── audio_analysis.py   # Voice analysis
│   │   └── report_generator.py # PDF generation
│   ├── static/                  # Static files
│   │   ├── css/
│   │   ├── uploads/             # Resume uploads
│   │   └── reports/             # Generated reports
│   └── templates/               # HTML templates
├── config.py                    # Configuration
├── requirements.txt             # Python dependencies
└── run.py                       # Application entry point
```

## 🔧 Configuration

Edit `config.py` to modify settings:

- `TECH_ROUND_QUESTIONS` - Number of technical questions (default: 5)
- `HR_ROUND_QUESTIONS` - Number of HR questions (default: 4)
- `CODING_ROUND_PROBLEMS` - Number of coding problems (default: 2)
- `FACE_DETECTION_INTERVAL` - Emotion check interval in seconds (default: 5)
- `MAX_VIOLATIONS` - Maximum security violations allowed (default: 3)

## 🐛 Troubleshooting

### Camera/Mic Not Working
- Ensure browser has permission to access camera/microphone
- Use HTTPS in production (required for WebRTC)
- Try a different browser (Chrome/Edge recommended)

### DeepFace Errors
- Ensure internet connection for first-time model download
- Install required system libraries for OpenCV
- Check TensorFlow compatibility

### Gemini API Errors
- Verify API key is correctly set in `.env`
- Check API quota and billing
- Review error messages for rate limits

### PyAudio Installation Issues (Windows)
```bash
pip install pipwin
pipwin install pyaudio
```

## 📊 Sample Questions

The platform generates adaptive questions. Examples include:

**Technical:** "Explain the difference between synchronous and asynchronous programming"
**Coding:** "Write a function to reverse a linked list"
**HR:** "Describe a challenging project and how you overcame obstacles"

## 🎓 Academic Note

This project demonstrates integration of:
- Web Development (Flask, REST APIs)
- Computer Vision (Face detection, emotion recognition)
- Natural Language Processing (Resume parsing, sentiment analysis)
- Machine Learning (DeepFace, audio feature extraction)
- Generative AI (Google Gemini for adaptive content)

Suitable for Final Year B.Tech/B.E projects in Computer Science or AI/ML streams.

## 📄 License

This project is for educational purposes as part of a final year engineering project.

## 🙏 Acknowledgments

- Google Gemini API for question generation
- DeepFace for emotion detection
- spaCy and NLTK for NLP
- Flask community for excellent documentation

## 📞 Support

For issues or questions:
1. Check the troubleshooting section
2. Review error logs in the terminal
3. Ensure all dependencies are correctly installed

---

**Built with ❤️ for Final Year Project 2026**
