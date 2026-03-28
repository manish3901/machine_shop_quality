"""
Dashboard Routes - Analytics and visualization pages
"""

from flask import Blueprint, render_template, request, jsonify, Response
from models import (
    db, ProductionEntry, Machine, MachineShed, Customer, IssueType, ProductionIssue, AuditLog,
    DailyRejection, RejectionDefect, DefectType, ProductionPlannedDowntime,
    SectionMaster, SectionCutLength, OperationType, ProductionEntryOperation,
    ProductionEntryOperator, ProductionEntrySupervisor, DailyRejectionSupervisor, EmpMaster, ReworkLog,
    ProductionSelfRejectionDefect
)
from sqlalchemy import func, and_, or_, literal_column
from datetime import datetime, timedelta, timezone
from utils.auth import login_required, admin_required
import json
import logging
import csv
from io import StringIO

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint('dashboard', __name__)


def _parse_datetime(value):
    if not value:
        return None
    try:
        if 'T' in value:
            return datetime.fromisoformat(value)
        return datetime.strptime(value, '%Y-%m-%d')
    except Exception:
        return None


def _default_dashboard_range(now=None):
    """Return the default datetime window (first of month to current time)."""
    now = now or datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month_start, now


def _resolve_datetime_window(start_value, end_value, *, default_range=None, days_param=None):
    start = _parse_datetime(start_value)
    end = _parse_datetime(end_value)
    default_start, default_end = default_range or _default_dashboard_range()
    days_to_apply = days_param if isinstance(days_param, (int, float)) and days_param > 0 else None
    if start and not end:
        end = start + timedelta(days=max(days_to_apply, 1)) if days_to_apply else start
    elif end and not start:
        start = end - timedelta(days=max(days_to_apply, 1)) if days_to_apply else end
    elif not start and not end:
        if days_to_apply:
            end = default_end
            start = end - timedelta(days=max(days_to_apply, 1))
        else:
            start, end = default_start, default_end
    if start > end:
        start, end = end, start
    return start, end


def _apply_entry_filters(query):
    customer_id = request.args.get('customer_id', type=int)
    machine_id = request.args.get('machine_id', type=int)
    shed_id = request.args.get('shed_id', type=int)
    shift = (request.args.get('shift') or '').strip()
    section_number = (request.args.get('section_number') or request.args.get('section') or '').strip()
    cut_length = (request.args.get('cut_length') or request.args.get('cutlength') or '').strip()
    operation_type_id = request.args.get('operation_type_id', type=int)
    entry_no = (request.args.get('entry_no') or '').strip()
    emp_code = (request.args.get('emp_code') or '').strip()

    if customer_id:
        query = query.filter(ProductionEntry.customer_id == customer_id)
    if shed_id:
        query = query.join(Machine, Machine.id == ProductionEntry.machine_id)
        query = query.filter(Machine.shed_id == shed_id)
    if machine_id:
        query = query.filter(ProductionEntry.machine_id == machine_id)
    if shift:
        query = query.filter(ProductionEntry.shift.ilike(f"%{shift}%"))
    if section_number:
        query = query.filter(ProductionEntry.section_number.ilike(f"%{section_number}%"))
    if cut_length:
        try:
            query = query.filter(ProductionEntry.cutlength == float(cut_length))
        except ValueError:
            pass
    if operation_type_id:
        query = query.join(ProductionEntryOperation, ProductionEntryOperation.production_entry_id == ProductionEntry.id)
        query = query.filter(ProductionEntryOperation.operation_type_id == operation_type_id).distinct()
    if entry_no:
        query = query.filter(ProductionEntry.entry_no.ilike(f"%{entry_no}%"))
    if emp_code:
        matching_emp_ids = [
            row[0] for row in db.session.query(EmpMaster.emp_id)
            .filter(EmpMaster.emp_code.ilike(f"%{emp_code}%")).all()
        ]
        if not matching_emp_ids:
            query = query.filter(ProductionEntry.id == -1)
        else:
            operator_entry_ids = db.session.query(ProductionEntryOperator.production_entry_id).filter(
                ProductionEntryOperator.operator_emp_id.in_(matching_emp_ids)
            )
            supervisor_entry_ids = db.session.query(ProductionEntrySupervisor.production_entry_id).filter(
                ProductionEntrySupervisor.supervisor_emp_id.in_(matching_emp_ids)
            )
            quality_entry_ids = db.session.query(DailyRejection.production_entry_id)\
                .join(DailyRejectionSupervisor, DailyRejectionSupervisor.rejection_id == DailyRejection.id)\
                .filter(
                    DailyRejectionSupervisor.supervisor_emp_id.in_(matching_emp_ids),
                    DailyRejection.production_entry_id.isnot(None)
                )
            query = query.filter(or_(
                ProductionEntry.id.in_(operator_entry_ids),
                ProductionEntry.id.in_(supervisor_entry_ids),
                ProductionEntry.id.in_(quality_entry_ids)
            ))
    return query


def _dashboard_filter_options():
    customers = Customer.query.filter_by(status='Active').order_by(Customer.customer_name).all()
    sheds = MachineShed.query.filter_by(status='Active').order_by(MachineShed.shed_name).all()
    machines = Machine.query.filter_by(status='Active').order_by(Machine.machine_name).all()
    operations = OperationType.query.order_by(OperationType.operation_name).all()
    defect_types = DefectType.query.filter_by(is_active=True).order_by(DefectType.defect_name).all()
    selected_customer_id = request.args.get('customer_id', type=int)
    selected_section_number = (request.args.get('section_number') or request.args.get('section') or '').strip()
    sections = SectionMaster.query.filter_by(customer_id=selected_customer_id, status='Active').order_by(SectionMaster.section_number).all() if selected_customer_id else []
    selected_section = next((s for s in sections if (s.section_number or '').strip() == selected_section_number), None)
    cut_lengths = SectionCutLength.query.filter_by(section_id=selected_section.id, status='Active').order_by(SectionCutLength.cut_length).all() if selected_section else []
    return {
        'filter_customers': customers,
        'filter_sheds': sheds,
        'filter_machines': machines,
        'filter_operations': operations,
        'filter_sections': sections,
        'filter_cut_lengths': cut_lengths,
        'filter_defect_types': defect_types
    }


def _self_rejection_breakdown(entry_ids, defect_type_id=None):
    if not entry_ids:
        return []
    query = db.session.query(
        DefectType.defect_name,
        func.sum(ProductionSelfRejectionDefect.reject_qty).label('total_qty'),
        func.count(func.distinct(ProductionSelfRejectionDefect.production_entry_id)).label('entries'),
        func.sum(
            func.coalesce(ProductionSelfRejectionDefect.reject_qty, 0) *
            func.coalesce(ProductionEntry.self_rejection_weight_per_pcs, 0)
        ).label('total_weight')
    ).join(
        ProductionSelfRejectionDefect, ProductionSelfRejectionDefect.defect_type_id == DefectType.id
    ).join(
        ProductionEntry, ProductionEntry.id == ProductionSelfRejectionDefect.production_entry_id
    ).filter(
        ProductionSelfRejectionDefect.production_entry_id.in_(entry_ids)
    )
    if defect_type_id:
        query = query.filter(ProductionSelfRejectionDefect.defect_type_id == defect_type_id)
    rows = query.group_by(DefectType.defect_name)\
        .order_by(func.sum(ProductionSelfRejectionDefect.reject_qty).desc()).all()
    total_qty_all = sum(int(row[1] or 0) for row in rows) or 0
    breakdown = []
    running = 0
    for idx, row in enumerate(rows, start=1):
        qty = int(row[1] or 0)
        running += qty
        breakdown.append({
            'rank': idx,
            'defect_type': row[0] or 'Defect',
            'count': qty,
            'entries': int(row[2] or 0),
            'weight': round(float(row[3] or 0), 3),
            'share_pct': round((qty / total_qty_all * 100), 1) if total_qty_all > 0 else 0,
            'cumulative_pct': round((running / total_qty_all * 100), 1) if total_qty_all > 0 else 0
        })
    return breakdown


