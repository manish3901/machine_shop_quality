"""
API Routes for Production Data
RESTful endpoints for production entry management
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta, timezone
from models import (
    db, ProductionEntry, ProductionIssue, EmpMaster, AuditLog, DowntimeReason, ReworkLog
)
from sqlalchemy import func, and_, or_
import logging

logger = logging.getLogger(__name__)
api_bp = Blueprint('api', __name__)


@api_bp.route('/production-entries/check-overlap', methods=['GET'])
def check_overlap_detailed():
    """
    Detailed overlap check for production entries.
    Query params: machine_id, start_time, end_time, [exclude_id]
    Returns entry details if overlap exists, else null.
    """
    machine_id = request.args.get('machine_id', type=int)
    start_time_str = request.args.get('start_time')
    end_time_str = request.args.get('end_time')
    exclude_id = request.args.get('exclude_id', type=int)

    if not all([machine_id, start_time_str, end_time_str]):
        return jsonify({'error': 'Missing parameters'}), 400

    try:
        start_time = datetime.fromisoformat(start_time_str)
        end_time = datetime.fromisoformat(end_time_str)
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    if start_time >= end_time:
        return jsonify({'error': 'Start time must be earlier than end time'}), 400

    query = ProductionEntry.query.filter(
        ProductionEntry.machine_id == machine_id,
        ProductionEntry.start_time < end_time,
        ProductionEntry.end_time > start_time
    )

    if exclude_id:
        query = query.filter(ProductionEntry.id != exclude_id)

    overlap = query.first()

    if not overlap:
        return jsonify({'overlap': False})

    # Return detailed conflict data
    return jsonify({
        'overlap': True,
        'entry': {
            'id': overlap.id,
            'entry_no': overlap.entry_no,
            'machine_name': overlap.machine.machine_name if overlap.machine else 'Unknown',
            'start_time': overlap.start_time.isoformat(),
            'end_time': overlap.end_time.isoformat(),
            'customer_name': overlap.customer.customer_name if overlap.customer else 'Unknown',
            'section_number': overlap.section_number or 'N/A',
            'cutlength': overlap.cutlength or 'N/A',
            'actual_quantity': overlap.actual_quantity or 0,
            'processes': [op.operation_type.operation_name for op in overlap.operations] if overlap.operations else []
        }
    })


# ==================== PRODUCTION ENTRY ENDPOINTS ====================

@api_bp.route('/production-entries', methods=['POST'])
def create_production_entry():
    """
    Create a new production entry
    POST /api/production-entries
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['production_date', 'shift', 'machine_id', 'customer_id', 'planned_quantity']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Parse date
        prod_date = datetime.strptime(data['production_date'], '%Y-%m-%d').date()
        
        # Create entry
        entry = ProductionEntry(
            production_date=prod_date,
            shift=data['shift'].upper(),
            shift_index={'A': 1, 'B': 2, 'C': 3}.get(data['shift'].upper(), 1),
            machine_id=data['machine_id'],
            customer_id=data['customer_id'],
            operation_type_id=data.get('operation_type_id'),
            operator_emp_id=data.get('operator_id'), 
            section_number=data.get('section_number'),
            cutlength=data.get('cutlength'),
            planned_quantity=data['planned_quantity'],
            actual_quantity=data.get('actual_quantity', 0),
            cycle_time_seconds=data.get('cycle_time_seconds', 0),
            downtime_minutes=data.get('downtime_minutes', 0),
            remarks=data.get('remarks'),
            created_by=data.get('created_by', 'system')
        )
        
        # Compute variance
        entry.compute_variance()
        
        db.session.add(entry)
        db.session.commit()
        
        # Log audit trail
        audit = AuditLog(
            entity_type='ProductionEntry',
            entity_id=entry.id,
            action='CREATE',
            changed_by=data.get('created_by', 'system'),
            changes={'created': True}
        )
        db.session.add(audit)
        db.session.commit()
        
        logger.info(f'Production entry created: {entry.id}')
        
        return jsonify({
            'id': entry.id,
            'message': 'Production entry created successfully'
        }), 201
        
    except Exception as e:
        logger.error(f'Error creating production entry: {str(e)}')
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/production-entries/<int:entry_id>', methods=['PUT'])
def update_production_entry(entry_id):
    """
    Update a production entry
    PUT /api/production-entries/<id>
    """
    try:
        entry = ProductionEntry.query.get(entry_id)
        if not entry:
            return jsonify({'error': 'Entry not found'}), 404
        
        data = request.get_json()
        
        # Track changes for audit
        changes = {}
        
        # Update fields
        fields_to_update = {
            'planned_quantity': 'planned_quantity',
            'actual_quantity': 'actual_quantity',
            'cycle_time_seconds': 'cycle_time_seconds',
            'downtime_minutes': 'downtime_minutes',
            'remarks': 'remarks',
            'operator_id': 'operator_emp_id', 
            'section_number': 'section_number',
            'cutlength': 'cutlength'
        }
        
        for api_field, db_field in fields_to_update.items():
            if api_field in data:
                old_value = getattr(entry, db_field)
                new_value = data[api_field]
                if old_value != new_value:
                    setattr(entry, db_field, new_value)
                    changes[db_field] = {'old': old_value, 'new': new_value}
        
        # Recompute variance if quantities changed
        if 'planned_quantity' in data or 'actual_quantity' in data:
            entry.compute_variance()
        
        entry.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        
        # Log audit trail
        if changes:
            audit = AuditLog(
                entity_type='ProductionEntry',
                entity_id=entry_id,
                action='UPDATE',
                changed_by=data.get('updated_by', 'system'),
                changes=changes
            )
            db.session.add(audit)
            db.session.commit()
        
        logger.info(f'Production entry updated: {entry_id}')
        
        return jsonify({'message': 'Production entry updated successfully'}), 200
        
    except Exception as e:
        logger.error(f'Error updating production entry: {str(e)}')
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/production-entries/<int:entry_id>', methods=['GET'])
def get_production_entry(entry_id):
    """Get a single production entry"""
    entry = ProductionEntry.query.get(entry_id)
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404

    rework_map = {}
    rework_history = []
    total_rework_qty = entry.rework_qty or 0
    for log in entry.rework_logs:
        label = log.defect_type.defect_name if log.defect_type else f'Defect-{log.defect_type_id}'
        if label not in rework_map:
            rework_map[label] = {
                'defect_type_id': log.defect_type_id,
                'defect_type': label,
                'rework_qty': 0
            }
        rework_map[label]['rework_qty'] += log.rework_qty or 0
        rework_history.append({
            'defect_type_id': log.defect_type_id,
            'defect_type': label,
            'rework_qty': log.rework_qty,
            'remarks': log.remarks,
            'created_at': log.created_at.isoformat() if log.created_at else None,
            'created_by': log.created_by
        })
    
    return jsonify({
        'id': entry.id,
        'entry_no': entry.entry_no,
        'production_date': entry.production_date.isoformat(),
        'shift': entry.shift,
        'start_time': entry.start_time.isoformat() if entry.start_time else None,
        'end_time': entry.end_time.isoformat() if entry.end_time else None,
        'shed_name': entry.machine.shed.shed_name if entry.machine and entry.machine.shed else None,
        'machine_name': entry.machine.machine_name,
        'customer_name': entry.customer.customer_name,
        'section_number': entry.section_number,
        'cutlength': entry.cutlength,
        'operator_name': entry.operator.emp_name if entry.operator else None,
        'planned_quantity': entry.planned_quantity,
        'actual_quantity': entry.actual_quantity,
        'self_rejection_qty': entry.self_rejection_qty or 0,
        'total_self_rejection_pcs': entry.self_rejection_qty or 0,
        'self_rejection_weight_per_pcs': entry.self_rejection_weight_per_pcs or 0,
        'machining_scrap_weight_kg': entry.machining_scrap_weight_kg or 0,
        'total_machining_scrap_kg': entry.machining_scrap_weight_kg or 0,
        'total_self_rejection_kg': round((entry.self_rejection_weight_per_pcs or 0) * (entry.self_rejection_qty or 0), 3),
        'total_self_rejection_all_kg': round(((entry.self_rejection_weight_per_pcs or 0) * (entry.self_rejection_qty or 0)) + (entry.machining_scrap_weight_kg or 0), 3),
        'self_rejection_details': [{
            'defect_type_id': row.defect_type_id,
            'defect_type': row.defect_type.defect_name if row.defect_type else None,
            'reject_qty': row.reject_qty or 0
        } for row in entry.self_rejection_defects],
        'qty_variance': entry.qty_variance,
        'qty_variance_percent': entry.qty_variance_percent,
        'efficiency': entry.efficiency,
        'total_ok': entry.total_ok_quantity,
        'rework_qty': total_rework_qty,
        'rework_details': list(rework_map.values()),
        'rework_history': rework_history,
        'ideal_cycle_time': entry.ideal_cycle_time,
        'total_ideal_time_minutes': entry.total_ideal_time_minutes,
        'total_time_taken_minutes': entry.total_time_taken_minutes,
        'downtime_minutes': entry.downtime_minutes,
        'remarks': entry.remarks,
        'created_by': entry.created_by,
        'created_at': entry.created_at.isoformat(),
        'operators_detailed': [{
            'name': op.operator_info.emp_name,
            'code': op.operator_info.emp_code,
            'start_time': op.start_time.isoformat() if op.start_time else None,
            'end_time': op.end_time.isoformat() if op.end_time else None
        } for op in entry.operators],
        'operations_detailed': [{
            'id': op.operation_type_id,
            'name': op.operation_type.operation_name if op.operation_type else None
        } for op in entry.operations],
        'supervisors_detailed': [{
            'name': sup.supervisor_info.emp_name,
            'code': sup.supervisor_info.emp_code,
            'start_time': sup.start_time.isoformat() if sup.start_time else None,
            'end_time': sup.end_time.isoformat() if sup.end_time else None
        } for sup in entry.supervisors],
        'planned_downtime': [{
            'reason': pd.reason.reason_name,
            'duration': pd.duration_minutes
        } for pd in entry.planned_downtime],
        'issues': [{
            'issue_type': issue.issue_type.issue_name,
            'impact_minutes': issue.impact_minutes,
            'description': issue.custom_remark
        } for issue in entry.issues],
        'rejection': {
            'id': entry.rejection.id,
            'rejection_datetime': entry.rejection.rejection_datetime.isoformat(),
            'total_parts_inspected_qty': entry.rejection.total_parts_inspected_qty,
            'defect_category': entry.rejection.defect_category,
            'rejection_reason': entry.rejection.rejection_reason,
            'rj_pcs': entry.rejection.rj_pcs,
            'weight_per_pcs': entry.rejection.weight_per_pcs,
            'rj_weight': entry.rejection.rj_weight,
            'supervisors': [{
                'name': sup.supervisor_info.emp_name,
                'code': sup.supervisor_info.emp_code,
                'start_time': sup.start_time.strftime('%H:%M') if sup.start_time else None,
                'end_time': sup.end_time.strftime('%H:%M') if sup.end_time else None
            } for sup in entry.rejection.supervisors],
            'defects': [{
                'name': d.defect_type.defect_name,
                'count': d.defect_count
            } for d in entry.rejection.defects]
        } if entry.rejection else None
    }), 200


