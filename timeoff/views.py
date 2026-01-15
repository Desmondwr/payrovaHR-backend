from datetime import date

from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.database_utils import get_tenant_database_alias
from accounts.permissions import IsEmployer
from employees.models import Employee

from .models import (
    TimeOffAccrualSubscription,
    TimeOffAllocation,
    TimeOffAllocationLine,
    TimeOffAllocationRequest,
    TimeOffConfiguration,
    TimeOffLedgerEntry,
    TimeOffRequest,
    TimeOffType,
    ensure_timeoff_configuration,
)
from .serializers import (
    TimeOffAllocationCreateSerializer,
    TimeOffAllocationRequestSerializer,
    TimeOffAllocationSerializer,
    TimeOffBalanceSerializer,
    TimeOffBulkAllocationSerializer,
    TimeOffConfigurationSerializer,
    TimeOffLedgerEntrySerializer,
    TimeOffRequestInputSerializer,
    TimeOffRequestSerializer,
    TimeOffTypeSerializer,
)
from .services import (
    apply_approval_transitions,
    apply_rejection_or_cancellation_transitions,
    apply_submit_transitions,
    compute_balances,
    post_allocation_entries,
    run_accruals_for_subscriptions,
)


def _load_config(employer_id: int, tenant_db: str) -> dict:
    config = ensure_timeoff_configuration(employer_id, tenant_db)
    return config.to_config_dict()


