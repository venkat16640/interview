"""
security_service.py
===================
Centralised security layer for the Interview / Exam platform.

Features
--------
* In-memory rate-limiter (per IP + per user)
* Brute-force login-attempt tracker with auto-lockout
* CSRF token generation and validation
* Violation severity scoring
* Exam-integrity score calculator
* Audit-log helper
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Optional

from flask import request, session, jsonify, current_app

# ──────────────────────────────────────────────────────────────────
# In-memory stores  (reset on server restart – fine for SQLite dev)
# ──────────────────────────────────────────────────────────────────

# { ip: [(timestamp, endpoint), ...] }
_rate_store: Dict[str, list] = defaultdict(list)

# { ip: {'count': int, 'locked_until': float | None} }
_login_attempts: Dict[str, dict] = defaultdict(lambda: {'count': 0, 'locked_until': None})

# { ip: float }  – last request time for throttling
_throttle_store: Dict[str, float] = defaultdict(float)


# ══════════════════════════════════════════════════════════════════
# 1. Rate Limiter
# ══════════════════════════════════════════════════════════════════

def check_rate_limit(ip: str, endpoint: str, max_requests: int = 60,
                     window_seconds: int = 60) -> bool:
    """
    Returns True if the request is ALLOWED, False if rate-limited.
    Sliding-window algorithm.
    """
    now = time.time()
    cutoff = now - window_seconds

    # Drop old entries
    _rate_store[ip] = [(ts, ep) for (ts, ep) in _rate_store[ip] if ts > cutoff]

    # Count requests to this endpoint
    endpoint_hits = sum(1 for (_, ep) in _rate_store[ip] if ep == endpoint)
    if endpoint_hits >= max_requests:
        return False

    _rate_store[ip].append((now, endpoint))
    return True


def rate_limit(max_requests: int = 30, window_seconds: int = 60):
    """
    Flask route decorator – enforces per-IP rate-limiting.
    Usage::

        @bp.route('/api/something')
        @rate_limit(max_requests=10, window_seconds=60)
        def something(): ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            ip = _get_ip()
            endpoint = request.endpoint or request.path
            if not check_rate_limit(ip, endpoint, max_requests, window_seconds):
                return jsonify({
                    'error': 'Too many requests. Please slow down.',
                    'retry_after': window_seconds
                }), 429
            return f(*args, **kwargs)
        return decorated
    return decorator


# ══════════════════════════════════════════════════════════════════
# 2. Brute-force Login Protection
# ══════════════════════════════════════════════════════════════════

MAX_LOGIN_ATTEMPTS  = 5          # attempts before lockout
LOCKOUT_SECONDS     = 15 * 60   # 15 minutes
ATTEMPT_RESET_SECS  = 10 * 60   # reset counter after 10 min of no tries


def record_failed_login(ip: str) -> dict:
    """
    Record a failed login and return status dict:
    {'locked': bool, 'attempts': int, 'locked_until': str|None}
    """
    entry = _login_attempts[ip]
    now = time.time()

    # If currently locked check if window expired
    if entry['locked_until'] and now < entry['locked_until']:
        remaining = int(entry['locked_until'] - now)
        return {'locked': True, 'attempts': entry['count'],
                'locked_until': _fmt_ts(entry['locked_until']),
                'remaining_seconds': remaining}

    # Reset counter if last attempt was long ago
    last = entry.get('last_attempt', 0)
    if now - last > ATTEMPT_RESET_SECS and entry['count'] > 0:
        entry['count'] = 0
        entry['locked_until'] = None

    entry['count'] += 1
    entry['last_attempt'] = now

    if entry['count'] >= MAX_LOGIN_ATTEMPTS:
        entry['locked_until'] = now + LOCKOUT_SECONDS
        return {'locked': True, 'attempts': entry['count'],
                'locked_until': _fmt_ts(entry['locked_until']),
                'remaining_seconds': LOCKOUT_SECONDS}

    return {'locked': False, 'attempts': entry['count'],
            'locked_until': None, 'remaining_seconds': 0}


def check_login_locked(ip: str) -> dict:
    """Check whether an IP is currently locked out (without incrementing count)."""
    entry = _login_attempts[ip]
    now = time.time()
    if entry['locked_until'] and now < entry['locked_until']:
        remaining = int(entry['locked_until'] - now)
        return {'locked': True, 'remaining_seconds': remaining,
                'locked_until': _fmt_ts(entry['locked_until'])}
    return {'locked': False, 'remaining_seconds': 0, 'locked_until': None}


def clear_login_attempts(ip: str):
    """Call on successful login to reset counter."""
    _login_attempts[ip] = {'count': 0, 'locked_until': None}


# ══════════════════════════════════════════════════════════════════
# 3. CSRF Token Helpers
# ══════════════════════════════════════════════════════════════════

CSRF_SESSION_KEY = '_csrf_token'
CSRF_HEADER_NAME = 'X-CSRF-Token'
CSRF_FORM_FIELD  = 'csrf_token'


def generate_csrf_token() -> str:
    """Generate and store a CSRF token in the session."""
    token = secrets.token_hex(32)
    session[CSRF_SESSION_KEY] = token
    return token


def get_csrf_token() -> str:
    """Return existing CSRF token, creating one if absent."""
    if CSRF_SESSION_KEY not in session:
        return generate_csrf_token()
    return session[CSRF_SESSION_KEY]