def _compute_oee_summary(entries):
    total_planned = sum((e.planned_quantity or 0) for e in entries)
    total_actual = sum((e.actual_quantity or 0) for e in entries)
    total_ok = sum((e.total_ok_quantity or 0) for e in entries)
    total_downtime = sum((e.downtime_minutes or 0) for e in entries)
    total_operating_minutes = sum((e.total_time_taken_minutes or 0) for e in entries)
    total_planned_minutes = total_operating_minutes + total_downtime
    availability = (total_operating_minutes / total_planned_minutes * 100) if total_planned_minutes > 0 else 0
    total_ideal_minutes = 0.0
    for e in entries:
        ideal_mins = getattr(e, 'total_ideal_time_minutes', 0) or 0
        if not ideal_mins:
            ict_mins_per_pc = getattr(e, 'ideal_cycle_time', 0) or 0
            ideal_mins = (e.total_ok_quantity or 0) * ict_mins_per_pc
        total_ideal_minutes += ideal_mins
    performance = (total_ideal_minutes / total_operating_minutes * 100) if total_operating_minutes > 0 else 0
    entry_ids = [e.id for e in entries]
    rejected = 0
    if entry_ids:
        rejected = db.session.query(func.sum(DailyRejection.rj_pcs)).filter(DailyRejection.production_entry_id.in_(entry_ids)).scalar() or 0
    total_count = total_ok + rejected
    quality = (total_ok / total_count * 100) if total_count > 0 else 100
    oee = (availability / 100) * (performance / 100) * (quality / 100) * 100
    oee = min(max(oee, 0), 100)
    return {
        'total_planned': total_planned,
        'total_actual': total_actual,
        'total_ok': total_ok,
        'total_downtime': total_downtime,
        'total_operating_minutes': total_operating_minutes,
        'total_planned_minutes': total_planned_minutes,
        'total_ideal_minutes': total_ideal_minutes,
        'total_rejected_pcs': rejected,
        'availability': availability,
        'performance': performance,
        'quality': quality,
        'oee': oee
    }


