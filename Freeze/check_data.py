import json
from app import create_app
from models import db, ProductionEntry

app = create_app('development')
with app.app_context():
    entries = ProductionEntry.query.order_by(ProductionEntry.production_date.desc()).limit(20).all()
    data = []
    for e in entries:
        data.append({
            'id': e.id,
            'prod_date': str(e.production_date),
            'machine': e.machine.machine_name if e.machine else 'N/A',
            'planned': e.planned_quantity,
            'actual': e.actual_quantity
        })
    print(json.dumps(data, indent=2))
