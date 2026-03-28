from functools import wraps
from flask import session, redirect, url_for, request, flash
from sqlalchemy import text

from models import db

MACHINE_SHOP_MODULE_CODE = 'MACHINE_SHOP'
FULL_ACCESS_ROLE_NAMES = {'admin', 'ceo', 'hod', 'avp', 'gm'}
MODULE_ALLOWED_ROLE_NAMES = FULL_ACCESS_ROLE_NAMES | {'supervisor'}


def _has_module_access(user_id, module_code=MACHINE_SHOP_MODULE_CODE):
    """Return True when the user has active view access to the module."""
    if not user_id:
        return False
    row = db.session.execute(text("""
        SELECT 1
        FROM user_module_access uma
        JOIN modules m ON m.module_id = uma.module_id
        JOIN user_login u ON u.user_id = uma.user_id
        WHERE uma.user_id = :user_id
          AND m.module_code = :module_code
          AND COALESCE(m.is_active, TRUE) = TRUE
          AND COALESCE(uma.is_active, TRUE) = TRUE
          AND COALESCE(uma.can_view, FALSE) = TRUE
          AND COALESCE(u.is_active, TRUE) = TRUE
        LIMIT 1
    """), {'user_id': user_id, 'module_code': module_code}).fetchone()
    return row is not None


def _get_role_name(role_id):
    """Return normalized role name for the current user."""
    if not role_id:
        return ''
    row = db.session.execute(text("""
        SELECT role_name
        FROM roles
        WHERE role_id = :role_id
          AND COALESCE(is_active, TRUE) = TRUE
        LIMIT 1
    """), {'role_id': role_id}).fetchone()
    return (row[0] or '').strip().lower() if row else ''


def _has_role_access(role_id, *, allow_master_data=False):
    role_name = _get_role_name(role_id)
    if not role_name:
        return False
    if allow_master_data:
        return role_name in FULL_ACCESS_ROLE_NAMES
    return role_name in MODULE_ALLOWED_ROLE_NAMES

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('web.login', next=request.url))
        if not _has_module_access(session.get('user_id')):
            session.clear()
            flash('You do not have access to the Machine Shop module.', 'error')
            return redirect(url_for('web.login'))
        role_id = (session.get('user') or {}).get('role_id')
        if not _has_role_access(role_id, allow_master_data=False):
            flash('Your role does not have access to the Machine Shop module.', 'error')
            return redirect(url_for('web.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('web.login', next=request.url))
        if not _has_module_access(session.get('user_id')):
            session.clear()
            flash('You do not have access to the Machine Shop module.', 'error')
            return redirect(url_for('web.login'))
        role_id = (session.get('user') or {}).get('role_id')
        if not _has_role_access(role_id, allow_master_data=True):
            flash('Master data access is allowed only for Admin, CEO, HOD, AVP, and GM roles.', 'error')
            return redirect(url_for('web.index'))
            
        return f(*args, **kwargs)
    return decorated_function


def _has_quality_access(user_id, permission_type):
    """
    Check if user has specific quality permission.
    permission_type: 'rejection_form' or 'rejection_records'
    """
    if not user_id:
        return False
    
    # Import here to avoid circular imports if any
    from models import MachineShopQualityAccess
    
    access = MachineShopQualityAccess.query.filter_by(user_id=user_id).first()
    if not access:
        return False
        
    if permission_type == 'rejection_form':
        return bool(access.can_rejection_form)
    elif permission_type == 'rejection_records':
        return bool(access.can_rejection_records)
        
    return False


def rejection_form_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('web.login', next=request.url))
        # Admins always have access
        if session.get('user', {}).get('role_id') == 1:
            return f(*args, **kwargs)
        if not _has_quality_access(session.get('user_id'), 'rejection_form'):
            flash('You do not have permission to access the Rejection Form.', 'error')
            return redirect(url_for('web.index'))
        return f(*args, **kwargs)
    return decorated_function


def rejection_records_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('web.login', next=request.url))
        # Admins always have access
        if session.get('user', {}).get('role_id') == 1:
            return f(*args, **kwargs)
        if not _has_quality_access(session.get('user_id'), 'rejection_records'):
            flash('You do not have permission to access Rejection Records.', 'error')
            return redirect(url_for('web.index'))
        return f(*args, **kwargs)
    return decorated_function