@dashboard_bp.route('/daily')
@login_required
def daily_dashboard():
    """Daily production dashboard"""
    selected_date = _parse_datetime(request.args.get('date'))
    start_datetime, end_datetime = _resolve_datetime_window(
        request.args.get('start_date'),
        request.args.get('end_date'),
        default_range=_default_dashboard_range()
    )
    if selected_date and not request.args.get('start_date') and not request.args.get('end_date'):
        start_datetime = datetime.combine(selected_date, datetime.min.time())
        end_datetime = datetime.combine(selected_date, datetime.max.time())
    start_date = start_datetime.date()
    end_date = end_datetime.date()
    start_datetime_value = start_datetime.strftime('%Y-%m-%dT%H:%M')
    end_datetime_value = end_datetime.strftime('%Y-%m-%dT%H:%M')

    entries_query = ProductionEntry.query.filter(
        and_(ProductionEntry.production_date >= start_date, ProductionEntry.production_date <= end_date)
    )
    entries_query = _apply_entry_filters(entries_query)
    entries = entries_query.all()
    
    # Calculate metrics
    oee_summary = _compute_oee_summary(entries)
    total_planned = oee_summary['total_planned']
    total_actual = oee_summary['total_actual']
    total_ok = oee_summary['total_ok']
    total_rejected_pcs = oee_summary['total_rejected_pcs']
    total_downtime = oee_summary['total_downtime']
    total_operating_minutes = oee_summary['total_operating_minutes']
    total_planned_minutes = oee_summary['total_planned_minutes']
    total_ideal_minutes = oee_summary['total_ideal_minutes']
    availability = oee_summary['availability']
    performance = oee_summary['performance']
    quality = oee_summary['quality']
    oee = oee_summary['oee']
    entry_ids = [e.id for e in entries]
    total_rework = sum((e.rework_qty or 0) for e in entries)
    total_self_rejection = sum((e.self_rejection_qty or 0) for e in entries)
    total_machining_scrap_kg = sum((e.machining_scrap_weight_kg or 0) for e in entries)
    efficiency = (total_ok / total_planned * 100) if total_planned > 0 else 0
    final_rejected_pcs = max(total_rejected_pcs - total_rework, 0)
    rework_breakdown = []
    if entry_ids:
        rework_rows = db.session.query(
            DefectType.defect_name,
            func.sum(ReworkLog.rework_qty)
        ).join(ReworkLog, ReworkLog.defect_type_id == DefectType.id)\
         .filter(ReworkLog.production_entry_id.in_(entry_ids))\
         .group_by(DefectType.defect_name)\
         .order_by(func.sum(ReworkLog.rework_qty).desc()).all()
        rework_breakdown = [{
            'defect_type': r[0] or 'Defect',
            'qty': int(r[1] or 0)
        } for r in rework_rows if r[1]]

    # Quality uses produced OK as good count, and includes rejection impact.
    if entry_ids:
        rejections = DailyRejection.query.filter(DailyRejection.production_entry_id.in_(entry_ids)).all()
    else:
        rejections = DailyRejection.query.filter(
            and_(DailyRejection.rejection_date >= start_date, DailyRejection.rejection_date <= end_date)
        ).all()
    ideal_vs_available_gap = total_operating_minutes - total_ideal_minutes
    
    # Pareto Data (Defects)
    rejection_ids = [r.id for r in rejections]
    pareto_data = []
    if rejection_ids:
        defects = db.session.query(
            DefectType.defect_name,
            func.sum(RejectionDefect.defect_count).label('total_count')
        ).join(RejectionDefect).filter(RejectionDefect.rejection_id.in_(rejection_ids))\
         .group_by(DefectType.defect_name).order_by(func.sum(RejectionDefect.defect_count).desc()).all()
        
        pareto_data = [{'label': d[0], 'value': int(d[1])} for d in defects]

    # Trends (Last 7 Days)
    trend_start = start_date if (end_date - start_date).days >= 1 else (end_date - timedelta(days=6))
    trend_end = end_date
    trend_query = ProductionEntry.query.filter(ProductionEntry.production_date.between(trend_start, trend_end))
    trend_query = _apply_entry_filters(trend_query)
    trend_entries = trend_query.all()
    trend_data = {}
    days_count = (trend_end - trend_start).days + 1
    for i in range(days_count):
        d = (trend_start + timedelta(days=i)).isoformat()
        trend_data[d] = {'planned': 0, 'actual': 0, 'final_ok': 0}
        
    for e in trend_entries:
        d = e.production_date.isoformat()
        if d in trend_data:
            trend_data[d]['planned'] += e.planned_quantity
            trend_data[d]['actual'] += e.actual_quantity
            trend_data[d]['final_ok'] += int(e.total_ok_quantity or 0)
            
    sorted_trend = sorted(trend_data.items())
    
    # Calculate by_shift
    by_shift = {}
    for e in entries:
        shift_values = [s.strip() for s in (e.shift or '').split(',') if s.strip()] or ['Unknown']
        for shift_key in shift_values:
            if shift_key not in by_shift:
                by_shift[shift_key] = {'actual': 0, 'planned': 0, 'final_ok': 0, 'efficiency': 0, 'downtime': 0, 'machines': set(), 'entries': 0}
            by_shift[shift_key]['actual'] += getattr(e, 'actual_quantity', 0) or 0
            by_shift[shift_key]['planned'] += getattr(e, 'planned_quantity', 0) or 0
            by_shift[shift_key]['final_ok'] += getattr(e, 'total_ok_quantity', 0) or 0
            by_shift[shift_key]['downtime'] += getattr(e, 'downtime_minutes', 0) or 0
            by_shift[shift_key]['machines'].add(e.machine_id)
            by_shift[shift_key]['entries'] += 1

    for s, data in by_shift.items():
        if data['planned'] > 0:
            data['efficiency'] = round((data['final_ok'] / data['planned']) * 100, 2)
        data['machines'] = len(data['machines'])
    
    # Calculate underperforming machines (lowest efficiency) and chart payload
    machine_stats = {}
    for e in entries:
        m_name = e.machine.machine_name if e.machine else f'Machine-{e.machine_id}'
        if m_name not in machine_stats:
            machine_stats[m_name] = {'planned': 0, 'actual': 0}
            machine_stats[m_name]['final_ok'] = 0
        machine_stats[m_name]['planned'] += e.planned_quantity or 0
        machine_stats[m_name]['actual'] += e.actual_quantity or 0
        machine_stats[m_name]['final_ok'] += int(e.total_ok_quantity or 0)
        
    underperforming = []
    for m_name, stats in machine_stats.items():
        final_qty = stats.get('final_ok', 0)
        eff = (final_qty / stats['planned'] * 100) if stats['planned'] > 0 else 0
        underperforming.append({'machine': m_name, 'planned': stats['planned'], 'actual': stats['actual'], 'final_ok': final_qty, 'efficiency': round(eff, 2)})
        
    underperforming.sort(key=lambda x: x['efficiency'])
    
    machine_chart_labels = list(machine_stats.keys())
    machine_chart_planned = [machine_stats[k]['planned'] for k in machine_chart_labels]
    machine_chart_actual = [machine_stats[k]['actual'] for k in machine_chart_labels]
    machine_chart_final = [machine_stats[k]['final_ok'] for k in machine_chart_labels]
    machine_table = []
    total_machine_final = sum(machine_chart_final) or 0
    for label in machine_chart_labels:
        planned_val = machine_stats.get(label, {}).get('planned', 0)
        actual_val = machine_stats.get(label, {}).get('actual', 0)
        final_val = machine_stats.get(label, {}).get('final_ok', 0)
        machine_table.append({
            'machine': label,
            'planned': planned_val,
            'actual': actual_val,
            'final_ok': final_val,
            'variance': final_val - planned_val,
            'plan_attainment_pct': round((final_val / planned_val * 100), 1) if planned_val > 0 else 0,
            'actual_to_final_loss': actual_val - final_val,
            'share_of_final_ok_pct': round((final_val / total_machine_final * 100), 1) if total_machine_final > 0 else 0
        })
    trend_table = [{
        'date': x[0],
        'planned': x[1]['planned'],
        'actual': x[1]['actual'],
        'final_ok': int(x[1]['final_ok']),
        'variance_vs_plan': int(x[1]['final_ok']) - x[1]['planned'],
        'actual_to_final_loss': x[1]['actual'] - int(x[1]['final_ok']),
        'plan_attainment_pct': round((int(x[1]['final_ok']) / x[1]['planned'] * 100), 1) if x[1]['planned'] > 0 else 0
    } for x in sorted_trend]
    total_pareto = sum(d['value'] for d in pareto_data) or 0
    running_pareto = 0
    pareto_table = []
    for idx, d in enumerate(pareto_data, start=1):
        running_pareto += d['value']
        pareto_table.append({
            'rank': idx,
            'defect_type': d['label'],
            'count': d['value'],
            'share_pct': round((d['value'] / total_pareto * 100), 1) if total_pareto > 0 else 0,
            'cumulative_pct': round((running_pareto / total_pareto * 100), 1) if total_pareto > 0 else 0
        })
    shift_table = [{
        'shift': shift_key,
        'planned': shift_values['planned'],
        'actual': shift_values['actual'],
        'final_ok': shift_values['final_ok'],
        'efficiency': shift_values['efficiency'],
        'downtime': shift_values['downtime'],
        'machines': shift_values['machines'],
        'entries': shift_values['entries'],
        'variance': shift_values['final_ok'] - shift_values['planned']
    } for shift_key, shift_values in by_shift.items()]
    oee_table = [
        {'metric': 'Availability', 'value_pct': round(availability, 1), 'numerator': round(total_operating_minutes, 1), 'denominator': round(total_planned_minutes, 1), 'formula': 'Operating Time / Planned Time', 'basis': f'{round(total_operating_minutes,1)} / {round(total_planned_minutes,1)} min'},
        {'metric': 'Performance', 'value_pct': round(performance, 1), 'numerator': round(total_ideal_minutes, 1), 'denominator': round(total_operating_minutes, 1), 'formula': 'Ideal Time / Operating Time', 'basis': f'{round(total_ideal_minutes,1)} / {round(total_operating_minutes,1)} min'},
        {'metric': 'Quality', 'value_pct': round(quality, 1), 'numerator': round(total_ok, 1), 'denominator': round(total_ok + total_rejected_pcs, 1), 'formula': 'Final OK / (Final OK + Rejects)', 'basis': f'{round(total_ok,1)} / {round(total_ok + total_rejected_pcs,1)} pcs'}
    ]

    # Sidebar employee performance for filtered entries
    employee_performance = []
    if entry_ids:
        operator_rows = db.session.query(
            EmpMaster.emp_name,
            EmpMaster.emp_code,
            func.count(ProductionEntryOperator.id).label('assignments'),
            func.sum(ProductionEntry.actual_quantity).label('actual_qty')
        ).join(ProductionEntryOperator, ProductionEntryOperator.operator_emp_id == EmpMaster.emp_id)\
         .join(ProductionEntry, ProductionEntry.id == ProductionEntryOperator.production_entry_id)\
         .filter(ProductionEntry.id.in_(entry_ids))\
         .group_by(EmpMaster.emp_id, EmpMaster.emp_name, EmpMaster.emp_code).all()
        supervisor_rows = db.session.query(
            EmpMaster.emp_name,
            EmpMaster.emp_code,
            func.count(ProductionEntrySupervisor.id).label('assignments'),
            func.sum(ProductionEntry.actual_quantity).label('actual_qty')
        ).join(ProductionEntrySupervisor, ProductionEntrySupervisor.supervisor_emp_id == EmpMaster.emp_id)\
         .join(ProductionEntry, ProductionEntry.id == ProductionEntrySupervisor.production_entry_id)\
         .filter(ProductionEntry.id.in_(entry_ids))\
         .group_by(EmpMaster.emp_id, EmpMaster.emp_name, EmpMaster.emp_code).all()
        employee_performance = [{
            'name': r[0], 'code': r[1], 'role': 'Operator', 'assignments': int(r[2] or 0), 'actual_qty': int(r[3] or 0)
        } for r in operator_rows] + [{
            'name': r[0], 'code': r[1], 'role': 'Supervisor', 'assignments': int(r[2] or 0), 'actual_qty': int(r[3] or 0)
        } for r in supervisor_rows]
        employee_performance.sort(key=lambda x: (x['actual_qty'], x['assignments']), reverse=True)
        employee_performance = employee_performance[:10]

    context = _dashboard_filter_options()
    return render_template('dashboard_daily.html',
                         date=end_date,
                         start_datetime=start_datetime,
                         end_datetime=end_datetime,
                         start_date=start_date,
                         end_date=end_date,
                         start_datetime_value=start_datetime_value,
                         end_datetime_value=end_datetime_value,
                         entries=entries,
                         total_planned=total_planned,
                         total_actual=total_actual,
                         total_ok=total_ok,
                         total_final_ok=total_ok,
                          total_rework=total_rework,
                          total_self_rejection=total_self_rejection,
                          total_self_rejection_pcs=total_self_rejection,
                          total_machining_scrap_kg=round(total_machining_scrap_kg, 3),
                          total_rejected_pcs=total_rejected_pcs,
                         final_rejected_pcs=final_rejected_pcs,
                         rework_breakdown=rework_breakdown,
                         efficiency=round(efficiency, 2),
                         total_downtime=total_downtime,
                         total_operating_minutes=round(total_operating_minutes, 1),
                         total_planned_minutes=round(total_planned_minutes, 1),
                         total_ideal_minutes=round(total_ideal_minutes, 1),
                         ideal_vs_available_gap=round(ideal_vs_available_gap, 1),
                         by_shift=by_shift,
                         underperforming=underperforming[:5],
                         oee_metrics={
                             'oee': round(oee, 1),
                             'availability': round(availability, 1),
                             'performance': round(performance, 1),
                             'quality': round(quality, 1)
                         },
                         employee_performance=employee_performance,
                         pareto_json=json.dumps(pareto_data),
                         machine_chart_labels=json.dumps(machine_chart_labels),
                         machine_chart_planned=json.dumps(machine_chart_planned),
                         machine_chart_actual=json.dumps(machine_chart_actual),
                         machine_chart_final=json.dumps(machine_chart_final),
                         trend_labels=json.dumps([x[0] for x in sorted_trend]),
                         trend_planned=json.dumps([x[1]['planned'] for x in sorted_trend]),
                         trend_actual=json.dumps([x[1]['actual'] for x in sorted_trend]),
                         trend_final=json.dumps([x[1]['final_ok'] for x in sorted_trend]),
                         machine_table=machine_table,
                          trend_table=trend_table,
                          pareto_table=pareto_table,
                          shift_table=shift_table,
                          oee_table=oee_table,
                         **context)


