import os
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)


class Config:
    """Base configuration class"""

    # ── Flask Core ───────────────────────────────────────────────────
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()

    # ── Database ─────────────────────────────────────────────────────
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get('DATABASE_URL') or
        'sqlite:///' + os.path.join(BASE_DIR, 'interview_platform.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Upload Settings ──────────────────────────────────────────────
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024   # 10 MB (reduced from 16)
    ALLOWED_EXTENSIONS = {'pdf', 'docx'}

    # ── Session / Cookie Security ────────────────────────────────────
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    SESSION_COOKIE_SECURE      = False   # True in production (HTTPS)
    SESSION_COOKIE_HTTPONLY    = True    # Prevent JS access to cookie
    SESSION_COOKIE_SAMESITE    = 'Lax'
    SESSION_COOKIE_NAME        = 'exam_session'

    # ── AI / Gemini API ──────────────────────────────────────────────
    GEMINI_API_KEY = (os.environ.get('GEMINI_API_KEY') or
                      os.environ.get('OPENAI_API_KEY') or 'your-api-key-here')
    OPENAI_API_KEY = GEMINI_API_KEY

    # ── Interview / Round Settings ───────────────────────────────────
    TECH_ROUND_QUESTIONS   = 5
    HR_ROUND_QUESTIONS     = 4
    CODING_ROUND_PROBLEMS  = 3

    # ── Security / Anti-Cheat Settings ──────────────────────────────
    FACE_DETECTION_INTERVAL  = 5          # seconds between face checks
    MAX_VIOLATIONS           = 5          # violations before auto-submit
    INTEGRITY_MIN_SCORE      = 20         # below this → force terminate
    LOGIN_MAX_ATTEMPTS       = 5          # brute-force limit
    LOGIN_LOCKOUT_MINUTES    = 15         # lockout duration
    RATE_LIMIT_PER_MINUTE    = 60         # global API rate limit

    # Exam lockdown flags
    REQUIRE_FULLSCREEN       = True       # force fullscreen during exam
    BLOCK_COPY_PASTE         = True       # block clipboard actions
    BLOCK_RIGHT_CLICK        = True       # disable right-click menu
    BLOCK_DEVTOOLS           = True       # detect DevTools opening
    ENABLE_FACE_VERIFICATION = True       # require webcam identity check
    HEARTBEAT_INTERVAL_SEC   = 15        # how often client sends heartbeat

    # ── Report Settings ──────────────────────────────────────────────
    REPORTS_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'reports')


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG   = True
    TESTING = False
    # Relaxed for local dev
    REQUIRE_FULLSCREEN = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG                  = False
    TESTING                = False
    SESSION_COOKIE_SECURE  = True
    REQUIRE_FULLSCREEN     = True


class TestingConfig(Config):
    """Testing configuration"""
    TESTING                = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED        = False
    REQUIRE_FULLSCREEN      = False


# Configuration registry
config = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'testing':     TestingConfig,
    'default':     DevelopmentConfig,
}
