#!/usr/bin/env python3
"""
Generate dummy_blood_report.pdf for local testing and CI.

Usage:
    pip install fpdf2
    python generate_dummy_report.py
"""
from pathlib import Path
from fpdf import FPDF
from fpdf.enums import XPos, YPos


def generate(out: Path = Path("dummy_blood_report.pdf")) -> None:
    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "COMPLETE BLOOD COUNT REPORT", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 6, "City General Hospital - Department of Haematology", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(4)

    # Patient info
    pdf.set_font("Helvetica", size=11)
    for label, val in [
        ("Patient", "John Doe"),
        ("Date of Birth", "15-May-1980"),
        ("Test Date", "15-Jan-2024"),
        ("Ordering Physician", "Dr. Sarah Ahmed, MD"),
    ]:
        pdf.cell(60, 7, f"{label}:", border=0)
        pdf.cell(0, 7, val, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    # Results table
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Test Results", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    headers = ["Test", "Result", "Reference Range", "Status"]
    col_w = [65, 40, 55, 30]
    rows = [
        ("Haemoglobin",   "13.5 g/dL",  "12.0-17.5 g/dL",   "Normal"),
        ("WBC Count",     "7500 /uL",   "4500-11000 /uL",    "Normal"),
        ("Platelet Count","250000 /uL", "150000-400000 /uL", "Normal"),
        ("Vitamin B12",   "180 pg/mL",  "200-900 pg/mL",     "LOW"),
        ("Ferritin",      "8 ng/mL",    "12-300 ng/mL",      "LOW"),
        ("MCV",           "72 fL",      "80-100 fL",         "LOW"),
        ("MCH",           "24 pg",      "27-33 pg",          "LOW"),
        ("Serum Iron",    "40 ug/dL",   "60-170 ug/dL",      "LOW"),
    ]

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(200, 220, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 8, h, border=1, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", size=10)
    for row in rows:
        status = row[3]
        if status == "LOW":
            pdf.set_fill_color(255, 210, 210)
        elif status == "HIGH":
            pdf.set_fill_color(255, 240, 180)
        else:
            pdf.set_fill_color(235, 255, 235)
        for i, cell in enumerate(row):
            pdf.cell(col_w[i], 8, cell, border=1, fill=(i == 3))
        pdf.ln()

    # Clinical notes
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Clinical Assessment", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(0, 6,
        "Iron deficiency anaemia with concurrent Vitamin B12 deficiency is noted. "
        "Low MCV, MCH, and serum iron are consistent with microcytic hypochromic anaemia. "
        "B12 deficiency may contribute to neurological symptoms. "
        "Recommend: dietary assessment, oral iron supplementation (ferrous sulphate 200mg TDS), "
        "intramuscular B12 injections, and repeat CBC in 3 months. "
        "Consider gastroenterology referral if dietary causes are excluded.")

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 6, "Report verified by: Dr. Sarah Ahmed, MD (Haematology)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, "This report is generated for testing purposes only.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.output(str(out))
    print(f"Generated: {out}  ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    generate()
