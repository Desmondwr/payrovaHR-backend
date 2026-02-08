from datetime import date

from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.database_utils import get_tenant_database_alias
from accounts.permissions import EmployerAccessPermission, EmployerOrEmployeeAccessPermission
from accounts.rbac import get_active_employer, is_delegate_user, get_delegate_scope, apply_scope_filter
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
from .notifications import (
    notify_timeoff_request_submitted,
    notify_timeoff_request_approved,
    notify_timeoff_request_rejected,
    notify_timeoff_request_cancelled,
    notify_allocation_request_submitted,
    notify_allocation_request_approved,
    notify_allocation_request_rejected,
    notify_allocation_request_cancelled,
)


def _load_config(employer_id: int, tenant_db: str) -> dict:
    config = ensure_timeoff_configuration(employer_id, tenant_db)
    return config.to_config_dict()


class TimeOffConfigurationViewSet(viewsets.ModelViewSet):
    """
    Manage tenant-specific Time Off configuration (global + leave types).
    """

    permission_classes = [permissions.IsAuthenticated, EmployerOrEmployeeAccessPermission]
    permission_map = {
        "list": ["timeoff.configuration.view", "timeoff.manage"],
        "retrieve": ["timeoff.configuration.view", "timeoff.manage"],
        "create": ["timeoff.configuration.update", "timeoff.manage"],
        "update": ["timeoff.configuration.update", "timeoff.manage"],
        "partial_update": ["timeoff.configuration.update", "timeoff.manage"],
        "destroy": ["timeoff.configuration.update", "timeoff.manage"],
        "global_config": ["timeoff.configuration.update", "timeoff.manage"],
        "*": ["timeoff.manage"],
    }
    serializer_class = TimeOffConfigurationSerializer

    def get_queryset(self):
        user = self.request.user
        employer = None
        if getattr(user, "employer_profile", None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved
        if employer:
            tenant_db = get_tenant_database_alias(employer)
            return TimeOffConfiguration.objects.using(tenant_db).filter(employer_id=employer.id)
        if hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            return TimeOffConfiguration.objects.using(tenant_db).filter(employer_id=employee.employer_id)
        return TimeOffConfiguration.objects.none()

    def perform_create(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        user = self.request.user
        if not (
            getattr(user, "employer_profile", None)
            or user.is_admin
            or user.is_superuser
            or is_delegate_user(user, employer.id)
        ):
            raise PermissionDenied("Only employers can create configurations.")
        tenant_db = get_tenant_database_alias(employer)
        serializer.save(
            employer_id=employer.id,
            tenant_id=employer.id,
            schema_version=2,
        )
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)
        ensure_timeoff_configuration(instance.employer_id, tenant_db)

    def perform_update(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        user = self.request.user
        if not (
            getattr(user, "employer_profile", None)
            or user.is_admin
            or user.is_superuser
            or is_delegate_user(user, employer.id)
        ):
            raise PermissionDenied("Only employers can update configurations.")
        tenant_db = get_tenant_database_alias(employer)
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

        employer = None
        if getattr(request.user, "employer_profile", None):
            employer = request.user.employer_profile
        else:
            resolved = get_active_employer(request, require_context=False)
            if resolved and (request.user.is_admin or request.user.is_superuser or is_delegate_user(request.user, resolved.id)):
                employer = resolved

        if employer:
            tenant_db = get_tenant_database_alias(employer)
            employer_id = employer.id
        elif hasattr(request.user, "employee_profile") and request.user.employee_profile:
            employee = request.user.employee_profile
            employer_id = employee.employer_id
            tenant_db = employee._state.db or "default"
        else:
            raise PermissionDenied("Unable to resolve tenant.")

        config = ensure_timeoff_configuration(employer_id, tenant_db)

        if request.method == "PATCH":
            user = request.user
            if not employer or not (
                getattr(user, "employer_profile", None)
                or user.is_admin
                or user.is_superuser
                or is_delegate_user(user, employer.id)
            ):
                raise PermissionDenied("Only employers can update configurations.")
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

    permission_classes = [permissions.IsAuthenticated, EmployerOrEmployeeAccessPermission]
    permission_map = {
        "list": ["timeoff.type.view", "timeoff.manage"],
        "retrieve": ["timeoff.type.view", "timeoff.manage"],
        "create": ["timeoff.type.create", "timeoff.manage"],
        "update": ["timeoff.type.update", "timeoff.manage"],
        "partial_update": ["timeoff.type.update", "timeoff.manage"],
        "destroy": ["timeoff.type.delete", "timeoff.manage"],
        "*": ["timeoff.manage"],
    }
    serializer_class = TimeOffTypeSerializer

    def get_queryset(self):
        user = self.request.user
        employer = None
        if getattr(user, "employer_profile", None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved
        if employer:
            tenant_db = get_tenant_database_alias(employer)
            ensure_timeoff_configuration(employer.id, tenant_db)
            return TimeOffType.objects.using(tenant_db).filter(employer_id=employer.id)
        if hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            ensure_timeoff_configuration(employee.employer_id, tenant_db)
            return TimeOffType.objects.using(tenant_db).filter(employer_id=employee.employer_id)
        return TimeOffType.objects.none()

    def perform_create(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        user = self.request.user
        if not (
            getattr(user, "employer_profile", None)
            or user.is_admin
            or user.is_superuser
            or is_delegate_user(user, employer.id)
        ):
            raise PermissionDenied("Only employers can create leave types.")
        tenant_db = get_tenant_database_alias(employer)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    def perform_update(self, serializer):
        employer = get_active_employer(self.request, require_context=True)
        user = self.request.user
        if not (
            getattr(user, "employer_profile", None)
            or user.is_admin
            or user.is_superuser
            or is_delegate_user(user, employer.id)
        ):
            raise PermissionDenied("Only employers can update leave types.")
        tenant_db = get_tenant_database_alias(employer)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)


class TimeOffRequestViewSet(viewsets.ModelViewSet):
    """
    CRUD + workflows for time off requests (tenant-aware).
    """

    permission_classes = [permissions.IsAuthenticated, EmployerOrEmployeeAccessPermission]
    permission_map = {
        "list": ["timeoff.request.view", "timeoff.manage"],
        "retrieve": ["timeoff.request.view", "timeoff.manage"],
        "create": ["timeoff.request.create", "timeoff.manage"],
        "update": ["timeoff.request.update", "timeoff.manage"],
        "partial_update": ["timeoff.request.update", "timeoff.manage"],
        "destroy": ["timeoff.request.delete", "timeoff.manage"],
        "submit": ["timeoff.request.submit", "timeoff.manage"],
        "approve": ["timeoff.request.approve", "timeoff.manage"],
        "reject": ["timeoff.request.reject", "timeoff.manage"],
        "cancel": ["timeoff.request.cancel", "timeoff.manage"],
        "*": ["timeoff.manage"],
    }

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return TimeOffRequestInputSerializer
        return TimeOffRequestSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        tenant_db = "default"
        employer = None
        if getattr(user, "employer_profile", None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved
        if employer:
            tenant_db = get_tenant_database_alias(employer)
        elif hasattr(user, "employee_profile") and user.employee_profile:
            tenant_db = user.employee_profile._state.db or "default"
        context["tenant_db"] = tenant_db
        return context

    def perform_create(self, serializer):
        req_obj = serializer.save()
        actor_id = getattr(self.request.user, "id", None)
        if req_obj.status in ["SUBMITTED", "PENDING"]:
            notify_timeoff_request_submitted(req_obj, actor_id=actor_id)
        elif req_obj.status == "APPROVED":
            notify_timeoff_request_submitted(req_obj, actor_id=actor_id)
            notify_timeoff_request_approved(req_obj, actor_id=actor_id, auto=True)

    def get_queryset(self):
        user = self.request.user
        params = self.request.query_params
        status_param = params.get("status")
        leave_type_param = params.get("leave_type_code")
        date_from = params.get("from")
        date_to = params.get("to")
        employee_id = params.get("employee_id")
        scope = params.get("scope")

        employer = None
        if getattr(user, "employer_profile", None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved

        if employer:
            tenant_db = get_tenant_database_alias(employer)
            qs = TimeOffRequest.objects.using(tenant_db).filter(employer_id=employer.id)
            if is_delegate_user(user, employer.id):
                scope_data = get_delegate_scope(user, employer.id)
                qs = apply_scope_filter(
                    qs,
                    scope_data,
                    branch_field="employee__branch_id",
                    department_field="employee__department_id",
                    self_field="employee_id",
                )
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
        if employee_id and employer:
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

    def _revalidate_submission(self, request_obj):
        payload = {
            "leave_type_code": request_obj.leave_type_code,
            "start_date": request_obj.start_at.date().isoformat() if request_obj.start_at else None,
            "end_date": request_obj.end_at.date().isoformat() if request_obj.end_at else None,
            "description": request_obj.description or request_obj.reason or "",
            "attachments": request_obj.attachments or [],
            "submit": True,
        }
        serializer = TimeOffRequestInputSerializer(
            instance=request_obj,
            data=payload,
            context=self.get_serializer_context(),
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        req_obj = self.get_object()
        if req_obj.status not in ["DRAFT", "SUBMITTED", "PENDING"]:
            return Response({"detail": "Request cannot be submitted from current status."}, status=status.HTTP_400_BAD_REQUEST)
        self._revalidate_submission(req_obj)
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
        actor_id = getattr(request.user, "id", None)
        if req_obj.status in ["SUBMITTED", "PENDING"]:
            notify_timeoff_request_submitted(req_obj, actor_id=actor_id)
        elif req_obj.status == "APPROVED":
            notify_timeoff_request_submitted(req_obj, actor_id=actor_id)
            notify_timeoff_request_approved(req_obj, actor_id=actor_id, auto=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="approve", permission_classes=[permissions.IsAuthenticated, EmployerAccessPermission])
    def approve(self, request, pk=None):
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
        notify_timeoff_request_approved(req_obj, actor_id=request.user.id)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="reject", permission_classes=[permissions.IsAuthenticated, EmployerAccessPermission])
    def reject(self, request, pk=None):
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
        notify_timeoff_request_rejected(req_obj, actor_id=request.user.id)
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
        notify_timeoff_request_cancelled(req_obj, actor_id=request.user.id)
        return Response(serializer.data)


class TimeOffBalanceViewSet(viewsets.ViewSet):
    """
    Read-only balances per leave type for an employee.
    """

    permission_classes = [permissions.IsAuthenticated, EmployerOrEmployeeAccessPermission]
    required_permissions = ["timeoff.request.view", "timeoff.manage"]

    def _get_context(self, request):
        user = request.user
        employee = None
        tenant_db = "default"
        employer_id = None

        # Employer admin/delegate: allow employee_id param
        employer = None
        if getattr(user, "employer_profile", None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved

        if employer:
            employer_id = employer.id
            tenant_db = get_tenant_database_alias(employer)
            employee_id = request.query_params.get("employee_id")
            if employee_id:
                employee = Employee.objects.using(tenant_db).filter(id=employee_id).first()
            else:
                raise PermissionDenied("employee_id is required for employer balance lookup.")
            if employee and is_delegate_user(user, employer.id):
                scope = get_delegate_scope(user, employer.id)
                scoped = apply_scope_filter(
                    Employee.objects.using(tenant_db).filter(id=employee.id),
                    scope,
                    branch_field="branch_id",
                    department_field="department_id",
                    self_field="id",
                )
                if not scoped.exists():
                    raise PermissionDenied("Unable to resolve employee for balance lookup.")
        elif hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            employer_id = employee.employer_id

        if not employee:
            raise PermissionDenied("Unable to resolve employee for balance lookup.")

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
                raise PermissionDenied("Invalid as_of date format. Use YYYY-MM-DD.")
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

    permission_classes = [permissions.IsAuthenticated, EmployerOrEmployeeAccessPermission]
    required_permissions = ["timeoff.request.view", "timeoff.manage"]
    serializer_class = TimeOffLedgerEntrySerializer

    def get_queryset(self):
        user = self.request.user
        tenant_db = "default"
        employer_id = None
        employer = None
        if getattr(user, "employer_profile", None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved
        if employer:
            employer_id = employer.id
            tenant_db = get_tenant_database_alias(employer)
        elif hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            employer_id = employee.employer_id
            tenant_db = employee._state.db or "default"
        else:
            return TimeOffLedgerEntry.objects.none()

        qs = TimeOffLedgerEntry.objects.using(tenant_db).filter(employer_id=employer_id)
        if employer and is_delegate_user(user, employer.id):
            scope = get_delegate_scope(user, employer.id)
            qs = apply_scope_filter(
                qs,
                scope,
                branch_field="employee__branch_id",
                department_field="employee__department_id",
                self_field="employee_id",
            )

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
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["timeoff.allocation.view", "timeoff.manage"],
        "retrieve": ["timeoff.allocation.view", "timeoff.manage"],
        "create": ["timeoff.allocation.create", "timeoff.manage"],
        "update": ["timeoff.allocation.update", "timeoff.manage"],
        "partial_update": ["timeoff.allocation.update", "timeoff.manage"],
        "destroy": ["timeoff.allocation.delete", "timeoff.manage"],
        "bulk": ["timeoff.allocation.bulk", "timeoff.manage"],
        "confirm": ["timeoff.allocation.confirm", "timeoff.manage"],
        "cancel": ["timeoff.allocation.cancel", "timeoff.manage"],
        "*": ["timeoff.manage"],
    }

    def get_serializer_class(self):
        if self.action in ["create"]:
            return TimeOffAllocationCreateSerializer
        if self.action == "bulk":
            return TimeOffBulkAllocationSerializer
        return TimeOffAllocationSerializer

    def get_queryset(self):
        user = self.request.user
        employer = None
        if getattr(user, "employer_profile", None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved
        if not employer:
            return TimeOffAllocation.objects.none()
        tenant_db = get_tenant_database_alias(employer)
        qs = TimeOffAllocation.objects.using(tenant_db).filter(employer_id=employer.id)
        if is_delegate_user(user, employer.id):
            scope = get_delegate_scope(user, employer.id)
            qs = apply_scope_filter(
                qs,
                scope,
                branch_field="lines__employee__branch_id",
                department_field="lines__employee__department_id",
                self_field="lines__employee_id",
            )
        return qs

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
    permission_classes = [permissions.IsAuthenticated, EmployerOrEmployeeAccessPermission]
    permission_map = {
        "list": ["timeoff.allocation.view", "timeoff.manage"],
        "retrieve": ["timeoff.allocation.view", "timeoff.manage"],
        "create": ["timeoff.allocation.create", "timeoff.manage"],
        "update": ["timeoff.allocation.update", "timeoff.manage"],
        "partial_update": ["timeoff.allocation.update", "timeoff.manage"],
        "destroy": ["timeoff.allocation.delete", "timeoff.manage"],
        "approve": ["timeoff.allocation.approve", "timeoff.manage"],
        "reject": ["timeoff.allocation.reject", "timeoff.manage"],
        "cancel": ["timeoff.allocation.cancel", "timeoff.manage"],
        "*": ["timeoff.manage"],
    }
    serializer_class = TimeOffAllocationRequestSerializer

    def perform_create(self, serializer):
        allocation_request = serializer.save()
        notify_allocation_request_submitted(allocation_request, actor_id=self.request.user.id)

    def get_queryset(self):
        user = self.request.user
        employer = None
        if getattr(user, "employer_profile", None):
            employer = user.employer_profile
        else:
            resolved = get_active_employer(self.request, require_context=False)
            if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
                employer = resolved
        if employer:
            tenant_db = get_tenant_database_alias(employer)
            qs = TimeOffAllocationRequest.objects.using(tenant_db).filter(employer_id=employer.id)
            if is_delegate_user(user, employer.id):
                scope = get_delegate_scope(user, employer.id)
                qs = apply_scope_filter(
                    qs,
                    scope,
                    branch_field="employee__branch_id",
                    department_field="employee__department_id",
                    self_field="employee_id",
                )
            return qs
        if hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            return TimeOffAllocationRequest.objects.using(tenant_db).filter(employee=employee)
        return TimeOffAllocationRequest.objects.none()

    @action(detail=True, methods=["post"], url_path="approve", permission_classes=[permissions.IsAuthenticated, EmployerAccessPermission])
    def approve(self, request, pk=None):
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
        notify_allocation_request_approved(req, actor_id=request.user.id)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="reject", permission_classes=[permissions.IsAuthenticated, EmployerAccessPermission])
    def reject(self, request, pk=None):
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
        notify_allocation_request_rejected(req, actor_id=request.user.id)
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
        notify_allocation_request_cancelled(req, actor_id=request.user.id)
        return Response(serializer.data)


class AccrualRunViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["timeoff.accrual.run", "timeoff.manage"]

    def create(self, request):
        run_date_param = request.data.get("run_date")
        upto = date.fromisoformat(run_date_param) if run_date_param else date.today()
        employer = get_active_employer(request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        run_accruals_for_subscriptions(
            upto_date=upto,
            created_by=request.user.id,
            db_alias=tenant_db,
        )
        return Response({"status": "ok", "run_date": str(upto)})
