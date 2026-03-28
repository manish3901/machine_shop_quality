import pandas as pd
import json

excel_path = 'Daily production planing month of FEB.xlsx'
xl = pd.ExcelFile(excel_path)

results = {}

for sheet_name in xl.sheet_names[:3]: # Check first 3 sheets
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    
    # Find header row
    header_idx = -1
    for i, row in df.iterrows():
        if any('Sr. No.' in str(val) for val in row.values):
            header_idx = i
            break
            
    if header_idx != -1:
        # Get the actual columns and some data
        df_header = pd.read_excel(excel_path, sheet_name=sheet_name, skiprows=header_idx)
        cols = [str(c) for c in df_header.columns]
        data_rows = df_header.head(5).values.tolist() if hasattr(df_header, 'head') else []
        results[sheet_name] = {
            'columns': cols,
            'sample_data': df_header.head(5).astype(str).values.tolist()
        }
    else:
        results[sheet_name] = "Header not found"

print(json.dumps(results, indent=2))
