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
from contracts.models import (
    Allowance,
    CalculationScale,
    Contract,
    ContractComponentTemplate,
    ContractElement,
    Deduction,
    ScaleRange,
)
from contracts.payroll_defaults import PAYROLL_DEFAULT_BASIS_ROWS, ensure_payroll_default_bases
from employees.models import Employee
from timeoff.models import TimeOffConfiguration, TimeOffRequest, TimeOffType
from treasury.models import BankAccount, PaymentBatch, PaymentLine

from payroll.models import (
    AttendancePayrollImpactConfig,
    CalculationBasis,
    CalculationBasisAdvantage,
    PayrollGeneratedItem,
    PayrollConfiguration,
    Salary,
    SalaryAdvantage,
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

    def _create_allowance(self, *, name, code, amount, sys=None, type="FIXED", effective_from=None):
        return Allowance.objects.create(
            contract=self.contract,
            name=name,
            code=code,
            type=type,
            amount=Decimal(str(amount)),
            sys=sys,
            effective_from=effective_from,
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

    def _add_deduction_element(self, deduction, month="__", year="__", amount=None):
        deduction_amount = amount if amount is not None else getattr(deduction, "amount", Decimal("0.00"))
        return ContractElement.objects.create(
            contract=self.contract,
            deduction=deduction,
            amount=Decimal(str(deduction_amount or "0")),
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

    def test_gross_includes_basic_when_sal_brut_mapping_omits_basic(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        transport = self._create_allowance(name="Transport", code="TRSP", amount="20000")

        self._link_basis("SAL-BRUT", allowance=transport)
        self._link_basis("SAL-BRUT-TAX", allowance=transport)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=transport)

        self._add_advantage_element(basic, amount="100000")
        self._add_advantage_element(transport, amount="20000")

        salary = self._run()
        self.assertEqual(salary.gross_salary, Decimal("120000"))

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

    def test_effective_from_applies_to_wildcard_elements(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        bonus = self._create_allowance(
            name="Bonus",
            code="BONUS",
            amount="5000",
            effective_from=date(2026, 2, 1),
        )

        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT", allowance=bonus)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)

        self._add_advantage_element(basic, amount="100000", month="__", year="__")
        self._add_advantage_element(bonus, amount="5000", month="__", year="__")

        jan_salary = self._run(year=2026, month=1)
        feb_salary = self._run(year=2026, month=2)

        self.assertEqual(jan_salary.gross_salary, Decimal("100000"))
        self.assertEqual(feb_salary.gross_salary, Decimal("105000"))

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

    def test_base_salary_alias_is_resolved_for_rate_deduction_basis(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        self.contract.base_salary = Decimal("100000.00")
        self.contract.save()
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="100000")

        deduction = self._create_deduction(
            name="Alias Basis Deduction",
            code="ALIAS10",
            calculation_basis="BASE_SALARY",
            is_rate=True,
            employee_rate=Decimal("10.00"),
        )
        self._add_deduction_element(deduction)

        salary = self._run()
        line = SalaryDeduction.objects.get(salary=salary, code="ALIAS10")
        self.assertEqual(line.base_amount, Decimal("100000"))
        self.assertEqual(line.amount, Decimal("10000"))

    def test_irpp_uses_base_salary_alias_for_base_amount(self):
        self.config.irpp_withholding_threshold = Decimal("0.00")
        self.config.save(update_fields=["irpp_withholding_threshold", "updated_at"])

        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        self.contract.base_salary = Decimal("100000.00")
        self.contract.save()
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="100000")

        irpp = self._create_deduction(
            name="IRPP",
            code="IRPP",
            sys="IRPP",
            calculation_basis="BASE_SALARY",
            is_scale=True,
        )
        self._add_deduction_element(irpp)

        salary = self._run()
        line = SalaryDeduction.objects.get(salary=salary, code="IRPP")
        self.assertEqual(line.base_amount, Decimal("100000"))
        self.assertGreater(line.amount, Decimal("0"))

    def test_fixed_deduction_without_code_or_sys_uses_element_amount(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="100000")

        loan = self._create_deduction(
            name="Staff Loan",
            code="",
            sys="",
            calculation_basis="SAL-BRUT",
            is_rate=False,
            is_scale=False,
            is_base=False,
        )
        self._add_deduction_element(loan, amount="5000")

        salary = self._run()
        line = SalaryDeduction.objects.get(salary=salary, name="Staff Loan")
        self.assertEqual(line.amount, Decimal("5000"))
        self.assertEqual(salary.total_employee_deductions, Decimal("5000"))
        self.assertEqual(salary.net_salary, Decimal("95000"))

    def test_irpp_and_cac_are_detected_from_name_when_code_is_blank(self):
        self.config.irpp_withholding_threshold = Decimal("0.00")
        self.config.save(update_fields=["irpp_withholding_threshold", "updated_at"])

        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="100000")

        irpp = self._create_deduction(
            name="IRPP",
            code="",
            sys="",
            calculation_basis="SAL-BRUT-TAX-IRPP",
            is_scale=True,
        )
        cac = self._create_deduction(
            name="CAC",
            code="",
            sys="",
            calculation_basis="SAL-BRUT-TAX-IRPP",
        )
        self._add_deduction_element(irpp)
        self._add_deduction_element(cac)

        salary = self._run()
        irpp_line = SalaryDeduction.objects.get(salary=salary, name="IRPP")
        cac_line = SalaryDeduction.objects.get(salary=salary, name="CAC")

        self.assertGreater(irpp_line.amount, Decimal("0"))
        self.assertGreater(cac_line.amount, Decimal("0"))

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

    def test_deductions_are_computed_in_social_irpp_cac_then_other_order(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="100000", sys="BASIC_SALARY")
        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="100000")

        pvid = self._create_deduction(
            name="PVID",
            code="PVID",
            sys="PVID",
            calculation_basis="SAL-BRUT",
            is_rate=True,
            employee_rate=Decimal("2.50"),
        )
        irpp = self._create_deduction(
            name="IRPP",
            code="IRPP",
            sys="IRPP",
            calculation_basis="SAL-BRUT-TAX-IRPP",
            is_scale=True,
            calculation_scale=None,
        )
        cac = self._create_deduction(
            name="CAC",
            code="CAC",
            sys="CAC",
            calculation_basis="SAL-BRUT-TAX-IRPP",
        )
        loan = self._create_deduction(
            name="Loan",
            code="LOAN",
            calculation_basis="SAL-BRUT",
            is_rate=True,
            employee_rate=Decimal("5.00"),
        )

        loan_element = self._add_deduction_element(loan)
        cac_element = self._add_deduction_element(cac)
        irpp_element = self._add_deduction_element(irpp)
        pvid_element = self._add_deduction_element(pvid)

        service = PayrollCalculationService(
            employer_id=self.employer.id,
            year=self.year,
            month=self.month,
            tenant_db="default",
        )
        adjustments = service.build_monthly_adjustments(self.contract)
        prorata = service._resolve_prorata_factor(self.contract, adjustments)
        adjusted_basic_salary = self.contract.base_salary * prorata

        advantage_elements = service._filter_elements(
            ContractElement.objects.filter(
                institution_id=self.employer.id,
                contract=self.contract,
                is_enable=True,
                advantage__isnull=False,
            ).select_related("advantage")
        )
        advantage_lines = service._build_advantage_lines(
            contract=self.contract,
            advantage_elements=advantage_elements,
            adjusted_basic_salary=adjusted_basic_salary,
            adjustments=adjustments,
        )
        bases = service._calculate_bases(advantage_lines, adjusted_basic_salary)

        lines, _ = service._compute_deductions(
            deduction_elements=[loan_element, cac_element, irpp_element, pvid_element],
            bases=bases,
            adjusted_basic_salary=adjusted_basic_salary,
        )
        self.assertEqual([line.code for line in lines], ["PVID", "IRPP", "CAC", "LOAN"])

    def test_irpp_withholding_threshold_applies_below_62000(self):
        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="60000", sys="BASIC_SALARY")
        self.contract.base_salary = Decimal("60000.00")
        self.contract.save()

        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="60000")

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
        irpp_line = SalaryDeduction.objects.get(salary=salary, code="IRPP")
        cac_line = SalaryDeduction.objects.get(salary=salary, code="CAC")

        self.assertEqual(irpp_line.amount, Decimal("0"))
        self.assertEqual(cac_line.amount, Decimal("0"))
        self.assertEqual(salary.net_salary, Decimal("60000"))

    def test_irpp_threshold_and_cac_rate_are_configurable(self):
        self.config.irpp_withholding_threshold = Decimal("0.00")
        self.config.cac_rate_percentage = Decimal("12.50")
        self.config.save(update_fields=["irpp_withholding_threshold", "cac_rate_percentage", "updated_at"])

        basic = self._create_allowance(name="Basic Salary", code="BASIC", amount="60000", sys="BASIC_SALARY")
        self.contract.base_salary = Decimal("60000.00")
        self.contract.save()

        self._link_basis("SAL-BRUT", allowance=basic)
        self._link_basis("SAL-BRUT-TAX", allowance=basic)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=basic)
        self._add_advantage_element(basic, amount="60000")

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
        irpp_line = SalaryDeduction.objects.get(salary=salary, code="IRPP")
        cac_line = SalaryDeduction.objects.get(salary=salary, code="CAC")

        self.assertEqual(irpp_line.amount, Decimal("6000"))
        self.assertEqual(cac_line.amount, Decimal("750"))
        self.assertEqual(cac_line.rate, Decimal("12.50"))

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


class AttendancePayrollImpactConfigTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="owner-impact@acme.test",
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
            employee_id="EMP-IMPACT-001",
            first_name="John",
            last_name="Smith",
            email="john@example.com",
            job_title="Engineer",
            employment_type="FULL_TIME",
            employment_status="ACTIVE",
            hire_date=date(2025, 1, 1),
        )
        self.year = 2026
        self.month = 1
        self.contract = Contract.objects.create(
            employer_id=self.employer.id,
            contract_id=f"CNT-IMP-{uuid.uuid4().hex[:8].upper()}",
            employee=self.employee,
            contract_type="PERMANENT",
            start_date=date(self.year, self.month, 1),
            status="ACTIVE",
            base_salary=Decimal("100000.00"),
            currency="XAF",
            pay_frequency="MONTHLY",
            created_by=self.user.id,
        )
        PayrollConfiguration.objects.create(
            employer_id=self.employer.id,
            rounding_scale=0,
            rounding_mode=PayrollConfiguration.ROUND_HALF_UP,
        )
        AttendanceConfiguration.objects.create(
            employer_id=self.employer.id,
            is_enabled=True,
            allow_systray_portal=True,
        )
        self._create_schedule()
        self.basic_allowance = self._create_allowance(
            name="Basic Salary",
            code="BASIC",
            amount="100000",
            sys="BASIC_SALARY",
        )
        self._add_advantage_element(self.basic_allowance, amount="100000")

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
        self._link_basis("SAL-BRUT", allowance=self.basic_allowance)
        self._link_basis("SAL-BRUT-TAX", allowance=self.basic_allowance)
        self._link_basis("SAL-BRUT-TAX-IRPP", allowance=self.basic_allowance)
        self._link_basis("SAL-BRUT-COT-AF-PV", allowance=self.basic_allowance)
        self._link_basis("SAL-BRUT-COT-AT", allowance=self.basic_allowance)

    def _create_schedule(self):
        schedule = WorkingSchedule.objects.create(
            employer_id=self.employer.id,
            name="Default Schedule",
            default_daily_minutes=480,
            is_default=True,
            timezone="UTC",
        )
        for weekday in range(0, 5):
            start = datetime(self.year, self.month, 5, 9, 0, 0).time()
            end = datetime(self.year, self.month, 5, 17, 0, 0).time()
            schedule.days.create(
                weekday=weekday,
                start_time=start,
                end_time=end,
                break_minutes=0,
            )

    def _basis(self, code):
        return CalculationBasis.objects.get(employer_id=self.employer.id, code=code)

    def _link_basis(self, basis_code, allowance=None, allowance_code=None):
        CalculationBasisAdvantage.objects.create(
            employer_id=self.employer.id,
            basis=self._basis(basis_code),
            allowance=allowance,
            allowance_code=allowance_code,
        )

    def _create_allowance(self, *, name, code, amount, sys=None):
        return Allowance.objects.create(
            contract=self.contract,
            name=name,
            code=code,
            type="FIXED",
            amount=Decimal(str(amount)),
            sys=sys,
            is_enable=True,
        )

    def _create_deduction(self, *, name, code):
        return Deduction.objects.create(
            contract=self.contract,
            name=name,
            code=code,
            type="FIXED",
            amount=Decimal("0.00"),
            is_employee=True,
            is_employer=False,
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

    def _run(self):
        service = PayrollCalculationService(
            employer_id=self.employer.id,
            year=self.year,
            month=self.month,
            tenant_db="default",
        )
        return service.run(mode=Salary.STATUS_SIMULATED)[0].salary

    def _create_attendance_record(
        self,
        *,
        check_in_at,
        check_out_at,
        expected_minutes,
        worked_minutes,
        overtime_worked_minutes=0,
        overtime_approved_minutes=0,
        status=AttendanceRecord.STATUS_APPROVED,
    ):
        AttendanceRecord.objects.create(
            employer_id=self.employer.id,
            employee=self.employee,
            check_in_at=check_in_at,
            check_out_at=check_out_at,
            expected_minutes=expected_minutes,
            worked_minutes=worked_minutes,
            overtime_worked_minutes=overtime_worked_minutes,
            overtime_approved_minutes=overtime_approved_minutes,
            status=status,
            mode=AttendanceRecord.MODE_MANUAL,
        )

    def test_lateness_deduction_computed_with_grace_minutes(self):
        late_deduction = self._create_deduction(name="Late Penalty", code="LATE_PEN")
        AttendancePayrollImpactConfig.objects.create(
            employer_id=self.employer.id,
            event_code=AttendancePayrollImpactConfig.EVENT_LATENESS,
            affects_payroll=True,
            bucket=AttendancePayrollImpactConfig.BUCKET_DEDUCTION,
            deduction=late_deduction,
            calc_method=AttendancePayrollImpactConfig.CALC_PER_MINUTE,
            value=Decimal("10.00"),
            grace_minutes=5,
            requires_validation=True,
            is_active=True,
        )

        check_in = timezone.make_aware(datetime(self.year, self.month, 5, 9, 20, 0))
        check_out = timezone.make_aware(datetime(self.year, self.month, 5, 17, 0, 0))
        self._create_attendance_record(
            check_in_at=check_in,
            check_out_at=check_out,
            expected_minutes=480,
            worked_minutes=460,
        )

        salary = self._run()
        line = SalaryDeduction.objects.get(salary=salary, code="LATE_PEN")
        self.assertEqual(line.amount, Decimal("150"))
        self.assertEqual(salary.total_employee_deductions, Decimal("150"))

    def test_absence_deduction_based_on_daily_rate(self):
        absence_deduction = self._create_deduction(name="Absence Penalty", code="ABS_PEN")
        AttendancePayrollImpactConfig.objects.create(
            employer_id=self.employer.id,
            event_code=AttendancePayrollImpactConfig.EVENT_ABSENCE,
            affects_payroll=True,
            bucket=AttendancePayrollImpactConfig.BUCKET_DEDUCTION,
            deduction=absence_deduction,
            calc_method=AttendancePayrollImpactConfig.CALC_PERCENT_DAILY_RATE,
            value=Decimal("100.00"),
            requires_validation=True,
            is_active=True,
        )

        check_in = timezone.make_aware(datetime(self.year, self.month, 6, 9, 0, 0))
        check_out = timezone.make_aware(datetime(self.year, self.month, 6, 17, 0, 0))
        self._create_attendance_record(
            check_in_at=check_in,
            check_out_at=check_out,
            expected_minutes=480,
            worked_minutes=0,
        )

        salary = self._run()
        line = SalaryDeduction.objects.get(salary=salary, code="ABS_PEN")
        self.assertEqual(line.amount, Decimal("3226"))

    def test_deduction_target_code_from_contract_configuration_template(self):
        self._create_deduction(name="Late Penalty", code="LATE_PEN")
        ContractComponentTemplate.objects.create(
            employer_id=self.employer.id,
            component_type=ContractComponentTemplate.COMPONENT_DEDUCTION,
            code="LATE_PEN",
            name="Late Penalty",
            is_active=True,
        )
        AttendancePayrollImpactConfig.objects.create(
            employer_id=self.employer.id,
            event_code=AttendancePayrollImpactConfig.EVENT_LATENESS,
            affects_payroll=True,
            bucket=AttendancePayrollImpactConfig.BUCKET_DEDUCTION,
            target_code="LATE_PEN",
            target_name="Late Penalty",
            calc_method=AttendancePayrollImpactConfig.CALC_PER_MINUTE,
            value=Decimal("10.00"),
            grace_minutes=5,
            requires_validation=True,
            is_active=True,
        )

        check_in = timezone.make_aware(datetime(self.year, self.month, 5, 9, 20, 0))
        check_out = timezone.make_aware(datetime(self.year, self.month, 5, 17, 0, 0))
        self._create_attendance_record(
            check_in_at=check_in,
            check_out_at=check_out,
            expected_minutes=480,
            worked_minutes=460,
        )

        salary = self._run()
        line = SalaryDeduction.objects.get(salary=salary, code="LATE_PEN")
        self.assertEqual(line.name, "Late Penalty")
        self.assertEqual(line.amount, Decimal("150"))

    def test_overtime_advantage_computed_with_multiplier(self):
        overtime_allowance = self._create_allowance(name="Overtime Pay", code="OT_PAY", amount="0")
        AttendancePayrollImpactConfig.objects.create(
            employer_id=self.employer.id,
            event_code=AttendancePayrollImpactConfig.EVENT_OVERTIME,
            affects_payroll=True,
            bucket=AttendancePayrollImpactConfig.BUCKET_ADVANTAGE,
            allowance=overtime_allowance,
            calc_method=AttendancePayrollImpactConfig.CALC_MULTIPLIER_HOURLY_RATE,
            value=Decimal("1.50"),
            multiplier=Decimal("1.50"),
            requires_validation=True,
            is_active=True,
        )

        check_in = timezone.make_aware(datetime(self.year, self.month, 7, 9, 0, 0))
        check_out = timezone.make_aware(datetime(self.year, self.month, 7, 19, 0, 0))
        self._create_attendance_record(
            check_in_at=check_in,
            check_out_at=check_out,
            expected_minutes=480,
            worked_minutes=600,
            overtime_worked_minutes=120,
            overtime_approved_minutes=120,
        )

        salary = self._run()
        line = SalaryAdvantage.objects.get(salary=salary, code="OT_PAY")
        self.assertEqual(line.amount, Decimal("1210"))

    def test_advantage_target_code_from_contract_configuration_template(self):
        self._create_allowance(name="Overtime Pay", code="OT_PAY", amount="0")
        ContractComponentTemplate.objects.create(
            employer_id=self.employer.id,
            component_type=ContractComponentTemplate.COMPONENT_ADVANTAGE,
            code="OT_PAY",
            name="Overtime Pay",
            is_active=True,
        )
        AttendancePayrollImpactConfig.objects.create(
            employer_id=self.employer.id,
            event_code=AttendancePayrollImpactConfig.EVENT_OVERTIME,
            affects_payroll=True,
            bucket=AttendancePayrollImpactConfig.BUCKET_ADVANTAGE,
            target_code="OT_PAY",
            target_name="Overtime Pay",
            calc_method=AttendancePayrollImpactConfig.CALC_MULTIPLIER_HOURLY_RATE,
            value=Decimal("1.50"),
            multiplier=Decimal("1.50"),
            requires_validation=True,
            is_active=True,
        )

        check_in = timezone.make_aware(datetime(self.year, self.month, 7, 9, 0, 0))
        check_out = timezone.make_aware(datetime(self.year, self.month, 7, 19, 0, 0))
        self._create_attendance_record(
            check_in_at=check_in,
            check_out_at=check_out,
            expected_minutes=480,
            worked_minutes=600,
            overtime_worked_minutes=120,
            overtime_approved_minutes=120,
        )

        salary = self._run()
        line = SalaryAdvantage.objects.get(salary=salary, code="OT_PAY")
        self.assertEqual(line.name, "Overtime Pay")
        self.assertEqual(line.amount, Decimal("1210"))

    def test_idempotency_rerun_updates_amount_without_duplicates(self):
        overtime_allowance = self._create_allowance(name="Overtime Pay", code="OT_PAY", amount="0")
        AttendancePayrollImpactConfig.objects.create(
            employer_id=self.employer.id,
            event_code=AttendancePayrollImpactConfig.EVENT_OVERTIME,
            affects_payroll=True,
            bucket=AttendancePayrollImpactConfig.BUCKET_ADVANTAGE,
            allowance=overtime_allowance,
            calc_method=AttendancePayrollImpactConfig.CALC_MULTIPLIER_HOURLY_RATE,
            multiplier=Decimal("1.50"),
            value=Decimal("1.50"),
            requires_validation=True,
            is_active=True,
        )

        check_in = timezone.make_aware(datetime(self.year, self.month, 8, 9, 0, 0))
        check_out = timezone.make_aware(datetime(self.year, self.month, 8, 18, 0, 0))
        record = AttendanceRecord.objects.create(
            employer_id=self.employer.id,
            employee=self.employee,
            check_in_at=check_in,
            check_out_at=check_out,
            expected_minutes=480,
            worked_minutes=540,
            overtime_worked_minutes=60,
            overtime_approved_minutes=60,
            status=AttendanceRecord.STATUS_APPROVED,
            mode=AttendanceRecord.MODE_MANUAL,
        )

        first_salary = self._run()
        first_line = SalaryAdvantage.objects.get(salary=first_salary, code="OT_PAY")
        self.assertEqual(first_line.amount, Decimal("605"))
        self.assertEqual(
            PayrollGeneratedItem.objects.filter(
                employer_id=self.employer.id,
                employee=self.employee,
                year=self.year,
                month=self.month,
                source_event_code=AttendancePayrollImpactConfig.EVENT_OVERTIME,
                is_active=True,
            ).count(),
            1,
        )

        record.overtime_worked_minutes = 120
        record.overtime_approved_minutes = 120
        record.save(update_fields=["overtime_worked_minutes", "overtime_approved_minutes", "updated_at"])

        second_salary = self._run()
        second_line = SalaryAdvantage.objects.get(salary=second_salary, code="OT_PAY")
        self.assertEqual(second_line.amount, Decimal("1210"))
        generated_items = PayrollGeneratedItem.objects.filter(
            employer_id=self.employer.id,
            employee=self.employee,
            year=self.year,
            month=self.month,
            source_event_code=AttendancePayrollImpactConfig.EVENT_OVERTIME,
            is_active=True,
        )
        self.assertEqual(generated_items.count(), 1)
        self.assertEqual(generated_items.first().amount, Decimal("1210"))