@api_bp.route('/production-entries', methods=['GET'])
def list_production_entries():
    """
    List production entries with filtering
    GET /api/production-entries?date=2024-01-01&machine_id=1&shift=A
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        
        query = ProductionEntry.query
        
        # Filters
        if request.args.get('production_date'):
            prod_date = datetime.strptime(request.args.get('production_date'), '%Y-%m-%d').date()
            query = query.filter_by(production_date=prod_date)
        
        if request.args.get('machine_id'):
            query = query.filter_by(machine_id=request.args.get('machine_id', type=int))
        
        if request.args.get('shift'):
            query = query.filter_by(shift=request.args.get('shift').upper())
        
        if request.args.get('customer_id'):
            query = query.filter_by(customer_id=request.args.get('customer_id', type=int))
        
        # Date range filter
        if request.args.get('start_date'):
            start = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d').date()
            query = query.filter(ProductionEntry.production_date >= start)
        
        if request.args.get('end_date'):
            end = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d').date()
            query = query.filter(ProductionEntry.production_date <= end)
        
        # Sorting
        query = query.order_by(ProductionEntry.production_date.desc(), 
                              ProductionEntry.shift_index.desc())
        
        paginated = query.paginate(page=page, per_page=per_page)
        
        entries = [{
            'id': entry.id,
            'date': entry.production_date.isoformat(),
            'shift': entry.shift,
            'machine': entry.machine.machine_name,
            'customer': entry.customer.customer_name,
            'planned': entry.planned_quantity,
            'actual': entry.actual_quantity,
            'variance': entry.qty_variance,
            'variance_pct': round(entry.qty_variance_percent, 2) if entry.qty_variance_percent else 0,
            'efficiency': round(entry.efficiency, 2)
        } for entry in paginated.items]
        
        return jsonify({
            'entries': entries,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': paginated.total,
                'pages': paginated.pages
            }
        }), 200
        
    except Exception as e:
        logger.error(f'Error listing entries: {str(e)}')
        return jsonify({'error': str(e)}), 500


@api_bp.route('/production-entries/<int:entry_id>/issues', methods=['POST'])
def add_issue_to_entry(entry_id):
    """Add an issue/remark to a production entry"""
    try:
        entry = ProductionEntry.query.get(entry_id)
        if not entry:
            return jsonify({'error': 'Entry not found'}), 404
        
        data = request.get_json()
        
        issue = ProductionIssue(
            production_entry_id=entry_id,
            issue_type_id=data.get('issue_type_id'),
            custom_remark=data.get('custom_remark'),
            impact_minutes=data.get('impact_minutes', 0)
        )
        
        db.session.add(issue)
        db.session.commit()
        
        return jsonify({'id': issue.id, 'message': 'Issue added'}), 201
        
    except Exception as e:
        logger.error(f'Error adding issue: {str(e)}')
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ==================== ANALYTICS ENDPOINTS ====================

@api_bp.route('/analytics/daily-summary', methods=['GET'])
def get_daily_summary():
    """Get daily production summary"""
    try:
        prod_date = request.args.get('date')
        if not prod_date:
            prod_date = datetime.now(timezone.utc).date()
        else:
            prod_date = datetime.strptime(prod_date, '%Y-%m-%d').date()
        
        entries = ProductionEntry.query.filter_by(production_date=prod_date).all()
        
        summary = {
            'date': prod_date.isoformat(),
            'total_machines': len(set(e.machine_id for e in entries)),
            'total_entries': len(entries),
            'total_planned': sum(e.planned_quantity for e in entries),
            'total_actual': sum(e.actual_quantity for e in entries),
            'total_downtime_minutes': sum(e.downtime_minutes for e in entries),
            'efficiency': round((sum(e.actual_quantity for e in entries) / 
                                sum(e.planned_quantity for e in entries) * 100), 2) 
                        if sum(e.planned_quantity for e in entries) > 0 else 0,
            'by_shift': get_shift_summary(entries)
        }
        
        return jsonify(summary), 200
        
    except Exception as e:
        logger.error(f'Error getting daily summary: {str(e)}')
        return jsonify({'error': str(e)}), 500


def get_shift_summary(entries):
    """Helper function to get summary by shift"""
    shifts = {'A': [], 'B': [], 'C': []}
    
    for entry in entries:
        shifts[entry.shift].append(entry)
    
    result = {}
    for shift, shift_entries in shifts.items():
        if shift_entries:
            result[shift] = {
                'total_planned': sum(e.planned_quantity for e in shift_entries),
                'total_actual': sum(e.actual_quantity for e in shift_entries),
                'machines': len(set(e.machine_id for e in shift_entries)),
                'efficiency': round((sum(e.actual_quantity for e in shift_entries) / 
                                   sum(e.planned_quantity for e in shift_entries) * 100), 2)
                            if sum(e.planned_quantity for e in shift_entries) > 0 else 0
            }
    
    return result


@api_bp.route('/analytics/machine-performance', methods=['GET'])
def get_machine_performance():
    """Machine utilization and performance metrics"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date:
            start_date = (datetime.now(timezone.utc) - timedelta(days=30)).date()
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        if not end_date:
            end_date = datetime.now(timezone.utc).date()
        else:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        entries = ProductionEntry.query.filter(
            and_(
                ProductionEntry.production_date >= start_date,
                ProductionEntry.production_date <= end_date
            )
        ).all()
        
        machines = {}
        for entry in entries:
            if entry.machine_id not in machines:
                machines[entry.machine_id] = {
                    'machine_name': entry.machine.machine_name,
                    'total_planned': 0,
                    'total_actual': 0,
                    'total_downtime': 0,
                    'entries': 0
                }
            
            machines[entry.machine_id]['total_planned'] += entry.planned_quantity
            machines[entry.machine_id]['total_actual'] += entry.actual_quantity
            machines[entry.machine_id]['total_downtime'] += entry.downtime_minutes
            machines[entry.machine_id]['entries'] += 1
        
        # Calculate efficiency for each machine
        performance = []
        for machine_id, data in machines.items():
            efficiency = (data['total_actual'] / data['total_planned'] * 100) if data['total_planned'] > 0 else 0
            performance.append({
                'machine_id': machine_id,
                'machine_name': data['machine_name'],
                'total_planned': data['total_planned'],
                'total_actual': data['total_actual'],
                'efficiency_percent': round(efficiency, 2),
                'avg_downtime_minutes': round(data['total_downtime'] / data['entries'], 2),
                'entries_count': data['entries']
            })
        
        # Sort by efficiency
        performance.sort(key=lambda x: x['efficiency_percent'])
        
        return jsonify({
            'period': {'start': start_date.isoformat(), 'end': end_date.isoformat()},
            'machines': performance
        }), 200
        
    except Exception as e:
        logger.error(f'Error getting machine performance: {str(e)}')
        return jsonify({'error': str(e)}), 500


