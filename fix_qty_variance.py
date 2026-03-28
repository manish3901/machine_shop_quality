"""Make qty_variance column nullable in production_entries."""
from ms_planning import create_app
from models import db

app = create_app()
with app.app_context():
    with db.engine.connect() as conn:
        result = conn.execute(db.text(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name='production_entries' AND column_name='qty_variance'"
        ))
        row = result.fetchone()
        print('qty_variance column:', row)
        if row and row[1] == 'NO':
            conn.execute(db.text(
                'ALTER TABLE production_entries ALTER COLUMN qty_variance DROP NOT NULL'
            ))
            conn.commit()
            print('SUCCESS: Dropped NOT NULL constraint on qty_variance')
        elif row:
            print('Already nullable, no change needed.')
        else:
            print('Column does not exist in DB — no action needed.')
