import pandas as pd
import os
import re
from datetime import datetime, date
from app import create_app
from models import db, ProductionEntry, Machine, Customer, OperationType

def get_db_lookups(app):
    with app.app_context():
        machines = {m.machine_name.upper(): m.id for m in Machine.query.all()}
        customers = {c.customer_name.upper(): c.id for c in Customer.query.all()}
        operations = {o.operation_name.upper(): o.id for o in OperationType.query.all()}
        return machines, customers, operations

def parse_sheet_date(sheet_name):
    """Parse '11-12' or '11 TO 12' or ' 25-26' into start and end days for Feb 2026"""
    cleaned = re.sub(r'\s+', ' ', sheet_name).upper().replace('TO', '-').strip()
    match = re.search(r'(\d+)\s*-\s*(\d+)', cleaned)
    if match:
        day1 = int(match.group(1))
        # Handle Month transition (e.g. 28-1)
        day2 = int(match.group(2))
        
        try:
            # Assuming Feb 2026 for now as per filename
            date1 = date(2026, 2, day1)
            
            # If day2 < day1, it might be next month (March)
            month2 = 2
            if day2 < day1:
                month2 = 3
                
            date2 = date(2026, month2, day2)
            return date1, date2
        except:
            return None, None
    return None, None

def find_header_row(df):
    """Find the row index containing 'Sr. No.' or 'Machine'"""
    for i, row in df.iterrows():
        row_str = str(row.values).upper()
        if 'SR. NO.' in row_str or 'NAME OF MACHINE' in row_str:
            return i
    return -1

def parse_cycle_time(ct_val):
    """Parse cycle time from various Excel formats into seconds"""
    try:
        # Remove text
        s = re.sub(r'[^\d.]', '', str(ct_val))
        if not s: return 0
        val = float(s)
        
        # Heuristics
        # If small (< 10), likely minutes. e.g. 5 => 300s
        if val < 10: return int(val * 60)
        
        # If reasonable seconds (10 - 300)
        if 10 <= val <= 500: return int(val)
        
        # If encoded mmss e.g. 2123 (2m 12.3s -> 132s) or 90129 (??)
        # Let's try mmss logic: last 2 digits are seconds/fraction
        # 2123 -> 21m 23s (too big) or 2m 12s??
        
        # Let's try splitting
        if val > 1000:
             # Assume m...ss
             # e.g. 2123 -> 2m 12.3s -> 132s
             # e.g. 1030 -> 1m 3s No, 10m 30s.
             
             # Try interpreting as "digits are sequence"
             # 2 1 2 3 -> 2 mins, 12.3 secs?
             # This specific format seems to be m + ss + fraction
             
             s_str = str(int(val))
             if len(s_str) >= 3:
                 start = int(s_str[:-2]) # mins
                 end = int(s_str[-2:])   # secs
                 if start < 100 and end < 60:
                     return start * 60 + end
                     
             # Fallback: treat as seconds directly? 2123s = 35 mins. Too high.
             # Maybe milliseconds? 2.1s is too fast.
             
        # Fallback for weird values: return 0 to trigger Actual fallback
        return 0
    except:
        return 0

def calculate_plan_fallback(ct_seconds, actual, hours=8):
    """Calculate plan if missing, based on C/T or Actual"""
    if ct_seconds > 0:
        available_seconds = hours * 3600
        calc_plan = int(available_seconds / ct_seconds)
        # Sanity check: if calculated plan is wildly different from actual (e.g. 10x),
        # use Actual to be safe.
        if actual > 0:
            ratio = calc_plan / actual
            if 0.5 <= ratio <= 2.0:
                return calc_plan
    
    # Ultimate fallback: Plan = Actual (100% efficiency)
    return actual if actual > 0 else 0

