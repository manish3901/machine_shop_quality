# Machine Shop Production Planning System

## Overview

A comprehensive web-based production planning and tracking system for machine shops. Digitizes daily production tracking for CNC, VMC, and other machines across multiple shifts (A, B, C). Provides real-time dashboards, analytics, and root cause analysis to identify bottlenecks and improve production efficiency.

## Key Features

### 📊 Core Functionality
- **Daily Production Entry**: Form-based data entry for each machine per shift
- **Plan vs Actual Tracking**: Real-time variance analysis and efficiency metrics
- **Shift-wise Monitoring**: Separate tracking for A, B, and C shifts (6AM-2PM, 2PM-10PM, 10PM-6AM)
- **Issue Categorization**: Structured issue tracking (No Operator, No Material, Setup Delay, QC Issue, Machine Breakdown, Tool Change)
- **Bulk CSV Upload**: Import multiple entries at once

### 📈 Analytics & Dashboards
- **Daily Dashboard**: Real-time production metrics, efficiency scores, top issues
- **Weekly Reports**: Trend analysis, performance comparison
- **Machine Performance**: Utilization heatmap, downtime analysis, historical trends
- **Shift Analysis**: Shift-wise efficiency comparison, bottleneck identification
- **Issues Analysis**: Pareto charts, root cause categorization, trend tracking

### 🗄️ Master Data Management
- Machine catalog (name, type, specs)
- Customer database
- Operation types with standard cycle times
- Issue types and severity levels
- Employee/operator directory

### 🔐 Audit & Compliance
- Complete audit trail for all changes
- User-based activity tracking
- Timestamp on every entry
- Role-based access control (Phase 2)

---

## Project Structure

```
machine_shop/
├── app.py                    # Flask application factory
├── config.py                 # Configuration management
├── models.py                 # SQLAlchemy database models
├── requirements.txt          # Python dependencies
├── routes/
│   ├── __init__.py
│   ├── api.py               # REST API endpoints
│   ├── web.py               # Web form pages
│   ├── dashboard.py         # Dashboard pages
│   └── master_data.py       # Master data CRUD
├── templates/
│   ├── base.html            # Base template with navigation
│   ├── production_entry.html # Data entry form
│   ├── view_entries.html    # View all entries
│   ├── dashboard_daily.html # Daily dashboard
│   ├── machine_performance.html  # Machine metrics
│   ├── shift_analysis.html  # Shift comparison
│   ├── issues_analysis.html # Issue deep-dive
│   └── master/              # Master data templates
├── static/
│   ├── css/
│   └── js/
└── uploads/                 # User uploaded files (bulk CSVs, photos)
```

---

## Installation & Setup

### Prerequisites
- Python 3.8+
- PostgreSQL 10+ (or SQLite for development)
- pip (Python package manager)

### Step 1: Clone & Setup Environment

```bash
cd path/to/MOA/machine_shop

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure Database

Create a `.env` file in the project root:

```env
# Development
FLASK_ENV=development
FLASK_APP=app.py

# Database (for PostgreSQL)
DATABASE_URL=postgresql://username:password@localhost:5432/machine_shop_db

# For SQLite (simple dev setup):
# DATABASE_URL=sqlite:///machine_shop.db

# Flask
SECRET_KEY=your-secret-key-here
```

### Step 4: Initialize Database

```bash
# Create PostgreSQL database
createdb machine_shop_db

# Initialize Flask-Migrate
flask db init

# Create initial migration
flask db migrate -m "Initial schema"

# Apply migration
flask db upgrade
```

### Step 5: Load Initial Master Data

```bash
python
>>> from app import create_app, db
>>> from models import Machine, Customer, OperationType, IssueType

