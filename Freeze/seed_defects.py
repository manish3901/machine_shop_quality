from models import db, DefectType
from ms_planning import app

def seed_defects():
    with app.app_context():
        common_defects = [
            ("Surface Scratches", "Surface"),
            ("Dimension Variation", "Dimensional"),
            ("Burr / Rough Cut", "Machining"),
            ("Dent Marks", "Surface"),
            ("Tool Marks / Chatter", "Machining"),
            ("Bending Issue", "Dimensional"),
            ("Drilling Misalignment", "Machining"),
            ("Tapping Issue", "Machining"),
            ("Material Hardness Issue", "Material"),
            ("Anodizing Defect", "Surface"),
            ("Powder Coating Issues", "Surface"),
            ("Incorrect Packing", "Other")
        ]
        
        for name, cat in common_defects:
            existing = DefectType.query.filter_by(defect_name=name).first()
            if not existing:
                defect = DefectType(defect_name=name, category=cat, is_active=True)
                db.session.add(defect)
        
        db.session.commit()
        print("Defect types seeded successfully.")

if __name__ == "__main__":
    seed_defects()
