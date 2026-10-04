"""Generate identical Markdown/PDF summaries from submission_details.json."""
import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',help='PDF path; default is next to project folder')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    data=json.loads((root/'submission_details.json').read_text(encoding='utf-8'))
    draft=data['status']!='final'
    title='TicketPilot - Assignment Submission'
    warning='DRAFT - REQUIRED LIVE EVIDENCE PENDING' if draft else 'FINAL SUBMISSION SUMMARY'
    md=f'# {title}\n\n**{warning}**\n\n'
    md+='\n'.join(f'- **{label}:** {value}' for label,value in data['fields'])+'\n'
    (root/'SUBMISSION.md').write_text(md,encoding='utf-8')
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    green=colors.HexColor('#17694f'); ink=colors.HexColor('#172f2e')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleCustom',fontName='Helvetica-Bold',fontSize=25,leading=30,textColor=ink,spaceAfter=9))
    styles.add(ParagraphStyle(name='Kicker',fontName='Helvetica-Bold',fontSize=9,leading=13,textColor=green,spaceAfter=9))
    styles.add(ParagraphStyle(name='SmallLabel',fontName='Helvetica-Bold',fontSize=8.5,leading=12,textColor=ink))
    styles.add(ParagraphStyle(name='FieldValue',fontName='Helvetica',fontSize=9,leading=12,textColor=ink,splitLongWords=True))
    styles.add(ParagraphStyle(name='NoteCustom',fontName='Helvetica',fontSize=9,leading=13,textColor=ink,spaceAfter=10))
    out=Path(args.output) if args.output else root.parent/'i221296_submission.pdf'
    doc=SimpleDocTemplate(str(out),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=45)
    story=[Paragraph('AGENT ARENA / ASSIGNMENT 1',styles['Kicker']),Paragraph('TicketPilot',styles['TitleCustom']),
           Paragraph('Eraj Zaman  |  i221296',styles['NoteCustom']),
           Paragraph(warning,styles['Kicker'])]
    if draft:
        story.append(Paragraph('The source implementation and offline evidence are available. Provider access, measured model comparison, repository access and public deployment remain pending. This is not a completed Classroom submission.',styles['NoteCustom']))
    def table(fields):
        rows=[]
        for label,value in fields:
            rendered=escape(value)
            if value.startswith('https://'):
                rendered=f'<link href="{escape(value)}" color="#17694f">{escape(value)}</link>'
            rows.append([Paragraph(escape(label),styles['SmallLabel']),Paragraph(rendered,styles['FieldValue'])])
        t=Table(rows,colWidths=[150,361],hAlign='LEFT')
        t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),
            ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
            ('LINEBELOW',(0,0),(-1,-1),0.4,colors.HexColor('#dce5e0')),
            ('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.white,colors.HexColor('#f6f8f3')])]))
        return t
    story.append(table(data['fields'][:14]))
    story += [PageBreak(),Paragraph('Runtime & verification',styles['TitleCustom']),Paragraph(warning,styles['Kicker']),table(data['fields'][14:])]
    def footer(canvas,doc):
        canvas.saveState();canvas.setStrokeColor(colors.HexColor('#dce5e0'));canvas.line(42,34,553,34)
        canvas.setFont('Helvetica',8);canvas.setFillColor(ink)
        canvas.drawString(42,22,'TicketPilot  /  Eraj Zaman  /  i221296')
        canvas.drawRightString(553,22,f'{doc.page}');canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    print(str(out))

if __name__=='__main__': main()
