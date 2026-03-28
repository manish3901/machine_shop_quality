# Machine Shop Production and Quality Management System

## Overview

This project is a web application built for a machine shop environment where the Production Department and Quality Department work on the same daily output but often maintain information separately.

The system brings both teams onto one platform:

- Production records what was planned, what was actually produced, who worked on it, what machine was used, and what issues affected output.
- Quality records inspection results, rejection details, rework, and defect-wise analysis against the same production entries.

Because both departments are connected to the same production records, the shop gets a clearer view of what was produced, what was accepted, what was rejected, what was reworked, and where the main losses are happening.

## Why This System Helps

In many machine shops, production and quality data are tracked in separate sheets, notebooks, or disconnected systems. That creates common problems:

- delayed visibility into actual shift performance
- mismatch between production quantity and inspected quantity
- difficulty tracking rejection and rework against a specific job or machine
- repeated manual reporting at the end of the day or week
- weak root-cause analysis for low efficiency, downtime, and scrap

This application solves that by creating one operational flow from plan to production to inspection to analysis.

## Business Value

### For the Production Department

- captures daily production shift-wise and machine-wise
- compares planned quantity against actual quantity
- tracks downtime, issues, and efficiency losses
- shows operator, supervisor, machine, customer, section, and operation details together
- helps production leaders identify underperforming machines, shifts, and bottlenecks quickly

### For the Quality Department

- links quality rejection directly to the original production entry
- records defect-wise rejection quantities
- captures rework details and their impact on final accepted quantity
- improves traceability of inspection decisions
- helps the team analyze recurring defects by customer, section, machine, shift, and date

### For Management

- provides dashboards instead of manual spreadsheet follow-up
- improves accountability with user-linked records and timestamps
- supports daily review meetings with better facts
- helps reduce scrap, rework, and hidden losses
- creates a stronger base for continuous improvement and OEE-style tracking

## End-to-End Workflow

### 1. Production Planning and Entry

The production team creates or records daily output for each machine and shift. A production entry can include:

- production date and shift
- machine and shed
- customer, section, and cut length
- planned quantity and actual quantity
- operators and supervisors
- operation or process details
- downtime and issue reasons
- remarks and related context

### 2. Production Monitoring

Supervisors and managers can review production records to compare:

- plan vs actual
- machine-wise performance
- shift-wise performance
- issue impact
- downtime and efficiency

### 3. Quality Inspection and Rejection

The quality team can open the rejection form against a production record and inspect:

- total inspected quantity
- defect-wise rejection summary
- rework summary
- quality supervisor details
- final quality impact on the production record

This keeps quality events connected to the actual production history instead of being stored separately.

### 4. Quality and Production Analysis

Once production and quality data are stored together, the system can show:

- daily and weekly dashboard summaries
- machine performance trends
- issue analysis
- shift comparison
- rejection records and defect-wise breakdown
- rework visibility
- final OK quantity after quality impact

## Main Modules

### Production Module

Used by the production department to record and manage day-to-day machine output.

Key outcomes:

- daily production entry
- viewing and editing production records
- plan vs actual tracking
- machine and shift performance review

### Quality Rejection Module

Used by the quality department to log inspection outcome against production records.

Key outcomes:

- defect-wise rejection capture
- rework recording
- linked production inspection context
- rejection and rework history

### Dashboards and Analytics

Used by supervisors, production heads, quality engineers, and management.

Key outcomes:

- daily dashboard
- weekly dashboard
- machine performance analysis
- employee performance insights
- shift analysis
- issues analysis

### Master Data Management

Used to maintain the reference data that drives the application.

Typical master data includes:

- machines
- sheds
- machine types
- customers
- sections
- cut lengths
- operations
- employees
- issue types
- defect types
- downtime reasons

### Access Control

Used to control who can access production, dashboards, quality forms, and records. This is especially helpful when production and quality responsibilities need separate permissions.

## How Production and Quality Stay Connected

The biggest strength of this project is the link between production entries and quality rejection entries.

That connection helps the organization answer questions like:

- Which machine produced the rejected parts?
- Which shift had the highest rejection?
- Which customer section or cut length is creating repeated quality issues?
- How much of the rejected quantity was recovered through rework?
- What is the final accepted quantity after inspection?
- Are low production efficiency and high rejection happening together?

This is where the project becomes more than a data-entry tool. It becomes an operational decision system.

## Typical Users

- Production operators
- Production supervisors
- Shift in-charges
- Quality inspectors
- Quality supervisors
- Department heads
- Management reviewers
- Admin or master data maintainers

## Project Structure

```text
machine_shop/
├── __init__.py
├── config.py
├── models.py
├── ms_planning.py
├── requirements.txt
├── routes/
│   ├── access_control.py
│   ├── api.py
│   ├── dashboard.py
│   ├── master_data.py
│   ├── rejection.py
│   └── web.py
├── templates/
│   ├── production_entry.html
│   ├── view_entries.html
│   ├── dashboard_daily.html
│   ├── dashboard_weekly.html
│   ├── machine_performance.html
│   ├── shift_analysis.html
│   ├── issues_analysis.html
│   ├── rejection_form.html
│   ├── rejection_records.html
│   └── master/
├── utils/
│   └── auth.py
└── schema_ms.sql
```

## Key Functional Areas

### Production Tracking

- daily production entry
- actual quantity reporting
- operator and supervisor mapping
- machine-wise and shift-wise visibility

### Planning Support

- planning-related utilities and reports
- comparison between expected and achieved output
- support for operational review and scheduling decisions

### Quality Tracking

- quality rejection form linked to production
- defect-wise rejection entries
- rework summary and logs
- quality records review

### Analysis and Review

- dashboard-based review
- issue trend analysis
- quality impact review
- shift and employee comparison

## How It Improves Daily Operations

### Better Traceability

Every production record can be followed through inspection, rejection, rework, and final outcome.

### Faster Review Meetings

Production and quality leaders can review one source of truth instead of collecting reports from multiple files.

### Better Loss Identification

The system helps separate losses caused by:

- machine issues
- manpower issues
- process issues
- quality defects
- downtime
- planning gaps

### Improved Accountability

Because entries are linked to machines, people, shifts, and dates, it becomes easier to identify where support or corrective action is required.

### Stronger Continuous Improvement

The data collected by this system can support Kaizen, root cause analysis, defect reduction, and process improvement initiatives.

## Setup

### Prerequisites

- Python 3.10+
- Database configured through environment variables
- `pip` for dependency installation

### Local Setup

```bash
cd machine_shop
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local environment file:

```env
SECRET_KEY=change-me
DATABASE_URL=your-database-connection-string
```

You can use the included `.env.example` as a starting point.

### Run the Application

Run the project using the application entrypoint used in your environment. In this codebase, the Flask app and route modules are already organized under the `machine_shop` package, so start the app using the same command pattern you use locally today.

If your environment already has a working startup command or batch file, continue using that same method.

## Suggested Department Use

### Production Team Uses It For

- entering daily output
- reviewing variance
- checking machine performance
- tracking shift execution

### Quality Team Uses It For

- recording rejection
- tracking rework
- monitoring defect trends
- auditing inspection outcome

### Management Uses It For

- monitoring daily health of the machine shop
- comparing departments and shifts
- prioritizing actions on recurring losses
- reviewing performance with actual operational evidence

## Summary

This project is designed as a practical machine shop operations system, not just a software demo.

It helps the Production Department and Quality Department work with shared data, shared traceability, and shared visibility. That improves decision-making, reduces manual reporting effort, and makes it easier to control output, rejection, rework, and performance on the shop floor.
