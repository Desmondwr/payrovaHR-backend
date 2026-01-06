from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from contracts.models import ContractTemplate
from accounts.models import EmployerProfile
from accounts.database_utils import get_tenant_database_alias
from io import BytesIO
from contracts.services import _basic_pdf_bytes

# Generic fallback body (used for non-PERMANENT types)
BASE_BODY = """
EMPLOYMENT CONTRACT

Created by:
{CO_NAME}
{CO_ADDRESS}, {CO_CITY}, {CO_COUNTRY}

Prepared for:
{EMP_FIRST} {EMP_LAST}
{EMP_ADDRESS}, {EMP_CITY}, {EMP_COUNTRY}

1. INTRODUCTION & RECITALS
This Employment Contract (“Agreement”) is entered into between {CO_NAME}, a company duly organized under the laws of {CO_COUNTRY}, with its principal place of business at {CO_ADDRESS}, {CO_CITY} (“Employer” or “Company”), and {EMP_FIRST} {EMP_LAST}, residing at {EMP_ADDRESS}, {EMP_CITY}, {EMP_COUNTRY} (“Employee”).

2. TERM & POSITION
Start Date: {START_DATE}; End Date: {END_DATE}
Role: {EMP_TITLE}; Location: {BRANCH_NAME} / {DEPARTMENT_NAME}; full effort, skill, and attention required; duties as assigned.

3. COMPENSATION & BENEFITS
Base Salary: {BASE_SALARY} {CURRENCY}, paid {PAY_FREQUENCY}.
Allowances: {ALLOWANCES}. Deductions: {DEDUCTIONS}.
Statutory taxes/withholdings apply. Benefits per Company policy and law.

4. CONFIDENTIALITY & INTELLECTUAL PROPERTY
Protect all Company confidential/proprietary info; do not misuse. All work product/IP created during employment belongs to {CO_NAME}.

5. NON-COMPETE & NON-SOLICITATION
For 12 months post-termination, do not solicit Company clients, employees, or contractors. Non-compete applies only as permitted by law.

6. TERMINATION
Either Party may terminate with {NOTICE_PERIOD} written notice unless immediate termination for gross misconduct/breach/legal grounds.

7. RETURN OF COMPANY PROPERTY
On termination, promptly return all Company property, data, documents, and equipment; retain no copies.

8. GOVERNING LAW
This Agreement is governed by the laws of {CO_COUNTRY}.

9. ENTIRE AGREEMENT & AMENDMENTS
Supersedes prior understandings; changes must be in writing and signed by both Parties.

10. SIGNATURES
For {CO_NAME}: __________________ Date: {SIGN_DATE_CO}
Employee ({EMP_FIRST} {EMP_LAST}): __________________ Date: {SIGN_DATE_EMP}
""".strip()

