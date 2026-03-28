"""
Rejection Management Routes
Handles rejection form submission and records display with analytics
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, flash, send_file
from models import db, DailyRejection, Customer, MachineShed, Machine, EmpMaster, DefectType, RejectionDefect, DailyRejectionSupervisor, ProductionEntry, OperationType, ProductionEntryOperation, ProductionEntryOperator, ProductionEntrySupervisor, SectionMaster, SectionCutLength, ReworkLog
from datetime import datetime, timedelta
from sqlalchemy import func, extract, or_, and_
from sqlalchemy.orm import joinedload
from utils.auth import login_required, rejection_form_required, rejection_records_required
import logging
from io import BytesIO
import pandas as pd

logger = logging.getLogger(__name__)
rejection_bp = Blueprint('rejection', __name__)


def _parse_local_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _default_rejection_window():
    now = datetime.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now


def _resolve_rejection_window(start_value, end_value):
    default_start, default_end = _default_rejection_window()
    start_dt = _parse_local_datetime(start_value) or default_start
    end_dt = _parse_local_datetime(end_value) or default_end
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    return start_dt, end_dt


def _apply_rejection_filters(query):
    start_dt, end_dt = _resolve_rejection_window(
        request.args.get('start_date'),
        request.args.get('end_date')
    )
    query = query.filter(or_(
        and_(DailyRejection.rejection_datetime.isnot(None), DailyRejection.rejection_datetime >= start_dt),
        and_(DailyRejection.rejection_datetime.is_(None), DailyRejection.rejection_date >= start_dt.date())
    ))
    query = query.filter(or_(
        and_(DailyRejection.rejection_datetime.isnot(None), DailyRejection.rejection_datetime <= end_dt),
        and_(DailyRejection.rejection_datetime.is_(None), DailyRejection.rejection_date <= end_dt.date())
    ))

    entry_no_filter = (request.args.get('entry_no') or '').strip()
    if entry_no_filter:
        query = query.join(ProductionEntry, ProductionEntry.id == DailyRejection.production_entry_id)
        query = query.filter(ProductionEntry.entry_no.ilike(f"%{entry_no_filter}%"))

    customer_id = request.args.get('customer_id', type=int)
    if customer_id:
        query = query.filter(DailyRejection.customer_id == customer_id)

    shed_id = request.args.get('shed_id', type=int)
    if shed_id:
        query = query.join(ProductionEntry, ProductionEntry.id == DailyRejection.production_entry_id)
        query = query.join(Machine, Machine.id == ProductionEntry.machine_id)
        query = query.filter(Machine.shed_id == shed_id)

    section_filter = (request.args.get('section_number') or request.args.get('section') or '').strip()
    if section_filter:
        query = query.filter(DailyRejection.section_number.ilike(f"%{section_filter}%"))

    cutlength_filter = (request.args.get('cut_length') or request.args.get('length') or '').strip()
    if cutlength_filter:
        try:
            query = query.filter(DailyRejection.length == float(cutlength_filter))
        except ValueError:
            pass

    month = (request.args.get('month') or '').strip()
    if month:
        query = query.filter(DailyRejection.month == month)

    shift = (request.args.get('shift') or '').strip()
    if shift:
        query = query.filter(DailyRejection.shift.ilike(f"%{shift}%"))

    defect_type_id = request.args.get('defect_type_id', type=int)
    if defect_type_id:
        query = query.join(RejectionDefect, RejectionDefect.rejection_id == DailyRejection.id)
        query = query.filter(RejectionDefect.defect_type_id == defect_type_id).distinct()

    operation_type_id = request.args.get('operation_type_id', type=int)
    if operation_type_id:
        query = query.join(ProductionEntry, ProductionEntry.id == DailyRejection.production_entry_id)
        query = query.join(ProductionEntryOperation, ProductionEntryOperation.production_entry_id == ProductionEntry.id)
        query = query.filter(ProductionEntryOperation.operation_type_id == operation_type_id).distinct()

    reason = (request.args.get('reason') or '').strip()
    if reason:
        query = query.filter(DailyRejection.rejection_reason.ilike(f"%{reason}%"))

    emp_code = (request.args.get('emp_code') or '').strip()
    if emp_code:
        matching_emp_ids = [
            row[0] for row in db.session.query(EmpMaster.emp_id)
            .filter(EmpMaster.emp_code.ilike(f"%{emp_code}%"))
            .all()
        ]
        if not matching_emp_ids:
            query = query.filter(DailyRejection.id == -1)
        else:
            supervisor_rejection_ids = db.session.query(DailyRejectionSupervisor.rejection_id).filter(
                DailyRejectionSupervisor.supervisor_emp_id.in_(matching_emp_ids)
            )
            linked_prod_ids = db.session.query(ProductionEntry.id).filter(or_(
                ProductionEntry.operator_emp_id.in_(matching_emp_ids),
                ProductionEntry.id.in_(
                    db.session.query(ProductionEntryOperator.production_entry_id).filter(
                        ProductionEntryOperator.operator_emp_id.in_(matching_emp_ids)
                    )
                ),
                ProductionEntry.id.in_(
                    db.session.query(ProductionEntrySupervisor.production_entry_id).filter(
                        ProductionEntrySupervisor.supervisor_emp_id.in_(matching_emp_ids)
                    )
                )
            ))
            query = query.filter(or_(
                DailyRejection.operator_emp_id.in_(matching_emp_ids),
                DailyRejection.id.in_(supervisor_rejection_ids),
                DailyRejection.production_entry_id.in_(linked_prod_ids)
            ))

    quality_status = (request.args.get('quality_status') or '').strip().lower()
    if quality_status == 'completed':
        # Linked to a production entry (inspection done against a production record)
        query = query.filter(DailyRejection.production_entry_id.isnot(None))
    elif quality_status == 'pending':
        # Standalone rejection entries not linked to a production record
        query = query.filter(DailyRejection.production_entry_id.is_(None))

    return query, start_dt, end_dt


def _apply_rejection_dimension_filters(query, *, include_month=False):
    entry_no_filter = (request.args.get('entry_no') or '').strip()
    if entry_no_filter:
        query = query.join(ProductionEntry, ProductionEntry.id == DailyRejection.production_entry_id)
        query = query.filter(ProductionEntry.entry_no.ilike(f"%{entry_no_filter}%"))

    customer_id = request.args.get('customer_id', type=int)
    if customer_id:
        query = query.filter(DailyRejection.customer_id == customer_id)

    section_filter = (request.args.get('section_number') or request.args.get('section') or '').strip()
    if section_filter:
        query = query.filter(DailyRejection.section_number.ilike(f"%{section_filter}%"))

    cutlength_filter = (request.args.get('cut_length') or request.args.get('length') or '').strip()
    if cutlength_filter:
        try:
            query = query.filter(DailyRejection.length == float(cutlength_filter))
        except ValueError:
            pass

    if include_month:
        month = (request.args.get('month') or '').strip()
        if month:
            query = query.filter(DailyRejection.month == month)

    shift = (request.args.get('shift') or '').strip()
    if shift:
        query = query.filter(DailyRejection.shift.ilike(f"%{shift}%"))

    defect_type_id = request.args.get('defect_type_id', type=int)
    if defect_type_id:
        query = query.join(RejectionDefect, RejectionDefect.rejection_id == DailyRejection.id)
        query = query.filter(RejectionDefect.defect_type_id == defect_type_id).distinct()

    operation_type_id = request.args.get('operation_type_id', type=int)
    if operation_type_id:
        query = query.join(ProductionEntry, ProductionEntry.id == DailyRejection.production_entry_id)
        query = query.join(ProductionEntryOperation, ProductionEntryOperation.production_entry_id == ProductionEntry.id)
        query = query.filter(ProductionEntryOperation.operation_type_id == operation_type_id).distinct()

    reason = (request.args.get('reason') or '').strip()
    if reason:
        query = query.filter(DailyRejection.rejection_reason.ilike(f"%{reason}%"))

    emp_code = (request.args.get('emp_code') or '').strip()
    if emp_code:
        matching_emp_ids = [
            row[0] for row in db.session.query(EmpMaster.emp_id)
            .filter(EmpMaster.emp_code.ilike(f"%{emp_code}%"))
            .all()
        ]
        if not matching_emp_ids:
            query = query.filter(DailyRejection.id == -1)
        else:
            supervisor_rejection_ids = db.session.query(DailyRejectionSupervisor.rejection_id).filter(
                DailyRejectionSupervisor.supervisor_emp_id.in_(matching_emp_ids)
            )
            linked_prod_ids = db.session.query(ProductionEntry.id).filter(or_(
                ProductionEntry.operator_emp_id.in_(matching_emp_ids),
                ProductionEntry.id.in_(
                    db.session.query(ProductionEntryOperator.production_entry_id).filter(
                        ProductionEntryOperator.operator_emp_id.in_(matching_emp_ids)
                    )
                ),
                ProductionEntry.id.in_(
                    db.session.query(ProductionEntrySupervisor.production_entry_id).filter(
                        ProductionEntrySupervisor.supervisor_emp_id.in_(matching_emp_ids)
                    )
                )
            ))
            query = query.filter(or_(
                DailyRejection.operator_emp_id.in_(matching_emp_ids),
                DailyRejection.id.in_(supervisor_rejection_ids),
                DailyRejection.production_entry_id.in_(linked_prod_ids)
            ))

    quality_status = (request.args.get('quality_status') or '').strip().lower()
    if quality_status == 'completed':
        query = query.filter(DailyRejection.production_entry_id.isnot(None))
    elif quality_status == 'pending':
        query = query.filter(DailyRejection.production_entry_id.is_(None))

    return query


@rejection_bp.route('/form', methods=['GET', 'POST'])
@rejection_form_required
def rejection_form():
    """
    Rejection entry form
    GET: Show form with master data, potentially pre-filled from production_id
    POST: Process form submission
    """
    prod_id = request.args.get('production_id', type=int)
    production_entry = None
    if prod_id:
        from models import ProductionEntry
        production_entry = ProductionEntry.query.get(prod_id)

    if request.method == 'GET':
        # Fetch all active customers for dropdown
        customers = Customer.query.filter_by(status='Active').order_by(Customer.customer_name).all()
        # Fetch all active defect types
        defect_types = DefectType.query.filter_by(is_active=True).order_by(DefectType.defect_name).all()
        
        return render_template('rejection_form.html', 
                             customers=customers, 
                             defect_types=defect_types,
                             production_entry=production_entry,
                             now=datetime.now())
    
    elif request.method == 'POST':
        try:
            production_entry_id = int(request.form.get('production_entry_id')) if request.form.get('production_entry_id') else None
            linked_production = ProductionEntry.query.get(production_entry_id) if production_entry_id else None

            # Parse datetime and extract month
            reject_dt_str = request.form.get('rejection_datetime')
            if reject_dt_str:
                rejection_datetime = datetime.strptime(reject_dt_str, '%Y-%m-%dT%H:%M')
            else:
                rejection_datetime = datetime.now()
                
            month = rejection_datetime.strftime('%Y-%m')
            
            weight_per_pcs = request.form.get('weight_per_pcs')
            if linked_production and not weight_per_pcs:
                weight_per_pcs = linked_production.self_rejection_weight_per_pcs or 0
            weight_per_pcs = float(weight_per_pcs or 0)

            # Create rejection entry
            rejection = DailyRejection(
                production_entry_id=production_entry_id,
                rejection_date=rejection_datetime.date(),
                rejection_datetime=rejection_datetime,
                shift=request.form.get('shift'),
                month=month,
                customer_id=int(request.form['customer_id']),
                section_number=request.form['section_number'],
                length=float(request.form['length']) if request.form.get('length') else None,
                total_parts_inspected_qty=int(request.form.get('total_parts_inspected_qty', 0)),
                rj_pcs=int(request.form.get('rj_pcs_total', 0)),
                weight_per_pcs=weight_per_pcs,
                rejection_reason=request.form.get('rejection_reason', 'Multi-Defect'),
                operator_emp_id=int(request.form.getlist('supervisor_ids')[0]) if request.form.getlist('supervisor_ids') else 1,
                created_by=session.get('user', {}).get('email', 'system')
            )
            
            # Compute rejection weight
            rejection.compute_rj_weight()
            
            db.session.add(rejection)
            db.session.flush() 
            
            # Handle multiple Defects
            defect_type_ids = request.form.getlist('defect_type_id[]')
            defect_counts = request.form.getlist('defect_count[]')
            rework_defect_type_ids = request.form.getlist('rework_defect_type_id[]')
            rework_qtys = request.form.getlist('rework_qty[]')
            rework_remarks = (request.form.get('rework_remarks') or '').strip()
            total_defect_count = 0
            total_logged_rework = 0
            rework_logs_to_create = []

            raw_defect_rows = []
            for i in range(len(defect_type_ids)):
                defect_type_id = (defect_type_ids[i] if i < len(defect_type_ids) else '') or ''
                defect_count_raw = (defect_counts[i] if i < len(defect_counts) else '') or ''
                defect_count = int(defect_count_raw) if str(defect_count_raw).strip() else 0

                if not defect_type_id and defect_count == 0:
                    continue
                if not defect_type_id and defect_count > 0:
                    raise ValueError(f"Rejection row #{i + 1}: defect type is required when defect qty is entered.")
                if defect_type_id and defect_count <= 0:
                    raise ValueError(f"Rejection row #{i + 1}: defect qty must be greater than 0 when a defect type is selected.")

                raw_defect_rows.append((i, int(defect_type_id), defect_count))

            rework_totals_by_defect = {}
            for i in range(max(len(rework_defect_type_ids), len(rework_qtys))):
                defect_type_id = (rework_defect_type_ids[i] if i < len(rework_defect_type_ids) else '') or ''
                rework_qty_raw = (rework_qtys[i] if i < len(rework_qtys) else '') or ''
                rework_qty = int(rework_qty_raw) if str(rework_qty_raw).strip() else 0

                if not defect_type_id and rework_qty == 0:
                    continue
                if not defect_type_id and rework_qty > 0:
                    raise ValueError(f"Rework row #{i + 1}: defect type is required when rework qty is entered.")
                if rework_qty < 0:
                    raise ValueError(f"Rework row #{i + 1}: rework qty cannot be negative.")

                defect_type_id = int(defect_type_id)
                rework_totals_by_defect[defect_type_id] = rework_totals_by_defect.get(defect_type_id, 0) + rework_qty

            if rework_totals_by_defect and not linked_production:
                raise ValueError('Rework Summary can only be used when the rejection is linked to a production entry.')

            for _, defect_type_id, count in raw_defect_rows:
                total_defect_count += count
                rj_defect = RejectionDefect(
                    rejection_id=rejection.id,
                    defect_type_id=defect_type_id,
                    defect_count=count
                )
                db.session.add(rj_defect)
             
            # Re-validate sum of defects against total inspected
            if total_defect_count > rejection.total_parts_inspected_qty:
                raise ValueError(f"Total defect count ({total_defect_count}) cannot exceed total parts inspected ({rejection.total_parts_inspected_qty})")

            total_logged_rework = sum(rework_totals_by_defect.values())
            if (total_defect_count + total_logged_rework) > rejection.total_parts_inspected_qty:
                raise ValueError(
                    f"Total rejected qty + total rework qty ({total_defect_count + total_logged_rework}) "
                    f"cannot exceed total parts inspected ({rejection.total_parts_inspected_qty})"
                )

            # Rejection form stores gross rejection. Rework logged here is tracked separately.
            rejection.rj_pcs = total_defect_count
            rejection.compute_rj_weight()

            if linked_production and linked_production.rework_qty is None:
                linked_production.rework_qty = 0

            if linked_production and rework_totals_by_defect:
                for defect_type_id, rework_qty in rework_totals_by_defect.items():
                    if rework_qty <= 0:
                        continue
                    log_remarks = f"Rework recorded from rejection form. Reworked qty: {rework_qty}. Gross rejection remains unchanged until explicit log rework action."
                    if rework_remarks:
                        log_remarks = f"{log_remarks} Remarks: {rework_remarks}"
                    rework_logs_to_create.append(ReworkLog(
                        production_entry_id=linked_production.id,
                        rejection_id=rejection.id,
                        defect_type_id=defect_type_id,
                        rework_qty=rework_qty,
                        remarks=log_remarks,
                        created_by=session.get('user', {}).get('email', 'system')
                    ))
                linked_production.rework_qty = (linked_production.rework_qty or 0) + total_logged_rework
                for rework_log in rework_logs_to_create:
                    db.session.add(rework_log)

            # Handle multiple QC Supervisors with times
            supervisor_ids = request.form.getlist('supervisor_ids[]')
            sup_start_times = request.form.getlist('sup_start_time[]')
            sup_end_times = request.form.getlist('sup_end_time[]')
            
            for i in range(len(supervisor_ids)):
                if supervisor_ids[i]:
                    st = datetime.strptime(sup_start_times[i], '%Y-%m-%dT%H:%M') if i < len(sup_start_times) and sup_start_times[i] else None
                    et = datetime.strptime(sup_end_times[i], '%Y-%m-%dT%H:%M') if i < len(sup_end_times) and sup_end_times[i] else None
                    if st and et and st >= et:
                        raise ValueError(f'Quality Supervisor row #{i + 1}: Start Datetime must be earlier than End Datetime.')
                    sup_entry = DailyRejectionSupervisor(
                        rejection_id=rejection.id,
                        supervisor_emp_id=int(supervisor_ids[i]),
                        start_time=st,
                        end_time=et
                    )
                    db.session.add(sup_entry)
            
            db.session.commit()
            
            flash('Rejection record submitted successfully!', 'success')
            return redirect(url_for('rejection.rejection_records'))
            
        except Exception as e:
            logger.error(f'Error saving rejection entry: {str(e)}')
            db.session.rollback()
            flash(f'Error submitting rejection: {str(e)}', 'error')
            return redirect(url_for('rejection.rejection_form', production_id=prod_id))


@rejection_bp.route('/records')
@rejection_records_required
def rejection_records():
    """Display rejection records with filters and analytics"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Build query with filters
    query = DailyRejection.query
    query, start_dt, end_dt = _apply_rejection_filters(query)
    section_filter = (request.args.get('section_number') or request.args.get('section') or '').strip()
    
    # Order by date descending
    query = query.order_by(DailyRejection.rejection_date.desc())
    
    # Paginate results
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get filter options
    sheds = MachineShed.query.filter_by(status='Active').order_by(MachineShed.shed_name).all()
    customers = Customer.query.filter_by(status='Active').order_by(Customer.customer_name).all()
    defect_types = DefectType.query.filter_by(is_active=True).order_by(DefectType.defect_name).all()
    operations = OperationType.query.order_by(OperationType.operation_name).all()
    selected_customer_id = request.args.get('customer_id', type=int)
    sections = SectionMaster.query.filter_by(customer_id=selected_customer_id, status='Active').order_by(SectionMaster.section_number).all() if selected_customer_id else []
    selected_section_number = section_filter
    selected_section = next((s for s in sections if (s.section_number or '').strip() == selected_section_number), None)
    cut_lengths = SectionCutLength.query.filter_by(section_id=selected_section.id, status='Active').order_by(SectionCutLength.cut_length).all() if selected_section else []
    
    # Get unique months for filter
    months = db.session.query(DailyRejection.month).distinct().order_by(DailyRejection.month.desc()).all()
    months = [m[0] for m in months]
    
    return render_template('rejection_records.html',
                         rejections=paginated.items,
                         pagination=paginated,
                         sheds=sheds,
                         customers=customers,
                         months=months,
                         defect_types=defect_types,
                         operations=operations,
                         sections=sections,
                         cut_lengths=cut_lengths,
                         start_datetime_value=start_dt.strftime('%Y-%m-%dT%H:%M'),
                         end_datetime_value=end_dt.strftime('%Y-%m-%dT%H:%M'))


