from datetime import date, datetime
from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from accounts.models import EmployerProfile
from attendance.models import AttendanceConfiguration, AttendanceRecord, WorkingSchedule
from contracts.models import Allowance, CalculationScale, Contract, ContractElement, Deduction, ScaleRange
from contracts.payroll_defaults import PAYROLL_DEFAULT_BASIS_ROWS, ensure_payroll_default_bases
from employees.models import Employee
from timeoff.models import TimeOffConfiguration, TimeOffRequest, TimeOffType
from treasury.models import BankAccount, PaymentBatch, PaymentLine

from payroll.models import (
    CalculationBasis,
    CalculationBasisAdvantage,
    PayrollConfiguration,
    Salary,
    SalaryDeduction,
)
from payroll.services import PayrollCalculationService, validate_payroll


class PayrollFeatureTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="owner@acme.test",
            password="pass",
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
            employee_id="EMP-001",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            job_title="Engineer",
            employment_type="FULL_TIME",
            employment_status="ACTIVE",
            hire_date=date(2025, 1, 1),
            bank_name="Employee Bank",
            bank_account_number="EMP-123",
        )
        self.year = 2026
        self.month = 1
        self.contract = Contract.objects.create(
            employer_id=self.employer.id,
            contract_id=f"CNT-{uuid.uuid4().hex[:8].upper()}",
            employee=self.employee,
            contract_type="PERMANENT",
            start_date=date(self.year, self.month, 1),
            status="ACTIVE",
            base_salary=Decimal("100000.00"),
            currency="XAF",
            pay_frequency="MONTHLY",
            created_by=self.user.id,
        )
        self.config = PayrollConfiguration.objects.create(
            employer_id=self.employer.id,
            rounding_scale=0,
            rounding_mode=PayrollConfiguration.ROUND_HALF_UP,
        )

        for code in [
            "SAL-BRUT",
            "SAL-NON-TAX",
            "SAL-BRUT-TAX",
            "SAL-BRUT-TAX-IRPP",
            "SAL-BRUT-COT-AF-PV",
            "SAL-BRUT-COT-AT",
            "SAL-BASE",
        ]:
            CalculationBasis.objects.create(employer_id=self.employer.id, code=code, name=code)

    def _basis(self, code):
        return CalculationBasis.objects.get(employer_id=self.employer.id, code=code)

    def _link_basis(self, basis_code, allowance=None, allowance_code=None):
        CalculationBasisAdvantage.objects.create(
            employer_id=self.employer.id,
            basis=self._basis(basis_code),
            allowance=allowance,
            allowance_code=allowance_code,
        )

    def _create_allowance(self, *, name, code, amount, sys=None, type="FIXED"):
        return Allowance.objects.create(
            contract=self.contract,
            name=name,
            code=code,
            type=type,
            amount=Decimal(str(amount)),
            sys=sys,
            is_enable=True,
        )

    def _create_deduction(
        self,
        *,
        name,
        code,
        sys=None,
        calculation_basis="SAL-BRUT",
        is_rate=False,
        is_scale=False,
        is_base=False,
        employee_rate=None,
        employer_rate=None,
        is_employee=True,
        is_employer=False,
        calculation_scale=None,
    ):
        return Deduction.objects.create(
            contract=self.contract,
            name=name,
            code=code,
            sys=sys,
            type="FIXED",
            amount=Decimal("0.00"),
            calculation_basis=calculation_basis,
            is_rate=is_rate,
            is_scale=is_scale,
            is_base=is_base,
            employee_rate=employee_rate,
            employer_rate=employer_rate,
            is_employee=is_employee,
            is_employer=is_employer,
            calculation_scale=calculation_scale,
            is_enable=True,
            is_count=True,
        )

    def _add_advantage_element(self, allowance, amount=None, month="__", year="__"):
        ContractElement.objects.create(
            contract=self.contract,
            advantage=allowance,
            amount=Decimal(str(amount if amount is not None else allowance.amount)),
            month=month,
            year=year,
            institution_id=self.employer.id,
            is_enable=True,
        )

    def _add_deduction_element(self, deduction, month="__", year="__"):
        ContractElement.objects.create(
            contract=self.contract,
            deduction=deduction,
            amount=Decimal("0.00"),
            month=month,
            year=year,
            institution_id=self.employer.id,
            is_enable=True,
        )

    def _run(self, year=None, month=None, mode=Salary.STATUS_SIMULATED):
        service = PayrollCalculationService(
            employer_id=self.employer.id,
            year=year or self.year,
            month=month or self.month,
            tenant_db="default",
        )
        return service.run(mode=mode)[0].salary

    def test_basis_computations(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        transport = self._create_allowance(name="Transport", code="TRSP", amount="20000")

        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT", allowance=transport)
        self._link_basis("SAL-NON-TAX", allowance=transport)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._link_basis("SAL-BRUT-COT-AF-PV", allowance=basic)
        self._link_basis("SAL-BRUT-COT-AT", allowance=basic)

        self._add_advantage_element(basic, amount="100000")
        self._add_advantage_element(transport, amount="20000")

        salary = self._run()
        self.assertEqual(salary.gross_salary, Decimal("120000"))
        self.assertEqual(salary.taxable_gross_salary, Decimal("100000"))
        self.assertEqual(salary.irpp_taxable_gross_salary, Decimal("100000"))
        self.assertEqual(salary.contribution_base_af_pv, Decimal("100000"))
        self.assertEqual(salary.contribution_base_at, Decimal("100000"))

    def test_bases_fallback_when_no_mappings_exist(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="120000", sys="BASIC_SALARY")
        self.contract.base_salary = Decimal("120000.00")
        self.contract.save()
        self._add_advantage_element(basic, amount="120000")

        salary = self._run()
        self.assertEqual(salary.gross_salary, Decimal("120000"))
        self.assertEqual(salary.taxable_gross_salary, Decimal("120000"))
        self.assertEqual(salary.irpp_taxable_gross_salary, Decimal("120000"))
        self.assertEqual(salary.contribution_base_af_pv, Decimal("120000"))
        self.assertEqual(salary.contribution_base_at, Decimal("120000"))
        self.assertEqual(salary.net_salary, Decimal("120000"))

    def test_bases_fallback_uses_total_advantages_for_gross(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        transport = self._create_allowance(name="Transport", code="TRSP", amount="20000")
        self.contract.base_salary = Decimal("100000.00")
        self.contract.save()

        self._add_advantage_element(basic, amount="100000")
        self._add_advantage_element(transport, amount="20000")

        salary = self._run()
        self.assertEqual(salary.gross_salary, Decimal("120000"))
        self.assertEqual(salary.taxable_gross_salary, Decimal("120000"))
        self.assertEqual(salary.irpp_taxable_gross_salary, Decimal("120000"))
        self.assertEqual(salary.contribution_base_af_pv, Decimal("100000"))
        self.assertEqual(salary.contribution_base_at, Decimal("100000"))
        self.assertEqual(salary.net_salary, Decimal("120000"))

    def test_default_basis_codes_are_seeded_automatically(self):
        CalculationBasis.objects.filter(employer_id=self.employer.id).delete()

        ensure_payroll_default_bases(
            employer_id=self.employer.id,
            tenant_db="default",
        )

        rows = CalculationBasis.objects.filter(employer_id=self.employer.id)
        row_by_code = {row.code: row for row in rows}
        expected_codes = [code for code, _ in PAYROLL_DEFAULT_BASIS_ROWS]

        self.assertEqual(set(row_by_code.keys()), set(expected_codes))
        for code, expected_name in PAYROLL_DEFAULT_BASIS_ROWS:
            row = row_by_code[code]
            self.assertTrue(row.is_active)
            self.assertEqual(row.name, expected_name)

    def test_element_month_year_filter_with_double_underscore(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        bonus = self._create_allowance(name="Bonus", code="BONUS", amount="5000")
        future_bonus = self._create_allowance(name="Future Bonus", code="FUTURE", amount="9000")

        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT", allowance=bonus)
        self._link_basis("SAL-BRUT", allowance=future_bonus)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)

        self._add_advantage_element(basic, amount="100000", month="__", year="__")
        self._add_advantage_element(bonus, amount="5000", month="01", year="2026")
        self._add_advantage_element(future_bonus, amount="9000", month="02", year="2026")

        jan_salary = self._run(year=2026, month=1)
        feb_salary = self._run(year=2026, month=2)

        self.assertEqual(jan_salary.gross_salary, Decimal("105000"))
        self.assertEqual(feb_salary.gross_salary, Decimal("109000"))

    def test_rate_deduction(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="100000")

        cnps = self._create_deduction(
            name="CNPS Employee",
            code="CNPS_EMP",
            calculation_basis="SAL-BRUT",
            is_rate=True,
            employee_rate=Decimal("10.00"),
        )
        self._add_deduction_element(cnps)

        salary = self._run()
        line = SalaryDeduction.objects.get(salary=salary, code="CNPS_EMP")
        self.assertEqual(line.amount, Decimal("10000"))

    def test_scale_deduction(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="100000")

        scale = CalculationScale.objects.create(
            employer_id=self.employer.id,
            code="CNPS-SCALE",
            name="CNPS Scale",
            is_enable=True,
        )
        ScaleRange.objects.create(
            employer_id=self.employer.id,
            calculation_scale=scale,
            range1=0,
            range2=200000,
            coefficient=5,
            indice=0,
            is_enable=True,
        )
        deduction = self._create_deduction(
            name="Scale Deduction",
            code="SCALE",
            calculation_basis="SAL-BRUT",
            is_scale=True,
            calculation_scale="CNPS-SCALE",
        )
        self._add_deduction_element(deduction)

        salary = self._run()
        line = SalaryDeduction.objects.get(salary=salary, code="SCALE")
        self.assertEqual(line.amount, Decimal("5000"))

    def test_irpp_special_progressive_with_cac(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="300000", sys="BASIC_SALARY")
        self.contract.base_salary = Decimal("300000.00")
        self.contract.save()
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="300000")

        scale = CalculationScale.objects.create(
            employer_id=self.employer.id,
            code="IRPP-SCALE",
            name="IRPP Scale",
            is_enable=True,
        )
        ScaleRange.objects.create(
            employer_id=self.employer.id,
            calculation_scale=scale,
            range1=0,
            range2=2000000,
            coefficient=10,
            indice=200000,
            is_enable=True,
        )
        ScaleRange.objects.create(
            employer_id=self.employer.id,
            calculation_scale=scale,
            range1=2000000,
            range2=None,
            coefficient=20,
            indice=0,
            is_enable=True,
        )

        irpp = self._create_deduction(
            name="IRPP",
            code="IRPP",
            sys="IRPP",
            calculation_basis="SAL-BRUT-TAX-IRPP",
            is_scale=True,
            calculation_scale="IRPP-SCALE",
            is_employee=True,
        )
        cac = self._create_deduction(
            name="CAC",
            code="CAC",
            sys="CAC",
            calculation_basis="SAL-BRUT-TAX-IRPP",
            is_employee=True,
        )
        self._add_deduction_element(irpp)
        self._add_deduction_element(cac)

        salary = self._run()
        irpp_line = SalaryDeduction.objects.get(salary=salary, code="IRPP")
        cac_line = SalaryDeduction.objects.get(salary=salary, code="CAC")

        self.assertEqual(irpp_line.amount, Decimal("43333"))
        self.assertEqual(cac_line.amount, Decimal("4333"))

    def test_irpp_uses_cameroon_default_scale_when_missing(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="300000", sys="BASIC_SALARY")
        self.contract.base_salary = Decimal("300000.00")
        self.contract.save()
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="300000")

        irpp = self._create_deduction(
            name="IRPP",
            code="IRPP",
            sys="IRPP",
            calculation_basis="SAL-BRUT-TAX-IRPP",
            is_scale=True,
            calculation_scale=None,
            is_employee=True,
        )
        cac = self._create_deduction(
            name="CAC",
            code="CAC",
            sys="CAC",
            calculation_basis="SAL-BRUT-TAX-IRPP",
            is_employee=True,
        )
        self._add_deduction_element(irpp)
        self._add_deduction_element(cac)

        salary = self._run()
        default_scale = CalculationScale.objects.get(
            employer_id=self.employer.id,
            code="CM-IRPP-DEFAULT",
        )
        default_ranges_count = ScaleRange.objects.filter(
            employer_id=self.employer.id,
            calculation_scale=default_scale,
        ).count()
        self.assertEqual(default_ranges_count, 4)

        irpp_line = SalaryDeduction.objects.get(salary=salary, code="IRPP")
        cac_line = SalaryDeduction.objects.get(salary=salary, code="CAC")
        self.assertEqual(irpp_line.amount, Decimal("41667"))
        self.assertEqual(cac_line.amount, Decimal("4167"))

    def test_tdl_uses_cameroon_default_scale_when_missing(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="300000", sys="BASIC_SALARY")
        self.contract.base_salary = Decimal("300000.00")
        self.contract.save()
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="300000")

        tdl = self._create_deduction(
            name="TDL",
            code="TDL",
            sys="TDL",
            calculation_basis=None,
            is_rate=False,
            is_scale=False,
            is_base=False,
            calculation_scale=None,
            is_employee=True,
        )
        self._add_deduction_element(tdl)

        salary = self._run()
        default_scale = CalculationScale.objects.get(
            employer_id=self.employer.id,
            code="CM-TDL-DEFAULT",
        )
        default_ranges_count = ScaleRange.objects.filter(
            employer_id=self.employer.id,
            calculation_scale=default_scale,
        ).count()
        self.assertEqual(default_ranges_count, 10)

        tdl_line = SalaryDeduction.objects.get(salary=salary, code="TDL")
        self.assertEqual(tdl_line.base_amount, Decimal("300000"))
        self.assertEqual(tdl_line.amount, Decimal("2000"))

    def test_rav_uses_cameroon_default_scale_when_missing(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="300000", sys="BASIC_SALARY")
        transport = self._create_allowance(name="Transport", code="TRSP", amount="50000")
        self.contract.base_salary = Decimal("300000.00")
        self.contract.save()
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT", allowance=transport)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="300000")
        self._add_advantage_element(transport, amount="50000")

        rav = self._create_deduction(
            name="RAV",
            code="RAV",
            sys="RAV",
            calculation_basis=None,
            is_rate=False,
            is_scale=False,
            is_base=False,
            calculation_scale=None,
            is_employee=True,
        )
        self._add_deduction_element(rav)

        salary = self._run()
        default_scale = CalculationScale.objects.get(
            employer_id=self.employer.id,
            code="CM-RAV-DEFAULT",
        )
        default_ranges_count = ScaleRange.objects.filter(
            employer_id=self.employer.id,
            calculation_scale=default_scale,
        ).count()
        self.assertEqual(default_ranges_count, 12)

        rav_line = SalaryDeduction.objects.get(salary=salary, code="RAV")
        self.assertEqual(rav_line.base_amount, Decimal("350000"))
        self.assertEqual(rav_line.amount, Decimal("4550"))

    def test_prorata_with_unpaid_leave(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="310000", sys="BASIC_SALARY")
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="310000")
        self.contract.base_salary = Decimal("310000.00")
        self.contract.save()

        config_defaults = TimeOffConfiguration.build_defaults(self.employer.id)
        timeoff_config = TimeOffConfiguration.objects.create(**config_defaults)
        TimeOffType.objects.create(
            configuration=timeoff_config,
            employer_id=self.employer.id,
            code="UNPAID",
            name="Unpaid Leave",
            paid=False,
        )

        start_at = timezone.make_aware(datetime(self.year, self.month, 10, 9, 0, 0))
        end_at = timezone.make_aware(datetime(self.year, self.month, 10, 17, 0, 0))
        TimeOffRequest.objects.create(
            employer_id=self.employer.id,
            employee=self.employee,
            leave_type_code="UNPAID",
            start_at=start_at,
            end_at=end_at,
            duration_minutes=480,
            status="APPROVED",
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        salary = self._run()
        self.assertEqual(salary.base_salary, Decimal("300000"))

    def test_prorata_ignores_timeoff_outside_contract_period(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="310000", sys="BASIC_SALARY")
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="310000")
        self.contract.base_salary = Decimal("310000.00")
        self.contract.start_date = date(self.year, self.month, 15)
        self.contract.save()

        config_defaults = TimeOffConfiguration.build_defaults(self.employer.id)
        timeoff_config = TimeOffConfiguration.objects.create(**config_defaults)
        TimeOffType.objects.create(
            configuration=timeoff_config,
            employer_id=self.employer.id,
            code="UNPAID",
            name="Unpaid Leave",
            paid=False,
        )

        start_at = timezone.make_aware(datetime(self.year, self.month, 10, 9, 0, 0))
        end_at = timezone.make_aware(datetime(self.year, self.month, 10, 17, 0, 0))
        TimeOffRequest.objects.create(
            employer_id=self.employer.id,
            employee=self.employee,
            leave_type_code="UNPAID",
            start_at=start_at,
            end_at=end_at,
            duration_minutes=480,
            status="APPROVED",
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        salary = self._run()
        self.assertEqual(salary.base_salary, Decimal("170000"))

    def test_attendance_uses_schedule_daily_minutes_for_absence_prorata(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="310000", sys="BASIC_SALARY")
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="310000")
        self.contract.base_salary = Decimal("310000.00")
        self.contract.save()

        config_defaults = TimeOffConfiguration.build_defaults(self.employer.id)
        config_defaults["working_hours_per_day"] = 10
        TimeOffConfiguration.objects.create(**config_defaults)

        AttendanceConfiguration.objects.create(
            employer_id=self.employer.id,
            is_enabled=True,
        )
        WorkingSchedule.objects.create(
            employer_id=self.employer.id,
            name="Default Schedule",
            default_daily_minutes=480,
            is_default=True,
        )

        check_in = timezone.make_aware(datetime(self.year, self.month, 10, 9, 0, 0))
        check_out = timezone.make_aware(datetime(self.year, self.month, 10, 17, 0, 0))
        AttendanceRecord.objects.create(
            employer_id=self.employer.id,
            employee=self.employee,
            check_in_at=check_in,
            check_out_at=check_out,
            worked_minutes=0,
            expected_minutes=480,
            overtime_worked_minutes=0,
            overtime_approved_minutes=0,
            status=AttendanceRecord.STATUS_APPROVED,
        )

        salary = self._run()
        self.assertEqual(salary.absence_days, Decimal("1"))
        self.assertEqual(salary.base_salary, Decimal("300000"))

    def test_attendance_adjustments_skipped_when_module_disabled(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="310000", sys="BASIC_SALARY")
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="310000")
        self.contract.base_salary = Decimal("310000.00")
        self.contract.save()

        AttendanceConfiguration.objects.create(
            employer_id=self.employer.id,
            is_enabled=False,
        )

        check_in = timezone.make_aware(datetime(self.year, self.month, 10, 9, 0, 0))
        check_out = timezone.make_aware(datetime(self.year, self.month, 10, 17, 0, 0))
        AttendanceRecord.objects.create(
            employer_id=self.employer.id,
            employee=self.employee,
            check_in_at=check_in,
            check_out_at=check_out,
            worked_minutes=0,
            expected_minutes=480,
            overtime_worked_minutes=0,
            overtime_approved_minutes=0,
            status=AttendanceRecord.STATUS_APPROVED,
        )

        salary = self._run()
        self.assertEqual(salary.absence_days, Decimal("0"))
        self.assertEqual(salary.base_salary, Decimal("310000"))

    def test_validate_creates_treasury_batch(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="100000")

        BankAccount.objects.create(
            employer_id=self.employer.id,
            name="Main Account",
            currency="XAF",
            bank_name="Bank",
            account_number="001122",
            account_holder_name="Acme Payroll",
            is_active=True,
        )

        generated_salary = self._run(mode=Salary.STATUS_GENERATED)
        request = APIRequestFactory().post("/api/payroll/validate/")
        request.user = self.user

        batches = validate_payroll(request=request, tenant_db="default", salaries=[generated_salary])
        self.assertEqual(len(batches), 1)
        self.assertEqual(PaymentBatch.objects.count(), 1)
        self.assertEqual(PaymentLine.objects.count(), 1)

        generated_salary.refresh_from_db()
        self.assertEqual(generated_salary.status, Salary.STATUS_VALIDATED)

    def test_validate_autocreates_treasury_bank_source_from_employer_profile(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="100000")

        self.assertEqual(BankAccount.objects.count(), 0)

        generated_salary = self._run(mode=Salary.STATUS_GENERATED)
        request = APIRequestFactory().post("/api/payroll/validate/")
        request.user = self.user

        batches = validate_payroll(request=request, tenant_db="default", salaries=[generated_salary])
        self.assertEqual(len(batches), 1)
        self.assertEqual(BankAccount.objects.count(), 1)
        self.assertEqual(PaymentBatch.objects.count(), 1)
        self.assertEqual(PaymentLine.objects.count(), 1)

        source_account = BankAccount.objects.first()
        self.assertTrue(source_account.is_active)
        self.assertEqual(source_account.bank_name, self.employer.bank_name)
        self.assertEqual(source_account.account_number, self.employer.bank_account_number)

    def test_validate_error_mentions_employer_treasury_bank_account(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="100000")

        self.employer.bank_name = None
        self.employer.bank_account_number = None
        self.employer.save(update_fields=["bank_name", "bank_account_number"])

        generated_salary = self._run(mode=Salary.STATUS_GENERATED)
        request = APIRequestFactory().post("/api/payroll/validate/")
        request.user = self.user

        with self.assertRaises(ValidationError) as exc:
            validate_payroll(request=request, tenant_db="default", salaries=[generated_salary])

        message = str(exc.exception.detail).lower()
        self.assertIn("employer treasury bank account", message)
        self.assertIn("employee bank accounts are beneficiary details only", message)
