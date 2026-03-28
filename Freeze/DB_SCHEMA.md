# Machine Shop Database Schema

This document tracks the database schema for the `machine_shop` module and its integration with the main MOA database.

## Shared Tables (Existing in MOA)

### `emp_master` (Read-Only for Machine Shop)
- Used for linking operators to production entries.
- Key columns used: `emp_id` (PK), `emp_name`, `emp_code`.

### `user_login` (Read-Only for Machine Shop)
- Used for authentication (via main app session/auth logic).

## New Tables (Machine Shop Specific)

### Master Data

#### `machines`
- `id` (PK)
- `machine_name` (Unique)
- `machine_type` (CNC, VMC, etc.)
- `section_number`
- `cutlength`
- `status`
- `created_at`, `updated_at`

#### `customers`
- `id` (PK)
- `customer_name` (Unique)
- `customer_code`
- `status`
- ... (contact details)

#### `operation_types`
- `id` (PK)
- `operation_name` (SLITTING, MILLING, etc.)
- `standard_cycle_time_seconds`

#### `issue_types`
- `id` (PK)
- `issue_name`
- `category` (NO_OPERATOR, BREAKDOWN, etc.)
- `severity`

### Transaction Data

#### `production_entries`
- `id` (PK)
- `production_date`
- `shift` (A, B, C)
- `machine_id` (FK -> machines.id)
- `customer_id` (FK -> customers.id)
- `operation_type_id` (FK -> operation_types.id)
- `operator_emp_id` (FK -> emp_master.emp_id) **[Changed from operator_id]**
- `planned_quantity`
- `actual_quantity`
- `downtime_minutes`
- `remarks`
- `created_by` (User ID/Name)

#### `production_issues`
- `id` (PK)
- `production_entry_id` (FK)
- `issue_type_id` (FK)
- `impact_minutes`

#### `audit_logs`
- Tracks changes to master data and entries.
