from datetime import date, datetime, time as dtime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from rest_framework import serializers

from employees.models import Employee
from timeoff.models import (
    TimeOffAllocation,
    TimeOffAllocationLine,
    TimeOffConfiguration,
    TimeOffLedgerEntry,
    TimeOffRequest,
    TimeOffType,
    ensure_timeoff_configuration,
)
from timeoff.serializers import TimeOffRequestInputSerializer
from timeoff.services import (
    apply_approval_transitions,
    apply_rejection_or_cancellation_transitions,
    apply_submit_transitions,
    calculate_duration_minutes,
    post_allocation_entries,
    round_minutes,
)


class TimeOffFeatureTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        User = get_user_model()
        self.employer_user = User.objects.create_user(
            email="employer@example.com",
            password="pass",
            is_employer=True,
        )
        from accounts.models import EmployerProfile

        self.employer_profile = EmployerProfile.objects.create(
            user=self.employer_user,
            company_name="Acme Corp",
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

        self.employee_user = User.objects.create_user(
            email="employee@example.com",
            password="pass",
            is_employee=True,
        )
        self.employee = Employee.objects.create(
            employer_id=self.employer_profile.id,
            user_id=self.employee_user.id,
            employee_id="E1",
            first_name="Jane",
            last_name="Doe",
            email="employee@example.com",
            job_title="Engineer",
            employment_type="FULL_TIME",
            hire_date=date.today(),
        )
        # Cache to avoid property lookups
        self.employee_user._employee_profile_cache = self.employee

    def _request_context(self, user):
        req = self.factory.post("/fake")
        req.user = user
        return {"request": req, "tenant_db": "default"}

    def _basic_payload(self, **overrides):
        base = {
            "leave_type_code": "ANL",
            "start_date": date.today().isoformat(),
            "end_date": date.today().isoformat(),
            "description": "Test request",
        }
        base.update(overrides)
        return base

    def test_full_day_duration_excludes_weekends(self):
        # Find a Friday to span a weekend (Fri->Mon = 2 working days)
        start = date.today()
        while start.weekday() != 4:
            start += timedelta(days=1)
        end = start + timedelta(days=3)
        start_at, end_at, minutes, days = calculate_duration_minutes(
            start_date=start,
            end_date=end,
            half_day=False,
            half_day_period=None,
            custom_hours=False,
            from_time_val=None,
            to_time_val=None,
            working_hours_per_day=8,
            weekend_days=["SATURDAY", "SUNDAY"],
            count_weekends_as_leave=False,
            rounding={"increment_minutes": 30, "method": "NEAREST"},
        )
        self.assertEqual(minutes, 8 * 60 * 2)
        self.assertEqual(days, 2.0)
        self.assertEqual(start_at.date(), start)
        self.assertEqual(end_at.date(), end)

    def test_half_day_and_custom_hours_duration(self):
        _, _, half_minutes, half_days = calculate_duration_minutes(
            start_date=date.today(),
            end_date=None,
            half_day=True,
            half_day_period="MORNING",
            custom_hours=False,
            from_time_val=None,
            to_time_val=None,
            working_hours_per_day=8,
            weekend_days=[],
            count_weekends_as_leave=True,
            rounding={"increment_minutes": 30, "method": "NEAREST"},
        )
        self.assertEqual(half_minutes, 4 * 60)
        self.assertEqual(half_days, 0.5)

        _, _, custom_minutes, custom_days = calculate_duration_minutes(
            start_date=date.today(),
            end_date=None,
            half_day=False,
            half_day_period=None,
            custom_hours=True,
            from_time_val=dtime(hour=9, minute=0),
            to_time_val=dtime(hour=12, minute=30),
            working_hours_per_day=8,
            weekend_days=[],
            count_weekends_as_leave=True,
            rounding={"increment_minutes": 30, "method": "NEAREST"},
        )
        self.assertEqual(custom_minutes, 210)
        self.assertAlmostEqual(custom_days, 210 / (8 * 60))

    def test_rounding_methods(self):
        self.assertEqual(round_minutes(61, {"increment_minutes": 30, "method": "NEAREST"}), 60)
        self.assertEqual(round_minutes(61, {"increment_minutes": 30, "method": "UP"}), 90)
        self.assertEqual(round_minutes(61, {"increment_minutes": 30, "method": "DOWN"}), 60)

    def test_overlap_validation_blocks_new_request(self):
        existing = TimeOffRequest.objects.create(
            employer_id=self.employer_profile.id,
            tenant_id=self.employer_profile.id,
            employee=self.employee,
            leave_type_code="ANL",
            start_at=datetime.combine(date.today(), dtime.min),
            end_at=datetime.combine(date.today(), dtime.max),
            duration_minutes=8 * 60,
            status="APPROVED",
            created_by=self.employee_user.id,
            updated_by=self.employee_user.id,
        )
        payload = self._basic_payload()
        serializer = TimeOffRequestInputSerializer(
            data=payload,
            context=self._request_context(self.employee_user),
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_backdated_and_document_validation(self):
        config = ensure_timeoff_configuration(self.employer_profile.id, "default")
        config.allow_backdated_requests = False
        config.save()
        leave_type = TimeOffType.objects.get(employer_id=self.employer_profile.id, code="ANL")
        leave_type.request_requires_document = True
        leave_type.save()
        payload = self._basic_payload(start_date=(date.today() - timedelta(days=1)).isoformat(), leave_type_code="ANL")
        serializer = TimeOffRequestInputSerializer(
            data=payload,
            context=self._request_context(self.employee_user),
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_ledger_posting_flow_is_idempotent(self):
        req = TimeOffRequest.objects.create(
            employer_id=self.employer_profile.id,
            tenant_id=self.employer_profile.id,
            employee=self.employee,
            leave_type_code="ANL",
            start_at=datetime.combine(date.today(), dtime.min),
            end_at=datetime.combine(date.today(), dtime.max),
            duration_minutes=120,
            status="DRAFT",
            created_by=self.employer_user.id,
            updated_by=self.employer_user.id,
        )
        apply_submit_transitions(
            request=req,
            duration_minutes=req.duration_minutes,
            reservation_policy="RESERVE_ON_SUBMIT",
            created_by=self.employer_user.id,
            db_alias="default",
            effective_date=req.start_at.date(),
        )
        self.assertEqual(
            TimeOffLedgerEntry.objects.filter(request=req, entry_type="RESERVATION").count(),
            1,
        )
        apply_approval_transitions(
            request=req,
            duration_minutes=req.duration_minutes,
            reservation_policy="RESERVE_ON_SUBMIT",
            created_by=self.employer_user.id,
            db_alias="default",
            effective_date=req.start_at.date(),
        )
        apply_approval_transitions(  # repeat to ensure no duplicates
            request=req,
            duration_minutes=req.duration_minutes,
            reservation_policy="RESERVE_ON_SUBMIT",
            created_by=self.employer_user.id,
            db_alias="default",
            effective_date=req.start_at.date(),
        )
        self.assertEqual(
            TimeOffLedgerEntry.objects.filter(request=req, entry_type="DEBIT").count(),
            1,
        )
        self.assertEqual(
            TimeOffLedgerEntry.objects.filter(request=req, entry_type="REVERSAL").count(),
            1,
        )
        req2 = TimeOffRequest.objects.create(
            employer_id=self.employer_profile.id,
            tenant_id=self.employer_profile.id,
            employee=self.employee,
            leave_type_code="ANL",
            start_at=datetime.combine(date.today(), dtime.min),
            end_at=datetime.combine(date.today(), dtime.max),
            duration_minutes=120,
            status="DRAFT",
            created_by=self.employer_user.id,
            updated_by=self.employer_user.id,
        )
        apply_submit_transitions(
            request=req2,
            duration_minutes=req2.duration_minutes,
            reservation_policy="RESERVE_ON_SUBMIT",
            created_by=self.employer_user.id,
            db_alias="default",
            effective_date=req2.start_at.date(),
        )
        apply_rejection_or_cancellation_transitions(
            request=req2,
            duration_minutes=req2.duration_minutes,
            reservation_policy="RESERVE_ON_SUBMIT",
            created_by=self.employer_user.id,
            db_alias="default",
            effective_date=req2.start_at.date(),
            cancelled=True,
        )
        self.assertEqual(
            TimeOffLedgerEntry.objects.filter(request=req2, entry_type="REVERSAL").count(),
            1,
        )

    def test_allocation_confirm_posts_ledger_and_bulk_counts(self):
        allocation = TimeOffAllocation.objects.create(
            employer_id=self.employer_profile.id,
            tenant_id=self.employer_profile.id,
            name="Grant",
            leave_type_code="ANL",
            allocation_type="REGULAR",
            amount=2,
            unit="DAYS",
            start_date=date.today(),
            created_by=self.employer_user.id,
        )
        line1 = TimeOffAllocationLine.objects.create(allocation=allocation, employee=self.employee, status="DRAFT")
        working_hours = 8
        rounding = {"increment_minutes": 30, "method": "NEAREST"}
        post_allocation_entries(
            allocation=allocation,
            lines=[line1],
            working_hours=working_hours,
            rounding=rounding,
            created_by=self.employer_user.id,
            db_alias="default",
        )
        self.assertEqual(
            TimeOffLedgerEntry.objects.filter(allocation=allocation, entry_type="ALLOCATION").count(),
            1,
        )
        # Bulk with two employees
        emp2 = Employee.objects.create(
            employer_id=self.employer_profile.id,
            employee_id="E2",
            first_name="John",
            last_name="Smith",
            email="john@example.com",
            job_title="Engineer",
            employment_type="FULL_TIME",
            hire_date=date.today(),
        )
        allocation_bulk = TimeOffAllocation.objects.create(
            employer_id=self.employer_profile.id,
            tenant_id=self.employer_profile.id,
            name="Bulk",
            leave_type_code="ANL",
            allocation_type="REGULAR",
            amount=1,
            unit="DAYS",
            start_date=date.today(),
            created_by=self.employer_user.id,
        )
        l1 = TimeOffAllocationLine.objects.create(allocation=allocation_bulk, employee=self.employee, status="DRAFT")
        l2 = TimeOffAllocationLine.objects.create(allocation=allocation_bulk, employee=emp2, status="DRAFT")
        post_allocation_entries(
            allocation=allocation_bulk,
            lines=[l1, l2],
            working_hours=working_hours,
            rounding=rounding,
            created_by=self.employer_user.id,
            db_alias="default",
        )
        self.assertEqual(
            TimeOffLedgerEntry.objects.filter(allocation=allocation_bulk, entry_type="ALLOCATION").count(),
            2,
        )

    def test_tenant_isolation_blocks_other_employer_employee(self):
        other_emp = Employee.objects.create(
            employer_id=999,
            first_name="Other",
            last_name="User",
            email="other@example.com",
            job_title="Analyst",
            employment_type="FULL_TIME",
            hire_date=date.today(),
        )
        payload = self._basic_payload(employee=other_emp.id)
        serializer = TimeOffRequestInputSerializer(
            data=payload,
            context=self._request_context(self.employer_user),
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)
