import os
import sys
from sqlalchemy import text
from models import db
from flask import Flask

def apply_patch():
    app = Flask(__name__)
    # Fallback to local sqlite if DB_URL not set, but usually we have it in config
    # Loading config from the app
    sys.path.append(os.getcwd())
    try:
        from config import Config
        app.config.from_object(Config)
    except ImportError:
        # Try finding where config is
        app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    
    db.init_app(app)
    
    with app.app_context():
        try:
            # Add new columns to production_entries
            db.session.execute(text("ALTER TABLE production_entries ADD COLUMN IF NOT EXISTS ideal_cycle_time DOUBLE PRECISION;"))
            db.session.execute(text("ALTER TABLE production_entries ADD COLUMN IF NOT EXISTS actual_cycle_time DOUBLE PRECISION;"))
            db.session.execute(text("ALTER TABLE production_entries ADD COLUMN IF NOT EXISTS total_time_taken_minutes INTEGER DEFAULT 0;"))
            db.session.execute(text("ALTER TABLE production_entries ADD COLUMN IF NOT EXISTS total_ideal_time_minutes DOUBLE PRECISION DEFAULT 0.0;"))
            
            # Optionally rename or remove old column if you are sure
            # db.session.execute(text("ALTER TABLE production_entries DROP COLUMN IF EXISTS cycle_time_seconds;"))
            
            db.session.commit()
            print("Successfully applied production time tracking patch.")
        except Exception as e:
            db.session.rollback()
            print(f"Error applying patch: {e}")

if __name__ == "__main__":
    apply_patch()
