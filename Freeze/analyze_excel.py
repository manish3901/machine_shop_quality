import pandas as pd
import json

excel_path = 'Daily production planing month of FEB.xlsx'
try:
    xl = pd.ExcelFile(excel_path)
    sheet_names = xl.sheet_names
    print(f"Sheet Names: {sheet_names}")
    
    # Analyze the first few data sheets
    data_samples = {}
    for sheet in sheet_names[:3]:
        df = pd.read_excel(excel_path, sheet_name=sheet, nrows=5)
        data_samples[sheet] = df.to_dict(orient='records')
        print(f"\n--- Sheet: {sheet} ---")
        print(df.columns.tolist())
        print(df.head())

    with open('excel_analysis.json', 'w') as f:
        json.dump({'sheet_names': sheet_names, 'samples': data_samples}, f, indent=2, default=str)
except Exception as e:
    print(f"Error reading Excel: {str(e)}")
