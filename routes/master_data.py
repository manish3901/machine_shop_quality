"""
Master Data Management Routes
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from models import db, Machine, MachineShed, MachineType, Customer, OperationType, IssueType, EmpMaster, AuditLog, SectionMaster, SectionCutLength, IdealCycleTime, DowntimeReason, DefectType, MachineTarget
from datetime import datetime, timezone
from sqlalchemy import func
from utils.auth import login_required, admin_required
import logging
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)
master_data_bp = Blueprint('master_data', __name__)


def _machine_shed_assignment_conflicts(selected_machine_ids, current_shed_id=None):
    """Return machines already assigned to another shed."""
    if not selected_machine_ids:
        return []

    query = Machine.query.filter(Machine.id.in_(selected_machine_ids), Machine.shed_id.isnot(None))
    if current_shed_id is not None:
        query = query.filter(Machine.shed_id != current_shed_id)
    return query.order_by(Machine.machine_name).all()


def _machine_type_options():
    master_types = [
        machine_type.type_name for machine_type in MachineType.query.filter_by(status='Active').order_by(MachineType.type_name).all()
    ]
    existing_types = [
        row[0] for row in db.session.query(Machine.machine_type).filter(
            Machine.machine_type.isnot(None),
            Machine.machine_type != ''
        ).distinct().order_by(Machine.machine_type).all()
    ]
    return sorted(set(master_types + existing_types))


@master_data_bp.route('/machine-types')
@admin_required
def list_machine_types():
    """List all machine types."""
    page = request.args.get('page', 1, type=int)
    pagination = MachineType.query.order_by(MachineType.type_name).paginate(page=page, per_page=15, error_out=False)
    return render_template('master/machine_types_list.html', pagination=pagination)


@master_data_bp.route('/machine-types/add', methods=['GET', 'POST'])
@admin_required
def add_machine_type():
    """Add new machine type."""
    if request.method == 'GET':
        return render_template('master/machine_type_form.html', machine_type=None)

    try:
        machine_type = MachineType(
            type_name=(request.form.get('type_name') or '').strip(),
            description=request.form.get('description'),
            status=request.form.get('status', 'Active')
        )
        db.session.add(machine_type)
        db.session.commit()
        flash('Machine type added successfully!', 'success')
        return redirect(url_for('master_data.list_machine_types'))
    except Exception as e:
        logger.error(f'Error adding machine type: {str(e)}')
        db.session.rollback()
        return render_template('master/machine_type_form.html', machine_type=None, error=str(e)), 500


@master_data_bp.route('/machine-types/<int:type_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_machine_type(type_id):
    """Edit machine type."""
    machine_type = MachineType.query.get_or_404(type_id)

    if request.method == 'GET':
        return render_template('master/machine_type_form.html', machine_type=machine_type)

    try:
        old_type_name = machine_type.type_name
        machine_type.type_name = (request.form.get('type_name') or '').strip()
        machine_type.description = request.form.get('description')
        machine_type.status = request.form.get('status', 'Active')
        machine_type.updated_at = datetime.now(timezone.utc)

        if old_type_name != machine_type.type_name:
            Machine.query.filter_by(machine_type=old_type_name).update(
                {'machine_type': machine_type.type_name},
                synchronize_session=False
            )

        db.session.commit()
        flash('Machine type updated successfully!', 'success')
        return redirect(url_for('master_data.list_machine_types'))
    except Exception as e:
        logger.error(f'Error editing machine type: {str(e)}')
        db.session.rollback()
        return render_template('master/machine_type_form.html', machine_type=machine_type, error=str(e)), 500


@master_data_bp.route('/machine-types/<int:type_id>/delete', methods=['POST'])
@admin_required
def delete_machine_type(type_id):
    """Delete machine type."""
    try:
        machine_type = MachineType.query.get_or_404(type_id)
        in_use = Machine.query.filter_by(machine_type=machine_type.type_name).first()
        if in_use:
            flash(f'Cannot delete machine type {machine_type.type_name}. It is already used by machine {in_use.machine_name}.', 'danger')
            return redirect(url_for('master_data.list_machine_types'))

        db.session.delete(machine_type)
        db.session.commit()
        flash('Machine type deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting machine type: {str(e)}', 'danger')
    return redirect(url_for('master_data.list_machine_types'))


@master_data_bp.route('/customers/<int:customer_id>/delete', methods=['POST'])
@admin_required
def delete_customer(customer_id):
    """Delete customer"""
    try:
        customer = Customer.query.get_or_404(customer_id)
        db.session.delete(customer)
        db.session.commit()
        flash('Customer deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting customer: Maybe they have sections or entries. Error: {str(e)}', 'danger')
    return redirect(url_for('master_data.list_customers'))


# ==================== SECTIONS ====================

# ==================== MACHINES ====================

@master_data_bp.route('/machine-sheds')
@admin_required
def list_machine_sheds():
    """List all machine sheds"""
    page = request.args.get('page', 1, type=int)
    pagination = MachineShed.query.order_by(MachineShed.shed_name).paginate(page=page, per_page=15, error_out=False)
    return render_template('master/machine_sheds_list.html', pagination=pagination)


@master_data_bp.route('/machine-sheds/<int:shed_id>')
@admin_required
def view_machine_shed(shed_id):
    """View a machine shed and all linked machines."""
    shed = MachineShed.query.get_or_404(shed_id)
    machines = Machine.query.filter_by(shed_id=shed.id).order_by(Machine.machine_name).all()
    return render_template('master/machine_shed_view.html', shed=shed, machines=machines)


@master_data_bp.route('/machine-sheds/add', methods=['GET', 'POST'])
@admin_required
def add_machine_shed():
    """Add new machine shed"""
    if request.method == 'GET':
        machines = Machine.query.order_by(Machine.machine_name).all()
        return render_template('master/machine_shed_form.html', shed=None, machines=machines, selected_machine_ids=[])

    try:
        selected_machine_ids = [int(machine_id) for machine_id in request.form.getlist('machine_ids') if machine_id]
        conflicting_machines = _machine_shed_assignment_conflicts(selected_machine_ids)
        if conflicting_machines:
            conflict_text = ', '.join(
                f"{machine.machine_name} ({machine.shed.shed_name})" for machine in conflicting_machines if machine.shed
            )
            flash(f'These machines are already linked to another shed. Remove them there first: {conflict_text}', 'danger')
            machines = Machine.query.order_by(Machine.machine_name).all()
            return render_template(
                'master/machine_shed_form.html',
                shed=None,
                machines=machines,
                selected_machine_ids=[str(machine_id) for machine_id in selected_machine_ids],
                conflict_message=f'These machines are already linked to another shed. Remove them there first: {conflict_text}'
            ), 400

        shed = MachineShed(
            shed_name=(request.form.get('shed_name') or '').strip(),
            description=request.form.get('description'),
            status=request.form.get('status', 'Active')
        )
        db.session.add(shed)
        db.session.flush()

        if selected_machine_ids:
            Machine.query.filter(Machine.id.in_(selected_machine_ids)).update(
                {'shed_id': shed.id},
                synchronize_session=False
            )

        db.session.commit()
        flash('Machine shed added successfully!', 'success')
        return redirect(url_for('master_data.list_machine_sheds'))
    except Exception as e:
        logger.error(f'Error adding machine shed: {str(e)}')
        db.session.rollback()
        machines = Machine.query.order_by(Machine.machine_name).all()
        return render_template(
            'master/machine_shed_form.html',
            shed=None,
            machines=machines,
            selected_machine_ids=request.form.getlist('machine_ids')
        ), 500


@master_data_bp.route('/machine-sheds/<int:shed_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_machine_shed(shed_id):
    """Edit machine shed"""
    shed = MachineShed.query.get_or_404(shed_id)

    if request.method == 'GET':
        machines = Machine.query.order_by(Machine.machine_name).all()
        selected_machine_ids = [str(machine.id) for machine in shed.machines]
        return render_template(
            'master/machine_shed_form.html',
            shed=shed,
            machines=machines,
            selected_machine_ids=selected_machine_ids
        )

    try:
        shed.shed_name = (request.form.get('shed_name') or '').strip()
        shed.description = request.form.get('description')
        shed.status = request.form.get('status', 'Active')
        shed.updated_at = datetime.now(timezone.utc)

        selected_machine_ids = {
            int(machine_id) for machine_id in request.form.getlist('machine_ids') if machine_id
        }
        conflicting_machines = _machine_shed_assignment_conflicts(selected_machine_ids, current_shed_id=shed.id)
        if conflicting_machines:
            conflict_text = ', '.join(
                f"{machine.machine_name} ({machine.shed.shed_name})" for machine in conflicting_machines if machine.shed
            )
            flash(f'These machines are already linked to another shed. Remove them there first: {conflict_text}', 'danger')
            machines = Machine.query.order_by(Machine.machine_name).all()
            return render_template(
                'master/machine_shed_form.html',
                shed=shed,
                machines=machines,
                selected_machine_ids=[str(machine_id) for machine_id in selected_machine_ids],
                conflict_message=f'These machines are already linked to another shed. Remove them there first: {conflict_text}'
            ), 400


        current_machine_query = Machine.query.filter_by(shed_id=shed.id)
        if selected_machine_ids:
            current_machine_query = current_machine_query.filter(~Machine.id.in_(selected_machine_ids))
        current_machine_query.update({'shed_id': None}, synchronize_session=False)

        if selected_machine_ids:
            Machine.query.filter(Machine.id.in_(selected_machine_ids)).update(
                {'shed_id': shed.id},
                synchronize_session=False
            )

        db.session.commit()
        flash('Machine shed updated successfully!', 'success')
        return redirect(url_for('master_data.list_machine_sheds'))
    except Exception as e:
        logger.error(f'Error editing machine shed: {str(e)}')
        db.session.rollback()
        machines = Machine.query.order_by(Machine.machine_name).all()
        return render_template(
            'master/machine_shed_form.html',
            shed=shed,
            machines=machines,
            selected_machine_ids=request.form.getlist('machine_ids')
        ), 500


@master_data_bp.route('/machine-sheds/<int:shed_id>/delete', methods=['POST'])
@admin_required
def delete_machine_shed(shed_id):
    """Delete machine shed"""
    try:
        shed = MachineShed.query.get_or_404(shed_id)
        db.session.delete(shed)
        db.session.commit()
        flash('Machine shed deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting machine shed: Maybe machines are mapped to it. Error: {str(e)}', 'danger')
    return redirect(url_for('master_data.list_machine_sheds'))


@master_data_bp.route('/machines')
@admin_required
def list_machines():
    """List all machines"""
    page = request.args.get('page', 1, type=int)
    shed_id = request.args.get('shed_id', type=int)
    machine_type = (request.args.get('machine_type') or '').strip()

    query = Machine.query
    if shed_id:
        query = query.filter(Machine.shed_id == shed_id)
    if machine_type:
        query = query.filter(Machine.machine_type == machine_type)

    pagination = query.order_by(Machine.machine_name).paginate(page=page, per_page=15, error_out=False)
    sheds = MachineShed.query.order_by(MachineShed.shed_name).all()
    machine_types = _machine_type_options()
    return render_template(
        'master/machines_list.html',
        pagination=pagination,
        sheds=sheds,
        machine_types=machine_types,
        selected_shed_id=shed_id,
        selected_machine_type=machine_type
    )


@master_data_bp.route('/machines/add', methods=['GET', 'POST'])
@admin_required
def add_machine():
    """Add new machine"""
    if request.method == 'GET':
        sheds = MachineShed.query.filter_by(status='Active').order_by(MachineShed.shed_name).all()
        return render_template('master/machine_form.html', machine=None, sheds=sheds, machine_types=_machine_type_options())
    
    elif request.method == 'POST':
        try:
            machine = Machine(
                machine_name=request.form['machine_name'],
                machine_type=request.form['machine_type'],
                status=request.form.get('status', 'Active'),
                shed_id=request.form.get('shed_id', type=int),
                monthly_capacity=request.form.get('monthly_capacity', 0)
            )
            
            db.session.add(machine)
            db.session.commit()
            
            return redirect(url_for('master_data.list_machines'))
            
        except Exception as e:
            logger.error(f'Error adding machine: {str(e)}')
            db.session.rollback()
            sheds = MachineShed.query.filter_by(status='Active').order_by(MachineShed.shed_name).all()
            return render_template('master/machine_form.html', machine=None, sheds=sheds, machine_types=_machine_type_options(), error=str(e)), 500


@master_data_bp.route('/machines/<int:machine_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_machine(machine_id):
    """Edit machine"""
    machine = Machine.query.get_or_404(machine_id)
    
    if request.method == 'GET':
        sheds = MachineShed.query.filter_by(status='Active').order_by(MachineShed.shed_name).all()
        return render_template('master/machine_form.html', machine=machine, sheds=sheds, machine_types=_machine_type_options())
    
    elif request.method == 'POST':
        try:
            machine.machine_name = request.form['machine_name']
            machine.machine_type = request.form['machine_type']
            machine.status = request.form.get('status', 'Active')
            machine.shed_id = request.form.get('shed_id', type=int)
            machine.monthly_capacity = request.form.get('monthly_capacity', 0)
            machine.updated_at = datetime.now(timezone.utc)
            
            db.session.commit()
            return redirect(url_for('master_data.list_machines'))
            
        except Exception as e:
            logger.error(f'Error editing machine: {str(e)}')
            db.session.rollback()
            sheds = MachineShed.query.filter_by(status='Active').order_by(MachineShed.shed_name).all()
            return render_template('master/machine_form.html', machine=machine, sheds=sheds, machine_types=_machine_type_options(), error=str(e)), 500


@master_data_bp.route('/machines/<int:machine_id>/delete', methods=['POST'])
@admin_required
def delete_machine(machine_id):
    """Delete machine"""
    try:
        machine = Machine.query.get_or_404(machine_id)
        db.session.delete(machine)
        db.session.commit()
        flash('Machine deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting machine: Maybe it is in use. Error: {str(e)}', 'danger')
    return redirect(url_for('master_data.list_machines'))


# ==================== CUSTOMERS ====================

@master_data_bp.route('/customers')
@admin_required
def list_customers():
    """List all customers"""
    page = request.args.get('page', 1, type=int)
    customer_id = request.args.get('customer_id', type=int)

    query = Customer.query
    if customer_id:
        query = query.filter(Customer.id == customer_id)

    pagination = query.order_by(Customer.customer_name).paginate(page=page, per_page=15, error_out=False)
    selected_customer = Customer.query.get(customer_id) if customer_id else None
    return render_template(
        'master/customers_list.html',
        pagination=pagination,
        selected_customer=selected_customer,
        selected_customer_id=customer_id
    )


@master_data_bp.route('/customers/add', methods=['GET', 'POST'])
@admin_required
def add_customer():
    """Add new customer"""
    if request.method == 'GET':
        return render_template('master/customer_form.html', customer=None)
    
    elif request.method == 'POST':
        try:
            customer = Customer(
                customer_name=request.form['customer_name'],
                customer_code=request.form.get('customer_code'),
                status=request.form.get('status', 'Active')
            )
            
            db.session.add(customer)
            db.session.flush() # Get customer ID
            
            # Create initial section and cut length
            sec_num = request.form.get('initial_section')
            init_length = request.form.get('initial_length')
            
            if sec_num and init_length:
                section = SectionMaster(
                    customer_id=customer.id,
                    section_number=sec_num
                )
                db.session.add(section)
                db.session.flush()
                
                cl = SectionCutLength(
                    section_id=section.id,
                    cut_length=float(init_length)
                )
                db.session.add(cl)
            
            db.session.commit()
            
            flash(f'Customer {customer.customer_name} added with initial section {sec_num} successfully!', 'success')
            return redirect(url_for('master_data.list_customers'))
            
        except Exception as e:
            logger.error(f'Error adding customer: {str(e)}')
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


@master_data_bp.route('/customers/<int:customer_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_customer(customer_id):
    """Edit customer"""
    customer = Customer.query.get_or_404(customer_id)
    
    if request.method == 'GET':
        return render_template('master/customer_form.html', customer=customer)
    
    elif request.method == 'POST':
        try:
            customer.customer_name = request.form['customer_name']
            customer.customer_code = request.form.get('customer_code')
            customer.status = request.form.get('status', 'Active')
            customer.updated_at = datetime.now(timezone.utc)
            
            db.session.commit()
            return redirect(url_for('master_data.list_customers'))
            
        except Exception as e:
            logger.error(f'Error editing customer: {str(e)}')
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


# ==================== SECTIONS & CYCLE TIMES ====================

@master_data_bp.route('/customers/<int:customer_id>/sections')
@admin_required
def manage_sections(customer_id):
    """Manage sections for a customer"""
    customer = Customer.query.get_or_404(customer_id)
    page = request.args.get('page', 1, type=int)
    q = (request.args.get('q') or '').strip()

    query = SectionMaster.query.filter_by(customer_id=customer_id)
    if q:
        # Partial match search (case-insensitive) to quickly find a section in large lists.
        query = query.filter(SectionMaster.section_number.ilike(f'%{q}%'))

    pagination = query.order_by(SectionMaster.section_number).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template(
        'master/sections_manage.html',
        customer=customer,
        sections=pagination.items,
        pagination=pagination,
        q=q
    )


@master_data_bp.route('/customers/<int:customer_id>/sections/add', methods=['POST'])
@admin_required
def add_section(customer_id):
    """Add new section to customer"""
    try:
        section_number = request.form.get('section_number')
        if not section_number:
            flash('Section number is required', 'error')
            return redirect(url_for('master_data.manage_sections', customer_id=customer_id))
            
        section = SectionMaster(customer_id=customer_id, section_number=section_number)
        db.session.add(section)
        db.session.commit()
        flash(f'Section {section_number} added successfully', 'success')
        
    except Exception as e:
        logger.error(f'Error adding section: {str(e)}')
        db.session.rollback()
        flash('Error adding section', 'error')
        
    return redirect(url_for('master_data.manage_sections', customer_id=customer_id))


@master_data_bp.route('/customers/<int:customer_id>/sections/bulk-add', methods=['POST'])
@admin_required
def bulk_add_sections(customer_id):
    """Add multiple sections to a customer at once (one per line)."""
    raw_text = (request.form.get('section_numbers') or '').strip()
    if not raw_text:
        flash('Please enter at least one section number.', 'error')
        return redirect(url_for('master_data.manage_sections', customer_id=customer_id))

    # Normalize: allow newline or comma separated.
    candidates = []
    for line in raw_text.replace(',', '\n').splitlines():
        value = (line or '').strip()
        if value:
            candidates.append(value)

    if not candidates:
        flash('Please enter at least one valid section number.', 'error')
        return redirect(url_for('master_data.manage_sections', customer_id=customer_id))

    # Deduplicate while preserving order.
    seen = set()
    section_numbers = []
    for s in candidates:
        key = s.strip()
        if key.lower() in seen:
            continue
        seen.add(key.lower())
        section_numbers.append(key)

    existing = {
        (row[0] or '').strip().lower()
        for row in db.session.query(SectionMaster.section_number)
        .filter(SectionMaster.customer_id == customer_id)
        .all()
    }

    to_add = [s for s in section_numbers if s.lower() not in existing]
    skipped = [s for s in section_numbers if s.lower() in existing]

    if not to_add:
        flash('All provided section numbers already exist for this customer.', 'warning')
        return redirect(url_for('master_data.manage_sections', customer_id=customer_id))

    try:
        for section_number in to_add:
            db.session.add(SectionMaster(customer_id=customer_id, section_number=section_number))
        db.session.commit()
    except IntegrityError:
        # If there is a race or a uniqueness conflict we didn't pre-detect, rollback cleanly.
        db.session.rollback()
        flash('Some section numbers already exist (unique constraint). Please retry.', 'error')
        return redirect(url_for('master_data.manage_sections', customer_id=customer_id))
    except Exception as e:
        logger.error(f'Error bulk adding sections: {str(e)}')
        db.session.rollback()
        flash('Error adding sections', 'error')
        return redirect(url_for('master_data.manage_sections', customer_id=customer_id))

    msg = f'Added {len(to_add)} section(s) successfully.'
    if skipped:
        msg += f' Skipped {len(skipped)} existing.'
    flash(msg, 'success')
    return redirect(url_for('master_data.manage_sections', customer_id=customer_id))


@master_data_bp.route('/sections/<int:section_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_section(section_id):
    """Edit section number"""
    section = SectionMaster.query.get_or_404(section_id)
    if request.method == 'GET':
        return render_template('master/section_form.html', section=section, customer=section.customer)
    
    elif request.method == 'POST':
        try:
            section.section_number = request.form['section_number']
            db.session.commit()
            flash('Section updated successfully!', 'success')
            return redirect(url_for('master_data.manage_sections', customer_id=section.customer_id))
        except Exception as e:
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


@master_data_bp.route('/sections/<int:section_id>/delete', methods=['POST'])
@admin_required
def delete_section(section_id):
    """Delete section"""
    section = SectionMaster.query.get_or_404(section_id)
    customer_id = section.customer_id
    try:
        db.session.delete(section)
        db.session.commit()
        flash('Section deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting section: Maybe it has cut lengths. Error: {str(e)}', 'danger')
    return redirect(url_for('master_data.manage_sections', customer_id=customer_id))


@master_data_bp.route('/sections/<int:section_id>/cut-lengths')
@admin_required
def manage_cut_lengths(section_id):
    """Manage cut lengths for a section"""
    section = SectionMaster.query.get_or_404(section_id)
    customer = section.customer
    cut_lengths = SectionCutLength.query.filter_by(section_id=section_id).order_by(SectionCutLength.cut_length).all()
    return render_template('master/cut_lengths_manage.html', section=section, customer=customer, cut_lengths=cut_lengths)


@master_data_bp.route('/sections/<int:section_id>/cut-lengths/add', methods=['POST'])
@admin_required
def add_cut_length(section_id):
    """Add new cut length to section"""
    try:
        cut_length = request.form.get('cut_length', type=float)
        if cut_length is None:
            flash('Cut length is required', 'error')
            return redirect(url_for('master_data.manage_cut_lengths', section_id=section_id))
            
        cl = SectionCutLength(section_id=section_id, cut_length=cut_length)
        db.session.add(cl)
        db.session.commit()
        flash(f'Cut length {cut_length} added successfully', 'success')
        
    except Exception as e:
        logger.error(f'Error adding cut length: {str(e)}')
        db.session.rollback()
        flash('Error adding cut length', 'error')
        
    return redirect(url_for('master_data.manage_cut_lengths', section_id=section_id))


@master_data_bp.route('/sections/<int:section_id>/cut-lengths/bulk-add', methods=['POST'])
@admin_required
def bulk_add_cut_lengths(section_id):
    """Add multiple cut lengths to a section at once (one per line)."""
    raw_text = (request.form.get('cut_lengths') or '').strip()
    if not raw_text:
        flash('Please enter at least one cut length.', 'error')
        return redirect(url_for('master_data.manage_cut_lengths', section_id=section_id))

    # Normalize: allow newline or comma separated.
    candidates = []
    for line in raw_text.replace(',', '\n').splitlines():
        value = (line or '').strip()
        if value:
            candidates.append(value)

    lengths = []
    bad = []
    for val in candidates:
        try:
            lengths.append(float(val))
        except Exception:
            bad.append(val)

    if not lengths:
        flash('No valid cut lengths found. Enter numbers like 796.5', 'error')
        return redirect(url_for('master_data.manage_cut_lengths', section_id=section_id))

    # Deduplicate (numeric) while preserving order.
    seen = set()
    unique_lengths = []
    for x in lengths:
        key = round(float(x), 6)
        if key in seen:
            continue
        seen.add(key)
        unique_lengths.append(float(x))

    existing = {
        round(float(row[0] or 0), 6)
        for row in db.session.query(SectionCutLength.cut_length)
        .filter(SectionCutLength.section_id == section_id)
        .all()
    }

    to_add = [x for x in unique_lengths if round(float(x), 6) not in existing]
    skipped = [x for x in unique_lengths if round(float(x), 6) in existing]

    if not to_add:
        flash('All provided cut lengths already exist for this section.', 'warning')
        return redirect(url_for('master_data.manage_cut_lengths', section_id=section_id))

    try:
        for cut_length in to_add:
            db.session.add(SectionCutLength(section_id=section_id, cut_length=cut_length))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('Some cut lengths already exist (unique constraint). Please retry.', 'error')
        return redirect(url_for('master_data.manage_cut_lengths', section_id=section_id))
    except Exception as e:
        logger.error(f'Error bulk adding cut lengths: {str(e)}')
        db.session.rollback()
        flash('Error adding cut lengths', 'error')
        return redirect(url_for('master_data.manage_cut_lengths', section_id=section_id))

    msg = f'Added {len(to_add)} cut length(s) successfully.'
    if skipped:
        msg += f' Skipped {len(skipped)} existing.'
    if bad:
        msg += f' Ignored {len(bad)} invalid value(s).'
    flash(msg, 'success')
    return redirect(url_for('master_data.manage_cut_lengths', section_id=section_id))


@master_data_bp.route('/cut-lengths/<int:cl_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_cut_length(cl_id):
    """Edit cut length"""
    cl = SectionCutLength.query.get_or_404(cl_id)
    section = cl.section
    if request.method == 'GET':
        return render_template('master/cut_length_form.html', cl=cl, section=section)
    
    elif request.method == 'POST':
        try:
            cl.cut_length = request.form.get('cut_length', type=float)
            cl.status = request.form.get('status', 'Active')
            db.session.commit()
            flash('Cut length updated successfully!', 'success')
            return redirect(url_for('master_data.manage_cut_lengths', section_id=cl.section_id))
        except Exception as e:
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


@master_data_bp.route('/cut-lengths/<int:cl_id>/delete', methods=['POST'])
@admin_required
def delete_cut_length(cl_id):
    """Delete cut length"""
    cl = SectionCutLength.query.get_or_404(cl_id)
    section_id = cl.section_id
    try:
        db.session.delete(cl)
        db.session.commit()
        flash('Cut length deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting cut length: {str(e)}', 'danger')
    return redirect(url_for('master_data.manage_cut_lengths', section_id=section_id))


@master_data_bp.route('/cut-lengths/<int:cl_id>/cycle-times')
@admin_required
def manage_ideal_cycle_times(cl_id):
    """Manage ideal cycle times for a cut length"""
    cl = SectionCutLength.query.get_or_404(cl_id)
    section = cl.section
    customer = section.customer
    # Order by Machine ID then Sequence to group them logically
    cycle_times = IdealCycleTime.query.filter_by(section_cut_length_id=cl_id)\
        .join(Machine)\
        .order_by(Machine.machine_name, IdealCycleTime.sequence).all()
    machines = Machine.query.filter_by(status='Active').all()
    operations = OperationType.query.order_by(OperationType.operation_name).all()
    
    return render_template('master/cycle_times_manage.html', 
                         cl=cl, section=section, customer=customer, 
                         cycle_times=cycle_times, machines=machines,
                         operations=operations)


@master_data_bp.route('/cut-lengths/<int:cl_id>/cycle-times/add', methods=['POST'])
@admin_required
def add_ideal_cycle_time(cl_id):
    """Add new ideal cycle time process step for one or more machines"""
    try:
        machine_ids = request.form.getlist('machine_id[]', type=int)
        process_name = request.form.get('process_name')
        minutes = request.form.get('cycle_time_minutes', type=float)
        base_seq = request.form.get('sequence', type=int)

        if not machine_ids or not process_name or minutes is None:
            flash('All fields are required', 'error')
            return redirect(url_for('master_data.manage_ideal_cycle_times', cl_id=cl_id))

        seconds = float(minutes) * 60.0

        for machine_id in machine_ids:
            seq = base_seq
            if not seq:
                max_seq = db.session.query(db.func.max(IdealCycleTime.sequence))\
                    .filter_by(section_cut_length_id=cl_id, machine_id=machine_id).scalar()
                seq = (max_seq or 0) + 1

            ict = IdealCycleTime(
                section_cut_length_id=cl_id,
                machine_id=machine_id,
                process_name=process_name,
                cycle_time_seconds=seconds,
                sequence=seq
            )
            db.session.add(ict)

        db.session.commit()
        count = len(machine_ids)
        flash(f'Process step "{process_name}" added for {count} machine(s) successfully', 'success')

    except Exception as e:
        logger.error(f'Error adding ideal cycle time: {str(e)}')
        db.session.rollback()
        flash('Error adding ideal cycle time', 'error')

    return redirect(url_for('master_data.manage_ideal_cycle_times', cl_id=cl_id))


@master_data_bp.route('/cycle-times/<int:ct_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_ideal_cycle_time(ct_id):
    """Edit ideal cycle time"""
    ct = IdealCycleTime.query.get_or_404(ct_id)
    cl = ct.cut_length_obj
    section = cl.section
    
    if request.method == 'GET':
        machines = Machine.query.filter_by(status='Active').all()
        operations = OperationType.query.order_by(OperationType.operation_name).all()
        return render_template('master/cycle_time_form.html', 
                             ct=ct, cl=cl, section=section, 
                             machines=machines, operations=operations)
    
    elif request.method == 'POST':
        try:
            ct.sequence = request.form.get('sequence', type=int)
            ct.machine_id = request.form.get('machine_id', type=int)
            ct.process_name = request.form.get('process_name')
            minutes = request.form.get('cycle_time_minutes', type=float)
            ct.cycle_time_seconds = (float(minutes) * 60.0) if minutes is not None else None
             
            db.session.commit()
            flash('Process step updated successfully!', 'success')
            return redirect(url_for('master_data.manage_ideal_cycle_times', cl_id=ct.section_cut_length_id))
        except Exception as e:
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


@master_data_bp.route('/cycle-times/<int:ct_id>/delete', methods=['POST'])
@admin_required
def delete_ideal_cycle_time(ct_id):
    """Delete ideal cycle time"""
    ct = IdealCycleTime.query.get_or_404(ct_id)
    cl_id = ct.section_cut_length_id
    try:
        db.session.delete(ct)
        db.session.commit()
        flash('Process step deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting process step: {str(e)}', 'danger')
    return redirect(url_for('master_data.manage_ideal_cycle_times', cl_id=cl_id))


@master_data_bp.route('/api/sections/<int:customer_id>', methods=['GET'])
def api_get_sections(customer_id):
    """API to get sections for a customer"""
    sections = SectionMaster.query.filter_by(customer_id=customer_id).all()
    return jsonify([{'id': s.id, 'number': s.section_number} for s in sections])


@master_data_bp.route('/api/cut-lengths/<int:section_id>', methods=['GET'])
def api_get_cut_lengths(section_id):
    """API to get cut lengths for a section"""
    cls = SectionCutLength.query.filter_by(section_id=section_id).all()
    return jsonify([{'id': c.id, 'length': c.cut_length} for c in cls])


@master_data_bp.route('/api/cycle-times', methods=['GET'])
def api_get_process_cycle_times():
    """API to get cycle times for a cut length and machine"""
    cl_id = request.args.get('cl_id', type=int)
    machine_id = request.args.get('machine_id', type=int)
    
    if not all([cl_id, machine_id]):
        return jsonify({'error': 'Missing parameters'}), 400
        
    cts = IdealCycleTime.query.filter_by(section_cut_length_id=cl_id, machine_id=machine_id).order_by(IdealCycleTime.sequence).all()
    total_time = sum(ct.cycle_time_seconds for ct in cts)
    
    # Pre-fetch matching operation types for IDs
    process_list = []
    for ct in cts:
        op = OperationType.query.filter_by(operation_name=ct.process_name).first()
        process_list.append({
            'id': ct.id,
            'name': ct.process_name,
            'seconds': ct.cycle_time_seconds,
            'operation_type_id': op.id if op else None
        })
    
    return jsonify({
        'processes': process_list,
        'total_seconds': total_time
    })


# ==================== OPERATION TYPES ====================

@master_data_bp.route('/operations')
@admin_required
def list_operations():
    """List all operation types"""
    page = request.args.get('page', 1, type=int)
    pagination = OperationType.query.order_by(OperationType.operation_name).paginate(page=page, per_page=15, error_out=False)
    return render_template('master/operations_list.html', pagination=pagination)


@master_data_bp.route('/operations/add', methods=['GET', 'POST'])
@admin_required
def add_operation():
    """Add new operation type"""
    if request.method == 'GET':
        return render_template('master/operation_form.html', operation=None)
    
    elif request.method == 'POST':
        try:
            operation_name = ' '.join((request.form.get('operation_name') or '').split())
            if not operation_name:
                flash('Operation name is required', 'error')
                return redirect(url_for('master_data.add_operation'))

            # Friendly duplicate handling (DB has a UNIQUE constraint on operation_name).
            existing_names = [
                (row[0] or '')
                for row in db.session.query(OperationType.operation_name).all()
            ]
            normalized_existing = {' '.join(str(name).split()).lower() for name in existing_names}
            if operation_name.lower() in normalized_existing:
                flash(f'Operation "{operation_name}" already exists.', 'warning')
                return redirect(url_for('master_data.add_operation'))

            operation = OperationType(
                operation_name=operation_name,
                description=request.form.get('description'),
                standard_cycle_time_seconds=request.form.get('standard_cycle_time_seconds', type=int)
            )
            
            db.session.add(operation)
            db.session.commit()
             
            return redirect(url_for('master_data.list_operations'))

        except IntegrityError:
            db.session.rollback()
            flash(f'Operation "{(request.form.get("operation_name") or "").strip()}" already exists.', 'warning')
            return redirect(url_for('master_data.add_operation'))
        except Exception as e:
            logger.error(f'Error adding operation: {str(e)}')
            db.session.rollback()
            flash(f'Error adding operation: {str(e)}', 'danger')
            return redirect(url_for('master_data.add_operation'))


@master_data_bp.route('/operations/<int:operation_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_operation(operation_id):
    """Edit operation type"""
    operation = OperationType.query.get_or_404(operation_id)
    
    if request.method == 'GET':
        return render_template('master/operation_form.html', operation=operation)
    
    elif request.method == 'POST':
        try:
            operation.operation_name = request.form['operation_name']
            operation.description = request.form.get('description')
            operation.standard_cycle_time_seconds = request.form.get('standard_cycle_time_seconds', type=int)
            
            db.session.commit()
            return redirect(url_for('master_data.list_operations'))
            
        except Exception as e:
            logger.error(f'Error editing operation: {str(e)}')
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


@master_data_bp.route('/operations/<int:operation_id>/delete', methods=['POST'])
@admin_required
def delete_operation(operation_id):
    """Delete operation type"""
    try:
        operation = OperationType.query.get_or_404(operation_id)
        db.session.delete(operation)
        db.session.commit()
        flash('Operation deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting operation: It may be used in production entries. Error: {str(e)}', 'danger')
    return redirect(url_for('master_data.list_operations'))


@master_data_bp.route('/operations/bulk-add', methods=['POST'])
@admin_required
def bulk_add_operations():
    """Bulk add operation types (one per line, commas supported)."""
    raw_text = (request.form.get('operation_names') or '').strip()
    if not raw_text:
        flash('Please enter at least one operation name.', 'error')
        return redirect(url_for('master_data.list_operations'))

    candidates = []
    for line in raw_text.replace(',', '\n').splitlines():
        value = (line or '').strip()
        if value:
            candidates.append(value)

    if not candidates:
        flash('Please enter at least one valid operation name.', 'error')
        return redirect(url_for('master_data.list_operations'))

    seen = set()
    op_names = []
    for name in candidates:
        normalized = ' '.join(name.split())
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        op_names.append(normalized)

    existing = {
        ' '.join((row[0] or '').split()).lower()
        for row in db.session.query(OperationType.operation_name)
        .filter(OperationType.operation_name.isnot(None))
        .all()
    }

    to_add = [n for n in op_names if n.lower() not in existing]
    skipped = [n for n in op_names if n.lower() in existing]

    if not to_add:
        flash('All provided operation names already exist.', 'warning')
        return redirect(url_for('master_data.list_operations'))

    try:
        for operation_name in to_add:
            db.session.add(OperationType(operation_name=operation_name))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('Some operation names already exist (unique constraint). Please retry.', 'error')
        return redirect(url_for('master_data.list_operations'))
    except Exception as e:
        logger.error(f'Error bulk adding operations: {str(e)}')
        db.session.rollback()
        flash('Error adding operations', 'error')
        return redirect(url_for('master_data.list_operations'))

    msg = f'Added {len(to_add)} operation(s) successfully.'
    if skipped:
        msg += f' Skipped {len(skipped)} existing.'
    flash(msg, 'success')
    return redirect(url_for('master_data.list_operations'))


# ==================== ISSUE TYPES ====================

@master_data_bp.route('/issues')
@admin_required
def list_issues():
    """List all issue types"""
    page = request.args.get('page', 1, type=int)
    pagination = IssueType.query.order_by(IssueType.issue_name).paginate(page=page, per_page=15, error_out=False)
    return render_template('master/issues_list.html', pagination=pagination)


@master_data_bp.route('/issues/add', methods=['GET', 'POST'])
@admin_required
def add_issue():
    """Add new issue type"""
    if request.method == 'GET':
        return render_template('master/issue_form.html', issue=None)
    
    elif request.method == 'POST':
        try:
            issue = IssueType(
                issue_name=request.form['issue_name'],
                category=request.form.get('category'),
                severity=request.form.get('severity', 'Medium'),
                description=request.form.get('description')
            )
            
            db.session.add(issue)
            db.session.commit()
            
            return redirect(url_for('master_data.list_issues'))
            
        except Exception as e:
            logger.error(f'Error adding issue: {str(e)}')
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


@master_data_bp.route('/issues/<int:issue_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_issue(issue_id):
    """Edit issue type"""
    issue = IssueType.query.get_or_404(issue_id)
    
    if request.method == 'GET':
        return render_template('master/issue_form.html', issue=issue)
    
    elif request.method == 'POST':
        try:
            issue.issue_name = request.form['issue_name']
            issue.category = request.form.get('category')
            issue.severity = request.form.get('severity', 'Medium')
            issue.description = request.form.get('description')
            
            db.session.commit()
            return redirect(url_for('master_data.list_issues'))
            
        except Exception as e:
            logger.error(f'Error editing issue: {str(e)}')
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


# ==================== EMPLOYEES ====================

@master_data_bp.route('/employees')
@admin_required
def list_employees():
    """List all employees/operators from shared master"""
    page = request.args.get('page', 1, type=int)
    pagination = EmpMaster.query.filter_by(status='Active').order_by(EmpMaster.emp_name).paginate(page=page, per_page=15, error_out=False)
    return render_template('master/employees_list.html', pagination=pagination)


@master_data_bp.route('/employees/add', methods=['GET', 'POST'])
def add_employee():
    """Redirect to MOA Admin for adding employees"""
    return render_template('error.html', error="Please use the main MOA Admin Portal to manage employees."), 403


# ==================== API ENDPOINTS FOR AJAX ====================

@master_data_bp.route('/api/machines', methods=['GET'])
def api_get_machines():
    """Get list of machines (for dropdowns)"""
    status = request.args.get('status', 'Active')
    shed_id = request.args.get('shed_id', type=int)
    query = Machine.query.filter_by(status=status)
    if shed_id:
        query = query.filter_by(shed_id=shed_id)
    machines = query.order_by(Machine.machine_name).all()
    return jsonify([{
        'id': m.id,
        'name': m.machine_name,
        'shed_id': m.shed_id
    } for m in machines])


@master_data_bp.route('/api/machine-sheds', methods=['GET'])
def api_get_machine_sheds():
    """Get list of machine sheds"""
    status = request.args.get('status', 'Active')
    sheds = MachineShed.query.filter_by(status=status).order_by(MachineShed.shed_name).all()
    return jsonify([{
        'id': shed.id,
        'name': shed.shed_name
    } for shed in sheds])


@master_data_bp.route('/api/customers', methods=['GET'])
def api_get_customers():
    """Get list of customers (for dropdowns)"""
    status = request.args.get('status', 'Active')
    q = (request.args.get('q') or '').strip()
    limit = request.args.get('limit', 50, type=int)
    select2 = (request.args.get('select2') or '').strip() in ('1', 'true', 'yes')

    # Clamp limits to protect the server.
    limit = max(1, min(limit, 200))

    query = Customer.query.filter_by(status=status)
    if q:
        query = query.filter(Customer.customer_name.ilike(f'%{q}%'))

    customers = query.order_by(Customer.customer_name).limit(limit).all()

    if select2:
        return jsonify({
            'results': [{
                'id': c.id,
                'text': c.customer_name
            } for c in customers]
        })

    # Backwards-compatible format (used by some simple dropdown fetches).
    return jsonify([{
        'id': c.id,
        'name': c.customer_name
    } for c in customers])


@master_data_bp.route('/api/operations', methods=['GET'])
def api_get_operations():
    """Get list of operation types"""
    operations = OperationType.query.order_by(OperationType.operation_name).all()
    return jsonify([{
        'id': o.id,
        'operation_name': o.operation_name,
        'name': o.operation_name,
        'standard_time': o.standard_cycle_time_seconds,
        'cycle_time_seconds': o.standard_cycle_time_seconds
    } for o in operations])


@master_data_bp.route('/api/operations/by-combo', methods=['GET'])
def api_get_operations_by_combo():
    """Get operations by machine + customer + section + cut length combo."""
    machine_id = request.args.get('machine_id', type=int)
    customer_id = request.args.get('customer_id', type=int)
    section_id = request.args.get('section_id', type=int)
    cut_length_id = request.args.get('cut_length_id', type=int)
    if not all([machine_id, customer_id, section_id, cut_length_id]):
        return jsonify([])

    section = SectionMaster.query.filter_by(id=section_id, customer_id=customer_id).first()
    if not section:
        return jsonify([])

    cut_length = SectionCutLength.query.filter_by(id=cut_length_id, section_id=section_id).first()
    if not cut_length:
        return jsonify([])

    cycle_rows = IdealCycleTime.query.filter_by(
        machine_id=machine_id,
        section_cut_length_id=cut_length_id
    ).order_by(IdealCycleTime.sequence, IdealCycleTime.id).all()

    result = []
    seen = set()
    for row in cycle_rows:
        op = OperationType.query.filter(func.lower(OperationType.operation_name) == func.lower(row.process_name)).first()
        key = (op.id if op else row.process_name).__str__().lower()
        if key in seen:
            continue
        seen.add(key)
        result.append({
            'id': op.id if op else None,
            'operation_type_id': op.id if op else None,
            'operation_name': op.operation_name if op else row.process_name,
            'name': op.operation_name if op else row.process_name,
            'seconds': row.cycle_time_seconds,
            'cycle_time_seconds': row.cycle_time_seconds
        })
    return jsonify(result)


@master_data_bp.route('/api/issues', methods=['GET'])
def api_get_issues():
    """Get list of issue types"""
    category = request.args.get('category')
    query = IssueType.query
    if category:
        query = query.filter_by(category=category)
    
    issues = query.all()
    return jsonify([{
        'id': i.id,
        'name': i.issue_name,
        'category': i.category,
        'severity': i.severity
    } for i in issues])


@master_data_bp.route('/api/employees', methods=['GET'])
@login_required
def api_get_employees():
    """Get list of employees from EmpMaster"""
    status = request.args.get('status', 'Active')
    emp_code = request.args.get('emp_code')
    
    query = EmpMaster.query
    if status:
        query = query.filter(EmpMaster.status.ilike(status))
    
    if emp_code:
        # Some codes might be stored as '15853' or ' 15853 '
        query = query.filter(EmpMaster.emp_code.ilike(f"%{emp_code.strip()}%"))
        employee = query.first()
        if employee:
            return jsonify({
                'id': employee.emp_id,
                'name': employee.emp_name,
                'emp_code': employee.emp_code
            })
        return jsonify({'error': 'Employee not found'}), 404
    
    # Return list if no specific code
    employees = query.all()
    return jsonify([{
        'id': e.emp_id,
        'name': e.emp_name,
        'emp_code': e.emp_code
    } for e in employees])


@master_data_bp.route('/api/all-operations', methods=['GET'])
@login_required
def api_get_all_operations():
    """Return all active operation types (fallback when no cycle times configured)"""
    ops = OperationType.query.order_by(OperationType.operation_name).all()
    return jsonify([{
        'id': op.id,
        'name': op.operation_name
    } for op in ops])

@master_data_bp.route('/api/downtime-reasons', methods=['GET'])
@login_required
def api_get_downtime_reasons():
    """Get list of active planned downtime reasons, excluding fixed per shift reasons"""
    reasons = DowntimeReason.query.filter_by(
        status='Active',
        is_fixed=False
    ).all()
    return jsonify([{
        'id': r.id,
        'reason_name': r.reason_name
    } for r in reasons])

# ==================== DOWNTIME REASONS ====================

@master_data_bp.route('/downtime-reasons')
@admin_required
def list_downtime_reasons():
    """List all downtime reasons"""
    reasons = DowntimeReason.query.order_by(DowntimeReason.reason_name).all()
    return render_template('master/downtime_reasons_list.html', reasons=reasons)


@master_data_bp.route('/downtime-reasons/add', methods=['GET', 'POST'])
@admin_required
def add_downtime_reason():
    """Add new downtime reason"""
    if request.method == 'GET':
        return render_template('master/downtime_reason_form.html', reason=None)
    
    elif request.method == 'POST':
        try:
            reason = DowntimeReason(
                reason_name=request.form['reason_name'],
                description=request.form.get('description'),
                is_fixed=True if request.form.get('is_fixed') == 'on' else False,
                default_minutes=int(request.form.get('default_minutes', 0)) if request.form.get('default_minutes') else 0,
                status=request.form.get('status', 'Active')
            )
            db.session.add(reason)
            db.session.commit()
            flash('Downtime reason added successfully!', 'success')
            return redirect(url_for('master_data.list_downtime_reasons'))
        except Exception as e:
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


@master_data_bp.route('/downtime-reasons/<int:reason_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_downtime_reason(reason_id):
    """Edit downtime reason"""
    reason = DowntimeReason.query.get_or_404(reason_id)
    if request.method == 'GET':
        return render_template('master/downtime_reason_form.html', reason=reason)
    
    elif request.method == 'POST':
        try:
            reason.reason_name = request.form['reason_name']
            reason.description = request.form.get('description')
            reason.is_fixed = True if request.form.get('is_fixed') == 'on' else False
            reason.default_minutes = int(request.form.get('default_minutes', 0)) if request.form.get('default_minutes') else 0
            reason.status = request.form.get('status', 'Active')
            db.session.commit()
            flash('Downtime reason updated successfully!', 'success')
            return redirect(url_for('master_data.list_downtime_reasons'))
        except Exception as e:
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


@master_data_bp.route('/downtime-reasons/<int:reason_id>/delete', methods=['POST'])
@admin_required
def delete_downtime_reason(reason_id):
    """Delete downtime reason"""
    try:
        reason = DowntimeReason.query.get_or_404(reason_id)
        db.session.delete(reason)
        db.session.commit()
        flash('Downtime reason deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting reason: Maybe it is in use. Error: {str(e)}', 'danger')
    return redirect(url_for('master_data.list_downtime_reasons'))
# ==================== DEFECT TYPES ====================

@master_data_bp.route('/defect-types')
@admin_required
def list_defect_types():
    """List all defect types"""
    defects = DefectType.query.order_by(DefectType.defect_name).all()
    return render_template('master/defect_types_list.html', defects=defects)


@master_data_bp.route('/defect-types/add', methods=['GET', 'POST'])
@admin_required
def add_defect_type():
    """Add new defect type"""
    if request.method == 'GET':
        return render_template('master/defect_type_form.html', defect=None)
    
    elif request.method == 'POST':
        try:
            defect = DefectType(
                defect_name=request.form['defect_name'],
                category=request.form.get('category'),
                is_active=True if request.form.get('is_active') == 'on' else False
            )
            db.session.add(defect)
            db.session.commit()
            flash('Defect type added successfully!', 'success')
            return redirect(url_for('master_data.list_defect_types'))
        except Exception as e:
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


@master_data_bp.route('/defect-types/<int:defect_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_defect_type(defect_id):
    """Edit defect type"""
    defect = DefectType.query.get_or_404(defect_id)
    if request.method == 'GET':
        return render_template('master/defect_type_form.html', defect=defect)
    
    elif request.method == 'POST':
        try:
            defect.defect_name = request.form['defect_name']
            defect.category = request.form.get('category')
            defect.is_active = True if request.form.get('is_active') == 'on' else False
            db.session.commit()
            flash('Defect type updated successfully!', 'success')
            return redirect(url_for('master_data.list_defect_types'))
        except Exception as e:
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


@master_data_bp.route('/defect-types/<int:defect_id>/delete', methods=['POST'])
@admin_required
def delete_defect_type(defect_id):
    """Delete defect type"""
    try:
        defect = DefectType.query.get_or_404(defect_id)
        db.session.delete(defect)
        db.session.commit()
        flash('Defect type deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting defect type: Maybe it is in use. Error: {str(e)}', 'danger')
    return redirect(url_for('master_data.list_defect_types'))


# ==================== MACHINE TARGETS ====================

@master_data_bp.route('/machine-targets')
@admin_required
def list_machine_targets():
    """List all machine targets"""
    targets = MachineTarget.query.order_by(MachineTarget.target_month.desc(), MachineTarget.machine_id).all()
    return render_template('master/machine_targets_list.html', targets=targets)


@master_data_bp.route('/machine-targets/add', methods=['GET', 'POST'])
@admin_required
def add_machine_target():
    """Add new machine target"""
    if request.method == 'GET':
        machines = Machine.query.order_by(Machine.machine_name).all()
        return render_template('master/machine_target_form.html', target=None, machines=machines)
    
    elif request.method == 'POST':
        try:
            # Check if target already exists for this machine and month
            machine_id = request.form['machine_id']
            target_month = request.form['target_month']
            
            existing = MachineTarget.query.filter_by(machine_id=machine_id, target_month=target_month).first()
            if existing:
                flash(f'Target for this machine in {target_month} already exists.', 'danger')
                return redirect(url_for('master_data.add_machine_target'))

            target = MachineTarget(
                machine_id=machine_id,
                target_month=target_month,
                target_qty=request.form.get('target_qty', 0, type=int),
                capacity=request.form.get('capacity', 0, type=int)
            )
            db.session.add(target)
            db.session.commit()
            flash('Machine target added successfully!', 'success')
            return redirect(url_for('master_data.list_machine_targets'))
        except Exception as e:
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


@master_data_bp.route('/machine-targets/<int:target_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_machine_target(target_id):
    """Edit machine target"""
    target = MachineTarget.query.get_or_404(target_id)
    if request.method == 'GET':
        machines = Machine.query.order_by(Machine.machine_name).all()
        return render_template('master/machine_target_form.html', target=target, machines=machines)
    
    elif request.method == 'POST':
        try:
            # Don't change machine/month if it creates duplicate
            new_m_id = request.form['machine_id']
            new_month = request.form['target_month']
            
            existing = MachineTarget.query.filter(
                MachineTarget.machine_id == new_m_id, 
                MachineTarget.target_month == new_month,
                MachineTarget.id != target.id
            ).first()
            
            if existing:
                flash(f'Target for this machine in {new_month} already exists.', 'danger')
                return redirect(url_for('master_data.edit_machine_target', target_id=target.id))

            target.machine_id = new_m_id
            target.target_month = new_month
            target.target_qty = request.form.get('target_qty', 0, type=int)
            target.capacity = request.form.get('capacity', 0, type=int)
            
            db.session.commit()
            flash('Machine target updated successfully!', 'success')
            return redirect(url_for('master_data.list_machine_targets'))
        except Exception as e:
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500


@master_data_bp.route('/machine-targets/<int:target_id>/delete', methods=['POST'])
@admin_required
def delete_machine_target(target_id):
    """Delete machine target"""
    try:
        target = MachineTarget.query.get_or_404(target_id)
        db.session.delete(target)
        db.session.commit()
        flash('Machine target deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting machine target: {str(e)}', 'danger')
    return redirect(url_for('master_data.list_machine_targets'))

