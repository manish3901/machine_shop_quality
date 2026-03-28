import pandas as pd
from import_excel_data import find_header_row

excel_path = 'Daily production planing month of FEB.xlsx'

for sheet_name in [' 25-26', ' 26-27']:
    try:
        df_full = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        header_idx = find_header_row(df_full.head(20))

        if header_idx != -1:
            # Find machine col
            meta_row = df_full.iloc[header_idx]
            machine_col = -1
            total_plan_col = -1
            
            for c_idx, val in enumerate(meta_row):
                v = str(val).upper()
                if 'MACHINE' in v:
                    machine_col = c_idx
                if 'TOTAL PLAN' in v:
                    total_plan_col = c_idx
                    
            print(f"Sheet {sheet_name}: Machine Col: {machine_col}, Total Plan Col: {total_plan_col}")
            
            if machine_col != -1 and total_plan_col != -1:
                # Dump VMC-5 row
                for r_idx, row in df_full.iterrows():
                    if r_idx <= header_idx: continue
                    m = str(row.iloc[machine_col]).upper().strip()
                    if m == 'VMC-5':
                        tp = row.iloc[total_plan_col]
                        print(f"  VMC-5 Total Plan: {tp}")
        else:
            print(f"Header not found in {sheet_name}")
    except Exception as e:
        print(f"Error reading {sheet_name}: {e}")
