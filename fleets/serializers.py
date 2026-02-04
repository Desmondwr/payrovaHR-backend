from django.conf import settings
from rest_framework import serializers
from rest_framework.utils import model_meta

from accounts.database_utils import ensure_tenant_database_loaded, get_tenant_database_alias

from employees.models import Branch, Employee

from .models import (
    AccidentEvent,
    DriverAssignment,
    FleetSetting,
    Manufacturer,
    ServiceRecord,
    ServiceType,
    Vendor,
    Vehicle,
    VehicleCategory,
    VehicleContract,
    VehicleModel,
)


class TenantPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        queryset = super().get_queryset()
        if queryset is None:
            return queryset
        serializer = getattr(self, "parent", None)
        tenant_db = None
        if serializer and hasattr(serializer, "_resolve_tenant_db_alias"):
            try:
                tenant_db = serializer._resolve_tenant_db_alias()
            except Exception:
                tenant_db = None
        if tenant_db is None and serializer and hasattr(serializer, "parent"):
            parent_serializer = serializer.parent
            if parent_serializer and hasattr(parent_serializer, "_resolve_tenant_db_alias"):
                try:
                    tenant_db = parent_serializer._resolve_tenant_db_alias()
                except Exception:
                    tenant_db = None
        if tenant_db:
            return queryset.using(tenant_db)
        return queryset


class EmployerScopedSerializer(serializers.ModelSerializer):
    def _set_field_queryset(self, field_name, queryset):
        field = self.fields.get(field_name)
        if not field:
            return
        if hasattr(field, "child_relation"):
            field.child_relation.queryset = queryset
        else:
            field.queryset = queryset

    def get_extra_kwargs(self):
        extra_kwargs = super().get_extra_kwargs()
        employer_kwargs = extra_kwargs.setdefault("employer_id", {})
        employer_kwargs["read_only"] = True
        return extra_kwargs

    def create(self, validated_data):
        tenant_db = self._resolve_tenant_db_alias()
        ModelClass = self.Meta.model
        info = model_meta.get_field_info(ModelClass)
        many_to_many = {}

        for field_name in list(validated_data.keys()):
            if field_name in info.relations and info.relations[field_name].to_many:
                many_to_many[field_name] = validated_data.pop(field_name)

        instance = ModelClass.objects.using(tenant_db).create(**validated_data)

        for field_name, value in many_to_many.items():
            relation_manager = getattr(instance, field_name)
            relation_manager.set(value)

        return instance

    def update(self, instance, validated_data):
        tenant_db = self._resolve_tenant_db_alias()
        info = model_meta.get_field_info(instance.__class__)
        m2m_fields = []

        for attr, value in validated_data.items():
            if attr in info.relations and info.relations[attr].to_many:
                m2m_fields.append((attr, value))
            else:
                setattr(instance, attr, value)

        instance.save(using=tenant_db)

        for attr, value in m2m_fields:
            relation_manager = getattr(instance, attr)
            relation_manager.set(value)

        return instance

    def _resolve_tenant_db_alias(self):
        instance = getattr(self, "instance", None)
        if instance is not None and not isinstance(instance, (list, tuple)):
            instance_db = getattr(instance._state, "db", None)
            if instance_db:
                return instance_db
        tenant_db = self.context.get("tenant_db")
        if tenant_db:
            return tenant_db
        tenant_db = getattr(settings, "CURRENT_TENANT_DB", None)
        if tenant_db:
            return tenant_db

        employer_id = self.context.get("employer_id")
        alias = self._load_alias_for_employer(employer_id)
        if alias:
            return alias

        request = self.context.get("request")
        if request and hasattr(request, "headers"):
            header_value = request.headers.get("x-employer-id")
            if header_value:
                try:
                    header_id = int(header_value)
                except (TypeError, ValueError):
                    header_id = None
                alias = self._load_alias_for_employer(header_id)
                if alias:
                    return alias

        return tenant_db or "default"

    def _load_alias_for_employer(self, employer_id):
        if not employer_id:
            return None
        from accounts.models import EmployerProfile

        employer_profile = EmployerProfile.objects.filter(id=employer_id).first()
        if employer_profile and employer_profile.database_name:
            ensure_tenant_database_loaded(employer_profile)
            return get_tenant_database_alias(employer_profile)
        return None


class ManufacturerSerializer(EmployerScopedSerializer):
    class Meta:
        model = Manufacturer
        fields = [
            "id",
            "employer_id",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]


