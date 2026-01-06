import os
from io import BytesIO
from django.core.files.base import ContentFile
from django.utils import timezone
from .models import Contract, ContractTemplate, ContractDocument
from accounts.models import EmployerProfile


def _basic_pdf_bytes(title: str, body: str) -> bytes:
    """Generate a minimal, standards-compliant PDF using only the stdlib (no third-party deps)."""
    def esc(text: str) -> str:
        return (
            text.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("\r", "")
            .replace("\n", "")
        )

    lines = [title, ""] + body.split("\n")
    y = 770  # start near top of letter-sized page
    ops = []
    first = True
    for line in lines:
        if y < 60:
            break
        font_size = 14 if first else 11
        ops.append(f"BT /F1 {font_size} Tf 50 {y} Td ({esc(line)}) Tj ET")
        y -= 18
        first = False

    content = "\n".join(ops).encode("utf-8")

    pdf = bytearray()
    pdf.extend(b"%PDF-1.4\n")
    offsets = []

    def add(obj_bytes: bytes):
        offsets.append(len(pdf))
        pdf.extend(obj_bytes)
        if not pdf.endswith(b"\n"):
            pdf.extend(b"\n")

    add(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    add(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    add(
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )
    add(
        b"4 0 obj\n<< /Length "
        + str(len(content)).encode("ascii")
        + b" >>\nstream\n"
        + content
        + b"\nendstream\nendobj\n"
    )
    add(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)+1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets:
        pdf.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        b"trailer\n<< /Size "
        + str(len(offsets) + 1).encode("ascii")
        + b" /Root 1 0 R >>\n"
    )
    pdf.extend(b"startxref\n" + str(xref_start).encode("ascii") + b"\n%%EOF\n")
    return bytes(pdf)


def generate_contract_pdf(contract, template=None):
    """
    Generates a PDF contract document based on a template.
    
    Args:
        contract (Contract): The contract instance.
        template (ContractTemplate, optional): Specific template to use. 
                                              If None, finds default for contract type.
                                              
    Returns:
        ContractDocument: The generated document object.
        
    Raises:
        ValueError: If no template found.
        ImportError: If python-docx is not installed.
    """
    
    
    # Check dependencies (Optional - we handle import error later for fallback)
    # try:
    #     from docx import Document
    #     from docx.shared import Pt
    # except ImportError:
    #     pass 


    # 1. Resolve Template
    if not template:
        # Resolve default template for this type (ignore stale config overrides)
        db_alias = contract._state.db or 'default'
        template = (
            ContractTemplate.objects.using(db_alias)
            .filter(employer_id=contract.employer_id, contract_type=contract.contract_type, is_default=True)
            .order_by('-created_at')
            .first()
        )
        if not template:
            raise ValueError(f"No default template found for contract type {contract.contract_type}")

    # 2. Prepare Context (placeholder-style strings for templating)
    employer_profile = EmployerProfile.objects.using('default').get(id=contract.employer_id)

    try:
        employee_obj = contract.employee
    except Exception:
        employee_obj = None

    try:
        branch_obj = contract.branch
    except Exception:
        branch_obj = None
    try:
        department_obj = contract.department
    except Exception:
        department_obj = None

    allowances_list = [f"{a.name}: {a.amount} ({a.type})" for a in contract.allowances.all()]
    deductions_list = [f"{d.name}: {d.amount} ({d.type})" for d in contract.deductions.all()]

    context = {
        '{CO_NAME}': employer_profile.company_name,
        '{CO_ADDRESS}': getattr(employer_profile, 'physical_address', '') or '',
        '{CO_CITY}': getattr(employer_profile, 'company_location', '') or '',
        '{CO_COUNTRY}': getattr(employer_profile, 'country', '') or '',
        '{EMP_FIRST}': getattr(employee_obj, 'first_name', '') or '',
        '{EMP_LAST}': getattr(employee_obj, 'last_name', '') or '',
        '{EMP_TITLE}': getattr(employee_obj, 'job_title', '') or 'Employee',
        '{EMP_ADDRESS}': getattr(employee_obj, 'address', '') or '',
        '{EMP_CITY}': getattr(employee_obj, 'city', '') or '',
        '{EMP_COUNTRY}': getattr(employee_obj, 'country', '') or '',
        '{BRANCH_NAME}': getattr(branch_obj, 'name', '') or '',
        '{DEPARTMENT_NAME}': getattr(department_obj, 'name', '') or '',
        '{START_DATE}': contract.start_date.strftime('%Y-%m-%d') if contract.start_date else '',
        '{END_DATE}': contract.end_date.strftime('%Y-%m-%d') if contract.end_date else '',
        '{BASE_SALARY}': f"{contract.base_salary}",
        '{CURRENCY}': contract.currency,
        '{PAY_FREQUENCY}': contract.pay_frequency,
        '{ALLOWANCES}': "; ".join(allowances_list) if allowances_list else "None",
        '{DEDUCTIONS}': "; ".join(deductions_list) if deductions_list else "None",
        '{PROBATION_PERIOD}': getattr(contract, 'probation_period', '') if hasattr(contract, 'probation_period') else '',
        '{NOTICE_PERIOD}': getattr(contract, 'notice_period', '') if hasattr(contract, 'notice_period') else '',
        '{HOURS_PER_WEEK}': getattr(contract, 'hours_per_week', '') if hasattr(contract, 'hours_per_week') else '',
        '{SIGN_DATE_CO}': timezone.now().strftime('%Y-%m-%d'),
        '{SIGN_DATE_EMP}': timezone.now().strftime('%Y-%m-%d'),
    }

    def render_pdf_from_body(title: str, body: str) -> ContentFile:
        """Render a simple PDF using reportlab with placeholder substitution."""
        for key, val in context.items():
            body = body.replace(key, str(val))
            title = title.replace(key, str(val))
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            # Fallback to a minimal PDF built with stdlib to avoid broken files
            return ContentFile(_basic_pdf_bytes(title, body))

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 50
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, title)
        y -= 24
        c.setFont("Helvetica", 10)
        for para in body.split("\n\n"):
            for line in para.split("\n"):
                if y < 50:
                    c.showPage()
                    y = height - 50
                    c.setFont("Helvetica", 10)
                c.drawString(50, y, line.strip())
                y -= 14
            y -= 8
        c.showPage()
        c.save()
        buffer.seek(0)
        return ContentFile(buffer.getvalue())

    # 3. Load and Process DOCX
    # We need to read the file from the template.file (FieldFile)
    
    db_alias = contract._state.db or 'default'

    ext = (template.file.name or '').lower()
    if ext.endswith('.pdf'):
        # Always render a fresh PDF with merged context (do not reuse raw template bytes).
        try:
            from contracts.management.commands.seed_contract_template import TYPE_BODIES, BASE_BODY
            body_text = TYPE_BODIES.get(contract.contract_type, BASE_BODY)
        except Exception:
            body_text = ""
        content_file = render_pdf_from_body(f'{contract.contract_type} CONTRACT', body_text or "Contract")
        file_name = f"Contract_{contract.contract_id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    else:
        # DOCX path with python-docx
        try:
            from docx import Document
            
            template.file.open('rb')
            doc = Document(template.file)
            template.file.close() # Good practice

            # Helper to replace text in runs (preserves formatting)
            def replace_text_in_paragraph(paragraph, key, value):
                if key in paragraph.text:
                    paragraph.text = paragraph.text.replace(key, str(value))

            for paragraph in doc.paragraphs:
                for key, value in context.items():
                    if key in paragraph.text:
                        replace_text_in_paragraph(paragraph, key, value)

            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                             for key, value in context.items():
                                if key in paragraph.text:
                                    replace_text_in_paragraph(paragraph, key, value)
                                    
            docx_io = BytesIO()
            doc.save(docx_io)
            docx_io.seek(0)
            content_file = ContentFile(docx_io.getvalue())
            file_name = f"Contract_{contract.contract_id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.docx"
        except ImportError:
            # Fallback if python-docx missing: render a simple PDF from body
            from contracts.management.commands.seed_contract_template import TYPE_BODIES, BASE_BODY
            body_text = TYPE_BODIES.get(contract.contract_type, BASE_BODY)
            content_file = render_pdf_from_body(f'{contract.contract_type} CONTRACT', body_text)
            file_name = f"Contract_{contract.contract_id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        except Exception as e:
            raise ValueError(f"Could not open template file: {e}")

    # Remove previous generated docs (and their files) to avoid stale/corrupted files
    old_docs = ContractDocument.objects.using(db_alias).filter(contract=contract)
    for old in old_docs:
        if old.file:
            old.file.delete(save=False)
        old.delete()

    doc_obj = ContractDocument(
        contract=contract,
        generated_from=template,
        name=file_name
    )
    doc_obj.file.save(file_name, content_file, save=False)
    doc_obj.save(using=db_alias)
    return doc_obj