def validate_csrf(f):
    """
    Decorator that validates the CSRF token on POST / PUT / PATCH / DELETE.
    Accepts token from form field OR request header.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            expected = session.get(CSRF_SESSION_KEY)
            submitted = (request.form.get(CSRF_FORM_FIELD) or
                         request.headers.get(CSRF_HEADER_NAME) or
                         (request.get_json(silent=True) or {}).get(CSRF_FORM_FIELD))
            if not expected or not submitted or not hmac.compare_digest(expected, submitted):
                return jsonify({'error': 'CSRF validation failed'}), 403
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════════════════════════════
# 4. Violation Severity Scoring
# ══════════════════════════════════════════════════════════════════

VIOLATION_WEIGHTS = {
    'tab_switch':           3,
    'fullscreen_exit':      4,
    'copy_attempt':         2,
    'paste_attempt':        3,
    'right_click':          1,
    'multiple_faces':       5,
    'no_face':              4,
    'identity_mismatch':    8,
    'devtools_open':        5,
    'keyboard_shortcut':    2,
    'window_blur':          2,
    'screen_capture':       6,
    'phone_detected':       5,
    'print_attempt':        3,
    'text_selection':       1,
}

SEVERITY_THRESHOLDS = {
    'clean':    0,
    'low':      5,
    'medium':   15,
    'high':     30,
    'critical': 50,
}


def compute_severity(violation_map: dict) -> dict:
    """
    violation_map = {'tab_switch': 2, 'copy_attempt': 1, ...}
    Returns {'score': int, 'level': str, 'breakdown': dict}
    """
    total = 0
    breakdown = {}
    for vtype, count in violation_map.items():
        weight = VIOLATION_WEIGHTS.get(vtype, 1)
        pts = weight * count
        breakdown[vtype] = {'count': count, 'weight': weight, 'points': pts}
        total += pts

    level = 'clean'
    for lvl, threshold in sorted(SEVERITY_THRESHOLDS.items(), key=lambda x: x[1], reverse=True):
        if total >= threshold:
            level = lvl
            break

    return {'score': total, 'level': level, 'breakdown': breakdown}


def compute_integrity_score(total_violations: int,
                            violation_map: dict,
                            duration_minutes: float) -> float:
    """
    Returns an exam integrity score from 0–100
    (100 = perfectly clean, 0 = completely compromised).
    """
    severity = compute_severity(violation_map)
    raw_penalty = severity['score']

    # Normalise by session length (longer exams tolerate slightly more)
    time_factor = max(1.0, duration_minutes / 30.0)
    adjusted_penalty = raw_penalty / time_factor

    score = max(0.0, 100.0 - adjusted_penalty * 2)
    return round(score, 1)


# ══════════════════════════════════════════════════════════════════
# 5. Audit Log Helper
# ══════════════════════════════════════════════════════════════════

def build_audit_entry(event_type: str, user_id: Optional[int],
                      interview_id: Optional[int], details: dict) -> dict:
    """Build a JSON-serialisable audit-log entry."""
    return {
        'timestamp': datetime.utcnow().isoformat(),
        'event_type': event_type,
        'user_id': user_id,
        'interview_id': interview_id,
        'ip': _get_ip(),
        'user_agent': request.headers.get('User-Agent', ''),
        'details': details,
    }


def append_audit_log(interview, event_type: str, details: dict):
    """
    Append to the interview's violation_log JSON field.
    interview is an Interview model instance.
    """
    existing = []
    if interview.violation_log:
        try:
            existing = json.loads(interview.violation_log)
        except (json.JSONDecodeError, TypeError):
            existing = []

    entry = {
        'ts': datetime.utcnow().isoformat(),
        'type': event_type,
        'ip': _get_ip(),
        **details,
    }
    existing.append(entry)
    interview.violation_log = json.dumps(existing[-200:])  # cap at 200 entries


# ══════════════════════════════════════════════════════════════════
# 6. Input Sanitisation
# ══════════════════════════════════════════════════════════════════

import re

DANGEROUS_PATTERNS = [
    r'<script[^>]*>.*?</script>',
    r'javascript:',
    r'on\w+\s*=',
    r'<iframe',
    r'<object',
    r'<embed',
    r'eval\s*\(',
    r'document\.cookie',
    r'window\.location',
]
_DANGER_RE = re.compile('|'.join(DANGEROUS_PATTERNS), re.IGNORECASE | re.DOTALL)


def sanitise_input(text: str) -> str:
    """Strip dangerous HTML / JS patterns from user input."""
    if not isinstance(text, str):
        return text
    cleaned = _DANGER_RE.sub('', text)
    # Collapse excessive whitespace
    cleaned = re.sub(r'\s{3,}', '  ', cleaned)
    return cleaned[:50_000]  # hard length cap


def validate_file_extension(filename: str, allowed: set) -> bool:
    """Return True if the file extension is in the allowed set."""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in allowed


def is_safe_path(base_dir: str, candidate_path: str) -> bool:
    """Prevent path-traversal: ensure candidate_path is under base_dir."""
    base = os.path.realpath(base_dir)
    candidate = os.path.realpath(candidate_path)
    return candidate.startswith(base)


# ══════════════════════════════════════════════════════════════════
# 7. Security Headers Helper (called from create_app)
# ══════════════════════════════════════════════════════════════════

def apply_security_headers(response):
    """Add hardening HTTP headers to every Flask response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = (
        'camera=self, microphone=self, fullscreen=self, '
        'geolocation=(), payment=()'
    )
    # Only in production (HTTPS) will HSTS actually be effective
    if not current_app.debug:
        response.headers['Strict-Transport-Security'] = (
            'max-age=63072000; includeSubDomains; preload'
        )
    return response


# ══════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════

def _get_ip() -> str:
    """Resolve real client IP, respecting reverse-proxy headers."""
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'


def _fmt_ts(ts: float) -> str:
    return datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S UTC')