@dashboard_bp.route('/weekly')
@login_required
def weekly_dashboard():
    """Weekly production dashboard"""
    start_datetime, end_datetime = _resolve_datetime_window(
        request.args.get('start_date'),
        request.args.get('end_date'),
        default_range=_default_dashboard_range(),
        days_param=request.args.get('days', type=int)
    )
    start_date = start_datetime.date()
    end_date = end_datetime.date()
    
    entries_query = ProductionEntry.query.filter(
        and_(ProductionEntry.production_date >= start_date, ProductionEntry.production_date <= end_date)
    )
    entries_query = _apply_entry_filters(entries_query)
    entries = entries_query.all()
    
    total_final_ok = sum(int(e.total_ok_quantity or 0) for e in entries)
    # Daily breakdown
    daily_data = {}
    for entry in entries:
        date_key = entry.production_date.isoformat()
        if date_key not in daily_data:
            daily_data[date_key] = {'planned': 0, 'actual': 0, 'final_ok': 0, 'entries': 0}
        daily_data[date_key]['planned'] += entry.planned_quantity
        daily_data[date_key]['actual'] += entry.actual_quantity
        daily_data[date_key]['final_ok'] += int(entry.total_ok_quantity or 0)
        daily_data[date_key]['entries'] += 1
    
    # Calculate trends
    total_planned = sum(e.planned_quantity for e in entries)
    total_actual = sum(e.actual_quantity for e in entries)
    efficiency = (total_actual / total_planned * 100) if total_planned > 0 else 0
    
    # Top reported defect types (from rejection defect breakdown)
    filtered_entry_ids = [e.id for e in entries]
    if filtered_entry_ids:
        top_defects = db.session.query(
            DefectType.defect_name,
            func.sum(RejectionDefect.defect_count).label('count')
        ).join(RejectionDefect, RejectionDefect.defect_type_id == DefectType.id)\
         .join(DailyRejection, DailyRejection.id == RejectionDefect.rejection_id)\
         .filter(
            DailyRejection.production_entry_id.in_(filtered_entry_ids),
            DailyRejection.rejection_date >= start_date,
            DailyRejection.rejection_date <= end_date
         ).group_by(DefectType.id, DefectType.defect_name)\
         .order_by(func.sum(RejectionDefect.defect_count).desc()).limit(5).all()
    else:
        top_defects = []
    
    weekly_table = [{
        'date': k,
        'planned': v['planned'],
        'actual': v['actual'],
        'final_ok': v['final_ok'],
        'entries': v['entries'],
        'variance_vs_plan': v['final_ok'] - v['planned'],
        'actual_to_final_loss': v['actual'] - v['final_ok'],
        'plan_attainment_pct': round((v['final_ok'] / v['planned'] * 100), 1) if v['planned'] > 0 else 0
    } for k, v in sorted(daily_data.items())]

    total_rework_qty = sum((e.rework_qty or 0) for e in entries)
    total_self_rejection = sum((e.self_rejection_qty or 0) for e in entries)
    total_machining_scrap_kg = sum((e.machining_scrap_weight_kg or 0) for e in entries)
    total_quality_rejections = 0
    rework_materials = []
    self_rejection_materials = _self_rejection_breakdown(filtered_entry_ids)
    if filtered_entry_ids:
        total_quality_rejections = db.session.query(func.sum(DailyRejection.rj_pcs))\
            .filter(DailyRejection.production_entry_id.in_(filtered_entry_ids)).scalar() or 0
        rework_rows = db.session.query(
            DefectType.defect_name,
            func.sum(ReworkLog.rework_qty).label('qty')
        ).join(DefectType, DefectType.id == ReworkLog.defect_type_id)\
         .filter(ReworkLog.production_entry_id.in_(filtered_entry_ids))\
         .group_by(DefectType.defect_name).order_by(func.sum(ReworkLog.rework_qty).desc()).all()
        rework_materials = [{'defect_type': r[0], 'qty': int(r[1] or 0)} for r in rework_rows if r[1]]
    weekly_rework_summary = {
        'total_rework_qty': total_rework_qty,
        'total_self_rejection': total_self_rejection,
        'total_self_rejection_pcs': total_self_rejection,
        'total_machining_scrap_kg': round(total_machining_scrap_kg, 3),
        'quality_rejections': int(total_quality_rejections or 0),
        'rework_materials': rework_materials,
        'self_rejection_materials': self_rejection_materials
    }

    context = _dashboard_filter_options()
    return render_template('dashboard_weekly.html',
                          start_date=start_date,
                          end_date=end_date,
                          start_datetime=start_datetime,
                          end_datetime=end_datetime,
                          start_datetime_value=start_datetime.strftime('%Y-%m-%dT%H:%M'),
                          end_datetime_value=end_datetime.strftime('%Y-%m-%dT%H:%M'),
                          daily_data=json.dumps(daily_data),
                          weekly_table=weekly_table,
                          total_planned=total_planned,
                          total_actual=total_actual,
                          total_final_ok=total_final_ok,
                          efficiency=round(efficiency, 2),
                          top_defects=top_defects,
                          weekly_rework_summary=weekly_rework_summary,
                          **context)