class VehicleCategorySerializer(EmployerScopedSerializer):
    class Meta:
        model = VehicleCategory
        fields = ["id", "employer_id", "name", "description", "priority", "is_active", "created_at", "updated_at"]


class VehicleModelSerializer(EmployerScopedSerializer):
    manufacturer_name = serializers.CharField(source="manufacturer.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self._resolve_tenant_db_alias()
        self.fields["manufacturer"].queryset = Manufacturer.objects.using(tenant_db)
        self.fields["category"].queryset = VehicleCategory.objects.using(tenant_db)

    class Meta:
        model = VehicleModel
        fields = [
            "id",
            "employer_id",
            "name",
            "manufacturer",
            "manufacturer_name",
            "category",
            "category_name",
            "vehicle_type",
            "seating_capacity",
            "doors",
            "fuel_type",
            "transmission",
            "power_source",
            "co2_emissions",
            "is_active",
            "created_at",
            "updated_at",
        ]


class ServiceTypeSerializer(EmployerScopedSerializer):
    def create(self, validated_data):
        tenant_db = self._resolve_tenant_db_alias()
        return ServiceType.objects.using(tenant_db).create(**validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        tenant_db = self._resolve_tenant_db_alias()
        instance.save(using=tenant_db)
        return instance

    class Meta:
        model = ServiceType
        fields = [
            "id",
            "employer_id",
            "name",
            "description",
            "severity",
            "default_stage",
            "is_active",
            "created_at",
            "updated_at",
        ]


class VendorSerializer(EmployerScopedSerializer):
    service_types = TenantPrimaryKeyRelatedField(many=True, queryset=ServiceType.objects.all())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self._resolve_tenant_db_alias()
        self._set_field_queryset("service_types", ServiceType.objects.using(tenant_db))

    def create(self, validated_data):
        tenant_db = self._resolve_tenant_db_alias()
        service_types = validated_data.pop("service_types", [])
        vendor = Vendor.objects.using(tenant_db).create(**validated_data)
        if service_types:
            vendor.service_types.set(service_types)
        return vendor

    def update(self, instance, validated_data):
        service_types = validated_data.pop("service_types", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        tenant_db = self._resolve_tenant_db_alias()
        instance.save(using=tenant_db)
        if service_types is not None:
            instance.service_types.set(service_types)
        return instance

    class Meta:
        model = Vendor
        fields = [
            "id",
            "employer_id",
            "name",
            "vendor_type",
            "contact_email",
            "contact_phone",
            "address",
            "service_types",
            "is_active",
            "created_at",
            "updated_at",
        ]


class FleetSettingSerializer(EmployerScopedSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self._resolve_tenant_db_alias()
        self.fields["default_vendor"].queryset = Vendor.objects.using(tenant_db)

    def create(self, validated_data):
        tenant_db = self._resolve_tenant_db_alias()
        employer_id = validated_data.pop("employer_id", None) or self.context.get("employer_id")
        if employer_id is None:
            raise serializers.ValidationError({"employer_id": "Employer context is required."})
        instance, _created = FleetSetting.objects.using(tenant_db).update_or_create(
            employer_id=employer_id,
            defaults=validated_data,
        )
        return instance

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        tenant_db = self._resolve_tenant_db_alias()
        instance.save(using=tenant_db)
        return instance

    class Meta:
        model = FleetSetting
        fields = [
            "id",
            "employer_id",
            "contract_alert_days",
            "allow_new_requests",
            "default_vendor",
            "notification_channels",
            "allow_requests_from_inventory_only",
            "created_at",
            "updated_at",
        ]


class VehicleSerializer(EmployerScopedSerializer):
    model_name = serializers.CharField(source="vehicle_model.name", read_only=True)
    manufacturer_name = serializers.CharField(source="vehicle_model.manufacturer.name", read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self._resolve_tenant_db_alias()
        self.fields["vehicle_model"].queryset = VehicleModel.objects.using(tenant_db)

    def create(self, validated_data):
        tenant_db = self._resolve_tenant_db_alias()
        return Vehicle.objects.using(tenant_db).create(**validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        tenant_db = self._resolve_tenant_db_alias()
        instance.save(using=tenant_db)
        return instance

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "employer_id",
            "vehicle_model",
            "model_name",
            "manufacturer_name",
            "license_plate",
            "status",
            "location",
            "odometer",
            "tags",
            "external_id",
            "notes",
            "created_at",
            "updated_at",
        ]


class DriverAssignmentSerializer(EmployerScopedSerializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.none())
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all(), allow_null=True, required=False)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    vehicle = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all())
    vehicle_license_plate = serializers.CharField(source="vehicle.license_plate", read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        employer_id = self.context.get("employer_id")
        tenant_db = self._resolve_tenant_db_alias()
        branch_qs = Branch.objects.using(tenant_db)
        employee_qs = Employee.objects.using(tenant_db)
        vehicle_qs = Vehicle.objects.using(tenant_db)
        branch_field = self.fields["branch"]
        if employer_id:
            branch_field.queryset = branch_qs.filter(employer_id=employer_id)
        else:
            branch_field.queryset = branch_qs
        branch_field.required = self.instance is None
        self.fields["employee"].queryset = employee_qs
        self.fields["vehicle"].queryset = vehicle_qs

    def validate(self, attrs):
        branch = attrs.get("branch") or (self.instance.branch if self.instance else None)
        if branch is None:
            raise serializers.ValidationError({"branch": "Driver assignment must reference a branch."})
        employer_id = self.context.get("employer_id")
        if employer_id and branch.employer_id != employer_id:
            raise serializers.ValidationError({"branch": "Branch must belong to the current employer."})
        attrs["branch"] = branch
        return super().validate(attrs)

    def create(self, validated_data):
        tenant_db = self._resolve_tenant_db_alias()
        return DriverAssignment.objects.using(tenant_db).create(**validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        tenant_db = self._resolve_tenant_db_alias()
        instance.save(using=tenant_db)
        return instance

    class Meta:
        model = DriverAssignment
        fields = [
            "id",
            "employer_id",
            "vehicle",
            "vehicle_license_plate",
            "branch",
            "branch_name",
            "employee",
            "employee_name",
            "external_driver_name",
            "external_driver_contact",
            "assignment_type",
            "start_date",
            "end_date",
            "assignment_notes",
            "assigned_at",
            "created_at",
            "updated_at",
        ]


class VehicleContractSerializer(EmployerScopedSerializer):
    vehicle = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all())
    vehicle_license_plate = serializers.CharField(source="vehicle.license_plate", read_only=True)
    responsible_person = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all(), allow_null=True, required=False)
    responsible_person_name = serializers.CharField(source="responsible_person.full_name", read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self._resolve_tenant_db_alias()
        self.fields["vehicle"].queryset = Vehicle.objects.using(tenant_db)
        self.fields["responsible_person"].queryset = Employee.objects.using(tenant_db)

    def create(self, validated_data):
        tenant_db = self._resolve_tenant_db_alias()
        return VehicleContract.objects.using(tenant_db).create(**validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        tenant_db = self._resolve_tenant_db_alias()
        instance.save(using=tenant_db)
        return instance

    class Meta:
        model = VehicleContract
        fields = [
            "id",
            "employer_id",
            "vehicle",
            "vehicle_license_plate",
            "start_date",
            "end_date",
            "responsible_person",
            "responsible_person_name",
            "catalog_value",
            "residual_value",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]


class ServiceRecordSerializer(EmployerScopedSerializer):
    vehicle = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all())
    service_type = serializers.PrimaryKeyRelatedField(queryset=ServiceType.objects.all())
    vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self._resolve_tenant_db_alias()
        self.fields["vehicle"].queryset = Vehicle.objects.using(tenant_db)
        self.fields["service_type"].queryset = ServiceType.objects.using(tenant_db)
        self.fields["vendor"].queryset = Vendor.objects.using(tenant_db)

    class Meta:
        model = ServiceRecord
        fields = [
            "id",
            "employer_id",
            "vehicle",
            "service_type",
            "vendor",
            "date",
            "odometer",
            "stage",
            "cost_estimate",
            "cost_final",
            "notes",
            "attachments",
            "created_at",
            "updated_at",
        ]


class AccidentEventSerializer(EmployerScopedSerializer):
    vehicle = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all())
    services = serializers.PrimaryKeyRelatedField(queryset=ServiceRecord.objects.all(), many=True, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant_db = self._resolve_tenant_db_alias()
        self.fields["vehicle"].queryset = Vehicle.objects.using(tenant_db)
        self._set_field_queryset("services", ServiceRecord.objects.using(tenant_db))

    class Meta:
        model = AccidentEvent
        fields = [
            "id",
            "employer_id",
            "vehicle",
            "category",
            "reported_at",
            "services",
            "total_estimated_cost",
            "total_actual_cost",
            "notes",
            "created_at",
            "updated_at",
        ]
