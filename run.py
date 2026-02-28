import os
from app import create_app, db

# Create the Flask application
app = create_app(os.getenv('FLASK_ENV') or 'development')

# Create database tables
with app.app_context():
    db.create_all()
    print("Database initialized successfully!")

if __name__ == '__main__':
    print("Starting Intelligent Interview Platform...")
    print(f"Environment: Production (High Performance)")
    print(f"Server running on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
