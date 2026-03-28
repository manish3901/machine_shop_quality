"""
Initialize master data for Machine Shop Production Planning System
Run this script after database setup to load initial machines, customers, etc.
"""

from app import create_app, db
from models import Machine, Customer, OperationType, IssueType
import sys

def init_data():
    """Initialize master data"""
    
    app = create_app('development')
    
    with app.app_context():
        print("🔄 Initializing master data...")
        
        # ==================== MACHINES ====================
        print("\n📦 Adding machines...")
        machines = [
            Machine(machine_name='VMC-1', machine_type='VMC', status='Active'),
            Machine(machine_name='VMC-2', machine_type='VMC', status='Active'),
            Machine(machine_name='VMC-3', machine_type='VMC', status='Active'),
            Machine(machine_name='VMC-4', machine_type='VMC', status='Active'),
            Machine(machine_name='VMC-5', machine_type='VMC', status='Active'),
            Machine(machine_name='CNC-1', machine_type='CNC', status='Active'),
            Machine(machine_name='CNC-2', machine_type='CNC', status='Active'),
            Machine(machine_name='CNC-3', machine_type='CNC', status='Active'),
            Machine(machine_name='CNC-4', machine_type='CNC', status='Active'),
            Machine(machine_name='CNC-5', machine_type='CNC', status='Active'),
            Machine(machine_name='CNC-6', machine_type='CNC', status='Active'),
        ]
        
        for machine in machines:
            if not Machine.query.filter_by(machine_name=machine.machine_name).first():
                db.session.add(machine)
                print(f"  ✓ Added {machine.machine_name}")
        
        # ==================== CUSTOMERS ====================
        print("\n🏢 Adding customers...")
        customers = [
            Customer(customer_name='C2', customer_code='C2', status='Active'),
            Customer(customer_name='AGAM', customer_code='AGAM', status='Active'),
            Customer(customer_name='Q-RAILING', customer_code='Q-RAILING', status='Active'),
        ]
        
        for customer in customers:
            if not Customer.query.filter_by(customer_name=customer.customer_name).first():
                db.session.add(customer)
                print(f"  ✓ Added {customer.customer_name}")
        
        # ==================== OPERATION TYPES ====================
        print("\n⚙️ Adding operation types...")
        operations = [
            OperationType(
                operation_name='SLITTING',
                description='Slitting operation',
                standard_cycle_time_seconds=360  # 6 min
            ),
            OperationType(
                operation_name='MILLING',
                description='Milling operation',
                standard_cycle_time_seconds=300  # 5 min
            ),
            OperationType(
                operation_name='DRILLING',
                description='Drilling operation',
                standard_cycle_time_seconds=180  # 3 min
            ),
            OperationType(
                operation_name='ALL',
                description='All operations',
                standard_cycle_time_seconds=900  # 15 min
            ),
            OperationType(
                operation_name='2ND',
                description='Second operation',
                standard_cycle_time_seconds=600  # 10 min
            ),
            OperationType(
                operation_name='REDIUS',
                description='Radius/Rounding operation',
                standard_cycle_time_seconds=180  # 3 min
            ),
            OperationType(
                operation_name='C/T',
                description='Complex operation',
                standard_cycle_time_seconds=600  # 10 min
            ),
            OperationType(
                operation_name='SETUP',
                description='Setup/Changeover',
                standard_cycle_time_seconds=1200  # 20 min
            ),
        ]
        
        for operation in operations:
            if not OperationType.query.filter_by(operation_name=operation.operation_name).first():
                db.session.add(operation)
                print(f"  ✓ Added {operation.operation_name}")
        
        # ==================== ISSUE TYPES ====================
        print("\n🚨 Adding issue types...")
        issues = [
            IssueType(
                issue_name='No Operator',
                category='NO_OPERATOR',
                severity='Critical',
                description='Operator not available for the shift'
            ),
            IssueType(
                issue_name='No Material',
                category='NO_MATERIAL',
                severity='Critical',
                description='Required material/component not available'
            ),
            IssueType(
                issue_name='Setup Delay',
                category='SETUP_DELAY',
                severity='High',
                description='Machine setup/changeover taking longer than expected'
            ),
            IssueType(
                issue_name='QC Issue',
                category='QC_ISSUE',
                severity='High',
                description='Quality check rejection, parts need rework'
            ),
            IssueType(
                issue_name='Machine Breakdown',
                category='BREAKDOWN',
                severity='Critical',
                description='Machine mechanical or electrical failure'
            ),
            IssueType(
                issue_name='Tool Change',
                category='TOOL_CHANGE',
                severity='Medium',
                description='Tool replacement or maintenance required'
            ),
            IssueType(
                issue_name='Power Failure',
                category='BREAKDOWN',
                severity='Critical',
                description='Electrical power failure'
            ),
            IssueType(
                issue_name='Waiting for Job',
                category='NO_MATERIAL',
                severity='Medium',
                description='Waiting for next job/work order'
            ),
        ]
        
        for issue in issues:
            if not IssueType.query.filter_by(issue_name=issue.issue_name).first():
                db.session.add(issue)
                print(f"  ✓ Added {issue.issue_name}")
        

        # Commit all changes
        db.session.commit()
        
        # Print summary
        print("\n" + "="*50)
        print("✅ Master Data Initialized Successfully!")
        print("="*50)
        print(f"📦 Machines: {Machine.query.count()}")
        print(f"🏢 Customers: {Customer.query.count()}")
        print(f"⚙️  Operations: {OperationType.query.count()}")
        print(f"🚨 Issue Types: {IssueType.query.count()}")
        print("="*50)
        print("\n🚀 Ready to start entering production data!")
        print("   Visit: http://localhost:5000/production-entry")


if __name__ == '__main__':
    try:
        init_data()
    except Exception as e:
        print(f"\n❌ Error during initialization: {str(e)}")
        sys.exit(1)