class TimeOffConfigurationViewSet(viewsets.ModelViewSet):
    """
    Manage tenant-specific Time Off configuration (global + leave types).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TimeOffConfigurationSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            return TimeOffConfiguration.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        if hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            return TimeOffConfiguration.objects.using(tenant_db).filter(employer_id=employee.employer_id)
        return TimeOffConfiguration.objects.none()

    def perform_create(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employers can create configurations.")
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save(
            employer_id=self.request.user.employer_profile.id,
            tenant_id=self.request.user.employer_profile.id,
            schema_version=2,
        )
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)
        ensure_timeoff_configuration(instance.employer_id, tenant_db)

    def perform_update(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employers can update configurations.")
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)
        ensure_timeoff_configuration(instance.employer_id, tenant_db)

    @action(detail=False, methods=["get", "patch"], url_path="global")
    def global_config(self, request):
        """
        Singleton-like helper per employer. GET returns config; PATCH updates it.
        Creates a default record if missing.
        """

        if hasattr(request.user, "employer_profile"):
            employer = request.user.employer_profile
            tenant_db = get_tenant_database_alias(employer)
            employer_id = employer.id
        elif hasattr(request.user, "employee_profile") and request.user.employee_profile:
            employee = request.user.employee_profile
            employer_id = employee.employer_id
            tenant_db = employee._state.db or "default"
        else:
            raise permissions.PermissionDenied("Unable to resolve tenant.")

        config = ensure_timeoff_configuration(employer_id, tenant_db)

        if request.method == "PATCH":
            if not hasattr(request.user, "employer_profile"):
                raise permissions.PermissionDenied("Only employers can update configurations.")
            serializer = self.get_serializer(config, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)

        serializer = self.get_serializer(config)
        return Response(serializer.data)


class TimeOffTypeViewSet(viewsets.ModelViewSet):
    """
    CRUD for leave types stored in the new normalized table.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TimeOffTypeSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            ensure_timeoff_configuration(user.employer_profile.id, tenant_db)
            return TimeOffType.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        if hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            ensure_timeoff_configuration(employee.employer_id, tenant_db)
            return TimeOffType.objects.using(tenant_db).filter(employer_id=employee.employer_id)
        return TimeOffType.objects.none()

    def perform_create(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employers can create leave types.")
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    def perform_update(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employers can update leave types.")
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)


class TimeOffRequestViewSet(viewsets.ModelViewSet):
    """
    CRUD + workflows for time off requests (tenant-aware).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return TimeOffRequestInputSerializer
        return TimeOffRequestSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        tenant_db = "default"
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
        elif hasattr(user, "employee_profile") and user.employee_profile:
            tenant_db = user.employee_profile._state.db or "default"
        context["tenant_db"] = tenant_db
        return context

    def get_queryset(self):
        user = self.request.user
        params = self.request.query_params
        status_param = params.get("status")
        leave_type_param = params.get("leave_type_code")
        date_from = params.get("from")
        date_to = params.get("to")
        employee_id = params.get("employee_id")
        scope = params.get("scope")

        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            qs = TimeOffRequest.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        elif hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            qs = TimeOffRequest.objects.using(tenant_db).filter(employee=employee)
        else:
            return TimeOffRequest.objects.none()

        if scope == "mine" and hasattr(user, "employee_profile") and user.employee_profile:
            qs = qs.filter(employee=user.employee_profile)
        if status_param:
            qs = qs.filter(status=status_param)
        if leave_type_param:
            qs = qs.filter(leave_type_code=leave_type_param)
        if employee_id and hasattr(user, "employer_profile"):
            qs = qs.filter(employee_id=employee_id)
        if date_from:
            qs = qs.filter(start_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(end_at__date__lte=date_to)
        return qs

    def perform_update(self, serializer):
        instance = serializer.instance
        if hasattr(instance, "is_editable") and not instance.is_editable:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": "Only draft or submitted requests can be edited."})
        serializer.save(updated_by=self.request.user.id)

    def _get_policies(self, request_obj):
        tenant_db = request_obj._state.db or "default"
        config = _load_config(request_obj.employer_id, tenant_db)
        leave_types = config.get("leave_types") or []
        leave_type = next((lt for lt in leave_types if lt.get("code") == request_obj.leave_type_code), {})
        global_settings = config.get("global_settings") or {}
        reservation_policy = (
            leave_type.get("reservation_policy")
            or global_settings.get("reservation_policy")
            or "RESERVE_ON_SUBMIT"
        )
        approval_policy = leave_type.get("approval_policy") or {}
        return reservation_policy, approval_policy, tenant_db

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        req_obj = self.get_object()
        if req_obj.status not in ["DRAFT", "SUBMITTED", "PENDING"]:
            return Response({"detail": "Request cannot be submitted from current status."}, status=status.HTTP_400_BAD_REQUEST)
        reservation_policy, approval_policy, tenant_db = self._get_policies(req_obj)
        apply_submit_transitions(
            request=req_obj,
            duration_minutes=req_obj.duration_minutes,
            reservation_policy=reservation_policy,
            created_by=request.user.id,
            db_alias=tenant_db,
            effective_date=req_obj.start_at.date(),
        )
        if approval_policy.get("auto_approve"):
            apply_approval_transitions(
                request=req_obj,
                duration_minutes=req_obj.duration_minutes,
                reservation_policy=reservation_policy,
                created_by=request.user.id,
                db_alias=tenant_db,
                effective_date=req_obj.start_at.date(),
            )
        serializer = TimeOffRequestSerializer(req_obj, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        if not hasattr(request.user, "employer_profile"):
            return Response({"detail": "Only employer users can approve requests."}, status=status.HTTP_403_FORBIDDEN)
        req_obj = self.get_object()
        if req_obj.status == "APPROVED":
            serializer = TimeOffRequestSerializer(req_obj, context=self.get_serializer_context())
            return Response(serializer.data)
        reservation_policy, _, tenant_db = self._get_policies(req_obj)
        apply_approval_transitions(
            request=req_obj,
            duration_minutes=req_obj.duration_minutes,
            reservation_policy=reservation_policy,
            created_by=request.user.id,
            db_alias=tenant_db,
            effective_date=req_obj.start_at.date(),
        )
        serializer = TimeOffRequestSerializer(req_obj, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        if not hasattr(request.user, "employer_profile"):
            return Response({"detail": "Only employer users can reject requests."}, status=status.HTTP_403_FORBIDDEN)
        req_obj = self.get_object()
        reservation_policy, _, tenant_db = self._get_policies(req_obj)
        apply_rejection_or_cancellation_transitions(
            request=req_obj,
            duration_minutes=req_obj.duration_minutes,
            reservation_policy=reservation_policy,
            created_by=request.user.id,
            db_alias=tenant_db,
            effective_date=req_obj.start_at.date(),
            cancelled=False,
        )
        serializer = TimeOffRequestSerializer(req_obj, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        req_obj = self.get_object()
        reservation_policy, _, tenant_db = self._get_policies(req_obj)
        apply_rejection_or_cancellation_transitions(
            request=req_obj,
            duration_minutes=req_obj.duration_minutes,
            reservation_policy=reservation_policy,
            created_by=request.user.id,
            db_alias=tenant_db,
            effective_date=req_obj.start_at.date(),
            cancelled=True,
        )
        serializer = TimeOffRequestSerializer(req_obj, context=self.get_serializer_context())
        return Response(serializer.data)


class TimeOffBalanceViewSet(viewsets.ViewSet):
    """
    Read-only balances per leave type for an employee.
    """

    permission_classes = [permissions.IsAuthenticated]

    def _get_context(self, request):
        user = request.user
        employee = None
        tenant_db = "default"
        employer_id = None

        # Employer admin: allow employee_id param
        if hasattr(user, "employer_profile"):
            employer_id = user.employer_profile.id
            tenant_db = get_tenant_database_alias(user.employer_profile)
            employee_id = request.query_params.get("employee_id")
            if employee_id:
                employee = Employee.objects.using(tenant_db).filter(id=employee_id).first()
            else:
                raise permissions.PermissionDenied("employee_id is required for employer balance lookup.")
        elif hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            employer_id = employee.employer_id

        if not employee:
            raise permissions.PermissionDenied("Unable to resolve employee for balance lookup.")

        return employee, employer_id, tenant_db

    def list(self, request):
        employee, employer_id, tenant_db = self._get_context(request)

        config = _load_config(employer_id, tenant_db)
        global_settings = config.get("global_settings") or {}
        reservation_policy = global_settings.get("reservation_policy") or "RESERVE_ON_SUBMIT"
        as_of_param = request.query_params.get("as_of")
        as_of_date = None
        if as_of_param:
            try:
                as_of_date = date.fromisoformat(as_of_param)
            except ValueError:
                raise permissions.PermissionDenied("Invalid as_of date format. Use YYYY-MM-DD.")
        reservation_map = {}
        for lt in config.get("leave_types") or []:
            policy = lt.get("reservation_policy") or reservation_policy
            reservation_map[lt.get("code")] = policy

        entries = TimeOffLedgerEntry.objects.using(tenant_db).filter(employee=employee)
        if as_of_date:
            entries = entries.filter(effective_date__lte=as_of_date)
        data = TimeOffBalanceSerializer.from_entries(
            entries,
            reservation_policy,
            as_of=as_of_date,
            reservation_policy_by_code=reservation_map,
        )
        return Response(data)


class TimeOffLedgerViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ledger entries with filters for audit/admin.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TimeOffLedgerEntrySerializer

    def get_queryset(self):
        user = self.request.user
        tenant_db = "default"
        employer_id = None
        if hasattr(user, "employer_profile"):
            employer_id = user.employer_profile.id
            tenant_db = get_tenant_database_alias(user.employer_profile)
        elif hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            employer_id = employee.employer_id
            tenant_db = employee._state.db or "default"
        else:
            return TimeOffLedgerEntry.objects.none()

        qs = TimeOffLedgerEntry.objects.using(tenant_db).filter(employer_id=employer_id)

        params = self.request.query_params
        employee_id = params.get("employee_id")
        leave_type_code = params.get("leave_type_code")
        entry_type = params.get("entry_type")
        request_id = params.get("request_id")
        date_from = params.get("from")
        date_to = params.get("to")

        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        if leave_type_code:
            qs = qs.filter(leave_type_code=leave_type_code)
        if entry_type:
            qs = qs.filter(entry_type=entry_type)
        if request_id:
            qs = qs.filter(request_id=request_id)
        if date_from:
            qs = qs.filter(effective_date__gte=date_from)
        if date_to:
            qs = qs.filter(effective_date__lte=date_to)

        return qs


class TimeOffAllocationViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsEmployer]

    def get_serializer_class(self):
        if self.action in ["create"]:
            return TimeOffAllocationCreateSerializer
        if self.action == "bulk":
            return TimeOffBulkAllocationSerializer
        return TimeOffAllocationSerializer

    def get_queryset(self):
        user = self.request.user
        if not hasattr(user, "employer_profile"):
            return TimeOffAllocation.objects.none()
        tenant_db = get_tenant_database_alias(user.employer_profile)
        return TimeOffAllocation.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)

    def perform_create(self, serializer):
        allocation = serializer.save()
        tenant_db = allocation._state.db or "default"
        if allocation._state.db != tenant_db:
            allocation.save(using=tenant_db)

    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk(self, request):
        serializer = TimeOffBulkAllocationSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        allocation = serializer.save()
        output = TimeOffAllocationSerializer(allocation, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        allocation = self.get_object()
        tenant_db = allocation._state.db or "default"
        if allocation.status == "CONFIRMED":
            serializer = TimeOffAllocationSerializer(allocation, context=self.get_serializer_context())
            return Response(serializer.data)
        config = _load_config(allocation.employer_id, tenant_db)
        global_settings = config.get("global_settings") or {}
        working_hours = int(global_settings.get("working_hours_per_day", 8) or 8)
        rounding = global_settings.get("rounding") or {}
        lines = allocation.lines.all()
        post_allocation_entries(
            allocation=allocation,
            lines=lines,
            working_hours=working_hours,
            rounding=rounding,
            created_by=request.user.id,
            db_alias=tenant_db,
        )
        if allocation.allocation_type == "ACCRUAL" and allocation.accrual_plan:
            for line in lines:
                TimeOffAccrualSubscription.objects.using(tenant_db).get_or_create(
                    allocation=allocation,
                    plan=allocation.accrual_plan,
                    employee=line.employee,
                    leave_type_code=allocation.leave_type_code,
                    start_date=allocation.start_date,
                    end_date=allocation.end_date,
                    defaults={"created_by": request.user.id},
                )
        allocation.status = "CONFIRMED"
        allocation.save(using=tenant_db)
        serializer = TimeOffAllocationSerializer(allocation, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        allocation = self.get_object()
        tenant_db = allocation._state.db or "default"
        allocation.status = "CANCELLED"
        allocation.save(using=tenant_db)
        allocation.lines.update(status="CANCELLED")
        serializer = TimeOffAllocationSerializer(allocation, context=self.get_serializer_context())
        return Response(serializer.data)


class TimeOffAllocationRequestViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TimeOffAllocationRequestSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            return TimeOffAllocationRequest.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        if hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            return TimeOffAllocationRequest.objects.using(tenant_db).filter(employee=employee)
        return TimeOffAllocationRequest.objects.none()

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        if not hasattr(request.user, "employer_profile"):
            return Response({"detail": "Only employer users can approve allocation requests."}, status=status.HTTP_403_FORBIDDEN)
        req = self.get_object()
        if req.status != "PENDING":
            serializer = self.get_serializer(req)
            return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
        tenant_db = req._state.db or "default"
        config = _load_config(req.employer_id, tenant_db)
        global_settings = config.get("global_settings") or {}
        working_hours = int(global_settings.get("working_hours_per_day", 8) or 8)
        rounding = global_settings.get("rounding") or {}

        allocation = TimeOffAllocation.objects.using(tenant_db).create(
            employer_id=req.employer_id,
            tenant_id=req.tenant_id,
            name=f"Allocation for {req.employee_id}",
            leave_type_code=req.leave_type_code,
            allocation_type="REGULAR",
            amount=req.amount,
            unit=req.unit,
            start_date=date.today(),
            employee=req.employee,
            status="CONFIRMED",
            created_by=request.user.id,
        )
        line = TimeOffAllocationLine.objects.using(tenant_db).create(
            allocation=allocation,
            employee=req.employee,
            status="CONFIRMED",
        )
        post_allocation_entries(
            allocation=allocation,
            lines=[line],
            working_hours=working_hours,
            rounding=rounding,
            created_by=request.user.id,
            db_alias=tenant_db,
        )
        req.status = "APPROVED"
        req.acted_at = timezone.now()
        req.acted_by = request.user.id
        req.save(using=tenant_db)
        serializer = self.get_serializer(req)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        if not hasattr(request.user, "employer_profile"):
            return Response({"detail": "Only employer users can reject allocation requests."}, status=status.HTTP_403_FORBIDDEN)
        req = self.get_object()
        if req.status != "PENDING":
            serializer = self.get_serializer(req)
            return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
        tenant_db = req._state.db or "default"
        req.status = "REJECTED"
        req.acted_at = timezone.now()
        req.acted_by = request.user.id
        req.save(using=tenant_db)
        serializer = self.get_serializer(req)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        req = self.get_object()
        if req.status not in ["PENDING", "APPROVED"]:
            serializer = self.get_serializer(req)
            return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
        tenant_db = req._state.db or "default"
        req.status = "CANCELLED"
        req.acted_at = timezone.now()
        req.acted_by = request.user.id
        req.save(using=tenant_db)
        serializer = self.get_serializer(req)
        return Response(serializer.data)


class AccrualRunViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated, IsEmployer]

    def create(self, request):
        run_date_param = request.data.get("run_date")
        upto = date.fromisoformat(run_date_param) if run_date_param else date.today()
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        run_accruals_for_subscriptions(
            upto_date=upto,
            created_by=request.user.id,
            db_alias=tenant_db,
        )
        return Response({"status": "ok", "run_date": str(upto)})
