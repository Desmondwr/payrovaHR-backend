from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from accounts.permissions import IsEmployer
from accounts.database_utils import get_tenant_database_alias
from employees.models import Employee
from .models import TimeOffConfiguration, TimeOffRequest, TimeOffLedgerEntry
from .serializers import (
    TimeOffConfigurationSerializer,
    TimeOffRequestSerializer,
    TimeOffBalanceSerializer,
    TimeOffLedgerEntrySerializer,
)
from .defaults import merge_time_off_defaults, get_time_off_defaults
from .services import (
    apply_submit_transitions,
    apply_approval_transitions,
    apply_rejection_or_cancellation_transitions,
)


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
        serializer.save(employer_id=self.request.user.employer_profile.id)
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    def perform_update(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employers can update configurations.")
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

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

        config, created = TimeOffConfiguration.objects.using(tenant_db).get_or_create(
            employer_id=employer_id,
            defaults={"configuration": merge_time_off_defaults({})},
        )

        if request.method == "PATCH":
            if not hasattr(request.user, "employer_profile"):
                raise permissions.PermissionDenied("Only employers can update configurations.")
            serializer = self.get_serializer(config, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)

        serializer = self.get_serializer(config)
        return Response(serializer.data)


class TimeOffRequestViewSet(viewsets.ModelViewSet):
    """
    Basic CRUD for time off requests (tenant-aware).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TimeOffRequestSerializer

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
        # Employer access: all requests for their tenant
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            return TimeOffRequest.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)

        # Employee access: own requests
        if hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            return TimeOffRequest.objects.using(tenant_db).filter(employee=employee)

        return TimeOffRequest.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        if not hasattr(user, "employer_profile") and not hasattr(user, "employee_profile"):
            raise permissions.PermissionDenied("Unable to resolve tenant.")

        employee_obj = None
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            employer_id = user.employer_profile.id
            # Employer must provide employee explicitly
            employee_id = self.request.data.get("employee") or self.request.data.get("employee_id")
            if not employee_id:
                raise permissions.PermissionDenied("employee is required.")
            employee_obj = Employee.objects.using(tenant_db).filter(id=employee_id, employer_id=employer_id).first()
            if not employee_obj:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"employee": ["Invalid employee for this tenant."]})
        else:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            employer_id = employee.employer_id
            employee_obj = employee

        serializer.save(
            employer_id=employer_id,
            employee=employee_obj,
            created_by=user.id,
            updated_by=user.id,
        )
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    def perform_update(self, serializer):
        instance = serializer.instance
        if hasattr(instance, "is_editable") and not instance.is_editable:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": "Only draft or submitted requests can be edited."})

        serializer.save(updated_by=self.request.user.id)

    def _get_reservation_policy(self, tenant_db, employer_id):
        config_obj = TimeOffConfiguration.objects.using(tenant_db).filter(employer_id=employer_id).first()
        if config_obj:
            config = config_obj.configuration or {}
        else:
            config = get_time_off_defaults()
        return (config.get("global_settings") or {}).get("reservation_policy") or "RESERVE_ON_SUBMIT"

    def _get_duration_minutes(self, request_obj):
        return request_obj.duration_minutes or 0

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        req_obj = self.get_object()
        tenant_db = req_obj._state.db or "default"
        policy = self._get_reservation_policy(tenant_db, req_obj.employer_id)
        duration = self._get_duration_minutes(req_obj)
        apply_submit_transitions(
            request=req_obj,
            duration_minutes=duration,
            reservation_policy=policy,
            created_by=request.user.id,
            db_alias=tenant_db,
            effective_date=req_obj.start_at.date(),
        )
        serializer = self.get_serializer(req_obj)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        req_obj = self.get_object()
        tenant_db = req_obj._state.db or "default"
        policy = self._get_reservation_policy(tenant_db, req_obj.employer_id)
        duration = self._get_duration_minutes(req_obj)
        apply_approval_transitions(
            request=req_obj,
            duration_minutes=duration,
            reservation_policy=policy,
            created_by=request.user.id,
            db_alias=tenant_db,
            effective_date=req_obj.start_at.date(),
        )
        serializer = self.get_serializer(req_obj)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        req_obj = self.get_object()
        tenant_db = req_obj._state.db or "default"
        policy = self._get_reservation_policy(tenant_db, req_obj.employer_id)
        duration = self._get_duration_minutes(req_obj)
        apply_rejection_or_cancellation_transitions(
            request=req_obj,
            duration_minutes=duration,
            reservation_policy=policy,
            created_by=request.user.id,
            db_alias=tenant_db,
            effective_date=req_obj.start_at.date(),
            cancelled=False,
        )
        serializer = self.get_serializer(req_obj)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        req_obj = self.get_object()
        tenant_db = req_obj._state.db or "default"
        policy = self._get_reservation_policy(tenant_db, req_obj.employer_id)
        duration = self._get_duration_minutes(req_obj)
        apply_rejection_or_cancellation_transitions(
            request=req_obj,
            duration_minutes=duration,
            reservation_policy=policy,
            created_by=request.user.id,
            db_alias=tenant_db,
            effective_date=req_obj.start_at.date(),
            cancelled=True,
        )
        serializer = self.get_serializer(req_obj)
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
                # If no employee_id, deny to avoid returning all employees
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

        # Reservation policy from config (fallback to defaults)
        config_obj = TimeOffConfiguration.objects.using(tenant_db).filter(employer_id=employer_id).first()
        if config_obj:
            config = config_obj.configuration or {}
        else:
            config = get_time_off_defaults()

        reservation_policy = (
            (config.get("global_settings") or {}).get("reservation_policy") or "RESERVE_ON_SUBMIT"
        )

        entries = TimeOffLedgerEntry.objects.using(tenant_db).filter(employee=employee)
        data = TimeOffBalanceSerializer.from_entries(entries, reservation_policy)
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
