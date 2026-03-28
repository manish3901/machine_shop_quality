import psycopg2
from psycopg2 import extras
import hashlib

def get_db():
    # Using credentials from config.py and verify_manish_reset.py
    return psycopg2.connect(
        host="localhost", 
        database="MOA", 
        user="postgres", 
        password="password", 
        port=5432
    )

def check_user_by_code(emp_code, password):
    print(f"Checking Emp Code: {emp_code}")
    conn = get_db()
    cur = conn.cursor(cursor_factory=extras.RealDictCursor)
    
    # Get user by joining with emp_master on emp_code
    cur.execute("""
        SELECT u.user_id, u.email_login, u.password_hash, u.is_active, u.role_id, u.emp_id, e.emp_code, e.emp_name, e.status as emp_status
        FROM user_login u 
        JOIN emp_master e ON u.emp_id = e.emp_id 
        WHERE e.emp_code = %s
    """, (emp_code,))
    
    user = cur.fetchone()
    
    if not user:
        print(f"[-] No user found with emp_code {emp_code}.")
        cur.close(); conn.close()
        return

    print(f"[+] User Found: {user['email_login']} (ID: {user['user_id']})")
    print(f"[+] Active (user_login): {user['is_active']}")
    print(f"[+] Status (emp_master): {user['emp_status']}")
    print(f"[+] Role ID: {user['role_id']}")
    
    # Hash Info
    stored_hash = user['password_hash']
    print(f"[+] Hash Length: {len(stored_hash)}")
    print(f"[+] Hash Start:  {stored_hash[:10]}...")
    print(f"[+] Hash End:    ...{stored_hash[-10:]}")
    
    # Provided Password Hash
    target_hash = hashlib.sha256(password.encode()).hexdigest()
    print(f"\n[+] Provided Pwd: {password}")
    print(f"[+] Provided Hash: {target_hash[:10]}...{target_hash[-10:]}")
    
    if stored_hash == target_hash:
        print("[+] SUCCESS: Hash MATCHES perfectly.")
    else:
        print("[-] FAILURE: Hash DOES NOT MATCH.")
        # Check some variations
        vars = {
            "Admin123": hashlib.sha256("Admin123".encode()).hexdigest(),
            "admin123": hashlib.sha256("admin123".encode()).hexdigest(),
            "admin1234": hashlib.sha256("admin1234".encode()).hexdigest(),
            "123456": hashlib.sha256("123456".encode()).hexdigest(),
        }
        for name, vh in vars.items():
            if stored_hash == vh:
                print(f"[!] MATCH FOUND with variant: {name}")
                break

    cur.close(); conn.close()

if __name__ == "__main__":
    check_user_by_code("15125", "Admin1234")
