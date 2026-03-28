"""Seed default fixed downtime reasons into the DB."""
from ms_planning import create_app
from models import db, DowntimeReason

app = create_app()
with app.app_context():
    defaults = [
        {'reason_name': 'Lunch Break', 'is_fixed': True, 'default_minutes': 30},
        {'reason_name': 'Machine Handover', 'is_fixed': True, 'default_minutes': 30},
        {'reason_name': '5S', 'is_fixed': True, 'default_minutes': 10},
    ]
    for d in defaults:
        r = DowntimeReason.query.filter_by(reason_name=d['reason_name']).first()
        if r:
            r.is_fixed = d['is_fixed']
            r.default_minutes = d['default_minutes']
            print(f'Updated: {d["reason_name"]}')
        else:
            db.session.add(DowntimeReason(
                reason_name=d['reason_name'],
                is_fixed=d['is_fixed'],
                default_minutes=d['default_minutes'],
                status='Active',
                company_id=1
            ))
            print(f'Created: {d["reason_name"]}')
    db.session.commit()
    print('All done.')
