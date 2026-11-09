import os
import io
import zipfile
from datetime import datetime
from typing import List
from fastapi import FastAPI, Request, File, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from parser_xml import parsear_factura_xml

app = FastAPI(
    title="IVA Rápido - Sistema Contable",
    description="Plataforma web para gestión y cálculo automático de IVA",
    version="1.0.0",
)

UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Base de datos en memoria
facturas_db = []


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/resumen-iva")
async def obtener_resumen_iva():
    iva_trasladado = sum(f["monto_iva"] for f in facturas_db if f["tipo_comprobante"] == "I")
    iva_acreditable = sum(f["monto_iva"] for f in facturas_db if f["tipo_comprobante"] == "E")
    
    diferencia = iva_trasladado - iva_acreditable
    
    if diferencia >= 0:
        saldo_a_pagar = round(diferencia, 2)
        saldo_a_favor = 0.0
    else:
        saldo_a_pagar = 0.0
        saldo_a_favor = round(abs(diferencia), 2)

    tasas_breakdown = {"16%": 0.0, "8%": 0.0, "0%": 0.0, "Exento": 0.0}
    for f in facturas_db:
        tasa = f.get("tasa_iva", "16%")
        if tasa in tasas_breakdown:
            tasas_breakdown[tasa] += f["monto_iva"]
        else:
            tasas_breakdown["16%"] += f["monto_iva"]

    return {
        "periodo": "Noviembre 2026",
        "iva_trasladado": round(iva_trasladado, 2),
        "iva_acreditable": round(iva_acreditable, 2),
        "iva_a_pagar": saldo_a_pagar,
        "saldo_a_favor": saldo_a_favor,
        "total_documentos": len(facturas_db),
        "total_ingresos": len([f for f in facturas_db if f["tipo_comprobante"] == "I"]),
        "total_egresos": len([f for f in facturas_db if f["tipo_comprobante"] == "E"]),
        "desglose_tasas": {k: round(v, 2) for k, v in tasas_breakdown.items()},
        "facturas": facturas_db
    }


@app.post("/api/subir-facturas")
async def subir_facturas(files: List[UploadFile] = File(...)):
    procesados = []
    errores = 0

    for file in files:
        filename = file.filename.lower()
        content = await file.read()

        if filename.endswith(".xml"):
            try:
                datos = parsear_factura_xml(content)
                facturas_db.append(datos)
                procesados.append(datos)
            except Exception:
                errores += 1

        elif filename.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for zip_info in z.infolist():
                        if zip_info.filename.lower().endswith(".xml") and not zip_info.is_dir():
                            with z.open(zip_info) as xml_file:
                                try:
                                    xml_bytes = xml_file.read()
                                    datos = parsear_factura_xml(xml_bytes)
                                    facturas_db.append(datos)
                                    procesados.append(datos)
                                except Exception:
                                    errores += 1
            except Exception:
                errores += 1

    return {
        "mensaje": f"Se procesaron {len(procesados)} facturas correctamente.",
        "facturas_procesadas": procesados,
        "errores": errores,
        "total_facturas": len(facturas_db)
    }


@app.get("/api/exportar-excel")
async def exportar_excel():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Papel de Trabajo IVA"

    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    fill_header = PatternFill(start_color="1F3448", end_color="1F3448", fill_type="solid")
    font_bold = Font(name="Calibri", size=11, bold=True)
    border_thin = Border(
        left=Side(style='thin', color='DCE2E8'),
        right=Side(style='thin', color='DCE2E8'),
        top=Side(style='thin', color='DCE2E8'),
        bottom=Side(style='thin', color='DCE2E8')
    )

    ws.merge_cells("A1:G1")
    ws["A1"] = "IVA RÁPIDO — PAPEL DE TRABAJO CONTABLE Y DETERMINACIÓN DE IVA"
    ws["A1"].font = Font(name="Calibri", size=14, bold=True, color="1F3448")
    ws["A1"].alignment = Alignment(vertical="center")

    ws["A2"] = "Periodo Fiscal: Noviembre 2026"
    ws["A2"].font = Font(name="Calibri", size=10, italic=True, color="6C757D")

    headers = ["FECHA", "TIPO", "RFC EMISOR", "SUBTOTAL", "TASA IVA", "MONTO IVA", "ESTADO"]
    for col_num, header_title in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_num, value=header_title)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center" if col_num in [2, 5, 7] else "left")
        cell.border = border_thin

    row_idx = 5
    for f in facturas_db:
        ws.cell(row=row_idx, column=1, value=f["fecha"]).border = border_thin
        
        tipo_str = "Ingreso (Cobrado)" if f["tipo_comprobante"] == "I" else "Egreso (Pagado)"
        cell_tipo = ws.cell(row=row_idx, column=2, value=tipo_str)
        cell_tipo.alignment = Alignment(horizontal="center")
        cell_tipo.border = border_thin

        ws.cell(row=row_idx, column=3, value=f["rfc_emisor"]).border = border_thin
        
        cell_sub = ws.cell(row=row_idx, column=4, value=f["subtotal"])
        cell_sub.number_format = '"$"#,##0.00'
        cell_sub.border = border_thin
        
        cell_tasa = ws.cell(row=row_idx, column=5, value=f["tasa_iva"])
        cell_tasa.alignment = Alignment(horizontal="center")
        cell_tasa.border = border_thin

        cell_iva = ws.cell(row=row_idx, column=6, value=f["monto_iva"])
        cell_iva.number_format = '"$"#,##0.00'
        cell_iva.border = border_thin

        cell_st = ws.cell(row=row_idx, column=7, value=f["estatus"])
        cell_st.alignment = Alignment(horizontal="center")
        cell_st.border = border_thin
        
        row_idx += 1

    totales_row = max(row_idx, 5)
    ws.cell(row=totales_row, column=3, value="TOTALES:").font = font_bold
    
    cell_tot_sub = ws.cell(row=totales_row, column=4, value=f"=SUM(D5:D{totales_row-1})" if totales_row > 5 else 0)
    cell_tot_sub.font = font_bold
    cell_tot_sub.number_format = '"$"#,##0.00'
    
    cell_tot_iva = ws.cell(row=totales_row, column=6, value=f"=SUM(F5:F{totales_row-1})" if totales_row > 5 else 0)
    cell_tot_iva.font = font_bold
    cell_tot_iva.number_format = '"$"#,##0.00'

    col_widths = {'A': 14, 'B': 18, 'C': 18, 'D': 16, 'E': 12, 'F': 16, 'G': 14}
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            "Content-Disposition": "attachment; filename=Papel_de_Trabajo_IVA.xlsx"
        }
    )


