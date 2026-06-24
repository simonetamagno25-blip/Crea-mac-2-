"""Esegue la migrazione JSON -> tabelle e mostra il risultato."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import connect, init_schema, needs_migration, migrate_from_json_blob, count_rows

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")

conn = connect(DB_PATH)
init_schema(conn)

if needs_migration(conn):
    print("Migrazione in corso...")
    migrate_from_json_blob(conn)
    print("Fatto.")
else:
    print("Nessuna migrazione necessaria (tabelle gia popolate).")

counts = count_rows(conn)
print("\nTabelle:")
for table, n in counts.items():
    print(f"  {table}: {n} righe")

print("\nSchema:")
for row in conn.execute(
    "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
):
    print(f"\n--- {row[0]} ---")
    print(row[1])

conn.close()
