import os
import sys

# Add the current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ms_planning import create_app
from models import (
    db, Machine, Customer, OperationType, IssueType, ProductionEntry, EmpMaster,
    ProductionEntryOperator, SectionMaster, SectionCutLength, IdealCycleTime,
    DowntimeReason, ProductionPlannedDowntime
)

def reset_db():
    app = create_app('development')
    with app.app_context():
        print("🗑️ Dropping Machine Shop tables...")
        # We can use db.drop_all() if we are careful about EmpMaster
        # But for safety, let's just drop the ones we manage.
        from models import (
            ProductionEntry, Machine, Customer, OperationType, IssueType, 
            ProductionEntryOperator, SectionMaster, SectionCutLength, 
            IdealCycleTime, DowntimeReason, ProductionPlannedDowntime
        )
        
        # Drop in reverse order of dependencies
        ProductionPlannedDowntime.__table__.drop(db.engine, checkfirst=True)
        ProductionEntryOperator.__table__.drop(db.engine, checkfirst=True)
        IdealCycleTime.__table__.drop(db.engine, checkfirst=True)
        SectionCutLength.__table__.drop(db.engine, checkfirst=True)
        SectionMaster.__table__.drop(db.engine, checkfirst=True)
        ProductionEntry.__table__.drop(db.engine, checkfirst=True)
        Machine.__table__.drop(db.engine, checkfirst=True)
        Customer.__table__.drop(db.engine, checkfirst=True)
        OperationType.__table__.drop(db.engine, checkfirst=True)
        IssueType.__table__.drop(db.engine, checkfirst=True)
        DowntimeReason.__table__.drop(db.engine, checkfirst=True)
        
        print("✨ Creating tables with new schema...")
        db.create_all()
        print("✅ Tables created.")

        from init_data import init_data
        init_data()
        print("✅ Initial data seeded.")

if __name__ == "__main__":
    reset_db()
