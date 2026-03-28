import os
import sys
import json

# Add the current directory and machine_shop directory to sys.path
# This allows running the app from either the root or within machine_shop/
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if current_dir not in sys.path:
    sys.path.append(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from flask import Flask, render_template, jsonify
try:
    from flask_migrate import Migrate
except ImportError:
    Migrate = None
from datetime import datetime, timezone
from config import config
from models import db
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

migrate = Migrate() if Migrate else None


def ensure_incremental_machine_shop_schema():
    """Idempotent schema patch for fields introduced after initial deployment."""
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS ms_machine_sheds (
            id SERIAL PRIMARY KEY,
            shed_name VARCHAR(100) NOT NULL UNIQUE,
            description TEXT,
            status VARCHAR(20),
            company_id INTEGER,
            created_at TIMESTAMP WITHOUT TIME ZONE,
            updated_at TIMESTAMP WITHOUT TIME ZONE
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_ms_machine_sheds_shed_name ON ms_machine_sheds (shed_name)",
        "CREATE INDEX IF NOT EXISTS ix_ms_machine_sheds_company_id ON ms_machine_sheds (company_id)",
        """
        CREATE TABLE IF NOT EXISTS ms_machine_types (
            id SERIAL PRIMARY KEY,
            type_name VARCHAR(50) NOT NULL UNIQUE,
            description TEXT,
            status VARCHAR(20),
            company_id INTEGER,
            created_at TIMESTAMP WITHOUT TIME ZONE,
            updated_at TIMESTAMP WITHOUT TIME ZONE
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_ms_machine_types_type_name ON ms_machine_types (type_name)",
        "CREATE INDEX IF NOT EXISTS ix_ms_machine_types_company_id ON ms_machine_types (company_id)",
        "ALTER TABLE ms_machines ADD COLUMN IF NOT EXISTS shed_id INTEGER",
        "CREATE INDEX IF NOT EXISTS ix_ms_machines_shed_id ON ms_machines (shed_id)",
        "ALTER TABLE ms_production_entries ADD COLUMN IF NOT EXISTS self_rejection_weight_per_pcs FLOAT",
        "ALTER TABLE ms_production_entries ADD COLUMN IF NOT EXISTS self_rejection_weight FLOAT",
        """
        CREATE TABLE IF NOT EXISTS ms_production_self_rejection_defects (
            id SERIAL PRIMARY KEY,
            production_entry_id INTEGER NOT NULL REFERENCES ms_production_entries (id),
            defect_type_id INTEGER NOT NULL REFERENCES ms_defect_types (id),
            reject_qty INTEGER NOT NULL DEFAULT 0
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_ms_production_self_rejection_defects_production_entry_id ON ms_production_self_rejection_defects (production_entry_id)",
        "CREATE INDEX IF NOT EXISTS ix_ms_production_self_rejection_defects_defect_type_id ON ms_production_self_rejection_defects (defect_type_id)",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_ms_machines_shed_id'
                  AND table_name = 'ms_machines'
            ) THEN
                ALTER TABLE ms_machines
                ADD CONSTRAINT fk_ms_machines_shed_id
                FOREIGN KEY (shed_id) REFERENCES ms_machine_sheds (id);
            END IF;
        END $$;
        """,
        """
        INSERT INTO ms_machine_types (type_name, status, company_id, created_at, updated_at)
        SELECT DISTINCT machine_type, 'Active', 1, NOW(), NOW()
        FROM ms_machines
        WHERE machine_type IS NOT NULL
          AND machine_type <> ''
          AND NOT EXISTS (
              SELECT 1 FROM ms_machine_types mt WHERE mt.type_name = ms_machines.machine_type
          );
        """
    ]
    for ddl in ddl_statements:
        db.session.execute(db.text(ddl))
    db.session.commit()


def create_app(config_name='development'):
    """Application factory"""
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    if migrate:
        migrate.init_app(app, db)
    
    # Create upload folder if not exists
    import os
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Register blueprints
    from routes.api import api_bp
    from routes.web import web_bp
    from routes.dashboard import dashboard_bp
    from routes.master_data import master_data_bp
    from routes.rejection import rejection_bp
    
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(web_bp, url_prefix='/')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(master_data_bp, url_prefix='/master')
    app.register_blueprint(rejection_bp, url_prefix='/rejection')
    
    # Error handlers
    @app.errorhandler(404)
    def page_not_found(error):
        return jsonify({'error': 'Page not found'}), 404
    
    @app.errorhandler(500)
    def server_error(error):
        logger.error(f'Server error: {error}')
        return jsonify({'error': 'Internal server error'}), 500

    @app.get('/health')
    def health_check():
        return jsonify({
            'status': 'ok',
            'service': 'machine_shop',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 200

    @app.get('/health/db')
    def health_check_db():
        try:
            db.session.execute(db.text('SELECT 1'))
            return jsonify({
                'status': 'ok',
                'service': 'machine_shop',
                'database': 'ok',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 200
        except Exception as exc:
            logger.error(f'Database health check failed: {exc}')
            return jsonify({
                'status': 'error',
                'service': 'machine_shop',
                'database': 'unavailable',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 503
    
    # Custom Jinja filters
    @app.template_filter('getEfficiencyBadge')
    def get_efficiency_badge(efficiency):
        try:
            eff = float(efficiency)
            if eff >= 90: return 'efficiency-excellent'
            if eff >= 75: return 'efficiency-good'
            if eff >= 50: return 'efficiency-fair'
            return 'efficiency-poor'
        except (ValueError, TypeError):
            return 'efficiency-poor'
    
    # Never auto-create schema on production startup unless explicitly enabled.
    if os.getenv('MS_AUTO_CREATE_TABLES', '').strip().lower() in {'1', 'true', 'yes'}:
        with app.app_context():
            db.create_all()
            logger.warning('MS_AUTO_CREATE_TABLES enabled; schema was created/updated at startup')
    with app.app_context():
        try:
            ensure_incremental_machine_shop_schema()
        except Exception as exc:
            db.session.rollback()
            logger.error(f'Incremental Machine Shop schema sync failed: {exc}')
    
    @app.context_processor
    def inject_now():
        return {'now': datetime.now(timezone.utc)}
    
    @app.template_filter('from_json')
    def from_json_filter(value):
        return json.loads(value)
    
    logger.info(f'Application initialized with config: {config_name}')
    return app


def serve_with_waitress(host='0.0.0.0', port=5000, threads=4):
    """Waitress entrypoint for production deployment."""
    from waitress import serve
    logger.info(f"Starting Machine Shop Service on {host}:{port} with Waitress")
    serve(app, host=host, port=port, threads=threads)


app = create_app(os.getenv('FLASK_ENV', 'production'))



if __name__ == "__main__":
    # Default production entrypoint (Waitress).
    # Allow override via env vars for container/service configs.
    host = os.getenv("MS_HOST", "0.0.0.0")
    port = int(os.getenv("MS_PORT", os.getenv("PORT", "3550")))
    threads = int(os.getenv("MS_THREADS", os.getenv("WAITRESS_THREADS", "4")))
    serve_with_waitress(host=host, port=port, threads=threads)