@dashboard_bp.route('/machine-performance')
@login_required
def machine_performance_dashboard():
    """Machine-wise performance dashboard"""
    start_datetime, end_datetime = _resolve_datetime_window(
        request.args.get('start_date'),
        request.args.get('end_date'),
        default_range=_default_dashboard_range(),
        days_param=request.args.get('days', type=int)
    )
    start_date = start_datetime.date()
    end_date = end_datetime.date()
    
    entries_query = ProductionEntry.query.filter(
        and_(ProductionEntry.production_date >= start_date, ProductionEntry.production_date <= end_date)
    )
    entries_query = _apply_entry_filters(entries_query)
    entries = entries_query.all()
    
    active_machines = Machine.query.filter_by(status='Active').order_by(Machine.machine_name).all()
    machine_data = {
        machine.id: {
            'name': machine.machine_name,
            'type': machine.machine_type,
            'planned': 0,
            'actual': 0,
            'final_ok': 0,
            'downtime': 0,
            'entries': 0,
            'machine_id': machine.id
        }
        for machine in active_machines
    }
    for entry in entries:
        if entry.machine_id not in machine_data:
            machine_data[entry.machine_id] = {
                'name': entry.machine.machine_name if entry.machine else f'Machine-{entry.machine_id}',
                'type': entry.machine.machine_type if entry.machine else '-',
                'planned': 0,
                'actual': 0,
                'final_ok': 0,
                'downtime': 0,
                'entries': 0,
                'machine_id': entry.machine_id
            }
        machine_data[entry.machine_id]['planned'] += entry.planned_quantity or 0
        machine_data[entry.machine_id]['actual'] += entry.actual_quantity or 0
        machine_data[entry.machine_id]['final_ok'] += int(entry.total_ok_quantity or 0)
        machine_data[entry.machine_id]['downtime'] += entry.downtime_minutes or 0
        machine_data[entry.machine_id]['entries'] += 1

    # Calculate metrics
    performance = []
    for machine_id, data in machine_data.items():
        planned_qty = data.get('planned') or 0
        final_ok_qty = data.get('final_ok') or 0
        efficiency = (final_ok_qty / planned_qty * 100) if planned_qty > 0 else 0
        avg_downtime = data['downtime'] / data['entries'] if data['entries'] > 0 else 0
        performance.append({
            'machine_id': machine_id,
            'machine': data['name'],
            'type': data['type'],
            'planned': planned_qty,
            'actual': data['actual'],
            'final_ok': final_ok_qty,
            'efficiency': round(efficiency, 2),
            'avg_downtime': round(avg_downtime, 2),
            'entries': data['entries']
        })
    
    # Sort by efficiency (lowest first)
    performance.sort(key=lambda x: x['efficiency'])
    
    machine_table = [{
        'machine': m['machine'],
        'type': m['type'],
        'planned': m['planned'],
        'actual': m['actual'],
        'final_ok': m['final_ok'],
        'efficiency': m['efficiency'],
        'avg_downtime': m['avg_downtime'],
        'entries': m['entries']
    } for m in performance]
    period_days = (end_date - start_date).days + 1
    final_total_ok = sum(m['final_ok'] for m in performance)
    context = _dashboard_filter_options()
    return render_template('machine_performance.html',
                         machines=performance,
                         machine_table=machine_table,
                         period_days=period_days,
                         start_date=start_date,
                         end_date=end_date,
                         start_datetime=start_datetime,
                         end_datetime=end_datetime,
                         start_datetime_value=start_datetime.strftime('%Y-%m-%dT%H:%M'),
                         end_datetime_value=end_datetime.strftime('%Y-%m-%dT%H:%M'),
                         final_total_ok=final_total_ok,
                         **context)


@dashboard_bp.route('/shift-analysis')
@login_required
def shift_analysis_dashboard():
    """Shift comparison and analysis"""
    start_datetime, end_datetime = _resolve_datetime_window(
        request.args.get('start_date'),
        request.args.get('end_date'),
        default_range=_default_dashboard_range(),
        days_param=request.args.get('days', type=int)
    )
    start_date = start_datetime.date()
    end_date = end_datetime.date()
    
    entries_query = ProductionEntry.query.filter(
        and_(ProductionEntry.production_date >= start_date, ProductionEntry.production_date <= end_date)
    )
    entries_query = _apply_entry_filters(entries_query)
    entries = entries_query.all()
    
    # Shift analysis
    shifts = {'A': [], 'B': [], 'C': []}
    for entry in entries:
        shift_values = [s.strip() for s in (entry.shift or '').split(',') if s.strip()]
        if not shift_values:
            continue
        for s in shift_values:
            if s in shifts:
                shifts[s].append(entry)
    
    shift_metrics = {}
    for shift, shift_entries in shifts.items():
        total_planned = sum(e.planned_quantity for e in shift_entries)
        total_actual = sum(e.actual_quantity for e in shift_entries)
        efficiency = (total_actual / total_planned * 100) if total_planned > 0 else 0
        
        shift_metrics[shift] = {
            'planned': total_planned,
            'actual': total_actual,
            'efficiency': round(efficiency, 2),
            'entries': len(shift_entries),
            'machines': len(set(e.machine_id for e in shift_entries)),
            'downtime': sum(e.downtime_minutes for e in shift_entries)
        }
    entry_ids = [e.id for e in entries]
    rejection_totals = None
    if entry_ids:
        rejection_totals = db.session.query(
            DailyRejection.production_entry_id.label('entry_id'),
            func.coalesce(func.sum(DailyRejection.rj_pcs), 0).label('rj_pcs')
        ).filter(DailyRejection.production_entry_id.in_(entry_ids))\
         .group_by(DailyRejection.production_entry_id).subquery()
    quality_expr = func.sum(literal_column('0'))
    if rejection_totals is not None:
        quality_expr = func.sum(func.coalesce(rejection_totals.c.rj_pcs, 0))

    def _row_to_dict(r, role):
        planned = float(r[5] or 0)
        actual = float(r[4] or 0)
        rework = float(r[6] or 0)
        quality_rej = float(r[8] or 0)
        final_ok = max(actual - quality_rej, 0)
        eff = round((actual / planned * 100) if planned else 0, 2)
        perf = round((final_ok / planned * 100) if planned else 0, 2)
        return {
            'name': r[0],
            'code': r[1],
            'shift': r[2],
            'role': role,
            'assignments': int(r[3] or 0),
            'actual_qty': int(actual),
            'planned_qty': int(planned),
            'total_ok': int(final_ok),
            'rework_qty': int(r[6] or 0),
            'self_rejection_qty': int(r[7] or 0),
            'total_self_rejection_pcs': int(r[7] or 0),
            'quality_rejections': int(quality_rej),
            'efficiency': eff,
            'performance': perf
        }

    employee_performance = []
    if entry_ids:
        operator_query = db.session.query(
            EmpMaster.emp_name,
            EmpMaster.emp_code,
            ProductionEntry.shift,
            func.count(ProductionEntryOperator.id).label('assignments'),
            func.sum(ProductionEntry.actual_quantity).label('actual_qty'),
            func.sum(ProductionEntry.planned_quantity).label('planned_qty'),
            func.sum(func.coalesce(ProductionEntry.rework_qty, 0)).label('rework_qty'),
            func.sum(func.coalesce(ProductionEntry.self_rejection_qty, 0)).label('self_rejection_qty'),
            quality_expr.label('quality_rejections')
        ).join(ProductionEntryOperator, ProductionEntryOperator.operator_emp_id == EmpMaster.emp_id)\
         .join(ProductionEntry, ProductionEntry.id == ProductionEntryOperator.production_entry_id)
        supervisor_query = db.session.query(
            EmpMaster.emp_name,
            EmpMaster.emp_code,
            ProductionEntry.shift,
            func.count(ProductionEntrySupervisor.id).label('assignments'),
            func.sum(ProductionEntry.actual_quantity).label('actual_qty'),
            func.sum(ProductionEntry.planned_quantity).label('planned_qty'),
            func.sum(func.coalesce(ProductionEntry.rework_qty, 0)).label('rework_qty'),
            func.sum(func.coalesce(ProductionEntry.self_rejection_qty, 0)).label('self_rejection_qty'),
            quality_expr.label('quality_rejections')
        ).join(ProductionEntrySupervisor, ProductionEntrySupervisor.supervisor_emp_id == EmpMaster.emp_id)\
         .join(ProductionEntry, ProductionEntry.id == ProductionEntrySupervisor.production_entry_id)
        if rejection_totals is not None:
            operator_query = operator_query.outerjoin(rejection_totals, rejection_totals.c.entry_id == ProductionEntry.id)
            supervisor_query = supervisor_query.outerjoin(rejection_totals, rejection_totals.c.entry_id == ProductionEntry.id)
        operator_rows = operator_query.filter(ProductionEntry.id.in_(entry_ids))\
            .group_by(EmpMaster.emp_id, EmpMaster.emp_name, EmpMaster.emp_code, ProductionEntry.shift).all()
        supervisor_rows = supervisor_query.filter(ProductionEntry.id.in_(entry_ids))\
            .group_by(EmpMaster.emp_id, EmpMaster.emp_name, EmpMaster.emp_code, ProductionEntry.shift).all()
        combined = [_row_to_dict(r, 'Operator') for r in operator_rows] + [_row_to_dict(r, 'Supervisor') for r in supervisor_rows]
        combined.sort(key=lambda x: (x['total_ok'], x['assignments']), reverse=True)
        employee_performance = combined[:12]
    
    shift_table = [{
        'shift': shift_key,
        'planned': data['planned'],
        'actual': data['actual'],
        'efficiency': data['efficiency'],
        'downtime': data['downtime'],
        'variance': data['actual'] - data['planned'],
        'avg_downtime_per_entry': round((data['downtime'] / data['entries']), 1) if data['entries'] > 0 else 0,
        'entries': data['entries']
    } for shift_key, data in shift_metrics.items()]

    period_days = (end_date - start_date).days + 1
    context = _dashboard_filter_options()
    return render_template('shift_analysis.html',
                          shift_metrics=json.dumps(shift_metrics),
                          shift_table=shift_table,
                          period_days=period_days,
                          start_date=start_date,
                          end_date=end_date,
                          start_datetime=start_datetime,
                          end_datetime=end_datetime,
                          start_datetime_value=start_datetime.strftime('%Y-%m-%dT%H:%M'),
                          end_datetime_value=end_datetime.strftime('%Y-%m-%dT%H:%M'),
                          employee_performance=employee_performance,
                          **context)


