import os
import sys
from sqlalchemy import text

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from ms_planning import create_app
from models import db

def apply_patch():
    app = create_app('development')
    with app.app_context():
        try:
            # 1. Add entry_no to production_entries
            print("Adding entry_no to production_entries...")
            db.session.execute(text("ALTER TABLE production_entries ADD COLUMN IF NOT EXISTS entry_no VARCHAR(20) UNIQUE;"))
            
            # 2. Add columns to daily_rejections
            print("Updating daily_rejections table...")
            db.session.execute(text("ALTER TABLE daily_rejections ADD COLUMN IF NOT EXISTS production_entry_id INTEGER REFERENCES production_entries(id);"))
            db.session.execute(text("ALTER TABLE daily_rejections ADD COLUMN IF NOT EXISTS shift VARCHAR(1);"))
            
            # 3. Create daily_rejection_supervisors table
            print("Creating daily_rejection_supervisors table...")
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS daily_rejection_supervisors (
                    id SERIAL PRIMARY KEY,
                    rejection_id INTEGER NOT NULL REFERENCES daily_rejections(id) ON DELETE CASCADE,
                    supervisor_emp_id INTEGER NOT NULL REFERENCES emp_master(emp_id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            
            # 4. Create indexes
            print("Creating indexes...")
            db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_drs_rejection_id ON daily_rejection_supervisors(rejection_id);"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_dr_pe_id ON daily_rejections(production_entry_id);"))
            
            db.session.commit()
            print("Successfully applied schema patches.")
            
        except Exception as e:
            db.session.rollback()
            print(f"Error applying patch: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    apply_patch()
