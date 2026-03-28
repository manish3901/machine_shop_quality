import psycopg2
from psycopg2 import extras
import hashlib

def get_db():
    return psycopg2.connect(host="localhost", database="MOA", user="postgres", password="password", port=5432)

def final_report():
    conn = get_db()
    cur = conn.cursor(cursor_factory=extras.RealDictCursor)
    
    email = "manish@globalaluminium.com"
    pwd_to_test = "Admin1234"
    emp_code = "15125"
    
    print("--- LOGIN DIAGNOSTIC REPORT ---")
    
    cur.execute("""
        SELECT u.user_id, u.email_login, u.password_hash, u.is_active, u.role_id, e.emp_code, e.emp_name, e.status as emp_status
        FROM user_login u 
        JOIN emp_master e ON u.emp_id = e.emp_id 
        WHERE e.emp_code = %s OR u.email_login = %s
    """, (emp_code, email))
    
    rows = cur.fetchall()
    
    if not rows:
        print("[-] User NOT FOUND by email or emp_code.")
        return

    for user in rows:
        print(f"\nUser: {user['email_login']} | Emp Code: {user['emp_code']}")
        print(f"Name: {user['emp_name']}")
        print(f"Status (Login): {'ACTIVE' if user['is_active'] else 'INACTIVE'}")
        print(f"Status (Emp):   {user['emp_status']}")
        
        # Hash Comparison
        stored_hash = user['password_hash']
        provided_hash = hashlib.sha256(pwd_to_test.encode()).hexdigest()
        
        print(f"Stored Hash:   {stored_hash}")
        print(f"Provided Hash: {provided_hash} (for '{pwd_to_test}')")
        
        if stored_hash == provided_hash:
            print("[+] Result: PASSWORD MATCHES.")
        else:
            print("[-] Result: PASSWORD DOES NOT MATCH.")
            
            # Check for common variants
            variants = ["Admin123", "admin123", "Global@123", "admin1234", "Admin@123"]
            for v in variants:
                if stored_hash == hashlib.sha256(v.encode()).hexdigest():
                    print(f"[!] SUGGESTION: The stored hash matches the password '{v}'.")
                    break

    cur.close(); conn.close()
    print("\n--- END OF REPORT ---")

if __name__ == "__main__":
    final_report()
