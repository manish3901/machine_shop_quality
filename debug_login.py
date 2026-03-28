import os
import sys
import hashlib
from sqlalchemy import text

# Setup paths as in ms_planning.py
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if current_dir not in sys.path:
    sys.path.append(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from ms_planning import create_app
from models import db

app = create_app('development')
email_to_check = 'manish@globalaluminium.com'
password_to_check = 'Admin1234'

with app.app_context():
    print(f"Checking user: {email_to_check} / Emp Code: 15125")
    
    # 1. Check if user exists
    query = text("SELECT * FROM user_login WHERE email_login = :email")
    user = db.session.execute(query, {'email': email_to_check}).fetchone()
    
    if not user:
        print(f"[-] User {email_to_check} NOT FOUND in user_login table.")
        # Try finding by emp_code if possible (joining with emp_master)
        print("\nSearching by emp_code 15125...")
        emp_query = text("""
            SELECT u.*, e.emp_code, e.emp_name 
            FROM user_login u 
            JOIN emp_master e ON u.emp_id = e.emp_id 
            WHERE e.emp_code = '15125'
        """)
        user_by_code = db.session.execute(emp_query).fetchone()
        if user_by_code:
            print(f"[!] Found user by emp_code: {user_by_code.email_login}")
            user = user_by_code
        else:
            print("[-] No user found with emp_code 15125.")
            user = None

    if user:
        print(f"[+] User found: ID={user.user_id}, Email={user.email_login}, Active={user.is_active}, Role={user.role_id}")
        
        # 2. Check password
        target_hash = hashlib.sha256(password_to_check.encode()).hexdigest()
        print(f"Target Hash: {target_hash}")
        print(f"Stored Hash: {user.password_hash}")
        
        if user.password_hash == target_hash:
            print("[+] Password hash MATCHES.")
        else:
            print("[-] Password hash DOES NOT MATCH.")
            
        # 3. Check if active
        if not user.is_active:
            print("[-] User account is INACTIVE (is_active=False).")

        # 4. Check emp_master link
        if user.emp_id:
            emp = db.session.execute(text("SELECT emp_name, status, emp_code FROM emp_master WHERE emp_id = :emp_id"), {'emp_id': user.emp_id}).fetchone()
            if emp:
                print(f"[+] Linked Employee: {emp.emp_name} ({emp.emp_code}), Status: {emp.status}")
            else:
                print(f"[-] Linked Employee ID {user.emp_id} NOT FOUND in emp_master.")
