"""
security_routes.py  –  /security/ blueprint
=============================================
All exam-integrity / anti-cheating API endpoints.

Endpoints
---------
POST /security/log-event          – log a browser security event
POST /security/heartbeat          – keep-alive + lockdown state
GET  /security/status/<interview_id> – get live security status
GET  /security/report/<interview_id> – full security report
POST /security/lockdown/activate  – start fullscreen lockdown
POST /security/lockdown/release   – release lockdown on completion
"""

import json
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from app import db
from app.models import AuditLog, ExamLockdown, Interview
from app.routes.main import login_required
from app.services.security_service import (
    _get_ip,
    append_audit_log,
    compute_integrity_score,
    compute_severity,
    rate_limit,
    VIOLATION_WEIGHTS,
)

bp = Blueprint('security', __name__, url_prefix='/security')


# ══════════════════════════════════════════════════════════════════
# Helper
# ══════════════════════════════════════════════════════════════════

def _get_or_create_lockdown(interview_id: int, user_id: int) -> ExamLockdown:
    ld = ExamLockdown.query.filter_by(interview_id=interview_id).first()
    if not ld:
        ld = ExamLockdown(interview_id=interview_id, user_id=user_id)
        db.session.add(ld)
        db.session.flush()
    return ld


def _severity_for_type(vtype: str) -> str:
    weight = VIOLATION_WEIGHTS.get(vtype, 1)
    if weight >= 6:
        return 'critical'
    if weight >= 4:
        return 'high'
    if weight >= 2:
        return 'medium'
    return 'low'


def _update_integrity(interview: Interview):
    """Recalculate and persist the integrity score."""
    vmap = interview.get_violation_map()
    started = interview.started_at or datetime.utcnow()
    minutes = max(1.0, (datetime.utcnow() - started).total_seconds() / 60)
    interview.integrity_score = compute_integrity_score(
        interview.violations, vmap, minutes
    )


# ══════════════════════════════════════════════════════════════════
# 1.  Log Security Event
# ══════════════════════════════════════════════════════════════════

