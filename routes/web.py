"""
Web Routes - Main web pages
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, flash, send_file
from models import (
    db, ProductionEntry, Machine, MachineShed, Customer, EmpMaster, OperationType, IssueType,
    ProductionEntryOperator, ProductionPlannedDowntime, DowntimeReason,
    ProductionEntryOperation, ProductionEntrySupervisor, SectionMaster, SectionCutLength,
    DefectType, ProductionSelfRejectionDefect
)
from datetime import datetime, timedelta, timezone
from utils.auth import login_required, admin_required, _has_module_access, _has_role_access
from sqlalchemy import or_
import os
import hashlib
import logging
from io import BytesIO
import pandas as pd
from werkzeug.security import check_password_hash

logger = logging.getLogger(__name__)
web_bp = Blueprint('web', __name__)


def _parse_local_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _default_records_window():
    now = datetime.now()
    # Default to "this month so far", but include entries later today (future times)
    # because operators often submit shift entries before the shift fully ends.
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start, end


def _resolve_records_window(start_value, end_value):
    default_start, default_end = _default_records_window()
    start_dt = _parse_local_datetime(start_value) or default_start
    end_dt = _parse_local_datetime(end_value) or default_end
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    return start_dt, end_dt


def _apply_production_emp_code_filter(query, emp_code):
    emp_code = (emp_code or '').strip()
    if not emp_code:
        return query
    matching_emp_ids = [
        row[0] for row in db.session.query(EmpMaster.emp_id)
        .filter(EmpMaster.emp_code.ilike(f"%{emp_code}%"))
        .all()
    ]
    if not matching_emp_ids:
        return query.filter(ProductionEntry.id == -1)

    operator_entry_ids = db.session.query(ProductionEntryOperator.production_entry_id).filter(
        ProductionEntryOperator.operator_emp_id.in_(matching_emp_ids)
    )
    supervisor_entry_ids = db.session.query(ProductionEntrySupervisor.production_entry_id).filter(
        ProductionEntrySupervisor.supervisor_emp_id.in_(matching_emp_ids)
    )
    return query.filter(or_(
        ProductionEntry.operator_emp_id.in_(matching_emp_ids),
        ProductionEntry.id.in_(operator_entry_ids),
        ProductionEntry.id.in_(supervisor_entry_ids)
    ))


def _build_production_entries_query():
    query = ProductionEntry.query
    start_dt, end_dt = _resolve_records_window(
        request.args.get('start_time'),
        request.args.get('end_time')
    )

    entry_no = (request.args.get('entry_no') or '').strip()
    if entry_no:
        # When searching by Entry No, don't hide the record just because the selected
        # time window doesn't overlap (common when the entry time is later today).
        query = query.filter(ProductionEntry.entry_no.ilike(f"%{entry_no}%"))
    else:
        # Show any production entry that overlaps the requested window.
        # This avoids hiding entries that were submitted for later in the day
        # or entries spanning across date boundaries.
        query = query.filter(ProductionEntry.start_time <= end_dt)
        query = query.filter(ProductionEntry.end_time >= start_dt)

    if request.args.get('machine_id'):
        query = query.filter_by(machine_id=request.args.get('machine_id', type=int))

    if request.args.get('shed_id'):
        query = query.join(Machine, Machine.id == ProductionEntry.machine_id)
        query = query.filter(Machine.shed_id == request.args.get('shed_id', type=int))

    if request.args.get('shift'):
        query = query.filter_by(shift=request.args.get('shift').upper())

    if request.args.get('customer_id'):
        query = query.filter_by(customer_id=request.args.get('customer_id', type=int))

    section_filter = (request.args.get('section_number') or request.args.get('section') or '').strip()
    if section_filter:
        query = query.filter(ProductionEntry.section_number.ilike(f"%{section_filter}%"))

    cutlength_filter = (request.args.get('cut_length') or request.args.get('cutlength') or '').strip()
    if cutlength_filter:
        try:
            cl = float(cutlength_filter)
            query = query.filter(ProductionEntry.cutlength == cl)
        except ValueError:
            pass

    operation_type_id = request.args.get('operation_type_id', type=int)
    if operation_type_id:
        query = query.join(ProductionEntryOperation, ProductionEntryOperation.production_entry_id == ProductionEntry.id)
        query = query.filter(ProductionEntryOperation.operation_type_id == operation_type_id)
        query = query.distinct()

    quality_status = (request.args.get('quality_status') or '').strip().lower()
    if quality_status == 'pending':
        query = query.filter(ProductionEntry.rejection == None)  # noqa: E711
    elif quality_status == 'completed':
        query = query.filter(ProductionEntry.rejection != None)  # noqa: E711

    query = _apply_production_emp_code_filter(query, request.args.get('emp_code'))
    return query, start_dt, end_dt


def _parse_self_rejection_rows(form):
    defect_type_ids = form.getlist('self_rejection_defect_type_id[]')
    reject_qtys = form.getlist('self_rejection_defect_qty[]')
    rows = []
    total_qty = 0

    for i in range(max(len(defect_type_ids), len(reject_qtys))):
        defect_type_id = (defect_type_ids[i] if i < len(defect_type_ids) else '').strip()
        reject_qty_raw = (reject_qtys[i] if i < len(reject_qtys) else '').strip()
        # Defect-wise self rejection is optional. Ignore empty rows and rows with 0 qty.
        qty = int(reject_qty_raw or 0)
        if not defect_type_id and qty <= 0:
            continue
        if not defect_type_id and qty > 0:
            raise ValueError('Please select a defect type for each self rejection row with qty > 0.')
        if defect_type_id and qty <= 0:
            raise ValueError('Self rejection qty must be greater than 0 for each selected defect.')
        rows.append({
            'defect_type_id': int(defect_type_id),
            'reject_qty': qty
        })
        total_qty += qty

    machining_scrap_weight = float(form.get('total_machining_scrap_kg') or 0)
    if machining_scrap_weight <= 0:
        raise ValueError('Total Machining Scrap (kg) is required and must be greater than 0.')

    weight_per_pcs = round(float(form.get('self_rejection_weight_per_pcs') or 0), 3)
    if weight_per_pcs <= 0:
        raise ValueError('Weight/PC (kg) is required and must be greater than 0.')

    return rows, total_qty, weight_per_pcs, round(machining_scrap_weight, 3)


def _safe_int(value, default=0):
    if value is None:
        return default
    if isinstance(value, str):
        value = value.strip()
        if value == '':
            return default
    return int(value)


def _safe_float(value, default=0.0):
    if value is None:
        return default
    if isinstance(value, str):
        value = value.strip()
        if value == '':
            return default
    return float(value)


@web_bp.route('/')
def index():
    """Home page / Dashboard redirect"""
    return redirect(url_for('dashboard.daily_dashboard'))


@web_bp.route('/production-entry', methods=['GET', 'POST'])
@login_required
def production_entry_form():
    """
    Production data entry form
    GET: Show form with master data
    POST: Process form submission
    """
    if request.method == 'GET':
        # Fetch master data
        sheds = MachineShed.query.filter_by(status='Active').order_by(MachineShed.shed_name).all()
        machines = Machine.query.filter_by(status='Active').order_by(Machine.machine_name).all()
        customers = Customer.query.filter_by(status='Active').all()
        operations = OperationType.query.all()
        employees = EmpMaster.query.filter_by(status='Active').all()
        defect_types = DefectType.query.filter_by(is_active=True).order_by(DefectType.defect_name).all()
        
        # Calculate current shift
        now_local = datetime.now() # Assuming server is on local time or we use a better offset
        hour = now_local.hour
        if 6 <= hour < 14:
            current_shift = 'A'
        elif 14 <= hour < 22:
            current_shift = 'B'
        else:
            current_shift = 'C'
            
        # Fetch fixed downtime reasons
        fixed_reasons = DowntimeReason.query.filter_by(status='Active', is_fixed=True).all()
        fixed_downtime_total = sum(r.default_minutes for r in fixed_reasons if r.default_minutes)
        
        return render_template('production_entry.html',
                             sheds=sheds,
                             machines=machines,
                             customers=customers,
                             operations=operations,
                             employees=employees,
                             defect_types=defect_types,
                             current_shift=current_shift,
                             now=now_local,
                             fixed_reasons=fixed_reasons,
                             fixed_downtime_total=fixed_downtime_total)
    
    elif request.method == 'POST':
        try:
            # Get form data
            shifts_str = request.form.get('shift', '').upper()
            first_shift = shifts_str.split(',')[0].strip() if shifts_str else 'A'
            # Parse Production Start/End
            start_time = datetime.fromisoformat(request.form['start_time'])
            end_time = datetime.fromisoformat(request.form['end_time'])

            if start_time >= end_time:
                raise ValueError('Actual Production Start Time must be earlier than Actual Production End Time.')
             
            # Overlap Validation
            machine_id = int(request.form['machine_id'])
            overlap = ProductionEntry.query.filter(
                ProductionEntry.machine_id == machine_id,
                ProductionEntry.start_time < end_time,
                ProductionEntry.end_time > start_time
            ).first()
            
            if overlap:
                flash(f'Overlap detected! Machine is already scheduled for another entry between {overlap.start_time.strftime("%H:%M")} and {overlap.end_time.strftime("%H:%M")}.', 'danger')
                return redirect(url_for('web.production_entry_form'))

            planned_qty = _safe_int(request.form['planned_quantity'])
            actual_qty = _safe_int(request.form.get('actual_quantity'))
            self_rejection_rows, self_rejection_qty, self_rejection_weight_per_pcs, machining_scrap_weight_kg = _parse_self_rejection_rows(request.form)
            qty_var = actual_qty - planned_qty
            qty_var_pct = (qty_var / planned_qty * 100) if planned_qty > 0 else 0.0
            total_runtime_mins = float(request.form.get('total_time_taken_minutes') or 0)
            total_ideal_mins = float(request.form.get('total_ideal_time_minutes') or 0)
            if total_ideal_mins > total_runtime_mins:
                flash('Total Ideal Time (Mins) cannot be more than Total Available Machine Hours. Please review both fields.', 'danger')
                return redirect(url_for('web.production_entry_form'))

            prod_entry = ProductionEntry(
                production_date=datetime.strptime(request.form['production_date'], '%Y-%m-%d').date(),
                shift=shifts_str,
                shift_index={'A': 1, 'B': 2, 'C': 3}.get(first_shift, 1),
                start_time=start_time,
                end_time=end_time,
                machine_id=machine_id,
                customer_id=int(request.form['customer_id']),
                operation_type_id=int(request.form.getlist('operation_type_id[]')[0]) if request.form.getlist('operation_type_id[]') else None,
                section_number=request.form.get('section_number'),
                cutlength=_safe_float(request.form.get('cutlength'), None) if request.form.get('cutlength') else None,
                planned_quantity=planned_qty,
                actual_quantity=actual_qty,
                qty_variance=qty_var,
                qty_variance_percent=qty_var_pct,
                self_rejection_qty=self_rejection_qty,
                self_rejection_weight_per_pcs=self_rejection_weight_per_pcs,
                machining_scrap_weight_kg=machining_scrap_weight_kg,
                ideal_cycle_time=_safe_float(request.form.get('ideal_cycle_time')) if request.form.get('ideal_cycle_time') and not request.form.get('no_cycle_time') else None,
                total_time_taken_minutes=int(total_runtime_mins),
                total_ideal_time_minutes=total_ideal_mins,
                downtime_minutes=_safe_int(request.form.get('total_planned_downtime')),
                remarks=request.form.get('remarks'),
                created_by=request.form.get('created_by', 'web_form')
            )
            
            # Generate Unique Entry No
            year = prod_entry.production_date.year
            from sqlalchemy import extract
            count = ProductionEntry.query.filter(extract('year', ProductionEntry.production_date) == year).count() + 1
            prod_entry.entry_no = f"MS-{year}-{count:04d}"
            
            db.session.add(prod_entry)
            db.session.flush()
            
            # Add Operations
            op_type_ids = request.form.getlist('operation_type_id[]')
            for op_id in op_type_ids:
                if op_id:
                    op_mapping = ProductionEntryOperation(
                        production_entry_id=prod_entry.id,
                        operation_type_id=int(op_id)
                    )
                    db.session.add(op_mapping)

            for self_row in self_rejection_rows:
                db.session.add(ProductionSelfRejectionDefect(
                    production_entry_id=prod_entry.id,
                    defect_type_id=self_row['defect_type_id'],
                    reject_qty=self_row['reject_qty']
                ))
            
            # Handle multiple operators with their own times
            op_ids = request.form.getlist('operator_id[]')
            op_starts = request.form.getlist('op_start_time[]')
            op_ends = request.form.getlist('op_end_time[]')
            
            for i in range(len(op_ids)):
                if op_ids[i]:
                    op_start = datetime.fromisoformat(op_starts[i]) if i < len(op_starts) and op_starts[i] else start_time
                    op_end = datetime.fromisoformat(op_ends[i]) if i < len(op_ends) and op_ends[i] else end_time
                    if op_start >= op_end:
                        raise ValueError(f'Operator row #{i + 1}: Start Time must be earlier than End Time.')
                    mapping = ProductionEntryOperator(
                        production_entry_id=prod_entry.id,
                        operator_emp_id=int(op_ids[i]),
                        start_time=op_start,
                        end_time=op_end
                    )
                    db.session.add(mapping)

            # Handle multiple supervisors with their own times
            sup_ids = request.form.getlist('supervisor_id[]')
            sup_starts = request.form.getlist('sup_start_time[]')
            sup_ends = request.form.getlist('sup_end_time[]')
            
            for i in range(len(sup_ids)):
                if sup_ids[i]:
                    sup_start = datetime.fromisoformat(sup_starts[i]) if i < len(sup_starts) and sup_starts[i] else start_time
                    sup_end = datetime.fromisoformat(sup_ends[i]) if i < len(sup_ends) and sup_ends[i] else end_time
                    if sup_start >= sup_end:
                        raise ValueError(f'Supervisor row #{i + 1}: Start Time must be earlier than End Time.')
                    mapping = ProductionEntrySupervisor(
                        production_entry_id=prod_entry.id,
                        supervisor_emp_id=int(sup_ids[i]),
                        start_time=sup_start,
                        end_time=sup_end
                    )
                    db.session.add(mapping)

            # Add Fixed Downtime Records (from configured DowntimeReasons)
            shifts = [s.strip() for s in shifts_str.split(',') if s.strip()]
            fixed_reasons = DowntimeReason.query.filter_by(status='Active', is_fixed=True).all()
            
            for shift_name in shifts:
                for reason in fixed_reasons:
                    if reason.default_minutes and reason.default_minutes > 0:
                        dt_record = ProductionPlannedDowntime(
                            production_entry_id=prod_entry.id,
                            reason_id=reason.id,
                            duration_minutes=reason.default_minutes
                        )
                        db.session.add(dt_record)

            # Handle Manual/Additional planned downtime
            dt_reason_ids = request.form.getlist('downtime_reason_id[]')
            dt_durations = request.form.getlist('downtime_minutes[]')
            
            for i in range(len(dt_reason_ids)):
                if dt_reason_ids[i] and dt_durations[i]:
                    dt_record = ProductionPlannedDowntime(
                        production_entry_id=prod_entry.id,
                        reason_id=_safe_int(dt_reason_ids[i]),
                        duration_minutes=_safe_int(dt_durations[i])
                    )
                    db.session.add(dt_record)
            
            db.session.commit()
            flash(f'Production entry submitted successfully! Entry No: {prod_entry.entry_no}', 'success')
            # Jump directly to the created record to avoid confusion with default filters/time windows.
            return redirect(url_for('web.view_entries', entry_no=prod_entry.entry_no))
             
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            return redirect(url_for('web.production_entry_form'))
        except Exception as e:
            db.session.rollback()
            logger.exception('Error saving production entry')
            # Show a clear user-facing failure reason (trimmed) instead of silent failure.
            msg = str(e)
            if len(msg) > 250:
                msg = msg[:250] + '...'
            flash(f'Failed to submit production entry: {msg}', 'danger')
            return redirect(url_for('web.production_entry_form'))


@web_bp.route('/production-entry/bulk-upload', methods=['GET', 'POST'])
# @login_required
def bulk_upload():
    """Bulk upload CSV"""
    if request.method == 'GET':
        return render_template('bulk_upload.html')
    
    elif request.method == 'POST':
        # Handled by API endpoint
        return redirect(url_for('web.production_entry_form'))


@web_bp.route('/entries')
# @login_required
def view_entries():
    """View all entries with filtering"""
    page = request.args.get('page', 1, type=int)
    query, start_dt, end_dt = _build_production_entries_query()

    paginated = query.order_by(ProductionEntry.production_date.desc(), ProductionEntry.id.desc()).paginate(page=page, per_page=50)
    
    sheds = MachineShed.query.filter_by(status='Active').order_by(MachineShed.shed_name).all()
    machines = Machine.query.all()
    customers = Customer.query.filter_by(status='Active').all()
    operations = OperationType.query.order_by(OperationType.operation_name).all()
    selected_customer_id = request.args.get('customer_id', type=int)
    sections = SectionMaster.query.filter_by(customer_id=selected_customer_id, status='Active').order_by(SectionMaster.section_number).all() if selected_customer_id else []
    selected_section_number = (request.args.get('section_number') or request.args.get('section') or '').strip()
    selected_section = next((s for s in sections if (s.section_number or '').strip() == selected_section_number), None)
    cut_lengths = SectionCutLength.query.filter_by(section_id=selected_section.id, status='Active').order_by(SectionCutLength.cut_length).all() if selected_section else []
    
    return render_template('view_entries.html',
                         entries=paginated.items,
                         pagination=paginated,
                         sheds=sheds,
                         machines=machines,
                         customers=customers,
                         operations=operations,
                         sections=sections,
                         cut_lengths=cut_lengths,
                         start_time_value=start_dt.strftime('%Y-%m-%dT%H:%M'),
                         end_time_value=end_dt.strftime('%Y-%m-%dT%H:%M'))


@web_bp.route('/entries/embed')
def view_entries_embed():
    """Embedded production-records view without sidebar/filter chrome."""
    page = request.args.get('page', 1, type=int)
    query, _, _ = _build_production_entries_query()
    paginated = query.order_by(ProductionEntry.production_date.desc(), ProductionEntry.id.desc()).paginate(page=page, per_page=25)
    embed_args = request.args.to_dict(flat=True)
    embed_args.pop('page', None)
    return render_template(
        'production_records_embed.html',
        entries=paginated.items,
        pagination=paginated,
        embed_args=embed_args
    )


@web_bp.route('/entries/export')
# @login_required
def export_entries_excel():
    """Export filtered production records to Excel."""
    query, _, _ = _build_production_entries_query()

    entries = query.order_by(ProductionEntry.production_date.desc(), ProductionEntry.id.desc()).all()

    rows = []
    for e in entries:
        total_self_rejection_kg = round((e.self_rejection_weight_per_pcs or 0) * (e.self_rejection_qty or 0), 3)
        total_self_rejection_all_kg = round(total_self_rejection_kg + (e.machining_scrap_weight_kg or 0), 3)
        operators = '; '.join([
            f"{op.operator_info.emp_name if op.operator_info else ''} ({op.operator_info.emp_code if op.operator_info else ''}) [{op.start_time} - {op.end_time}]"
            for op in e.operators
        ])
        supervisors = '; '.join([
            f"{sup.supervisor_info.emp_name if sup.supervisor_info else ''} ({sup.supervisor_info.emp_code if sup.supervisor_info else ''}) [{sup.start_time} - {sup.end_time}]"
            for sup in e.supervisors
        ])
        operations = '; '.join([
            op.operation_type.operation_name if op.operation_type else ''
            for op in e.operations
        ])
        downtime_details = '; '.join([
            f"{pd.reason.reason_name if pd.reason else 'N/A'}: {pd.duration_minutes or 0} min"
            for pd in e.planned_downtime
        ])
        downtime_sum = sum((pd.duration_minutes or 0) for pd in e.planned_downtime)
        issues = '; '.join([
            f"{issue.issue_type.issue_name if issue.issue_type else 'Issue'} ({issue.impact_minutes or 0}m): {issue.custom_remark or ''}"
            for issue in e.issues
        ])
        rework_summary = {}
        for log in e.rework_logs:
            label = log.defect_type.defect_name if log.defect_type else f"Defect-{log.defect_type_id}"
            rework_summary[label] = rework_summary.get(label, 0) + (log.rework_qty or 0)
        rework_details = '; '.join(f"{label}: {qty} pcs" for label, qty in rework_summary.items())
        self_rejection_details = '; '.join([
            f"{row.defect_type.defect_name if row.defect_type else 'Defect'}: {row.reject_qty or 0} pcs"
            for row in e.self_rejection_defects
        ])

        rejection = e.rejection
        rejection_defects = ''
        rejection_supervisors = ''
        rejection_quality_score = None
        rejection_final_reject_pcs = None
        rejection_total_rework_qty = None
        rejection_final_ok_qty = None
        if rejection:
            rejection_defects = '; '.join([
                f"{d.defect_type.defect_name if d.defect_type else 'Defect'}: {d.defect_count}"
                for d in rejection.defects
            ])
            rejection_supervisors = '; '.join([
                f"{s.supervisor_info.emp_name if s.supervisor_info else ''} ({s.supervisor_info.emp_code if s.supervisor_info else ''}) [{s.start_time} - {s.end_time}]"
                for s in rejection.supervisors
            ])
            if (rejection.total_parts_inspected_qty or 0) > 0:
                rejection_quality_score = round(((rejection.total_parts_inspected_qty - (rejection.rj_pcs or 0)) / rejection.total_parts_inspected_qty) * 100, 2)
                if rejection_quality_score < 0:
                    rejection_quality_score = 0
            rejection_final_reject_pcs = rejection.rj_pcs or 0
            rejection_total_rework_qty = e.rework_qty or 0
            rejection_final_ok_qty = e.total_ok_quantity

        rows.append({
            'Entry ID': e.id,
            'Entry No': e.entry_no,
            'Production Date': e.production_date,
            'Shift': e.shift,
            'Start Time': e.start_time,
            'End Time': e.end_time,
            'Shed': e.machine.shed.shed_name if e.machine and e.machine.shed else None,
            'Machine': e.machine.machine_name if e.machine else None,
            'Machine Type': e.machine.machine_type if e.machine else None,
            'Customer': e.customer.customer_name if e.customer else None,
            'Section Number': e.section_number,
            'Cut Length (mm)': e.cutlength,
            'Planned Quantity': e.planned_quantity,
            'Actual OK Quantity': e.actual_quantity,
            'Rework Quantity': e.rework_qty or 0,
            'Rework Details': rework_details,
            'Total OK (Auto)': e.total_ok_quantity,
            'Total OK Note': 'ProductionEntry.total_ok_quantity = actual_quantity - current remaining quality rejects. Rework logs reduce the remaining rejection balance, so rework is already reflected indirectly and is not added again.',
            'Total Self Rejection PCS': e.self_rejection_qty or 0,
            'Weight/PC (kg)': e.self_rejection_weight_per_pcs or 0,
            'Total Self Rejection KGs (Auto)': total_self_rejection_kg,
            'Total Machining Scrap (kg)': e.machining_scrap_weight_kg or 0,
            'Total Self Rejection (All) KGs (Auto)': total_self_rejection_all_kg,
            'Production Self Rejection Details': self_rejection_details,
            'Qty Variance (Auto)': e.qty_variance,
            'Qty Variance % (Auto)': e.qty_variance_percent,
            'Efficiency % (Auto)': round(e.efficiency or 0, 2),
            'Ideal Cycle Time/Pc (Sum)': e.ideal_cycle_time,
            'Total Ideal Time (Mins)': e.total_ideal_time_minutes,
            'Total Shift Time / Runtime (Mins)': e.total_time_taken_minutes,
            'Downtime Minutes (Stored)': e.downtime_minutes,
            'Planned Downtime Sum (Rows)': downtime_sum,
            'Total Unaccounted Time (Auto)': round((e.total_time_taken_minutes or 0) - (e.total_ideal_time_minutes or 0), 2),
            'Operations / Process': operations,
            'Operators (with time)': operators,
            'Supervisors (with time)': supervisors,
            'Planned Downtime Details': downtime_details,
            'Production Issues': issues,
            'Remarks': e.remarks,
            'Created By': e.created_by,
            'Created At': e.created_at,
            'Updated At': e.updated_at,
            'Rejection ID': rejection.id if rejection else None,
            'Rejection Datetime': rejection.rejection_datetime if rejection else None,
            'Rejection Inspected Qty': rejection.total_parts_inspected_qty if rejection else None,
            'Rejection Pcs': rejection.rj_pcs if rejection else None,
            'Rejection Weight/Pc': rejection.weight_per_pcs if rejection else None,
            'Rejection Weight (Auto)': rejection.rj_weight if rejection else None,
            'Rejection Quality Score %': rejection_quality_score,
            'Rejection Quality Remarks': rejection.rejection_reason if rejection else None,
            'Rejection Reason': rejection.rejection_reason if rejection else None,
            'Rejection Defects': rejection_defects,
            'Rejection Supervisors': rejection_supervisors,
            'Rejection Final Reject Pcs (After Rework)': rejection_final_reject_pcs,
            'Rejection Total Rework Qty': rejection_total_rework_qty,
            'Rejection Final OK Qty (Auto)': rejection_final_ok_qty
        })

    df = pd.DataFrame(rows)
    output = BytesIO()
    df.to_excel(output, index=False, sheet_name='Production Records')
    output.seek(0)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(
        output,
        as_attachment=True,
        download_name=f'production_records_export_{ts}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@web_bp.route('/entry/<int:entry_id>')
# @login_required
def view_entry(entry_id):
    """View single entry details"""
    entry = ProductionEntry.query.get_or_404(entry_id)
    return render_template('entry_detail.html', entry=entry)


@web_bp.route('/entry/<int:entry_id>/edit', methods=['GET', 'POST'])
# @login_required
def edit_entry(entry_id):
    """Edit production entry"""
    entry = ProductionEntry.query.get_or_404(entry_id)
    
    if request.method == 'GET':
        sheds = MachineShed.query.filter_by(status='Active').order_by(MachineShed.shed_name).all()
        machines = Machine.query.order_by(Machine.machine_name).all()
        customers = Customer.query.all()
        operations = OperationType.query.all()
        employees = EmpMaster.query.all()
        defect_types = DefectType.query.filter_by(is_active=True).order_by(DefectType.defect_name).all()
        
        reasons = DowntimeReason.query.filter_by(status='Active').order_by(DowntimeReason.reason_name).all()
        fixed_reasons = DowntimeReason.query.filter_by(status='Active', is_fixed=True).all()
        fixed_downtime_total = sum(r.default_minutes for r in fixed_reasons if r.default_minutes)

        current_section_id = ''
        current_cutlength_id = ''
        current_operation_id = ''

        if entry.section_number:
            section_query = SectionMaster.query.filter_by(
                customer_id=entry.customer_id,
                section_number=entry.section_number,
                status='Active'
            ).first()
            if section_query:
                current_section_id = section_query.id
                if entry.cutlength is not None:
                    cutlength_query = SectionCutLength.query.filter_by(
                        section_id=section_query.id,
                        cut_length=entry.cutlength,
                        status='Active'
                    ).first()
                    if cutlength_query:
                        current_cutlength_id = cutlength_query.id

        if entry.operations:
            current_operation_id = entry.operations[0].operation_type_id
        elif entry.operation_type_id:
            current_operation_id = entry.operation_type_id

        return render_template('edit_entry.html',
                             entry=entry,
                             sheds=sheds,
                             machines=machines,
                             customers=customers,
                             operations=operations,
                             employees=employees,
                             defect_types=defect_types,
                             downtime_reasons=reasons,
                             fixed_reasons=fixed_reasons,
                             fixed_downtime_total=fixed_downtime_total,
                             current_section_id=current_section_id,
                             current_cutlength_id=current_cutlength_id,
                             current_operation_id=current_operation_id)
    
    elif request.method == 'POST':
        try:
            # Get form data
            shifts_str = request.form.get('shift', '').upper()
            first_shift = [s.strip() for s in shifts_str.split(',') if s.strip()][0] if shifts_str else 'A'
            
            # Overlap Validation
            machine_id = int(request.form['machine_id'])
            start_time = datetime.fromisoformat(request.form['start_time'])
            end_time = datetime.fromisoformat(request.form['end_time'])

            if start_time >= end_time:
                raise ValueError('Actual Production Start Time must be earlier than Actual Production End Time.')
             
            overlap = ProductionEntry.query.filter(
                ProductionEntry.machine_id == machine_id,
                ProductionEntry.id != entry_id,
                ProductionEntry.start_time < end_time,
                ProductionEntry.end_time > start_time
            ).first()
            
            if overlap:
                flash(f'Overlap detected! Machine is already scheduled for another entry between {overlap.start_time.strftime("%H:%M")} and {overlap.end_time.strftime("%H:%M")}.', 'danger')
                return redirect(url_for('web.edit_entry', entry_id=entry_id))

            entry.production_date = datetime.strptime(request.form['production_date'], '%Y-%m-%d').date()
            entry.shift = shifts_str
            entry.shift_index = {'A': 1, 'B': 2, 'C': 3}.get(first_shift, 1)
            entry.start_time = start_time
            entry.end_time = end_time
            entry.machine_id = machine_id
            entry.customer_id = _safe_int(request.form['customer_id'])
            entry.operation_type_id = _safe_int(request.form.getlist('operation_type_id[]')[0], None) if request.form.getlist('operation_type_id[]') else None
            entry.section_number = request.form.get('section_number')
            entry.cutlength = _safe_float(request.form.get('cutlength'), None) if request.form.get('cutlength') else None
            entry.planned_quantity = _safe_int(request.form['planned_quantity'])
            entry.actual_quantity = _safe_int(request.form.get('actual_quantity'))
            self_rejection_rows, self_rejection_qty, self_rejection_weight_per_pcs, machining_scrap_weight_kg = _parse_self_rejection_rows(request.form)
            entry.qty_variance = entry.actual_quantity - entry.planned_quantity
            entry.qty_variance_percent = (entry.qty_variance / entry.planned_quantity * 100) if entry.planned_quantity > 0 else 0.0
            total_runtime_mins = float(request.form.get('total_time_taken_minutes') or 0)
            total_ideal_mins = float(request.form.get('total_ideal_time_minutes') or 0)
            if total_ideal_mins > total_runtime_mins:
                flash('Total Ideal Time (Mins) cannot be more than Total Available Machine Hours. Please review both fields.', 'danger')
                return redirect(url_for('web.edit_entry', entry_id=entry_id))
            
            entry.self_rejection_qty = self_rejection_qty
            entry.self_rejection_weight_per_pcs = self_rejection_weight_per_pcs
            entry.machining_scrap_weight_kg = machining_scrap_weight_kg
            entry.ideal_cycle_time = _safe_float(request.form.get('ideal_cycle_time'))
            entry.total_time_taken_minutes = int(total_runtime_mins)
            entry.total_ideal_time_minutes = total_ideal_mins
            entry.downtime_minutes = _safe_int(request.form.get('total_planned_downtime'))
            entry.remarks = request.form.get('remarks')

            
            entry.updated_at = datetime.now(timezone.utc)
            
            # Update operations
            ProductionEntryOperation.query.filter_by(production_entry_id=entry.id).delete()
            op_type_ids = request.form.getlist('operation_type_id[]')
            for op_id in op_type_ids:
                if op_id:
                    op_mapping = ProductionEntryOperation(
                        production_entry_id=entry.id,
                        operation_type_id=_safe_int(op_id)
                    )
                    db.session.add(op_mapping)
            
            # Update operators
            ProductionEntryOperator.query.filter_by(production_entry_id=entry.id).delete()
            op_ids = request.form.getlist('operator_id[]')
            op_starts = request.form.getlist('op_start_time[]')
            op_ends = request.form.getlist('op_end_time[]')
            
            for i in range(len(op_ids)):
                if op_ids[i]:
                    op_start = datetime.fromisoformat(op_starts[i]) if i < len(op_starts) and op_starts[i] else entry.start_time
                    op_end = datetime.fromisoformat(op_ends[i]) if i < len(op_ends) and op_ends[i] else entry.end_time
                    if op_start >= op_end:
                        raise ValueError(f'Operator row #{i + 1}: Start Time must be earlier than End Time.')
                    mapping = ProductionEntryOperator(
                        production_entry_id=entry.id,
                        operator_emp_id=_safe_int(op_ids[i]),
                        start_time=op_start,
                        end_time=op_end
                    )
                    db.session.add(mapping)
            
            # Update supervisors
            ProductionEntrySupervisor.query.filter_by(production_entry_id=entry.id).delete()
            sup_ids = request.form.getlist('supervisor_id[]')
            sup_starts = request.form.getlist('sup_start_time[]')
            sup_ends = request.form.getlist('sup_end_time[]')
            
            for i in range(len(sup_ids)):
                if sup_ids[i]:
                    sup_start = datetime.fromisoformat(sup_starts[i]) if i < len(sup_starts) and sup_starts[i] else entry.start_time
                    sup_end = datetime.fromisoformat(sup_ends[i]) if i < len(sup_ends) and sup_ends[i] else entry.end_time
                    if sup_start >= sup_end:
                        raise ValueError(f'Supervisor row #{i + 1}: Start Time must be earlier than End Time.')
                    mapping = ProductionEntrySupervisor(
                        production_entry_id=entry.id,
                        supervisor_emp_id=_safe_int(sup_ids[i]),
                        start_time=sup_start,
                        end_time=sup_end
                    )
                    db.session.add(mapping)
            
            # Update planned downtime using the rows posted from the edit modal.
            # In edit mode, the visible downtime rows are the source of truth.
            ProductionPlannedDowntime.query.filter_by(production_entry_id=entry.id).delete()
            ProductionSelfRejectionDefect.query.filter_by(production_entry_id=entry.id).delete()

            dt_reason_ids = request.form.getlist('downtime_reason_id[]')
            dt_durations = request.form.getlist('downtime_minutes[]')
            for i in range(len(dt_reason_ids)):
                if dt_reason_ids[i] and dt_durations[i]:
                    dt_record = ProductionPlannedDowntime(
                        production_entry_id=entry.id,
                        reason_id=_safe_int(dt_reason_ids[i]),
                        duration_minutes=_safe_int(dt_durations[i])
                    )
                    db.session.add(dt_record)

            for self_row in self_rejection_rows:
                db.session.add(ProductionSelfRejectionDefect(
                    production_entry_id=entry.id,
                    defect_type_id=self_row['defect_type_id'],
                    reject_qty=self_row['reject_qty']
                ))
                
            db.session.commit()
            flash('Production entry updated successfully!', 'success')
            return redirect(url_for('web.view_entry', entry_id=entry_id))
            
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            return redirect(url_for('web.edit_entry', entry_id=entry_id))
        except Exception as e:
            logger.error(f'Error editing entry: {str(e)}')
            db.session.rollback()
            return render_template('error.html', error=str(e)), 500

# ==================== AUTHENTICATION ====================

@web_bp.route('/login', methods=['GET', 'POST'])
def login():
    debug_enabled = os.getenv('MS_LOGIN_DEBUG', '').strip().lower() in {'1', 'true', 'yes'}
    if request.method == 'GET':
        debug_payload = session.pop('login_debug', None) if debug_enabled else None
        return render_template('login.html', login_debug=debug_payload, login_debug_enabled=debug_enabled)
    
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    
    if not email or not password:
        flash('Please provide email and password', 'error')
        return redirect(url_for('web.login'))
    
    # Simple hash check matching MOA logic
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    
    # Direct SQL query since UserLogin might not be in our limited models.py yet
    from sqlalchemy import text
    try:
        debug = {
            'email': email,
            'user_found': False,
            'is_active': None,
            'password_match': None,
            'password_hash_type': None,
            'module_access': None,
            'role_allowed': None,
            'fail_reason': None
        }

        user_query = text("""
            SELECT u.user_id, e.emp_name, e.emp_code, u.email_login, u.role_id, u.is_active, u.password_hash
            FROM user_login u
            LEFT JOIN emp_master e ON u.emp_id = e.emp_id
            WHERE u.email_login = :email
        """)
        row = db.session.execute(user_query, {'email': email}).fetchone()

        if not row:
            debug['fail_reason'] = 'User not found for email'
            logger.warning(f'Login failed: user not found (email={email})')
            if debug_enabled:
                session['login_debug'] = debug
            flash('Invalid email or password', 'error')
            return redirect(url_for('web.login'))

        debug['user_found'] = True
        debug['is_active'] = bool(row.is_active)

        if not row.is_active:
            debug['fail_reason'] = 'User is inactive'
            logger.warning(f'Login failed: inactive user (email={email}, user_id={row.user_id})')
            if debug_enabled:
                session['login_debug'] = debug
            flash('Invalid email or password', 'error')
            return redirect(url_for('web.login'))

        stored_hash = row.password_hash or ''
        # Support both SHA-256 hex (legacy) and Werkzeug hashes (scrypt:/pbkdf2:),
        # since admin.py can reset in either format depending on env.
        if isinstance(stored_hash, str) and stored_hash.startswith(('scrypt:', 'pbkdf2:')):
            debug['password_hash_type'] = stored_hash.split(':', 1)[0]
            debug['password_match'] = bool(check_password_hash(stored_hash, password))
        else:
            debug['password_hash_type'] = 'sha256'
            debug['password_match'] = (stored_hash == pw_hash)
        if not debug['password_match']:
            debug['fail_reason'] = 'Password hash mismatch'
            logger.warning(f'Login failed: bad password (email={email}, user_id={row.user_id})')
            if debug_enabled:
                session['login_debug'] = debug
            flash('Invalid email or password', 'error')
            return redirect(url_for('web.login'))

        debug['module_access'] = bool(_has_module_access(row.user_id))
        if not debug['module_access']:
            debug['fail_reason'] = 'No module access (user_module_access)'
            logger.warning(f'Login blocked: no module access (email={email}, user_id={row.user_id})')
            if debug_enabled:
                session['login_debug'] = debug
            flash('You do not have access to the Machine Shop module.', 'error')
            return redirect(url_for('web.login'))

        debug['role_allowed'] = bool(_has_role_access(row.role_id, allow_master_data=False))
        if not debug['role_allowed']:
            debug['fail_reason'] = 'Role not allowed for module'
            logger.warning(f'Login blocked: role not allowed (email={email}, user_id={row.user_id}, role_id={row.role_id})')
            if debug_enabled:
                session['login_debug'] = debug
            flash('Your role does not have access to the Machine Shop module.', 'error')
            return redirect(url_for('web.login'))

        # Successful login
        if debug_enabled:
            debug['fail_reason'] = None
            session.pop('login_debug', None)

        session['user_id'] = row.user_id
        session['user'] = {
            'name': row.emp_name,
            'email': row.email_login,
            'role_id': row.role_id,
            'emp_code': str(row.emp_code) if row.emp_code else None
        }
        next_url = request.args.get('next')
        return redirect(next_url or url_for('web.index'))
            
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        flash('An error occurred during login', 'error')
        return redirect(url_for('web.login'))

@web_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('web.login'))
