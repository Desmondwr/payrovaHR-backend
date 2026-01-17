from datetime import date

from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.database_utils import ensure_tenant_database_loaded, get_tenant_database_alias
from accounts.permissions import IsEmployer
from accounts.models import EmployerProfile
from employees.models import Employee

from .models import (
    AttendanceDay,
    AttendanceDevice,
    AttendanceEvent,
    AttendanceKioskSettings,
    AttendancePolicy,
    AttendanceRecord,
    OvertimeRequest,
)
from .serializers import (
    AttendanceDayManualMarkSerializer,
    AttendanceDaySerializer,
    AttendanceDeviceSerializer,
    AttendanceEventCreateSerializer,
    AttendanceEventSerializer,
    AttendanceKioskSettingsSerializer,
    AttendancePolicySerializer,
    AttendanceRecordCreateSerializer,
    AttendanceRecordSerializer,
    EmployeeScheduleSerializer,
    OvertimeRequestCreateSerializer,
    OvertimeRequestSerializer,
    ShiftTemplateSerializer,
)
from .services import (
    apply_overtime_approval,
    close_check_out_record,
    create_check_in_record,
    ensure_kiosk_settings,
    ensure_attendance_policy,
    get_open_attendance_record,
    rebuild_attendance_day,
    resolve_attendance_policy,
)
from .models import EmployeeSchedule, ShiftTemplate


class AttendancePolicyViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AttendancePolicySerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            return AttendancePolicy.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        if hasattr(user, "employee_profile") and user.employee_profile:
            tenant_db = user.employee_profile._state.db or "default"
            return AttendancePolicy.objects.using(tenant_db).filter(employer_id=user.employee_profile.employer_id)
        return AttendancePolicy.objects.none()

    def perform_create(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employers can create attendance policies.")
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save(employer_id=self.request.user.employer_profile.id)
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    def perform_update(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employers can update attendance policies.")
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    @action(detail=False, methods=["get"], url_path="effective")
    def effective_policy(self, request):
        user = request.user
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            employee_id = request.query_params.get("employee_id")
            if not employee_id:
                raise permissions.PermissionDenied("employee_id is required for employer effective policy.")
            employee = Employee.objects.using(tenant_db).filter(id=employee_id).first()
            if not employee:
                raise permissions.PermissionDenied("Employee not found for this tenant.")
        elif hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"
        else:
            raise permissions.PermissionDenied("Unable to resolve tenant.")

        ensure_attendance_policy(employee.employer_id, tenant_db)
        policy = resolve_attendance_policy(employee, tenant_db)
        return Response(policy)


class ShiftTemplateViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ShiftTemplateSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            return ShiftTemplate.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        if hasattr(user, "employee_profile") and user.employee_profile:
            tenant_db = user.employee_profile._state.db or "default"
            return ShiftTemplate.objects.using(tenant_db).filter(employer_id=user.employee_profile.employer_id)
        return ShiftTemplate.objects.none()

    def perform_create(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employers can create shift templates.")
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save(employer_id=self.request.user.employer_profile.id)
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    def perform_update(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employers can update shift templates.")
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)


class EmployeeScheduleViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EmployeeScheduleSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            return EmployeeSchedule.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        if hasattr(user, "employee_profile") and user.employee_profile:
            tenant_db = user.employee_profile._state.db or "default"
            return EmployeeSchedule.objects.using(tenant_db).filter(employee=user.employee_profile)
        return EmployeeSchedule.objects.none()

    def perform_create(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employers can create schedules.")
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save(employer_id=self.request.user.employer_profile.id)
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    def perform_update(self, serializer):
        if not hasattr(self.request.user, "employer_profile"):
            raise permissions.PermissionDenied("Only employers can update schedules.")
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save()
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)


class AttendanceEventViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create"]:
            return AttendanceEventCreateSerializer
        return AttendanceEventSerializer

    def get_queryset(self):
        user = self.request.user
        params = self.request.query_params
        date_from = params.get("from")
        date_to = params.get("to")
        employee_id = params.get("employee_id")

        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            qs = AttendanceEvent.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
            if employee_id:
                qs = qs.filter(employee_id=employee_id)
        elif hasattr(user, "employee_profile") and user.employee_profile:
            tenant_db = user.employee_profile._state.db or "default"
            qs = AttendanceEvent.objects.using(tenant_db).filter(employee=user.employee_profile)
        else:
            return AttendanceEvent.objects.none()

        if date_from:
            qs = qs.filter(attendance_date__gte=date_from)
        if date_to:
            qs = qs.filter(attendance_date__lte=date_to)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        instance = serializer.save()
        tenant_db = instance._state.db or "default"

        policy = resolve_attendance_policy(instance.employee, tenant_db)
        attendance_policy = policy.get("attendance_policy") or {}
        if not hasattr(user, "employer_profile") and not attendance_policy.get("allow_self_check_in", True):
            raise permissions.PermissionDenied("Self check-in/out is disabled.")

        rebuild_attendance_day(instance.employee, instance.attendance_date, tenant_db, policy)

    @action(detail=False, methods=["post"], url_path="check-in")
    def check_in(self, request):
        payload = request.data.copy()
        payload["event_type"] = AttendanceEvent.EVENT_IN
        payload["source"] = payload.get("source", AttendanceEvent.SOURCE_MOBILE)
        serializer = AttendanceEventCreateSerializer(data=payload, context={"request": request})
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        rebuild_attendance_day(event.employee, event.attendance_date, event._state.db or "default")
        return Response(AttendanceEventSerializer(event).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="check-out")
    def check_out(self, request):
        payload = request.data.copy()
        payload["event_type"] = AttendanceEvent.EVENT_OUT
        payload["source"] = payload.get("source", AttendanceEvent.SOURCE_MOBILE)
        serializer = AttendanceEventCreateSerializer(data=payload, context={"request": request})
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        rebuild_attendance_day(event.employee, event.attendance_date, event._state.db or "default")
        return Response(AttendanceEventSerializer(event).data, status=status.HTTP_201_CREATED)


class AttendanceDayViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AttendanceDaySerializer

    def get_queryset(self):
        user = self.request.user
        params = self.request.query_params
        date_from = params.get("from")
        date_to = params.get("to")
        employee_id = params.get("employee_id")
        status_param = params.get("status")

        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            qs = AttendanceDay.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
            if employee_id:
                qs = qs.filter(employee_id=employee_id)
        elif hasattr(user, "employee_profile") and user.employee_profile:
            tenant_db = user.employee_profile._state.db or "default"
            qs = AttendanceDay.objects.using(tenant_db).filter(employee=user.employee_profile)
        else:
            return AttendanceDay.objects.none()

        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    @action(detail=False, methods=["post"], permission_classes=[IsEmployer], url_path="manual-mark")
    def manual_mark(self, request):
        serializer = AttendanceDayManualMarkSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        employee = serializer.validated_data["employee"]
        tenant_db = serializer.validated_data["tenant_db"]
        policy = resolve_attendance_policy(employee, tenant_db)
        attendance_policy = policy.get("attendance_policy") or {}
        if not attendance_policy.get("allow_manual_edits", True):
            return Response({"detail": "Manual attendance edits are disabled."}, status=status.HTTP_403_FORBIDDEN)
        if attendance_policy.get("require_edit_reason") and not serializer.validated_data.get("reason"):
            return Response({"detail": "Reason is required for manual edits."}, status=status.HTTP_400_BAD_REQUEST)

        attendance_date = serializer.validated_data["date"]
        attendance_day, _ = AttendanceDay.objects.using(tenant_db).get_or_create(
            employee=employee,
            date=attendance_date,
            defaults={"employer_id": employee.employer_id},
        )
        if attendance_day.locked_for_payroll:
            return Response({"detail": "Attendance day is locked for payroll."}, status=status.HTTP_400_BAD_REQUEST)

        attendance_day.status = serializer.validated_data["status"]
        attendance_day.first_in_at = serializer.validated_data.get("first_in_at")
        attendance_day.last_out_at = serializer.validated_data.get("last_out_at")
        attendance_day.worked_minutes = serializer.validated_data.get("worked_minutes", attendance_day.worked_minutes)
        attendance_day.save(using=tenant_db)

        return Response(AttendanceDaySerializer(attendance_day).data)

    @action(detail=False, methods=["post"], permission_classes=[IsEmployer], url_path="rebuild")
    def rebuild(self, request):
        employee_id = request.data.get("employee_id")
        target_date = request.data.get("date")
        if not employee_id or not target_date:
            return Response({"detail": "employee_id and date are required."}, status=status.HTTP_400_BAD_REQUEST)
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        employee = Employee.objects.using(tenant_db).filter(id=employee_id).first()
        if not employee:
            return Response({"detail": "Employee not found for this tenant."}, status=status.HTTP_404_NOT_FOUND)
        attendance_date = date.fromisoformat(target_date)
        attendance_day = rebuild_attendance_day(employee, attendance_date, tenant_db)
        return Response(AttendanceDaySerializer(attendance_day).data)


class AttendanceDeviceViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsEmployer]
    serializer_class = AttendanceDeviceSerializer

    def get_queryset(self):
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        return AttendanceDevice.objects.using(tenant_db).filter(employer_id=self.request.user.employer_profile.id)

    def perform_create(self, serializer):
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save(employer_id=self.request.user.employer_profile.id)
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)


class AttendanceKioskSettingsViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsEmployer]
    serializer_class = AttendanceKioskSettingsSerializer

    def get_queryset(self):
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        return AttendanceKioskSettings.objects.using(tenant_db).filter(employer_id=self.request.user.employer_profile.id)

    def perform_create(self, serializer):
        tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
        serializer.save(employer_id=self.request.user.employer_profile.id)
        instance = serializer.instance
        if instance._state.db != tenant_db:
            instance.save(using=tenant_db)

    @action(detail=False, methods=["get", "patch"], url_path="global")
    def global_settings(self, request):
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        settings = ensure_kiosk_settings(request.user.employer_profile.id, tenant_db)

        if request.method == "PATCH":
            serializer = self.get_serializer(settings, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)

        serializer = self.get_serializer(settings)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="qr")
    def qr(self, request):
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        settings = ensure_kiosk_settings(request.user.employer_profile.id, tenant_db)
        kiosk_url = request.build_absolute_uri(
            f"/attendance/kiosk/punch/?employer_id={request.user.employer_profile.id}&kiosk_token={settings.kiosk_url_token}"
        )
        return Response(
            {
                "employer_id": request.user.employer_profile.id,
                "kiosk_token": settings.kiosk_url_token,
                "kiosk_url": kiosk_url,
            }
        )

    @action(detail=True, methods=["post"], url_path="regenerate-token")
    def regenerate_token(self, request, pk=None):
        settings = self.get_object()
        settings.regenerate_token()
        settings.save(using=settings._state.db or "default", update_fields=["kiosk_url_token"])
        serializer = self.get_serializer(settings)
        return Response(serializer.data)


class AttendanceRecordViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create"]:
            return AttendanceRecordCreateSerializer
        return AttendanceRecordSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            return AttendanceRecord.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        if hasattr(user, "employee_profile") and user.employee_profile:
            tenant_db = user.employee_profile._state.db or "default"
            return AttendanceRecord.objects.using(tenant_db).filter(employee=user.employee_profile)
        return AttendanceRecord.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        record = serializer.save()
        output = AttendanceRecordSerializer(record)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="check-in")
    def check_in(self, request):
        user = request.user
        employee = None
        tenant_db = "default"

        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            employee_id = request.data.get("employee_id")
            if not employee_id:
                return Response({"detail": "employee_id is required."}, status=status.HTTP_400_BAD_REQUEST)
            employee = Employee.objects.using(tenant_db).filter(id=employee_id).first()
        elif hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"

        if not employee:
            return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)

        record = create_check_in_record(
            employee=employee,
            tenant_db=tenant_db,
            mode=AttendanceRecord.MODE_SYSTRAY,
            ip_address=request.META.get("REMOTE_ADDR"),
            gps_lat=request.data.get("gps_lat"),
            gps_lng=request.data.get("gps_lng"),
            created_by_id=user.id,
        )
        return Response(AttendanceRecordSerializer(record).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="check-out")
    def check_out(self, request):
        user = request.user
        employee = None
        tenant_db = "default"

        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            employee_id = request.data.get("employee_id")
            if not employee_id:
                return Response({"detail": "employee_id is required."}, status=status.HTTP_400_BAD_REQUEST)
            employee = Employee.objects.using(tenant_db).filter(id=employee_id).first()
        elif hasattr(user, "employee_profile") and user.employee_profile:
            employee = user.employee_profile
            tenant_db = employee._state.db or "default"

        if not employee:
            return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)

        record = get_open_attendance_record(employee, tenant_db)
        if not record:
            return Response({"detail": "No open attendance record."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            record = close_check_out_record(
                record,
                tenant_db,
                ip_address=request.META.get("REMOTE_ADDR"),
                gps_lat=request.data.get("gps_lat"),
                gps_lng=request.data.get("gps_lng"),
                overtime_reason=request.data.get("overtime_reason"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AttendanceRecordSerializer(record).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], permission_classes=[IsEmployer], url_path="to-approve")
    def to_approve(self, request):
        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        records = AttendanceRecord.objects.using(tenant_db).filter(
            employer_id=request.user.employer_profile.id,
            overtime_status=AttendanceRecord.STATUS_TO_APPROVE,
        )
        serializer = AttendanceRecordSerializer(records, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsEmployer], url_path="approve")
    def approve(self, request, pk=None):
        record = self.get_object()
        tenant_db = record._state.db or "default"
        extra_minutes = request.data.get("extra_minutes")
        overtime_reason = request.data.get("overtime_reason")
        if extra_minutes is not None:
            record.extra_minutes = max(0, int(extra_minutes))
        if overtime_reason is not None:
            record.overtime_reason = overtime_reason
        record.overtime_status = AttendanceRecord.STATUS_APPROVED
        record.save(using=tenant_db)
        return Response(AttendanceRecordSerializer(record).data)

    @action(detail=True, methods=["post"], permission_classes=[IsEmployer], url_path="refuse")
    def refuse(self, request, pk=None):
        record = self.get_object()
        tenant_db = record._state.db or "default"
        record.overtime_status = AttendanceRecord.STATUS_REFUSED
        record.save(using=tenant_db)
        return Response(AttendanceRecordSerializer(record).data)


class OvertimeRequestViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create"]:
            return OvertimeRequestCreateSerializer
        return OvertimeRequestSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, "employer_profile"):
            tenant_db = get_tenant_database_alias(user.employer_profile)
            return OvertimeRequest.objects.using(tenant_db).filter(employer_id=user.employer_profile.id)
        if hasattr(user, "employee_profile") and user.employee_profile:
            tenant_db = user.employee_profile._state.db or "default"
            return OvertimeRequest.objects.using(tenant_db).filter(employee=user.employee_profile)
        return OvertimeRequest.objects.none()

    def perform_create(self, serializer):
        instance = serializer.save()
        if instance._state.db == "default" and hasattr(self.request.user, "employer_profile"):
            tenant_db = get_tenant_database_alias(self.request.user.employer_profile)
            instance.save(using=tenant_db)

    @action(detail=True, methods=["post"], permission_classes=[IsEmployer], url_path="approve")
    def approve(self, request, pk=None):
        ot_request = self.get_object()
        tenant_db = ot_request._state.db or "default"
        ot_request.approve(request.user.id)
        ot_request.save(using=tenant_db)
        apply_overtime_approval(ot_request.employee, ot_request.date, tenant_db)
        return Response(OvertimeRequestSerializer(ot_request).data)

    @action(detail=True, methods=["post"], permission_classes=[IsEmployer], url_path="reject")
    def reject(self, request, pk=None):
        ot_request = self.get_object()
        tenant_db = ot_request._state.db or "default"
        ot_request.reject(request.user.id)
        ot_request.save(using=tenant_db)
        apply_overtime_approval(ot_request.employee, ot_request.date, tenant_db)
        return Response(OvertimeRequestSerializer(ot_request).data)


class DeviceEventIngestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data or {}
        auth_token = data.get("auth_token")
        employer_id = data.get("employer_id")
        events = data.get("events") or []
        if not auth_token or not employer_id:
            return Response(
                {"detail": "auth_token and employer_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        employer = EmployerProfile.objects.filter(id=employer_id, database_created=True).first()
        if not employer:
            return Response({"detail": "Employer not found."}, status=status.HTTP_404_NOT_FOUND)

        tenant_db = ensure_tenant_database_loaded(employer)
        device = AttendanceDevice.objects.using(tenant_db).filter(auth_token=auth_token, is_active=True).first()
        if not device:
            return Response({"detail": "Invalid device token."}, status=status.HTTP_403_FORBIDDEN)
        successes = 0
        errors = []
        for idx, payload in enumerate(events):
            serializer = AttendanceEventCreateSerializer(
                data={
                    "employee_id": payload.get("employee_id"),
                    "timestamp": payload.get("timestamp"),
                    "event_type": payload.get("event_type"),
                    "source": AttendanceEvent.SOURCE_DEVICE,
                    "device": str(device.id),
                    "metadata": payload.get("metadata") or {},
                },
                context={"request": request},
            )
            if serializer.is_valid():
                event = serializer.save()
                rebuild_attendance_day(event.employee, event.attendance_date, tenant_db)
                successes += 1
            else:
                errors.append({"index": idx, "errors": serializer.errors})

        device.last_seen_at = timezone.now()
        device.save(using=tenant_db)

        return Response(
            {"received": len(events), "processed": successes, "errors": errors},
            status=status.HTTP_200_OK,
        )


class KioskPunchView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data or {}
        employer_id = data.get("employer_id")
        kiosk_token = data.get("kiosk_token")
        badge_id = data.get("badge_id")
        employee_id = data.get("employee_id")
        pin_code = data.get("pin_code")
        device_id = data.get("device_id")
        gps_lat = data.get("gps_lat")
        gps_lng = data.get("gps_lng")
        overtime_reason = data.get("overtime_reason")

        if not employer_id or not kiosk_token:
            return Response(
                {"detail": "employer_id and kiosk_token are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        employer = EmployerProfile.objects.filter(id=employer_id, database_created=True).first()
        if not employer:
            return Response({"detail": "Employer not found."}, status=status.HTTP_404_NOT_FOUND)

        tenant_db = ensure_tenant_database_loaded(employer)
        settings = AttendanceKioskSettings.objects.using(tenant_db).filter(
            employer_id=employer_id,
            kiosk_url_token=kiosk_token,
            is_active=True,
        ).first()
        if not settings:
            return Response({"detail": "Invalid kiosk token."}, status=status.HTTP_403_FORBIDDEN)

        if badge_id:
            employee = Employee.objects.using(tenant_db).filter(badge_id=badge_id, employer_id=employer_id).first()
        elif employee_id:
            employee = Employee.objects.using(tenant_db).filter(id=employee_id, employer_id=employer_id).first()
        else:
            employee = None

        if not employee:
            return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)

        if settings.pin_required and not employee.check_pin_code(pin_code or ""):
            return Response({"detail": "Invalid PIN."}, status=status.HTTP_403_FORBIDDEN)

        kiosk_device = None
        if device_id:
            kiosk_device = AttendanceDevice.objects.using(tenant_db).filter(id=device_id, device_type="KIOSK").first()

        open_record = get_open_attendance_record(employee, tenant_db)
        if open_record:
            try:
                record = close_check_out_record(
                    open_record,
                    tenant_db,
                    ip_address=request.META.get("REMOTE_ADDR"),
                    gps_lat=gps_lat,
                    gps_lng=gps_lng,
                    overtime_reason=overtime_reason,
                )
                action = "CHECKED_OUT"
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            record = create_check_in_record(
                employee=employee,
                tenant_db=tenant_db,
                mode=AttendanceRecord.MODE_KIOSK,
                ip_address=request.META.get("REMOTE_ADDR"),
                gps_lat=gps_lat,
                gps_lng=gps_lng,
                kiosk_device=kiosk_device,
                created_by_id=None,
            )
            action = "CHECKED_IN"

        return Response(
            {"action": action, "record": AttendanceRecordSerializer(record).data},
            status=status.HTTP_200_OK,
        )