@app.get("/api/exportar-pdf")
async def exportar_pdf():
    """
    Genera un dictamen de Liquidación Fiscal en PDF con maquetación ERP plano e institucional.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'ERPTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#1F3448')
    )
    meta_style = ParagraphStyle(
        'ERPMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#4A5568')
    )
    section_style = ParagraphStyle(
        'ERPSection',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#1F3448')
    )

    fecha_emision = datetime.now().strftime("%Y-%m-%d %H:%M")
    header_table_data = [
        [
            Paragraph("<b>IVA RÁPIDO — CÉDULA DE DETERMINACIÓN DE IVA</b>", title_style),
            Paragraph(f"<b>Emisión:</b> {fecha_emision}<br/><b>Periodo:</b> Noviembre 2026", meta_style)
        ]
    ]
    t_header = Table(header_table_data, colWidths=[380, 160])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, colors.HexColor('#1F3448'))
    ]))
    story.append(t_header)
    story.append(Spacer(1, 14))

    iva_trasladado = sum(f["monto_iva"] for f in facturas_db if f["tipo_comprobante"] == "I")
    iva_acreditable = sum(f["monto_iva"] for f in facturas_db if f["tipo_comprobante"] == "E")
    diferencia = iva_trasladado - iva_acreditable
    
    concepto_neto = "SALDO A PAGAR" if diferencia >= 0 else "SALDO A FAVOR"
    monto_neto = abs(diferencia)

    story.append(Paragraph("Resumen de Determinación de Impuesto Indirecto", section_style))
    story.append(Spacer(1, 6))

    summary_data = [
        ["CONCEPTO FISCAL", "TIPO IMPUESTO", "MONTO ACUMULADO"],
        ["IVA Trasladado", "Cobrado en Ingresos (CFDI 'I')", f"${iva_trasladado:,.2f}"],
        ["IVA Acreditable", "Pagado en Egresos (CFDI 'E')", f"${iva_acreditable:,.2f}"],
        [f"DETERMINACIÓN NETA", concepto_neto, f"${monto_neto:,.2f}"]
    ]

    t_summary = Table(summary_data, colWidths=[200, 200, 140])
    t_summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F3448')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#1F3448')),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#1F3448')),
        ('LINEBELOW', (0, -1), (-1, -1), 2, colors.HexColor('#1F3448')),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#E2E8F0'))
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 16))

    story.append(Paragraph("Libro de Comprobantes Fiscales Procesados", section_style))
    story.append(Spacer(1, 6))

    table_headers = [["FECHA", "TIPO", "RFC EMISOR", "SUBTOTAL", "TASA", "MONTO IVA", "ESTADO"]]
    table_rows = []
    
    for f in facturas_db:
        tipo_lbl = "Ingreso" if f["tipo_comprobante"] == "I" else "Egreso"
        table_rows.append([
            f["fecha"],
            tipo_lbl,
            f["rfc_emisor"],
            f"${f['subtotal']:,.2f}",
            f["tasa_iva"],
            f"${f['monto_iva']:,.2f}",
            f["estatus"]
        ])

    data_full = table_headers + (table_rows if table_rows else [["-", "-", "Sin registros", "$0.00", "-", "$0.00", "-"]])
    
    t_detail = Table(data_full, colWidths=[65, 55, 130, 95, 45, 85, 65])
    
    style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F3448')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('ALIGN', (4, 0), (4, -1), 'CENTER'),
        ('ALIGN', (5, 0), (5, -1), 'RIGHT'),
        ('ALIGN', (6, 0), (6, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DCE2E8'))
    ]

    for i in range(1, len(data_full)):
        if i % 2 == 0:
            style_commands.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#F8F9FA')))

    t_detail.setStyle(TableStyle(style_commands))
    story.append(t_detail)

    doc.build(story)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type='application/pdf',
        headers={
            "Content-Disposition": "attachment; filename=Cedula_Determinacion_IVA.pdf"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)