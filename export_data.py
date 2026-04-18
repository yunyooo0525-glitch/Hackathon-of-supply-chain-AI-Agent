import sqlite3
import json
import os

def export_db(db_path, output_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    
    data = {}
    for table in tables:
        # Get column names
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [info[1] for info in cursor.fetchall()]
        
        # Get all rows
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        
        # Combine into list of dicts
        data[table] = [dict(zip(columns, row)) for row in rows]
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    conn.close()
    print(f"Successfully exported {len(tables)} tables to {output_path}")

if __name__ == "__main__":
    export_db("db.sqlite", "db_data.json")
