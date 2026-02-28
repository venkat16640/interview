"""
Database initialization script - Creates all new tables
"""
import os
import sys

# Ensure we're in the right directory
os.chdir(os.path.dirname(__file__))

print("=" * 70)
print("DATABASE INITIALIZATION - Enhanced Interview Platform")
print("=" * 70)

try:
    print("\n[1/4] Importing Flask app...")
    from app import create_app, db
    print("✅ Flask app imported")
    
    print("\n[2/4] Importing all models...")
    from app.models import (
        User, Interview, Question, EmotionLog,
        CodeSubmission, Hint, HintUsage, PracticeQuestion, Leaderboard
    )
    print("✅ All models imported:")
    print("  - Core models: User, Interview, Question, EmotionLog")
    print("  - New models: CodeSubmission, Hint, HintUsage, PracticeQuestion, Leaderboard")
    
    print("\n[3/4] Creating Flask application...")
    app = create_app(os.getenv('FLASK_ENV') or 'development')
    print(f"✅ App created - Environment: {os.getenv('FLASK_ENV') or 'development'}")
    
    print("\n[4/4] Creating database tables...")
    with app.app_context():
        # Create all tables
        db.create_all()
        print("✅ All tables created/verified successfully!")
        
        # List all tables
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        print(f"\nTotal tables in database: {len(tables)}")
        print("\nTables:")
        for table in sorted(tables):
            print(f"  • {table}")
    
    print("\n" + "=" * 70)
    print("✅ DATABASE INITIALIZATION COMPLETE")
    print("=" * 70)
    print("\n🎉 New Features Ready:")
    print("  • Code submission tracking with test cases")
    print("  • Multi-language code execution (Python, JavaScript)")
    print("  • Performance metrics (execution time, memory usage)")
    print("  • Progressive hints system")
    print("  • Global leaderboard")
    print("  • Practice mode")
    print("\n✅ Ready to start the application!")
    print("   Run: python run.py")
    print("=" * 70)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
