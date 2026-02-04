from django.conf import settings
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.notifications import create_notification
from accounts.models import EmployerProfile
from accounts.database_utils import get_tenant_database_alias
from accounts.permissions import IsAuthenticated, EmployerAccessPermission
from accounts.rbac import get_active_employer, is_delegate_user, get_delegate_scope, apply_scope_filter
from django.contrib.auth import get_user_model
from .models import FrontdeskStation, StationResponsible, Visitor, Visit
from .serializers import (
    FrontdeskStationSerializer,
    StationResponsibleSerializer,
    VisitorSerializer,
    VisitSerializer,
    KioskCheckInSerializer,
    KioskStationSerializer,
    KioskHostSerializer,
)

User = get_user_model()
from employees.models import Employee


class FrontdeskStationViewSet(viewsets.ModelViewSet):
    """Manage branch-based stations (one active per branch)."""

    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["frontdesk.station.view", "frontdesk.manage"],
        "retrieve": ["frontdesk.station.view", "frontdesk.manage"],
        "create": ["frontdesk.station.create", "frontdesk.manage"],
        "update": ["frontdesk.station.update", "frontdesk.manage"],
        "partial_update": ["frontdesk.station.update", "frontdesk.manage"],
        "destroy": ["frontdesk.station.delete", "frontdesk.manage"],
        "delete_station": ["frontdesk.station.delete", "frontdesk.manage"],
        "*": ["frontdesk.manage"],
    }
    serializer_class = FrontdeskStationSerializer

    def get_queryset(self):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        qs = (
            FrontdeskStation.objects.using(tenant_db)
            .filter(employer_id=employer.id)
            .select_related("branch")
            .prefetch_related("responsibles")
        )
        if is_delegate_user(self.request.user, employer.id):
            scope = get_delegate_scope(self.request.user, employer.id)
            qs = apply_scope_filter(qs, scope, branch_field="branch_id")
        return qs

    def perform_destroy(self, instance):
        tenant_db = get_tenant_database_alias(get_active_employer(self.request, require_context=True))
        instance.delete(using=tenant_db)

    @action(detail=True, methods=["delete"], url_path="delete")
    def delete_station(self, request, pk=None):
        station = self.get_object()
        tenant_db = get_tenant_database_alias(get_active_employer(request, require_context=True))
        station.delete(using=tenant_db)
        return Response(status=status.HTTP_204_NO_CONTENT)


class StationResponsibleViewSet(viewsets.ModelViewSet):
    """Manage station responsibles (HR/office admins scoped to branch)."""

    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["frontdesk.responsible.view", "frontdesk.manage"],
        "retrieve": ["frontdesk.responsible.view", "frontdesk.manage"],
        "create": ["frontdesk.responsible.create", "frontdesk.manage"],
        "update": ["frontdesk.responsible.update", "frontdesk.manage"],
        "partial_update": ["frontdesk.responsible.update", "frontdesk.manage"],
        "destroy": ["frontdesk.responsible.delete", "frontdesk.manage"],
        "*": ["frontdesk.manage"],
    }
    serializer_class = StationResponsibleSerializer

    def get_queryset(self):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        qs = (
            StationResponsible.objects.using(tenant_db)
            .filter(station__employer_id=employer.id)
            .select_related("station", "employee")
        )
        if is_delegate_user(self.request.user, employer.id):
            scope = get_delegate_scope(self.request.user, employer.id)
            qs = apply_scope_filter(qs, scope, branch_field="station__branch_id")
        return qs

    def perform_destroy(self, instance):
        tenant_db = get_tenant_database_alias(get_active_employer(self.request, require_context=True))
        instance.delete(using=tenant_db)