@rejection_bp.route('/records/export')
@rejection_records_required
def export_rejection_records():
    """Export filtered rejection records to Excel."""
    query = DailyRejection.query.options(joinedload(DailyRejection.production_entry_obj))
    query, _, _ = _apply_rejection_filters(query)

    records = query.order_by(DailyRejection.rejection_date.desc(), DailyRejection.id.desc()).all()

    rows = []
    for r in records:
        defects = '; '.join([
            f"{d.defect_type.defect_name if d.defect_type else 'Defect'}: {d.defect_count}"
            for d in r.defects
        ])
        rework_history_notes = []
        supervisors = '; '.join([
            f"{s.supervisor_info.emp_name if s.supervisor_info else ''} ({s.supervisor_info.emp_code if s.supervisor_info else ''}) [{s.start_time} - {s.end_time}]"
            for s in r.supervisors
        ])
        rej_pct = ((r.rj_pcs or 0) / (r.total_parts_inspected_qty or 1) * 100) if (r.total_parts_inspected_qty or 0) > 0 else 0
        quality_score = 100 - rej_pct if (r.total_parts_inspected_qty or 0) > 0 else 0

        pe = r.production_entry_obj
        rework_qty = pe.rework_qty if pe else 0
        rework_summary = {}
        self_rejection_details = ''
        total_self_rejection_kg = None
        total_self_rejection_all_kg = None
        if pe:
            total_self_rejection_kg = round((pe.self_rejection_weight_per_pcs or 0) * (pe.self_rejection_qty or 0), 3)
            total_self_rejection_all_kg = round(total_self_rejection_kg + (pe.machining_scrap_weight_kg or 0), 3)
            for log in getattr(pe, 'rework_logs', []):
                if log.rejection_id != r.id:
                    continue
                label = log.defect_type.defect_name if log.defect_type else f"Defect-{log.defect_type_id}"
                rework_summary[label] = rework_summary.get(label, 0) + (log.rework_qty or 0)
                if log.remarks:
                    rework_history_notes.append(log.remarks)
            self_rejection_details = '; '.join([
                f"{d.defect_type.defect_name if d.defect_type else 'Defect'}: {d.reject_qty or 0} pcs"
                for d in getattr(pe, 'self_rejection_defects', [])
            ])
        rework_details = '; '.join(f"{label}: reworked {qty} pcs" for label, qty in rework_summary.items())
        total_rework_weight = round((r.weight_per_pcs or 0) * (rework_qty or 0), 3) if rework_qty else 0
        rows.append({
            'Rejection ID': r.id,
            'Production Entry ID': r.production_entry_id,
            'Production Entry No': pe.entry_no if pe else None,
            'Rejection Date': r.rejection_date,
            'Rejection Datetime': r.rejection_datetime,
            'Shift': r.shift,
            'Month': r.month,
            'Customer': r.customer.customer_name if r.customer else None,
            'Section Number': r.section_number,
            'Length': r.length,
            'Total Parts Inspected': r.total_parts_inspected_qty,
            'Rejected Pieces': r.rj_pcs,
            'Rejection % (Auto)': round(rej_pct, 2),
            'Quality Score % (Auto)': round(quality_score, 2),
            'Weight Per Piece': r.weight_per_pcs,
            'Rejected Weight (Auto)': r.rj_weight,
            'Defect Types': '; '.join(sorted(set([d.defect_type.defect_name if d.defect_type else 'Defect' for d in r.defects]))),
            'Rejection Reason': r.rejection_reason,
            'Quality Remarks': r.rejection_reason,
            'Operator': r.operator.emp_name if r.operator else None,
            'Operator Code': r.operator.emp_code if r.operator else None,
            'Defect Breakdown': defects,
            'Supervisors (with time)': supervisors,
            'Linked Prod Shed': pe.machine.shed.shed_name if pe and pe.machine and pe.machine.shed else None,
            'Linked Prod Machine': pe.machine.machine_name if pe and pe.machine else None,
            'Linked Prod Machine Type': pe.machine.machine_type if pe and pe.machine else None,
            'Linked Prod Start Time': pe.start_time if pe else None,
            'Linked Prod End Time': pe.end_time if pe else None,
            'Linked Prod Operations / Process': '; '.join([
                op.operation_type.operation_name if op.operation_type else ''
                for op in pe.operations
            ]) if pe else None,
            'Linked Prod Planned Qty': pe.planned_quantity if pe else None,
            'Linked Prod Actual Qty': pe.actual_quantity if pe else None,
            'Linked Prod Total Self Rejection PCS': pe.self_rejection_qty if pe else None,
            'Linked Prod Weight/PC (kg)': pe.self_rejection_weight_per_pcs if pe else None,
            'Linked Prod Total Self Rejection KGs (Auto)': total_self_rejection_kg,
            'Linked Prod Total Machining Scrap (kg)': pe.machining_scrap_weight_kg if pe else None,
            'Linked Prod Total Self Rejection (All) KGs (Auto)': total_self_rejection_all_kg,
            'Linked Prod Self Rejection Details': self_rejection_details,
            'Linked Prod Total OK (Auto)': pe.total_ok_quantity if pe else None,
            'Linked Prod Total OK Note': 'total_ok_quantity = actual_quantity - current remaining quality rejects. Rework logs reduce the remaining rejection balance, so rework is already reflected and is not added again.',
            'Linked Prod Efficiency % (Auto)': round(pe.efficiency, 2) if pe else None,
            'Total Rework Qty (Logged)': rework_qty,
            'Total Rework Weight (kg) (Auto)': total_rework_weight,
            'Rework Details (Defect-wise Logged Qty)': rework_details,
            'Rework Remarks': ' | '.join(rework_history_notes),
            'Rework Logic Note': 'Rejection form stores gross rejection and rework separately. Remaining reject balance changes only when explicit log rework action reduces rejection counts.',
            'Created By': r.created_by,
            'Created At': r.created_at,
            'Updated At': r.updated_at
        })

    df = pd.DataFrame(rows)
    output = BytesIO()
    df.to_excel(output, index=False, sheet_name='Rejection Records')
    output.seek(0)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(
        output,
        as_attachment=True,
        download_name=f'rejection_records_export_{ts}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@rejection_bp.route('/api/employee/<emp_code>')
@login_required
def get_employee_by_code(emp_code):
    """API endpoint to fetch employee details by employee code"""
    try:
        employee = EmpMaster.query.filter(
            EmpMaster.emp_code.ilike(f"%{emp_code.strip()}%"), 
            EmpMaster.status == 'Active'
        ).first()
        
        if employee:
            return jsonify({
                'success': True,
                'emp_id': employee.emp_id,
                'emp_code': employee.emp_code,
                'emp_name': employee.emp_name,
                'designation': employee.designation
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Employee not found or inactive'
            }), 404
            
    except Exception as e:
        logger.error(f'Error fetching employee: {str(e)}')
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@rejection_bp.route('/api/rejection-detail/<int:rejection_id>')
@login_required
def get_rejection_detail(rejection_id):
    """API endpoint to fetch full rejection details for the unified record modal"""
    try:
        rejection = DailyRejection.query.get_or_404(rejection_id)
        
        # Format rejection data
        rj_data = {
            'id': rejection.id,
            'rejection_datetime': rejection.rejection_datetime.isoformat(),
            'total_parts_inspected_qty': rejection.total_parts_inspected_qty,
            'rj_pcs': rejection.rj_pcs,
            'rj_weight': rejection.rj_weight,
            'weight_per_pcs': rejection.weight_per_pcs,
            'rejection_reason': rejection.rejection_reason,
            'customer_name': rejection.customer.customer_name,
            'section_number': rejection.section_number,
            'length': rejection.length,
            'supervisors': [{
                'name': s.supervisor_info.emp_name,
                'code': s.supervisor_info.emp_code,
                'start_time': s.start_time.strftime('%H:%M') if s.start_time else None,
                'end_time': s.end_time.strftime('%H:%M') if s.end_time else None
            } for s in rejection.supervisors],
            'defects': [{
                'id': d.id,
                'defect_type_id': d.defect_type_id,
                'name': d.defect_type.defect_name,
                'category': d.defect_type.category,
                'count': d.defect_count
            } for d in rejection.defects]
        }
        
        # Link to production data if exists
        prod_data = None
        if rejection.production_entry_id:
            prod = ProductionEntry.query.get(rejection.production_entry_id)
            if prod:
                rework_map = {}
                rework_history = []
                for log in prod.rework_logs:
                    if log.rejection_id != rejection.id:
                        continue
                    label = log.defect_type.defect_name if log.defect_type else f'Defect-{log.defect_type_id}'
                    if label not in rework_map:
                        rework_map[label] = {
                            'defect_type_id': log.defect_type_id,
                            'defect_type': label,
                            'rework_qty': 0
                        }
                    rework_map[label]['rework_qty'] += (log.rework_qty or 0)
                    rework_history.append({
                        'defect_type_id': log.defect_type_id,
                        'defect_type': label,
                        'rework_qty': log.rework_qty,
                        'remarks': log.remarks,
                        'created_at': log.created_at.isoformat() if log.created_at else None,
                        'created_by': log.created_by
                    })
                rejection_rework_qty = sum(item['rework_qty'] for item in rework_map.values())
                prod_data = {
                    'id': prod.id,
                    'entry_no': prod.entry_no,
                    'production_date': prod.production_date.strftime('%Y-%m-%d'),
                    'shift': prod.shift,
                    'machine_name': prod.machine.machine_name,
                    'actual_quantity': prod.actual_quantity,
                    'rework_qty': rejection_rework_qty,
                    'rework_weight': round((rejection.weight_per_pcs or 0) * rejection_rework_qty, 3),
                    'total_ok': prod.total_ok_quantity,
                    'total_rework_qty': rejection_rework_qty,
                    'rework_details': list(rework_map.values()),
                    'rework_history': rework_history
                }
        
        return jsonify({
            'success': True,
            'rejection': rj_data,
            'production': prod_data
        }), 200
        
    except Exception as e:
        logger.error(f'Error fetching rejection detail: {str(e)}')
        return jsonify({'error': str(e)}), 500


@rejection_bp.route('/api/log-rework', methods=['POST'])
@login_required
def log_rework():
    """API endpoint to log reworking of rejected pieces"""
    try:
        prod_id = request.form.get('production_id', type=int)
        rework_qty = request.form.get('rework_qty', type=int)
        rejection_id = request.form.get('rejection_id', type=int)
        defect_type_id = request.form.get('defect_type_id', type=int)
        remarks = request.form.get('remarks')
        
        if not prod_id or not rework_qty or not rejection_id or not defect_type_id:
            return jsonify({'success': False, 'error': 'Production ID, Rejection entry, defect type and rework quantity are required'}), 400
            
        prod = ProductionEntry.query.get_or_404(prod_id)
        rejection = DailyRejection.query.get_or_404(rejection_id)
        if rejection.production_entry_id and rejection.production_entry_id != prod.id:
            return jsonify({'success': False, 'error': 'Rejection entry does not belong to the selected production record'}), 400
        
        defect_entry = RejectionDefect.query.filter_by(
            rejection_id=rejection.id,
            defect_type_id=defect_type_id
        ).first()
        if not defect_entry:
            return jsonify({'success': False, 'error': 'Selected defect type does not have rejected pieces available'}), 400

        if rework_qty > defect_entry.defect_count:
            return jsonify({'success': False, 'error': f'Rework quantity ({rework_qty}) exceeds available rejects for the selected defect ({defect_entry.defect_count})'}), 400

        if rework_qty > rejection.rj_pcs:
            return jsonify({'success': False, 'error': f'Rework quantity ({rework_qty}) exceeds remaining rejects ({rejection.rj_pcs})'}), 400
        
        # Log the rework
        prod.rework_qty = (prod.rework_qty or 0) + rework_qty
        if remarks:
            prod.remarks = f"{prod.remarks}\n[REWORK LOG]: {rework_qty} pcs reworked. {remarks}" if prod.remarks else f"[REWORK LOG]: {rework_qty} pcs reworked. {remarks}"
        defect_entry.defect_count = max(0, defect_entry.defect_count - rework_qty)
        rejection.rj_pcs = max(0, rejection.rj_pcs - rework_qty)
        rejection.compute_rj_weight()

        rework_log = ReworkLog(
            production_entry_id=prod.id,
            rejection_id=rejection.id,
            defect_type_id=defect_type_id,
            rework_qty=rework_qty,
            remarks=remarks,
            created_by=session.get('user', {}).get('email', 'system')
        )
        db.session.add(rework_log)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Rework of {rework_qty} pieces logged correctly. Remaining rejects: {rejection.rj_pcs}.'
        }), 200
        
    except Exception as e:
        logger.error(f'Error logging rework: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@rejection_bp.route('/api/analytics')
@login_required
def get_analytics():
    """API endpoint for analytics data with filters"""
    try:
        query = DailyRejection.query
        query, _, end_dt = _apply_rejection_filters(query)
        
        # Get all filtered records
        rejections = query.all()
        
        # Calculate summary metrics
        total_inspected = sum(r.total_parts_inspected_qty or 0 for r in rejections)
        total_pcs = sum(r.rj_pcs for r in rejections)
        total_weight = sum(r.rj_weight for r in rejections)
        total_records = len(rejections)
        
        rej_ids = [r.id for r in rejections] if rejections else [-1]
        
        # Rejection by customer
        customer_data = db.session.query(
            Customer.customer_name,
            func.sum(DailyRejection.rj_pcs).label('total_pcs'),
            func.sum(DailyRejection.rj_weight).label('total_weight')
        ).join(DailyRejection).filter(
            DailyRejection.id.in_(rej_ids)
        ).group_by(Customer.customer_name).all()
        
        # Rejection by defect type
        defect_type_data = db.session.query(
            DefectType.defect_name,
            func.sum(RejectionDefect.defect_count).label('total_pcs')
        ).join(RejectionDefect, RejectionDefect.defect_type_id == DefectType.id).filter(
            RejectionDefect.rejection_id.in_(rej_ids)
        ).group_by(DefectType.defect_name).all()
        
        # Trailing 6-month trend: keep dimension filters, but do not collapse to the
        # current datetime window or selected single month, otherwise the chart often
        # ends up with only one point and appears blank.
        trend_start = (end_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=155)).replace(day=1)
        trend_query = _apply_rejection_dimension_filters(DailyRejection.query, include_month=False)
        trend_query = trend_query.filter(or_(
            and_(DailyRejection.rejection_datetime.isnot(None), DailyRejection.rejection_datetime >= trend_start),
            and_(DailyRejection.rejection_datetime.is_(None), DailyRejection.rejection_date >= trend_start.date())
        ))
        trend_query = trend_query.filter(or_(
            and_(DailyRejection.rejection_datetime.isnot(None), DailyRejection.rejection_datetime <= end_dt),
            and_(DailyRejection.rejection_datetime.is_(None), DailyRejection.rejection_date <= end_dt.date())
        ))

        monthly_trend_rows = db.session.query(
            DailyRejection.month,
            func.sum(DailyRejection.rj_pcs).label('total_pcs'),
            func.sum(DailyRejection.rj_weight).label('total_weight')
        ).filter(
            DailyRejection.id.in_(trend_query.with_entities(DailyRejection.id))
        ).group_by(DailyRejection.month).order_by(DailyRejection.month).all()
        monthly_map = {
            row[0]: {
                'pcs': int(row[1] or 0),
                'weight': round(float(row[2] or 0), 2)
            }
            for row in monthly_trend_rows
        }
        monthly_trend = []
        cursor = trend_start.replace(day=1)
        end_month = end_dt.replace(day=1)
        while cursor <= end_month:
            key = cursor.strftime('%Y-%m')
            monthly_trend.append({
                'month': key,
                'pcs': monthly_map.get(key, {}).get('pcs', 0),
                'weight': monthly_map.get(key, {}).get('weight', 0.0)
            })
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year + 1, month=1)
            else:
                cursor = cursor.replace(month=cursor.month + 1)
        
        return jsonify({
            'summary': {
                'total_inspected': total_inspected,
                'total_pcs': total_pcs,
                'total_weight': round(total_weight, 2),
                'total_records': total_records
            },
            'by_customer': [{
                'customer': c[0],
                'pcs': c[1],
                'weight': round(c[2], 2)
            } for c in customer_data],
            'by_defect_type': [{
                'defect_type': r[0] or 'Other',
                'pcs': r[1]
            } for r in defect_type_data],
            'monthly_trend': monthly_trend
        }), 200
        
    except Exception as e:
        logger.error(f'Error getting analytics: {str(e)}')
        return jsonify({'error': str(e)}), 500
