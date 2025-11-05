import pandas as pd
import sqlite3
from datetime import datetime
import os

def create_sqlite_database():
    # File paths
    excel_file = r'C:\Users\adina\OneDrive\DevSecOps\ArcadiaSales\files\Template.xlsx'
    db_file = r'C:\Users\adina\OneDrive\DevSecOps\ArcadiaSales\files\arcadia_sales.db'
    
    # Read Excel file
    try:
        df = pd.read_excel(excel_file, sheet_name='sale_details')
        print(f"Successfully read Excel file: {excel_file}")
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    # Create SQLite connection
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Drop and recreate table with constraints to enforce validations
    drop_table_sql = """
    DROP TABLE IF EXISTS sale_details;
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS sale_details (
        s_no INTEGER,
        booking_date DATE,
        project TEXT,
        spg_praneeth TEXT CHECK (spg_praneeth IN ('SPG','Praneeth')),
        token INTEGER,
        buyer_name TEXT,
        sol TEXT,
        type_of_sale TEXT CHECK (type_of_sale IN ('OTP','R')),
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
        balance_tobe_received_during_exec REAL,
        sale_person_name TEXT,
        crm_name TEXT
    );
    """
    
    try:
        cursor.execute(drop_table_sql)
        cursor.execute(create_table_sql)
        print("Created table 'sale_details'")
    except Exception as e:
        print(f"Error creating table: {e}")
        conn.close()
        return

    # Insert data into SQLite table
    try:
        # Convert date columns to proper format
        if 'booking_date' in df.columns:
            df['booking_date'] = pd.to_datetime(df['booking_date'], errors='coerce').apply(
                lambda d: d.date() if pd.notnull(d) else None
            )
        
        # Normalize allowed-list fields
        if 'spg_praneeth' in df.columns:
            df['spg_praneeth'] = df['spg_praneeth'].astype(str).str.strip().replace({
                'spg': 'SPG', 'SPG': 'SPG', 'Spg': 'SPG',
                'praneeth': 'Praneeth', 'Praneeth': 'Praneeth', 'PRANEETH': 'Praneeth'
            })
        if 'type_of_sale' in df.columns:
            df['type_of_sale'] = df['type_of_sale'].astype(str).str.strip().str.upper()

        # Ensure buyer_name column exists (map from legacy 'name' if needed)
        if 'buyer_name' not in df.columns and 'name' in df.columns:
            df['buyer_name'] = df['name']
        if 'buyer_name' not in df.columns:
            df['buyer_name'] = None

        # Ensure optional new columns exist
        for opt_col in ['sale_person_name', 'crm_name']:
            if opt_col not in df.columns:
                df[opt_col] = None

        # Convert numeric columns to appropriate types
        numeric_columns = ['s_no', 'token', 'land_sqyards', 'sbua_sqft', 'base_sqft_price',
                          'amenties_and_premiums', 'amount_received',
                          'balance_tobe_received_during_exec']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # Calculate fields
        base = df['base_sqft_price'] if 'base_sqft_price' in df.columns else 0
        prem = df['amenties_and_premiums'] if 'amenties_and_premiums' in df.columns else 0
        sbua = df['sbua_sqft'] if 'sbua_sqft' in df.columns else 0
        land = df['land_sqyards'] if 'land_sqyards' in df.columns else 0
        amt_received = df['amount_received'] if 'amount_received' in df.columns else 0

        df['total_sale_price'] = (base + prem) * land
        df['balance_amount'] = df['total_sale_price'] - amt_received

        def compute_plan_approval(row):
            tos = row.get('type_of_sale', '')
            if tos == 'OTP':
                return row['balance_amount']
            elif tos == 'R':
                return (row['total_sale_price'] * 0.20) - row['balance_amount']
            return None

        df['balance_tobe_received_by_plan_approval'] = df.apply(compute_plan_approval, axis=1)

        # Prepare insert
        insert_sql = """
        INSERT INTO sale_details (
            s_no, booking_date, project, spg_praneeth, token, buyer_name, sol, type_of_sale,
            land_sqyards, sbua_sqft, facing, base_sqft_price, amenties_and_premiums,
            total_sale_price, amount_received, balance_amount,
            balance_tobe_received_by_plan_approval, notes, balance_tobe_received_during_exec,
            sale_person_name, crm_name
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """

        rows = []
        for _, r in df.iterrows():
            rows.append((
                int(r['s_no']) if not pd.isna(r.get('s_no')) else None,
                r.get('booking_date'),
                r.get('project'),
                r.get('spg_praneeth'),
                int(r['token']) if not pd.isna(r.get('token')) else None,
                r.get('buyer_name'),
                r.get('sol'),
                r.get('type_of_sale'),
                int(r['land_sqyards']) if not pd.isna(r.get('land_sqyards')) else None,
                float(r['sbua_sqft']) if not pd.isna(r.get('sbua_sqft')) else None,
                r.get('facing'),
                float(r['base_sqft_price']) if not pd.isna(r.get('base_sqft_price')) else None,
                float(r['amenties_and_premiums']) if not pd.isna(r.get('amenties_and_premiums')) else None,
                float(r['total_sale_price']) if not pd.isna(r.get('total_sale_price')) else None,
                float(r['amount_received']) if not pd.isna(r.get('amount_received')) else None,
                float(r['balance_amount']) if not pd.isna(r.get('balance_amount')) else None,
                float(r['balance_tobe_received_by_plan_approval']) if not pd.isna(r.get('balance_tobe_received_by_plan_approval')) else None,
                r.get('notes'),
                float(r['balance_tobe_received_during_exec']) if not pd.isna(r.get('balance_tobe_received_during_exec')) else None,
                r.get('sale_person_name'),
                r.get('crm_name')
            ))

        cursor.executemany(insert_sql, rows)
        print(f"Successfully loaded {len(rows)} rows into 'sale_details' table")
        
        # Verify data was inserted
        cursor.execute("SELECT COUNT(*) FROM sale_details")
        count = cursor.fetchone()[0]
        print(f"Verified {count} records in the database")
        
    except Exception as e:
        print(f"Error inserting data: {e}")
    finally:
        conn.commit()
        conn.close()
        print(f"Database created successfully at: {db_file}")

if __name__ == "__main__":
    create_sqlite_database()
