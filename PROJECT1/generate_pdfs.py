from fpdf import FPDF

class GCE_Generator:
    def __init__(self, data, date):
        self.data = data
        self.date = date
        self.pdf = FPDF()

    def generate_combined_pdf(self):
        # PAGE 1: CHECKLIST
        self.add_checklist_page()
        
        # PAGE 2: CLAIM BILL
        self.add_claim_bill_page()
        
        # PAGE 3: ISSUE REGISTER
        self.add_issue_register_page()
        
        return self.pdf.output(dest='S') # Output as string/bytes

    def add_checklist_page(self):
        self.pdf.add_page()
        self.pdf.set_font("Arial", "B", 14)
        self.pdf.cell(0, 10, "GOVERNMENT COLLEGE OF ENGINEERING, SALEM", ln=True, align="C")
        self.pdf.set_font("Arial", "B", 10)
        self.pdf.cell(0, 5, "CHECKLIST FOR QUESTION PAPER SCRUTINY", ln=True, align="C")
        
        self.pdf.ln(10)
        self.pdf.set_font("Arial", "", 10)
        f = self.data['faculty']
        self.pdf.cell(0, 8, f"Member Name: {f['name']}", ln=True)
        self.pdf.cell(0, 8, f"Designation: {f['designation']} / {f['department']}", ln=True)
        # ... Add more fields based on your image layout ...

    def add_claim_bill_page(self):
        self.pdf.add_page()
        self.pdf.set_font("Arial", "B", 12)
        self.pdf.cell(0, 10, "CLAIM FOR SCRUTINY MEMBER", ln=True, align="C")
        
        # Math Table
        self.pdf.ln(5)
        self.pdf.cell(100, 8, "Remuneration", 1)
        self.pdf.cell(40, 8, f"Rs. {self.data['remuneration']}", 1, ln=True)
        self.pdf.cell(100, 8, "TA (12/km capped at 3600)", 1)
        self.pdf.cell(40, 8, f"Rs. {self.data['ta']}", 1, ln=True)
        self.pdf.cell(100, 8, "DA (Holiday Allowance)", 1)
        self.pdf.cell(40, 8, f"Rs. {self.data['da']}", 1, ln=True)
        self.pdf.set_font("Arial", "B", 11)
        self.pdf.cell(100, 8, "GRAND TOTAL", 1)
        self.pdf.cell(40, 8, f"Rs. {self.data['grand_total']}", 1, ln=True)