class VisitorViewSet(viewsets.ModelViewSet):
    """CRUD for external visitors."""

    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["frontdesk.visitor.view", "frontdesk.manage"],
        "retrieve": ["frontdesk.visitor.view", "frontdesk.manage"],
        "create": ["frontdesk.visitor.create", "frontdesk.manage"],
        "update": ["frontdesk.visitor.update", "frontdesk.manage"],
        "partial_update": ["frontdesk.visitor.update", "frontdesk.manage"],
        "destroy": ["frontdesk.visitor.delete", "frontdesk.manage"],
        "*": ["frontdesk.manage"],
    }
    serializer_class = VisitorSerializer

    def get_queryset(self):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        return Visitor.objects.using(tenant_db).filter(employer_id=employer.id)

    def perform_destroy(self, instance):
        tenant_db = get_tenant_database_alias(get_active_employer(self.request, require_context=True))
        instance.delete(using=tenant_db)


class VisitViewSet(viewsets.ModelViewSet):
    """Visitor lifecycle: planned/walk-in, check-in, manual check-out."""

    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    permission_map = {
        "list": ["frontdesk.visit.view", "frontdesk.manage"],
        "retrieve": ["frontdesk.visit.view", "frontdesk.manage"],
        "create": ["frontdesk.visit.create", "frontdesk.manage"],
        "update": ["frontdesk.visit.update", "frontdesk.manage"],
        "partial_update": ["frontdesk.visit.update", "frontdesk.manage"],
        "destroy": ["frontdesk.visit.delete", "frontdesk.manage"],
        "check_in": ["frontdesk.visit.check_in", "frontdesk.manage"],
        "check_out": ["frontdesk.visit.check_out", "frontdesk.manage"],
        "cancel": ["frontdesk.visit.cancel", "frontdesk.manage"],
        "*": ["frontdesk.manage"],
    }
    serializer_class = VisitSerializer

    def get_queryset(self):
        employer = get_active_employer(self.request, require_context=True)
        tenant_db = get_tenant_database_alias(employer)
        qs = (
            Visit.objects.using(tenant_db)
            .filter(employer_id=employer.id)
            .select_related("branch", "station", "visitor", "host")
        )
        if is_delegate_user(self.request.user, employer.id):
            scope = get_delegate_scope(self.request.user, employer.id)
            qs = apply_scope_filter(qs, scope, branch_field="branch_id")

        branch = self.request.query_params.get("branch")
        status_filter = self.request.query_params.get("status")
        station = self.request.query_params.get("station")
        if branch:
            qs = qs.filter(branch_id=branch)
        if station:
            qs = qs.filter(station_id=station)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def perform_destroy(self, instance):
        tenant_db = get_tenant_database_alias(get_active_employer(self.request, require_context=True))
        instance.delete(using=tenant_db)

    @action(detail=True, methods=["post"])
    def check_in(self, request, pk=None):
        visit = self.get_object()
        if visit.status == "CHECKED_OUT":
            return Response({"detail": "Visit already checked out."}, status=status.HTTP_400_BAD_REQUEST)
        if visit.status == "CHECKED_IN":
            return Response({"detail": "Visit already checked in."}, status=status.HTTP_200_OK)
        if visit.status == "CANCELLED":
            return Response({"detail": "Cancelled visits cannot be checked in."}, status=status.HTTP_400_BAD_REQUEST)

        method = request.data.get("method", "MANUAL")
        kiosk_reference = request.data.get("kiosk_reference")
        visit.check_in(method=method, kiosk_reference=kiosk_reference)
        serializer = self.get_serializer(visit)
        if visit.host and visit.host.user_id:
            employer_profile = EmployerProfile.objects.filter(id=visit.employer_id).first()
            target_user = User.objects.filter(id=visit.host.user_id).first()
            create_notification(
                user=target_user,
                title="Visitor arrived",
                body=f"{visit.visitor.full_name} has checked in.",
                type="ACTION",
                employer_profile=employer_profile,
                data={"visit_id": str(visit.id), "visitor": visit.visitor.full_name},
            )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def check_out(self, request, pk=None):
        visit = self.get_object()
        if visit.status == "CHECKED_OUT":
            return Response({"detail": "Visit already checked out."}, status=status.HTTP_200_OK)
        if visit.status != "CHECKED_IN":
            return Response({"detail": "Visit must be checked in before checkout."}, status=status.HTTP_400_BAD_REQUEST)

        visit.check_out(user_id=request.user.id)
        serializer = self.get_serializer(visit)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        visit = self.get_object()
        if visit.status == "CANCELLED":
            serializer = self.get_serializer(visit)
            return Response(serializer.data, status=status.HTTP_200_OK)
        if visit.status != "PLANNED":
            return Response({"detail": "Only planned visits can be cancelled."}, status=status.HTTP_400_BAD_REQUEST)

        tenant_db = get_tenant_database_alias(request.user.employer_profile)
        visit.status = "CANCELLED"
        visit.save(using=tenant_db)
        serializer = self.get_serializer(visit)
        return Response(serializer.data, status=status.HTTP_200_OK)


