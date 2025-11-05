import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base, scoped_session
from io import StringIO
import re
import csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(BASE_DIR, '..', 'arcadia_sales.db'))
DATABASE_URL = f"sqlite:///{DB_PATH}"

app = Flask(__name__)
app.secret_key = os.environ.get('APP_SECRET', 'dev-secret-key')

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)  # 'CRM' or 'ADMIN'

Base.metadata.create_all(engine)

def seed_users():
    db = SessionLocal()
    try:
        # Create users table if not exists
        if not engine.dialect.has_table(engine.connect(), 'users'):
            Base.metadata.tables['users'].create(bind=engine)
        # Seed defaults
        def ensure_user(username, password, role):
            u = db.query(User).filter_by(username=username).first()
            if not u:
                u = User(username=username, password_hash=generate_password_hash(password), role=role)
                db.add(u)
        ensure_user('vasu', 'kaka', 'CRM')
        ensure_user('admin', 'admin', 'ADMIN')
        db.commit()
    finally:
        db.close()

seed_users()

# Option tables for dynamic select values
def ensure_option_tables():
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS spg_options (value TEXT PRIMARY KEY)")
        cur.execute("CREATE TABLE IF NOT EXISTS sale_type_options (value TEXT PRIMARY KEY)")
        # Seed defaults if empty
        cur.execute("SELECT COUNT(*) FROM spg_options");
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO spg_options(value) VALUES (?)", [("SPG",),("Praneeth",)])
        cur.execute("SELECT COUNT(*) FROM sale_type_options");
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO sale_type_options(value) VALUES (?)", [("OTP",),("R",)])
        conn.commit()
    finally:
        conn.close()

ensure_option_tables()

# Helpers

def current_user():
    if 'user_id' in session:
        db = SessionLocal()
        try:
            return db.query(User).get(session['user_id'])
        finally:
            db.close()
    return None

def login_required(role=None):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for('login', next=request.path))
            if role and user.role != role:
                flash('Unauthorized', 'error')
                return redirect(url_for('index'))
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator

def get_options(table):
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT value FROM {table} ORDER BY value")
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

def is_valid_option(table, value):
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM {table} WHERE value = ?", (value,))
        return cur.fetchone() is not None
    finally:
        conn.close()

def clean_number(val):
    return float(re.sub(r"[^0-9.-]", "", (val or '0'))) if re.sub(r"[^0-9.-]", "", (val or '')) != '' else 0.0

def compute_totals(base, prem, land, received, tos):
    total = (base + prem) * land
    balance = total - received
    by_plan = balance if tos == 'OTP' else (total * 0.20) - balance
    return total, balance, by_plan

