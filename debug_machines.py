import pandas as pd
from import_excel_data import find_header_row

excel_path = 'Daily production planing month of FEB.xlsx'
sheet_name = ' 25-26'

df_raw = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, nrows=20)
header_idx = find_header_row(df_raw)
print(f"Header found at: {header_idx}")

if header_idx != -1:
    df_full = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
    meta_row = df_full.iloc[header_idx]
    machine_col = -1
    for c_idx, val in enumerate(meta_row):
        if 'MACHINE' in str(val).upper():
            machine_col = c_idx
            break
            
    print(f"Machine column index: {machine_col}")
    
    if machine_col != -1:
        print("Machine names in Excel:")
        machines = df_full.iloc[header_idx+1:, machine_col].dropna().unique()
        for m in machines:
            if 'TOTAL' not in str(m).upper():
                print(f"'{m}'")
