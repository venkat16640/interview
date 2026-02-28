from datetime import datetime
from app import db
import json

class User(db.Model):
    """User model for authentication"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    reference_photo_path = db.Column(db.String(255), nullable=True)
    
    # Gamification
    xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    badges = db.Column(db.Text, default='[]')  # JSON list of badges
    
    # Preferences
    avatar_preference = db.Column(db.String(50), default='female_1')
    
    # Relationships
    interviews = db.relationship('Interview', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def get_badges(self):
        return json.loads(self.badges)
    
    def add_badge(self, badge_name):
        current_badges = self.get_badges()
        if badge_name not in current_badges:
            current_badges.append(badge_name)
            self.badges = json.dumps(current_badges)
    
    def add_xp(self, amount):
        self.xp += amount
        # Simple level up logic: Level = 1 + (XP / 1000)
        self.level = 1 + (self.xp // 1000)


class Interview(db.Model):
    """Interview session model"""
    __tablename__ = 'interviews'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    resume_path = db.Column(db.String(255), nullable=True)
    parsed_resume = db.Column(db.Text, nullable=True)  # JSON string
    
    # Interview state
    current_round = db.Column(db.String(20), default='tech')  # tech, coding, hr
    current_question_index = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='in_progress')  # in_progress, completed
    baseline_photo_path = db.Column(db.String(255), nullable=True) # Identity proof photo
    
    # Timestamps
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Scores
    tech_score = db.Column(db.Float, default=0.0)
    hr_score = db.Column(db.Float, default=0.0)
    coding_score = db.Column(db.Float, default=0.0)
    overall_score = db.Column(db.Float, default=0.0)
    
    # Security violations & integrity
    violations = db.Column(db.Integer, default=0)
    violation_log = db.Column(db.Text, nullable=True)  # JSON array of audit entries
    violation_map = db.Column(db.Text, nullable=True)   # JSON dict {type: count}
    integrity_score = db.Column(db.Float, default=100.0)  # 0-100 exam integrity score
    
    # Lockdown state
    fullscreen_exits = db.Column(db.Integer, default=0)
    tab_switches = db.Column(db.Integer, default=0)
    copy_attempts = db.Column(db.Integer, default=0)
    
    # Report
    report_path = db.Column(db.String(255), nullable=True)
    
    # Relationships
    questions = db.relationship('Question', backref='interview', lazy=True, cascade='all, delete-orphan')
    emotions = db.relationship('EmotionLog', backref='interview', lazy=True, cascade='all, delete-orphan')
    audit_logs = db.relationship('AuditLog', backref='interview', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Interview {self.id} - {self.status}>'
    
    def get_parsed_resume(self):
        """Parse JSON resume data"""
        if self.parsed_resume:
            return json.loads(self.parsed_resume)
        return {}
    
    def set_parsed_resume(self, data):
        """Set resume data as JSON"""
        self.parsed_resume = json.dumps(data)

    def get_violation_map(self) -> dict:
        """Return violation-type counter dict."""
        if self.violation_map:
            try:
                return json.loads(self.violation_map)
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

    def increment_violation(self, vtype: str):
        """Increment a specific violation type counter."""
        vmap = self.get_violation_map()
        vmap[vtype] = vmap.get(vtype, 0) + 1
        self.violation_map = json.dumps(vmap)
        self.violations += 1


class Question(db.Model):
    """Question and response model"""
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=False)
    
    round_type = db.Column(db.String(20), nullable=False)  # tech, hr, coding
    question_text = db.Column(db.Text, nullable=False)
    answer_text = db.Column(db.Text, nullable=True)
    
    # Audio analysis
    audio_transcript = db.Column(db.Text, nullable=True)
    sentiment_score = db.Column(db.Float, nullable=True)
    confidence_score = db.Column(db.Float, nullable=True)
    
    # Scoring
    answer_score = db.Column(db.Float, default=0.0)
    feedback = db.Column(db.Text, nullable=True)  # AI feedback on the answer
    
    # Timestamps
    asked_at = db.Column(db.DateTime, default=datetime.utcnow)
    answered_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<Question {self.id} - {self.round_type}>'


class EmotionLog(db.Model):
    """Real-time emotion tracking"""
    __tablename__ = 'emotion_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=False)
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    emotion = db.Column(db.String(20), nullable=False)  # happy, sad, angry, neutral, etc.
    confidence = db.Column(db.Float, nullable=False)
    
    # Face detection data
    faces_detected = db.Column(db.Integer, default=1)
    is_violation = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<EmotionLog {self.emotion} - {self.confidence:.2f}>'


class CodeSubmission(db.Model):
    """Track all code submissions for a question"""
    __tablename__ = 'code_submissions'
    
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=False)
    
    # Code details
    code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(20), default='python')  # python, java, cpp, javascript
    
    # Test results
    test_cases_passed = db.Column(db.Integer, default=0)
    test_cases_total = db.Column(db.Integer, default=0)
    test_results = db.Column(db.Text, nullable=True)  # JSON: detailed test case results
    
    # Performance metrics
    execution_time = db.Column(db.Float, nullable=True)  # in milliseconds
    memory_used = db.Column(db.Float, nullable=True)  # in MB
    
    # Scoring
    score = db.Column(db.Float, default=0.0)
    is_correct = db.Column(db.Boolean, default=False)
    
    # Metadata
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, passed, failed, error
    error_message = db.Column(db.Text, nullable=True)
    
    # Relationships
    question = db.relationship('Question', backref='submissions')
    
    def __repr__(self):
        return f'<CodeSubmission {self.id} - {self.status}>'
    
    def get_test_results(self):
        """Parse JSON test results"""
        if self.test_results:
            return json.loads(self.test_results)
        return []
    
    def set_test_results(self, results):
        """Set test results as JSON"""
        self.test_results = json.dumps(results)


class Hint(db.Model):
    """Hints for coding questions"""
    __tablename__ = 'hints'
    
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    
    # Hint details
    hint_level = db.Column(db.Integer, nullable=False)  # 1=Approach, 2=Pseudocode, 3=Solution
    hint_text = db.Column(db.Text, nullable=False)
    point_deduction = db.Column(db.Float, default=0.5)  # Points deducted for using this hint
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Hint Level {self.hint_level}>'


class HintUsage(db.Model):
    """Track which hints candidates used"""
    __tablename__ = 'hint_usage'
    
    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=False)
    hint_id = db.Column(db.Integer, db.ForeignKey('hints.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    
    used_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<HintUsage {self.id}>'


class PracticeQuestion(db.Model):
    """Practice questions for candidates"""
    __tablename__ = 'practice_questions'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Question details
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    difficulty = db.Column(db.String(20), default='easy')  # easy, medium, hard
    category = db.Column(db.String(50), nullable=False)  # coding, technical, hr
    
    # For coding questions
    test_cases = db.Column(db.Text, nullable=True)  # JSON
    solution_code = db.Column(db.Text, nullable=True)
    starter_code = db.Column(db.Text, nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<PracticeQuestion {self.title}>'


class Leaderboard(db.Model):
    """Global leaderboard for candidate rankings"""
    __tablename__ = 'leaderboard'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=False)
    
    # Scores
    overall_score = db.Column(db.Float, default=0.0)
    tech_score = db.Column(db.Float, default=0.0)
    coding_score = db.Column(db.Float, default=0.0)
    hr_score = db.Column(db.Float, default=0.0)
    
    # Rankings
    global_rank = db.Column(db.Integer, nullable=True)
    percentile = db.Column(db.Float, nullable=True)
    
    # Metadata
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='leaderboard_entries')
    interview = db.relationship('Interview', backref='leaderboard_entry')
    
    def __repr__(self):
        return f'<Leaderboard Rank {self.global_rank}>'


class AuditLog(db.Model):
    """Security audit log – every probe/violation event is written here."""
    __tablename__ = 'audit_logs'

    id           = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    timestamp    = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    event_type   = db.Column(db.String(60), nullable=False)   # e.g. 'tab_switch'
    severity     = db.Column(db.String(20), default='low')    # low/medium/high/critical
    ip_address   = db.Column(db.String(45), nullable=True)
    user_agent   = db.Column(db.String(512), nullable=True)
    details      = db.Column(db.Text, nullable=True)          # JSON extra details

    def __repr__(self):
        return f'<AuditLog {self.event_type} @ {self.timestamp}>'

    def get_details(self) -> dict:
        if self.details:
            try:
                return json.loads(self.details)
            except (json.JSONDecodeError, TypeError):
                pass
        return {}


class ExamLockdown(db.Model):
    """Tracks browser-lock state for an interview session."""
    __tablename__ = 'exam_lockdown'

    id           = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), unique=True, nullable=False)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Lockdown state
    is_locked        = db.Column(db.Boolean, default=False)
    locked_at        = db.Column(db.DateTime, nullable=True)
    fullscreen_active = db.Column(db.Boolean, default=False)
    last_heartbeat   = db.Column(db.DateTime, nullable=True)

    # Counters (mirrors Interview for quick querying)
    fullscreen_exits = db.Column(db.Integer, default=0)
    tab_switches     = db.Column(db.Integer, default=0)
    copy_attempts    = db.Column(db.Integer, default=0)
    total_violations = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<ExamLockdown interview={self.interview_id} locked={self.is_locked}>'