@app.route('/')
def index():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    if user.role == 'ADMIN':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('crm_new'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(username=username).first()
            if user and check_password_hash(user.password_hash, password):
                session['user_id'] = user.id
                session['role'] = user.role
                if user.role == 'ADMIN':
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('crm_new'))
            flash('Invalid credentials', 'error')
        finally:
            db.close()
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# CRM Routes
@app.route('/crm/new', methods=['GET','POST'])
@login_required(role='CRM')
def crm_new():
    user = current_user()
    if request.method == 'POST':
        data = dict(request.form)
        errors = []
        spg = data.get('spg_praneeth','').strip() or 'SPG'
        tos = (data.get('type_of_sale','').strip() or 'OTP').upper()
        if not is_valid_option('spg_options', spg):
            errors.append('spg_praneeth invalid')
        if not is_valid_option('sale_type_options', tos):
            errors.append('type_of_sale invalid')
        base = clean_number(data.get('base_sqft_price'))
        prem = clean_number(data.get('amenties_and_premiums'))
        sbua = clean_number(data.get('sbua_sqft'))
        land = clean_number(data.get('land_sqyards'))
        amt_received = clean_number(data.get('amount_received'))
        total_sale_price, balance_amount, by_plan = compute_totals(base, prem, land, amt_received, tos)
        if errors:
            return jsonify({"ok": False, "errors": errors})
        # Get next s_no and insert
        conn = engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COALESCE(MAX(s_no), 0) + 1 FROM sale_details")
            next_sno = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO sale_details (
                    s_no, booking_date, project, spg_praneeth, token, buyer_name, sol, type_of_sale,
                    land_sqyards, sbua_sqft, facing, base_sqft_price, amenties_and_premiums,
                    total_sale_price, amount_received, balance_amount,
                    balance_tobe_received_by_plan_approval, notes, balance_tobe_received_during_exec,
                    sale_person_name, crm_name
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    int(next_sno),
                    data.get('booking_date') or None,
                    data.get('project'),
                    spg,
                    int(data.get('token') or 0) or None,
                    data.get('buyer_name'),
                    data.get('sol'),
                    tos,
                    int(land) if land else None,
                    float(sbua) if sbua else None,
                    data.get('facing'),
                    float(base) if base else None,
                    float(prem) if prem else None,
                    float(total_sale_price),
                    float(amt_received) if amt_received else None,
                    float(balance_amount),
                    float(by_plan),
                    data.get('notes'),
                    float(data.get('balance_tobe_received_during_exec') or 0) or None,
                    data.get('sale_person_name'),
                    user.username
                )
            )
            conn.commit()
        finally:
            conn.close()
        return jsonify({"ok": True})
    # GET: load options and next s_no
    conn = engine.raw_connection()
    spg_opts, tos_opts, next_sno = [], [], 1
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM spg_options ORDER BY value"); spg_opts = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT value FROM sale_type_options ORDER BY value"); tos_opts = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT COALESCE(MAX(s_no), 0) + 1 FROM sale_details"); next_sno = cur.fetchone()[0]
    finally:
        conn.close()
    today = datetime.today().strftime('%Y-%m-%d')
    return render_template('crm_new.html', user=user, spg_opts=spg_opts, tos_opts=tos_opts, next_sno=next_sno, today=today)

@app.route('/crm/list')
@login_required(role='CRM')
def crm_list():
    user = current_user()
    sort = request.args.get('sort','date_desc')
    order_clause = "(booking_date IS NULL) ASC, booking_date DESC, s_no"
    if sort == 'sno_desc':
        order_clause = "s_no DESC"
    elif sort == 'total_desc':
        order_clause = "total_sale_price DESC"
    conn = engine.raw_connection()
    rows = []
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT rowid, * FROM sale_details WHERE crm_name = ? ORDER BY {order_clause}", (user.username,))
        cols = [d[0] for d in cur.description]
        for r in cur.fetchall():
            rows.append(dict(zip(cols, r)))
    finally:
        conn.close()
    return render_template('crm_list.html', rows=rows, user=user, sort=sort)