def import_data():
    app = create_app('development')
    machines_map, customers_map, ops_map = get_db_lookups(app)
    
    excel_path = 'Daily production planing month of FEB.xlsx'
    xl = pd.ExcelFile(excel_path)
    
    total_updated = 0
    total_added = 0
    
    sheets_to_process = xl.sheet_names # Parse all sheets
    
    for sheet_name in sheets_to_process:
        print(f"\nProcessing sheet: {sheet_name}")
        date1, date2 = parse_sheet_date(sheet_name)
        if not date1:
            print(f"Skipping {sheet_name} - could not parse date")
            continue
            
        # Read first few rows to find header
        df_raw = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, nrows=10)
        header_idx = find_header_row(df_raw)
        
        if header_idx == -1:
            print(f"Skipping {sheet_name} - Header not found")
            continue
            
        # Re-read full dataframe
        df_full = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        
        # Plan/Actual row is usually header + 1
        plan_actual_row_idx = header_idx + 1
        if plan_actual_row_idx >= len(df_full):
            continue
            
        plan_actual_row = df_full.iloc[plan_actual_row_idx]
        
        # dynamic shift mapping logic (retained)
        plan_cols = []
        for c_idx, val in enumerate(plan_actual_row):
            if 'PLAN' in str(val).upper() and 'TOTAL' not in str(val).upper():
                plan_cols.append(c_idx)
                
        shift_col_map = {}
        if len(plan_cols) >= 3:
            plan_cols.sort()
            shift_col_map['B'] = {'p': plan_cols[0], 'a': plan_cols[0]+1}
            shift_col_map['C'] = {'p': plan_cols[1], 'a': plan_cols[1]+1}
            shift_col_map['A'] = {'p': plan_cols[2], 'a': plan_cols[2]+1}
        else:
             continue # Skip if cant map

        # Map Metadata Columns
        meta_row = df_full.iloc[header_idx]
        col_map = {}
        for c_idx, val in enumerate(meta_row):
            v = str(val).upper()
            if 'MACHINE' in v: col_map['machine'] = c_idx
            elif 'CUSTOMER' in v: col_map['customer'] = c_idx
            elif 'SEC' in v: col_map['sec'] = c_idx
            elif 'LENGTH' in v: col_map['length'] = c_idx
            elif 'OPERATION' in v: col_map['op'] = c_idx
            elif 'C/T' in v: col_map['ct'] = c_idx
            
        if 'machine' not in col_map: continue
            
        # Iterate Data Rows
        with app.app_context():
            for r_idx in range(plan_actual_row_idx + 1, len(df_full)):
                row = df_full.iloc[r_idx]
                
                if pd.isna(row[col_map['machine']]) or 'TOTAL' in str(row[col_map['machine']]).upper(): break
                    
                machine_name = str(row[col_map['machine']]).strip().upper()
                if not machine_name or machine_name == 'NAN': continue
                
                m_id = machines_map.get(machine_name)
                if not m_id: continue
                
                # Get details
                cust_name = str(row[col_map.get('customer', -1)]) if 'customer' in col_map else 'AGAM'
                c_id = customers_map.get(cust_name.strip().upper(), customers_map.get('AGAM'))
                
                op_name = str(row[col_map.get('op', -1)]) if 'op' in col_map else 'MILLING'
                o_id = ops_map.get(op_name.strip().upper(), ops_map.get('MILLING'))

                try:
                    ct_raw = row[col_map['ct']] if 'ct' in col_map else 0
                    ct_seconds = parse_cycle_time(ct_raw)
                except:
                    ct_seconds = 0
                
                shifts = [
                    {'name': 'B', 'date': date1},
                    {'name': 'C', 'date': date1},
                    {'name': 'A', 'date': date2}
                ]
                
                for s in shifts:
                    cols = shift_col_map.get(s['name'])
                    if not cols: continue
                    
                    try:
                        p_val = row[cols['p']]
                        a_val = row[cols['a']]
                        
                        planned = int(float(p_val)) if pd.notnull(p_val) and str(p_val).replace('.','').isdigit() else 0
                        actual = int(float(a_val)) if pd.notnull(a_val) and str(a_val).replace('.','').isdigit() else 0
                        
                        # UPSERT LOGIC
                        existing = ProductionEntry.query.filter_by(
                            production_date=s['date'],
                            shift=s['name'],
                            machine_id=m_id
                        ).first()
                        
                        # Logic:
                        # 1. If Excel has data (Plan > 0 or Act > 0), use Excel.
                        # 2. If Excel is 0/0, but DB has Actual > 0 and Plan == 0, Backfill Plan.
                        
                        excel_has_data = (planned > 0 or actual > 0)
                        
                        if not excel_has_data and not existing:
                            continue
                            
                        if existing:
                            # Use DB actual if Excel is 0 (assume DB is source of truth for Actuals if Excel empty)
                            # Or if Excel has Actual, overwrite DB? 
                            # User said "sync plan". Let's assume production is correct in DB if Excel is 0.
                            
                            target_actual = actual if actual > 0 else existing.actual_quantity
                            target_plan = planned
                            
                            # Fallback calc
                            if target_plan == 0 and target_actual > 0:
                                target_plan = calculate_plan_fallback(ct_seconds, target_actual)
                            
                            changes = False
                            if existing.planned_quantity != target_plan:
                                existing.planned_quantity = target_plan
                                changes = True
                                
                            if actual > 0 and existing.actual_quantity != actual:
                                existing.actual_quantity = actual
                                changes = True
                                
                            if changes:
                                existing.compute_variance()
                                if existing.cycle_time_seconds == 0 and ct_seconds > 0:
                                    existing.cycle_time_seconds = ct_seconds
                                total_updated += 1
                        else:
                            # New entry, Excel must have data
                            if not excel_has_data: continue
                            
                            # Fallback calc for new entry
                            if planned == 0 and actual > 0:
                                planned = calculate_plan_fallback(ct_seconds, actual)
                                
                            new_entry = ProductionEntry(
                                production_date=s['date'],
                                shift=s['name'],
                                shift_index={'A':1, 'B':2, 'C':3}[s['name']],
                                machine_id=m_id,
                                customer_id=c_id,
                                operation_type_id=o_id,
                                planned_quantity=planned,
                                actual_quantity=actual,
                                cycle_time_seconds=ct_seconds,
                                created_by='excel_sync'
                            )
                            new_entry.compute_variance()
                            db.session.add(new_entry)
                            total_added += 1
                            
                    except Exception:
                        pass
                            
                    except Exception:
                        pass
            
            db.session.commit()
            print(f"Sheet done.")
            
    print(f"\nSync Complete. Added: {total_added}, Updated: {total_updated}")

if __name__ == '__main__':
    import_data()