def resolve_station_by_slug(kiosk_slug):
    """Find station across tenant databases by kiosk_slug."""
    aliases = list(settings.DATABASES.keys())
    # Prefer tenant databases first, then default
    tenant_aliases = [a for a in aliases if a.startswith("tenant_")]
    ordered_aliases = tenant_aliases + [a for a in aliases if a not in tenant_aliases]
    for alias in ordered_aliases:
        try:
            station = FrontdeskStation.objects.using(alias).select_related("branch").get(kiosk_slug=kiosk_slug)
            return station, alias
        except FrontdeskStation.DoesNotExist:
            continue
    return None, None


def process_kiosk_check_in(request, kiosk_slug):
    """Shared logic to create a visit for a kiosk check-in."""
    station, tenant_db = resolve_station_by_slug(kiosk_slug)
    if not station:
        return Response({"detail": "Invalid kiosk."}, status=status.HTTP_404_NOT_FOUND)
    if not station.is_active or not station.allow_self_check_in:
        return Response({"detail": "Self check-in is disabled for this station."}, status=status.HTTP_400_BAD_REQUEST)

    serializer = KioskCheckInSerializer(
        data=request.data,
        context={"station": station, "tenant_db": tenant_db},
    )
    serializer.is_valid(raise_exception=True)
    visit = serializer.save()
    response_serializer = VisitSerializer(visit, context={"request": request})
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class KioskCheckInView(APIView):
    """Unauthenticated kiosk/QR self check-in using station kiosk_slug."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, kiosk_slug):
        return process_kiosk_check_in(request, kiosk_slug)


class KioskStationView(APIView):
    """Public station lookup by kiosk_slug for kiosk UI configuration."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, kiosk_slug):
        station, tenant_db = resolve_station_by_slug(kiosk_slug)
        if not station:
            return Response({"detail": "Invalid kiosk."}, status=status.HTTP_404_NOT_FOUND)
        serializer = KioskStationSerializer(station, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class KioskHostsView(APIView):
    """Public list of active hosts for a station (branch-scoped)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, kiosk_slug):
        station, tenant_db = resolve_station_by_slug(kiosk_slug)
        if not station:
            return Response({"detail": "Invalid kiosk."}, status=status.HTTP_404_NOT_FOUND)
        if not station.is_active or not station.allow_self_check_in:
            return Response({"detail": "Self check-in is disabled for this station."}, status=status.HTTP_400_BAD_REQUEST)

        hosts = (
            Employee.objects.using(tenant_db)
            .filter(
                employer_id=station.employer_id,
                branch_id=station.branch_id,
                employment_status="ACTIVE",
            )
            .order_by("last_name", "first_name")
        )
        serializer = KioskHostSerializer(hosts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GlobalKioskCheckInView(APIView):
    """Unauthenticated check-in that accepts kiosk_slug in the request payload."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        kiosk_slug = request.data.get("kiosk_slug")
        if not kiosk_slug:
            return Response({"detail": "kiosk_slug is required."}, status=status.HTTP_400_BAD_REQUEST)
        return process_kiosk_check_in(request, kiosk_slug)