@app.route('/crm/export')
@login_required(role='CRM')
def crm_export():
    user = current_user()
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT booking_date, s_no, buyer_name, sale_person_name, total_sale_price,
                   amount_received, balance_amount, balance_tobe_received_by_plan_approval,
                   balance_tobe_received_during_exec
            FROM sale_details WHERE crm_name = ? ORDER BY booking_date DESC, s_no
        """, (user.username,))
        rows = cur.fetchall()
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['booking_date','s_no','buyer_name','sale_person_name','total_sale_price','amount_received','balance_amount','balance_by_plan','balance_during_exec'])
        writer.writerows(rows)
        output.seek(0)
        return send_file(output, mimetype='text/csv', as_attachment=True, download_name='my_sales.csv')
    finally:
        conn.close()

@app.route('/crm/edit/<int:rowid>', methods=['GET','POST'])
@login_required(role='CRM')
def crm_edit(rowid):
    user = current_user()
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        if request.method == 'POST':
            data = dict(request.form)
            # Only allow editable non-calculated fields
            allowed = ['booking_date','project','spg_praneeth','token','buyer_name','sol','type_of_sale',
                       'land_sqyards','sbua_sqft','facing','base_sqft_price','amenties_and_premiums',
                       'amount_received','notes','sale_person_name']
            sets = []
            vals = []
            for k in allowed:
                if k in data:
                    sets.append(f"{k}=?")
                    vals.append(data[k])
            # Recompute calculated fields (updated formula)
            base = clean_number(data.get('base_sqft_price'))
            prem = clean_number(data.get('amenties_and_premiums'))
            sbua = clean_number(data.get('sbua_sqft'))
            land = clean_number(data.get('land_sqyards'))
            amt_received = clean_number(data.get('amount_received'))
            tos = (data.get('type_of_sale') or '').upper()
            total_sale_price, balance_amount, by_plan = compute_totals(base, prem, land, amt_received, tos)
            sets += ["total_sale_price=?","balance_amount=?","balance_tobe_received_by_plan_approval=?"]
            vals += [total_sale_price, balance_amount, by_plan]
            # Enforce ownership
            vals.append(user.username)
            vals.append(rowid)
            sql = f"UPDATE sale_details SET {', '.join(sets)} WHERE crm_name = ? AND rowid = ?"
            cur.execute(sql, tuple(vals))
            conn.commit()
            return redirect(url_for('crm_list'))
        else:
            cur.execute("SELECT rowid, * FROM sale_details WHERE crm_name = ? AND rowid = ?", (user.username, rowid))
            row = cur.fetchone()
            if not row:
                flash('Not found or unauthorized', 'error')
                return redirect(url_for('crm_list'))
            cols = [d[0] for d in cur.description]
            rec = dict(zip(cols, row))
            return render_template('crm_edit.html', row=rec, user=user)
    finally:
        conn.close()

@app.route('/crm/delete/<int:rowid>', methods=['POST'])
@login_required(role='CRM')
def crm_delete(rowid):
    user = current_user()
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM sale_details WHERE rowid = ? AND crm_name = ?", (rowid, user.username))
        conn.commit()
        flash('Entry deleted', 'success')
    finally:
        conn.close()
    return redirect(url_for('crm_list'))

# Admin routes
@app.route('/admin/dashboard')
@login_required(role='ADMIN')
def admin_dashboard():
    # Filters
    month = request.args.get('month')
    year = request.args.get('year')
    crm = request.args.get('crm_name')
    sp = request.args.get('sale_person_name')
    spg = request.args.get('spg_praneeth')
    tos = request.args.get('type_of_sale')
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        # Options for dropdowns
        cur.execute("SELECT DISTINCT crm_name FROM sale_details WHERE crm_name IS NOT NULL ORDER BY crm_name")
        crm_opts = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT sale_person_name FROM sale_details WHERE sale_person_name IS NOT NULL ORDER BY sale_person_name")
        sp_opts = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT value FROM spg_options ORDER BY value")
        spg_opts = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT value FROM sale_type_options ORDER BY value")
        tos_opts = [r[0] for r in cur.fetchall()]

        # Detailed rows (not grouped); show all active rows by default
        query = (
            "SELECT rowid, booking_date, s_no, crm_name, sale_person_name, buyer_name, project, spg_praneeth, "
            "type_of_sale, total_sale_price, amount_received, balance_amount, "
            "balance_tobe_received_by_plan_approval, balance_tobe_received_during_exec "
            "FROM sale_details WHERE 1=1"
        )
        params = []
        if year:
            query += " AND strftime('%Y', booking_date) = ?"; params.append(year)
        if month:
            query += " AND strftime('%m', booking_date) = ?"; params.append(month.zfill(2))
        if crm:
            query += " AND crm_name = ?"; params.append(crm)
        if sp:
            query += " AND sale_person_name = ?"; params.append(sp)
        if spg:
            query += " AND spg_praneeth = ?"; params.append(spg)
        if tos:
            query += " AND type_of_sale = ?"; params.append(tos)
        query += " ORDER BY (booking_date IS NULL) ASC, booking_date DESC, s_no DESC"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        data = [dict(zip(cols, r)) for r in rows]
        return render_template('admin_dashboard.html', data=data, filters={'year':year,'month':month,'crm':crm,'sp':sp,'spg':spg,'tos':tos},
                               crm_opts=crm_opts, sp_opts=sp_opts, spg_opts=spg_opts, tos_opts=tos_opts)
    finally:
        conn.close()

@app.route('/admin/export')
@login_required(role='ADMIN')
def admin_export():
    # Export current filtered dashboard data as CSV
    month = request.args.get('month')
    year = request.args.get('year')
    crm = request.args.get('crm_name')
    sp = request.args.get('sale_person_name')
    spg = request.args.get('spg_praneeth')
    tos = request.args.get('type_of_sale')
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        query = "SELECT booking_date, crm_name, sale_person_name, spg_praneeth, type_of_sale, total_sale_price FROM sale_details WHERE 1=1"
        params = []
        if year:
            query += " AND strftime('%Y', booking_date) = ?"; params.append(year)
        if month:
            query += " AND strftime('%m', booking_date) = ?"; params.append(month.zfill(2))
        if crm:
            query += " AND crm_name = ?"; params.append(crm)
        if sp:
            query += " AND sale_person_name = ?"; params.append(sp)
        if spg:
            query += " AND spg_praneeth = ?"; params.append(spg)
        if tos:
            query += " AND type_of_sale = ?"; params.append(tos)
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['booking_date','crm_name','sale_person_name','spg_praneeth','type_of_sale','total_sale_price'])
        for r in rows:
            writer.writerow(r)
        output.seek(0)
        return send_file(output, mimetype='text/csv', as_attachment=True, download_name='dashboard_export.csv')
    finally:
        conn.close()

@app.route('/admin/crms')
@login_required(role='ADMIN')
def admin_crms():
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.username).all()
        return render_template('admin_crms.html', users=users)
    finally:
        db.close()

@app.route('/admin/crms/new', methods=['POST'])
@login_required(role='ADMIN')
def admin_crms_new():
    username = request.form.get('username','').strip()
    password = request.form.get('password','').strip()
    role = request.form.get('role','CRM')
    if not username or not password or role not in ('CRM','ADMIN'):
        flash('Provide username, password, and valid role', 'error')
        return redirect(url_for('admin_crms'))
    db = SessionLocal()
    try:
        if db.query(User).filter_by(username=username).first():
            flash('Username already exists', 'error')
        else:
            db.add(User(username=username, password_hash=generate_password_hash(password), role=role))
            db.commit()
            flash('User created', 'success')
    finally:
        db.close()
    return redirect(url_for('admin_crms'))

@app.route('/admin/crms/<int:uid>/edit', methods=['POST'])
@login_required(role='ADMIN')
def admin_crms_edit(uid):
    password = request.form.get('password','').strip()
    role = request.form.get('role','CRM')
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        if not u:
            flash('User not found', 'error')
        else:
            if password:
                u.password_hash = generate_password_hash(password)
            u.role = role if role in ('CRM','ADMIN') else u.role
            db.commit()
            flash('User updated', 'success')
    finally:
        db.close()
    return redirect(url_for('admin_crms'))

@app.route('/admin/crms/<int:uid>/delete', methods=['POST'])
@login_required(role='ADMIN')
def admin_crms_delete(uid):
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        if not u:
            flash('User not found', 'error')
        else:
            db.delete(u)
            db.commit()
            flash('User deleted', 'success')
    finally:
        db.close()
    return redirect(url_for('admin_crms'))

# Admin can create new sale entries (won't be editable by CRMs)
@app.route('/admin/new', methods=['GET','POST'])
@login_required(role='ADMIN')
def admin_new():
    user = current_user()
    if request.method == 'POST':
        data = dict(request.form)
        errors = []
        spg = (data.get('spg_praneeth','').strip() or 'SPG')
        tos = (data.get('type_of_sale','').strip() or 'OTP').upper()
        if not is_valid_option('spg_options', spg):
            errors.append('spg_praneeth invalid')
        if not is_valid_option('sale_type_options', tos):
            errors.append('type_of_sale invalid')
        base = clean_number(data.get('base_sqft_price'))
        prem = clean_number(data.get('amenties_and_premiums'))
        sbua = clean_number(data.get('sbua_sqft'))
        land = clean_number(data.get('land_sqyards'))
        amt_received = clean_number(data.get('amount_received'))
        total_sale_price, balance_amount, by_plan = compute_totals(base, prem, land, amt_received, tos)
        if errors:
            flash('; '.join(errors), 'error')
            return redirect(url_for('admin_new'))
        conn = engine.raw_connection()
        try:
            cur = conn.cursor()
            # next s_no
            cur.execute("SELECT COALESCE(MAX(s_no), 0) + 1 FROM sale_details")
            next_sno = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO sale_details (
                    s_no, booking_date, project, spg_praneeth, token, buyer_name, sol, type_of_sale,
                    land_sqyards, sbua_sqft, facing, base_sqft_price, amenties_and_premiums,
                    total_sale_price, amount_received, balance_amount,
                    balance_tobe_received_by_plan_approval, notes, balance_tobe_received_during_exec,
                    sale_person_name, crm_name
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    int(next_sno),
                    data.get('booking_date') or None,
                    data.get('project'),
                    spg,
                    int(data.get('token') or 0) or None,
                    data.get('buyer_name'),
                    data.get('sol'),
                    tos,
                    int(land) if land else None,
                    float(sbua) if sbua else None,
                    data.get('facing'),
                    float(base) if base else None,
                    float(prem) if prem else None,
                    float(total_sale_price),
                    float(amt_received) if amt_received else None,
                    float(balance_amount),
                    float(by_plan),
                    data.get('notes'),
                    float(data.get('balance_tobe_received_during_exec') or 0) or None,
                    data.get('sale_person_name'),
                    user.username
                )
            )
            conn.commit()
        finally:
            conn.close()
        flash('Sale created', 'success')
        return redirect(url_for('admin_new', saved=1))
    # GET: provide options, next s_no, and today
    conn = engine.raw_connection()
    spg_opts, tos_opts, next_sno = [], [], 1
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM spg_options ORDER BY value"); spg_opts = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT value FROM sale_type_options ORDER BY value"); tos_opts = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT COALESCE(MAX(s_no), 0) + 1 FROM sale_details"); next_sno = cur.fetchone()[0]
    finally:
        conn.close()
    today = datetime.today().strftime('%Y-%m-%d')
    return render_template('admin_new.html', spg_opts=spg_opts, tos_opts=tos_opts, next_sno=next_sno, today=today)

# Admin: My Entries list (only entries created by this admin)
@app.route('/admin/entries')
@login_required(role='ADMIN')
def admin_entries():
    user = current_user()
    sort = request.args.get('sort','date_desc')
    order_clause = "(booking_date IS NULL) ASC, booking_date DESC, s_no"
    if sort == 'sno_desc':
        order_clause = "s_no DESC"
    elif sort == 'total_desc':
        order_clause = "total_sale_price DESC"
    conn = engine.raw_connection()
    rows = []
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT rowid, * FROM sale_details WHERE crm_name = ? ORDER BY {order_clause}", (user.username,))
        cols = [d[0] for d in cur.description]
        for r in cur.fetchall():
            rows.append(dict(zip(cols, r)))
    finally:
        conn.close()
    return render_template('admin_list.html', rows=rows, user=user, sort=sort)

# Admin: Edit own entry
@app.route('/admin/edit/<int:rowid>', methods=['GET','POST'])
@login_required(role='ADMIN')
def admin_edit(rowid):
    user = current_user()
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        if request.method == 'POST':
            data = dict(request.form)
            allowed = ['booking_date','project','spg_praneeth','token','buyer_name','sol','type_of_sale',
                       'land_sqyards','sbua_sqft','facing','base_sqft_price','amenties_and_premiums',
                       'amount_received','notes','sale_person_name']
            sets = []
            vals = []
            for k in allowed:
                if k in data:
                    sets.append(f"{k}=?")
                    vals.append(data[k])
            def cleanf(x):
                return float(re.sub(r"[^0-9.-]", "", x or '0') or 0)
            base = cleanf(data.get('base_sqft_price'))
            prem = cleanf(data.get('amenties_and_premiums'))
            sbua = float(data.get('sbua_sqft') or 0)
            land = cleanf(data.get('land_sqyards'))
            amt_received = cleanf(data.get('amount_received'))
            total_sale_price = (base + prem) * land
            balance_amount = total_sale_price - amt_received
            tos = (data.get('type_of_sale') or '').upper()
            by_plan = balance_amount if tos == 'OTP' else (total_sale_price * 0.20) - balance_amount
            sets += ["total_sale_price= ?","balance_amount= ?","balance_tobe_received_by_plan_approval= ?"]
            vals += [total_sale_price, balance_amount, by_plan]
            vals.append(user.username)
            vals.append(rowid)
            sql = f"UPDATE sale_details SET {', '.join(sets)} WHERE crm_name = ? AND rowid = ?"
            cur.execute(sql, tuple(vals))
            conn.commit()
            return redirect(url_for('admin_entries'))
        else:
            cur.execute("SELECT rowid, * FROM sale_details WHERE crm_name = ? AND rowid = ?", (user.username, rowid))
            row = cur.fetchone()
            if not row:
                flash('Not found or unauthorized', 'error')
                return redirect(url_for('admin_entries'))
            cols = [d[0] for d in cur.description]
            rec = dict(zip(cols, row))
            return render_template('crm_edit.html', row=rec, user=user)
    finally:
        conn.close()

# Admin: Delete own entry
@app.route('/admin/delete/<int:rowid>', methods=['POST'])
@login_required(role='ADMIN')
def admin_delete(rowid):
    user = current_user()
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM sale_details WHERE rowid = ? AND crm_name = ?", (rowid, user.username))
        conn.commit()
        flash('Entry deleted', 'success')
    finally:
        conn.close()
    return redirect(url_for('admin_entries'))

@app.route('/admin/options', methods=['GET','POST'])
@login_required(role='ADMIN')
def admin_options():
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        if request.method == 'POST':
            kind = request.form.get('kind')
            val = (request.form.get('value') or '').strip()
            action = request.form.get('action')
            table = 'spg_options' if kind == 'spg' else 'sale_type_options'
            if action == 'add' and val:
                try:
                    cur.execute(f"INSERT INTO {table}(value) VALUES (?)", (val,))
                    conn.commit()
                    flash('Option added', 'success')
                except Exception:
                    flash('Option exists or invalid', 'error')
            elif action == 'delete' and val:
                cur.execute(f"DELETE FROM {table} WHERE value = ?", (val,))
                conn.commit()
                flash('Option deleted', 'success')
        cur.execute("SELECT value FROM spg_options ORDER BY value"); spg = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT value FROM sale_type_options ORDER BY value"); tos = [r[0] for r in cur.fetchall()]
        return render_template('admin_options.html', spg=spg, tos=tos)
    finally:
        conn.close()

# Static helper route for field rules (shown as tooltips/help)
@app.route('/field-rules')
def field_rules():
    return jsonify({
        'spg_praneeth': 'Allowed values: SPG or Praneeth',
        'type_of_sale': 'Allowed values: OTP or R',
        'calculated': 'Calculated: total_sale_price, balance_amount, balance_tobe_received_by_plan_approval',
    })

if __name__ == '__main__':
    app.run(debug=True)
