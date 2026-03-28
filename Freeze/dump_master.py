from app import create_app
from models import Machine, Customer, OperationType

app = create_app('development')
with app.app_context():
    print("--- MACHINES ---")
    for m in Machine.query.all():
        print(f"{m.id}|{m.machine_name}")
    
    print("\n--- CUSTOMERS ---")
    for c in Customer.query.all():
        print(f"{c.id}|{c.customer_name}")
    
    print("\n--- OPERATIONS ---")
    for o in OperationType.query.all():
        print(f"{o.id}|{o.operation_name}")
