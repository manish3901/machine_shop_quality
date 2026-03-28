from ms_planning import create_app
from models import db

app = create_app()
with app.app_context():
    with db.engine.connect() as conn:
        for col in ['qty_variance', 'qty_variance_percent', 'actual_cycle_time']:
            conn.execute(db.text(
                f'ALTER TABLE production_entries ALTER COLUMN {col} DROP NOT NULL'
            ))
            print(f'Made nullable: {col}')
        conn.commit()
    print('Done.')
