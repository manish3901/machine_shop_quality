import pandas as pd

file_path = 'Docs/Cust_Cycle_time_tmp.xlsx'

def find_cust_locations():
    df = pd.read_excel(file_path, sheet_name='Sheet1')
    
    customers = ['C2', 'AGAM', 'MEDIT', 'Q RAILING', 'Q-Railing']
    
    for cust in customers:
        print(f"\n--- Location for {cust} ---")
        mask = df.apply(lambda row: row.astype(str).str.contains(cust, case=False).any(), axis=1)
        indices = df[mask].index.tolist()
        print(f"Indices: {indices}")
        
        for idx in indices[:1]: # Just first occurrence context
            print(f"\nContext around row {idx}:")
            print(df.iloc[idx:idx+30].to_string())

if __name__ == "__main__":
    find_cust_locations()