>>> app = create_app('development')
>>> with app.app_context():
...     # Add machines
...     machines = [
...         Machine(machine_name='VMC-1', machine_type='VMC', section_number='2191', cutlength=489.7),
...         Machine(machine_name='VMC-2', machine_type='VMC', section_number='2123', cutlength=418.2),
...         Machine(machine_name='CNC-1', machine_type='CNC', section_number='99719'),
...         # Add more as needed
...     ]
...     for m in machines:
...         db.session.add(m)
...     
...     # Add customers
...     customers = [
...         Customer(customer_name='C2', customer_code='C2'),
...         Customer(customer_name='AGAM', customer_code='AGAM'),
...         # Add more
...     ]
...     for c in customers:
...         db.session.add(c)
...     
...     # Add operations
...     operations = [
...         OperationType(operation_name='SLITTING', standard_cycle_time_seconds=360),
...         OperationType(operation_name='MILLING', standard_cycle_time_seconds=300),
...         OperationType(operation_name='DRILLING'),
...         # Add more
...     ]
...     for o in operations:
...         db.session.add(o)
...     
...     # Add issue types
...     issues = [
...         IssueType(issue_name='No Operator', category='NO_OPERATOR', severity='High'),
...         IssueType(issue_name='No Material', category='NO_MATERIAL', severity='High'),
...         IssueType(issue_name='Setup Delay', category='SETUP_DELAY', severity='Medium'),
...         IssueType(issue_name='QC Issue', category='QC_ISSUE', severity='Medium'),
...         IssueType(issue_name='Machine Breakdown', category='BREAKDOWN', severity='Critical'),
...         IssueType(issue_name='Tool Change', category='TOOL_CHANGE', severity='Low'),
...     ]
...     for issue in issues:
...         db.session.add(issue)
...     
...     db.session.commit()
...     print("Master data loaded!")
```

### Step 6: Run Application

```bash
flask run
# Server runs at http://localhost:5000
```

---

## Usage Guide

### Data Entry (Daily)
1. Go to **New Entry** → Fill production form
2. Select date, shift, machine, customer
3. Enter planned and actual quantities
4. Document any issues or downtime
5. Click **Save Entry**

### Bulk Import (CSV)
1. Go to **Bulk Upload**
2. Prepare CSV with columns:
   - `production_date` (YYYY-MM-DD)
   - `shift` (A/B/C)
   - `machine_id` (ID from machines table)
   - `customer_id` (ID from customers table)
   - `planned_quantity`
   - `actual_quantity` (optional)
   - `remarks` (optional)

3. Upload file - entries imported automatically

### Dashboard Views

#### Daily Dashboard (Real-time)
- Overall efficiency score
- Plan vs actual by machine
- Shift-wise comparison
- Top 5 underperforming machines
- Live entries feed

#### Weekly Report
- Daily trend lines
- Cumulative metrics
- Top 5 issues of the week
- Day-by-day breakdown

#### Machine Performance
- Efficiency heatmap (color-coded by performance)
- Historical trends
- Downtime analysis
- Best/worst performers
- Production volume trends

#### Shift Analysis
- A, B, C shift efficiency comparison
- Resources utilization
- Issue distribution by shift
- Peak production hours

#### Issues Analysis
- Pareto chart of top issues
- Category-wise breakdown
- Impact analysis (hours lost)
- Trending issues
- Machine-issue correlation

---

## API Documentation

### Authentication
Currently no authentication. Phase 2 will add role-based access.

### Base URL
```
http://localhost:5000/api
```

### Endpoints

#### Production Entries

**Create Entry**
```
POST /api/production-entries
Content-Type: application/json

{
    "production_date": "2024-01-15",
    "shift": "B",
    "machine_id": 1,
    "customer_id": 2,
    "planned_quantity": 100,
    "actual_quantity": 85,
    "cycle_time_seconds": 120,
    "downtime_minutes": 15,
    "remarks": "Setup delay",
    "created_by": "operator_1"
}

Response: 201 Created
{
    "id": 456,
    "message": "Production entry created successfully"
}
```

**Get Entry**
```
GET /api/production-entries/{entry_id}