# Permanent-specific body provided by user
PERMANENT_BODY = """
PERMANENT (INDEFINITE) EMPLOYMENT CONTRACT

EMPLOYMENT CONTRACT (PERMANENT)

Created by:
{CO_NAME}
{CO_ADDRESS}, {CO_CITY}, {CO_COUNTRY}

Prepared for:
{EMP_FIRST} {EMP_LAST}
{EMP_ADDRESS}, {EMP_CITY}, {EMP_COUNTRY}

1. INTRODUCTION & RECITALS
This Employment Contract (“Agreement”) is entered into between {CO_NAME}, a company duly organized and existing under the laws of {CO_COUNTRY}, with its principal place of business at {CO_ADDRESS}, {CO_CITY} (“Employer” or “Company”), and {EMP_FIRST} {EMP_LAST}, residing at {EMP_ADDRESS}, {EMP_CITY}, {EMP_COUNTRY} (“Employee”).
WHEREAS, the Company desires to employ the Employee in a permanent capacity; and
WHEREAS, the Employee desires to accept such employment under the terms and conditions set forth herein;
NOW, THEREFORE, in consideration of the mutual covenants herein, the Parties agree as follows:

2. TERM OF EMPLOYMENT
Employment shall commence on {START_DATE} (“Start Date”) and shall continue for an indefinite period unless terminated in accordance with this Agreement or applicable law.
Nothing in this Agreement shall be construed as guaranteeing employment for a specific duration.

3. POSITION & DUTIES
The Employee is employed as {EMP_TITLE} and shall perform all duties customarily associated with this position, including duties reasonably assigned by the Company.
The Employee shall report to the manager designated by the Company and shall perform duties at {BRANCH_NAME} / {DEPARTMENT_NAME}, or such other location as reasonably required.
The Employee agrees to devote full professional effort, skill, and attention to the performance of duties.

4. COMPENSATION & BENEFITS
Base Salary: {BASE_SALARY} {CURRENCY}, paid {PAY_FREQUENCY}.
Allowances: {ALLOWANCES}.
Deductions: {DEDUCTIONS}.
All statutory taxes and withholdings apply.
Employee shall be entitled to benefits, leave, and entitlements in accordance with Company policy and applicable law.

5. PROBATION
The Employee shall be subject to a probation period of {PROBATION_PERIOD}, during which employment may be terminated with reduced notice as permitted by law.

6. CONFIDENTIALITY & INTELLECTUAL PROPERTY
The Employee shall not disclose or misuse confidential or proprietary information during or after employment.
All inventions, work product, discoveries, and intellectual property created during employment shall be the exclusive property of {CO_NAME}.

7. NON-COMPETE & NON-SOLICITATION
For 12 months following termination, the Employee shall not solicit Company clients, employees, or contractors.
Any non-compete obligations shall apply only to the extent permitted by law.

8. TERMINATION
Either Party may terminate this Agreement by providing {NOTICE_PERIOD} written notice.
Immediate termination may occur for gross misconduct, breach, or legal grounds.

9. RETURN OF COMPANY PROPERTY
Upon termination, all Company property, data, documents, and equipment must be returned immediately.

10. GOVERNING LAW
This Agreement shall be governed by the laws of {CO_COUNTRY}.

11. ENTIRE AGREEMENT & AMENDMENTS
This Agreement constitutes the entire agreement and supersedes all prior understandings.
Amendments must be in writing and signed by both Parties.

12. SIGNATURES
For {CO_NAME}: __________________ Date: {SIGN_DATE_CO}
Employee ({EMP_FIRST} {EMP_LAST}): __________________ Date: {SIGN_DATE_EMP}
""".strip()

FIXED_TERM_BODY = """
FIXED-TERM EMPLOYMENT CONTRACT

EMPLOYMENT CONTRACT (FIXED-TERM)

Created by:
{CO_NAME}
{CO_ADDRESS}, {CO_CITY}, {CO_COUNTRY}

Prepared for:
{EMP_FIRST} {EMP_LAST}
{EMP_ADDRESS}, {EMP_CITY}, {EMP_COUNTRY}

1. INTRODUCTION & RECITALS
This Employment Contract (“Agreement”) is entered into between {CO_NAME}, a company duly organized and existing under the laws of {CO_COUNTRY}, with its principal place of business at {CO_ADDRESS}, {CO_CITY} (“Employer” or “Company”), and {EMP_FIRST} {EMP_LAST}, residing at {EMP_ADDRESS}, {EMP_CITY}, {EMP_COUNTRY} (“Employee”).
WHEREAS, the Company desires to employ the Employee on a fixed-term basis; and
WHEREAS, the Employee desires to accept such employment under the terms and conditions set forth herein;
NOW, THEREFORE, in consideration of the mutual covenants herein, the Parties agree as follows:

2. TERM OF EMPLOYMENT
Employment shall commence on {START_DATE} and shall automatically terminate on {END_DATE}, unless renewed in writing by the Parties.
Nothing herein creates any expectation of renewal or continued employment beyond the fixed term.

3. POSITION & DUTIES
The Employee is employed as {EMP_TITLE} and shall perform all duties customarily associated with this position, including duties reasonably assigned by the Company.
The Employee shall report to the manager designated by the Company and shall perform duties at {BRANCH_NAME} / {DEPARTMENT_NAME}, or such other location as reasonably required.
The Employee agrees to devote full professional effort, skill, and attention to the performance of duties.

4. COMPENSATION & BENEFITS
Base Salary: {BASE_SALARY} {CURRENCY}, paid {PAY_FREQUENCY}.
Allowances: {ALLOWANCES}.
Deductions: {DEDUCTIONS}.
All statutory taxes and withholdings apply.
Employee shall be entitled to benefits, leave, and entitlements in accordance with Company policy and applicable law.

5. PROBATION
The Employee may be subject to a probation period of {PROBATION_PERIOD}, during which employment may be terminated with reduced notice as permitted by law.

6. CONFIDENTIALITY & INTELLECTUAL PROPERTY
The Employee shall not disclose or misuse confidential or proprietary information during or after employment.
All inventions, work product, discoveries, and intellectual property created during employment shall be the exclusive property of {CO_NAME}.

7. NON-COMPETE & NON-SOLICITATION
For 12 months following termination, the Employee shall not solicit Company clients, employees, or contractors.
Any non-compete obligations shall apply only to the extent permitted by law.

8. TERMINATION
Either Party may terminate this Agreement by providing {NOTICE_PERIOD} written notice, subject to the fixed end date.
Immediate termination may occur for gross misconduct, breach, or legal grounds.

9. RETURN OF COMPANY PROPERTY
Upon termination, all Company property, data, documents, and equipment must be returned immediately.

10. GOVERNING LAW
This Agreement shall be governed by the laws of {CO_COUNTRY}.

11. ENTIRE AGREEMENT & AMENDMENTS
This Agreement constitutes the entire agreement and supersedes all prior understandings.
Amendments must be in writing and signed by both Parties.

12. SIGNATURES
For {CO_NAME}: __________________ Date: {SIGN_DATE_CO}
Employee ({EMP_FIRST} {EMP_LAST}): __________________ Date: {SIGN_DATE_EMP}
""".strip()


