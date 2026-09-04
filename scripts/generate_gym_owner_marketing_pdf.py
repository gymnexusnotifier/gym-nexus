"""Generate the gym-owner marketing and demo PDF."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

OUT = Path("docs/gym-owner-marketing-brochure.pdf")
W, H = A4
NAVY = colors.HexColor("#081827")
NAVY_2 = colors.HexColor("#102d43")
CYAN = colors.HexColor("#28d7e8")
MINT = colors.HexColor("#79f2bd")
WHITE = colors.white
MUTED = colors.HexColor("#a9c0d2")
INK = colors.HexColor("#18364c")
PALE = colors.HexColor("#effbfc")
PURPLE = colors.HexColor("#8b5cf6")
RED = colors.HexColor("#f87171")
GOLD = colors.HexColor("#fbbf24")

styles = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=15, textColor=INK)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=11, textColor=MUTED)
WHITE_BODY = ParagraphStyle("whitebody", parent=BODY, textColor=WHITE)


def text(c, value, x, y, size=10, color=INK, bold=False):
    c.setFillColor(color)
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.drawString(x, y, value)


def wrapped(c, value, x, y, width, style=BODY):
    p = Paragraph(value, style)
    _, height = p.wrap(width, H)
    p.drawOn(c, x, y - height)
    return height


def pill(c, label, x, y, fill=CYAN, fg=NAVY):
    width = stringWidth(label, "Helvetica-Bold", 8) + 18
    c.setFillColor(fill)
    c.roundRect(x, y - 14, width, 18, 9, fill=1, stroke=0)
    text(c, label, x + 9, y - 9, 8, fg, True)
    return width


def chrome(c, title, active="Dashboard"):
    c.setFillColor(NAVY)
    c.roundRect(40, 105, W - 80, H - 170, 12, fill=1, stroke=0)
    c.setFillColor(NAVY_2)
    c.roundRect(40, 105, 145, H - 170, 12, fill=1, stroke=0)
    text(c, "GYM CONSOLE", 58, H - 100, 11, WHITE, True)
    c.setFillColor(CYAN)
    c.circle(50, H - 96, 3, fill=1, stroke=0)
    nav = ["Dashboard", "Members", "Plans", "Payments", "Classes", "Attendance", "Inquiries", "Staff", "Billing"]
    for i, item in enumerate(nav):
        y = H - 145 - i * 25
        if item == active:
            c.setFillColor(colors.HexColor("#174c64"))
            c.roundRect(52, y - 8, 120, 20, 6, fill=1, stroke=0)
        text(c, item, 62, y, 8, WHITE if item == active else MUTED, item == active)
    text(c, title, 210, H - 125, 16, WHITE, True)
    c.setStrokeColor(colors.HexColor("#31516a"))
    c.line(210, H - 140, W - 60, H - 140)


def stat(c, label, value, x, y, accent=CYAN):
    c.setFillColor(colors.HexColor("#143149"))
    c.roundRect(x, y, 112, 62, 8, fill=1, stroke=0)
    c.setFillColor(accent)
    c.rect(x, y + 59, 112, 3, fill=1, stroke=0)
    text(c, label.upper(), x + 10, y + 42, 7, MUTED, True)
    text(c, value, x + 10, y + 17, 19, WHITE, True)


def dashboard_preview(c):
    chrome(c, "AI Insights", "Dashboard")
    for i, (label, value) in enumerate([
        ("Today's check-ins", "42"), ("Currently in gym", "18"), ("Active members", "326"), ("Revenue this month", "Rs. 84K")
    ]):
        stat(c, label, value, 210 + (i % 4) * 122, H - 220, [CYAN, MINT, PURPLE, GOLD][i])
    c.setFillColor(colors.HexColor("#143149"))
    c.roundRect(210, H - 425, 250, 170, 8, fill=1, stroke=0)
    text(c, "TRAFFIC BY TIME", 225, H - 280, 9, WHITE, True)
    for i, height in enumerate([22, 35, 48, 30, 74, 112, 88, 44, 20]):
        c.setFillColor(CYAN if i == 5 else colors.HexColor("#287b96"))
        c.roundRect(228 + i * 23, H - 393, 13, height, 3, fill=1, stroke=0)
    text(c, "06h     09h     12h     15h     18h     21h", 225, H - 410, 7, MUTED)
    c.setFillColor(colors.HexColor("#143149"))
    c.roundRect(475, H - 425, 180, 170, 8, fill=1, stroke=0)
    text(c, "GROWTH OPPORTUNITIES", 490, H - 280, 9, WHITE, True)
    for i, item in enumerate(["Renewals next 30 days", "Lead conversion", "At-risk members"]):
        pill(c, ["18", "12.5%", "9"][i], 490, H - 310 - i * 34, [GOLD, MINT, RED][i], NAVY)
        text(c, item, 540, H - 319 - i * 34, 8, MUTED)


def table_preview(c, title, active, headers, rows, y=H - 220):
    chrome(c, title, active)
    x, width = 210, W - 270
    c.setFillColor(colors.HexColor("#143149"))
    c.roundRect(x, y - 220, width, 190, 8, fill=1, stroke=0)
    col_width = width / len(headers)
    for i, header in enumerate(headers):
        text(c, header.upper(), x + 12 + i * col_width, y - 55, 7, MUTED, True)
    for r, row in enumerate(rows):
        yy = y - 88 - r * 34
        c.setStrokeColor(colors.HexColor("#31516a"))
        c.line(x + 10, yy + 13, x + width - 10, yy + 13)
        for i, value in enumerate(row):
            text(c, value, x + 12 + i * col_width, yy, 8, WHITE if i == 0 else MUTED, i == 0)


def page_footer(c, page):
    text(c, f"GYM CONSOLE  /  GYM OWNER DEMO KIT  /  {page:02d}", 42, 28, 7, MUTED, True)


def build():
    OUT.parent.mkdir(exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=A4)
    c.setTitle("Gym Console - Gym Owner Demo Brochure")

    # 1 Cover
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(CYAN)
    c.circle(W - 55, H - 62, 95, fill=1, stroke=0)
    c.setFillColor(PURPLE)
    c.circle(W - 75, H - 85, 48, fill=1, stroke=0)
    text(c, "GYM CONSOLE", 48, H - 90, 14, CYAN, True)
    text(c, "Your gym,", 48, H - 215, 36, WHITE, True)
    text(c, "finally in sync.", 48, H - 258, 36, CYAN, True)
    wrapped(c, "A smarter operating system for modern gyms: member relationships, attendance, payments, classes, staff, and growth signals in one calm workspace.", 48, H - 300, 355, WHITE_BODY)
    pill(c, "GYM OWNER EDITION", 48, H - 395, MINT, NAVY)
    text(c, "A ready-to-share product story for client demos", 48, 86, 10, MUTED)
    c.showPage()

    # 2 Value proposition
    c.setFillColor(PALE); c.rect(0, 0, W, H, fill=1, stroke=0)
    text(c, "A better day at the gym", 48, H - 70, 27, NAVY, True)
    wrapped(c, "Gym Console turns the scattered work behind a great member experience into one visible flow. Less chasing. Fewer spreadsheets. More time for people.", 48, H - 95, 500, BODY)
    cards = [
        ("SEE THE FLOOR", "Know who is in, when your gym is busiest, and where the quiet windows are.", CYAN),
        ("KEEP REVENUE MOVING", "Record every payment, capture UPI references, and send a polished receipt automatically.", MINT),
        ("RETENTION WITH CONTEXT", "Spot at-risk members, upcoming renewals, and today's follow-ups before they go cold.", PURPLE),
        ("DELEGATE WITH CONTROL", "Invite staff and trainers, choose their privileges, and keep an activity history.", GOLD),
    ]
    for i, (head, body, accent) in enumerate(cards):
        x = 48 + (i % 2) * 260; y = H - 225 - (i // 2) * 145
        c.setFillColor(WHITE); c.roundRect(x, y, 230, 105, 10, fill=1, stroke=0)
        c.setFillColor(accent); c.rect(x, y + 101, 230, 4, fill=1, stroke=0)
        text(c, head, x + 16, y + 75, 11, NAVY, True)
        wrapped(c, body, x + 16, y + 62, 198, BODY)
    text(c, "THE PROMISE", 48, 115, 9, PURPLE, True)
    text(c, "Run the business from the same place your team runs the day.", 48, 92, 16, NAVY, True)
    page_footer(c, 2); c.showPage()

    # 3 Dashboard preview
    c.setFillColor(NAVY); c.rect(0, 0, W, H, fill=1, stroke=0)
    text(c, "One glance. Better decisions.", 48, H - 65, 25, WHITE, True)
    wrapped(c, "AI Insights brings the most important signals to the front: traffic, revenue, retention, and action items. It is operational clarity, not vanity analytics.", 48, H - 91, 500, WHITE_BODY)
    dashboard_preview(c)
    page_footer(c, 3); c.showPage()

    # 4 Attendance
    c.setFillColor(PALE); c.rect(0, 0, W, H, fill=1, stroke=0)
    text(c, "Attendance that tells a story", 48, H - 65, 25, NAVY, True)
    wrapped(c, "Use face scanning for a fast front desk, or manual marking when the camera is unavailable. Every check-in and check-out becomes useful business context.", 48, H - 91, 500, BODY)
    table_preview(c, "Attendance Log", "Attendance", ["Date", "Check-in", "Check-out", "Member"], [
        ("04 Sep", "18:10", "19:20", "Aarav Sharma"), ("04 Sep", "18:05", "19:00", "Maya Patel"),
        ("04 Sep", "07:15", "08:20", "Kabir Singh"), ("03 Sep", "12:00", "12:45", "Riya Mehta")
    ], H - 220)
    pill(c, "PEAK 18:00", 210, H - 470, CYAN, NAVY)
    pill(c, "AVG VISIT 58 MIN", 320, H - 470, MINT, NAVY)
    text(c, "Schedule your team around demand, not guesswork.", 210, H - 510, 12, NAVY, True)
    page_footer(c, 4); c.showPage()

    # 5 Payments
    c.setFillColor(NAVY); c.rect(0, 0, W, H, fill=1, stroke=0)
    text(c, "Every payment, professionally closed", 48, H - 65, 25, WHITE, True)
    wrapped(c, "Cash, UPI, card, and bank transfer all live in one payment trail. UPI payments capture a UTR or transaction ID, while the member receives a confirmation email with the branded receipt attached.", 48, H - 91, 500, WHITE_BODY)
    table_preview(c, "Payments", "Payments", ["Member", "Method", "Amount", "Receipt"], [
        ("Aarav Sharma", "UPI / UTR", "Rs. 2,000", "PDF"), ("Maya Patel", "Card", "Rs. 5,000", "PDF"),
        ("Kabir Singh", "Cash", "Rs. 2,000", "PDF"), ("Riya Mehta", "Bank transfer", "Rs. 2,000", "PDF")
    ], H - 220)
    c.setFillColor(colors.HexColor("#143149")); c.roundRect(210, 145, W - 270, 75, 8, fill=1, stroke=0)
    text(c, "MEMBER EMAIL", 228, 190, 8, MUTED, True)
    text(c, "Payment confirmed + receipt_7A31C2F1.pdf", 228, 165, 12, CYAN, True)
    page_footer(c, 5); c.showPage()

    # 6 Team and close
    c.setFillColor(PALE); c.rect(0, 0, W, H, fill=1, stroke=0)
    text(c, "Grow the team without losing control", 48, H - 65, 25, NAVY, True)
    wrapped(c, "Invite a staff member or trainer with a temporary password, assign only the areas they need, and review activity history when you need the full picture.", 48, H - 91, 500, BODY)
    table_preview(c, "Team Access", "Staff", ["Team member", "Role", "Access", "Status"], [
        ("frontdesk@afc.com", "Staff", "Members / Payments", "Active"),
        ("coach@afc.com", "Trainer", "Classes / Attendance", "Active"),
        ("manager@afc.com", "Staff", "All operations", "Active"),
    ], H - 220)
    text(c, "A simple demo flow", 48, 205, 14, NAVY, True)
    steps = ["1  Add a plan", "2  Add a member", "3  Mark attendance", "4  Record payment", "5  Act on AI Insights"]
    for i, step in enumerate(steps):
        x = 48 + (i % 3) * 175; y = 170 - (i // 3) * 38
        pill(c, step, x, y, [CYAN, MINT, PURPLE, GOLD, RED][i], NAVY)
    text(c, "Ready for a live demo", 48, 75, 18, NAVY, True)
    text(c, "Show the floor. Show the numbers. Show the next best action.", 48, 51, 10, INK)
    page_footer(c, 6); c.showPage()
    c.save()
    print(f"Created {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
