from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, MachineShopQualityAccess, EmpMaster
from utils.auth import admin_required
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)
access_control_bp = Blueprint('access_control', __name__)

@access_control_bp.route('/manage-access')
@admin_required
def manage_access():
    """List all users with Machine Shop access and their quality permissions"""
    try:
        # Fetch all users who have access to MACHINE_SHOP module in the global MOA system
        users_query = text("""
            SELECT u.user_id, e.emp_name, e.emp_code, u.email_login,
                   qa.can_rejection_form, qa.can_rejection_records
            FROM user_login u
            JOIN user_module_access uma ON u.user_id = uma.user_id
            JOIN modules m ON m.module_id = uma.module_id
            LEFT JOIN emp_master e ON u.emp_id = e.emp_id
            LEFT JOIN ms_quality_access qa ON u.user_id = qa.user_id
            WHERE m.module_code = 'MACHINE_SHOP'
              AND COALESCE(m.is_active, TRUE) = TRUE
              AND COALESCE(uma.is_active, TRUE) = TRUE
              AND COALESCE(uma.can_view, FALSE) = TRUE
              AND COALESCE(u.is_active, TRUE) = TRUE
            ORDER BY e.emp_name
        """)
        users = db.session.execute(users_query).fetchall()
        return render_template('manage_access.html', users=users)
    except Exception as e:
        logger.error(f"Error fetching users for access management: {str(e)}")
        flash("An error occurred while loading user list.", "danger")
        return redirect(url_for('web.index'))

@access_control_bp.route('/manage-access/update', methods=['POST'])
@admin_required
def update_access():
    """Update quality permissions for a specific user"""
    try:
        user_id = request.form.get('user_id', type=int)
        if not user_id:
            flash("Invalid User ID.", "danger")
            return redirect(url_for('access_control.manage_access'))

        can_form = request.form.get('can_rejection_form') == 'yes'
        can_records = request.form.get('can_rejection_records') == 'yes'
        
        access = MachineShopQualityAccess.query.filter_by(user_id=user_id).first()
        if not access:
            access = MachineShopQualityAccess(user_id=user_id)
            db.session.add(access)
        
        access.can_rejection_form = can_form
        access.can_rejection_records = can_records
        db.session.commit()
        
        flash(f'Access permissions updated successfully for User ID {user_id}.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user access: {str(e)}")
        flash("Failed to update permissions.", "danger")
        
    return redirect(url_for('access_control.manage_access'))
