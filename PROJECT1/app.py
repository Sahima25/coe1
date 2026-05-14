import io
import os
import re
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
import pandas as pd
import mysql.connector
import json
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'gce_salem_ultimate_master_2026'

# ==========================================
# 1. DATABASE & AUTO-FIX
# ==========================================
def get_db(with_db=True):
    # Add all possible passwords here (Your PC's and Admin PC's)
    passwords = ["gcecoe@#23", "Sahi@123", "root", ""] 
    
    for pwd in passwords:
        try:
            config = {
                "host": "localhost", 
                "user": "root", 
                "password": pwd, 
                "auth_plugin": 'mysql_native_password'
            }
            if with_db: 
                config["database"] = "scrutiny_db"
            
            conn = mysql.connector.connect(**config)
            if conn.is_connected(): 
                return conn
        except:
            continue # Try the next password in the list
    return None

def init_db():
    try:
        conn = get_db(with_db=False)
        if not conn: return
        cursor = conn.cursor()
        cursor.execute("CREATE DATABASE IF NOT EXISTS scrutiny_db")
        cursor.close()
        conn.close()
        
        db = get_db()
        c = db.cursor()
        
        c.execute("CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(50) UNIQUE, password VARCHAR(100), role VARCHAR(20))")
        c.execute("INSERT IGNORE INTO users (username, password, role) VALUES ('admin', 'coe123', 'admin')")
        
        c.execute("""CREATE TABLE IF NOT EXISTS faculty_master (
            faculty_id VARCHAR(50) PRIMARY KEY, name VARCHAR(150), designation VARCHAR(150), 
            department VARCHAR(150), institution_address TEXT, mobile_number VARCHAR(50), 
            email_address VARCHAR(150), bank_name VARCHAR(150), account_number VARCHAR(50), 
            ifsc VARCHAR(50), branch_name VARCHAR(150), place VARCHAR(150), 
            distance FLOAT DEFAULT 0, category VARCHAR(50), bank_type VARCHAR(50) DEFAULT 'Nationalized')""")
            
        c.execute("CREATE TABLE IF NOT EXISTS course_master (course_code VARCHAR(50) PRIMARY KEY, course_name VARCHAR(200), department VARCHAR(100), regulation VARCHAR(20), semester INT)")
        c.execute("CREATE TABLE IF NOT EXISTS calendar_master (date DATE PRIMARY KEY, day_type VARCHAR(50) DEFAULT 'Working')")
        
        c.execute("""CREATE TABLE IF NOT EXISTS scrutiny_records (
            id INT AUTO_INCREMENT PRIMARY KEY, faculty_id VARCHAR(50), scrutiny_date DATE, 
            courses_json TEXT, courses_count INT, remuneration FLOAT, ta_amount FLOAT, 
            da_amount FLOAT, grand_total FLOAT, session_name VARCHAR(50), 
            session_year VARCHAR(20), regulation VARCHAR(20) DEFAULT '2022', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
            
        c.execute("""CREATE TABLE IF NOT EXISTS val_sessions (
            id INT AUTO_INCREMENT PRIMARY KEY, type VARCHAR(20), academic_year VARCHAR(20), 
            sem_type VARCHAR(20), num_phases INT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS val_phases (
            id INT AUTO_INCREMENT PRIMARY KEY, session_id INT, phase_number INT, start_date DATE, end_date DATE)""")
            
        c.execute("""CREATE TABLE IF NOT EXISTS val_subjects (
            id INT AUTO_INCREMENT PRIMARY KEY, phase_id INT, exam_date VARCHAR(50), session_fn_an VARCHAR(20), 
            department VARCHAR(50), course_code VARCHAR(50), course_name VARCHAR(255), 
            valuation_strength VARCHAR(50), dummy_number_start VARCHAR(100))""")
            
        c.execute("""CREATE TABLE IF NOT EXISTS val_examiners (
            id INT AUTO_INCREMENT PRIMARY KEY, phase_id INT, s_no VARCHAR(20), staff_name VARCHAR(150), 
            college_address TEXT, mobile VARCHAR(50), email VARCHAR(100), allocations_json TEXT)""")
            
        c.execute("""CREATE TABLE IF NOT EXISTS prac_schedules (
            id INT AUTO_INCREMENT PRIMARY KEY, order_no VARCHAR(50), exam_date VARCHAR(100), 
            degree VARCHAR(50), programme VARCHAR(100), semester VARCHAR(20), 
            course_code VARCHAR(50), course_title VARCHAR(255), duration VARCHAR(20), 
            board VARCHAR(100), total_candidates LONGTEXT, internal_examiner LONGTEXT, 
            external_examiner LONGTEXT, skilled_assistant VARCHAR(150), session_name VARCHAR(50), session_year VARCHAR(20))""")
            
        try:
            c.execute("ALTER TABLE prac_schedules MODIFY total_candidates LONGTEXT")
            c.execute("ALTER TABLE prac_schedules MODIFY internal_examiner LONGTEXT")
            c.execute("ALTER TABLE prac_schedules MODIFY external_examiner LONGTEXT")
            c.execute("SHOW COLUMNS FROM prac_schedules LIKE 'skilled_assistant'")
            if not c.fetchone(): c.execute("ALTER TABLE prac_schedules ADD COLUMN skilled_assistant VARCHAR(150) AFTER external_examiner")
        except:
            pass
            
        db.commit()
        db.close()
    except Exception as e: 
        print(f"DB Init Error: {e}")

init_db()

# ==========================================
# 2. UTILS & PDF ENGINE
# ==========================================
def clean_str(val): 
    if isinstance(val, pd.Series): val = val.dropna().iloc[0] if not val.dropna().empty else ""
    if pd.isna(val) or str(val).lower() in ['nan','none','null','']: return ''
    return str(val).strip()

def clean_name(n):
    if isinstance(n, pd.Series): n = n.dropna().iloc[0] if not n.dropna().empty else ""
    if pd.isna(n): return ""
    n_str = str(n).strip()
    if n_str.lower() in ['none', 'nan', 'null', '']: return ""
    return n_str

def safe_float(val): 
    if isinstance(val, pd.Series): val = val.dropna().iloc[0] if not val.dropna().empty else 0.0
    if pd.isna(val) or str(val).strip() == '' or str(val).lower() in ['nan', 'none']: return 0.0
    try:
        cleaned = re.sub(r'[^\d.]', '', str(val))
        return float(cleaned) if cleaned else 0.0
    except: return 0.0

def format_val(val):
    if pd.isna(val) or str(val).strip() == '' or str(val).lower() == 'nan': return ''
    try: 
        if float(val).is_integer(): return str(int(float(val)))
        return str(val)
    except: return str(val)

def normalize_columns(df):
    cleaned_cols = []
    for c in df.columns:
        c_str = str(c).lower().replace('\n', ' ').replace('\r', '').strip()
        c_str = ' '.join(c_str.split()) 
        if 'skilled' in c_str and 'assistant' in c_str: c_str = 'skilled_assistant'
        elif 'course' in c_str and 'code' in c_str: c_str = 'course_code'
        elif 'course' in c_str and ('name' in c_str or 'title' in c_str): c_str = 'course_title'
        elif 'internal' in c_str: c_str = 'internal_examiner'
        elif 'external' in c_str: c_str = 'external_examiner'
        elif c_str.startswith('s.no') or c_str.startswith('s no') or c_str.startswith('sl') or 'order' in c_str: c_str = 'order_no'
        elif 'candidat' in c_str or 'canditat' in c_str or 'strength' in c_str or 'total' in c_str: c_str = 'total_candidates'
        elif 'date' in c_str: c_str = 'exam_date'
        elif 'session' in c_str: c_str = 'session'
        elif 'degree' in c_str: c_str = 'degree'
        elif 'branch name' in c_str or 'bank branch' in c_str: c_str = 'branch_name'
        elif 'programm' in c_str or 'branch' in c_str: c_str = 'programme'
        elif 'sem' in c_str: c_str = 'semester'
        elif 'duration' in c_str: c_str = 'duration'
        elif 'board' in c_str or 'organising' in c_str or 'department' in c_str: c_str = 'board'
        elif 'examiner' in c_str and 'name' in c_str: c_str = 'examiner_name'
        else: c_str = c_str.replace(' ', '_')
        cleaned_cols.append(c_str)
    df.columns = cleaned_cols
    return df

def num_to_words(num):
    try:
        num = int(float(num))
        if num == 0: return "Zero"
        units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
        teens = ["Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
        def chunk(n):
            if n < 10: return units[n]
            elif n < 20: return teens[n-10]
            elif n < 100: return tens[n // 10] + (" " + units[n % 10] if n % 10 != 0 else "")
            return units[n // 100] + " Hundred" + (" and " + chunk(n % 100) if n % 100 != 0 else "")
        words = ""
        if num >= 10000000: words += chunk(num // 10000000) + " Crore "; num %= 10000000
        if num >= 100000: words += chunk(num // 100000) + " Lakh "; num %= 100000
        if num >= 1000: words += chunk(num // 1000) + " Thousand "; num %= 1000
        if num > 0: words += chunk(num)
        return words.strip() + " only"
    except: return "Zero only"

def get_logo_path():
    for n in ['logo.jpg', 'logo.png', 'logo.jpeg']: 
        if os.path.exists(n): return n
    return None

class CustomPDF(FPDF):
    def header(self):
        logo = get_logo_path()
        if logo:
            try:
                self.image(logo, x=15, y=8, w=22)
            except:
                pass
        self.set_y(10)
        self.set_font("Helvetica", 'B', 12)
        self.cell(0, 6, "GOVERNMENT COLLEGE OF ENGINEERING, SALEM - 636 011", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Helvetica", '', 9)
        self.cell(0, 5, "(NAAC Accredited with A+, An Autonomous Institution, Affiliated to Anna University, Chennai)", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Helvetica", 'B', 10)
        self.cell(0, 6, "OFFICE OF THE CONTROLLER OF EXAMINATIONS", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)


# ==========================================
# 3. AUTH & DASHBOARD ROUTES
# ==========================================
@app.route('/')
def index(): return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM users WHERE username=%s AND password=%s", (request.form['username'], request.form['password']))
    user = c.fetchone(); db.close()
    if user: 
        session['user'] = user['username']
        return redirect(url_for('dashboard'))
    return render_template('index.html', error="Invalid Login")

@app.route('/dashboard')
def dashboard(): 
    if 'user' not in session: return redirect(url_for('index'))
    return render_template('dashboard.html', totals={'remun':0, 'ta':0, 'da':0, 'grand':0, 'total_claims':0})

@app.route('/logout')
def logout(): 
    session.clear(); return redirect(url_for('index'))

@app.route('/api/get_faculty_exact')
def get_faculty_exact():
    name = request.args.get('name', '')
    if not name: return jsonify({"found": False})
    db = get_db(); c = db.cursor(dictionary=True)
    
    c.execute("SELECT designation, institution_address, distance FROM faculty_master WHERE name = %s LIMIT 1", (name,))
    fac = c.fetchone()
    
    if not fac:
        clean_n = name.replace(' ', '').replace('.', '').lower()
        c.execute("SELECT designation, institution_address, distance FROM faculty_master WHERE LOWER(REPLACE(REPLACE(name, ' ', ''), '.', '')) = %s LIMIT 1", (clean_n,))
        fac = c.fetchone()
        
    if not fac:
        c.execute("SELECT designation, institution_address, distance FROM faculty_master WHERE name LIKE %s LIMIT 1", (f"%{name}%",))
        fac = c.fetchone()
        
    db.close()
    if fac: return jsonify({"found": True, "designation": fac['designation'], "institution": fac['institution_address'], "distance": fac['distance']})
    return jsonify({"found": False})

# Route to show the Edit Form
@app.route('/edit_faculty/<fid>')
def edit_faculty(fid):
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db()
    c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM faculty_master WHERE faculty_id = %s", (fid,))
    fac = c.fetchone()
    db.close()
    if not fac:
        flash("Faculty not found!", "danger")
        return redirect(url_for('manage_faculty'))
    return render_template('edit_faculty.html', f=fac)

# Route to process the Update
@app.route('/update_faculty', methods=['POST'])
def update_faculty():
    if 'user' not in session: return redirect(url_for('index'))
    f = request.form
    try:
        db = get_db()
        c = db.cursor()
        sql = """REPLACE INTO faculty_master 
                 (faculty_id, name, designation, department, institution_address, 
                  mobile_number, email_address, bank_name, account_number, ifsc, 
                  branch_name, place, distance, category, bank_type) 
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        val = (f['faculty_id'], f['name'], f['designation'], f['department'], 
               f['institution_address'], f['mobile_number'], f['email_address'], 
               f['bank_name'], f['account_number'], f['ifsc'], f['branch_name'], 
               f['place'], safe_float(f['distance']), f['category'], f['bank_type'])
        c.execute(sql, val)
        db.commit()
        db.close()
        flash(f"Details for {f['name']} updated successfully!", "success")
    except Exception as e:
        flash(f"Error updating faculty: {str(e)}", "danger")
    return redirect(url_for('manage_faculty'))
# ==========================================
# 4. SCRUTINY MODULE
# ==========================================
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
        session['active_reg'] = request.form.get('regulation', '2022')
    return render_template('session_hub.html', sess=session.get('active_sess'), yr=session.get('active_year'))

@app.route('/scrutiny')
def scrutiny(): 
    if 'user' not in session: return redirect(url_for('index'))
    return render_template('scrutiny.html', sess=session.get('active_sess'), yr=session.get('active_year'))

@app.route('/process', methods=['POST'])
def process():
    d = request.json
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM faculty_master WHERE faculty_id=%s", (d['faculty_id'],))
    fac = c.fetchone()
    courses = []
    tot_qps = 0
    for i in d.get('courses', []):
        if not i.get('code'): continue
        qty = int(float(i.get('count', 1)))
        c.execute("SELECT * FROM course_master WHERE course_code=%s", (i['code'],))
        cm = c.fetchone()
        courses.append({'code': i['code'], 'name': cm['course_name'] if cm else 'Manual Entry', 'qty': qty, 'amount': qty * 150})
        tot_qps += qty
    c.execute("SELECT day_type FROM calendar_master WHERE date=%s", (d['date'],))
    cal = c.fetchone()
    is_hol = (cal['day_type'] == 'Holiday') if cal else (datetime.strptime(d['date'], '%Y-%m-%d').weekday() == 6)
    remun = tot_qps * 150
    dist = int(float(fac.get('distance') or 0.0))
    is_external = (fac.get('category') == 'External')
    ta, da, internal_da, external_da = 0, 0, 0, 0
    if is_external:
        if dist < 35: external_da = 200; ta = 400
        else: external_da = 300; ta = dist * 12
    else:
        if is_hol: internal_da = 150
    da = internal_da + external_da
    grand = remun + ta + da
    reg = session.get('active_reg', '2022')
    c.execute("""INSERT INTO scrutiny_records (faculty_id, scrutiny_date, courses_json, courses_count, remuneration, ta_amount, da_amount, grand_total, session_name, session_year, regulation) 
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", 
              (fac['faculty_id'], d['date'], json.dumps(courses), tot_qps, remun, ta, da, grand, d['session_name'], d['session_year'], reg))
    db.commit(); db.close()
    return jsonify({"success": True, "faculty_id": fac['faculty_id']})
@app.route('/api/toggle_calendar_date', methods=['POST'])
def toggle_calendar_date():
    if 'user' not in session: 
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    data = request.json
    date_val = data.get('date')
    
    try:
        # Determine if the clicked day is a Sunday
        dt_obj = datetime.strptime(date_val, '%Y-%m-%d')
        is_sunday = (dt_obj.weekday() == 6)
        
        db = get_db()
        c = db.cursor(dictionary=True)
        
        # Check if an override already exists in the database
        c.execute("SELECT * FROM calendar_master WHERE date=%s", (date_val,))
        existing = c.fetchone()
        
        if existing:
            # If it exists, we DELETE it to revert to the "Default" behavior
            c.execute("DELETE FROM calendar_master WHERE date=%s", (date_val,))
            new_status = 'Default'
        else:
            # If it doesn't exist, we create an override
            # Rule: If it's Sunday, override to Working. If it's Weekday, override to Holiday.
            new_type = 'Working' if is_sunday else 'Holiday'
            c.execute("INSERT INTO calendar_master (date, day_type) VALUES (%s, %s)", (date_val, new_type))
            new_status = new_type
            
        db.commit()
        db.close()
        
        # This matches the 'data.success' and 'data.new_status' in your JS
        return jsonify({"success": True, "new_status": new_status, "date": date_val})
        
    except Exception as e:
        print(f"Calendar Toggle Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
@app.route('/faculty_report/<fid>/claim')
def faculty_pdf(fid):
    db = get_db()
    c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM faculty_master WHERE faculty_id=%s", (fid,))
    fac = c.fetchone()
    c.execute("SELECT * FROM scrutiny_records WHERE faculty_id=%s ORDER BY id DESC LIMIT 1", (fid,))
    r = c.fetchone()
    db.close()
    
    if not r or not fac: return "Error: Data missing."

    for key in fac: 
        if fac[key] is None: fac[key] = ""
    for key in r: 
        if r[key] is None: r[key] = ""

    courses = json.loads(r['courses_json'])
    
    pdf = CustomPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    
    mob = format_val(fac['mobile_number'])
    acc = format_val(fac['account_number'])
    clean_bank_type = str(fac['bank_type']).replace('(MRFT)', '').replace('(ECS)', '').strip()
    
    is_ext = (fac['category'] == 'External')
    dist = int(float(fac['distance'])) if fac['distance'] else 0
    ta_amt = int(float(r['ta_amount']))
    da_amt = int(float(r['da_amount']))
    remun_amt = int(float(r['remuneration']))
    grand_amt = int(float(r['grand_total']))

    pdf.add_page()
    
    pdf.set_font("Helvetica", 'B', 9)
    pdf.cell(0, 5, f"B.E. / M.E. DEGREE EXAMINATIONS - {str(r['session_name']).upper()} {r['session_year']} SESSION", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.cell(0, 5, "CLAIM FOR SCRUTINY MEMBER", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    fields_left = [
        ("MONTH and YEAR :", f"{r['session_name']} {r['session_year']}"),
        ("FACULTY ID :", fac['faculty_id']),
        ("SCRUTINY MEMBER:", fac['name']),
        ("DESIGNATION :", fac['designation']),
        ("INSTITUTION ADDRESS:", str(fac['institution_address'])),
        ("MOBILE NUMBER :", mob),
        ("E-MAIL ADDRESS :", fac['email_address'])
    ]
    fields_right = [
        ("Phase :", "I / II"),
        ("Board :", fac['department']),
        ("BANK NAME :", fac['bank_name']),
        ("ACCOUNT NUMBER :", acc),
        ("IFSC :", fac['ifsc']),
        ("BRANCH NAME :", fac['branch_name']),
        ("BANK TYPE :", clean_bank_type)
    ]
    
    for left, right in zip(fields_left, fields_right):
        pdf.set_font("Helvetica", '', 8)
        pdf.cell(40, 5, left[0])
        if left[0] == "INSTITUTION ADDRESS:":
            pdf.set_font("Helvetica", '', 6.5)
            pdf.cell(65, 5, str(left[1])[:80])
        else:
            pdf.cell(65, 5, str(left[1])[:40])
            
        pdf.set_font("Helvetica", '', 8)
        pdf.cell(30, 5, right[0])
        pdf.cell(55, 5, str(right[1]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(2)
    pdf.set_font("Helvetica", 'B', 8)
    pdf.cell(0, 5, "Remuneration Details :", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    w = [7, 10, 18, 40, 9, 11]
    headers = ["S.No", "Degree", "Course Code", "Course Name", "QPs", "Amt(Rs)"] * 2
    for i, h in enumerate(headers): 
        pdf.cell(w[i%6], 5, h, 1, 0, 'C')
    pdf.ln()

    pdf.set_font("Helvetica", '', 7)
    for i in range(5):
        if i < len(courses):
            c1 = courses[i]
            pdf.cell(w[0], 5, str(i+1), 1, 0, 'C')
            pdf.cell(w[1], 5, "B.E", 1, 0, 'C')
            pdf.cell(w[2], 5, str(c1.get('code','')), 1, 0, 'C')
            pdf.cell(w[3], 5, f" {str(c1.get('name',''))[:25]}", 1, 0, 'L')
            pdf.cell(w[4], 5, str(int(float(c1.get('qty',0)))), 1, 0, 'C')
            pdf.cell(w[5], 5, str(int(float(c1.get('amount',0)))), 1, 0, 'C')
        else:
            for cw in w: pdf.cell(cw, 5, "", 1, 0, 'C')
                
        if i+5 < len(courses):
            c2 = courses[i+5]
            pdf.cell(w[0], 5, str(i+6), 1, 0, 'C')
            pdf.cell(w[1], 5, "B.E", 1, 0, 'C')
            pdf.cell(w[2], 5, str(c2.get('code','')), 1, 0, 'C')
            pdf.cell(w[3], 5, f" {str(c2.get('name',''))[:25]}", 1, 0, 'L')
            pdf.cell(w[4], 5, str(int(float(c2.get('qty',0)))), 1, 0, 'C')
            pdf.cell(w[5], 5, str(int(float(c2.get('amount',0)))), 1, 0, 'C')
        else:
            for cw in w: pdf.cell(cw, 5, "", 1, 0, 'C')
        pdf.ln()
    
    pdf.set_font("Helvetica", 'B', 7)
    pdf.cell(sum(w[:4]), 5, "Total Number of Question Paper(s) Scrutinised:", 1, 0, 'R')
    pdf.cell(w[4], 5, str(int(float(r['courses_count']))), 1, 0, 'C')
    pdf.cell(w[5] + sum(w[:4]), 5, "Total Claim (Rs) for Scrutinised Question Paper(s):", 1, 0, 'R')
    pdf.cell(w[4]+w[5], 5, str(remun_amt), 1, 0, 'C')
    pdf.ln(7)

    pdf.set_font("Helvetica", 'B', 8)
    pdf.cell(0, 5, "Travelling Allowance (TA)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    w_ta = [20, 40, 40, 25, 20, 20, 25]
    h_ta = ["Date", "From", "To", "Distance(km)", "Mode", "TA", "Amount(Rs)"]
    pdf.set_fill_color(240, 240, 240)
    for i, h in enumerate(h_ta): 
        pdf.cell(w_ta[i], 6, h, 1, 0, 'C', True)
    pdf.ln()
    
    pdf.set_font("Helvetica", '', 8)
    if is_ext:
        pdf.cell(w_ta[0], 5, str(r['scrutiny_date']), 1, 0, 'C')
        pdf.cell(w_ta[1], 5, str(fac['place'])[:20], 1, 0, 'C')
        pdf.cell(w_ta[2], 5, "GCE Salem", 1, 0, 'C')
        pdf.cell(w_ta[3], 5, str(dist), 1, 0, 'C')
        pdf.cell(w_ta[4], 5, "Road", 1, 0, 'C')
        pdf.cell(w_ta[5], 5, "-", 1, 0, 'C')
        pdf.cell(w_ta[6], 5, str(ta_amt), 1, 0, 'C')
    else:
        for i in range(7): 
            if i == 2: pdf.cell(w_ta[i], 5, "GCE Salem", 1, 0, 'C')
            elif i in [5, 6]: pdf.cell(w_ta[i], 5, "0", 1, 0, 'C')
            else: pdf.cell(w_ta[i], 5, "", 1, 0, 'C')
    pdf.ln(6)

    internal_da = da_amt if not is_ext else 0
    external_da = da_amt if is_ext else 0

    pdf.set_font("Helvetica", 'B', 8)
    pdf.cell(40, 5, "Daily Allowance (DA)", border=0, align='L')
    pdf.cell(40, 5, "Number of Day(s) :", border=0, align='R')
    pdf.cell(15, 5, "1", border=1, align='C')
    pdf.ln()
    
    pdf.cell(40, 5, "DA for Internal Faculty :", border=1, align='L')
    pdf.cell(25, 5, str(internal_da) if internal_da > 0 else "", border=1, align='C')
    pdf.ln()
    
    pdf.cell(40, 5, "DA for External Faculty:", border=1, align='L')
    pdf.cell(25, 5, str(external_da) if external_da > 0 else "", border=1, align='C')
    pdf.cell(40, 5, "", border=0) 
    pdf.cell(25, 5, "DA (Rs)", border=1, align='R')
    pdf.cell(30, 5, str(da_amt), border=1, align='C')
    pdf.ln(6)

    pdf.set_fill_color(220, 220, 220)
    pdf.cell(160, 6, "GRAND TOTAL (Rs)", border=1, align='R', fill=True)
    pdf.cell(30, 6, str(grand_amt), border=1, align='C', fill=True)
    pdf.ln(8)
    
    pdf.set_font("Helvetica", '', 9)
    pdf.cell(0, 5, f"Rupees {grand_amt} ({num_to_words(grand_amt)})", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(5)
    y_sig = pdf.get_y()
    pdf.cell(90, 5, "Station : Salem", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(90, 5, f"Date : {datetime.now().strftime('%d/%m/%Y')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_xy(150, y_sig)
    pdf.cell(40, 5, "Signature", border=0, align='R')
    
    pdf.set_y(y_sig + 15) 

    pdf.set_font("Helvetica", 'B', 8)
    pdf.cell(0, 6, "FOR OFFICE USE ONLY", border="LTR", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", '', 8)
    pdf.cell(0, 6, f"Passed for Rs.{grand_amt} (Rupees {num_to_words(grand_amt)}) through Bank Account.", border="LR", align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(95, 6, "Checked by ACOE :", border="LB", align='L')
    pdf.cell(95, 6, "Controller of Examinations", border="RB", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.ln(4)
    pdf.set_font("Helvetica", 'B', 9)
    pdf.cell(0, 5, "SELF DECLARATION", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", '', 8)
    sy = int(r['session_year'] or 2025)
    pdf.multi_cell(0, 4, f"I hereby declare that I will duly include the above claim in my Income Tax calculations for the Financial Year {sy}-{sy+1}.", align='C')

    questions = [
        ("Are the questions adhering to given Regulation?", 8), 
        ("Are the questions within the syllabus?", 8),
        ("Are the questions covered in all units uniformly?", 8), 
        ("Are the questions providing sufficient data for solving problems?", 8),
        ("Whether proper mark is allotted for each question?", 8), 
        ("Are the Blooms Taxonomy Level (BTL) correctly specified against each\nquestion? If No, correct the same.", 12),
        ("Are the required Tables, Charts etc., mentioned in the question paper?\nIf No, correct the same using RED ink.", 12), 
        ("Are the required Figures, Units correctly presented in the question paper?\nIf No, correct the same using RED ink.", 12),
        ("Is there any repeated question in the question paper? If YES, change\nthe question using RED ink pen.", 12), 
        ("Is there any ambiguity in the questions?", 8),
        ("Does the question paper have any grammatical mistakes?", 8), 
        ("Can students answer within the stipulated time?", 8),
        ("Standard of the question paper: High (H) / Normal (N) / Sub Standard (SS)", 8), 
        ("Can you recommend this question paper to the students for end\nsemester examination?", 12)
    ]
    
    # Page 2
    pdf.add_page()
    pdf.set_font("Times", 'B', 10)
    pdf.cell(0, 6, "CHECKLIST FOR QUESTION PAPER SCRUTINY", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    pdf.set_font("Helvetica", '', 9)
    pdf.cell(35, 6, "Scrutiny Member:")
    pdf.cell(100, 6, str(fac['name']))
    pdf.cell(25, 6, "Designation:")
    pdf.cell(30, 6, str(fac['designation']), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.cell(35, 6, "Institution Name:")
    pdf.cell(100, 6, str(fac['institution_address'])[:55])
    pdf.cell(25, 6, "Mobile No:")
    pdf.cell(30, 6, mob, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    sx, sy = pdf.get_x(), pdf.get_y()
    pdf.cell(35, 6, "Course Code(s):")
    
    pdf.set_xy(sx + 135, sy)
    pdf.cell(25, 6, "Date:")
    pdf.cell(30, 6, str(r['scrutiny_date']))
    
    pdf.set_xy(sx + 35, sy + 1)
    c_full = ", ".join([str(c.get('code','')) for c in courses])
    pdf.multi_cell(95, 4, c_full[:150], border=0, align='L')
    
    pdf.set_y(max(pdf.get_y(), sy + 6) + 2)

    pdf.set_font("Helvetica", 'B', 9)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(10, 6, "S.No", border=1, align='C', fill=True)
    pdf.cell(130, 6, "Details", border=1, align='C', fill=True)
    pdf.cell(50, 6, "Comments", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)
    
    pdf.set_font("Helvetica", '', 9)
    for idx, (q, h) in enumerate(questions, 1):
        sx, sy = pdf.get_x(), pdf.get_y()
        pdf.cell(10, h, str(idx), border=1, align='C')
        pdf.cell(130, h, "", border=1, align='C') 
        pdf.set_xy(sx + 10, sy + (1 if h == 12 else 1)) 
        pdf.multi_cell(130, 5, q, border=0, align='L')
        pdf.set_xy(sx + 140, sy)
        if idx == 13: 
            pdf.cell(16.6, h, "H", border=1, align='C')
            pdf.cell(16.7, h, "N", border=1, align='C')
            pdf.cell(16.7, h, "SS", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        else: 
            pdf.cell(25, h, "Yes", border=1, align='C')
            pdf.cell(25, h, "No", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

    sx, sy = pdf.get_x(), pdf.get_y()
    h_15 = 16
    if sy + h_15 > 270:
        pdf.add_page()
        sx, sy = pdf.get_x(), pdf.get_y()
    pdf.cell(10, h_15, "15.", border=1, align='C')
    pdf.cell(180, h_15, "", border=1, align='C')
    pdf.set_xy(sx + 10, sy + 2)
    pdf.multi_cell(180, 5, "Comments (Change of any Questions / Rejection of Question Paper):", border=0, align='L')
    pdf.set_y(sy + h_15)
    pdf.ln(3)

    pdf.set_font("Helvetica", 'I', 8)
    pdf.multi_cell(0, 4, "All the above said items are verified and suitable modification/corrections were made in the given hard copy of the question paper.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", 'B', 8)
    pdf.multi_cell(0, 4, "Declaration: I will not discuss or disclose anything related to this audit to anyone and none of my family member(s) and relative(s) are appearing for the examination.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(8)
    pdf.set_font("Helvetica", 'B', 9)
    pdf.cell(0, 5, "Signature of the Scrutiny Member", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.cell(0, 5, str(fac['name']), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Page 3
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 9)
    pdf.cell(0, 5, f"SCRUTINY OF QUESTION PAPER(S) - {str(r['session_name']).upper()} {r['session_year']}", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)

    def sum_row(l1, v1, l2, v2):
        pdf.set_font("Helvetica", 'B', 9)
        pdf.cell(30, 6, l1, border=0)
        pdf.cell(5, 6, ":", border=0)
        pdf.set_font("Helvetica", '', 9)
        pdf.cell(90, 6, str(v1), border=0)
        pdf.set_font("Helvetica", 'B', 9)
        pdf.cell(25, 6, l2, border=0)
        pdf.cell(5, 6, ":", border=0)
        pdf.set_font("Helvetica", '', 9)
        pdf.cell(35, 6, str(v2), border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    sum_row("Faculty ID", fac['faculty_id'], "Phase", "I / II")
    sum_row("Examiner Name", fac['name'], "Mobile No.", mob)
    sum_row("Designation", fac['designation'], "Department", fac['department'])
    sum_row("Institution", str(fac['institution_address'])[:45], "Board", fac['department'])
    pdf.ln(5)

    pdf.set_font("Helvetica", 'B', 9)
    pdf.cell(10, 8, "S No", border=1, align='C')
    pdf.cell(25, 8, "Date", border=1, align='C')
    pdf.cell(25, 8, "Course Code", border=1, align='C')
    pdf.cell(90, 8, "Course Name", border=1, align='C')
    pdf.cell(15, 8, "Count", border=1, align='C')
    pdf.cell(25, 8, "Cumulative", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

    pdf.set_font("Helvetica", '', 8)
    cumul = 0
    max_rows = max(len(courses), 15)
    for idx in range(max_rows):
        if idx < len(courses):
            c_item = courses[idx]
            qty_int = int(float(c_item.get('qty', 0)))
            cumul += qty_int
            name_str = str(c_item.get('name', ''))
            lines = 1 if len(name_str) <= 50 else 2
            h = 6 if lines == 1 else 10
            sx, sy = pdf.get_x(), pdf.get_y()
            pdf.cell(10, h, str(idx+1), border=1, align='C')
            pdf.cell(25, h, str(r['scrutiny_date']), border=1, align='C')
            pdf.cell(25, h, str(c_item.get('code', '')), border=1, align='C')
            pdf.cell(90, h, "", border=1, align='L') 
            cx, cy = pdf.get_x(), pdf.get_y()
            pdf.set_xy(sx + 60, sy + (1 if lines == 2 else 0))
            pdf.multi_cell(90, 4 if lines == 2 else 6, f" {name_str}", border=0, align='L')
            pdf.set_xy(cx, sy) 
            pdf.cell(15, h, str(qty_int), border=1, align='C')
            pdf.cell(25, h, str(cumul), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        else:
            if pdf.get_y() + 6 > 270:
                pdf.add_page()
            pdf.cell(10, 6, "", border=1, align='C')
            pdf.cell(25, 6, "", border=1, align='C')
            pdf.cell(25, 6, "", border=1, align='C')
            pdf.cell(90, 6, "", border=1, align='C')
            pdf.cell(15, 6, "", border=1, align='C')
            pdf.cell(25, 6, "", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

    pdf.ln(10)
    pdf.set_font("Helvetica", 'B', 9)
    pdf.cell(95, 6, "Place: Salem", border=0)
    pdf.cell(95, 6, "Signature of the Scrutiny Member", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    pdf.cell(95, 6, f"Date: {datetime.now().strftime('%d/%m/%Y')}", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    filename = f"Scrutiny_Claim_{fid}.pdf"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/pdf')

# ==========================================
# 5. PROJECT / PRACTICAL CLAIM MODULE
# ==========================================
@app.route('/upload_prac_schedule', methods=['POST'])
def upload_prac_schedule():
    if 'user' not in session: return redirect(url_for('index'))
    if 'file' not in request.files: return redirect(url_for('dashboard'))
    
    file = request.files['file']
    sess_name = request.form.get('session_name', 'NOV / DEC')
    yr = request.form.get('session_year', '2025')
    
    if file.filename != '':
        try:
            df = pd.read_excel(file) if file.filename.endswith('.xlsx') else pd.read_csv(file)
            
            header_row = -1
            for i in range(min(15, len(df))):
                row_vals = [str(x).lower().replace(' ', '') for x in df.iloc[i].values]
                if any(key in v for v in row_vals for key in ['s.no', 'sno', 'sl.no', 'coursecode', 'examiner', 'orderno', 'programme']):
                    header_row = i
                    break
            if header_row >= 0:
                df.columns = df.iloc[header_row]
                df = df.iloc[header_row+1:].reset_index(drop=True)
            
            df = normalize_columns(df)
            db = get_db(); c = db.cursor()
            
            records = []
            current_record = None

            for idx, row in df.iterrows():
                order_col = next((col for col in df.columns if 'order_no' in col), df.columns[0])
                order_val = str(row.get(order_col, '')).strip()

                is_new = False
                if order_val and order_val.lower() != 'nan':
                    if any(char.isdigit() for char in order_val):
                        is_new = True

                int_col = next((col for col in df.columns if 'internal' in col), None)
                cands_col = next((col for col in df.columns if 'candidate' in col or 'total' in col), None)
                
                int_val = str(row.get(int_col, '')).strip() if int_col else ''
                cands_val = str(row.get(cands_col, '')).strip() if cands_col else '0'

                if int_val.lower() == 'nan': int_val = ''
                if cands_val.lower() == 'nan': cands_val = '0'

                if is_new:
                    if current_record:
                        records.append(current_record)
                    current_record = row.to_dict()
                    current_record['Internal_List'] = [int_val]
                    current_record['Candidates_List'] = [cands_val]
                else:
                    if current_record:
                        current_record['Internal_List'].append(int_val)
                        current_record['Candidates_List'].append(cands_val)

            if current_record:
                records.append(current_record)
                
            count = 0
            for rec in records:
                order_no = clean_str(rec.get('order_no'))
                if order_no.endswith('.0'): order_no = order_no[:-2]
                
                exam_date = clean_str(rec.get('exam_date', ''))
                prog = clean_str(rec.get('programme', ''))
                
                prog_upper = prog.upper()
                if 'M.E' in prog_upper or 'ME ' in prog_upper: degree = 'PG'
                elif 'B.E' in prog_upper or 'BE ' in prog_upper: degree = 'UG'
                else: degree = 'UG'
                
                sem = clean_str(rec.get('semester', ''))
                ccode = clean_str(rec.get('course_code', ''))
                ctitle = clean_str(rec.get('course_title') or rec.get('course_name', ''))
                dur = clean_str(rec.get('duration', '3'))
                board = clean_str(rec.get('board', prog))
                
                int_ex_joined = '|||'.join([clean_str(x) for x in rec.get('Internal_List', [])])
                cands_joined = '|||'.join([str(int(safe_float(x))) for x in rec.get('Candidates_List', [])])
                
                ext_val = rec.get('external_examiner')
                if isinstance(ext_val, pd.Series): ext_val = ext_val.dropna().iloc[0] if not ext_val.dropna().empty else ''
                ext_ex = str(ext_val).strip() if pd.notna(ext_val) else ''
                sk_asst = clean_name(rec.get('skilled_assistant'))
                
                if not ccode and not int_ex_joined and not ext_ex: continue
                
                c.execute("""INSERT INTO prac_schedules 
                    (order_no, exam_date, degree, programme, semester, course_code, course_title, duration, 
                     board, total_candidates, internal_examiner, external_examiner, skilled_assistant, session_name, session_year) 
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (order_no, exam_date, degree, prog, sem, ccode, ctitle, dur, board, cands_joined, int_ex_joined, ext_ex, sk_asst, sess_name, yr)
                )
                count += 1
            db.commit(); db.close()
            flash(f"{count} Project / Practical Schedules Uploaded Successfully!", "success")
        except Exception as e: flash(f"Error parsing Excel file: {str(e)}", "danger")
    return redirect(url_for('manage_prac_schedules'))

@app.route('/manage_prac_schedules')
def manage_prac_schedules():
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM prac_schedules ORDER BY id DESC")
    schedules = c.fetchall(); db.close()
    
    for s in schedules:
        try:
            s['display_cands'] = sum(int(float(x)) for x in str(s['total_candidates']).split('|||') if x.strip())
        except:
            s['display_cands'] = 0

    return render_template('manage_prac_schedules.html', schedules=schedules)

@app.route('/delete_prac_schedule/<int:sid>')
def delete_prac_schedule(sid):
    db = get_db(); c = db.cursor(); c.execute("DELETE FROM prac_schedules WHERE id=%s", (sid,)); db.commit(); db.close()
    flash("Schedule deleted!", "success")
    return redirect(url_for('manage_prac_schedules'))

@app.route('/clear_prac_schedules')
def clear_prac_schedules():
    db = get_db(); c = db.cursor(); c.execute("TRUNCATE TABLE prac_schedules"); db.commit(); db.close()
    flash("All Claims cleared!", "success")
    return redirect(url_for('manage_prac_schedules'))

@app.route('/practical_hub')
def practical_hub():
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("SELECT DISTINCT board FROM prac_schedules WHERE board != ''")
    boards = [r['board'] for r in c.fetchall()]; db.close()
    return render_template('practical_hub.html', boards=boards)

@app.route('/preview_practical_claim', methods=['POST'])
def preview_practical_claim():
    if 'user' not in session: return redirect(url_for('index'))
    dept = request.form.get('department')
    order_no = request.form.get('order_no')
    
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM prac_schedules WHERE board=%s AND order_no=%s ORDER BY id DESC LIMIT 1", (dept, order_no))
    sched = c.fetchone(); db.close()
    if not sched:
        flash(f"Order Number '{order_no}' not found for {dept}!", "danger")
        return redirect(url_for('practical_hub'))
        
    int_examiners_raw = str(sched.get('internal_examiner', '')).split('|||')
    cands_raw = str(sched.get('total_candidates', '')).split('|||')
    
    internals = []
    total_registered = 0
    for i in range(6):
        name = int_examiners_raw[i] if i < len(int_examiners_raw) else ""
        name = clean_name(name.split('\n')[0]) if name else ""
        
        cand = cands_raw[i] if i < len(cands_raw) else ""
        cand_int = int(float(cand)) if cand and str(cand).replace('.','').isdigit() else 0
        total_registered += cand_int
        
        internals.append({"name": name, "cands": cand_int if name else ""})
        
    raw_ext_text = str(sched['external_examiner']).strip()
    ext_lines = [line.strip() for line in raw_ext_text.split('\n') if line.strip()]
    ext_name = clean_name(ext_lines[0] if ext_lines else "")
    
    ext_parsed_desig = ext_lines[1] if len(ext_lines) > 1 else "Unknown Designation"
    ext_parsed_inst = ""
    if len(ext_lines) >= 4: ext_parsed_inst = f"{ext_lines[2]}, {ext_lines[3]}"
    elif len(ext_lines) == 3: ext_parsed_inst = ext_lines[2]
    elif len(ext_lines) == 2: ext_parsed_inst = ext_lines[1]
    
    return render_template('practical_preview.html', sched=sched, total_registered=total_registered, internals=internals, dept=dept, ext_name=ext_name, sk_asst=clean_name(sched.get('skilled_assistant')), ext_desig=ext_parsed_desig, ext_inst=ext_parsed_inst)

@app.route('/generate_practical_claim', methods=['POST'])
@app.route('/download_practical_claim', methods=['POST'])
def download_practical_claim():
    if 'user' not in session: return redirect(url_for('index'))
    
    dept = request.form.get('department')
    order_no = request.form.get('order_no')
    
    pdf_session = request.form.get('session_name', 'NOV / DEC').upper()
    pdf_year = request.form.get('session_year', '2025')
    
    claim_type = request.form.get('claim_type', 'Project')
    
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM prac_schedules WHERE board=%s AND order_no=%s ORDER BY id DESC LIMIT 1", (dept, order_no))
    sched = c.fetchone()
    
    int_names = request.form.getlist('internal_examiner[]')
    int_desigs = request.form.getlist('int_desig[]')
    cands_present = request.form.getlist('candidates_present[]')
    
    ext_name = clean_name(request.form.get('external_examiner'))
    ext_desig_input = request.form.get('ext_desig', '')
    ext_inst_input = request.form.get('ext_inst', '')
    
    sk_asst_name = clean_name(request.form.get('skilled_assistant'))
    nt_staff_name = clean_name(request.form.get('non_teaching_staff'))
    
    def fetch_fac(name):
        if not name: return {}
        c.execute("SELECT * FROM faculty_master WHERE name = %s LIMIT 1", (name,))
        res = c.fetchone()
        if res: return res
        clean_n = name.replace(' ', '').replace('.', '').lower()
        c.execute("SELECT * FROM faculty_master WHERE LOWER(REPLACE(REPLACE(name, ' ', ''), '.', '')) = %s LIMIT 1", (clean_n,))
        res = c.fetchone()
        if res: return res
        c.execute("SELECT * FROM faculty_master WHERE name LIKE %s LIMIT 1", (f"%{name}%",))
        return c.fetchone() or {}
        
    ext_fac = fetch_fac(ext_name)
    sk_fac = fetch_fac(sk_asst_name)
    nt_fac = fetch_fac(nt_staff_name)
    
    degree_type = str(sched.get('degree', 'UG')).upper()
    prog_upper = str(sched.get('programme', '')).upper()
    
    if 'PG' in degree_type or 'M.E' in prog_upper or 'ME ' in prog_upper:
        display_degree = 'PG'
        rate_exam = 50
        rate_sk = 20
        rate_nt = 10
    else:  
        display_degree = 'UG'
        rate_exam = 25
        rate_sk = 10
        rate_nt = 6
        
    if claim_type == 'Project':
        rate_exam = 300
        min_exam = 500
    else:
        min_exam = 250
        
    valid_internals = []
    total_present = 0
    for name, desig_input, cand in zip(int_names, int_desigs, cands_present):
        name = clean_name(name)
        if name:
            cand_int = int(cand) if cand and str(cand).isdigit() else 0
            total_present += cand_int
            fac_info = fetch_fac(name)
            desig = desig_input if desig_input else fac_info.get('designation', 'Internal Examiner')
            
            remun = max(cand_int * rate_exam, min_exam) if cand_int > 0 else 0
            valid_internals.append({
                "name": name,
                "desig": desig,
                "cands": cand_int,
                "remun": remun,
                "fac_data": fac_info
            })
            
    db.close()
    int_total_all = sum(x['remun'] for x in valid_internals)
    
    ext_desig = ext_desig_input if ext_desig_input else ext_fac.get('designation', '')
    ext_institution = ext_inst_input if ext_inst_input else ext_fac.get('institution_address', '__________________')
    
    sk_desig = request.form.get('sk_desig', sk_fac.get('designation', 'Skilled Asst.'))
    nt_desig = request.form.get('nt_desig', nt_fac.get('designation', 'Lab Assistant'))
    
    ext_remun = max(total_present * rate_exam, min_exam) if total_present > 0 and ext_name else 0
    
    if sk_asst_name and sk_asst_name.lower() not in ['na', 'none', '-', '']:
        sk_remun = max(total_present * rate_sk, 100) if total_present > 0 else 0
    else:
        sk_remun = 0
        sk_asst_name = ""
        
    if nt_staff_name and nt_staff_name.lower() not in ['na', 'none', '-', '']:
        nt_remun = max(total_present * rate_nt, 75) if total_present > 0 else 0
    else:
        nt_remun = 0
        nt_staff_name = ""
    
    ext_dist = int(float(ext_fac.get('distance', 0) or 0))
    ext_ta = (ext_dist * 12) if ext_dist > 35 else 400
    ext_da = 300 if ext_dist > 35 else 200
    if ext_dist == 0 or not ext_name: ext_ta = 0; ext_da = 0 
    
    ext_total = ext_remun + ext_ta + ext_da if ext_name else 0
    sk_total = sk_remun if sk_asst_name else 0
    nt_total = nt_remun if nt_staff_name else 0
    
    gross_total = int_total_all + ext_total + sk_total + nt_total
    
    # -------------------------------------------------------------
    # PAGE 1: REMUNERATION TABLE (Landscape)
    # -------------------------------------------------------------
    pdf = CustomPDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(False)
    pdf.add_page()
    
    pdf.set_font("Helvetica", 'B', 11)
    title_session = f"{pdf_session} {pdf_year}"
    pdf.cell(0, 6, f"CLAIM FORM FOR {claim_type.upper()} EXAMINATION - {title_session}", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    
    total_reg_cands = sum(int(float(x)) for x in str(sched['total_candidates']).split('|||') if x.strip())
    
    pdf.set_font("Helvetica", 'B', 9)
    pdf.cell(35, 6, "Order No"); pdf.set_font("Helvetica", '', 9); pdf.cell(100, 6, f": {sched['order_no']}")
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(65, 6, "Date(s)"); pdf.set_font("Helvetica", '', 9); pdf.cell(70, 6, f": {sched['exam_date']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(35, 6, "Degree"); pdf.set_font("Helvetica", '', 9); pdf.cell(100, 6, f": {display_degree}")
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(65, 6, "Number of Day(s)"); pdf.set_font("Helvetica", '', 9); pdf.cell(70, 6, ": 1", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(35, 6, "Programme"); pdf.set_font("Helvetica", '', 9); pdf.cell(100, 6, f": {sched['programme']}")
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(65, 6, "Duration of Exam (hrs)"); pdf.set_font("Helvetica", '', 9); pdf.cell(70, 6, f": {sched['duration']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(35, 6, "Course Code"); pdf.set_font("Helvetica", '', 9); pdf.cell(100, 6, f": {sched['course_code']}")
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(65, 6, "Candidates Registered"); pdf.set_font("Helvetica", '', 9); pdf.cell(70, 6, f": {total_reg_cands}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(35, 6, "Course Name"); pdf.set_font("Helvetica", '', 9); pdf.cell(100, 6, f": {sched['course_title'][:55]}")
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(65, 6, "Candidates Present"); pdf.set_font("Helvetica", '', 9); pdf.cell(70, 6, f": {total_present}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)
    
    pdf.set_font("Helvetica", 'B', 9)
    pdf.cell(0, 6, "I. Remuneration for Internal Examiner, External Examiner, Skilled Assistant, and Non-Teaching Staff:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    w = [35, 45, 30, 45, 17, 22, 18, 18, 22, 25] 
    headers = ["Role", "Name", "Designation", "Institution", "Dist(km)", "Remun(Rs)", "TA(Rs)", "DA(Rs)", "Total(Rs)", "Sign"]
    pdf.set_fill_color(230, 230, 230)
    for i, h in enumerate(headers): pdf.cell(w[i], 8, h, 1, 0, 'C', fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", '', 8)
    
    def print_remun_row(role, name, desig, inst, dist, remun, ta, da, tot):
        if pdf.get_y() > 180: 
            pdf.add_page(orientation='L')
            pdf.set_font("Helvetica", 'B', 9)
            pdf.set_fill_color(230, 230, 230)
            for i, h in enumerate(headers): pdf.cell(w[i], 8, h, 1, 0, 'C', fill=True)
            pdf.ln()
            pdf.set_font("Helvetica", '', 8)
            
        startX = pdf.get_x()
        startY = pdf.get_y()
        row_h = 11 
        line_h = 4.0
        for width in w:
            pdf.rect(pdf.get_x(), pdf.get_y(), width, row_h)
            pdf.set_x(pdf.get_x() + width)
        pdf.set_xy(startX, startY)
        
        pdf.cell(w[0], row_h, f" {role}", 0, 0, 'L')
        pdf.set_xy(startX + sum(w[:1]), startY + (0.5 if len(str(name))>23 else 3.5))
        pdf.multi_cell(w[1], line_h, f" {name}" if name else " _________________", 0, 'L')
        pdf.set_xy(startX + sum(w[:2]), startY + (0.5 if len(str(desig))>16 else 3.5))
        pdf.multi_cell(w[2], line_h, f" {desig}" if desig else "", 0, 'L')
        pdf.set_xy(startX + sum(w[:3]), startY + (0.5 if len(str(inst))>26 else 3.5))
        pdf.multi_cell(w[3], line_h, f" {inst}" if inst else "", 0, 'L')
        pdf.set_xy(startX + sum(w[:4]), startY)
        pdf.cell(w[4], row_h, str(dist) if str(dist) != "NA" else "NA", 0, 0, 'C')
        pdf.cell(w[5], row_h, str(remun) if str(remun) != "" else "________", 0, 0, 'C')
        pdf.cell(w[6], row_h, str(ta) if str(ta) != "NA" else "NA", 0, 0, 'C')
        pdf.cell(w[7], row_h, str(da) if str(da) != "NA" else "NA", 0, 0, 'C')
        pdf.cell(w[8], row_h, str(tot) if str(tot) != "" and str(tot) != "0" else "________", 0, 0, 'C')
        pdf.cell(w[9], row_h, "", 0, 1, 'C') 
        pdf.set_y(startY + row_h) 

    for i, internal in enumerate(valid_internals):
        role_label = "Internal Examiner" if i == 0 else ""
        print_remun_row(role_label, internal['name'], internal['desig'], "GCE Salem", "NA", internal['remun'], "NA", "NA", internal['remun'])

    if not valid_internals:
        print_remun_row("Internal Examiner", "", "", "GCE Salem", "NA", "", "NA", "NA", "")

    print_remun_row("External Examiner", ext_name, ext_desig, ext_institution, ext_dist if ext_name else "NA", ext_remun if ext_name else "", ext_ta if ext_name else "NA", ext_da if ext_name else "NA", ext_total if ext_name else "")
    print_remun_row("Skilled Assistant", sk_asst_name, sk_desig, "GCE Salem", "NA", sk_remun if sk_asst_name else "", "NA", "NA", sk_total if sk_asst_name else "")
    print_remun_row("Non-Teaching Staff", nt_staff_name, nt_desig, "GCE Salem", "NA", nt_remun if nt_staff_name else "", "NA", "NA", nt_total if nt_staff_name else "")
    
    pdf.set_font("Helvetica", 'B', 9)
    pdf.cell(sum(w[:8]), 8, "Gross Total Amount (Rs)", 1, 0, 'R', fill=True)
    pdf.cell(w[8], 8, str(gross_total), 1, 0, 'C', fill=True)
    pdf.cell(w[9], 8, "", 1, 1, 'C')
    
    pdf.cell(sum(w[:3]), 8, "Gross Total Amount (in Words) :", 1, 0, 'L')
    pdf.set_font("Helvetica", '', 9)
    pdf.cell(0, 8, f" Rupees {num_to_words(gross_total)}", 1, 1, 'L')

    # -------------------------------------------------------------
    # PAGE 2: BANK ACCOUNT PARTICULARS ONLY (Landscape)
    # -------------------------------------------------------------
    pdf.add_page(orientation='L')
    
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(270, 6, f"CLAIM FORM FOR {claim_type.upper()} EXAMINATION - {title_session}", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(10)

    pdf.set_font("Helvetica", 'B', 10)
    pdf.cell(270, 6, "II. Bank Account Particulars:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    bw = [10, 50, 35, 30, 45, 65, 35] # Wider columns! Sum = 270
    b_heads = ["S.No", "Name of the Staff", "Designation", "Mobile Number", "Bank Account Number", "Bank Name & Branch", "IFSC Code"]
    pdf.set_fill_color(220, 220, 220)
    for i, h in enumerate(b_heads): pdf.cell(bw[i], 8, h, 1, 0, 'C', fill=True)
    pdf.ln()
    
    pdf.set_font("Helvetica", '', 9)
    bank_rows = []
    idx_counter = 1
    
    for internal in valid_internals:
        bank_rows.append((str(idx_counter), internal['name'], internal['desig'], internal['fac_data']))
        idx_counter += 1
        
    if not valid_internals:
        bank_rows.append(("1", "", "", {}))
        idx_counter += 1
        
    bank_rows.extend([
        (str(idx_counter), ext_name, ext_desig, ext_fac), 
        (str(idx_counter+1), sk_asst_name, sk_desig, sk_fac), 
        (str(idx_counter+2), nt_staff_name, nt_desig, nt_fac)
    ])
    
    for idx_num, name, desig, f_data in bank_rows:
        if not name: continue
        startX = pdf.get_x()
        startY = pdf.get_y()
        row_h = 12
        line_h = 5.0
        for width in bw:
            pdf.rect(pdf.get_x(), pdf.get_y(), width, row_h)
            pdf.set_x(pdf.get_x() + width)
        pdf.set_xy(startX, startY)
        
        pdf.cell(bw[0], row_h, f" {idx_num}", 0, 0, 'C')
        pdf.set_xy(startX + sum(bw[:1]), startY + (0.5 if len(str(name))>30 else 3.5))
        pdf.multi_cell(bw[1], line_h, f" {name}" if name else "", 0, 'L')
        pdf.set_xy(startX + sum(bw[:2]), startY + (0.5 if len(str(desig))>20 else 3.5))
        pdf.multi_cell(bw[2], line_h, f" {desig}" if desig else "", 0, 'L')
        pdf.set_xy(startX + sum(bw[:3]), startY)
        pdf.cell(bw[3], row_h, f" {f_data.get('mobile_number', '')}", 0, 0, 'C')
        pdf.cell(bw[4], row_h, f" {format_val(f_data.get('account_number', ''))}", 0, 0, 'C')
        
        combined_bank = f"{f_data.get('bank_name', '')} - {f_data.get('branch_name', '')}".strip(' - ')
        pdf.set_xy(startX + sum(bw[:5]), startY + (0.5 if len(str(combined_bank))>40 else 3.5))
        pdf.multi_cell(bw[5], line_h, f" {combined_bank}", 0, 'L')
        
        pdf.set_xy(startX + sum(bw[:6]), startY)
        pdf.cell(bw[6], row_h, f" {f_data.get('ifsc', '')}", 0, 1, 'C')
        pdf.set_y(startY + row_h)

    # Clean Signature Area without COE
    pdf.ln(30)
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(135, 6, "Checked and Verified", align='L')
    pdf.cell(135, 6, "Chief Superintendent", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    filename = f"{claim_type}_Claim_{dept}_{order_no}.pdf"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/pdf')

# ==========================================
# 6. THEORY VALUATION ENGINE 
# ==========================================
@app.route('/valuation_index')
def valuation_index():
    if 'user' not in session: return redirect(url_for('index'))
    return render_template('valuation_index.html')

@app.route('/valuation_setup/<val_type>', methods=['GET', 'POST'])
def valuation_setup(val_type):
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db(); c = db.cursor()
    if request.method == 'POST':
        ac_year = request.form.get('academic_year')
        sem_type = request.form.get('sem_type')
        num_phases = int(request.form.get('num_phases', 1))
        c.execute("INSERT INTO val_sessions (type, academic_year, sem_type, num_phases) VALUES (%s, %s, %s, %s)", (val_type, ac_year, sem_type, num_phases))
        session_id = c.lastrowid
        for i in range(1, num_phases + 1):
            c.execute("INSERT INTO val_phases (session_id, phase_number, start_date, end_date) VALUES (%s, %s, %s, %s)", 
                      (session_id, i, request.form.get(f'phase_{i}_start'), request.form.get(f'phase_{i}_end')))
        db.commit(); db.close()
        return redirect(url_for('valuation_phases', session_id=session_id))
    return render_template('valuation_setup.html', val_type=val_type)

@app.route('/valuation_phases/<int:session_id>')
def valuation_phases(session_id):
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM val_sessions WHERE id=%s", (session_id,))
    sess_data = c.fetchone()
    c.execute("SELECT * FROM val_phases WHERE session_id=%s ORDER BY phase_number", (session_id,))
    phases = c.fetchall(); db.close()
    return render_template('valuation_phases.html', session=sess_data, phases=phases)

@app.route('/valuation_hub/<int:phase_id>')
def valuation_hub(phase_id):
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM val_subjects WHERE phase_id=%s", (phase_id,))
    subjects = c.fetchall()
    c.execute("SELECT * FROM val_examiners WHERE phase_id=%s", (phase_id,))
    raw_examiners = c.fetchall(); db.close()
    return render_template('valuation_hub.html', phase_id=phase_id, subjects=subjects, examiner_count=len(raw_examiners))

@app.route('/upload_val_subjects/<int:phase_id>', methods=['POST'])
def upload_val_subjects(phase_id):
    if 'file' not in request.files: return redirect(request.url)
    df = pd.read_excel(request.files['file']); db = get_db(); c = db.cursor()
    for _, row in df.iterrows():
        c.execute("""INSERT INTO val_subjects (phase_id, exam_date, session_fn_an, department, course_code, course_name, valuation_strength, dummy_number_start) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (phase_id, clean_str(row.iloc[0]), clean_str(row.iloc[1]), clean_str(row.iloc[2]), clean_str(row.iloc[3]), clean_str(row.iloc[4]), clean_str(row.iloc[5]), clean_str(row.iloc[6])))
    db.commit(); db.close(); flash("Subjects uploaded successfully!", "success")
    return redirect(url_for('valuation_hub', phase_id=phase_id))

@app.route('/upload_val_examiners/<int:phase_id>', methods=['POST'])
def upload_val_examiners(phase_id):
    if 'file' not in request.files: return redirect(request.url)
    df = pd.read_excel(request.files['file'])
    
    db = get_db(); c = db.cursor()
    c.execute("DELETE FROM val_examiners WHERE phase_id=%s", (phase_id,)) 
    
    current_staff = {}
    allocs_by_staff = {}
    staff_order = []
    
    current_d1_date = ""
    current_d2_date = ""
    current_d3_date = ""

    for _, row in df.iterrows():
        name = str(row.get('Examiner Name', '')).strip()
        
        if name and name.lower() != 'nan':
            current_staff = {
                'name': name,
                'inst': str(row.get('Institution', '')),
                'mob': str(row.get('Mobile', '')),
                'email': str(row.get('Email', ''))
            }
            if name not in allocs_by_staff:
                allocs_by_staff[name] = []
                staff_order.append(name)
            current_d1_date = ""
            current_d2_date = ""
            current_d3_date = ""

        if not current_staff.get('name'): continue
        active_name = current_staff['name']

        if str(row.get('Day 1 Date', '')).strip() and str(row.get('Day 1 Date', '')).lower() != 'nan':
            current_d1_date = str(row.get('Day 1 Date', '')).strip()
        if str(row.get('Day 2 Date', '')).strip() and str(row.get('Day 2 Date', '')).lower() != 'nan':
            current_d2_date = str(row.get('Day 2 Date', '')).strip()
        if str(row.get('Day 3 Date', '')).strip() and str(row.get('Day 3 Date', '')).lower() != 'nan':
            current_d3_date = str(row.get('Day 3 Date', '')).strip()

        if current_d1_date:
            d1_fn_c = str(row.get('Day 1 FN Course', '')).strip()
            d1_fn_s = str(row.get('Day 1 FN Scripts', '')).strip()
            if d1_fn_c and d1_fn_c.lower() != 'nan' and str(d1_fn_s).replace('.','').isdigit():
                allocs_by_staff[active_name].append({'date': current_d1_date, 'session': 'FN', 'course': d1_fn_c.upper(), 'scripts': int(float(d1_fn_s))})
            d1_an_c = str(row.get('Day 1 AN Course', '')).strip()
            d1_an_s = str(row.get('Day 1 AN Scripts', '')).strip()
            if d1_an_c and d1_an_c.lower() != 'nan' and str(d1_an_s).replace('.','').isdigit():
                allocs_by_staff[active_name].append({'date': current_d1_date, 'session': 'AN', 'course': d1_an_c.upper(), 'scripts': int(float(d1_an_s))})

        if current_d2_date:
            d2_fn_c = str(row.get('Day 2 FN Course', '')).strip()
            d2_fn_s = str(row.get('Day 2 FN Scripts', '')).strip()
            if d2_fn_c and d2_fn_c.lower() != 'nan' and str(d2_fn_s).replace('.','').isdigit():
                allocs_by_staff[active_name].append({'date': current_d2_date, 'session': 'FN', 'course': d2_fn_c.upper(), 'scripts': int(float(d2_fn_s))})
            d2_an_c = str(row.get('Day 2 AN Course', '')).strip()
            d2_an_s = str(row.get('Day 2 AN Scripts', '')).strip()
            if d2_an_c and d2_an_c.lower() != 'nan' and str(d2_an_s).replace('.','').isdigit():
                allocs_by_staff[active_name].append({'date': current_d2_date, 'session': 'AN', 'course': d2_an_c.upper(), 'scripts': int(float(d2_an_s))})

        if current_d3_date:
            d3_fn_c = str(row.get('Day 3 FN Course', '')).strip()
            d3_fn_s = str(row.get('Day 3 FN Scripts', '')).strip()
            if d3_fn_c and d3_fn_c.lower() != 'nan' and str(d3_fn_s).replace('.','').isdigit():
                allocs_by_staff[active_name].append({'date': current_d3_date, 'session': 'FN', 'course': d3_fn_c.upper(), 'scripts': int(float(d3_fn_s))})
            d3_an_c = str(row.get('Day 3 AN Course', '')).strip()
            d3_an_s = str(row.get('Day 3 AN Scripts', '')).strip()
            if d3_an_c and d3_an_c.lower() != 'nan' and str(d3_an_s).replace('.','').isdigit():
                allocs_by_staff[active_name].append({'date': current_d3_date, 'session': 'AN', 'course': d3_an_c.upper(), 'scripts': int(float(d3_an_s))})
            
    s_no = 1
    for staff_name in staff_order:
        if not allocs_by_staff[staff_name]: continue 
        c.execute("""INSERT INTO val_examiners (phase_id, s_no, staff_name, college_address, mobile, email, allocations_json) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (phase_id, str(s_no), staff_name, "", "", "", json.dumps(allocs_by_staff[staff_name])))
        s_no += 1
            
    db.commit(); db.close()
    flash("Examiner Allocations formatted and uploaded successfully!", "success")
    return redirect(url_for('valuation_hub', phase_id=phase_id))

@app.route('/edit_val_examiners/<int:phase_id>', methods=['GET', 'POST'])
def edit_val_examiners(phase_id):
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db(); c = db.cursor(dictionary=True)
    if request.method == 'POST':
        for key, val in request.form.items():
            if key.startswith('alloc_'):
                ex_id = key.split('_')[1]
                c.execute("UPDATE val_examiners SET allocations_json=%s WHERE id=%s", (val, ex_id))
        db.commit(); flash("Examiner allocations updated!", "success")
        return redirect(url_for('edit_val_examiners', phase_id=phase_id))
        
    c.execute("SELECT * FROM val_examiners WHERE phase_id=%s ORDER BY id", (phase_id,))
    examiners = c.fetchall()
    for ex in examiners: ex['alloc_text'] = json.dumps(json.loads(ex['allocations_json']), indent=2)
    db.close()
    return render_template('edit_val_examiners.html', phase_id=phase_id, examiners=examiners)

def compute_all_packets(phase_id):
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM val_subjects WHERE phase_id=%s", (phase_id,))
    subjects = {str(s['course_code']).strip().upper(): s for s in c.fetchall()}
    
    c.execute("SELECT * FROM val_examiners WHERE phase_id=%s ORDER BY id", (phase_id,))
    examiners = c.fetchall(); db.close()
    
    course_trackers = {}
    for code, s in subjects.items():
        try: d_start = int(re.sub(r'\D', '', str(s['dummy_number_start'])))
        except: d_start = 1000000
        course_trackers[code] = {'dummy': d_start, 'packet_no': 1}
        
    all_packets = []
    
    for ex in examiners:
        allocs = json.loads(ex['allocations_json'])
        for alloc in allocs:
            code = alloc['course']
            count = alloc['scripts']
            eval_date = alloc['date']
            
            if count <= 0: continue
            if code not in course_trackers: course_trackers[code] = {'dummy': 1000000, 'packet_no': 1}
            tracker = course_trackers[code]
            
            chunks = []
            c_left = count
            while c_left > 35:
                chunks.append(30)
                c_left -= 30
            if c_left > 0:
                chunks.append(c_left)
                
            for chunk in chunks:
                start_d = tracker['dummy']
                end_d = start_d + chunk - 1
                all_packets.append({
                    'examiner_id': ex['id'], 'staff_name': ex['staff_name'],
                    'course_code': code, 'course_name': subjects.get(code, {}).get('course_name', '-'),
                    'date': eval_date,
                    'packet_no': tracker['packet_no'], 'scripts': chunk,
                    'dummy_range': f"{start_d} - {end_d}"
                })
                tracker['dummy'] = end_d + 1
                tracker['packet_no'] += 1
                
    return all_packets

@app.route('/issue_register_hub/<int:phase_id>')
def issue_register_hub(phase_id):
    if 'user' not in session: return redirect(url_for('index'))
    return render_template('issue_register_hub.html', phase_id=phase_id)

@app.route('/preview_issue_register/<int:phase_id>', methods=['POST'])
def preview_issue_register(phase_id):
    fac_id = clean_str(request.form.get('faculty_id'))
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM faculty_master WHERE faculty_id=%s", (fac_id,))
    fac = c.fetchone()
    
    if not fac:
        flash(f"Faculty ID {fac_id} not found in Master Database!", "danger")
        return redirect(url_for('issue_register_hub', phase_id=phase_id))
        
    all_packets = compute_all_packets(phase_id)
    fac_name_clean = fac['name'].lower().replace('.', '').replace(' ', '')
    my_packets = [p for p in all_packets if fac_name_clean in p['staff_name'].lower().replace('.', '').replace(' ', '') or p['staff_name'].lower().replace('.', '').replace(' ', '') in fac_name_clean]
            
    if not my_packets:
        flash(f"No valuation scripts allocated to {fac['name']} in this phase!", "warning")
        return redirect(url_for('issue_register_hub', phase_id=phase_id))

    return render_template('issue_preview.html', phase_id=phase_id, fac=fac, packets=my_packets)

@app.route('/download_issue_register/<int:phase_id>', methods=['POST'])
def download_issue_register(phase_id):
    fac_id = request.form.get('faculty_id')
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("SELECT * FROM faculty_master WHERE faculty_id=%s", (fac_id,))
    fac = c.fetchone()
    
    c.execute("""SELECT s.session_name, s.session_year FROM val_phases p 
                 JOIN val_sessions s ON p.session_id = s.id WHERE p.id=%s""", (phase_id,))
    sess_info = c.fetchone()
    db.close()
    
    all_packets = compute_all_packets(phase_id)
    fac_name_clean = fac['name'].lower().replace('.', '').replace(' ', '')
    my_packets = [p for p in all_packets if fac_name_clean in p['staff_name'].lower().replace('.', '').replace(' ', '') or p['staff_name'].lower().replace('.', '').replace(' ', '') in fac_name_clean]
    
    pdf = CustomPDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.set_font("Helvetica", 'B', 11)
    sess_title = f"{sess_info['session_name']} {sess_info['session_year']}" if sess_info else "NOV/DEC 2025"
    pdf.cell(0, 6, f"VALUATION / REVALUATION - {sess_title}", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(150, 0, 0)
    pdf.cell(0, 6, "Issue Register", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)
    
    pdf.set_font("Helvetica", 'B', 9)
    pdf.cell(35, 6, "Faculty Code"); pdf.set_font("Helvetica", '', 9); pdf.cell(140, 6, f": {fac['faculty_id']}")
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(30, 6, "Valuation"); pdf.set_font("Helvetica", '', 9); pdf.cell(60, 6, f": Central Valuation", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(35, 6, "Examiner Name"); pdf.set_font("Helvetica", '', 9); pdf.cell(140, 6, f": {fac['name']}")
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(30, 6, "Mobile"); pdf.set_font("Helvetica", '', 9); pdf.cell(60, 6, f": {fac['mobile_number']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(35, 6, "Designation"); pdf.set_font("Helvetica", '', 9); pdf.cell(140, 6, f": {fac['designation']}")
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(30, 6, "Department"); pdf.set_font("Helvetica", '', 9); pdf.cell(60, 6, f": {fac['department']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font("Helvetica", 'B', 9); pdf.cell(35, 6, "Institution"); pdf.set_font("Helvetica", '', 9); pdf.cell(140, 6, f": {fac['institution_address']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    
    w = [12, 22, 25, 80, 18, 45, 18, 22, 28] 
    headers = ["S No", "Date", "Course Code", "Course Name", "Packet No.", "Dummy Number(s)", "Scripts", "Cum. Total", "Signature"]
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Helvetica", 'B', 9)
    for i, h in enumerate(headers): pdf.cell(w[i], 8, h, 1, 0, 'C', fill=True)
    pdf.ln()
    
    pdf.set_font("Helvetica", '', 8)
    cum_total = 0
    for idx, p in enumerate(my_packets, 1):
        cum_total += p['scripts']
        startX = pdf.get_x(); startY = pdf.get_y()
        row_h = 10
        if startY + row_h > 180:
            pdf.add_page(orientation='L')
            pdf.set_font("Helvetica", 'B', 9)
            for i, h in enumerate(headers): pdf.cell(w[i], 8, h, 1, 0, 'C', fill=True)
            pdf.ln()
            pdf.set_font("Helvetica", '', 8)
            startX = pdf.get_x(); startY = pdf.get_y()
            
        for width in w:
            pdf.rect(pdf.get_x(), pdf.get_y(), width, row_h)
            pdf.set_x(pdf.get_x() + width)
        pdf.set_xy(startX, startY)
        
        pdf.cell(w[0], row_h, str(idx), 0, 0, 'C')
        pdf.cell(w[1], row_h, str(p['date'])[:10], 0, 0, 'C')
        pdf.cell(w[2], row_h, str(p['course_code']), 0, 0, 'C')
        
        pdf.set_xy(startX + sum(w[:3]), startY + (0.5 if len(str(p['course_name']))>45 else 2.5))
        pdf.multi_cell(w[3], 4.5, f" {p['course_name']}", 0, 'L')
        
        pdf.set_xy(startX + sum(w[:4]), startY)
        pdf.cell(w[4], row_h, str(p['packet_no']), 0, 0, 'C')
        pdf.cell(w[5], row_h, str(p['dummy_range']), 0, 0, 'C')
        pdf.cell(w[6], row_h, str(p['scripts']), 0, 0, 'C')
        pdf.cell(w[7], row_h, str(cum_total), 0, 0, 'C')
        pdf.cell(w[8], row_h, "", 0, 1, 'C') 
        pdf.set_y(startY + row_h)
        
    for idx in range(len(my_packets)+1, 16):
        if pdf.get_y() + 8 > 180:
            pdf.add_page(orientation='L')
            pdf.set_font("Helvetica", 'B', 9)
            for i, h in enumerate(headers): pdf.cell(w[i], 8, h, 1, 0, 'C', fill=True)
            pdf.ln()
            pdf.set_font("Helvetica", '', 8)
        for width in w: pdf.cell(width, 8, "", 1, 0, 'C')
        pdf.ln()
        
    pdf.ln(10)
    if pdf.get_y() + 6 > 180:
        pdf.add_page(orientation='L')
    pdf.set_font("Helvetica", 'B', 10)
    pdf.cell(0, 6, "Controller of Examinations", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"Issue_Register_{fac_id}.pdf", mimetype='application/pdf')

# ==========================================
# 7. MANAGEMENT, REPORTS & TEMPLATES
# ==========================================
@app.route('/manage_calendar', methods=['GET', 'POST'])
def manage_calendar():
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db(); c = db.cursor(dictionary=True)
    if request.method == 'POST':
        date_val = clean_str(request.form.get('date'))
        day_type = clean_str(request.form.get('day_type'))
        if date_val and day_type:
            c.execute("REPLACE INTO calendar_master (date, day_type) VALUES (%s, %s)", (date_val, day_type))
            db.commit()
            flash("Calendar Updated Successfully!", "success")
    c.execute("SELECT * FROM calendar_master ORDER BY date DESC")
    cal = c.fetchall(); db.close()
    return render_template('manage_calendar.html', calendar=cal)

@app.route('/delete_calendar/<date_val>')
def delete_calendar(date_val):
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db(); c = db.cursor()
    c.execute("DELETE FROM calendar_master WHERE date=%s", (date_val,))
    db.commit(); db.close()
    flash("Date removed from calendar.", "success")
    return redirect(url_for('manage_calendar'))

@app.route('/download_template')
def download_template():
    if 'user' not in session: return redirect(url_for('index'))
    t_type = request.args.get('type')
    
    if t_type == 'course':
        df = pd.DataFrame(columns=['Course Code', 'Course Name', 'Department', 'Regulation', 'Semester'])
        filename = 'Course_Master_Template.xlsx'
    elif t_type == 'faculty':
        df = pd.DataFrame(columns=['Faculty ID', 'Faculty Name', 'Designation', 'Department', 'Institution Address', 'Mobile Number', 'Email Address', 'Bank Name', 'Account Number', 'IFSC Code', 'Branch Name', 'Place', 'Distance', 'Category', 'Bank Type'])
        filename = 'Faculty_Master_Template.xlsx'
    elif t_type == 'val_subjects':
        df = pd.DataFrame(columns=['Exam Date', 'Session FN/AN', 'Department', 'Course Code', 'Course Name', 'Valuation Strength', 'Dummy Number Start'])
        filename = 'Valuation_Subjects_Template.xlsx'
    elif t_type == 'val_allocations':
        cols = ['S.No', 'Examiner Name', 'Institution', 'Mobile', 'Email',
                'Day 1 Date', 'Day 1 FN Course', 'Day 1 FN Scripts', 'Day 1 AN Course', 'Day 1 AN Scripts',
                'Day 2 Date', 'Day 2 FN Course', 'Day 2 FN Scripts', 'Day 2 AN Course', 'Day 2 AN Scripts',
                'Day 3 Date', 'Day 3 FN Course', 'Day 3 FN Scripts', 'Day 3 AN Course', 'Day 3 AN Scripts']
        df = pd.DataFrame(columns=cols)
        filename = 'Examiner_Allocations_Template.xlsx'
    elif t_type == 'prac_schedule':
        df = pd.DataFrame(columns=['S.No', 'Date of Exam', 'Degree', 'Programme', 'Semester', 'Course Code', 'Course Title', 'Duration', 'Board', 'Total Candidates', 'Internal Examiner Name', 'External Examiner Details', 'Skilled Assistant Name'])
        filename = 'Practical_Schedule_Template.xlsx'
    else: 
        return redirect(url_for('dashboard'))
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: 
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/manage_courses', methods=['GET', 'POST'])
def manage_courses():
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db(); c = db.cursor(dictionary=True)
    if request.method == 'POST':
        if 'file' in request.files and request.files['file'].filename != '':
            try:
                file = request.files['file']
                df = pd.read_excel(file) if file.filename.endswith('.xlsx') else pd.read_csv(file)
                df = normalize_columns(df)
                count = 0
                for _, row in df.iterrows():
                    code = clean_str(row.get('course_code'))
                    if not code: continue 
                    sem_val = row.get('semester')
                    sem = int(float(sem_val)) if pd.notna(sem_val) and str(sem_val).strip() != '' else 0
                    
                    # Fix: Make sure course names pull correctly!
                    course_name = clean_str(row.get('course_name') or row.get('course_title'))
                    department = clean_str(row.get('department') or row.get('programme') or row.get('board'))
                    
                    c.execute("REPLACE INTO course_master (course_code, course_name, department, regulation, semester) VALUES (%s,%s,%s,%s,%s)", 
                              (code, course_name, department, clean_str(row.get('regulation')), sem))
                    count += 1
                db.commit()
                flash(f"{count} Courses Uploaded Successfully!", "success")
            except Exception as e: flash(f"Upload Error: {str(e)}", "danger")
        else:
            f = request.form
            code = clean_str(f.get('course_code'))
            if code:
                sem_val = f.get('semester')
                sem = int(float(sem_val)) if sem_val and str(sem_val).strip() != '' else 0
                c.execute("REPLACE INTO course_master (course_code, course_name, department, regulation, semester) VALUES (%s,%s,%s,%s,%s)", 
                          (code, clean_str(f.get('course_name')), clean_str(f.get('department')), clean_str(f.get('regulation')), sem))
                db.commit()
                flash("Course Saved Successfully!", "success")
    c.execute("SELECT * FROM course_master")
    res = c.fetchall(); db.close()
    return render_template('manage_courses.html', courses=res)

@app.route('/delete_course/<path:ccode>')
def delete_course(ccode):
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db(); c = db.cursor()
    c.execute("DELETE FROM course_master WHERE course_code=%s", (ccode,))
    db.commit(); db.close()
    return redirect(url_for('manage_courses'))

@app.route('/manage_faculty', methods=['GET', 'POST'])
def manage_faculty():
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db(); c = db.cursor(dictionary=True)
    if request.method == 'POST':
        if 'file' in request.files and request.files['file'].filename != '':
            try:
                df = pd.read_excel(request.files['file']) if request.files['file'].filename.endswith('.xlsx') else pd.read_csv(request.files['file'])
                df = normalize_columns(df)
                
                count = 0
                for _, row in df.iterrows():
                    name_val = clean_str(row.get('name') or row.get('faculty_name') or row.get('examiner_name') or row.get('faculty_id'))
                    if not name_val: continue
                    
                    fid = clean_str(row.get('faculty_id'))
                    if not fid or fid.lower() == 'nan':
                        fid = 'TEMP_' + "".join(filter(str.isalnum, name_val)).upper()[:10]
                        
                    c.execute("""REPLACE INTO faculty_master (faculty_id, name, designation, department, institution_address, mobile_number, email_address, bank_name, account_number, ifsc, branch_name, place, distance, category, bank_type) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                              (fid, name_val, clean_str(row.get('designation')), clean_str(row.get('department') or row.get('board')), clean_str(row.get('institution_address') or row.get('institution')), clean_str(row.get('mobile_number')), clean_str(row.get('email_address')), clean_str(row.get('bank_name')), clean_str(row.get('account_number')), clean_str(row.get('ifsc') or row.get('ifsc_code')), clean_str(row.get('branch_name')), clean_str(row.get('place')), safe_float(row.get('distance')), clean_str(row.get('category')), clean_str(row.get('bank_type')) or 'Nationalized'))
                    count += 1
                db.commit()
                flash(f"{count} Faculty profiles uploaded successfully!", "success")
            except Exception as e:
                flash(f"Error: {str(e)}", "danger")
        else:
            f = request.form
            c.execute("""REPLACE INTO faculty_master (faculty_id, name, designation, department, institution_address, mobile_number, email_address, bank_name, account_number, ifsc, branch_name, place, distance, category, bank_type) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (f['faculty_id'], f['name'], f['designation'], f['department'], f['institution_address'], f['mobile_number'], f['email_address'], f['bank_name'], f['account_number'], f['ifsc'], f['branch_name'], f['place'], safe_float(f['distance']), f['category'], f['bank_type']))
            db.commit()
            flash("Faculty Saved!", "success")
    c.execute("SELECT * FROM faculty_master")
    res = c.fetchall(); db.close()
    return render_template('manage_faculty.html', faculty=res)

@app.route('/delete_faculty/<fid>')
def delete_faculty(fid):
    if 'user' not in session: return redirect(url_for('index'))
    db = get_db(); c = db.cursor()
    c.execute("DELETE FROM faculty_master WHERE faculty_id=%s", (fid,))
    db.commit(); db.close()
    return redirect(url_for('manage_faculty'))

@app.route('/report')
def report():
    if 'user' not in session: return redirect(url_for('index'))
    sess = session.get('active_sess'); yr = session.get('active_year'); reg = session.get('active_reg', '2022')
    cat = request.args.get('category', 'All'); bank = request.args.get('bank_type', 'All')
    db = get_db(); c = db.cursor(dictionary=True)
    q = """SELECT s.faculty_id, MAX(s.scrutiny_date) as latest_date, SUM(s.courses_count) as total_qps, SUM(s.remuneration) as remuneration, SUM(s.ta_amount) as ta_amount, SUM(s.da_amount) as da_amount, SUM(s.grand_total) as grand_total, f.name, f.department, f.bank_name, f.account_number, f.ifsc, f.category, f.bank_type FROM scrutiny_records s LEFT JOIN faculty_master f ON s.faculty_id = f.faculty_id WHERE s.session_name=%s AND s.session_year=%s"""
    p = [sess, yr]
    if cat != 'All': q += " AND f.category=%s"; p.append(cat)
    if bank != 'All': q += " AND f.bank_type=%s"; p.append(bank)
    q += " GROUP BY s.faculty_id, f.name, f.department, f.bank_name, f.account_number, f.ifsc, f.category, f.bank_type ORDER BY f.name ASC"
    c.execute(q, tuple(p))
    recs = c.fetchall(); db.close()
    tot = {"remun": 0, "ta": 0, "da": 0, "grand": 0}; bank_abs = {}
    for r in recs:
        tot['remun'] += r['remuneration'] or 0; tot['ta'] += r['ta_amount'] or 0; tot['da'] += r['da_amount'] or 0; tot['grand'] += r['grand_total'] or 0
        b = r['bank_name'] if r['bank_name'] else "Unknown"
        if b not in bank_abs: bank_abs[b] = {'count': 0, 'total': 0}
        bank_abs[b]['count'] += 1; bank_abs[b]['total'] += (r['grand_total'] or 0)
    return render_template('consolidated_report.html', records=recs, totals=tot, cat_filter=cat, bank_filter=bank, bank_abstract=bank_abs, reg=reg, sess=sess, yr=yr)

@app.route('/export_excel')
def export_excel():
    if 'user' not in session: return redirect(url_for('index'))
    sess = session.get('active_sess'); yr = session.get('active_year')
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("""SELECT f.faculty_id AS 'Faculty ID', f.name AS 'Name', f.department AS 'Department', f.bank_name AS 'Bank Name', f.account_number AS 'Account Number', f.ifsc AS 'IFSC', f.bank_type AS 'Bank Type', f.category AS 'Category', MAX(s.scrutiny_date) AS 'Latest Scrutiny Date', SUM(s.courses_count) AS 'Total QPs', SUM(s.remuneration) AS 'Total Remuneration', SUM(s.ta_amount) AS 'Total TA', SUM(s.da_amount) AS 'Total DA', SUM(s.grand_total) AS 'Grand Total' FROM scrutiny_records s JOIN faculty_master f ON s.faculty_id = f.faculty_id WHERE s.session_name=%s AND s.session_year=%s GROUP BY f.faculty_id, f.name, f.department, f.bank_name, f.account_number, f.ifsc, f.bank_type, f.category ORDER BY f.name ASC""", (sess, yr))
    recs = c.fetchall(); db.close()
    if not recs: return redirect(url_for('report'))
    df = pd.DataFrame(recs); output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False, sheet_name='Consolidated Bank Statement')
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"Bank_Statement_{str(sess).replace('/', '-')}_{yr}.xlsx", mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/api/search_courses')
def api_search(): 
    q = request.args.get('q','')
    db = get_db(); c = db.cursor(dictionary=True)
    c.execute("SELECT course_code, course_name FROM course_master WHERE course_code LIKE %s OR course_name LIKE %s LIMIT 10", (f"%{q}%", f"%{q}%"))
    res = c.fetchall(); db.close()
    return jsonify(res)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