CONTRACT_TYPES = [
    ("PERMANENT", "Default Permanent Contract", "default_permanent.pdf"),
    ("FIXED_TERM", "Default Fixed-Term Contract", "default_fixed_term.pdf"),
    ("INTERNSHIP", "Default Internship Contract", "default_internship.pdf"),
    ("CONSULTANT", "Default Consultant Contract", "default_consultant.pdf"),
    ("PART_TIME", "Default Part-Time Contract", "default_part_time.pdf"),
]

TYPE_BODIES = {
    "PERMANENT": PERMANENT_BODY,
    "FIXED_TERM": FIXED_TERM_BODY,
    "PART_TIME": """
PART-TIME EMPLOYMENT CONTRACT

EMPLOYMENT CONTRACT (PART-TIME)

Created by:
{CO_NAME}
{CO_ADDRESS}, {CO_CITY}, {CO_COUNTRY}

Prepared for:
{EMP_FIRST} {EMP_LAST}
{EMP_ADDRESS}, {EMP_CITY}, {EMP_COUNTRY}

1. INTRODUCTION & RECITALS
This Employment Contract (“Agreement”) is entered into between {CO_NAME}, a company duly organized and existing under the laws of {CO_COUNTRY}, with its principal place of business at {CO_ADDRESS}, {CO_CITY} (“Employer” or “Company”), and {EMP_FIRST} {EMP_LAST}, residing at {EMP_ADDRESS}, {EMP_CITY}, {EMP_COUNTRY} (“Employee”).
WHEREAS, the Company desires to employ the Employee on a part-time basis; and
WHEREAS, the Employee desires to accept such employment under the terms and conditions set forth herein;
NOW, THEREFORE, in consideration of the mutual covenants herein, the Parties agree as follows:

2. TERM OF EMPLOYMENT
Employment shall commence on {START_DATE}. End Date (if applicable): {END_DATE}.

3. POSITION & WORK SCHEDULE
The Employee is employed as {EMP_TITLE} and shall perform duties customarily associated with this position, including duties reasonably assigned by the Company.
The Employee shall work approximately {HOURS_PER_WEEK} hours per week, with schedule determined by the Company (subject to reasonable flexibility).
The Employee shall report to the manager designated by the Company and shall perform duties at {BRANCH_NAME} / {DEPARTMENT_NAME}, or such other location as reasonably required.
Compensation and benefits are pro-rated in accordance with hours worked and applicable law.

4. COMPENSATION & BENEFITS
Base Salary: {BASE_SALARY} {CURRENCY}, paid {PAY_FREQUENCY}.
Allowances: {ALLOWANCES}.
Deductions: {DEDUCTIONS}.
All statutory taxes and withholdings apply.
Employee shall be entitled to benefits, leave, and entitlements per Company policy and law, on a pro-rated basis where applicable.

5. PROBATION
The Employee may be subject to a probation period of {PROBATION_PERIOD}, during which employment may be terminated with reduced notice as permitted by law.

6. CONFIDENTIALITY & INTELLECTUAL PROPERTY
The Employee shall not disclose or misuse confidential or proprietary information during or after employment.
All inventions, work product, discoveries, and intellectual property created during employment shall be the exclusive property of {CO_NAME}.

7. NON-COMPETE & NON-SOLICITATION
For 12 months following termination, the Employee shall not solicit Company clients, employees, or contractors.
Any non-compete obligations shall apply only to the extent permitted by law.

8. TERMINATION
Either Party may terminate this Agreement by providing {NOTICE_PERIOD} written notice.
Immediate termination may occur for gross misconduct, breach, or legal grounds.

9. RETURN OF COMPANY PROPERTY
Upon termination, all Company property, data, documents, and equipment must be returned immediately.

10. GOVERNING LAW
This Agreement shall be governed by the laws of {CO_COUNTRY}.

11. ENTIRE AGREEMENT & AMENDMENTS
This Agreement constitutes the entire agreement and supersedes all prior understandings.
Amendments must be in writing and signed by both Parties.

12. SIGNATURES
For {CO_NAME}: __________________ Date: {SIGN_DATE_CO}
Employee ({EMP_FIRST} {EMP_LAST}): __________________ Date: {SIGN_DATE_EMP}
""".strip(),
    "INTERNSHIP": """
INTERNSHIP AGREEMENT

Created by:
{CO_NAME}
{CO_ADDRESS}, {CO_CITY}, {CO_COUNTRY}

Prepared for:
{EMP_FIRST} {EMP_LAST}
{EMP_ADDRESS}, {EMP_CITY}, {EMP_COUNTRY}

1. INTRODUCTION & RECITALS
This Internship Agreement (“Agreement”) is entered into between {CO_NAME}, a company duly organized and existing under the laws of {CO_COUNTRY}, with its principal place of business at {CO_ADDRESS}, {CO_CITY} (“Company”), and {EMP_FIRST} {EMP_LAST}, residing at {EMP_ADDRESS}, {EMP_CITY}, {EMP_COUNTRY} (“Intern”).

2. TERM
This Internship shall commence on {START_DATE} and end on {END_DATE}, unless terminated earlier. This Agreement does not create an employment relationship beyond the internship period, nor does it imply any guarantee of future employment.

3. TRAINING & SUPERVISION
The Intern shall perform duties under the supervision of a designated mentor and participate in learning activities. The Intern will carry out assigned tasks at {BRANCH_NAME} / {DEPARTMENT_NAME} or other locations as reasonably required. No promise of continued employment is made or implied.

4. COMPENSATION & BENEFITS
Base/Stipend: {BASE_SALARY} {CURRENCY}, paid {PAY_FREQUENCY} (if applicable).
Allowances: {ALLOWANCES}. Deductions: {DEDUCTIONS}. Statutory withholdings apply where applicable.
Any benefits or leave entitlements are limited to those expressly provided by Company policy and applicable law for interns.

5. CONFIDENTIALITY & INTELLECTUAL PROPERTY
The Intern shall not disclose or misuse confidential or proprietary information during or after the internship. All work product, inventions, and intellectual property created in the course of the internship are the exclusive property of {CO_NAME}.

6. NON-COMPETE & NON-SOLICITATION
For 12 months following the end of the internship, the Intern shall not solicit Company clients, employees, or contractors. Any non-compete obligations apply only to the extent permitted by law.

7. TERMINATION
Either Party may terminate this Agreement by providing {NOTICE_PERIOD} written notice. Immediate termination may occur for gross misconduct, breach, or legal grounds.

8. RETURN OF COMPANY PROPERTY
Upon termination or conclusion of the internship, all Company property, data, documents, and equipment must be returned immediately.

9. GOVERNING LAW
This Agreement shall be governed by the laws of {CO_COUNTRY}.

10. ENTIRE AGREEMENT & AMENDMENTS
This Agreement constitutes the entire agreement and supersedes all prior understandings. Amendments must be in writing and signed by both Parties.

11. SIGNATURES
For {CO_NAME}: __________________ Date: {SIGN_DATE_CO}
Intern ({EMP_FIRST} {EMP_LAST}): __________________ Date: {SIGN_DATE_EMP}
""".strip(),
    "CONSULTANT": """
CONSULTING AGREEMENT

Created by:
{CO_NAME}
{CO_ADDRESS}, {CO_CITY}, {CO_COUNTRY}

Prepared for:
{EMP_FIRST} {EMP_LAST}
{EMP_ADDRESS}, {EMP_CITY}, {EMP_COUNTRY}

1. INTRODUCTION & RECITALS
This Consulting Agreement (“Agreement”) is entered into between {CO_NAME}, a company duly organized and existing under the laws of {CO_COUNTRY}, with its principal place of business at {CO_ADDRESS}, {CO_CITY} (“Company”), and {EMP_FIRST} {EMP_LAST}, residing at {EMP_ADDRESS}, {EMP_CITY}, {EMP_COUNTRY} (“Consultant”).

2. INDEPENDENT CONTRACTOR STATUS
The Consultant is an independent contractor, not an employee. No employment benefits apply. The Consultant is responsible for all taxes, insurance, and statutory obligations.

3. SERVICES & DELIVERABLES
The Consultant shall provide professional services as agreed, subject to project scope and deliverables defined by the Parties. Location: {BRANCH_NAME} / {DEPARTMENT_NAME} or as mutually agreed. No guarantee of future engagements is implied.

4. FEES & PAYMENT
Fees: {BASE_SALARY} {CURRENCY}
Billing cadence: {PAY_FREQUENCY}
Invoices payable per agreed terms. Statutory withholdings, if any, as required by law.

5. CONFIDENTIALITY & IP OWNERSHIP
The Consultant shall not disclose or misuse Company confidential/proprietary information during or after the engagement. All deliverables and work product become the exclusive property of {CO_NAME} upon payment.

6. NON-SOLICITATION
For 12 months following termination, the Consultant shall not solicit Company clients, employees, or contractors. Any non-compete applies only to the extent permitted by law.

7. TERM & TERMINATION
Start Date: {START_DATE}; End Date (if applicable): {END_DATE}.
Either Party may terminate this Agreement by providing {NOTICE_PERIOD} written notice, subject to any project-specific terms. Immediate termination may occur for material breach or legal grounds.

8. RETURN OF COMPANY PROPERTY
Upon termination, all Company property, data, documents, and equipment must be returned immediately.

9. GOVERNING LAW
This Agreement shall be governed by the laws of {CO_COUNTRY}.

10. ENTIRE AGREEMENT & AMENDMENTS
This Agreement constitutes the entire agreement and supersedes all prior understandings. Amendments must be in writing and signed by both Parties.

11. SIGNATURES
For {CO_NAME}: __________________ Date: {SIGN_DATE_CO}
Consultant ({EMP_FIRST} {EMP_LAST}): __________________ Date: {SIGN_DATE_EMP}
""".strip(),
}