Response: 200 OK
{
    "id": 456,
    "date": "2024-01-15",
    "shift": "B",
    "machine": "VMC-1",
    "customer": "C2",
    ...
}
```

**List Entries** (with filtering)
```
GET /api/production-entries?production_date=2024-01-15&machine_id=1&shift=B&page=1

Query Params:
- production_date: Filter by single date
- start_date, end_date: Filter by date range
- machine_id: Filter by machine
- shift: Filter by shift (A/B/C)
- customer_id: Filter by customer
- page: Page number (default: 1, 50 items/page)

Response: 200 OK
{
    "entries": [...],
    "pagination": {
        "page": 1,
        "per_page": 50,
        "total": 245,
        "pages": 5
    }
}
```

**Update Entry**
```
PUT /api/production-entries/{entry_id}
Content-Type: application/json

{
    "actual_quantity": 90,
    "downtime_minutes": 20,
    "remarks": "Updated remarks",
    "updated_by": "supervisor_1"
}

Response: 200 OK
```

#### Analytics

**Daily Summary**
```
GET /api/analytics/daily-summary?date=2024-01-15

Response: 200 OK
{
    "date": "2024-01-15",
    "total_machines": 6,
    "total_entries": 18,
    "total_planned": 1500,
    "total_actual": 1200,
    "efficiency": 80.0,
    "by_shift": {
        "A": {"planned": 500, "actual": 420, "efficiency": 84.0},
        "B": {"planned": 500, "actual": 420, "efficiency": 84.0},
        "C": {"planned": 500, "actual": 360, "efficiency": 72.0}
    }
}
```

**Machine Performance** (30-day period)
```
GET /api/analytics/machine-performance?days=30

Response: 200 OK
{
    "machines": [
        {
            "machine_id": 1,
            "machine_name": "VMC-1",
            "efficiency_percent": 85.5,
            "avg_downtime_minutes": 12.5,
            "entries_count": 45
        }
    ]
}
```

**Top Issues** (Root cause analysis)
```
GET /api/analytics/top-issues?days=30&start_date=2024-01-01

Response: 200 OK
{
    "top_issues": [
        {
            "issue_name": "No Operator",
            "category": "NO_OPERATOR",
            "count": 45,
            "total_impact_minutes": 1350
        }
    ]
}
```

#### Master Data

**Get Machines**
```
GET /master/api/machines?status=Active

Response: 200 OK
[
    {"id": 1, "name": "VMC-1"},
    {"id": 2, "name": "VMC-2"}
]
```

**Get Customers**
```
GET /master/api/customers

Response: 200 OK
[...]
```

**Bulk Import CSV**
```
POST /api/import/csv
Content-Type: multipart/form-data
?user=operator_1

file: production_data.csv

Response: 200 OK
{
    "imported": 150,
    "errors": [],
    "message": "150 entries imported successfully"
}
```

---

## Improvement Ideas & Enhancements

### 🚀 Phase 2: Advanced Features

#### 1. **Predictive Analytics**
- Machine Learning model to predict breakdowns
- Trend forecasting for production demand
- Anomaly detection to flag unusual patterns
- Recommendation engine for optimization

#### 2. **Real-time Alerts**
- SMS/Email alerts for critical issues (No operator, No material)
- Push notifications for shift supervisors
- Automated escalation for downtime > threshold
- Daily summary reports

#### 3. **IoT Integration**
- Direct integration with PLC/CNC control systems
- Automatic actual quantity input from machines
- Real-time machine status monitoring
- Predictive maintenance based on signals

#### 4. **Mobile App**
- Lightweight mobile interface for operators
- Offline data collection (sync when online)
- Photo evidence upload for issues
- Quick-entry templates

#### 5. **Advanced Reporting**
- PDF report generation
- Export to Excel with formatting
- Custom report builder
- Scheduled report distribution

#### 6. **Resource Optimization**
- Machine scheduling optimization
- Operator skill-to-task matching
- Production bottleneck solver
- Shift load balancing

#### 7. **Quality Tracking**
- Integration with QC module
- Defect rate tracking by machine/shift
- Correlation with production speed
- OEE (Overall Equipment Effectiveness) calculation

#### 8. **Historical Analysis**
- 12-month trends
- Seasonal pattern detection
- Year-over-year comparison
- Capacity planning tools

### 🔧 Phase 2: Infrastructure

#### Authentication & Authorization
```python
# Add user roles
- Operator: Data entry only
- Supervisor: Data entry + approvals + shift view
- Manager: All access + reporting
- Admin: System configuration

# Implement with Flask-Login + JWT tokens
```

#### Database Optimization
- Add indexes for common queries
- Partition large tables by date
- Implement data archival strategy
- Backup automation

#### Performance Enhancements
- Caching layer (Redis) for dashboards
- Pagination for large result sets
- Query optimization
- CDN for static assets

#### Monitoring & Logging
- Application performance monitoring (APM)
- Error logging and alerts
- Database query logging
- API usage analytics

---

## Database Schema Summary

### Core Tables

**machines**
- Stores machine metadata (name, type, specs)

**customers**
- Customer information for traceability

**operation_types**
- Standard operations with cycle times

**employees**
- Operator/staff directory

**production_entries**
- Daily production transactions (main data)
- Indexes on: production_date, shift, machine_id

**production_issues**
- Issues linked to entries (many-to-many)

**issue_types**
- Categorized issue definitions

**daily_reports**
- Pre-computed daily summaries for fast dashboards

**audit_logs**
- Complete change history

---

## Sample Data Entry Workflow

```
Operator starts shift at 2 PM (B Shift)

1. Opens "New Entry" form
2. Form pre-fills with:
   - Date: Today
   - Shift: B
   - Operator: Auto-filled from login

3. Selects:
   - Machine: VMC-3
   - Customer: C2
   - Operation: SLITTING

4. Enters:
   - Planned Quantity: 73 (from work order)
   - Actual Quantity: 70 (completed at shift end)
   - Cycle Time: 6 min
   - Downtime: 0 min
   - Remarks: (none)

5. Clicks Save

6. System automatically calculates:
   - Variance: 70 - 73 = -3
   - Variance %: -3/73 * 100 = -4.1%
   - Efficiency: 95.9%

7. Data appears in:
   - Daily Dashboard (real-time)
   - Shift Summary
   - Weekly Report
   - Machine Performance Analytics
```

---

## Troubleshooting

### Issue: Database connection error
```
Solution:
1. Verify PostgreSQL is running: pg_isready
2. Check credentials in .env
3. Verify database exists: psql -l
4. Check (connection string format
```

### Issue: Port 5000 already in use
```
Flask run -p 5001
# Or kill the process using port 5000
```

### Issue: Import errors
```
pip install --upgrade -r requirements.txt
pip install -e .
```

---

## Performance Metrics to Track

1. **Production Metrics**
   - Daily output vs planned
   - Shift-wise efficiency
   - Machine utilization rate
   - Downtime percentage

2. **Quality Metrics**
   - Defect rate by machine
   - QC rejection rate
   - Rework time

3. **Operational Metrics**
   - Average cycle time vs standard
   - Setup time
   - Changeover efficiency

4. **People Metrics**
   - Operator efficiency
   - Shift performance
   - Training effectiveness

---

## Contributing

To add new features:

1. Create a feature branch: `git checkout -b feature/name`
2. Make changes and test locally
3. Submit pull request with description
4. Code review and merge

---

## License

Internal use only - Global Aluminium Pvt Ltd

---

## Support

For issues or feature requests, contact the Production Planning Team.

---

**Last Updated**: February 16, 2026
**Version**: 1.0 - MVP Release
