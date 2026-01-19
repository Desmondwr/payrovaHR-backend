from collections import defaultdict
import uuid

from django.db import models
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.database_utils import get_tenant_database_alias
from accounts.permissions import IsAuthenticated, IsEmployer
from employees.models import Employee

from .models import (
    AttendanceAllowedWifi,
    AttendanceConfiguration,
    AttendanceLocationSite,
    AttendanceKioskStation,
    AttendanceRecord,
    WorkingSchedule,
    WorkingScheduleDay,
)
from .serializers import (
    AttendanceAllowedWifiSerializer,
    AttendanceCheckInSerializer,
    AttendanceCheckOutSerializer,
    AttendanceConfigurationSerializer,
    AttendanceLocationSiteSerializer,
    AttendanceManualCreateSerializer,
    AttendanceRecordSerializer,
    AttendanceReportQuerySerializer,
    AttendanceKioskStationSerializer,
    KioskCheckSerializer,
    PartialApproveSerializer,
    WorkingScheduleDaySerializer,
    WorkingScheduleSerializer,
)
from .services import (
    ensure_attendance_configuration,
    perform_check_in,
    perform_check_out,
    resolve_station_by_token,
    resolve_configuration_by_kiosk_token,
    resolve_expected_minutes,
    is_employee_on_leave,
)


def _get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _employee_from_request(request, tenant_db=None) -> Employee:
    if hasattr(request.user, "employee_profile") and request.user.employee_profile:
        return request.user.employee_profile
    employee_id = request.data.get("employee_id") or request.query_params.get("employee_id")
    if hasattr(request.user, "employer_profile") and employee_id:
        employer = request.user.employer_profile
        db_alias = tenant_db or get_tenant_database_alias(employer)
        return Employee.objects.using(db_alias).filter(id=employee_id, employer_id=employer.id).first()
    return None


