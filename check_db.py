import os
import sys
import json
from app import create_app
from models import db, Machine, Customer, OperationType, EmpMaster, ProductionEntry
from sqlalchemy import inspect

app = create_app('development')
output = []
with app.app_context():
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    output.append(f"Tables in database: {tables}")
    
    for table in ['machines', 'customers', 'operation_types', 'emp_master', 'production_entries']:
        if table in tables:
            columns = [c['name'] for c in inspector.get_columns(table)]
            output.append(f"Columns in {table}: {columns}")
        else:
            output.append(f"CRITICAL: Table {table} is MISSING!")

    try:
        counts = {
            'Machines': Machine.query.count(),
            'Customers': Customer.query.count(),
            'Ops': OperationType.query.count(),
            'Emps': EmpMaster.query.count(),
            'Entries': ProductionEntry.query.count()
        }
        output.append(f"Data counts: {counts}")
    except Exception as e:
        output.append(f"Error querying data: {str(e)}")

with open('db_diag.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))

print("Diagnostic complete. Results in db_diag.txt")