@dashboard_bp.route('/issues-analysis')
@login_required
def issues_analysis_dashboard():
    """Defect analysis dashboard (type-wise)"""
    days = request.args.get('days', 30, type=int)
    defect_type_id = request.args.get('defect_type_id', type=int)
    start_datetime, end_datetime = _resolve_datetime_window(
        request.args.get('start_date'),
        request.args.get('end_date'),
        default_range=_default_dashboard_range(),
        days_param=days
    )
    start_date = start_datetime.date()
    end_date = end_datetime.date()

    entries_query = ProductionEntry.query.filter(
        and_(ProductionEntry.production_date >= start_date, ProductionEntry.production_date <= end_date)
    )
    if defect_type_id:
        entries_query = entries_query.join(DailyRejection, DailyRejection.production_entry_id == ProductionEntry.id)\
            .join(RejectionDefect, RejectionDefect.rejection_id == DailyRejection.id)\
            .filter(RejectionDefect.defect_type_id == defect_type_id)
    entries_query = _apply_entry_filters(entries_query).distinct()
    entries = entries_query.all()
    entry_ids = [e.id for e in entries]
    defects_query = db.session.query(
        DefectType.defect_name,
        DefectType.category,
        func.count(RejectionDefect.id).label('occurrences'),
        func.sum(RejectionDefect.defect_count).label('total_pcs')
    ).join(RejectionDefect, RejectionDefect.defect_type_id == DefectType.id)\
     .join(DailyRejection, DailyRejection.id == RejectionDefect.rejection_id)\
     .filter(
        DailyRejection.rejection_date >= start_date,
        DailyRejection.rejection_date <= end_date
     )

    # Keep dashboard filters aligned to production entries when available.
    # If no production-entry matches are found, fall back to date-based rejection data
    # so defect charts do not appear empty when rejection records exist.
    if entry_ids:
        defects_query = defects_query.filter(DailyRejection.production_entry_id.in_(entry_ids))
    if defect_type_id:
        defects_query = defects_query.filter(RejectionDefect.defect_type_id == defect_type_id)

    defects = defects_query.group_by(
        DefectType.id, DefectType.defect_name, DefectType.category
    ).order_by(func.sum(RejectionDefect.defect_count).desc()).all()

    # By defect type (direct aggregation from query result)
    by_defect_type = {}
    for d in defects:
        defect_name = d[0] or 'Unknown'
        if defect_name not in by_defect_type:
            by_defect_type[defect_name] = {'count': 0, 'impact': 0}
        by_defect_type[defect_name]['count'] += int(d[2] or 0)
        by_defect_type[defect_name]['impact'] += int(d[3] or 0)

    total_defects = sum(info['count'] for info in by_defect_type.values()) or 0
    defect_table = []
    running_defects = 0
    for idx, (name, info) in enumerate(sorted(by_defect_type.items(), key=lambda item: item[1]['count'], reverse=True), start=1):
        running_defects += info['count']
        defect_table.append({
            'rank': idx,
            'defect_type': name,
            'count': info['count'],
            'impact': info['impact'],
            'share_pct': round((info['count'] / total_defects * 100), 1) if total_defects > 0 else 0,
            'cumulative_pct': round((running_defects / total_defects * 100), 1) if total_defects > 0 else 0
        })

    self_rejection_table = _self_rejection_breakdown(entry_ids, defect_type_id=defect_type_id)
    self_rejection_by_defect_type = {
        row['defect_type']: {
            'count': row['count'],
            'entries': row['entries'],
            'weight': row['weight']
        }
        for row in self_rejection_table
    }

    defect_counts = {}
    rejection_totals = {}
    rework_totals = {}
    if entry_ids:
        defect_counts_query = db.session.query(
            DailyRejection.production_entry_id,
            func.coalesce(func.sum(RejectionDefect.defect_count), 0)
        ).join(RejectionDefect)
        if defect_type_id:
            defect_counts_query = defect_counts_query.filter(RejectionDefect.defect_type_id == defect_type_id)
        defect_counts_query = defect_counts_query.filter(DailyRejection.production_entry_id.in_(entry_ids))\
            .group_by(DailyRejection.production_entry_id).all()
        defect_counts = {row[0]: int(row[1] or 0) for row in defect_counts_query}

        rejection_totals_query = db.session.query(
            DailyRejection.production_entry_id,
            func.coalesce(func.sum(DailyRejection.rj_pcs), 0)
        ).filter(DailyRejection.production_entry_id.in_(entry_ids))\
         .group_by(DailyRejection.production_entry_id).all()
        rejection_totals = {row[0]: int(row[1] or 0) for row in rejection_totals_query}

        rework_totals_query = db.session.query(
            ReworkLog.production_entry_id,
            func.coalesce(func.sum(ReworkLog.rework_qty), 0)
        ).filter(ReworkLog.production_entry_id.in_(entry_ids))\
         .group_by(ReworkLog.production_entry_id).all()
        rework_totals = {row[0]: int(row[1] or 0) for row in rework_totals_query}

    sorted_entries = sorted(entries, key=lambda e: ((e.production_date or datetime(1970, 1, 1).date()), e.id), reverse=True)
    production_summary = []
    for entry in sorted_entries[:20]:
        final_ok = int(entry.total_ok_quantity or 0)
        final_rejects = rejection_totals.get(entry.id, 0)
        rework_qty = rework_totals.get(entry.id, 0)
        defects_for_entry = defect_counts.get(entry.id, 0)
        total_produced = final_ok + final_rejects
        production_summary.append({
            'entry_no': entry.entry_no or '-',
            'production_date': entry.production_date,
            'customer': entry.customer.customer_name if entry.customer else '-',
            'section_number': entry.section_number or '-',
            'final_ok': final_ok,
            'final_rejects': final_rejects,
            'rework_qty': rework_qty,
            'total_produced': total_produced,
            'defect_count': defects_for_entry
        })

    period_days = (end_date - start_date).days + 1
    context = _dashboard_filter_options()
    return render_template('issues_analysis.html',
                          top_issues=defects[:10],
                          by_defect_type=by_defect_type,
                          defect_table=defect_table,
                          self_rejection_by_defect_type=self_rejection_by_defect_type,
                          self_rejection_table=self_rejection_table,
                          period_days=period_days,
                          start_date=start_date,
                          end_date=end_date,
                          start_datetime=start_datetime,
                          end_datetime=end_datetime,
                          start_datetime_value=start_datetime.strftime('%Y-%m-%dT%H:%M'),
                          end_datetime_value=end_datetime.strftime('%Y-%m-%dT%H:%M'),
                          production_summary=production_summary,
                          **context)


