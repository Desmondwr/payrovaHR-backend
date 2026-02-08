from datetime import date, datetime, time as dtime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import EmployerProfile
from contracts.models import Contract
from employees.models import Employee
from payroll.models import (
    Advantage,
    CalculationBasis,
    CalculationBasisAdvantage,
    CalculationScale,
    Deduction,
    PayrollConfiguration,
    PayrollElement,
    Salary,
    ScaleRange,
    SalaryDeduction,
)
from payroll.services import PayrollCalculationService, REQUIRED_BASIS_CODES, validate_payroll
from timeoff.models import TimeOffConfiguration, TimeOffRequest, TimeOffType
from treasury.models import BankAccount, CashDesk, PaymentBatch, PaymentLine


class PayrollFeatureTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="owner@acme.test",
            password="test-pass",
            is_employer=True,
            is_employer_owner=True,
        )
        self.employer = EmployerProfile.objects.create(
            user=self.user,
            company_name="Acme Payroll",
            employer_name_or_group="Acme",
            organization_type="PRIVATE",
            industry_sector="Tech",
            date_of_incorporation=date.today(),
            company_location="City",
            physical_address="123 Street",
            phone_number="1234567890",
            official_company_email="hr@acme.test",
            rccm="rccm",
            taxpayer_identification_number="tin",
            cnps_employer_number="cnps",
            labour_inspectorate_declaration="decl",
            business_license="license",
            bank_name="Bank",
            bank_account_number="123",
        )
        self.employee = Employee.objects.create(
            employer_id=self.employer.id,
            employee_id="EMP-1",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            job_title="Engineer",
            employment_type="FULL_TIME",
            employment_status="ACTIVE",
            hire_date=date.today(),
        )
        self.config = PayrollConfiguration.objects.create(
            employer_id=self.employer.id,
            rounding_scale=2,
        )
        for code in REQUIRED_BASIS_CODES:
            CalculationBasis.objects.create(employer_id=self.employer.id, code=code, name=code)

    def _create_contract(self, base_salary=Decimal("1000.00")):
        return Contract.objects.create(
            employer_id=self.employer.id,
            contract_id=f"CNT-{timezone.now().timestamp()}",
            employee=self.employee,
            contract_type="PERMANENT",
            start_date=date(self._year, self._month, 1),
            status="ACTIVE",
            base_salary=base_salary,
            currency="XAF",
            pay_frequency="MONTHLY",
            created_by=1,
        )

    def _add_basis_membership(self, basis_code, advantage):
        basis = CalculationBasis.objects.get(employer_id=self.employer.id, code=basis_code)
        CalculationBasisAdvantage.objects.create(
            employer_id=self.employer.id,
            basis=basis,
            advantage=advantage,
        )

    def test_element_month_year_filter(self):
        self._year = 2026
        self._month = 5
        basic = Advantage.objects.create(
            employer_id=self.employer.id,
            code="BASIC",
            name="Basic Salary",
            sys_code="BASIC_SALARY",
            is_manual=False,
        )
        bonus = Advantage.objects.create(
            employer_id=self.employer.id,
            code="BONUS",
            name="Bonus",
            is_manual=True,
        )
        for code in ["SAL-BRUT", "SAL-BRUT-TAX", "SAL-BRUT-TAX-IRPP"]:
            self._add_basis_membership(code, basic)
        self._add_basis_membership("SAL-BRUT", bonus)

        contract = self._create_contract()
        PayrollElement.objects.create(
            employer_id=self.employer.id,
            contract=contract,
            advantage=basic,
            amount=Decimal("1000.00"),
            month="__",
            year="__",
        )
        PayrollElement.objects.create(
            employer_id=self.employer.id,
            contract=contract,
            advantage=bonus,
            amount=Decimal("200.00"),
            month="05",
            year="2026",
        )

        service = PayrollCalculationService(
            employer_id=self.employer.id, year=2026, month=5, tenant_db="default"
        )
        results = service.run(mode=Salary.STATUS_SIMULATED)
        self.assertEqual(len(results), 1)
        salary = results[0].salary
        self.assertEqual(salary.gross_salary, Decimal("1200.00"))

        service_june = PayrollCalculationService(
            employer_id=self.employer.id, year=2026, month=6, tenant_db="default"
        )
        results_june = service_june.run(mode=Salary.STATUS_SIMULATED)
        salary_june = results_june[0].salary
        self.assertEqual(salary_june.gross_salary, Decimal("1000.00"))

    def test_rate_deduction(self):
        self._year = 2026
        self._month = 5
        basic = Advantage.objects.create(
            employer_id=self.employer.id,
            code="BASIC",
            name="Basic Salary",
            sys_code="BASIC_SALARY",
            is_manual=False,
        )
        self._add_basis_membership("SAL-BRUT", basic)
        self._add_basis_membership("SAL-BRUT-TAX", basic)
        self._add_basis_membership("SAL-BRUT-TAX-IRPP", basic)

        deduction = Deduction.objects.create(
            employer_id=self.employer.id,
            code="PVID",
            name="PVID",
            sys_code="PVID",
            is_employee=True,
            is_employer=False,
            is_count=True,
            calculation_basis_code="SAL-BRUT",
            employee_rate=Decimal("10.00"),
            is_rate=True,
        )

        contract = self._create_contract()
        PayrollElement.objects.create(
            employer_id=self.employer.id,
            contract=contract,
            advantage=basic,
            amount=Decimal("1000.00"),
        )
        PayrollElement.objects.create(
            employer_id=self.employer.id,
            contract=contract,
            deduction=deduction,
            amount=Decimal("0.00"),
        )

        service = PayrollCalculationService(
            employer_id=self.employer.id, year=2026, month=5, tenant_db="default"
        )
        results = service.run(mode=Salary.STATUS_SIMULATED)
        salary = results[0].salary
        line = SalaryDeduction.objects.filter(salary=salary, code="PVID").first()
        self.assertIsNotNone(line)
        self.assertEqual(line.amount, Decimal("100.00"))

    def test_scale_deduction(self):
        self._year = 2026
        self._month = 5
        basic = Advantage.objects.create(
            employer_id=self.employer.id,
            code="BASIC",
            name="Basic Salary",
            sys_code="BASIC_SALARY",
            is_manual=False,
        )
        self._add_basis_membership("SAL-BRUT", basic)
        self._add_basis_membership("SAL-BRUT-TAX", basic)
        self._add_basis_membership("SAL-BRUT-TAX-IRPP", basic)

        scale = CalculationScale.objects.create(
            employer_id=self.employer.id,
            code="TEST",
            name="Test Scale",
        )
        ScaleRange.objects.create(
            employer_id=self.employer.id,
            scale=scale,
            range_min=Decimal("0.00"),
            range_max=Decimal("2000.00"),
            coefficient=Decimal("5.00"),
            position=1,
        )
        deduction = Deduction.objects.create(
            employer_id=self.employer.id,
            code="SCALE",
            name="Scale Deduction",
            is_employee=True,
            calculation_basis_code="SAL-BRUT",
            scale=scale,
            is_scale=True,
        )

        contract = self._create_contract()
        PayrollElement.objects.create(
            employer_id=self.employer.id,
            contract=contract,
            advantage=basic,
            amount=Decimal("1000.00"),
        )
        PayrollElement.objects.create(
            employer_id=self.employer.id,
            contract=contract,
            deduction=deduction,
            amount=Decimal("0.00"),
        )

        service = PayrollCalculationService(
            employer_id=self.employer.id, year=2026, month=5, tenant_db="default"
        )
        results = service.run(mode=Salary.STATUS_SIMULATED)
        salary = results[0].salary
        line = SalaryDeduction.objects.filter(salary=salary, code="SCALE").first()
        self.assertEqual(line.amount, Decimal("50.00"))

    def test_irpp_and_cac(self):
        self._year = 2026
        self._month = 5
        self.config.professional_expense_rate = Decimal("10.00")
        self.config.max_professional_expense_amount = Decimal("100.00")
        self.config.tax_exempt_threshold = Decimal("0.00")
        self.config.save()

        basic = Advantage.objects.create(
            employer_id=self.employer.id,
            code="BASIC",
            name="Basic Salary",
            sys_code="BASIC_SALARY",
            is_manual=False,
        )
        self._add_basis_membership("SAL-BRUT", basic)
        self._add_basis_membership("SAL-BRUT-TAX", basic)
        self._add_basis_membership("SAL-BRUT-TAX-IRPP", basic)

        pvid = Deduction.objects.create(
            employer_id=self.employer.id,
            code="PVID",
            name="PVID",
            sys_code="PVID",
            is_employee=True,
            calculation_basis_code="SAL-BRUT",
            employee_rate=Decimal("5.00"),
            is_rate=True,
        )

        scale = CalculationScale.objects.create(
            employer_id=self.employer.id,
            code="IRPP",
            name="IRPP Scale",
        )
        ScaleRange.objects.create(
            employer_id=self.employer.id,
            scale=scale,
            range_min=Decimal("0.00"),
            range_max=Decimal("1000000.00"),
            coefficient=Decimal("10.00"),
            indice=Decimal("0.00"),
            position=1,
        )
        irpp = Deduction.objects.create(
            employer_id=self.employer.id,
            code="IRPP",
            name="IRPP",
            sys_code="IRPP",
            is_employee=True,
            calculation_basis_code="SAL-BRUT-TAX-IRPP",
            scale=scale,
            is_scale=True,
        )
        cac = Deduction.objects.create(
            employer_id=self.employer.id,
            code="CAC",
            name="CAC",
            sys_code="CAC",
            is_employee=True,
            calculation_basis_code="SAL-BRUT-TAX-IRPP",
            is_rate=False,
            is_scale=True,
            scale=scale,
        )

        contract = self._create_contract(base_salary=Decimal("1000.00"))
        PayrollElement.objects.create(
            employer_id=self.employer.id,
            contract=contract,
            advantage=basic,
            amount=Decimal("1000.00"),
        )
        for deduction in (pvid, irpp, cac):
            PayrollElement.objects.create(
                employer_id=self.employer.id,
                contract=contract,
                deduction=deduction,
                amount=Decimal("0.00"),
            )

        service = PayrollCalculationService(
            employer_id=self.employer.id, year=2026, month=5, tenant_db="default"
        )
        results = service.run(mode=Salary.STATUS_SIMULATED)
        salary = results[0].salary

        irpp_line = SalaryDeduction.objects.filter(salary=salary, code="IRPP").first()
        cac_line = SalaryDeduction.objects.filter(salary=salary, code="CAC").first()
        self.assertIsNotNone(irpp_line)
        self.assertIsNotNone(cac_line)
        self.assertEqual(cac_line.amount, irpp_line.amount * Decimal("0.10"))

    def test_prorata_with_unpaid_leave(self):
        self._year = 2026
        self._month = 5
        basic = Advantage.objects.create(
            employer_id=self.employer.id,
            code="BASIC",
            name="Basic Salary",
            sys_code="BASIC_SALARY",
            is_manual=False,
        )
        self._add_basis_membership("SAL-BRUT", basic)
        self._add_basis_membership("SAL-BRUT-TAX", basic)
        self._add_basis_membership("SAL-BRUT-TAX-IRPP", basic)

        contract = self._create_contract(base_salary=Decimal("1000.00"))
        PayrollElement.objects.create(
            employer_id=self.employer.id,
            contract=contract,
            advantage=basic,
            amount=Decimal("1000.00"),
        )

        config = TimeOffConfiguration.build_defaults(self.employer.id)
        TimeOffConfiguration.objects.create(**config)
        TimeOffType.objects.create(
            configuration=TimeOffConfiguration.objects.first(),
            employer_id=self.employer.id,
            code="UNPAID",
            name="Unpaid Leave",
            paid=False,
        )
        start_at = datetime(self._year, self._month, 1, 8, 0, 0, tzinfo=timezone.utc)
        end_at = datetime(self._year, self._month, 2, 17, 0, 0, tzinfo=timezone.utc)
        TimeOffRequest.objects.create(
            employer_id=self.employer.id,
            employee=self.employee,
            leave_type_code="UNPAID",
            start_at=start_at,
            end_at=end_at,
            duration_minutes=16 * 60,
            status="APPROVED",
            created_by=1,
            updated_by=1,
        )

        service = PayrollCalculationService(
            employer_id=self.employer.id, year=self._year, month=self._month, tenant_db="default"
        )
        results = service.run(mode=Salary.STATUS_SIMULATED)
        salary = results[0].salary
        self.assertTrue(salary.base_salary < Decimal("1000.00"))

    def test_non_tax_basis_alias(self):
        self._year = 2026
        self._month = 5
        CalculationBasis.objects.filter(employer_id=self.employer.id, code="SAL-NON-TAX").delete()
        CalculationBasis.objects.create(employer_id=self.employer.id, code="NON-TAX", name="NON-TAX")

        basic = Advantage.objects.create(
            employer_id=self.employer.id,
            code="BASIC",
            name="Basic Salary",
            sys_code="BASIC_SALARY",
            is_manual=False,
        )
        meal = Advantage.objects.create(
            employer_id=self.employer.id,
            code="MEAL",
            name="Meal Benefit",
            is_manual=True,
        )
        for code in ["SAL-BRUT", "SAL-BRUT-TAX", "SAL-BRUT-TAX-IRPP", "SAL-BRUT-COT-AF-PV", "SAL-BRUT-COT-AT"]:
            self._add_basis_membership(code, basic)
        self._add_basis_membership("SAL-BRUT", meal)
        self._add_basis_membership("NON-TAX", meal)

        contract = self._create_contract(base_salary=Decimal("1000.00"))
        PayrollElement.objects.create(
            employer_id=self.employer.id,
            contract=contract,
            advantage=basic,
            amount=Decimal("1000.00"),
        )
        PayrollElement.objects.create(
            employer_id=self.employer.id,
            contract=contract,
            advantage=meal,
            amount=Decimal("200.00"),
        )

        service = PayrollCalculationService(
            employer_id=self.employer.id, year=self._year, month=self._month, tenant_db="default"
        )
        salary = service.run(mode=Salary.STATUS_SIMULATED)[0].salary
        self.assertEqual(salary.gross_salary, Decimal("1200.00"))
        self.assertEqual(salary.taxable_gross_salary, Decimal("1000.00"))

    def test_pvid_sys_code_alias(self):
        self._year = 2026
        self._month = 5
        self.config.professional_expense_rate = Decimal("0.00")
        self.config.max_professional_expense_amount = Decimal("0.00")
        self.config.tax_exempt_threshold = Decimal("0.00")
        self.config.save()

        basic = Advantage.objects.create(
            employer_id=self.employer.id,
            code="BASIC",
            name="Basic Salary",
            sys_code="BASIC_SALARY",
            is_manual=False,
        )
        self._add_basis_membership("SAL-BRUT", basic)
        self._add_basis_membership("SAL-BRUT-TAX", basic)
        self._add_basis_membership("SAL-BRUT-TAX-IRPP", basic)

        pvid = Deduction.objects.create(
            employer_id=self.employer.id,
            code="PVID",
            name="PVID",
            sys_code="PVID/S",
            is_employee=True,
            is_employer=False,
            is_count=True,
            calculation_basis_code="SAL-BRUT",
            employee_rate=Decimal("10.00"),
            is_rate=True,
        )

        scale = CalculationScale.objects.create(
            employer_id=self.employer.id,
            code="IRPP",
            name="IRPP Scale",
        )
        ScaleRange.objects.create(
            employer_id=self.employer.id,
            scale=scale,
            range_min=Decimal("0.00"),
            range_max=Decimal("1000000.00"),
            coefficient=Decimal("10.00"),
            indice=Decimal("0.00"),
            position=1,
        )
        irpp = Deduction.objects.create(
            employer_id=self.employer.id,
            code="IRPP",
            name="IRPP",
            sys_code="IRPP",
            is_employee=True,
            calculation_basis_code="SAL-BRUT-TAX-IRPP",
            scale=scale,
            is_scale=True,
        )

        contract = self._create_contract(base_salary=Decimal("1000.00"))
        PayrollElement.objects.create(
            employer_id=self.employer.id,
            contract=contract,
            advantage=basic,
            amount=Decimal("1000.00"),
        )
        for deduction in (pvid, irpp):
            PayrollElement.objects.create(
                employer_id=self.employer.id,
                contract=contract,
                deduction=deduction,
                amount=Decimal("0.00"),
            )

        service = PayrollCalculationService(
            employer_id=self.employer.id, year=self._year, month=self._month, tenant_db="default"
        )
        salary = service.run(mode=Salary.STATUS_SIMULATED)[0].salary
        irpp_line = SalaryDeduction.objects.filter(salary=salary, code="IRPP").first()
        self.assertIsNotNone(irpp_line)
        self.assertEqual(irpp_line.amount, Decimal("90.00"))

    def test_validate_creates_treasury_batch(self):
        self._year = 2026
        self._month = 5
        BankAccount.objects.create(
            employer_id=self.employer.id,
            name="Main",
            currency="XAF",
            bank_name="Bank",
            account_number="123",
            account_holder_name="Acme",
        )
        basic = Advantage.objects.create(
            employer_id=self.employer.id,
            code="BASIC",
            name="Basic Salary",
            sys_code="BASIC_SALARY",
            is_manual=False,
        )
        self._add_basis_membership("SAL-BRUT", basic)
        self._add_basis_membership("SAL-BRUT-TAX", basic)
        self._add_basis_membership("SAL-BRUT-TAX-IRPP", basic)
        contract = self._create_contract(base_salary=Decimal("1000.00"))
        PayrollElement.objects.create(
            employer_id=self.employer.id,
            contract=contract,
            advantage=basic,
            amount=Decimal("1000.00"),
        )
        service = PayrollCalculationService(
            employer_id=self.employer.id, year=self._year, month=self._month, tenant_db="default"
        )
        result = service.run(mode=Salary.STATUS_GENERATED)[0].salary

        class DummyUser:
            id = 1
            is_authenticated = True

        class DummyRequest:
            user = DummyUser()

        batches = validate_payroll(request=DummyRequest(), tenant_db="default", salaries=[result])
        self.assertEqual(len(batches), 1)
        self.assertEqual(PaymentBatch.objects.count(), 1)
        self.assertEqual(PaymentLine.objects.count(), 1)
        refreshed = Salary.objects.get(id=result.id)
        self.assertEqual(refreshed.status, Salary.STATUS_VALIDATED)

# Create your tests here.
