# DEPRECATED: This script was written for the SQLite era of NiriKsha.
# NiriKsha now uses Neon PostgreSQL exclusively.
# This script reads local SQLite .db files and must NOT be used with production data.
# Use the PostgreSQL admin console (Neon Dashboard) to inspect production data.

import sqlite3
import sys

db_name = sys.argv[1] if len(sys.argv) > 1 else 'legal_metrology.db'
con = sqlite3.connect(db_name)
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' and name NOT LIKE 'sqlite_%'").fetchall()]
counts = {t: cur.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
print(f"[{db_name}] COUNTS:", counts)