@dashboard_bp.route('/employee-performance')
@login_required
def employee_performance_dashboard():
    """Role-wise employee performance analytics dashboard."""
    start_datetime, end_datetime = _resolve_datetime_window(
        request.args.get('start_date'),
        request.args.get('end_date'),
        default_range=_default_dashboard_range(),
        days_param=request.args.get('days', type=int)
    )
    start_date = start_datetime.date()
    end_date = end_datetime.date()

    entries_query = ProductionEntry.query.filter(
        and_(ProductionEntry.production_date >= start_date, ProductionEntry.production_date <= end_date)
    )
    entries_query = _apply_entry_filters(entries_query)
    entries = entries_query.all()
    entry_ids = [e.id for e in entries]
    emp_code_filter = (request.args.get('emp_code') or '').strip()

    def _safe_pct(num_v, den_v):
        return (num_v / den_v * 100) if den_v and den_v > 0 else 0.0

    def _collect_role_rows(rel_attr, emp_attr, info_attr):
        stats = {}
        for entry in entries:
            final_ok = int(entry.total_ok_quantity or 0)
            planned = entry.planned_quantity or 0
            actual = entry.actual_quantity or 0
            rework = entry.rework_qty or 0
            self_rej = entry.self_rejection_qty or 0
            runtime = entry.total_time_taken_minutes or 0
            downtime = entry.downtime_minutes or 0
            ideal = entry.total_ideal_time_minutes or 0
            for rel in getattr(entry, rel_attr) or []:
                emp_id = getattr(rel, emp_attr, None)
                emp_info = getattr(rel, info_attr, None)
                if not emp_id or not emp_info:
                    continue
                stat = stats.setdefault(emp_id, {
                    'emp_id': emp_id,
                    'name': emp_info.emp_name or '-',
                    'code': emp_info.emp_code or '-',
                    'assignments_set': set(),
                    'planned_qty': 0.0,
                    'actual_qty': 0.0,
                    'final_ok_qty': 0.0,
                    'rework_qty': 0.0,
                    'self_rej_qty': 0.0,
                    'total_self_rejection_pcs': 0.0,
                    'runtime': 0.0,
                    'downtime': 0.0,
                    'ideal': 0.0
                })
                stat['assignments_set'].add(entry.id)
                stat['planned_qty'] += planned
                stat['actual_qty'] += actual
                stat['final_ok_qty'] += final_ok
                stat['rework_qty'] += rework
                stat['self_rej_qty'] += self_rej
                stat['total_self_rejection_pcs'] += self_rej
                stat['runtime'] += runtime
                stat['downtime'] += downtime
                stat['ideal'] += ideal
        rows = []
        for stat in stats.values():
            assignments = len(stat['assignments_set'])
            final_ok_qty = stat['final_ok_qty']
            planned_qty = stat['planned_qty']
            runtime = stat['runtime']
            downtime = stat['downtime']
            ideal = stat['ideal']
            efficiency = _safe_pct(final_ok_qty, planned_qty)
            availability = _safe_pct(runtime, runtime + downtime)
            performance = _safe_pct(ideal, runtime)
            quality = _safe_pct(final_ok_qty, final_ok_qty + stat['self_rej_qty'])
            score = (0.35 * efficiency) + (0.25 * availability) + (0.25 * quality) + (0.15 * performance)
            rows.append({
                'emp_id': stat['emp_id'],
                'name': stat['name'],
                'code': stat['code'],
                'assignments': assignments,
                'planned_qty': round(planned_qty, 1),
                'actual_qty': round(stat['actual_qty'], 1),
                'final_ok': round(final_ok_qty, 1),
                'rework_qty': round(stat['rework_qty'], 1),
                'self_rej_qty': round(stat['self_rej_qty'], 1),
                'total_self_rejection_pcs': round(stat['total_self_rejection_pcs'], 1),
                'efficiency': round(efficiency, 1),
                'availability': round(availability, 1),
                'performance': round(performance, 1),
                'quality': round(quality, 1),
                'score': round(min(max(score, 0), 100), 1)
            })
        rows.sort(key=lambda x: (x['score'], x['final_ok'], x['assignments']), reverse=True)
        if emp_code_filter:
            rows = [row for row in rows if emp_code_filter.lower() in (row['code'] or '').lower()]
        for i, row in enumerate(rows, start=1):
            row['rank'] = i
        return rows

    operator_rows = _collect_role_rows('operators', 'operator_emp_id', 'operator_info')
    supervisor_rows = _collect_role_rows('supervisors', 'supervisor_emp_id', 'supervisor_info')

    # Quality supervisor performance: driven by quality inspection volume and defect analysis depth.
    quality_q = db.session.query(
        DailyRejectionSupervisor.supervisor_emp_id,
        EmpMaster.emp_name,
        EmpMaster.emp_code,
        DailyRejectionSupervisor.rejection_id,
        DailyRejection.total_parts_inspected_qty,
        DailyRejection.rj_pcs,
        func.coalesce(ProductionEntry.actual_quantity, 0).label('actual_qty')
    ).join(EmpMaster, EmpMaster.emp_id == DailyRejectionSupervisor.supervisor_emp_id)\
     .join(DailyRejection, DailyRejection.id == DailyRejectionSupervisor.rejection_id)\
     .outerjoin(ProductionEntry, ProductionEntry.id == DailyRejection.production_entry_id)\
     .filter(DailyRejection.rejection_date >= start_date, DailyRejection.rejection_date <= end_date)

    customer_id = request.args.get('customer_id', type=int)
    section_number = (request.args.get('section_number') or request.args.get('section') or '').strip()
    cut_length = (request.args.get('cut_length') or request.args.get('cutlength') or '').strip()
    shift = (request.args.get('shift') or '').strip()
    if customer_id:
        quality_q = quality_q.filter(DailyRejection.customer_id == customer_id)
    if section_number:
        quality_q = quality_q.filter(DailyRejection.section_number.ilike(f"%{section_number}%"))
    if cut_length:
        try:
            quality_q = quality_q.filter(DailyRejection.length == float(cut_length))
        except ValueError:
            pass
    if shift:
        quality_q = quality_q.filter(DailyRejection.shift.ilike(f"%{shift}%"))
    if entry_ids:
        quality_q = quality_q.filter(DailyRejection.production_entry_id.in_(entry_ids))

    quality_assignments = quality_q.all()
    rej_ids = list({r[3] for r in quality_assignments})
    defect_map = {}
    if rej_ids:
        defect_rows = db.session.query(
            RejectionDefect.rejection_id,
            func.sum(RejectionDefect.defect_count).label('defect_pcs'),
            func.count(func.distinct(RejectionDefect.defect_type_id)).label('defect_types')
        ).filter(RejectionDefect.rejection_id.in_(rej_ids)).group_by(RejectionDefect.rejection_id).all()
        defect_map = {d[0]: {'defect_pcs': int(d[1] or 0), 'defect_types': int(d[2] or 0)} for d in defect_rows}

    quality_rows_map = {}
    for emp_id, emp_name, emp_code, rejection_id, inspected_qty, rejected_qty, actual_qty in quality_assignments:
        rec = quality_rows_map.setdefault(emp_id, {
            'emp_id': emp_id,
            'name': emp_name,
            'code': emp_code or '-',
            'inspections': 0,
            'actual_qty': 0.0,
            'inspected_qty': 0.0,
            'rejected_qty': 0.0,
            'defect_pcs': 0.0,
            'defect_types_total': 0.0
        })
        rec['inspections'] += 1
        rec['actual_qty'] += float(actual_qty or 0)
        rec['inspected_qty'] += float(inspected_qty or 0)
        rec['rejected_qty'] += float(rejected_qty or 0)
        dmeta = defect_map.get(rejection_id, {'defect_pcs': 0, 'defect_types': 0})
        rec['defect_pcs'] += float(dmeta['defect_pcs'])
        rec['defect_types_total'] += float(dmeta['defect_types'])

    quality_rows = list(quality_rows_map.values())
    max_inspections = max([r['inspections'] for r in quality_rows], default=0) or 1
    max_depth = max([_safe_pct(r['defect_pcs'], r['inspections']) for r in quality_rows], default=0) or 1
    max_types = max([_safe_pct(r['defect_types_total'], r['inspections']) for r in quality_rows], default=0) or 1

    for r in quality_rows:
        rej_rate = _safe_pct(r['rejected_qty'], r['inspected_qty'])
        analysis_depth = _safe_pct(r['defect_pcs'], r['inspections'])
        type_coverage = _safe_pct(r['defect_types_total'], r['inspections'])
        activity_score = _safe_pct(r['inspections'], max_inspections)
        depth_score = _safe_pct(analysis_depth, max_depth)
        coverage_score = _safe_pct(type_coverage, max_types)
        score = (0.40 * activity_score) + (0.35 * depth_score) + (0.25 * coverage_score)
        r['rejection_rate'] = round(rej_rate, 2)
        r['analysis_depth'] = round(analysis_depth, 2)
        r['type_coverage'] = round(type_coverage, 2)
        r['score'] = round(min(max(score, 0), 100), 1)
        r['actual_qty'] = round(r['actual_qty'], 1)
        r['inspected_qty'] = round(r['inspected_qty'], 1)
        r['rejected_qty'] = round(r['rejected_qty'], 1)
        r['defect_pcs'] = round(r['defect_pcs'], 1)

    quality_rows.sort(key=lambda x: (x['score'], x['inspections'], x['defect_pcs']), reverse=True)
    for i, row in enumerate(quality_rows, start=1):
        row['rank'] = i

    def _role_chart_payload(rows, label_field='score'):
        top = rows[:10]
        return {
            'labels': [f"{r['name']} ({r['code']})" for r in top],
            'score': [r.get('score', 0) for r in top],
            'efficiency': [r.get('efficiency', 0) for r in top],
            'quality': [r.get('quality', 0) for r in top],
            'actual_qty': [r.get('actual_qty', 0) for r in top],
            'final_ok': [r.get('final_ok', 0) for r in top],
            'assignments': [r.get('assignments', 0) for r in top],
            'rejection_rate': [r.get('rejection_rate', 0) for r in top],
            'inspections': [r.get('inspections', 0) for r in top],
            'analysis_depth': [r.get('analysis_depth', 0) for r in top]
        }

    period_days = (end_date - start_date).days + 1
    context = _dashboard_filter_options()
    return render_template(
        'employee_performance.html',
        start_date=start_date,
        end_date=end_date,
        period_days=period_days,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        start_datetime_value=start_datetime.strftime('%Y-%m-%dT%H:%M'),
        end_datetime_value=end_datetime.strftime('%Y-%m-%dT%H:%M'),
        operator_rows=operator_rows,
        supervisor_rows=supervisor_rows,
        quality_rows=quality_rows,
        operator_chart=json.dumps(_role_chart_payload(operator_rows)),
        supervisor_chart=json.dumps(_role_chart_payload(supervisor_rows)),
        quality_chart=json.dumps(_role_chart_payload(quality_rows)),
        **context
    )


