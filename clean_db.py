import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def clean_db():
    print("🗑️ connecting to database to drop tables...")
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="MOA",
            user="postgres",
            password="password",
            port=5432
        )
        cur = conn.cursor()
        
        tables = [
            'evidence',
            'production_issues',
            'production_entries',
            'daily_reports',
            'audit_logs',
            'machines',
            'customers',
            'operation_types',
            'issue_types'
        ]
        
        for table in tables:
            print(f"Dropping {table}...")
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            
        conn.commit()
        print("✅ All machine_shop tables dropped.")
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error dropping tables: {e}")

if __name__ == "__main__":
    clean_db()
