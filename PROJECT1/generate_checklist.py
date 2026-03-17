import io
import os
import mysql.connector
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from fpdf import FPDF
from fpdf.enums import XPos, YPos

app = Flask(__name__)
app.secret_key = 'gce_salem_production_2025'

# --- HELPER: Find the logo reliably ---
def get_logo_path():
    # Look in the same folder as app.py
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Try different extensions
    for ext in ['jpg', 'png', 'jpeg']:
        path = os.path.join(base_dir, f"logo.{ext}")
        if os.path.exists(path):
            return path
    return None

def get_db():
    return mysql.connector.connect(
        host="localhost", user="root", password="", database="scrutiny_db"
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('username') == 'admin' and request.form.get('password') == 'coe123':
        session['user'] = 'admin'
        return redirect(url_for('scrutiny_page'))
    return "Invalid Credentials"

@app.route('/scrutiny')
def scrutiny_page():
    if 'user' not in session: return redirect(url_for('index'))
    return render_template('scrutiny.html')

@app.route('/get_faculty/<fid>')
def get_faculty(fid):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM faculty_master WHERE faculty_id = %s", (fid.strip(),))
        res = cursor.fetchone()
        db.close()
        return jsonify(res) if res else jsonify({"error": "Faculty ID not found"})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/process', methods=['POST'])
def process():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    try:
        data = request.json
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # 1. Fetch Faculty
        f_id = data['faculty_id'].strip()
        cursor.execute("SELECT * FROM faculty_master WHERE faculty_id = %s", (f_id,))
        fac = cursor.fetchone()
        if not fac: return jsonify({"error": f"ID {f_id} not found"}), 404

        # 2. Fetch Subjects
        input_codes = [c.strip() for c in data['courses'] if c.strip()]
        courses = []
        for code in input_codes:
            cursor.execute("SELECT * FROM course_master WHERE course_code = %s", (code,))
            res = cursor.fetchone()
            if res:
                courses.append(res)
            else:
                courses.append({'course_code': code, 'course_name': 'Pending DB Update', 'semester': '-', 'department': '-'})
        db.close()

        # 3. CALCULATIONS
        remun = len(courses) * 150
        dist_one_way = int(float(fac.get('distance', 0) or 0))
        
        is_external = data.get('is_external')
        ta_amount = min(dist_one_way * 12, 3600) if (is_external and dist_one_way > 0) else 0
        
        is_holiday = data.get('is_holiday')
        da_amount = 150 if is_holiday else 0
            
        grand_total = remun + ta_amount + da_amount
        scrutiny_date = data.get('date', '2025-11-01')

        # 4. PDF GENERATION
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        # --- LOGO SECTION (Fixed Path) ---
        logo_path = get_logo_path()
        if logo_path:
            # Place logo at x=10, y=10, width=22mm
            pdf.image(logo_path, x=10, y=10, w=22)
            # Shift header to the right to avoid overlapping logo
            pdf.set_left_margin(35) 
        
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(0, 5, "GOVERNMENT COLLEGE OF ENGINEERING, SALEM - 636 011", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.set_font("Helvetica", '', 8)
        pdf.cell(0, 4, "(NAAC Accredited with A+, An Autonomous Institution, Affiliated to Anna University, Chennai)", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.set_font("Helvetica", 'B', 9)
        pdf.cell(0, 5, "OFFICE OF THE CONTROLLER OF EXAMINATIONS", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.ln(1)
        pdf.cell(0, 5, "B.E. / M.E. DEGREE EXAMINATIONS - NOVEMBER / DECEMBER 2025 SESSION", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.cell(0, 5, "CLAIM FOR SCRUTINY MEMBER", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        
        # Reset Margin for the rest of the document
        pdf.set_left_margin(10)
        pdf.ln(6)

        # --- INFO GRID ---
        pdf.set_font("Helvetica", '', 8)
        line_h = 6
        
        def draw_row(lbl1, val1, lbl2, val2):
            pdf.cell(35, line_h, lbl1, 0)
            pdf.cell(60, line_h, str(val1)[:35], 'B')
            pdf.cell(5, line_h, "", 0)
            pdf.cell(35, line_h, lbl2, 0)
            pdf.cell(0, line_h, str(val2)[:35], 'B', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        dept = fac.get('department', '')
        place = fac.get('place', '')
        mobile = fac.get('mobile_number', '')
        if mobile:
            try:
                mobile = str(int(float(mobile))) # Removes .0
            except: pass
        
        addr = (fac.get('institution_address', '') or '').replace('\n', ', ')

        draw_row("MONTH and YEAR :", "Nov / Dec 2025", "Phase :", "I / II")
        draw_row("FACULTY ID :", f_id, "Board :", dept)
        draw_row("SCRUTINY MEMBER:", fac.get('name', ''), " *BANK NAME :", fac.get('bank_name', ''))
        draw_row("DESIGNATION :", fac.get('designation', ''), "ACCOUNT NUMBER :", fac.get('account_number', ''))
        draw_row("INSTITUTION ADDR:", addr, "IFSC :", fac.get('ifsc', ''))
        draw_row("MOBILE NUMBER :", mobile, "BRANCH NAME :", fac.get('branch_name', ''))
        draw_row("E-MAIL ADDRESS :", fac.get('email_address', ''), "PLACE :", place)
        
        pdf.ln(5)

        # --- REMUNERATION TABLE ---
        pdf.set_font("Helvetica", 'B', 8)
        pdf.cell(0, 5, "Remuneration Details :", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(10, 8, "S.No", 1, 0, 'C', fill=True)
        pdf.cell(15, 8, "Degree", 1, 0, 'C', fill=True)
        pdf.cell(25, 8, "Course Code", 1, 0, 'C', fill=True)
        pdf.cell(90, 8, "Course Name", 1, 0, 'C', fill=True)
        pdf.cell(20, 8, "No. of QP", 1, 0, 'C', fill=True)
        pdf.cell(25, 8, "Amount (Rs)", 1, 1, 'C', fill=True)

        pdf.set_font("Helvetica", '', 8)
        for i, c in enumerate(courses, 1):
            pdf.cell(10, 6, str(i), 1, 0, 'C')
            pdf.cell(15, 6, "B.E", 1, 0, 'C')
            pdf.cell(25, 6, str(c['course_code']), 1, 0, 'C')
            pdf.cell(90, 6, f" {str(c['course_name'])}", 1, 0, 'L')
            pdf.cell(20, 6, "1", 1, 0, 'C')
            pdf.cell(25, 6, "150.00", 1, 1, 'R')

        pdf.set_font("Helvetica", 'B', 8)
        pdf.cell(160, 7, "Total Claim (Rs) for Scrutinised Question Paper(s) :", 1, 0, 'R')
        pdf.cell(25, 7, f"{remun:.2f}", 1, 1, 'R')
        pdf.ln(5)

        # --- TA TABLE ---
        pdf.set_font("Helvetica", 'B', 8)
        pdf.cell(0, 5, "Claim Bill for Travelling Allowance (TA) and Daily Allowance (DA):", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 5, "Travelling Allowance (TA) :", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.cell(25, 8, "Date of Journey", 1, 0, 'C', fill=True)
        pdf.cell(45, 8, "From", 1, 0, 'C', fill=True)
        pdf.cell(45, 8, "To", 1, 0, 'C', fill=True)
        pdf.cell(20, 8, "Dist (km)", 1, 0, 'C', fill=True)
        pdf.cell(20, 8, "Mode", 1, 0, 'C', fill=True)
        pdf.cell(30, 8, "Amount (Rs)", 1, 1, 'C', fill=True)

        pdf.set_font("Helvetica", '', 8)
        if is_external:
            pdf.cell(25, 6, str(scrutiny_date), 1, 0, 'C')
            pdf.cell(45, 6, str(place)[:25], 1, 0, 'C')
            pdf.cell(45, 6, "GCE, Salem", 1, 0, 'C')
            pdf.cell(20, 6, str(dist_one_way), 1, 0, 'C')
            pdf.cell(20, 6, "Road", 1, 0, 'C')
            pdf.cell(30, 6, f"{ta_amount:.2f}", 1, 1, 'R')
        else:
            pdf.cell(185, 6, "Not Applicable (Internal / Local)", 1, 1, 'C')

        pdf.ln(2)

        # --- DA TABLE ---
        pdf.set_font("Helvetica", 'B', 8)
        pdf.cell(0, 5, "Daily Allowance (DA) :", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        pdf.set_font("Helvetica", '', 8)
        da_desc = "None"
        if is_holiday: da_desc = "Holiday Allowance"
        elif is_external: da_desc = "External Duty"
        
        pdf.cell(40, 6, "DA Type:", 1, 0, 'L')
        pdf.cell(60, 6, da_desc, 1, 0, 'L')
        pdf.cell(40, 6, "No. of Days : 1", 1, 0, 'R')
        pdf.cell(45, 6, f"{da_amount:.2f}", 1, 1, 'R')

        # --- GRAND TOTAL ---
        pdf.ln(2)
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(140, 8, "GRAND TOTAL (Remuneration + TA + DA):", 1, 0, 'R')
        pdf.cell(45, 8, f"Rs. {grand_total:.2f}", 1, 1, 'R')

        # --- SIGNATURES ---
        pdf.ln(15)
        pdf.set_font("Helvetica", '', 8)
        curr_y = pdf.get_y()
        pdf.line(10, curr_y, 70, curr_y) 
        pdf.cell(60, 5, "Signature of the Scrutiny Member", 0, 0, 'L')
        pdf.line(140, curr_y, 200, curr_y) 
        pdf.cell(125, 5, "Controller of Examinations", 0, 1, 'R')

        output = io.BytesIO(pdf.output())
        return send_file(output, mimetype='application/pdf', as_attachment=True, download_name=f"Claim_{f_id}.pdf")

    except Exception as e:
        print(f"ERROR: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)