from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from functools import wraps
from app import db
from app.models import User, Interview

bp = Blueprint('main', __name__)

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first!', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@bp.route('/')
def index():
    """Landing page"""
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')


@bp.route('/dashboard')
@login_required
def dashboard():
    """User dashboard"""
    user = User.query.get(session['user_id'])
    interviews = Interview.query.filter_by(user_id=user.id).order_by(Interview.started_at.desc()).all()
    return render_template('dashboard.html', user=user, interviews=interviews, current_user=user)


@bp.route('/upload-reference-photo', methods=['POST'])
@login_required
def upload_reference_photo():
    """Handle reference photo upload (file or base64)"""
    import os
    from werkzeug.utils import secure_filename
    
    # 1. Handle live camera capture (Base64 JSON)
    if request.is_json:
        data = request.get_json()
        if 'image' in data:
            try:
                import base64
                image_data = data['image']
                image_bytes = base64.b64decode(image_data.split(',')[1])
                upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'reference_photos')
                os.makedirs(upload_dir, exist_ok=True)
                
                user_id = session['user_id']
                filename = secure_filename(f"user_{user_id}_reference.jpg")
                file_path = os.path.join(upload_dir, filename)
                with open(file_path, 'wb') as f:
                    f.write(image_bytes)
                    
                user = User.query.get(user_id)
                user.reference_photo_path = f"uploads/reference_photos/{filename}"
                db.session.commit()
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)}, 500
        return {'success': False, 'error': 'No image provided'}, 400

    # 2. Handle file upload (Form data)
    if 'photo' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('main.dashboard'))
    
    file = request.files['photo']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('main.dashboard'))
    
    if file:
        try:
            # Ensure upload directory exists
            upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'reference_photos')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Save file
            user_id = session['user_id']
            filename = secure_filename(f"user_{user_id}_reference.jpg")
            file_path = os.path.join(upload_dir, filename)
            file.save(file_path)
            
            # Update user record
            user = User.query.get(user_id)
            user.reference_photo_path = f"uploads/reference_photos/{filename}"
            db.session.commit()
            
            flash('Reference photo updated successfully! Identity verification enabled.', 'success')
            
        except Exception as e:
            flash(f'Error uploading photo: {str(e)}', 'danger')
            
    return redirect(url_for('main.dashboard'))


@bp.route('/update-avatar', methods=['POST'])
@login_required
def update_avatar():
    """Handle avatar preference update"""
    avatar = request.form.get('avatar')
    if avatar:
        try:
            user = User.query.get(session['user_id'])
            user.avatar_preference = avatar
            db.session.commit()
            flash('Interviewer avatar updated successfully!', 'success')
        except Exception as e:
            flash(f'Error updating avatar: {str(e)}', 'danger')
            
    return redirect(url_for('main.dashboard'))
