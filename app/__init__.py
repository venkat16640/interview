from flask import Flask, g
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from config import config
import os

# Initialize extensions
db = SQLAlchemy()


def create_app(config_name='development'):
    """Application factory pattern"""
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}},
         supports_credentials=True)

    # Create necessary directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['REPORTS_FOLDER'], exist_ok=True)

    # ── Security headers on every response ───────────────────────────
    from app.services.security_service import apply_security_headers, get_csrf_token

    @app.after_request
    def add_security_headers(response):
        return apply_security_headers(response)

    # ── Inject csrf_token into every template context ─────────────────
    @app.context_processor
    def inject_csrf():
        return {'csrf_token': get_csrf_token()}

    # ── Register blueprints ───────────────────────────────────────────
    from app.routes import auth, main, interview, api
    from app.routes import security as security_bp

    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(interview.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(security_bp.bp)

    return app