@api_bp.route('/analytics/top-issues', methods=['GET'])
def get_top_issues():
    """Get top issues causing deviations"""
    try:
        start_date = request.args.get('start_date')
        days = request.args.get('days', 30, type=int)
        
        if not start_date:
            start_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        end_date = datetime.now(timezone.utc).date()
        
        # Get issues in the period
        issues = db.session.query(
            IssueType.issue_name,
            IssueType.category,
            func.count(ProductionIssue.id).label('count'),
            func.sum(ProductionIssue.impact_minutes).label('total_impact')
        ).join(
            ProductionIssue
        ).join(
            ProductionEntry
        ).filter(
            and_(
                ProductionEntry.production_date >= start_date,
                ProductionEntry.production_date <= end_date
            )
        ).group_by(
            IssueType.id, IssueType.issue_name, IssueType.category
        ).order_by(
            func.count(ProductionIssue.id).desc()
        ).limit(10).all()
        
        result = [{
            'issue_name': issue[0],
            'category': issue[1],
            'count': issue[2],
            'total_impact_minutes': issue[3] or 0
        } for issue in issues]
        
        return jsonify({
            'period': {'start': start_date.isoformat(), 'end': end_date.isoformat()},
            'top_issues': result
        }), 200
        
    except Exception as e:
        logger.error(f'Error getting top issues: {str(e)}')
        return jsonify({'error': str(e)}), 500


