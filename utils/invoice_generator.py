# utils/invoice_generator.py
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from io import BytesIO
from django.conf import settings
import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Register the font
font_path = os.path.join(settings.BASE_DIR, 'fonts', 'Helvetica.ttf')
font_bold_path = os.path.join(settings.BASE_DIR, 'fonts', 'Helvetica-Bold.ttf')

pdfmetrics.registerFont(TTFont('Helvetica', font_path))
pdfmetrics.registerFont(TTFont('Helvetica-Bold', font_bold_path))

  
def generate_invoice_pdf(order):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4 

    # Company Logo
    logo_path = os.path.join(settings.MEDIA_ROOT, 'images/logo.png')
    if os.path.exists(logo_path):
        p.drawImage(logo_path, 50, height - 100, width=100, height=50)

    # Company Details
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 150, "Tax Invoice/Bill of Supply/Cash Memo")
    
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 180, "HERBAL POWER MARKETING")
    p.drawString(50, height - 195, "B-88, Amaltash Marg, Nearby -Sector -15 Metro")
    p.drawString(50, height - 210, "Station, Sector -2, Noida, UTTAR PRADESH")
    p.drawString(50, height - 225, "NOIDA, UTTAR PRADESH, 201301")

    # Customer Details
    p.drawString(300, height - 180, "Billing Address:")
    p.drawString(300, height - 195, order.shipping_address)

    # Order Details
    p.drawString(50, height - 270, f"Order Number: {order.order_number}")
    p.drawString(50, height - 285, f"Order Date: {order.order_date.strftime('%d.%m.%Y')}")
    p.drawString(50, height - 300, f"Invoice Number: IN-{order.id}")
    
    # GST Details
    p.drawString(300, height - 270, "GST Registration No: 09AAHCH1773P1ZX")
    p.drawString(300, height - 285, "PAN No: AAHCH1773P")

    # Table Header
    data = [['Description', 'Qty', 'Rate', 'Amount', 'GST', 'Total']]
    
    # Table Data
    for item in order.items.all():
        data.append([
            item.product.name,
            str(item.quantity),
            f"₹{item.price:.2f}",
            f"₹{(item.price * item.quantity):.2f}",
            f"₹{item.gst_amount:.2f}",
            f"₹{item.final_price:.2f}"
        ])
    
    # Totals
    data.append(['', '', '', '', 'Sub Total:', f"₹{order.total_amount:.2f}"])
    data.append(['', '', '', '', 'GST:', f"₹{(order.final_amount - order.total_amount):.2f}"])
    data.append(['', '', '', '', 'Total:', f"₹{order.final_amount:.2f}"])

    if order.user.role == 'MLM_MEMBER':
        data.append(['', '', '', '', 'BP Points:', str(order.total_bp)])

    # Create table
    table = Table(data, colWidths=[200, 50, 70, 70, 70, 70])
    table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
    ]))

    # Draw table
    table.wrapOn(p, width, height)
    table.drawOn(p, 30, height - 500)

    # Footer
    p.setFont("Helvetica", 10)
    p.drawString(50, 50, "This is a computer generated invoice")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer