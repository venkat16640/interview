from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User
from app.services.security_service import (
    record_failed_login, check_login_locked, clear_login_attempts,
    get_csrf_token, validate_csrf, generate_csrf_token,
    rate_limit, _get_ip, sanitise_input, VIOLATION_WEIGHTS
)
import re

bp = Blueprint('auth', __name__, url_prefix='/auth')

# ── helpers ────────────────────────────────────────────────────────

def _is_valid_email(email: str) -> bool:
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email))

def _is_strong_password(pwd: str) -> tuple[bool, str]:
    """Returns (ok, reason). Enforces company exam security password policy."""
    if len(pwd) < 8:
        return False, 'Password must be at least 8 characters.'
    if not re.search(r'[A-Z]', pwd):
        return False, 'Password must contain at least one uppercase letter.'
    if not re.search(r'[a-z]', pwd):
        return False, 'Password must contain at least one lowercase letter.'
    if not re.search(r'\d', pwd):
        return False, 'Password must contain at least one digit.'
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-]', pwd):
        return False, 'Password must contain at least one special character.'
    return True, ''


# ── register ───────────────────────────────────────────────────────

@bp.route('/register', methods=['GET', 'POST'])
@rate_limit(max_requests=10, window_seconds=60)
def register():
    """User registration with CSRF + input validation."""
    if request.method == 'POST':
        csrf_token_expected = session.get('_csrf_token')
        csrf_submitted = request.form.get('csrf_token')
        import hmac as _hmac
        if (not csrf_token_expected or not csrf_submitted or
                not _hmac.compare_digest(csrf_token_expected, csrf_submitted)):
            flash('Security check failed. Please try again.', 'danger')
            return redirect(url_for('auth.register'))

        username = sanitise_input(request.form.get('username', '').strip())
        email    = sanitise_input(request.form.get('email', '').strip().lower())
        password = request.form.get('password', '')

        # Validation
        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('auth.register'))

        if len(username) < 3 or len(username) > 30:
            flash('Username must be 3–30 characters.', 'danger')
            return redirect(url_for('auth.register'))

        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            flash('Username may only contain letters, numbers, and underscores.', 'danger')
            return redirect(url_for('auth.register'))

        if not _is_valid_email(email):
            flash('Invalid email address.', 'danger')
            return redirect(url_for('auth.register'))

        ok, reason = _is_strong_password(password)
        if not ok:
            flash(reason, 'danger')
            return redirect(url_for('auth.register'))

        # Duplicate checks
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('auth.register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('auth.register'))

        # Create user
        hashed = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)
        new_user = User(username=username, email=email, password_hash=hashed)
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('auth.login'))

    csrf_token = get_csrf_token()
    return render_template('auth/register.html', csrf_token=csrf_token)


# ── login ──────────────────────────────────────────────────────────

@bp.route('/login', methods=['GET', 'POST'])
@rate_limit(max_requests=15, window_seconds=60)
def login():
    """Login with brute-force lockout + CSRF protection."""
    ip = _get_ip()

    if request.method == 'POST':
        # CSRF check
        csrf_token_expected = session.get('_csrf_token')
        csrf_submitted = request.form.get('csrf_token')
        import hmac as _hmac
        if (not csrf_token_expected or not csrf_submitted or
                not _hmac.compare_digest(csrf_token_expected, csrf_submitted)):
            flash('Security check failed. Please try again.', 'danger')
            return redirect(url_for('auth.login'))

        # Lockout check before even touching the DB
        lock_status = check_login_locked(ip)
        if lock_status['locked']:
            mins = lock_status['remaining_seconds'] // 60
            secs = lock_status['remaining_seconds'] % 60
            flash(f'Account locked due to too many failed attempts. '
                  f'Try again in {mins}m {secs}s.', 'danger')
            return redirect(url_for('auth.login'))

        username = sanitise_input(request.form.get('username', '').strip())
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            # Successful login
            clear_login_attempts(ip)
            session.clear()                        # prevent session-fixation
            session['user_id']  = user.id
            session['username'] = user.username
            session.permanent   = True
            # Rotate CSRF token on login
            generate_csrf_token()
            flash('Login successful!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            result = record_failed_login(ip)
            remaining = MAX_LOGIN_ATTEMPTS - result['attempts']
            if result['locked']:
                mins = result['remaining_seconds'] // 60
                flash(f'Too many failed attempts. '
                      f'Account locked for {mins} minutes.', 'danger')
            else:
                flash(f'Invalid credentials. '
                      f'{max(0, remaining)} attempt(s) remaining before lockout.',
                      'danger')
            return redirect(url_for('auth.login'))

    csrf_token = get_csrf_token()
    return render_template('auth/login.html', csrf_token=csrf_token)


# ── logout ─────────────────────────────────────────────────────────

@bp.route('/logout')
def logout():
    """Logout – invalidates the whole session."""
    session.clear()
    flash('You have been logged out securely.', 'info')
    return redirect(url_for('auth.login'))


# ── lockout status (AJAX) ──────────────────────────────────────────

@bp.route('/lockout-status')
def lockout_status():
    """AJAX endpoint used by the login form to show a live countdown."""
    ip = _get_ip()
    status = check_login_locked(ip)
    return jsonify(status)


MAX_LOGIN_ATTEMPTS = 5  # must mirror security_service constant
