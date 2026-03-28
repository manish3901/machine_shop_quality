import pandas as pd
import os
import sys
import logging
from datetime import datetime, timezone
import re

# Add the current directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from app import create_app
from models import db, Machine, Customer, OperationType, ProductionEntry, ProductionIssue, IssueType, EmpMaster

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXCEL_PATH = r"c:\Users\Lenovo\OneDrive - Globalaluminium pvt ltd\Skills\Web_dev\MOA\machine_shop\Daily production planing month of FEB.xlsx"

def get_production_date(sheet_name, shift):
    """
    Parse sheet name like '11-12' and shift to get the correct date.
    Sheets like '11-12' mean B/C shifts are on the 11th, and A shift is on the 12th.
    """
    try:
        if '-' in sheet_name:
            day_parts = sheet_name.split('-')
            day1 = int(re.findall(r'\d+', day_parts[0])[0])
            day2 = int(re.findall(r'\d+', day_parts[1])[0])
            
            if shift in ['B', 'C']:
                return datetime(2026, 2, day1).date()
            else:
                return datetime(2026, 2, day2).date()
        else:
            # Single day like '1' or '2 TO 3'
            day = int(re.findall(r'\d+', sheet_name)[0])
            return datetime(2026, 2, day).date()
    except Exception as e:
        logger.error(f"Error parsing date for sheet {sheet_name}, shift {shift}: {e}")
        return datetime(2026, 2, 1).date()

def extract_issues(remarks):
    """Simple regex to extract issue types from remarks"""
    if not remarks or pd.isna(remarks):
        return []
    
    remarks_lower = str(remarks).lower()
    found_issues = []
    
    mapping = {
        'power': 'Power Cut',
        'machine': 'Machine Breakdown',
        'breakdown': 'Machine Breakdown',
        'material': 'No Material',
        'tooling': 'Tooling Issue',
        'setting': 'Setting Time',
        'wait': 'Waiting',
        'cleaning': 'Cleaning'
    }
    
    for kw, issue_name in mapping.items():
        if kw in remarks_lower:
            found_issues.append(issue_name)
    
    return list(set(found_issues))