class Command(BaseCommand):
    help = 'Creates default contract templates (one per contract type) for each employer.'

    def render_pdf(self, title: str, body: str) -> ContentFile:
        """
        Render a simple PDF from plain text using reportlab if available.
        Falls back to a minimal PDF built with stdlib when reportlab is unavailable.
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            return ContentFile(_basic_pdf_bytes(title, body))

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 50
        # Write title
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, title)
        y -= 20
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

    def handle(self, *args, **options):
        employers = EmployerProfile.objects.all()

        for employer in employers:
            tenant_db = get_tenant_database_alias(employer)

            # Ensure tenant DB is loaded
            from django.conf import settings
            if tenant_db not in settings.DATABASES:
                default_config = settings.DATABASES['default'].copy()
                default_config['NAME'] = employer.database_name
                settings.DATABASES[tenant_db] = default_config

            for contract_type, template_name, filename in CONTRACT_TYPES:
                # Skip if a default already exists for this type
                exists = ContractTemplate.objects.using(tenant_db).filter(
                    employer_id=employer.id,
                    contract_type=contract_type,
                    is_default=True
                ).exists()
                if exists:
                    self.stdout.write(f"Default template already exists for {employer.company_name} [{contract_type}]")
                    continue

                body = TYPE_BODIES.get(contract_type, BASE_BODY)

                title = f'{contract_type} EMPLOYMENT CONTRACT'
                content = self.render_pdf(title, body)
                template = ContractTemplate(
                    employer_id=employer.id,
                    name=template_name,
                    contract_type=contract_type,
                    is_default=True
                )
                template.file.save(filename, content, save=False)
                template.save(using=tenant_db)
                self.stdout.write(self.style.SUCCESS(f"Created default template for {employer.company_name} [{contract_type}]"))

        self.stdout.write(self.style.SUCCESS('Successfully seeded default templates.'))