class AttendanceConfigurationViewSet(viewsets.ModelViewSet):
    """Tenant-scoped attendance configuration."""

    permission_classes = [IsAuthenticated]
    serializer_class = AttendanceConfigurationSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            return AttendanceConfiguration.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        if hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            return AttendanceConfiguration.objects.using(tenant_db).filter(employer_id=employee.employer_id)
        return AttendanceConfiguration.objects.none()

    def perform_create(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employer users can create configurations.")
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        serializer.save(employer_id=employer.id)
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    def perform_update(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employer users can update configurations.")
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)


class KioskTokenRegenerateView(APIView):
    """Rotate kiosk access token for the employer."""

    permission_classes = [permissions.IsAuthenticated, IsEmployer]

    def post(self, request):
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        config = ensure_attendance_configuration(employer.id, tenant_db)
        config.kiosk_access_token = uuid.uuid4().hex
        config.save(using=tenant_db, update_fields=["kiosk_access_token", "updated_at"])
        return Response(
            {
                "kiosk_access_token": config.kiosk_access_token,
            },
            status=status.HTTP_200_OK,
        )


class AttendanceLocationSiteViewSet(viewsets.ModelViewSet):
    """Manage allowed geofence sites."""

    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = AttendanceLocationSiteSerializer

    def get_queryset(self):
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        return AttendanceLocationSite.objects.using(tenant_db).filter(employer_id=employer.id)

    def perform_create(self, serializer):
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        instance = AttendanceLocationSite.objects.using(tenant_db).create(
            employer_id=employer.id, **serializer.validated_data
        )
        serializer.instance = instance

    def perform_destroy(self, instance):
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        instance.delete(using=tenant_db)


class AttendanceAllowedWifiViewSet(viewsets.ModelViewSet):
    """Manage allowed Wi-Fi networks."""

    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = AttendanceAllowedWifiSerializer

    def get_queryset(self):
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        return AttendanceAllowedWifi.objects.using(tenant_db).filter(employer_id=employer.id)

    def perform_create(self, serializer):
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        instance = AttendanceAllowedWifi.objects.using(tenant_db).create(
            employer_id=employer.id, **serializer.validated_data
        )
        serializer.instance = instance

    def perform_destroy(self, instance):
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        instance.delete(using=tenant_db)


class AttendanceKioskStationViewSet(viewsets.ModelViewSet):
    """Manage branch-scoped kiosk stations."""

    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = AttendanceKioskStationSerializer

    def get_queryset(self):
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        return AttendanceKioskStation.objects.using(tenant_db).filter(employer_id=employer.id)

    def perform_create(self, serializer):
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        instance = AttendanceKioskStation.objects.using(tenant_db).create(
            employer_id=employer.id, **serializer.validated_data
        )
        serializer.instance = instance

    def perform_update(self, serializer):
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    def perform_destroy(self, instance):
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        instance.delete(using=tenant_db)


class WorkingScheduleViewSet(viewsets.ModelViewSet):
    """Manage working schedules and their day rules."""

    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = WorkingScheduleSerializer

    def get_queryset(self):
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        return WorkingSchedule.objects.using(tenant_db).filter(employer_id=employer.id)

    def perform_create(self, serializer):
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        serializer.save(employer_id=employer.id)
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    def perform_update(self, serializer):
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    def perform_destroy(self, instance):
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        instance.delete(using=tenant_db)

    def _get_schedule(self):
        employer = self.request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        try:
            return WorkingSchedule.objects.using(tenant_db).get(id=self.kwargs.get("pk"), employer_id=employer.id)
        except WorkingSchedule.DoesNotExist:
            raise permissions.PermissionDenied("Schedule not found for this employer.")

    @action(detail=True, methods=["get", "post"], url_path="days")
    def days(self, request, pk=None):
        schedule = self._get_schedule()
        tenant_db = get_tenant_database_alias(request.user.employer_profile)

        if request.method.lower() == "get":
            qs = WorkingScheduleDay.objects.using(tenant_db).filter(schedule=schedule)
            data = WorkingScheduleDaySerializer(qs, many=True).data
            return Response(data)

        serializer = WorkingScheduleDaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        weekday = serializer.validated_data.get("weekday")
        if WorkingScheduleDay.objects.using(tenant_db).filter(schedule=schedule, weekday=weekday).exists():
            return Response(
                {"weekday": "A day rule for this weekday already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        day = WorkingScheduleDay.objects.using(tenant_db).create(
            schedule=schedule,
            weekday=serializer.validated_data["weekday"],
            start_time=serializer.validated_data["start_time"],
            end_time=serializer.validated_data["end_time"],
            break_minutes=serializer.validated_data.get("break_minutes", 0),
        )
        return Response(WorkingScheduleDaySerializer(day).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "patch", "delete"], url_path="days/(?P<day_id>[^/.]+)")
    def day_detail(self, request, pk=None, day_id=None):
        schedule = self._get_schedule()
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        try:
            day = WorkingScheduleDay.objects.using(tenant_db).get(id=day_id, schedule=schedule)
        except WorkingScheduleDay.DoesNotExist:
            return Response({"detail": "Day rule not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.method.lower() == "get":
            return Response(WorkingScheduleDaySerializer(day).data)

        if request.method.lower() == "delete":
            day.delete(using=tenant_db)
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = WorkingScheduleDaySerializer(day, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        new_weekday = serializer.validated_data.get("weekday")
        if new_weekday is not None and new_weekday != day.weekday:
            if WorkingScheduleDay.objects.using(tenant_db).filter(schedule=schedule, weekday=new_weekday).exists():
                return Response(
                    {"weekday": "A day rule for this weekday already exists."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        serializer.save()
        if day._state.db != tenant_db:
            day.save(using=tenant_db)
        return Response(WorkingScheduleDaySerializer(day).data)


class AttendanceRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """List and approve attendance records."""

    permission_classes = [IsAuthenticated]
    serializer_class = AttendanceRecordSerializer

    def get_queryset(self):
        user = self.request.user
        params = self.request.query_params
        status_param = params.get("status")
        employee_id = params.get("employee_id")
        mode = params.get("mode")
        date_from = params.get("from")
        date_to = params.get("to")

        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            qs = AttendanceRecord.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        elif hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
            qs = AttendanceRecord.objects.using(tenant_db).filter(employee=employee)
        else:
            return AttendanceRecord.objects.none()

        if status_param:
            qs = qs.filter(status=status_param)
        if employee_id and hasattr(user, "employer_profile"):
            qs = qs.filter(employee_id=employee_id)
        if mode:
            qs = qs.filter(mode=mode)
        if date_from:
            qs = qs.filter(check_in_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(check_in_at__date__lte=date_to)
        return qs

    @action(detail=False, methods=["get"], url_path="to-approve", permission_classes=[IsAuthenticated, IsEmployer])
    def to_approve(self, request):
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        qs = AttendanceRecord.objects.using(tenant_db).filter(
            employer_id=employer.id, status=AttendanceRecord.STATUS_TO_APPROVE
        )
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="approve", permission_classes=[IsAuthenticated, IsEmployer])
    def approve(self, request, pk=None):
        record = self.get_object()
        tenant_db = record._state.db or "default"
        record.status = AttendanceRecord.STATUS_APPROVED
        record.save(using=tenant_db, update_fields=["status", "updated_at"])
        return Response(self.get_serializer(record).data)

    @action(detail=True, methods=["post"], url_path="refuse", permission_classes=[IsAuthenticated, IsEmployer])
    def refuse(self, request, pk=None):
        record = self.get_object()
        tenant_db = record._state.db or "default"
        record.status = AttendanceRecord.STATUS_REFUSED
        record.anomaly_reason = request.data.get("reason") or record.anomaly_reason
        record.save(using=tenant_db, update_fields=["status", "anomaly_reason", "updated_at"])
        return Response(self.get_serializer(record).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="partial-approve",
        permission_classes=[IsAuthenticated, IsEmployer],
    )
    def partial_approve(self, request, pk=None):
        record = self.get_object()
        serializer = PartialApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = serializer.validated_data["overtime_approved_minutes"]
        if record.overtime_worked_minutes and value > record.overtime_worked_minutes:
            value = record.overtime_worked_minutes
        tenant_db = record._state.db or "default"
        record.overtime_approved_minutes = value
        record.status = AttendanceRecord.STATUS_APPROVED
        record.save(using=tenant_db, update_fields=["overtime_approved_minutes", "status", "updated_at"])
        return Response(self.get_serializer(record).data)


class PortalCheckInView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = AttendanceCheckInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = _employee_from_request(request)
        if not employee:
            return Response({"detail": "Employee not found."}, status=status.HTTP_400_BAD_REQUEST)
        tenant_db = employee._state.db or "default"
        config = ensure_attendance_configuration(employee.employer_id, tenant_db)
        if not config.allow_systray_portal:
            return Response({"detail": "Portal check-ins are disabled."}, status=status.HTTP_403_FORBIDDEN)
        payload = dict(serializer.validated_data)
        payload["ip_address"] = _get_client_ip(request)
        record = perform_check_in(
            employee=employee,
            payload=payload,
            config=config,
            db_alias=tenant_db,
            mode=AttendanceRecord.MODE_PORTAL,
            created_by=request.user.id,
        )
        output = AttendanceRecordSerializer(record)
        return Response(output.data, status=status.HTTP_201_CREATED)


class PortalCheckOutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = AttendanceCheckOutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = _employee_from_request(request)
        if not employee:
            return Response({"detail": "Employee not found."}, status=status.HTTP_400_BAD_REQUEST)
        tenant_db = employee._state.db or "default"
        config = ensure_attendance_configuration(employee.employer_id, tenant_db)
        if not config.allow_systray_portal:
            return Response({"detail": "Portal check-outs are disabled."}, status=status.HTTP_403_FORBIDDEN)
        payload = dict(serializer.validated_data)
        payload["ip_address"] = _get_client_ip(request)
        record = perform_check_out(
            employee=employee,
            payload=payload,
            config=config,
            db_alias=tenant_db,
            mode=AttendanceRecord.MODE_PORTAL,
        )
        output = AttendanceRecordSerializer(record)
        return Response(output.data, status=status.HTTP_200_OK)


class KioskCheckView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = KioskCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        kiosk_token = payload.get("kiosk_token")
        if not kiosk_token:
            return Response({"detail": "kiosk_token is required"}, status=status.HTTP_400_BAD_REQUEST)

        station, tenant_db = resolve_station_by_token(kiosk_token)
        if station and tenant_db:
            employer_id = station.employer_id
        else:
            config, tenant_db = resolve_configuration_by_kiosk_token(kiosk_token)
            if not config or not tenant_db:
                return Response({"detail": "Invalid kiosk access"}, status=status.HTTP_404_NOT_FOUND)
            employer_id = config.employer_id
        config = ensure_attendance_configuration(employer_id, tenant_db)
        if not config.allow_kiosk:
            return Response({"detail": "Kiosk mode is disabled."}, status=status.HTTP_403_FORBIDDEN)

        identifier = payload.get("employee_identifier")
        employee = (
            Employee.objects.using(tenant_db)
            .filter(employer_id=employer_id)
            .filter(
                models.Q(badge_id__iexact=identifier)
                | models.Q(rfid_tag_id__iexact=identifier)
                | models.Q(employee_id__iexact=identifier)
            )
            .first()
        )
        if not employee:
            return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)
        if station and station.branch_id and employee.branch_id != station.branch_id:
            return Response({"detail": "Employee not assigned to this kiosk branch."}, status=status.HTTP_403_FORBIDDEN)
        if config.require_pin_for_kiosk and not employee.check_pin_code(payload.get("pin")):
            return Response({"detail": "Invalid PIN."}, status=status.HTTP_403_FORBIDDEN)

        payload["ip_address"] = _get_client_ip(request)

        existing = (
            AttendanceRecord.objects.using(tenant_db)
            .filter(employee=employee, check_out_at__isnull=True)
            .order_by("-check_in_at")
            .first()
        )
        if existing:
            record = perform_check_out(
                employee=employee,
                payload=payload,
                config=config,
                db_alias=tenant_db,
                mode=AttendanceRecord.MODE_KIOSK,
            )
        else:
            record = perform_check_in(
                employee=employee,
                payload=payload,
                config=config,
                db_alias=tenant_db,
                mode=AttendanceRecord.MODE_KIOSK,
            )
        record.kiosk_session_reference = kiosk_token
        record.kiosk_station = station
        record.save(using=tenant_db, update_fields=["kiosk_session_reference", "kiosk_station", "updated_at"])
        output = AttendanceRecordSerializer(record)
        return Response(output.data, status=status.HTTP_200_OK)


class AttendanceStatusView(APIView):
    """Return current check-in status for the authenticated employee."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        employee = _employee_from_request(request)
        if not employee:
            return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)
        tenant_db = employee._state.db or "default"
        open_record = (
            AttendanceRecord.objects.using(tenant_db)
            .filter(employee=employee, check_out_at__isnull=True)
            .order_by("-check_in_at")
            .first()
        )
        last_record = (
            AttendanceRecord.objects.using(tenant_db)
            .filter(employee=employee)
            .order_by("-check_in_at")
            .first()
        )
        status_payload = {
            "checked_in": open_record is not None,
            "current_record": AttendanceRecordSerializer(open_record).data if open_record else None,
            "last_record": AttendanceRecordSerializer(last_record).data if last_record else None,
        }
        return Response(status_payload, status=status.HTTP_200_OK)


class ManualAttendanceCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEmployer]

    def post(self, request):
        serializer = AttendanceManualCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employer = request.user.employer_profile
        tenant_db = get_tenant_database_alias(employer)
        data = serializer.validated_data

        employee = Employee.objects.using(tenant_db).filter(id=data["employee_id"], employer_id=employer.id).first()
        if not employee:
            return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)
        if not employee.is_active:
            return Response({"detail": "Employee is not active."}, status=status.HTTP_400_BAD_REQUEST)

        # Block manual attendance that overlaps approved/pending leave
        if is_employee_on_leave(employee, data["check_in_at"], tenant_db) or is_employee_on_leave(
            employee, data["check_out_at"], tenant_db
        ):
            return Response({"detail": "Employee is on approved leave for this period."}, status=status.HTTP_400_BAD_REQUEST)

        overlap = (
            AttendanceRecord.objects.using(tenant_db)
            .filter(employee=employee)
            .filter(check_out_at__gt=data["check_in_at"], check_in_at__lt=data["check_out_at"])
            .exists()
        )
        if overlap:
            return Response({"detail": "Overlapping attendance record exists."}, status=status.HTTP_400_BAD_REQUEST)

        config = ensure_attendance_configuration(employer.id, tenant_db)
        if not config.is_enabled:
            return Response({"detail": "Attendance module is disabled for this employer."}, status=status.HTTP_400_BAD_REQUEST)
        worked_minutes = int((data["check_out_at"] - data["check_in_at"]).total_seconds() // 60)
        expected_minutes = resolve_expected_minutes(employee, data["check_in_at"], tenant_db)
        overtime_worked = max(worked_minutes - (expected_minutes or 0), 0)
        approved_overtime = min(data.get("overtime_approved_minutes") or 0, overtime_worked)
        manual_status = AttendanceRecord.STATUS_TO_APPROVE
        anomaly_reason = "Manual record created"
        if approved_overtime:
            manual_status = AttendanceRecord.STATUS_APPROVED

        record = AttendanceRecord.objects.using(tenant_db).create(
            employer_id=employer.id,
            employee=employee,
            check_in_at=data["check_in_at"],
            check_out_at=data["check_out_at"],
            worked_minutes=worked_minutes,
            expected_minutes=expected_minutes,
            overtime_worked_minutes=overtime_worked,
            overtime_approved_minutes=approved_overtime,
            status=manual_status,
            mode=AttendanceRecord.MODE_MANUAL,
            anomaly_reason=anomaly_reason,
            created_by_id=request.user.id,
        )
        if config.auto_flag_anomalies and config.max_daily_work_minutes_before_flag:
            if record.worked_minutes > config.max_daily_work_minutes_before_flag:
                record.status = AttendanceRecord.STATUS_TO_APPROVE
                record.anomaly_reason = "Excessive hours"
                record.save(using=tenant_db, update_fields=["status", "anomaly_reason", "updated_at"])
        output = AttendanceRecordSerializer(record)
        return Response(output.data, status=status.HTTP_201_CREATED)


class AttendanceReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = AttendanceReportQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if hasattr(request.user, "employer_profile"):
            employer = request.user.employer_profile
            tenant_db = get_tenant_database_alias(employer)
            qs = AttendanceRecord.objects.using(tenant_db).filter(employer_id=employer.id)
        elif hasattr(request.user, "employee_profile") and request.user.employee_profile:
            employee = request.user.employee_profile
            tenant_db = employee._state.db or "default"
            qs = AttendanceRecord.objects.using(tenant_db).filter(employee=employee)
        else:
            return Response({"detail": "Unable to resolve tenant."}, status=status.HTTP_403_FORBIDDEN)

        if data.get("date_from"):
            qs = qs.filter(check_in_at__date__gte=data["date_from"])
        if data.get("date_to"):
            qs = qs.filter(check_in_at__date__lte=data["date_to"])
        if data.get("employee_id"):
            qs = qs.filter(employee_id=data["employee_id"])
        if data.get("department_id"):
            qs = qs.filter(employee__department_id=data["department_id"])

        measures = data.get("measures") or ["worked", "expected", "difference", "balance"]
        group_by = data.get("group_by") or []

        def aggregate_records(records):
            worked = sum(r.worked_minutes or 0 for r in records)
            expected = sum(r.expected_minutes or 0 for r in records)
            difference = worked - expected
            balance = sum((r.overtime_worked_minutes or 0) - (r.overtime_approved_minutes or 0) for r in records)
            return {
                "worked": worked,
                "expected": expected,
                "difference": difference,
                "balance": balance,
            }

        def group_key(rec):
            parts = []
            for dim in group_by:
                if dim == "month":
                    parts.append(rec.check_in_at.strftime("%Y-%m"))
                elif dim == "employee":
                    parts.append(str(rec.employee_id))
                elif dim == "department":
                    dept_key = (
                        str(rec.employee.department_id)
                        if rec.employee and rec.employee.department_id
                        else "unassigned"
                    )
                    parts.append(dept_key)
            return "|".join(parts) if parts else "all"

        buckets = defaultdict(list)
        iterable = qs.select_related("employee__department") if "department" in group_by else qs
        for rec in iterable:
            buckets[group_key(rec)].append(rec)

        results = []
        for key, records in buckets.items():
            aggregates = aggregate_records(records)
            results.append({"group": key, **{k: aggregates[k] for k in measures}})

        return Response({"results": results}, status=status.HTTP_200_OK)
