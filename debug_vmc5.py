import pandas as pd
from import_excel_data import find_header_row, find_shift_columns

excel_path = 'Daily production planing month of FEB.xlsx'
sheet_name = ' 25-26'

df_full = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
header_idx = find_header_row(df_full.head(20))

if header_idx != -1:
    meta_row = df_full.iloc[header_idx]
    machine_col = -1
    for c_idx, val in enumerate(meta_row):
        if 'MACHINE' in str(val).upper():
            machine_col = c_idx
            break
            
    # Find plan columns
    plan_actual_row_idx = header_idx + 1
    plan_actual_row = df_full.iloc[plan_actual_row_idx]
    plan_cols = []
    for c_idx, val in enumerate(plan_actual_row):
        if 'PLAN' in str(val).upper() and 'TOTAL' not in str(val).upper():
            plan_cols.append(c_idx)
    plan_cols.sort()
    
    print(f"Plan Columns found at: {plan_cols}")
    
    # Dump VMC-5 row
    for r_idx, row in df_full.iterrows():
        if r_idx <= header_idx: continue
        m = str(row.iloc[machine_col]).upper().strip()
        if m == 'VMC-5':
            print(f"Row {r_idx} for VMC-5:")
            # Print values at plan columns
            for i, pc in enumerate(plan_cols):
                shift = ['B', 'C', 'A'][i] if i < 3 else f"?{i}"
                val = row.iloc[pc]
                print(f"  Shift {shift} (Col {pc}): {val}")
