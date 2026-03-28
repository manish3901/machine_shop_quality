"""
Database Models for Machine Shop Production Planning
Tracks daily production for CNC and VMC machines across shifts (A, B, C)
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, Index

db = SQLAlchemy()

# ==================== TENANT / MULTI-TENANCY ====================

class Tenant(db.Model):
    """Configuration for multi-tenancy/department scaling"""
    __tablename__ = 'ms_tenants'
    
    company_id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), nullable=False)
    dept_id = db.Column(db.Integer, nullable=False)
    dept_code = db.Column(db.String(20), nullable=False)
    
    def __repr__(self):
        return f'<Tenant {self.company_name} - {self.dept_code}>'

# ==================== MASTER DATA TABLES ====================

class MachineShed(db.Model):
    """Master table for machine sheds / shop-floor areas."""
    __tablename__ = 'ms_machine_sheds'

    id = db.Column(db.Integer, primary_key=True)
    shed_name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='Active')
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    machines = db.relationship('Machine', backref='shed', lazy=True)

    def __repr__(self):
        return f'<MachineShed {self.shed_name}>'


class MachineType(db.Model):
    """Master table for machine types."""
    __tablename__ = 'ms_machine_types'

    id = db.Column(db.Integer, primary_key=True)
    type_name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='Active')
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<MachineType {self.type_name}>'


class Machine(db.Model):
    """Master table for machines"""
    __tablename__ = 'ms_machines'
    
    id = db.Column(db.Integer, primary_key=True)
    machine_name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    machine_type = db.Column(db.String(20), nullable=False)  # CNC, VMC, Lathe, etc.
    status = db.Column(db.String(20), default='Active')  # Active, Inactive, Maintenance
    shed_id = db.Column(db.Integer, db.ForeignKey('ms_machine_sheds.id'), index=True)
    monthly_capacity = db.Column(db.Integer, default=0) # Additional baseline capacity per month
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    production_entries = db.relationship('ProductionEntry', backref='machine', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Machine {self.machine_name}>'


class MachineTarget(db.Model):
    """Monthly targets for a machine"""
    __tablename__ = 'ms_machine_targets'
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('ms_machines.id'), nullable=False, index=True)
    target_month = db.Column(db.String(7), nullable=False, index=True)  # Format: YYYY-MM
    target_qty = db.Column(db.Integer, nullable=False, default=0)
    capacity = db.Column(db.Integer, nullable=False, default=0)
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    machine = db.relationship('Machine', backref=db.backref('targets', lazy=True, cascade='all, delete-orphan'))
    
    __table_args__ = (
        db.UniqueConstraint('machine_id', 'target_month', name='ms_uix_machine_month_target'),
    )
    
    def __repr__(self):
        return f'<MachineTarget {self.machine_id} {self.target_month}>'


class Customer(db.Model):
    """Master table for customers"""
    __tablename__ = 'ms_customers'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    customer_code = db.Column(db.String(20))
    status = db.Column(db.String(20), default='Active')
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    production_entries = db.relationship('ProductionEntry', backref='customer', lazy=True)
    
    def __repr__(self):
        return f'<Customer {self.customer_name}>'


class OperationType(db.Model):
    """Master table for operation types/descriptions"""
    __tablename__ = 'ms_operation_types'
    
    id = db.Column(db.Integer, primary_key=True)
    operation_name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    standard_cycle_time_seconds = db.Column(db.Integer)  # in seconds
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    production_entries = db.relationship('ProductionEntry', backref='operation_type_obj', lazy=True)
    
    def __repr__(self):
        return f'<OperationType {self.operation_name}>'


class IssueType(db.Model):
    """Master table for common issues/remarks"""
    __tablename__ = 'ms_issue_types'
    
    id = db.Column(db.Integer, primary_key=True)
    issue_name = db.Column(db.String(100), unique=True, nullable=False)
    category = db.Column(db.String(50), nullable=False)  # NO_OPERATOR, NO_MATERIAL, QC_ISSUE, BREAKDOWN, SETUP_DELAY, TOOL_CHANGE
    severity = db.Column(db.String(20), default='Medium')  # Low, Medium, High, Critical
    description = db.Column(db.Text)
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    entries_issues = db.relationship('ProductionIssue', backref='issue_type', lazy=True)
    
    def __repr__(self):
        return f'<IssueType {self.issue_name}>'


class EmpMaster(db.Model):
    """
    Read-only mapping to shared MOA emp_master table.
    We do not manage schema here, just map to it.
    """
    __tablename__ = 'emp_master'
    __table_args__ = {'extend_existing': True} 
    
    emp_id = db.Column(db.Integer, primary_key=True)
    emp_code = db.Column(db.String(50), unique=True)
    emp_name = db.Column(db.String(100))
    designation = db.Column(db.String(100))
    status = db.Column(db.String(20))
    
    # We don't define backrefs here to avoid conflict if other apps define them, 
    # but we can use backref from ProductionEntry
    
    def __repr__(self):
        return f'<EmpMaster {self.emp_name}>'


# ==================== TRANSACTION TABLES ====================

class ProductionEntryOperator(db.Model):
    """Mapping table for multiple operators per production entry"""
    __tablename__ = 'ms_production_entry_operators'
    
    id = db.Column(db.Integer, primary_key=True)
    production_entry_id = db.Column(db.Integer, db.ForeignKey('ms_production_entries.id'), nullable=False, index=True)
    operator_emp_id = db.Column(db.Integer, db.ForeignKey('emp_master.emp_id'), nullable=False, index=True)
    
    # Relationship back to employee info
    operator_info = db.relationship('EmpMaster')
    
    # NEW: Operator working times
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)


class DailyRejectionSupervisor(db.Model):
    """Mapping table for multiple quality supervisors per rejection entry"""
    __tablename__ = 'ms_daily_rejection_supervisors'
    
    id = db.Column(db.Integer, primary_key=True)
    rejection_id = db.Column(db.Integer, db.ForeignKey('ms_daily_rejections.id'), nullable=False, index=True)
    supervisor_emp_id = db.Column(db.Integer, db.ForeignKey('emp_master.emp_id'), nullable=False, index=True)
    
    # Relationship back to employee info
    supervisor_info = db.relationship('EmpMaster')
    
    # NEW: Supervisor inspection times
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)


class ProductionEntryOperation(db.Model):
    """Mapping table for multiple operations per production entry"""
    __tablename__ = 'ms_production_entry_operations'
    
    id = db.Column(db.Integer, primary_key=True)
    production_entry_id = db.Column(db.Integer, db.ForeignKey('ms_production_entries.id'), nullable=False, index=True)
    operation_type_id = db.Column(db.Integer, db.ForeignKey('ms_operation_types.id'), nullable=False, index=True)
    
    # Relationship back to operation type
    operation_type = db.relationship('OperationType')



class ProductionEntrySupervisor(db.Model):
    """Mapping table for multiple shift supervisors per production entry"""
    __tablename__ = 'ms_production_entry_supervisors'
    
    id = db.Column(db.Integer, primary_key=True)
    production_entry_id = db.Column(db.Integer, db.ForeignKey('ms_production_entries.id'), nullable=False, index=True)
    supervisor_emp_id = db.Column(db.Integer, db.ForeignKey('emp_master.emp_id'), nullable=False, index=True)
    
    # Relationship back to employee info
    supervisor_info = db.relationship('EmpMaster')
    
    # Supervisor shift times
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)


class ProductionEntry(db.Model):
    """Main production data - daily entry form data"""
    __tablename__ = 'ms_production_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    entry_no = db.Column(db.String(20), unique=True, index=True)
    
    # Date & Shift info
    production_date = db.Column(db.Date, nullable=False, index=True)
    shift = db.Column(db.String(100), nullable=False)  # Multiple shifts separated by comma (e.g. "A, B")
    shift_index = db.Column(db.Integer)  # 1 for A shift, 2 for B shift, 3 for C shift (for sorting)
    
    # NEW: Production run times
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    
    # Machine & Customer info
    machine_id = db.Column(db.Integer, db.ForeignKey('ms_machines.id'), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('ms_customers.id'), nullable=False)
    operation_type_id = db.Column(db.Integer, db.ForeignKey('ms_operation_types.id'))
    
    # Job Details (Moved from Machine Master to Transaction)
    section_number = db.Column(db.String(50))
    cutlength = db.Column(db.Float)
    
    # Operator info (Linked to shared emp_master)
    operator_emp_id = db.Column(db.Integer, db.ForeignKey('emp_master.emp_id'))
    operator = db.relationship('EmpMaster', backref='production_entries')
    
    # Check if we need to store name as text backup? 
    # Maybe good practice in case emp is deleted, but standard FK is better for consistency.
    # operator_name = db.Column(db.String(100)) 
    
    # Planned vs Actual
    planned_quantity = db.Column(db.Integer, nullable=False)
    actual_quantity = db.Column(db.Integer, default=0)
    
    # Cycle time tracking
    ideal_cycle_time = db.Column(db.Float)  # Ideal time in seconds (from master)
    actual_cycle_time = db.Column(db.Float) # Actual time in seconds (per piece)
    
    # Total time tracking (minutes)
    total_time_taken_minutes = db.Column(db.Integer, default=0) # Total run time
    total_ideal_time_minutes = db.Column(db.Float, default=0.0) # actual_qty * ideal_cycle_time / 60
    downtime_minutes = db.Column(db.Integer, default=0)
    
    # NEW: Self-rejection pieces count (recorded by operator)
    self_rejection_qty = db.Column(db.Integer, default=0)
    self_rejection_weight_per_pcs = db.Column(db.Float, default=0.0)
    machining_scrap_weight_kg = db.Column('self_rejection_weight', db.Float, default=0.0)
    
    # General remarks
    remarks = db.Column(db.Text)
    
    # Timestamps
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.String(100))  # User ID who created the entry
    
    # NEW: Rework tracking
    rework_qty = db.Column(db.Integer, default=0)
    
    # Relationships
    issues = db.relationship('ProductionIssue', backref='production_entry', lazy=True, cascade='all, delete-orphan')
    evidence = db.relationship('Evidence', backref='production_entry', lazy=True, cascade='all, delete-orphan')
    operators = db.relationship('ProductionEntryOperator', backref='production_entry', lazy=True, cascade='all, delete-orphan')
    supervisors = db.relationship('ProductionEntrySupervisor', backref='production_entry', lazy=True, cascade='all, delete-orphan')
    operations = db.relationship('ProductionEntryOperation', backref='production_entry', lazy=True, cascade='all, delete-orphan')
    rejection = db.relationship('DailyRejection', backref=db.backref('production_entry_obj', uselist=False), uselist=False)
    planned_downtime = db.relationship('ProductionPlannedDowntime', backref='production_entry', lazy=True, cascade='all, delete-orphan')
    rework_logs = db.relationship('ReworkLog', backref='production_entry', lazy=True, cascade='all, delete-orphan')
    self_rejection_defects = db.relationship('ProductionSelfRejectionDefect', backref='production_entry', lazy=True, cascade='all, delete-orphan')
    
    # Indexes for common queries
    __table_args__ = (
        Index('ms_idx_prod_date_shift_machine', 'production_date', 'shift', 'machine_id'),
        Index('ms_idx_prod_date_machine', 'production_date', 'machine_id'),
    )
    
    def __repr__(self):
        return f'<ProductionEntry {self.machine_id} {self.production_date} {self.shift}>'
    
    # Computed columns for production variance
    qty_variance = db.Column(db.Integer, nullable=False, default=0)
    qty_variance_percent = db.Column(db.Float, nullable=False, default=0.0)


    @property
    def total_ok_quantity(self):
        """Final OK quantity after quality rejection and rework adjustments.

        Rework logging reduces the remaining rejection balance (`rejection.rj_pcs`)
        and also tracks the restored pieces separately in `rework_qty`. Because the
        rejection balance is already net of rework, adding `rework_qty` again would
        double count recovered pieces.
        """
        produced_ok = self.actual_quantity or 0
        remaining_rejected = getattr(self.rejection, 'rj_pcs', 0) if self.rejection else 0
        return max(0, produced_ok - remaining_rejected)


    @property
    def efficiency(self):
        """Calculate efficiency percentage"""
        if self.planned_quantity and self.planned_quantity > 0:
            return (float(self.total_ok_quantity) / self.planned_quantity) * 100
        return 0.0


class ProductionIssue(db.Model):
    """Issues/remarks linked to production entries"""
    __tablename__ = 'ms_production_issues'
    
    id = db.Column(db.Integer, primary_key=True)
    production_entry_id = db.Column(db.Integer, db.ForeignKey('ms_production_entries.id'), nullable=False, index=True)
    issue_type_id = db.Column(db.Integer, db.ForeignKey('ms_issue_types.id'), nullable=False)
    
    # Custom remarks if not in predefined issue types
    custom_remark = db.Column(db.Text)
    
    # Duration (minutes)
    impact_minutes = db.Column(db.Integer, default=0)
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ProductionIssue {self.production_entry_id}>'


class ProductionSelfRejectionDefect(db.Model):
    """Mapping table for self rejection defect rows on production entry"""
    __tablename__ = 'ms_production_self_rejection_defects'

    id = db.Column(db.Integer, primary_key=True)
    production_entry_id = db.Column(db.Integer, db.ForeignKey('ms_production_entries.id'), nullable=False, index=True)
    defect_type_id = db.Column(db.Integer, db.ForeignKey('ms_defect_types.id'), nullable=False, index=True)
    reject_qty = db.Column(db.Integer, nullable=False, default=0)

    defect_type = db.relationship('DefectType')

    def __repr__(self):
        return f'<ProductionSelfRejectionDefect {self.production_entry_id} {self.defect_type_id}>'


class Evidence(db.Model):
    """Photo/doc evidence for issues"""
    __tablename__ = 'ms_evidence'
    
    id = db.Column(db.Integer, primary_key=True)
    production_entry_id = db.Column(db.Integer, db.ForeignKey('ms_production_entries.id'), nullable=False)
    
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(20))  # jpg, png, pdf, etc.
    description = db.Column(db.Text)
    company_id = db.Column(db.Integer, default=1, index=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.Column(db.String(100))
    
    def __repr__(self):
        return f'<Evidence {self.file_name}>'


class DailyReport(db.Model):
    """Pre-computed daily summaries for faster dashboard loading"""
    __tablename__ = 'ms_daily_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    report_date = db.Column(db.Date, unique=True, index=True, nullable=False)
    
    # Summary metrics
    total_machines_active = db.Column(db.Integer)
    total_planned_qty = db.Column(db.Integer)
    total_actual_qty = db.Column(db.Integer)
    total_downtime_minutes = db.Column(db.Integer)
    
    # Performance metrics
    overall_efficiency = db.Column(db.Float)  # %
    on_time_completion = db.Column(db.Integer)  # Count of entries matching plan
    
    # Top issues summary (JSON)
    top_issues_json = db.Column(db.JSON)  # {issue_name: count, ...}
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<DailyReport {self.report_date}>'


# ==================== AUDIT & LOGGING ====================

class AuditLog(db.Model):
    """Audit trail for all changes"""
    __tablename__ = 'ms_audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(50), nullable=False)  # ProductionEntry, Machine, etc.
    entity_id = db.Column(db.Integer)
    action = db.Column(db.String(20), nullable=False)  # CREATE, UPDATE, DELETE
    changed_by = db.Column(db.String(100), nullable=False)
    changes = db.Column(db.JSON)  # {'field': {'old': value, 'new': value}}
    company_id = db.Column(db.Integer, default=1, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f'<AuditLog {self.entity_type} {self.action}>'


class DailyRejection(db.Model):
    """Daily Rejection Report - Machine Shop Quality Control"""
    __tablename__ = 'ms_daily_rejections'
    
    id = db.Column(db.Integer, primary_key=True)
    production_entry_id = db.Column(db.Integer, db.ForeignKey('ms_production_entries.id'), nullable=True, index=True)
    
    # Date, Shift and Month
    rejection_date = db.Column(db.Date, nullable=False, index=True)
    shift = db.Column(db.String(1))  # A, B, C
    month = db.Column(db.String(7), nullable=False, index=True)  # Format: YYYY-MM for filtering
    
    # Customer info (Foreign key to existing customers table)
    customer_id = db.Column(db.Integer, db.ForeignKey('ms_customers.id'), nullable=False, index=True)
    customer = db.relationship('Customer', backref='rejections')
    
    # Job Details
    section_number = db.Column(db.String(50), nullable=False)
    length = db.Column(db.Float)  # Length in appropriate unit
    
    # Rejection Details
    rejection_reason = db.Column(db.String(200), nullable=False)
    rj_pcs = db.Column(db.Integer, nullable=False)  # Rejection pieces count
    weight_per_pcs = db.Column(db.Float, nullable=False)  # Weight per piece
    rj_weight = db.Column(db.Float, nullable=False)  # Total rejection weight (auto-computed)
    
    # Operator info (Linked to shared emp_master)
    operator_emp_id = db.Column(db.Integer, db.ForeignKey('emp_master.emp_id'), nullable=False)
    operator = db.relationship('EmpMaster', backref='rejection_entries')
    
    # Relationships
    supervisors = db.relationship('DailyRejectionSupervisor', backref='rejection', lazy=True, cascade='all, delete-orphan')
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    company_id = db.Column(db.Integer, default=1, index=True)
    created_by = db.Column(db.String(100))  # User who created the entry
    
    # Indexes for common queries
    __table_args__ = (
        Index('ms_idx_rejection_date_customer', 'rejection_date', 'customer_id'),
        Index('ms_idx_rejection_month', 'month'),
    )
    
    def __repr__(self):
        return f'<DailyRejection {self.rejection_date} {self.customer_id}>'
    
    def compute_rj_weight(self):
        """Compute total rejection weight"""
        self.rj_weight = self.rj_pcs * self.weight_per_pcs if self.rj_pcs and self.weight_per_pcs else 0

    # NEW: Phase 7 Fields
    rejection_datetime = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    total_parts_inspected_qty = db.Column(db.Integer, default=0)
    defect_category = db.Column(db.String(100))
    
    # Relationships for Phase 7
    defects = db.relationship('RejectionDefect', backref='rejection', lazy=True, cascade='all, delete-orphan')
    rework_logs = db.relationship('ReworkLog', backref='rejection', lazy=True, cascade='all, delete-orphan')

class DefectType(db.Model):
    """Master table for defect types in aluminum fabrication"""
    __tablename__ = 'ms_defect_types'
    
    id = db.Column(db.Integer, primary_key=True)
    defect_name = db.Column(db.String(100), unique=True, nullable=False)
    category = db.Column(db.String(50)) # e.g. Surface, Dimensional, Machining
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<DefectType {self.defect_name}>'

class RejectionDefect(db.Model):
    """Mapping table for multiple defects per rejection entry"""
    __tablename__ = 'ms_rejection_defects'
    
    id = db.Column(db.Integer, primary_key=True)
    rejection_id = db.Column(db.Integer, db.ForeignKey('ms_daily_rejections.id'), nullable=False, index=True)
    defect_type_id = db.Column(db.Integer, db.ForeignKey('ms_defect_types.id'), nullable=False)
    defect_count = db.Column(db.Integer, nullable=False, default=0)
    
    defect_type = db.relationship('DefectType')


class ReworkLog(db.Model):
    """Logs of reworked pieces per rejection/defect"""
    __tablename__ = 'ms_rework_logs'

    id = db.Column(db.Integer, primary_key=True)
    production_entry_id = db.Column(db.Integer, db.ForeignKey('ms_production_entries.id'), nullable=False, index=True)
    rejection_id = db.Column(db.Integer, db.ForeignKey('ms_daily_rejections.id'), nullable=False, index=True)
    defect_type_id = db.Column(db.Integer, db.ForeignKey('ms_defect_types.id'), nullable=False, index=True)
    rework_qty = db.Column(db.Integer, nullable=False, default=0)
    remarks = db.Column(db.String(255))
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    defect_type = db.relationship('DefectType')


class DowntimeReason(db.Model):
    """Master table for planned downtime reasons (NPD Trials, Setup, Training)"""
    __tablename__ = 'ms_downtime_reasons'
    
    id = db.Column(db.Integer, primary_key=True)
    reason_name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    is_fixed = db.Column(db.Boolean, default=False)  # True = Fixed per shift (auto calc), False = Unfixed (dropdown)
    default_minutes = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='Active')
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<DowntimeReason {self.reason_name}>'


class ProductionPlannedDowntime(db.Model):
    """Planned downtime records for a production entry"""
    __tablename__ = 'ms_production_planned_downtime'
    
    id = db.Column(db.Integer, primary_key=True)
    production_entry_id = db.Column(db.Integer, db.ForeignKey('ms_production_entries.id'), nullable=False, index=True)
    reason_id = db.Column(db.Integer, db.ForeignKey('ms_downtime_reasons.id'), nullable=False)
    duration_minutes = db.Column(db.Integer, default=0)
    
    reason = db.relationship('DowntimeReason')
    
    def __repr__(self):
        return f'<ProductionPlannedDowntime {self.production_entry_id} - {self.reason_id}>'


class SectionMaster(db.Model):
    """Standard sections for each customer"""
    __tablename__ = 'ms_section_master'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('ms_customers.id'), nullable=False, index=True)
    section_number = db.Column(db.String(50), nullable=False, index=True)
    status = db.Column(db.String(20), default='Active')
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    customer = db.relationship('Customer', backref='sections_master')
    cut_lengths = db.relationship('SectionCutLength', backref='section', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        db.UniqueConstraint('customer_id', 'section_number', name='ms_uix_cust_section'),
    )
    
    def __repr__(self):
        return f'<SectionMaster {self.section_number}>'


class SectionCutLength(db.Model):
    """Standard cut lengths for a section"""
    __tablename__ = 'ms_section_cut_lengths'
    
    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('ms_section_master.id'), nullable=False, index=True)
    cut_length = db.Column(db.Float, nullable=False)
    uom = db.Column(db.String(10), default='MM')  # MM, Inch, etc.
    status = db.Column(db.String(20), default='Active')
    company_id = db.Column(db.Integer, default=1, index=True)
    
    cycle_times = db.relationship('IdealCycleTime', backref='cut_length_obj', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        db.UniqueConstraint('section_id', 'cut_length', name='ms_uix_section_cutlength'),
    )
    
    def __repr__(self):
        return f'<SectionCutLength {self.cut_length} {self.uom}>'


class IdealCycleTime(db.Model):
    """Ideal cycle times for each process step on a machine"""
    __tablename__ = 'ms_ideal_cycle_times'
    
    id = db.Column(db.Integer, primary_key=True)
    section_cut_length_id = db.Column(db.Integer, db.ForeignKey('ms_section_cut_lengths.id'), nullable=False, index=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('ms_machines.id'), nullable=False, index=True)
    
    machine = db.relationship('Machine', backref='ideal_cycle_times', lazy=True)
    
    process_name = db.Column(db.String(100), nullable=False)  # Setup 1, Setup 2, Milling, etc.
    cycle_time_seconds = db.Column(db.Float, nullable=False)
    sequence = db.Column(db.Integer, default=1)  # For ordering steps if multiple
    company_id = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('section_cut_length_id', 'machine_id', 'sequence', name='ms_uix_cl_machine_sequence'),
    )
    
    def __repr__(self):
        return f'<IdealCycleTime {self.process_name} on {self.machine_id}: {self.cycle_time_seconds}s>'


class MachineShopQualityAccess(db.Model):
    """Dynamic quality permissions for Machine Shop users"""
    __tablename__ = 'ms_quality_access'
    
    user_id = db.Column(db.Integer, primary_key=True)
    can_rejection_form = db.Column(db.Boolean, default=False)
    can_rejection_records = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<QualityAccess User:{self.user_id} Form:{self.can_rejection_form} Records:{self.can_rejection_records}>'