def sync_data():
    app = create_app('development')
    with app.app_context():
        logger.info("Starting Master Data and Entry Synchronization...")
        
        try:
            # Clear existing production entries and issues to avoid duplicates and fix IDs
            # Delete issues first due to FK
            num_issues = db.session.query(ProductionIssue).delete()
            num_entries = db.session.query(ProductionEntry).delete()
            db.session.commit()
            logger.info(f"Cleared {num_entries} entries and {num_issues} issues.")
        except Exception as e:
            logger.error(f"Error clearing existing data: {e}")
            db.session.rollback()
            return

        excel_data = pd.ExcelFile(EXCEL_PATH)
        total_records = 0
        
        # Pre-load master data to maps
        machines_map = {m.machine_name.strip().upper(): m for m in Machine.query.all()}
        customers_map = {c.customer_name.strip().upper(): c for c in Customer.query.all()}
        operations_map = {o.operation_name.strip().upper(): o for o in OperationType.query.all()}
        issue_types_map = {i.issue_name.strip().upper(): i for i in IssueType.query.all()}
        
        # Default objects
        if 'AGAM' not in customers_map:
            agam = Customer(customer_name='AGAM', customer_code='AGM', status='Active')
            db.session.add(agam)
            db.session.commit()
            customers_map['AGAM'] = agam
            
        if 'MILLING' not in operations_map:
            milling = OperationType(operation_name='MILLING')
            db.session.add(milling)
            db.session.commit()
            operations_map['MILLING'] = milling

        for sheet_name in excel_data.sheet_names:
            if sheet_name.lower() in ['master', 'summary', 'sheet1']:
                continue
                
            logger.info(f"Processing sheet: {sheet_name}")
            df = excel_data.parse(sheet_name)
            
            # Find header row (contains "Sr. No.")
            header_row_idx = -1
            for i, row in df.iterrows():
                if any("sr. no." in str(val).lower() for val in row.values):
                    header_row_idx = i
                    break
            
            if header_row_idx == -1:
                continue
                
            df.columns = df.iloc[header_row_idx]
            df = df.iloc[header_row_idx + 1:].reset_index(drop=True)
            
            # Column mapping
            col_map = {}
            for col in df.columns:
                c_str = str(col).lower().strip()
                if 'machine' in c_str: col_map['machine'] = col
                elif 'customer' in c_str: col_map['customer'] = col
                elif 'operation' in c_str: col_map['operation'] = col
                elif 'planned' in c_str: col_map['planned'] = col
                elif 'actual' in c_str: col_map['actual'] = col
                elif 'shift' in c_str: col_map['shift'] = col
                elif 'c/t' in c_str: col_map['ct'] = col
                elif 'remarks' in c_str: col_map['remarks'] = col
                elif 'section' in c_str: col_map['section'] = col
                elif 'length' in c_str: col_map['length'] = col

            for _, row in df.iterrows():
                try:
                    m_name = str(row.get(col_map.get('machine'), '')).strip()
                    if not m_name or m_name.lower() in ['nan', 'none', '']: continue
                    
                    # 1. Sync Machine
                    m_key = m_name.upper()
                    if m_key not in machines_map:
                        new_m = Machine(machine_name=m_name, status='Active')
                        db.session.add(new_m)
                        db.session.flush()
                        machines_map[m_key] = new_m
                    machine = machines_map[m_key]
                    
                    # 2. Sync Customer
                    cust_name = str(row.get(col_map.get('customer'), 'AGAM')).strip()
                    if not cust_name or cust_name.lower() in ['nan', 'none']: cust_name = 'AGAM'
                    c_key = cust_name.upper()
                    if c_key not in customers_map:
                        new_c = Customer(customer_name=cust_name, status='Active')
                        db.session.add(new_c)
                        db.session.flush()
                        customers_map[c_key] = new_c
                    customer = customers_map[c_key]
                    
                    # 3. Sync Operation
                    op_name = str(row.get(col_map.get('operation'), 'MILLING')).strip()
                    if not op_name or op_name.lower() in ['nan', 'none']: op_name = 'MILLING'
                    o_key = op_name.upper()
                    if o_key not in operations_map:
                        new_o = OperationType(operation_name=op_name)
                        db.session.add(new_o)
                        db.session.flush()
                        operations_map[o_key] = new_o
                    operation = operations_map[o_key]
                    
                    shift = str(row.get(col_map.get('shift'), 'A')).strip().upper()
                    if shift not in ['A', 'B', 'C']: shift = 'A'
                    
                    prod_date = get_production_date(sheet_name, shift)
                    
                    # NaN Protection
                    def clean_float(val):
                        try:
                            v = float(val)
                            return 0.0 if pd.isna(v) else v
                        except:
                            return 0.0

                    planned = clean_float(row.get(col_map.get('planned'), 0))
                    actual = clean_float(row.get(col_map.get('actual'), 0))
                    ct = clean_float(row.get(col_map.get('ct'), 0))
                    remarks = str(row.get(col_map.get('remarks'), ''))
                    if remarks.lower() in ['nan', 'none']: remarks = ''
                    
                    section = str(row.get(col_map.get('section'), ''))
                    if section.lower() in ['nan', 'none']: section = ''
                    
                    length = clean_float(row.get(col_map.get('length'), 0))
                    
                    # 4. Create Entry
                    entry = ProductionEntry(
                        production_date=prod_date,
                        shift=shift,
                        machine_id=machine.id,
                        customer_id=customer.id,
                        operation_type_id=operation.id,
                        planned_quantity=planned,
                        actual_quantity=actual,
                        cycle_time_seconds=ct,
                        section_number=section,
                        cutlength=length,
                        remarks=remarks,
                        created_by='system_sync'
                    )
                    entry.compute_variance()
                    db.session.add(entry)
                    db.session.flush()
                    
                    # 5. Extract and link Issues
                    issue_names = extract_issues(remarks)
                    for iname in issue_names:
                        ik_key = iname.upper()
                        if ik_key not in issue_types_map:
                            new_it = IssueType(issue_name=iname, category='General')
                            db.session.add(new_it)
                            db.session.flush()
                            issue_types_map[ik_key] = new_it
                        
                        pi = ProductionIssue(
                            production_entry_id=entry.id,
                            issue_type_id=issue_types_map[ik_key].id,
                            impact_minutes=15, # Default impact
                            description=remarks
                        )
                        db.session.add(pi)
                    
                    total_records += 1
                except Exception as e:
                    import traceback
                    logger.error(f"Error processing row: {e}")
                    logger.error(traceback.format_exc())
                    db.session.rollback()
                    continue
            
            try:
                db.session.commit()
            except Exception as e:
                import traceback
                logger.error(f"Commit failed for sheet {sheet_name}: {e}")
                logger.error(traceback.format_exc())
                db.session.rollback()
            
        logger.info(f"Sync complete. Total entries imported: {total_records}")

if __name__ == "__main__":
    sync_data()
