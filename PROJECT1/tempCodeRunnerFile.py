import io
import os
import pandas as pd
import mysql.connector
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, flash
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from datetime import datetime

print("--- 1. Libraries Imported Successfully ---")

app = Flask(__name__)
app.secret_key = 'gce_salem_admin_dashboard_2025'

# ==========================================
# 1. DATABASE & UTILS
# ==========================================
def num_to_words(num):
    try:
        num = int(num)
        if num == 0: return "Zero"
        
        units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
        teens = ["Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
        
        def convert_chunk(n):
            if n < 10: return units[n]
            elif n < 20: return teens[n-10]
            elif n < 100: return tens[n // 10] + (" " + units[n % 10] if n % 10 != 0 else "")
            elif n < 1000: return units[n // 100] + " Hundred" + (" and " + convert_chunk(n % 100) if n % 100 != 0 else "")
            return ""

        words = ""
        if num >= 10000000:
            words += convert_chunk(num // 10000000) + " Crore "
            num %= 10000000
        if num >= 100000:
            words += convert_chunk(num // 100000) + " Lakh "
            num %= 100000
        if num >= 1000:
            words += convert_chunk(num // 1000) + " Thousand "
            num %= 1000
        if num > 0:
            words += convert_chunk(num)
            
        return words.strip() + " only"
    except:
        return "Zero only"

def format_val(val):
    try:
        if pd.isna(val) or str(val).strip() == '' or str(val).lower() == 'nan': return ''
        if float(val).is_integer(): return str(int(float(val)))
        return str(val)
    except:
        return str(val)

def clean_btype(val):
    try:
        if pd.isna(val) or str(val).strip() == '' or str(val).lower() == 'nan': return 'Nationalized'
        res = str(val).replace('(MRFT)', '').replace('(mrft)', '').replace('(ECS)', '').replace('(ecs)', '').strip()
        return res
    except:
        return 'Nationalized'

def get_db():
    return mysql.connector.connect(host="localhost", user="root", password="", database="scrutiny_db")

def get_logo_path():
    base = os.path.dirname(os.path.abspath(__file__))
    for n in ['logo.jpg', 'logo.png', 'logo.jpeg', 'LOGO.JPG']: 
        if os.path.exists(os.path.join(base, n)): return os.path.join(base, n)
    return None

def safe_float(val): 
    try: return float(val) if val else 0.0
    except: return 0.0

def normalize_columns(df):
    """Translates Excel headers to match our database columns perfectly"""
    df.columns = [str(c).strip().lower() for c in df.columns]
    rename_map = {
        'faculty id': 'faculty_id', 'faculty_id': 'faculty_id', 'id': 'faculty_id',
        'name': 'name', 'faculty name': 'name',
        'designation': 'designation', 'desig': 'designation',
        'department': 'department', 'dept': 'department',
        'institution address': 'institution_address', 'institution_address': 'institution_address', 
        'institution': 'institution_address', 'college': 'institution_address', 'address': 'institution_address',
        'mobile': 'mobile_number', 'mobile number': 'mobile_number', 'contact': 'mobile_number',
        'email': 'email_address', 'email address': 'email_address', 'mail id': 'email_address',
        'bank': 'bank_name', 'bank name': 'bank_name',
        'acc no': 'account_number', 'account number': 'account_number', 'a/c no': 'account_number',
        'ifsc': 'ifsc', 'ifsc code': 'ifsc',
        'branch': 'branch_name', 'branch name': 'branch_name',
        'place': 'place', 'city': 'place',
        'dist': 'distance', 'distance': 'distance',
        'cat': 'category', 'category': 'category',
        'type': 'bank_type', 'bank type': 'bank_type', 'payment mode': 'bank_type',
        'course code': 'course_code', 'subject code': 'course_code', 'sub code': 'course_code',
        'course name': 'course_name', 'subject name': 'course_name', 'sub name': 'course_name',
        'reg': 'regulation', 'sem': 'semester'
    }
    final_rename = {}
    for col in df.columns:
        if col in rename_map:
            final_rename[col] = rename_map[col]
    return df.rename(columns=final_rename)

def init_db():
    print("--- 2. Attempting to connect to XAMPP MySQL... ---")
    try:
        # TIMEOUT ADDED: If XAMPP is broken, this fails in 5 secs instead of hanging forever
        db = mysql.connector.connect(host="localhost", user="root", password="", connection_timeout=5)
        print("--- 3. SUCCESS! Connected to MySQL. ---")
        
        c = db.cursor()
        print("--- 4. Checking/Creating Database and Tables... ---")
        c.execute("CREATE DATABASE IF NOT EXISTS scrutiny_db")
        c.execute("USE scrutiny_db")
        
        c.execute("CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(50), password VARCHAR(100), role VARCHAR(20))")
        c.execute("SELECT COUNT(*) FROM users")
        if c.fetchone()[0] == 0: 
            c.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'coe123', 'admin')")
        
        c.execute("""CREATE TABLE IF NOT EXISTS faculty_master (
            faculty_id VARCHAR(50) PRIMARY KEY, name VARCHAR(150), designation VARCHAR(150), 
            department VARCHAR(150), institution_address TEXT, mobile_number VARCHAR(50), 
            email_address VARCHAR(150), bank_name VARCHAR(150), account_number VARCHAR(50), 
            ifsc VARCHAR(50), branch_name VARCHAR(150), place VARCHAR(150), 
            distance FLOAT DEFAULT 0, category VARCHAR(50), bank_type VARCHAR(50) DEFAULT 'Nationalized'
        )""")
        
        c.execute("DESCRIBE faculty_master")
        cols = [r[0].lower() for r in c.fetchall()]
        if 'bank_type' not in cols: 
            c.execute("ALTER TABLE faculty_master ADD COLUMN bank_type VARCHAR(50) DEFAULT 'Nationalized'")
        
        c.execute("CREATE TABLE IF NOT EXISTS course_master (course_code VARCHAR(50) PRIMARY KEY, course_name VARCHAR(200), department VARCHAR(100), regulation VARCHAR(20), semester INT)")
        c.execute("CREATE TABLE IF NOT EXISTS calendar_master (date DATE PRIMARY KEY, day_type VARCHAR(50) DEFAULT 'Working', description VARCHAR(150))")
        
        c.execute("""CREATE TABLE IF NOT EXISTS scrutiny_records (
            id INT AUTO_INCREMENT PRIMARY KEY, faculty_id VARCHAR(50), scrutiny_date DATE, 
            courses_count INT, remuneration FLOAT, ta_amount FLOAT, da_amount FLOAT, 
            grand_total FLOAT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
            generated_by VARCHAR(50) DEFAULT 'unknown', regulation VARCHAR(20), 
            session_name VARCHAR(50), session_year VARCHAR(20)
        )""")
        
        db.commit()
        db.close()
        print("--- 5. Database Setup Complete! ---")
    except Exception as e: 
        print(f"\n!!!!!! CRITICAL DB ERROR !!!!!!\n{e}\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")

print("--- 6. Running Initial Setup... ---")
init_db()

# ==========================================
# 2. ROUTES
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    db = get_db()
    c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM users WHERE username=%s AND password=%s", (request.form['username'], request.form['password']))
    user = c.fetchone()
    db.close()
    if user:
        session['user'] = user['username']
        session['role'] = user['role']
        return redirect(url_for('dashboard'))
    return render_template('index.html', error="Invalid Credentials")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user' in session: return render_template('dashboard.html')
    return redirect(url_for('index'))

# --- FACULTY MANAGER ---
@app.route('/manage_faculty', methods=['GET', 'POST'])
def manage_faculty():
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db()
    c = db.cursor(dictionary=True)
    
    if request.method == 'POST':
        if 'file' in request.files:
            try:
                file = request.files['file']
                if file.filename != '':
                    df = pd.read_excel(file) if file.filename.endswith('.xlsx') else pd.read_csv(file)
                    df = normalize_columns(df)
                    if 'faculty_id' in df.columns:
                        for _, r in df.iterrows():
                            fid = str(r.get('faculty_id')).strip()
                            if not fid or fid == 'nan': continue
                            
                            b_type = clean_btype(r.get('bank_type'))
                            dist = safe_float(r.get('distance'))
                            
                            sql = "REPLACE INTO faculty_master (faculty_id, name, designation, department, institution_address, mobile_number, email_address, bank_name, account_number, ifsc, branch_name, place, distance, category, bank_type) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                            val = (
                                fid, str(r.get('name'))[:150], str(r.get('designation'))[:150], 
                                str(r.get('department'))[:150], str(r.get('institution_address')), 
                                format_val(r.get('mobile_number')), str(r.get('email_address')), 
                                str(r.get('bank_name')), format_val(r.get('account_number')), 
                                str(r.get('ifsc')), str(r.get('branch_name')), str(r.get('place')), 
                                dist, str(r.get('category')), b_type
                            )
                            c.execute(sql, val)
                        db.commit()
                        flash("Faculty uploaded successfully!", "success")
            except Exception as e: flash(f"Error: {str(e)}", "danger")
        else:
            f = request.form
            b_type = clean_btype(f.get('bank_type', 'Nationalized'))
            sql = "REPLACE INTO faculty_master (faculty_id, name, designation, department, institution_address, mobile_number, email_address, bank_name, account_number, ifsc, branch_name, place, distance, category, bank_type) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            val = (f['faculty_id'], f['name'], f['designation'], f['department'], f['institution_address'], f['mobile_number'], f['email_address'], f['bank_name'], f['account_number'], f['ifsc'], f['branch_name'], f['place'], float(f['distance'] or 0), f['category'], b_type)
            c.execute(sql, val)
            db.commit()
            flash("Saved!", "success")
    
    c.execute("SELECT * FROM faculty_master")
    fac = c.fetchall()
    db.close()
    return render_template('manage_faculty.html', faculty=fac)

@app.route('/delete_faculty/<fid>')
def delete_faculty(fid):
    db = get_db()
    db.cursor().execute("DELETE FROM faculty_master WHERE faculty_id=%s", (fid,))
    db.commit()
    db.close()
    return redirect(url_for('manage_faculty'))

# --- COURSE MANAGER ---
@app.route('/manage_courses', methods=['GET', 'POST'])
def manage_courses():
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db()
    c = db.cursor(dictionary=True)
    
    if request.method == 'POST':
        if 'file' in request.files:
            try:
                file = request.files['file']
                if file.filename != '':
                    df = pd.read_excel(file) if file.filename.endswith('.xlsx') else pd.read_csv(file)
                    df = normalize_columns(df)
                    if 'course_code' in df.columns:
                        for _, r in df.iterrows():
                            ccode = str(r.get('course_code')).strip()
                            if not ccode or ccode == 'nan': continue
                            cname = str(r.get('course_name'))[:200]
                            dept = str(r.get('department'))[:100]
                            reg = str(r.get('regulation'))[:20]
                            
                            sem = r.get('semester')
                            try: sem = int(float(sem)) if pd.notna(sem) and str(sem).strip() != '' else 0
                            except: sem = 0
                            
                            sql = "REPLACE INTO course_master (course_code, course_name, department, regulation, semester) VALUES (%s,%s,%s,%s,%s)"
                            c.execute(sql, (ccode, cname, dept, reg, sem))
                        db.commit()
                        flash("Courses uploaded successfully!", "success")
            except Exception as e: flash(f"Error: {str(e)}", "danger")
        else:
            f = request.form
            sql = "REPLACE INTO course_master (course_code, course_name, department, regulation, semester) VALUES (%s,%s,%s,%s,%s)"
            c.execute(sql, (f['course_code'], f['course_name'], f['department'], f['regulation'], int(f['semester'] or 0)))
            db.commit()
            flash("Course Saved!", "success")
    
    c.execute("SELECT * FROM course_master")
    courses = c.fetchall()
    db.close()
    return render_template('manage_courses.html', courses=courses)

@app.route('/delete_course/<path:ccode>')
def delete_course(ccode):
    db = get_db()
    db.cursor().execute("DELETE FROM course_master WHERE course_code=%s", (ccode,))
    db.commit()
    db.close()
    return redirect(url_for('manage_courses'))


# --- CALENDAR MANAGER ---
@app.route('/manage_calendar')
def manage_calendar():
    if 'user' not in session: return redirect(url_for('index'))
    return render_template('manage_calendar.html')

@app.route('/api/get_calendar_events')
def get_calendar_events():
    db = get_db()
    c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM calendar_master")
    events = c.fetchall()
    db.close()
    return jsonify({str(e['date']): e['day_type'] for e in events})

@app.route('/api/toggle_calendar_date', methods=['POST'])
def toggle_calendar_date():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    date_val = request.json.get('date')
    try:
        dt_obj = datetime.strptime(date_val, '%Y-%m-%d')
        is_sunday = (dt_obj.weekday() == 6)
        db = get_db()
        c = db.cursor(dictionary=True)
        c.execute("SELECT * FROM calendar_master WHERE date=%s", (date_val,))
        if c.fetchone():
            c.execute("DELETE FROM calendar_master WHERE date=%s", (date_val,))
            new_status = 'Default'
        else:
            new_type = 'Working' if is_sunday else 'Holiday'
            c.execute("INSERT INTO calendar_master (date, day_type, description) VALUES (%s, %s, %s)", (date_val, new_type, 'Toggle'))
            new_status = new_type
        db.commit()
        db.close()
        return jsonify({"success": True, "new_status": new_status, "date": date_val})
    except Exception as e: return jsonify({"error": str(e)}), 500

# --- SESSION WORKFLOW ---
@app.route('/session_selector')
def session_selector():
    if 'user' not in session: return redirect(url_for('index'))
    return render_template('session_selector.html')

@app.route('/session_hub', methods=['GET', 'POST'])
def session_hub():
    if 'user' not in session: return redirect(url_for('index'))
    if request.method == 'POST':
        session['active_sess'] = request.form.get('session_name')
        session['active_year'] = request.form.get('session_year')
    if 'active_sess' not in session: return redirect(url_for('session_selector'))
    return render_template('session_hub.html', sess=session['active_sess'], yr=session['active_year'])

@app.route('/scrutiny')
def scrutiny():
    if 'user' not in session or 'active_sess' not in session: return redirect(url_for('session_selector'))
    return render_template('scrutiny.html', sess=session['active_sess'], yr=session['active_year'])


# --- REPORTS & EXCEL ---
@app.route('/report')
def report():
    if 'user' not in session or 'active_sess' not in session: return redirect(url_for('session_selector'))
    sess = session['active_sess']
    yr = session['active_year']
    
    cat = request.args.get('category', 'All')
    bank = request.args.get('bank_type', 'All')
    search_fid = request.args.get('search_fid', '').strip()
    
    db = get_db()
    c = db.cursor(dictionary=True)
    
    is_detailed = False
    p = [sess, yr]

    if search_fid:
        # DETAILED VIEW: Shows every single day they worked
        is_detailed = True
        q = """SELECT s.scrutiny_date, s.courses_count, s.remuneration, s.ta_amount, s.da_amount, s.grand_total, 
                      f.faculty_id, f.name, f.department, f.bank_name, f.account_number, f.ifsc, f.category, f.bank_type 
               FROM scrutiny_records s LEFT JOIN faculty_master f ON s.faculty_id = f.faculty_id 
               WHERE s.session_name=%s AND s.session_year=%s AND s.faculty_id=%s ORDER BY s.scrutiny_date DESC"""
        p.append(search_fid)
        c.execute(q, tuple(p))
    else:
        # CONSOLIDATED VIEW: Group by Faculty ID (1 row per faculty)
        q = """SELECT s.faculty_id, MAX(s.scrutiny_date) as scrutiny_date, 
                      SUM(s.courses_count) as courses_count, SUM(s.remuneration) as remuneration, 
                      SUM(s.ta_amount) as ta_amount, SUM(s.da_amount) as da_amount, SUM(s.grand_total) as grand_total,
                      f.name, f.department, f.bank_name, f.account_number, f.ifsc, f.category, f.bank_type 
               FROM scrutiny_records s LEFT JOIN faculty_master f ON s.faculty_id = f.faculty_id 
               WHERE s.session_name=%s AND s.session_year=%s"""
        
        if cat != 'All': 
            q += " AND f.category=%s"
            p.append(cat)
        if bank != 'All': 
            q += " AND f.bank_type=%s"
            p.append(bank)
        
        q += " GROUP BY s.faculty_id, f.name, f.department, f.bank_name, f.account_number, f.ifsc, f.category, f.bank_type ORDER BY MAX(s.created_at) DESC"
        c.execute(q, tuple(p))
        
    recs = c.fetchall()
    db.close()
    
    tot = {"remun":0, "ta":0, "da":0, "grand":0}
    bank_abs = {}
    for r in recs:
        tot['remun'] += r['remuneration']
        tot['ta'] += r['ta_amount']
        tot['da'] += r['da_amount']
        tot['grand'] += r['grand_total']
        
        if not is_detailed: 
            b = clean_btype(r['bank_name']) if r['bank_name'] else "Unknown"
            if b not in bank_abs: bank_abs[b] = {'count':0, 'total':0}
            bank_abs[b]['count'] += 1
            bank_abs[b]['total'] += r['grand_total']
        
    return render_template('consolidated_report.html', records=recs, totals=tot, cat_filter=cat, bank_filter=bank, search_fid=search_fid, is_detailed=is_detailed, bank_abstract=bank_abs, sess=sess, yr=yr)

@app.route('/export_excel')
def export_excel():
    if 'user' not in session or 'active_sess' not in session: return redirect(url_for('session_selector'))
    sess = session['active_sess']
    yr = session['active_year']
    
    db = get_db()
    c = db.cursor(dictionary=True)
    
    # Excel always exports the CONSOLIDATED totals
    query = """
        SELECT 
            f.faculty_id AS 'Faculty ID',
            f.name AS 'Name',
            f.department AS 'Department',
            f.bank_name AS 'Bank Name',
            f.account_number AS 'Account Number',
            f.ifsc AS 'IFSC',
            f.bank_type AS 'Bank Type',
            f.category AS 'Category',
            MAX(s.scrutiny_date) AS 'Latest Scrutiny Date',
            SUM(s.courses_count) AS 'Total QPs',
            SUM(s.remuneration) AS 'Total Remuneration',
            SUM(s.ta_amount) AS 'Total TA',
            SUM(s.da_amount) AS 'Total DA',
            SUM(s.grand_total) AS 'Grand Total'
        FROM scrutiny_records s
        JOIN faculty_master f ON s.faculty_id = f.faculty_id
        WHERE s.session_name=%s AND s.session_year=%s
        GROUP BY f.faculty_id, f.name, f.department, f.bank_name, f.account_number, f.ifsc, f.bank_type, f.category
    """
    c.execute(query, (sess, yr))
    recs = c.fetchall()
    db.close()

    if not recs:
        flash("No data available to export.", "danger")
        return redirect(url_for('report'))

    df = pd.DataFrame(recs)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Consolidated Bank Statement')
    output.seek(0)

    filename = f"Bank_Statement_{sess.replace('/', '-')}_{yr}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# --- APIs ---
@app.route('/api/search_courses')
def api_search(): 
    q = request.args.get('q','')
    db = get_db()
    c = db.cursor(dictionary=True)
    c.execute("SELECT course_code, course_name, regulation FROM course_master WHERE course_code LIKE %s OR course_name LIKE %s LIMIT 10", (f"%{q}%", f"%{q}%"))
    res = c.fetchall()
    db.close()
    return jsonify(res)

@app.route('/get_faculty/<fid>')
def get_fac(fid):
    db = get_db()
    c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM faculty_master WHERE faculty_id=%s", (fid,))
    r = c.fetchone()
    db.close()
    return jsonify(r) if r else jsonify({"error":"Not Found"})

# --- PROCESS SINGLE CLAIM (INSERT ALWAYS FOR HISTORY) ---
@app.route('/process', methods=['POST'])
def process():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    try:
        d = request.json
        db = get_db()
        c = db.cursor(dictionary=True)
        c.execute("SELECT * FROM faculty_master WHERE faculty_id=%s", (d['faculty_id'],))
        fac = c.fetchone()
        
        courses = []
        tot_qps = 0
        for i in d.get('courses', []):
            if not i.get('code'): continue
            qty = int(i.get('count', 1))
            c.execute("SELECT * FROM course_master WHERE course_code=%s", (i['code'],))
            cm = c.fetchone()
            courses.append({
                'course_code': i['code'], 
                'course_name': cm['course_name'] if cm else 'Manual Entry', 
                'qty': qty, 
                'amount': qty * 150.0
            })
            tot_qps += qty
            
        c.execute("SELECT day_type FROM calendar_master WHERE date=%s", (d['date'],))
        cal = c.fetchone()
        is_hol = (cal['day_type'] == 'Holiday') if cal else (datetime.strptime(d['date'], '%Y-%m-%d').weekday() == 6)
        
        remun = tot_qps * 150.0
        dist = int(fac['distance']) if fac['distance'] else 0
        is_external = (fac['category'] == 'External')
        
        ta, da = 0.0, 0.0
        internal_da, external_da = 0.0, 0.0
        
        if is_external:
            if dist < 35: 
                external_da = 200.0; ta = 400.0
            else: 
                external_da = 300.0; ta = dist * 12.0
        else:
            if is_hol: internal_da = 150.0
            
        da = internal_da + external_da
        grand = remun + ta + da
        
        # WE INSERT EVERY TIME TO PRESERVE HISTORY
        c.execute("""INSERT INTO scrutiny_records (faculty_id, scrutiny_date, courses_count, remuneration, ta_amount, da_amount, grand_total, generated_by, regulation, session_name, session_year) 
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", 
                  (fac['faculty_id'], d['date'], tot_qps, remun, ta, da, grand, session.get('user'), 
                   '', d['session_name'], d['session_year']))
        db.commit()
        db.close()
        
        # --- GENERATE PDF BUNDLE ---
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        logo = get_logo_path()
        
        mob = format_val(fac['mobile_number'])
        acc = format_val(fac['account_number'])
        clean_bank_type = clean_btype(fac['bank_type'])

        # ------------------ PAGE 1: CLAIM FORM ------------------
        pdf.add_page()
        if logo: pdf.image(logo, x=10, y=5, w=22)
        
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(190, 5, "GOVERNMENT COLLEGE OF ENGINEERING, SALEM - 636 011", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.set_font("Helvetica", '', 8)
        pdf.cell(190, 4, "(NAAC Accredited with A+, An Autonomous Institution, Affiliated to Anna University, Chennai)", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.set_font("Helvetica", 'B', 9)
        pdf.cell(190, 5, "OFFICE OF THE CONTROLLER OF EXAMINATIONS", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.ln(1)
        pdf.cell(190, 5, f"B.E. / M.E. DEGREE EXAMINATIONS - {d['session_name'].upper()} {d['session_year']} SESSION", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.cell(190, 5, "CLAIM FOR SCRUTINY MEMBER", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.ln(3)
        
        pdf.set_font("Helvetica", '', 8)
        def row_info(l1, v1, l2, v2):
            pdf.cell(40, 5, l1, border=0)
            pdf.cell(70, 5, str(v1), border=0) 
            pdf.cell(5, 5, "", border=0)
            pdf.cell(30, 5, l2, border=0)
            pdf.cell(45, 5, str(v2), border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        row_info("MONTH and YEAR :", f"{d['session_name']} {d['session_year']}", "Phase :", "I / II")
        row_info("FACULTY ID :", fac['faculty_id'], "Board :", fac['department'])
        row_info("SCRUTINY MEMBER:", fac['name'], "BANK NAME :", fac['bank_name'])
        row_info("DESIGNATION :", fac['designation'], "ACCOUNT NUMBER :", acc)
        row_info("INSTITUTION ADDRESS:", fac['institution_address'], "IFSC :", fac['ifsc'])
        row_info("MOBILE NUMBER :", mob, "BRANCH NAME :", fac['branch_name'])
        row_info("E-MAIL ADDRESS :", fac['email_address'], "BANK TYPE :", clean_bank_type)
        
        pdf.ln(3)
        pdf.set_font("Helvetica", 'B', 8)
        pdf.cell(190, 5, "Remuneration Details :", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_fill_color(240, 240, 240)
        
        widths = [7, 10, 18, 38, 11, 11]
        headers = ["S.No", "Degree", "Course Code", "Course Name", "QPs", "Amt(Rs)"]
        
        for _ in range(2):
            for w, h in zip(widths, headers):
                pdf.cell(w, 6, h, border=1, align='C', fill=True)
        pdf.ln()
        
        pdf.set_font("Helvetica", '', 7)
        for r_idx in range(5):
            for col_offset in [0, 5]:
                idx = r_idx + col_offset
                if idx < len(courses):
                    c = courses[idx]
                    pdf.cell(widths[0], 5, str(idx+1), border=1, align='C')
                    pdf.cell(widths[1], 5, "B.E", border=1, align='C')
                    pdf.cell(widths[2], 5, str(c['course_code']), border=1, align='C')
                    pdf.cell(widths[3], 5, f" {str(c['course_name'])[:22]}", border=1, align='L')
                    pdf.cell(widths[4], 5, str(c['qty']), border=1, align='C')
                    pdf.cell(widths[5], 5, f"{c['amount']:.0f}", border=1, align='R')
                else:
                    for w in widths:
                        pdf.cell(w, 5, "", border=1)
            pdf.ln()
        
        pdf.set_font("Helvetica", 'B', 7)
        pdf.cell(73, 5, "Total Number of Question Paper(s) Scrutinised:", border=1, align='R')
        pdf.cell(11, 5, str(tot_qps), border=1, align='C')
        pdf.cell(84, 5, "Total Claim (Rs) for Scrutinised Question Paper(s):", border=1, align='R')
        pdf.cell(22, 5, f"{remun:.0f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        
        pdf.ln(3)
        
        # --- TRAVELLING ALLOWANCE ---
        pdf.set_font("Helvetica", 'B', 8)
        pdf.cell(190, 5, "Travelling Allowance (TA)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_fill_color(230, 230, 230)
        
        pdf.cell(20, 8, "Date", border=1, align='C', fill=True)
        pdf.cell(40, 8, "From", border=1, align='C', fill=True)
        pdf.cell(40, 8, "To", border=1, align='C', fill=True)
        pdf.cell(25, 8, "Distance(km)", border=1, align='C', fill=True)
        pdf.cell(25, 8, "Mode", border=1, align='C', fill=True)
        pdf.cell(10, 8, "TA", border=1, align='C', fill=True)
        pdf.cell(30, 8, "Amount(Rs)", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)
        
        pdf.set_font("Helvetica", '', 7)
        if is_external:
            pdf.cell(20, 6, str(d['date']), border=1, align='C')
            pdf.cell(40, 6, str(fac['place'])[:20], border=1, align='C')
            pdf.cell(40, 6, "GCE Salem", border=1, align='C')
            pdf.cell(25, 6, str(dist), border=1, align='C')
            pdf.cell(25, 6, "Road", border=1, align='C')
            pdf.cell(10, 6, "-", border=1, align='C')
            pdf.cell(30, 6, f"{ta:.0f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        else:
            pdf.cell(20, 6, "", border=1, align='C')
            pdf.cell(40, 6, "", border=1, align='C')
            pdf.cell(40, 6, "GCE Salem", border=1, align='C')
            pdf.cell(25, 6, "", border=1, align='C')
            pdf.cell(25, 6, "", border=1, align='C')
            pdf.cell(10, 6, "0", border=1, align='C')
            pdf.cell(30, 6, "0", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            
        pdf.set_font("Helvetica", 'B', 8)
        
        pdf.cell(40, 5, "Daily Allowance (DA)", border=0, align='L')
        pdf.cell(30, 5, "Number of Day(s) :", border=0, align='R')
        pdf.cell(10, 5, "1", border=1, align='C')
        pdf.cell(110, 5, "", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        pdf.cell(40, 5, "DA for Internal Faculty :", border=1, align='L')
        pdf.cell(25, 5, f"{internal_da:.0f}" if internal_da > 0 else "", border=1, align='C')
        pdf.cell(125, 5, "", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        pdf.cell(40, 5, "DA for External Faculty:", border=1, align='L')
        pdf.cell(25, 5, f"{external_da:.0f}" if external_da > 0 else "", border=1, align='C')
        pdf.cell(20, 5, "DA (Rs)", border=1, align='R')
        pdf.cell(30, 5, f"{da:.0f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        
        pdf.ln(1)
        pdf.set_fill_color(220, 220, 220)
        pdf.cell(160, 6, "GRAND TOTAL (Rs)", border=1, align='R', fill=True)
        pdf.cell(30, 6, f"{grand:.0f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)
        
        pdf.ln(2)
        pdf.set_font("Helvetica", '', 9)
        pdf.cell(190, 5, f"Rupees {grand:.0f} ({num_to_words(grand)})", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        
        pdf.ln(4)
        y_sig = pdf.get_y()
        pdf.cell(90, 5, "Station : Salem", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(90, 5, f"Date : {datetime.now().strftime('%d/%m/%Y')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_xy(150, y_sig)
        pdf.cell(40, 5, "Signature", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
        
        pdf.ln(4)
        pdf.set_font("Helvetica", 'B', 8)
        
        pdf.cell(190, 6, "FOR OFFICE USE ONLY", border="LTR", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.set_font("Helvetica", '', 8)
        pdf.cell(190, 6, f"Passed for Rs.{grand:.0f} (Rupees {num_to_words(grand)}) through Bank Account.", border="LR", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
        pdf.cell(190, 6, "", border="LR", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(95, 6, "Checked by ACOE :", border="LB", align='L')
        pdf.cell(95, 6, "Controller of Examinations", border="RB", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')

        pdf.ln(3)
        pdf.set_font("Helvetica", 'B', 9)
        pdf.cell(190, 5, "SELF DECLARATION", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.set_font("Helvetica", '', 9)
        s_year = int(d['session_year'])
        fy = f"{s_year}-{s_year+1}"
        pdf.multi_cell(190, 5, f"I hereby declare that I will duly include the above claim in my Income Tax calculations for the Financial Year {fy}.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

        # ------------------ PAGES 2+: CHECKLISTS ------------------
        for sub in courses:
            pdf.add_page()
            if logo: pdf.image(logo, x=10, y=5, w=22)
            
            pdf.set_font("Helvetica", 'B', 10)
            pdf.cell(190, 5, "GOVERNMENT COLLEGE OF ENGINEERING, SALEM - 636 011", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            pdf.set_font("Helvetica", '', 8)
            pdf.cell(190, 4, "(NAAC Accredited with A+, An Autonomous Institution, Affiliated to Anna University, Chennai)", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            pdf.set_font("Helvetica", 'B', 9)
            pdf.cell(190, 5, "OFFICE OF THE CONTROLLER OF EXAMINATIONS", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            pdf.set_font("Times", 'B', 10)
            pdf.cell(190, 6, "CHECKLIST FOR QUESTION PAPER SCRUTINY", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            pdf.ln(3)

            pdf.set_font("Helvetica", '', 9)
            pdf.cell(45, 6, "Scrutiny Member Name:", border=0)
            pdf.cell(85, 6, str(fac['name']), border=0)
            pdf.cell(25, 6, "Designation:", border=0)
            pdf.cell(35, 6, str(fac['designation']), border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            pdf.cell(45, 6, "Institution Name:", border=0)
            pdf.cell(85, 6, str(fac['institution_address']), border=0)
            pdf.cell(25, 6, "Mobile No:", border=0)
            pdf.cell(35, 6, mob, border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            pdf.cell(45, 6, "Course Code and Name:", border=0)
            pdf.cell(95, 6, f"{sub['course_code']} - {str(sub['course_name'])}", border=0)
            pdf.cell(15, 6, "Date:", border=0)
            pdf.cell(35, 6, d['date'], border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)

            pdf.set_font("Helvetica", 'B', 9)
            pdf.set_fill_color(230, 230, 230)
            pdf.cell(10, 8, "S.No", border=1, align='C', fill=True)
            pdf.cell(130, 8, "Details", border=1, align='C', fill=True)
            pdf.cell(50, 8, "Comments", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)

            questions = [
                "Are the questions adhering to given Regulation?", 
                "Are the questions within the syllabus?", 
                "Are the questions covered in all units uniformly?",
                "Are the questions providing sufficient data for solving problems?", 
                "Whether proper mark is allotted for each question?",
                "Are the Blooms Taxonomy Level (BTL) correctly specified against each\nquestion? If No, correct the same.",
                "Are the required Tables, Charts etc., mentioned in the question paper?\nIf No, correct the same using RED ink.",
                "Are the required Figures, Units correctly presented in the question paper?\nIf No, correct the same using RED ink.",
                "Is there any repeated question in the question paper? If YES, change\nthe question using RED ink pen.",
                "Is there any ambiguity in the questions?", 
                "Does the question paper have any grammatical mistakes?",
                "Can students answer within the stipulated time?", 
                "Standard of the question paper: High (H) / Normal (N) / Sub Standard (SS)",
                "Can you recommend this question paper to the students for end\nsemester examination?"
            ]
            
            pdf.set_font("Helvetica", '', 9)
            for idx, q in enumerate(questions, 1):
                lines = q.split('\n')
                h = len(lines) * 6
                
                start_x, start_y = pdf.get_x(), pdf.get_y()
                
                if start_y + h > 270:
                    pdf.add_page()
                    start_x, start_y = pdf.get_x(), pdf.get_y()
                    
                pdf.cell(10, h, str(idx), border=1, align='C')
                
                pdf.set_xy(start_x + 10, start_y)
                pdf.multi_cell(130, 6, q, border=1, align='L', new_x=XPos.RIGHT, new_y=YPos.TOP)
                
                pdf.set_xy(start_x + 140, start_y)
                if idx == 13:
                    pdf.cell(16, h, "H", border=1, align='C')
                    pdf.cell(17, h, "N", border=1, align='C')
                    pdf.cell(17, h, "SS", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
                else:
                    pdf.cell(25, h, "Yes", border=1, align='C')
                    pdf.cell(25, h, "No", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

            start_x, start_y = pdf.get_x(), pdf.get_y()
            if start_y + 20 > 270:
                pdf.add_page()
                start_x, start_y = pdf.get_x(), pdf.get_y()
                
            pdf.cell(10, 20, "15.", border=1, align='C')
            pdf.set_xy(start_x + 10, start_y)
            pdf.multi_cell(180, 5, "Comments (Change of any Questions / Rejection of Question Paper):\n\n\n\n", border=1, align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            pdf.set_xy(10, start_y + 20) 

            pdf.ln(3)
            pdf.set_font("Helvetica", 'I', 8)
            pdf.multi_cell(0, 5, "All the above said items are verified and suitable modification/corrections were made in the given hard copy of the question paper.", align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", 'B', 8)
            pdf.multi_cell(0, 5, "Declaration: I will not discuss or disclose anything related to this audit to anyone and none of my family member(s) and relative(s) are appearing for the examination.", align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            pdf.ln(10)
            pdf.set_font("Helvetica", 'B', 9)
            pdf.cell(190, 5, "Signature of the Scrutiny Member", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
            pdf.ln(4)
            pdf.cell(190, 5, str(fac['name']), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')

        # ------------------ FINAL PAGE: SUMMARY TABLE ------------------
        pdf.add_page()
        if logo: pdf.image(logo, x=10, y=5, w=22)
        
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(190, 5, "GOVERNMENT COLLEGE OF ENGINEERING, SALEM - 636 011", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.set_font("Helvetica", '', 8)
        pdf.cell(190, 4, "(NAAC Accredited with A+, An Autonomous Institution, Affiliated to Anna University, Chennai)", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.set_font("Helvetica", 'B', 9)
        pdf.cell(190, 5, "OFFICE OF THE CONTROLLER OF EXAMINATIONS", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.cell(190, 5, f"SCRUTINY OF QUESTION PAPER(S) - {d['session_name'].upper()} {d['session_year']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.ln(5)

        def summary_row(l1, v1, l2, v2):
            pdf.set_font("Helvetica", 'B', 9)
            pdf.cell(30, 6, l1, 0, 0)
            pdf.cell(5, 6, ":", 0, 0)
            pdf.set_font("Helvetica", '', 9)
            pdf.cell(90, 6, str(v1), 0, 0)
            
            pdf.set_font("Helvetica", 'B', 9)
            pdf.cell(25, 6, l2, 0, 0)
            pdf.cell(5, 6, ":", 0, 0)
            pdf.set_font("Helvetica", '', 9)
            pdf.cell(35, 6, str(v2), 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        summary_row("Faculty ID", fac['faculty_id'], "Phase", "I / II")
        summary_row("Examiner Name", fac['name'], "Mobile No.", mob)
        summary_row("Designation", fac['designation'], "Department", fac['department'])
        summary_row("Institution", fac['institution_address'], "Board", fac['department'])

        pdf.ln(5)

        pdf.set_font("Helvetica", 'B', 9)
        pdf.cell(12, 10, "S No", border=1, align='C')
        pdf.cell(22, 10, "Date", border=1, align='C')
        pdf.cell(25, 10, "Course Code", border=1, align='C')
        pdf.cell(91, 10, "Course Name", border=1, align='C')
        pdf.cell(15, 10, "Count", border=1, align='C')
        pdf.cell(25, 10, "Cumulative", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

        pdf.set_font("Helvetica", '', 9)
        cumulative_total = 0
        max_rows = max(len(courses), 15) 
        
        for idx in range(max_rows):
            if idx < len(courses):
                c = courses[idx]
                cumulative_total += int(c['qty'])
                pdf.cell(12, 8, str(idx+1), border=1, align='C')
                pdf.cell(22, 8, str(d['date']), border=1, align='C')
                pdf.cell(25, 8, str(c['course_code']), border=1, align='C')
                pdf.cell(91, 8, f" {str(c['course_name'])[:55]}", border=1, align='L')
                pdf.cell(15, 8, str(c['qty']), border=1, align='C')
                pdf.cell(25, 8, str(cumulative_total), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            else:
                pdf.cell(12, 8, "", border=1, align='C')
                pdf.cell(22, 8, "", border=1, align='C')
                pdf.cell(25, 8, "", border=1, align='C')
                pdf.cell(91, 8, "", border=1, align='C')
                pdf.cell(15, 8, "", border=1, align='C')
                pdf.cell(25, 8, "", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

        pdf.ln(10)
        pdf.set_font("Helvetica", 'B', 9)
        pdf.cell(95, 6, "Place: Salem", border=0, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(95, 6, "Signature of the Scrutiny Member", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
        pdf.cell(95, 6, f"Date: {datetime.now().strftime('%d/%m/%Y')}", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        output = io.BytesIO(pdf.output())
        return send_file(output, mimetype='application/pdf', as_attachment=True, download_name=f"Claim_{fac['faculty_id']}.pdf")

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- CUMULATIVE & DETAILED PDF ---
@app.route('/faculty_report/<fid>/<report_type>')
def faculty_report(fid, report_type):
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db()
    c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM faculty_master WHERE faculty_id=%s", (fid,))
    fac = c.fetchone()
    
    sess, yr = session.get('active_sess'), session.get('active_year')
    
    if report_type == 'detailed':
        # Gets every single day
        c.execute("""SELECT * FROM scrutiny_records WHERE faculty_id=%s AND session_name=%s AND session_year=%s ORDER BY scrutiny_date""", (fid, sess, yr))
        recs = c.fetchall()
    else:
        # Merges everything into 1 single session row
        c.execute("""SELECT MAX(scrutiny_date) as scrutiny_date, 
                            SUM(courses_count) as courses_count, 
                            SUM(remuneration) as remuneration, 
                            SUM(ta_amount) as ta_amount, 
                            SUM(da_amount) as da_amount, 
                            SUM(grand_total) as grand_total 
                     FROM scrutiny_records 
                     WHERE faculty_id=%s AND session_name=%s AND session_year=%s""", (fid, sess, yr))
        recs = [c.fetchone()]
        if not recs[0]['courses_count']: recs = []

    db.close()
    
    if not recs: return "No records found for this session."
    
    t_rem = sum(r['remuneration'] for r in recs)
    t_ta = sum(r['ta_amount'] for r in recs)
    t_da = sum(r['da_amount'] for r in recs)
    grand = t_rem + t_ta + t_da
    
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    logo = get_logo_path()
    if logo: pdf.image(logo, x=10, y=5, w=22)
    pdf.set_left_margin(10)
    pdf.set_right_margin(10)
    
    pdf.set_font("Helvetica", 'B', 10)
    pdf.cell(190, 5, "GOVERNMENT COLLEGE OF ENGINEERING, SALEM - 636 011", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_font("Helvetica", '', 8)
    pdf.cell(190, 4, "(NAAC Accredited with A+, An Autonomous Institution)", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_font("Helvetica", 'B', 9)
    
    # Change title based on report type
    title_text = "CONSOLIDATED CLAIM FOR SCRUTINY MEMBER" if report_type == 'consolidated' else "DETAILED CLAIM FOR SCRUTINY MEMBER"
    pdf.cell(190, 5, title_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(6)
    
    pdf.set_font("Helvetica", '', 8)
    
    def row_info_rep(l1, v1, l2, v2):
        pdf.cell(40, 5, l1, border=0)
        pdf.cell(70, 5, str(v1), border=0)
        pdf.cell(5, 5, "", border=0)
        pdf.cell(30, 5, l2, border=0)
        pdf.cell(45, 5, str(v2), border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    acc = format_val(fac['account_number'])
    clean_bank_type = clean_btype(fac['bank_type'])
    
    row_info_rep("FACULTY ID :", fid, "Category :", fac['category'])
    row_info_rep("NAME :", fac['name'], "BANK NAME :", fac['bank_name'])
    row_info_rep("DESIGNATION :", fac['designation'], "ACCOUNT NUMBER :", acc)
    row_info_rep("DEPARTMENT :", fac['department'], "BANK TYPE :", clean_bank_type)
    pdf.ln(5)
    
    pdf.set_font("Helvetica", 'B', 8)
    
    # Change subtitle based on report type
    subtitle_text = "Duty Details (Consolidated Total):" if report_type == 'consolidated' else "Duty Details (Day-by-Day Breakdown):"
    pdf.cell(190, 5, subtitle_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(15, 8, "S.No", border=1, align='C', fill=True)
    pdf.cell(30, 8, "Date(s)", border=1, align='C', fill=True)
    pdf.cell(25, 8, "QP Count", border=1, align='C', fill=True)
    pdf.cell(30, 8, "Remun.", border=1, align='C', fill=True)
    pdf.cell(30, 8, "TA", border=1, align='C', fill=True)
    pdf.cell(30, 8, "DA", border=1, align='C', fill=True)
    pdf.cell(30, 8, "Total", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)
    
    pdf.set_font("Helvetica", '', 8)
    for i, r in enumerate(recs, 1):
        date_str = str(r['scrutiny_date']) if report_type == 'detailed' else "Session Total"
        pdf.cell(15, 7, str(i), border=1, align='C')
        pdf.cell(30, 7, date_str, border=1, align='C')
        pdf.cell(25, 7, str(r['courses_count']), border=1, align='C')
        pdf.cell(30, 7, f"{r['remuneration']:.2f}", border=1, align='R')
        pdf.cell(30, 7, f"{r['ta_amount']:.2f}", border=1, align='R')
        pdf.cell(30, 7, f"{r['da_amount']:.2f}", border=1, align='R')
        pdf.cell(30, 7, f"{r['grand_total']:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
        
    pdf.set_font("Helvetica", 'B', 8)
    pdf.cell(70, 8, "GRAND TOTAL", border=1, align='R')
    pdf.cell(30, 8, f"{t_rem:.2f}", border=1, align='R')
    pdf.cell(30, 8, f"{t_ta:.2f}", border=1, align='R')
    pdf.cell(30, 8, f"{t_da:.2f}", border=1, align='R')
    pdf.cell(30, 8, f"{grand:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R', fill=True)
    
    pdf.ln(5)
    pdf.set_font("Helvetica", '', 9)
    pdf.cell(0, 5, f"Passed for Rupees {grand:.0f} ({num_to_words(grand)})", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    
    pdf.ln(8)
    y_sig = pdf.get_y()
    pdf.cell(90, 5, "Station : Salem", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(90, 5, f"Date : {datetime.now().strftime('%d/%m/%Y')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_xy(150, y_sig + 5)
    pdf.cell(40, 5, "Signature", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')

    pdf.ln(8)
    pdf.set_font("Helvetica", 'B', 8)
    pdf.cell(190, 6, "FOR OFFICE USE ONLY", border="LTR", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_font("Helvetica", '', 8)
    pdf.cell(190, 6, f"Passed for Rs.{grand:.0f} (Rupees {num_to_words(grand)}) through Bank Account.", border="LR", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    pdf.cell(190, 6, "", border="LR", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(95, 6, "Checked by ACOE :", border="LB", align='L')
    pdf.cell(95, 6, "Controller of Examinations", border="RB", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')

    pdf.ln(6)
    pdf.set_font("Helvetica", 'B', 9)
    pdf.cell(0, 5, "SELF DECLARATION", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_font("Helvetica", '', 9)
    s_year = int(yr)
    fy = f"{s_year}-{s_year+1}"
    
    pdf.multi_cell(0, 5, f"I hereby declare that I will duly include the above claim in my Income Tax calculations for the Financial Year {fy}.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    
    output = io.BytesIO(pdf.output())
    filename_type = "Consolidated" if report_type == 'consolidated' else "Detailed"
    return send_file(output, mimetype='application/pdf', as_attachment=True, download_name=f"{filename_type}_{fid}.pdf")

if __name__ == '__main__':
    print("--- 7. Starting Flask Web Server on Port 5000... ---")
    print(">>> GO TO YOUR BROWSER NOW: http://127.0.0.1:5000 <<<")
    app.run(host='0.0.0.0', port=5000, debug=True)