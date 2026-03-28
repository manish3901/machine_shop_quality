import os
import sys
import pandas as pd
import re

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from ms_planning import create_app
from models import db, Customer, Machine, SectionMaster, SectionCutLength, IdealCycleTime

app = create_app('development')

def parse_time(time_str):
    """Convert '5 MINS' or '120 SEC' to seconds"""
    if pd.isna(time_str): return 0
    time_str = str(time_str).upper()
    match = re.search(r'([\d\.]+)', time_str)
    if not match: return 0
    val = float(match.group(1))
    if 'MIN' in time_str: return val * 60
    return val

def get_or_create_machine(machine_name, m_type='CNC'):
    mach = Machine.query.filter(Machine.machine_name.ilike(f'%{machine_name}%')).first()
    if not mach:
        mach = Machine(machine_name=machine_name, machine_type=m_type)
        db.session.add(mach)
        db.session.commit()
    return mach

def import_excel_data():
    file_path = 'Docs/Cust_Cycle_time_tmp.xlsx'
    df = pd.read_excel(file_path, sheet_name='Sheet1')
    
    with app.app_context():
        db.create_all()
        
        # --- AGAM (Rows 9-24) ---
        print("Importing AGAM...")
        agam = Customer.query.filter(Customer.customer_name.ilike('%AGAM%')).first()
        if not agam:
            agam = Customer(customer_name='AGAM', status='Active')
            db.session.add(agam)
            db.session.commit()
            
        for idx in range(10, 25):
            row = df.iloc[idx]
            sec_num = str(row.iloc[0]).strip()
            if not sec_num or sec_num == 'nan': continue
            
            # Setup 1
            if pd.notna(row.iloc[1]) and pd.notna(row.iloc[2]):
                mach = get_or_create_machine('CNC-4', 'CNC')
                section = SectionMaster.query.filter_by(customer_id=agam.id, section_number=sec_num).first()
                if not section:
                    section = SectionMaster(customer_id=agam.id, section_number=sec_num)
                    db.session.add(section)
                    db.session.commit()
                
                cl_val = 0 # Agam doesn't seem to have specific CL in these rows?
                cl = SectionCutLength.query.filter_by(section_id=section.id, cut_length=cl_val).first()
                if not cl:
                    cl = SectionCutLength(section_id=section.id, cut_length=cl_val)
                    db.session.add(cl)
                    db.session.commit()
                
                ict = IdealCycleTime(
                    section_cut_length_id=cl.id,
                    machine_id=mach.id,
                    process_name='Setup 1',
                    cycle_time_seconds=parse_time(row.iloc[2]),
                    sequence=1
                )
                db.session.add(ict)

        # --- C2 (Rows 57-74) ---
        print("Importing C2...")
        c2 = Customer.query.filter(Customer.customer_name.ilike('%C2%')).first()
        if not c2:
            c2 = Customer(customer_name='C2', status='Active')
            db.session.add(c2)
            db.session.commit()

        for idx in range(58, 75):
            row = df.iloc[idx]
            sec_num = str(row.iloc[0]).strip()
            if not sec_num or sec_num == 'nan': continue
            
            mach = get_or_create_machine('CNC-4', 'CNC')
            section = SectionMaster.query.filter_by(customer_id=c2.id, section_number=sec_num).first()
            if not section:
                section = SectionMaster(customer_id=c2.id, section_number=sec_num)
                db.session.add(section)
                db.session.commit()
            
            cl_val = 0
            cl = SectionCutLength.query.filter_by(section_id=section.id, cut_length=cl_val).first()
            if not cl:
                cl = SectionCutLength(section_id=section.id, cut_length=cl_val)
                db.session.add(cl)
                db.session.commit()

            ict = IdealCycleTime(
                section_cut_length_id=cl.id,
                machine_id=mach.id,
                process_name='Standard Cycle',
                cycle_time_seconds=parse_time(row.iloc[2]),
                sequence=1
            )
            db.session.add(ict)

        db.session.commit()
        print("Import Done.")

if __name__ == "__main__":
    import_excel_data()
