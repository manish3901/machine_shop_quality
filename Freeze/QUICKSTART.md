# Machine Shop System - Quick Start Guide

## ⚡ Get Started in 5 Minutes

### 1️⃣ Prerequisites Installed?
```bash
# Check Python version (need 3.8+)
python --version

# Check pip installed
pip --version
```

### 2️⃣ Setup Project

```bash
# Navigate to project
cd machine_shop

# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3️⃣ Configure Database

**Option A: SQLite (Easiest for Development)**
```bash
# Just run the app - SQLite will create automatically
flask run
# Visit http://localhost:5000
```

**Option B: PostgreSQL (Better for Production)**
```bash
# Create database
createdb machine_shop_db

# Create .env file with database URL
# DATABASE_URL=postgresql://postgres:password@localhost:5432/machine_shop_db

# Initialize database
flask db upgrade

# Run app
flask run
```

### 4️⃣ Load Initial Data

```bash
python init_data.py
```

(Or manually add through the web interface: Master Data → Add Machine/Customer/etc)

### 5️⃣ Start Using!

```bash
# App runs at:
http://localhost:5000
```

---

## 📋 Common Tasks

### Add New Machine
1. Go to **Master Data** → **Machines**
2. Click **Add Machine**
3. Fill: Name (VMC-1), Type (VMC), Section (#2191), Cutlength (489.7)
4. Save

### Enter Daily Production Data
1. Go to **New Entry**
2. Select: Date, Shift, Machine, Customer
3. Enter: Planned Qty, Actual Qty, Cycle Time, Downtime
4. Add remarks if any issues
5. Click **Save Entry**

### View Dashboard
- **Daily Dashboard**: Real-time metrics, efficiency scores
- **Weekly Report**: Trend analysis
- **Machine Performance**: Utilization heatmap
- **Shift Analysis**: Compare A, B, C shifts
- **Issues Analysis**: Root cause (Pareto chart)

### Bulk Import Entries
1. Prepare CSV file with columns:
   ```
   production_date,shift,machine_id,customer_id,planned_quantity,actual_quantity,remarks
   2024-01-15,A,1,1,100,95,Setup delay
   2024-01-15,B,2,2,80,80,
   ```

2. Go to **Bulk Upload**
3. Select file and upload
4. View results

### Export Data
```bash
# From API (example: get all entries from Jan 15)
curl "http://localhost:5000/api/production-entries?production_date=2024-01-15" \
  -H "Accept: application/json" > entries.json
```

---

## 🔍 Key URLs

| Page | URL |
|------|-----|
| Dashboard | http://localhost:5000 |
| New Entry | http://localhost:5000/production-entry |
| View Entries | http://localhost:5000/entries |
| Daily Dashboard | http://localhost:5000/dashboard/daily |
| Machine Performance | http://localhost:5000/dashboard/machine-performance |
| Machines Master | http://localhost:5000/master/machines |
| Customers Master | http://localhost:5000/master/customers |

---

## 🛠️ Troubleshooting

**Error: "No module named 'flask'"**
```bash
pip install -r requirements.txt
```

**Error: "Database connection failed"**
```bash
# Check if PostgreSQL is running:
pg_isready

# Or switch to SQLite in .env:
DATABASE_URL=sqlite:///machine_shop.db
```

**Error: "Port 5000 already in use"**
```bash
flask run -p 5001
```

**Need to reset database?**
```bash
# SQLite:
rm machine_shop.db
flask run  # Auto-creates new database

# PostgreSQL:
dropdb machine_shop_db
createdb machine_shop_db
flask db upgrade
```

---

## 📊 Sample Data Structure

### Production Entry
```
Date: 2024-01-15
Shift: B (2 PM - 10 PM)
Machine: VMC-3
Customer: C2
Planned: 73 pieces
Actual: 70 pieces
Variance: -3 (-4.1%)
Efficiency: 95.9%
Downtime: 0 min
Remarks: (none)
```

### Issue Categories
- ❌ **No Operator** - Missing staff
- ❌ **No Material** - Component shortage
- 🔧 **Setup Delay** - Changeover time
- ⚠️ **QC Issue** - Quality check rejection
- 💥 **Machine Breakdown** - Equipment failure
- 🔨 **Tool Change** - Tool replacement

---

## 🎯 Next Steps

### Day 1: Setup Phase
- [ ] Install system per instructions
- [ ] Configure database
- [ ] Add master data (5 machines, 3 customers)
- [ ] Test with sample entry

### Day 2: Data Collection
- [ ] Train operators on new entry form
- [ ] Start collecting daily data
- [ ] Monitor dashboard for any issues

### Week 1: Validation
- [ ] Compare old Excel vs new system
- [ ] Adjust if data structure needs tweaking
- [ ] Get feedback from supervisors

### Week 2: Full Deployment
- [ ] All shifts using system
- [ ] Dashboards displayed on shop floor
- [ ] Begin analysis phase

### Phase 2 (Month 2)
- [ ] Add automatic alerts
- [ ] Setup mobile app
- [ ] Implement predictive analytics
- [ ] IoT integration with machines

---

## 📞 Support

**Issues?**
1. Check README.md for detailed docs
2. Review troubleshooting section above
3. Check application logs

**Feature requests?**
Submit to production planning team

---

**Happy tracking! 🚀**