# ==================== CSV BULK UPLOAD ====================

@api_bp.route('/import/csv', methods=['POST'])
def import_csv():
    """
    Bulk import production entries from CSV
    CSV columns: production_date, shift, machine_id, customer_id, planned_quantity, actual_quantity, remarks
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if not file.filename.endswith('.csv'):
            return jsonify({'error': 'Only CSV files allowed'}), 400
        
        import csv
        import io
        
        stream = io.StringIO(file.stream.read().decode('utf8'), newline=None)
        csv_reader = csv.DictReader(stream)
        
        imported = 0
        errors = []
        
        for row_num, row in enumerate(csv_reader, 1):
            try:
                entry = ProductionEntry(
                    production_date=datetime.strptime(row['production_date'], '%Y-%m-%d').date(),
                    shift=row['shift'].upper(),
                    shift_index={'A': 1, 'B': 2, 'C': 3}.get(row['shift'].upper(), 1),
                    machine_id=int(row['machine_id']),
                    customer_id=int(row['customer_id']),
                    planned_quantity=int(row['planned_quantity']),
                    actual_quantity=int(row.get('actual_quantity', 0)),
                    remarks=row.get('remarks'),
                    created_by=request.args.get('user', 'csv_import')
                )
                entry.compute_variance()
                db.session.add(entry)
                imported += 1
                
            except Exception as e:
                errors.append(f'Row {row_num}: {str(e)}')
        
        db.session.commit()
        
        return jsonify({
            'imported': imported,
            'errors': errors,
            'message': f'{imported} entries imported successfully'
        }), 200
        
    except Exception as e:
        logger.error(f'Error importing CSV: {str(e)}')
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/downtime-reasons', methods=['GET'])
def get_downtime_reasons():
    """Get list of active planned downtime reasons"""
    status = request.args.get('status', 'Active')
    reasons = DowntimeReason.query.filter_by(status=status).all()
    return jsonify([{
        'id': r.id,
        'reason_name': r.reason_name
    } for r in reasons])