@dashboard_bp.route('/api/chart-data/<chart_type>')
def get_chart_data(chart_type):
    """Get data for charts"""
    try:
        if chart_type == 'plan-vs-actual':
            days = request.args.get('days', 7, type=int)
            start_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            
            entries = ProductionEntry.query.filter(
                ProductionEntry.production_date >= start_date
            ).all()
            
            daily = {}
            for entry in entries:
                date_key = entry.production_date.isoformat()
                if date_key not in daily:
                    daily[date_key] = {'planned': 0, 'actual': 0}
                daily[date_key]['planned'] += entry.planned_quantity
                daily[date_key]['actual'] += entry.actual_quantity
            
            return jsonify({
                'dates': sorted(daily.keys()),
                'planned': [daily[d]['planned'] for d in sorted(daily.keys())],
                'actual': [daily[d]['actual'] for d in sorted(daily.keys())]
            })
        
        elif chart_type == 'machine-efficiency':
            machines = Machine.query.filter_by(status='Active').all()
            
            efficiency_data = []
            for machine in machines:
                entries = ProductionEntry.query.filter_by(machine_id=machine.id).all()
                total_planned = sum(e.planned_quantity for e in entries)
                total_actual = sum(e.actual_quantity for e in entries)
                eff = (total_actual / total_planned * 100) if total_planned > 0 else 0
                efficiency_data.append({'machine': machine.machine_name, 'efficiency': round(eff, 2)})
            
            return jsonify(efficiency_data)
        
    except Exception as e:
        logger.error(f'Error getting chart data: {str(e)}')
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/oee-report')
@login_required
def oee_report_download():
    """Download OEE summary report for selected dashboard filters."""
    start_date = _parse_datetime(request.args.get('start_date'))
    end_date = _parse_datetime(request.args.get('end_date'))
    selected_date = _parse_datetime(request.args.get('date'))
    if selected_date and not start_date and not end_date:
        start_date = selected_date
        end_date = selected_date
    if not start_date and not end_date:
        start_date = datetime.now(timezone.utc).date()
        end_date = start_date
    if start_date and not end_date:
        end_date = start_date
    if end_date and not start_date:
        start_date = end_date
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    query = ProductionEntry.query.filter(
        and_(ProductionEntry.production_date >= start_date, ProductionEntry.production_date <= end_date)
    )
    query = _apply_entry_filters(query)
    entries = query.all()
    oee = _compute_oee_summary(entries)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Metric', 'Value'])
    writer.writerow(['Start Date', start_date.isoformat()])
    writer.writerow(['End Date', end_date.isoformat()])
    writer.writerow(['Entries', len(entries)])
    writer.writerow(['Total Planned Qty', oee['total_planned']])
    writer.writerow(['Total Actual Qty', oee['total_actual']])
    writer.writerow(['Total OK Qty', oee['total_ok']])
    writer.writerow(['Total Rejected Pcs', oee['total_rejected_pcs']])
    writer.writerow(['Total Downtime Minutes', oee['total_downtime']])
    writer.writerow(['Operating Minutes', round(oee['total_operating_minutes'], 2)])
    writer.writerow(['Planned Minutes', round(oee['total_planned_minutes'], 2)])
    writer.writerow(['Ideal Minutes', round(oee['total_ideal_minutes'], 2)])
    writer.writerow(['Availability %', round(oee['availability'], 2)])
    writer.writerow(['Performance %', round(oee['performance'], 2)])
    writer.writerow(['Quality %', round(oee['quality'], 2)])
    writer.writerow(['OEE %', round(oee['oee'], 2)])
    csv_data = output.getvalue()
    output.close()
    filename = f"oee_report_{start_date.isoformat()}_{end_date.isoformat()}.csv"
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
