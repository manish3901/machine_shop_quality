import pandas as pd
import numpy as np

excel_path = 'Daily production planing month of FEB.xlsx'
xl = pd.ExcelFile(excel_path)

for sheet_name in xl.sheet_names[:10]:
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    header_idx = -1
    for i, row in df.iterrows():
        if any('Sr. No.' in str(val) for val in row.values):
            header_idx = i
            break
            
    if header_idx == -1: continue
    
    df_data = pd.read_excel(excel_path, sheet_name=sheet_name, skiprows=header_idx+1)
    
    # Check for rows with Actual > 0 but Plan == 0
    # Positional indices from import script:
    # B: P=7, A=8
    # C: P=10, A=11
    # A: P=13, A=14
    # Total Plan: 16
    
    anomalies = []
    for idx, row in df_data.iterrows():
        machine = str(row.iloc[1])
        if 'NAN' in machine.upper() or 'TOTAL' in machine.upper(): continue
        
        for s_p, s_a, s_name in [(7, 8, 'B'), (10, 11, 'C'), (13, 14, 'A')]:
            p = row.iloc[s_p] if s_p < len(row) else 0
            a = row.iloc[s_a] if s_a < len(row) else 0
            tp = row.iloc[16] if 16 < len(row) else 0
            
            p_val = float(p) if pd.notnull(p) and str(p) != 'nan' else 0
            a_val = float(a) if pd.notnull(a) and str(a) != 'nan' else 0
            tp_val = float(tp) if pd.notnull(tp) and str(tp) != 'nan' else 0
            
            if a_val > 0 and p_val == 0:
                anomalies.append({
                    'Machine': machine,
                    'Shift': s_name,
                    'Actual': a_val,
                    'Plan': p_val,
                    'TotalPlan': tp_val
                })
                
    if anomalies:
        print(f"\nSheet: {sheet_name} - Found {len(anomalies)} anomalies")
        # Print first 5 anomalies
        for a in anomalies[:5]:
            print(f"  {a['Machine']} (Shift {a['Shift']}): Actual={a['Actual']}, Plan={a['Plan']}, TotalPlan={a['TotalPlan']}")