@bp.route('/log-event', methods=['POST'])
@login_required
@rate_limit(max_requests=120, window_seconds=60)   # generous – events come fast
def log_event():
    """
    Body (JSON):
    {
        "interview_id": 42,
        "event_type":   "tab_switch",   // see VIOLATION_WEIGHTS keys
        "details":      {}              // optional extra info
    }
    """
    try:
        data         = request.get_json(silent=True) or {}
        interview_id = data.get('interview_id')
        event_type   = data.get('event_type', 'unknown')
        details      = data.get('details', {})

        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid interview'}), 403

        # Persist violation on the interview record
        interview.increment_violation(event_type)

        # Update specific shortcut counters on interview
        if event_type == 'fullscreen_exit':
            interview.fullscreen_exits = (interview.fullscreen_exits or 0) + 1
        elif event_type == 'tab_switch':
            interview.tab_switches = (interview.tab_switches or 0) + 1
        elif event_type in ('copy_attempt', 'paste_attempt'):
            interview.copy_attempts = (interview.copy_attempts or 0) + 1

        # Append to violation_log
        append_audit_log(interview, event_type, details)

        # Recalculate integrity
        _update_integrity(interview)

        # Write a proper AuditLog record
        severity = _severity_for_type(event_type)
        audit = AuditLog(
            interview_id=interview_id,
            user_id=session['user_id'],
            event_type=event_type,
            severity=severity,
            ip_address=_get_ip(),
            user_agent=request.headers.get('User-Agent', '')[:512],
            details=json.dumps(details),
        )
        db.session.add(audit)

        # Update lockdown record
        ld = _get_or_create_lockdown(interview_id, session['user_id'])
        ld.total_violations = interview.violations
        if event_type == 'fullscreen_exit':
            ld.fullscreen_exits = interview.fullscreen_exits
            ld.fullscreen_active = False
        if event_type == 'tab_switch':
            ld.tab_switches = interview.tab_switches
        if event_type in ('copy_attempt', 'paste_attempt'):
            ld.copy_attempts = interview.copy_attempts

        db.session.commit()

        # Decide if we should terminate the exam
        should_terminate = interview.integrity_score < 20
        warning_level    = _severity_for_type(event_type)

        return jsonify({
            'success':         True,
            'total_violations': interview.violations,
            'integrity_score':  interview.integrity_score,
            'severity':         warning_level,
            'should_terminate': should_terminate,
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════
# 2.  Heartbeat  (keep-alive, verify lockdown still active)
# ══════════════════════════════════════════════════════════════════

@bp.route('/heartbeat', methods=['POST'])
@login_required
@rate_limit(max_requests=60, window_seconds=60)
def heartbeat():
    """
    Body (JSON):
    {
        "interview_id":    42,
        "fullscreen":      true,
        "tab_visible":     true,
        "screen_width":    1920,
        "screen_height":   1080
    }
    """
    try:
        data         = request.get_json(silent=True) or {}
        interview_id = data.get('interview_id')
        fullscreen   = data.get('fullscreen', False)
        tab_visible  = data.get('tab_visible', True)

        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid interview'}), 403

        ld = _get_or_create_lockdown(interview_id, session['user_id'])
        ld.last_heartbeat    = datetime.utcnow()
        ld.fullscreen_active = fullscreen
        ld.is_locked         = True

        if not fullscreen and interview.status == 'in_progress':
            # Auto-log a fullscreen exit if the client reports not-fullscreen
            pass  # The frontend explicitly sends log-event for this

        db.session.commit()

        return jsonify({
            'success':         True,
            'integrity_score': interview.integrity_score,
            'violations':      interview.violations,
            'fullscreen_ok':   fullscreen,
            'server_time':     datetime.utcnow().isoformat(),
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════
# 3.  Security Status  (used by the dashboard badge)
# ══════════════════════════════════════════════════════════════════

@bp.route('/status/<int:interview_id>', methods=['GET'])
@login_required
def status(interview_id: int):
    try:
        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid interview'}), 403

        vmap      = interview.get_violation_map()
        severity  = compute_severity(vmap)
        ld        = ExamLockdown.query.filter_by(interview_id=interview_id).first()

        return jsonify({
            'success':          True,
            'integrity_score':  interview.integrity_score,
            'total_violations': interview.violations,
            'violation_map':    vmap,
            'severity':         severity,
            'fullscreen_active': ld.fullscreen_active if ld else False,
            'last_heartbeat':   ld.last_heartbeat.isoformat() if ld and ld.last_heartbeat else None,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════
# 4.  Full Security Report
# ══════════════════════════════════════════════════════════════════

@bp.route('/report/<int:interview_id>', methods=['GET'])
@login_required
def report(interview_id: int):
    try:
        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid interview'}), 403

        audits = AuditLog.query.filter_by(interview_id=interview_id)\
            .order_by(AuditLog.timestamp.asc()).all()

        timeline = [{
            'timestamp': a.timestamp.isoformat(),
            'event_type': a.event_type,
            'severity':   a.severity,
            'details':    a.get_details(),
        } for a in audits]

        vmap     = interview.get_violation_map()
        severity = compute_severity(vmap)

        started   = interview.started_at or datetime.utcnow()
        completed = interview.completed_at or datetime.utcnow()
        duration  = (completed - started).total_seconds() / 60

        return jsonify({
            'success':          True,
            'interview_id':     interview_id,
            'integrity_score':  interview.integrity_score,
            'total_violations': interview.violations,
            'violation_map':    vmap,
            'severity':         severity,
            'duration_minutes': round(duration, 1),
            'timeline':         timeline,
            'fullscreen_exits': interview.fullscreen_exits or 0,
            'tab_switches':     interview.tab_switches or 0,
            'copy_attempts':    interview.copy_attempts or 0,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════
# 5.  Lockdown Activate  (called when exam starts)
# ══════════════════════════════════════════════════════════════════

@bp.route('/lockdown/activate', methods=['POST'])
@login_required
def lockdown_activate():
    try:
        data         = request.get_json(silent=True) or {}
        interview_id = data.get('interview_id')

        interview = Interview.query.get(interview_id)
        if not interview or interview.user_id != session['user_id']:
            return jsonify({'error': 'Invalid interview'}), 403

        ld = _get_or_create_lockdown(interview_id, session['user_id'])
        ld.is_locked  = True
        ld.locked_at  = datetime.utcnow()
        ld.fullscreen_active = data.get('fullscreen', False)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Lockdown activated'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════
# 6.  Lockdown Release  (called when exam ends / report generated)
# ══════════════════════════════════════════════════════════════════

@bp.route('/lockdown/release', methods=['POST'])
@login_required
def lockdown_release():
    try:
        data         = request.get_json(silent=True) or {}
        interview_id = data.get('interview_id')

        ld = ExamLockdown.query.filter_by(interview_id=interview_id,
                                          user_id=session['user_id']).first()
        if ld:
            ld.is_locked         = False
            ld.fullscreen_active = False
            db.session.commit()

        return jsonify({'success': True, 'message': 'Lockdown released'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
