import sqlite3
import pandas as pd
from pathlib import Path

def create_sqlite_database(excel_path, db_path):
    # Read the Excel file
    try:
        df = pd.read_excel(excel_path, sheet_name='sale_details')
        print(f"Successfully read Excel file: {excel_path}")
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    # Create SQLite database and connect
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table with specified schema
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS sale_details (
        s_no INTEGER,
        booking_date DATE,
        project TEXT,
        spg_praneeth TEXT,
        token INTEGER,
        name TEXT,
        sol TEXT,
        type_of_sale TEXT,
        land_sqyards INTEGER,
        sbua_sqft REAL,
        facing TEXT,
        base_sqft_price REAL,
        amenties_and_premiums REAL,
        total_sale_price REAL,
        amount_received REAL,
        balance_amount REAL,
        balance_tobe_received_by_plan_approval REAL,
        notes TEXT,
        balance_tobe_received_during_exec REAL
    )
    """

    try:
        cursor.execute(create_table_sql)
        print("Created 'sale_details' table in SQLite database")
    except Exception as e:
        print(f"Error creating table: {e}")
        conn.close()
        return

    # Write the data to SQLite
    try:
        df.to_sql('sale_details', conn, if_exists='replace', index=False)
        print(f"Successfully loaded {len(df)} rows into SQLite database")
    except Exception as e:
        print(f"Error writing to database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    # Define paths
    base_dir = Path(r"C:\Users\adina\OneDrive\DevSecOps\ArcadiaSales\files")
    excel_file = base_dir / "Template.xlsx"
    db_file = base_dir / "arcadia_sales.db"
    
    print(f"Starting conversion from {excel_file} to {db_file}")
    create_sqlite_database(excel_file, db_file)
    print("Conversion completed successfully!")
