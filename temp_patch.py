from ms_planning import create_app
from models import db
from sqlalchemy import text
import os

def patch():
    app = create_app('development')
    with app.app_context():
        with open('patch_schema.sql', 'r') as f:
            # Split by semicolon to execute each statement separately
            statements = f.read().split(';')
            for statement in statements:
                if statement.strip():
                    try:
                        db.session.execute(text(statement))
                        print(f"Executed: {statement[:50]}...")
                    except Exception as e:
                        print(f"Error executing statement: {str(e)}")
                        db.session.rollback()
            db.session.commit()
            print("Schema patched successfully!")

if __name__ == "__main__":
    patch()
