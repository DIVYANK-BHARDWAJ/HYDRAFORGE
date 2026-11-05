import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hydraforge.database.connection import DatabaseManager
from hydraforge.database.migrations import apply_migrations

db_url = "postgresql://neondb_owner:npg_x5dXuDFNvaW8@ep-misty-art-ao1lof4u-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
os.environ["DATABASE_URL"] = db_url

mgr = DatabaseManager()
print(f"Database Backend: {'PostgreSQL' if mgr.is_postgres else 'SQLite'}")
apply_migrations(mgr)
print("Migrations applied successfully!")

with mgr.connect() as conn:
    cur = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
    tables = [r["table_name"] for r in cur.fetchall()]
    print(f"Verified {len(tables)} tables in Neon PostgreSQL:")
    for t in tables:
        print(f"  - {t}")
