from django.utils import timezone
from django.db.models import Q
from rest_framework import serializers

from accounts.database_utils import get_tenant_database_alias
from accounts.rbac import get_active_employer, is_delegate_user
from employees.models import Branch, Employee
from .models import FrontdeskStation, StationResponsible, Visitor, Visit

DEFAULT_KIOSK_THEME = {
    "background_color": "#ffffff",
    "text_color": "#111827",
    "check_in_button_bg_color": "#2563eb",
}


def resolve_employer_context(request):
    if not request:
        return None, None
    user = request.user
    employer = None
    if getattr(user, "employer_profile", None):
        employer = user.employer_profile
    else:
        resolved = get_active_employer(request, require_context=False)
        if resolved and is_delegate_user(user, resolved.id):
            employer = resolved
    tenant_db = get_tenant_database_alias(employer) if employer else None
    return employer, tenant_db


def normalize_kiosk_theme(theme):
    merged = {**DEFAULT_KIOSK_THEME}
    if isinstance(theme, dict):
        merged.update({k: v for k, v in theme.items() if v is not None})
    return merged


class FrontdeskStationSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    kiosk_url_path = serializers.CharField(read_only=True)
    kiosk_logo = serializers.ImageField(required=False, allow_null=True, help_text="Optional uploaded logo for kiosk UI")
    responsibles = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        allow_empty=True,
        queryset=Employee.objects.none(),
        help_text="Active HR/office admins responsible for this station",
    )

    class Meta:
        model = FrontdeskStation
        fields = [
            "id",
            "employer_id",
            "branch",
            "branch_name",
            "name",
            "kiosk_slug",
            "kiosk_url_path",
            "is_active",
            "allow_self_check_in",
            "kiosk_theme",
            "kiosk_logo",
            "terms_and_conditions",
            "responsibles",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "employer_id", "kiosk_slug", "kiosk_url_path", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        employer, tenant_db = resolve_employer_context(request)
        if employer and tenant_db:
            self.fields["branch"].queryset = Branch.objects.using(tenant_db).filter(employer_id=employer.id)
            self.fields["responsibles"].queryset = (
                Employee.objects.using(tenant_db)
                .filter(employer_id=employer.id, employment_status="ACTIVE")
                .select_related("branch")
            )

    def validate(self, attrs):
        branch = attrs.get("branch") or getattr(self.instance, "branch", None)
        responsibles = attrs.get("responsibles")
        request = self.context.get("request")
        employer, _ = resolve_employer_context(request)
        employer_id = employer.id if employer else None

        if branch and employer_id and branch.employer_id != employer_id:
            raise serializers.ValidationError({"branch": "Branch must belong to the current employer."})

        if responsibles is not None:
            invalid = []
            for employee in responsibles:
                if employee.employment_status != "ACTIVE":
                    invalid.append(f"{employee.full_name} is not active")
                assigned_branch_ids = {str(branch_id) for branch_id in employee.assigned_branch_ids}
                if branch and str(branch.id) not in assigned_branch_ids:
                    invalid.append(f"{employee.full_name} is not part of branch {branch.name}")
                if employer_id and employee.employer_id != employer_id:
                    invalid.append(f"{employee.full_name} is not part of this employer")
            if invalid:
                raise serializers.ValidationError({"responsibles": invalid})
        return attrs

    def create(self, validated_data):
        responsibles = validated_data.pop("responsibles", [])
        request = self.context.get("request")
        employer, tenant_db = resolve_employer_context(request)
        employer_id = employer.id if employer else None
        tenant_db = tenant_db or "default"

        station_name = validated_data.pop("name", None)
        if not station_name:
            raise serializers.ValidationError({"name": "Station name is required."})

        station = FrontdeskStation.objects.using(tenant_db).create(
            employer_id=employer_id,
            name=station_name,
            **validated_data,
        )
        if responsibles:
            station.responsibles.set(responsibles)
        return station

    def update(self, instance, validated_data):
        responsibles = validated_data.pop("responsibles", None)
        branch = validated_data.get("branch")
        if branch and branch != instance.branch:
            raise serializers.ValidationError({"branch": "Station branch cannot be changed."})

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        request = self.context.get("request")
        _, tenant_db = resolve_employer_context(request)
        instance.save(using=tenant_db)

        if responsibles is not None:
            instance.responsibles.set(responsibles)
        return instance

    def validate_kiosk_theme(self, value):
        if value in (None, {}):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("kiosk_theme must be an object.")
        return value

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["kiosk_theme"] = normalize_kiosk_theme(instance.kiosk_theme or {})
        return representation


class StationResponsibleSerializer(serializers.ModelSerializer):
    station_name = serializers.CharField(source="station.name", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta:
        model = StationResponsible
        fields = ["id", "station", "station_name", "employee", "employee_name", "created_at"]
        read_only_fields = ["id", "created_at", "station_name", "employee_name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        employer, tenant_db = resolve_employer_context(request)
        if employer and tenant_db:
            self.fields["station"].queryset = FrontdeskStation.objects.using(tenant_db).filter(employer_id=employer.id)
            self.fields["employee"].queryset = Employee.objects.using(tenant_db).filter(
                employer_id=employer.id, employment_status="ACTIVE"
            )

    def validate(self, attrs):
        station = attrs.get("station") or getattr(self.instance, "station", None)
        employee = attrs.get("employee") or getattr(self.instance, "employee", None)
        request = self.context.get("request")
        employer, _ = resolve_employer_context(request)
        employer_id = employer.id if employer else None

        errors = {}
        if station and employer_id and station.employer_id != employer_id:
            errors["station"] = ["Station must belong to this employer."]
        if employee:
            if employee.employment_status != "ACTIVE":
                errors["employee"] = ["Responsible must be an active employee."]
            assigned_branch_ids = {str(branch_id) for branch_id in employee.assigned_branch_ids}
            if station and station.branch_id and str(station.branch_id) not in assigned_branch_ids:
                errors["employee"] = ["Responsible must belong to the same branch as the station."]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        _, tenant_db = resolve_employer_context(request)
        tenant_db = tenant_db or "default"
        return StationResponsible.objects.using(tenant_db).create(**validated_data)

    def update(self, instance, validated_data):
        request = self.context.get("request")
        _, tenant_db = resolve_employer_context(request)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(using=tenant_db)
        return instance


class VisitorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visitor
        fields = [
            "id",
            "employer_id",
            "full_name",
            "phone",
            "email",
            "organization",
            "id_type",
            "id_number",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "employer_id", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        employer, tenant_db = resolve_employer_context(request)
        employer_id = employer.id if employer else None
        tenant_db = tenant_db or "default"
        return Visitor.objects.using(tenant_db).create(employer_id=employer_id, **validated_data)

    def update(self, instance, validated_data):
        request = self.context.get("request")
        _, tenant_db = resolve_employer_context(request)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(using=tenant_db)
        return instance


class VisitSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    station_name = serializers.CharField(source="station.name", read_only=True)
    host_name = serializers.CharField(source="host.full_name", read_only=True)
    visitor_name = serializers.CharField(source="visitor.full_name", read_only=True)
    visitor_phone = serializers.CharField(source="visitor.phone", read_only=True)
    visitor_email = serializers.EmailField(source="visitor.email", read_only=True)

    class Meta:
        model = Visit
        fields = [
            "id",
            "employer_id",
            "branch",
            "branch_name",
            "station",
            "station_name",
            "visitor",
            "visitor_name",
            "visitor_phone",
            "visitor_email",
            "host",
            "host_name",
            "visit_type",
            "status",
            "visit_purpose",
            "planned_start",
            "planned_end",
            "check_in_time",
            "check_out_time",
            "check_in_method",
            "check_out_by_id",
            "kiosk_session_reference",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "employer_id",
            "check_in_time",
            "check_out_time",
            "check_out_by_id",
            "created_at",
            "updated_at",
            "visitor_phone",
            "visitor_email",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        employer, tenant_db = resolve_employer_context(request)
        if employer and tenant_db:
            self.fields["branch"].queryset = Branch.objects.using(tenant_db).filter(employer_id=employer.id)
            self.fields["station"].queryset = FrontdeskStation.objects.using(tenant_db).filter(employer_id=employer.id)
            self.fields["visitor"].queryset = Visitor.objects.using(tenant_db).filter(employer_id=employer.id)
            self.fields["host"].queryset = Employee.objects.using(tenant_db).filter(
                employer_id=employer.id, employment_status="ACTIVE"
            )

    def validate(self, attrs):
        branch = attrs.get("branch") or getattr(self.instance, "branch", None)
        station = attrs.get("station") or getattr(self.instance, "station", None)
        host = attrs.get("host") or getattr(self.instance, "host", None)
        visitor = attrs.get("visitor") or getattr(self.instance, "visitor", None)
        visit_type = attrs.get("visit_type") or getattr(self.instance, "visit_type", None)
        status = attrs.get("status") or getattr(self.instance, "status", None)
        request = self.context.get("request")
        employer, _ = resolve_employer_context(request)
        employer_id = employer.id if employer else None

        if branch and station and branch.id != station.branch_id:
            raise serializers.ValidationError({"station": "Station must belong to the selected branch."})
        host_branch_ids = {str(branch_id) for branch_id in host.assigned_branch_ids} if host else set()
        if branch and host and str(branch.id) not in host_branch_ids:
            raise serializers.ValidationError({"host": "Host must belong to the selected branch."})
        if branch and host and not host_branch_ids:
            raise serializers.ValidationError({"host": "Host must belong to a branch to be selectable."})
        if host and host.employment_status != "ACTIVE":
            raise serializers.ValidationError({"host": "Host must be an active employee."})
        if station and not station.is_active:
            raise serializers.ValidationError({"station": "Station must be active to receive visitors."})
        if employer_id and visitor and visitor.employer_id != employer_id:
            raise serializers.ValidationError({"visitor": "Visitor must belong to this employer."})
        if employer_id and station and station.employer_id != employer_id:
            raise serializers.ValidationError({"station": "Station must belong to this employer."})
        if visit_type == "WALK_IN" and status is None:
            attrs["status"] = "CHECKED_IN"
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        employer, tenant_db = resolve_employer_context(request)
        employer_id = employer.id if employer else None
        tenant_db = tenant_db or "default"

        status = validated_data.get("status")
        if status == "CHECKED_IN" and not validated_data.get("check_in_time"):
            validated_data["check_in_time"] = timezone.now()

        visit = Visit.objects.using(tenant_db).create(employer_id=employer_id, **validated_data)
        return visit

    def update(self, instance, validated_data):
        request = self.context.get("request")
        _, tenant_db = resolve_employer_context(request)
        status = validated_data.get("status", instance.status)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if status == "CHECKED_IN" and not instance.check_in_time:
            instance.check_in_time = timezone.now()
        if status == "CHECKED_OUT" and not instance.check_out_time:
            instance.check_out_time = timezone.now()

        instance.save(using=tenant_db)
        return instance


class KioskCheckInSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    organization = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    id_type = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    id_number = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    visit_purpose = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    host = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.none())
    kiosk_reference = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        station = self.context.get("station")
        tenant_db = self.context.get("tenant_db")
        if station and tenant_db:
            self.fields["host"].queryset = Employee.objects.using(tenant_db).filter(
                Q(branch_id=station.branch_id) | Q(secondary_branches__id=station.branch_id),
                employer_id=station.employer_id,
                employment_status="ACTIVE",
            ).distinct()

    def validate(self, attrs):
        station = self.context.get("station")
        host = attrs.get("host")
        errors = {}
        if station and host:
            host_branch_ids = {str(branch_id) for branch_id in host.assigned_branch_ids}
            if str(station.branch_id) not in host_branch_ids:
                errors["host"] = ["Host must belong to the same branch as the station."]
            if host.employer_id != station.employer_id:
                errors["host"] = ["Host must belong to this employer."]
            if host.employment_status != "ACTIVE":
                errors["host"] = ["Host must be active."]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        station = self.context["station"]
        tenant_db = self.context["tenant_db"]

        visitor = Visitor.objects.using(tenant_db).create(
            employer_id=station.employer_id,
            full_name=validated_data.get("full_name"),
            phone=validated_data.get("phone"),
            email=validated_data.get("email"),
            organization=validated_data.get("organization"),
            id_type=validated_data.get("id_type"),
            id_number=validated_data.get("id_number"),
        )

        visit = Visit.objects.using(tenant_db).create(
            employer_id=station.employer_id,
            branch=station.branch,
            station=station,
            visitor=visitor,
            host=validated_data.get("host"),
            visit_type="WALK_IN",
            status="CHECKED_IN",
            visit_purpose=validated_data.get("visit_purpose"),
            check_in_time=timezone.now(),
            check_in_method="KIOSK",
            kiosk_session_reference=validated_data.get("kiosk_reference"),
        )
        return visit


class KioskHostSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField()

    class Meta:
        model = Employee
        fields = ["id", "full_name", "email", "phone_number", "job_title", "branch"]
        read_only_fields = fields


class KioskStationSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    kiosk_logo_url = serializers.SerializerMethodField()

    class Meta:
        model = FrontdeskStation
        fields = [
            "id",
            "branch",
            "branch_name",
            "name",
            "kiosk_slug",
            "kiosk_url_path",
            "allow_self_check_in",
            "kiosk_theme",
            "kiosk_logo_url",
            "terms_and_conditions",
            "is_active",
        ]
        read_only_fields = fields

    def get_kiosk_logo_url(self, obj):
        request = self.context.get("request")
        if obj.kiosk_logo and request:
            return request.build_absolute_uri(obj.kiosk_logo.url)
        if obj.kiosk_logo:
            return obj.kiosk_logo.url
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["kiosk_theme"] = normalize_kiosk_theme(instance.kiosk_theme or {})
        return data
