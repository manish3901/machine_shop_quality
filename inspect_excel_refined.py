import pandas as pd
import sys

excel_path = 'Daily production planing month of FEB.xlsx'
xl = pd.ExcelFile(excel_path)

sheet_name = xl.sheet_names[0] # Focus on the first sheet
df_raw = pd.read_excel(excel_path, sheet_name=sheet_name)

# Find header row
header_idx = -1
for i, row in df_raw.iterrows():
    if any('Sr. No.' in str(val) for val in row.values):
        header_idx = i
        break

if header_idx != -1:
    print(f"Header found at row {header_idx}")
    # The row ABOVE the data might contain 'A Shift', 'B Shift' etc.
    # Let's peek at row header_idx - 1, header_idx, and header_idx + 1
    peek = df_raw.iloc[header_idx-1:header_idx+2]
    print("\nPeek at header rows:")
    print(peek.astype(str).to_string())
    
    # Re-read with correct header
    df = pd.read_excel(excel_path, sheet_name=sheet_name, skiprows=header_idx+1)
    print("\nColumns after skiprows:")
    for i, col in enumerate(df.columns):
        print(f"{i}: {col}")
        
    print("\nFirst data row:")
    if not df.empty:
        print(df.iloc[0].astype(str).to_string())
else:
    print("Header 'Sr. No.' not found")
