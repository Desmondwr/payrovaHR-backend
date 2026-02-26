from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.views import APIView

from accounts.database_utils import (
    ensure_tenant_database_loaded,
    get_employee_tenant_db_from_membership,
    get_tenant_database_alias,
)
from accounts.middleware import get_current_tenant_db
from accounts.permissions import (
    EmployerAccessPermission,
    EmployerOrEmployeeAccessPermission,
    IsEmployee,
    IsAuthenticated,
)
from accounts.rbac import get_active_employer, is_delegate_user
from accounts.utils import api_response
from employees.models import Employee

from .models import (
    BillingInvoice,
    BillingPayout,
    BillingPayoutBatch,
    BillingPayoutConfiguration,
    BillingPlan,
    BillingTransaction,
    EmployerSubscription,
    FundingMethod,
    GbPayEmployerConnection,
    PayoutMethod,
)
from .serializers import (
    BillingInvoiceSerializer,
    BillingPayoutBatchSerializer,
    BillingPayoutSerializer,
    BillingPayoutConfigurationSerializer,
    BillingPlanSerializer,
    BillingTransactionSerializer,
    EmployerSubscriptionSerializer,
    FundingDefaultSerializer,
    FundingMethodSerializer,
    GbPayBatchCreateSerializer,
    GbPayConnectionSerializer,
    InvoiceIssueSerializer,
    InvoicePaymentUpdateSerializer,
    PayoutDefaultSerializer,
    PayoutMethodSerializer,
    PayoutStatusUpdateSerializer,
    SubscriptionCreateSerializer,
    TransactionRefundSerializer,
)
from .gbpay_ops import (
    CATEGORY_TYPE_BANK,
    CATEGORY_TYPE_MOBILE,
    build_gbpay_context,
    create_payout_batch,
    get_active_connection,
    process_batch,
    process_payout,
    save_gbpay_connection,
    set_connection_active,
)
from .gbpay_service import GbPayApiError, GbPayService
from .services import (
    create_invoice_for_subscription,
    create_payout_with_transactions,
    create_refund_transaction,
    ensure_billing_payout_configuration,
    get_payout_provider,
    generate_payout_receipt,
    mark_invoice_failed,
    mark_invoice_paid,
    set_default_funding_method,
    set_default_payout_method,
    render_payout_batch_pdf,
    render_payout_batch_csv,
    update_payout_status,
)


class BillingEmployerContextMixin:
    def _resolve_employer(self):
        user = self.request.user
        if getattr(user, "employer_profile", None):
            return user.employer_profile

        resolved = get_active_employer(self.request, require_context=False)
        if resolved and (user.is_admin or user.is_superuser or is_delegate_user(user, resolved.id)):
            return resolved

        employee = getattr(user, "employee_profile", None)
        if employee and employee.employer_id:
            return get_active_employer(self.request, require_context=False)
        return None

    def get_employer_id(self):
        employer = self._resolve_employer()
        if employer:
            return employer.id
        raise PermissionDenied("Employer context could not be resolved.")

    def get_tenant_db_alias(self):
        tenant_db = get_current_tenant_db()
        if tenant_db and tenant_db != "default":
            return tenant_db

        employer = self._resolve_employer()
        if employer:
            if employer.database_name:
                return ensure_tenant_database_loaded(employer)
            return get_tenant_database_alias(employer)
        return "default"


class BillingTenantViewSet(BillingEmployerContextMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    permission_map = {"*": ["billing.manage"]}

    def get_queryset(self):
        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()
        return super().get_queryset().using(tenant_db).filter(employer_id=employer_id)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["tenant_db"] = self.get_tenant_db_alias()
        context["employer_id"] = self.get_employer_id()
        context["actor_id"] = getattr(self.request.user, "id", None)
        return context

    def _create_in_tenant(self, serializer, **extra_fields):
        tenant_db = self.get_tenant_db_alias()
        model_cls = serializer.Meta.model
        create_data = dict(serializer.validated_data)
        create_data.update(extra_fields)
        instance = model_cls.objects.using(tenant_db).create(**create_data)
        serializer.instance = instance
        return instance

    def perform_create(self, serializer):
        self._create_in_tenant(serializer, employer_id=self.get_employer_id())

    def perform_destroy(self, instance):
        instance.delete(using=self.get_tenant_db_alias())


class BillingPayoutConfigurationView(BillingEmployerContextMixin, APIView):
    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["billing.manage"]

    def get(self, request):
        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()
        config = ensure_billing_payout_configuration(employer_id=employer_id, tenant_db=tenant_db)
        serializer = BillingPayoutConfigurationSerializer(config)
        return api_response(success=True, message="Billing payout configuration retrieved.", data=serializer.data)

    def put(self, request):
        return self._update_config(request)

    def patch(self, request):
        return self._update_config(request)

    def _update_config(self, request):
        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()
        config = ensure_billing_payout_configuration(employer_id=employer_id, tenant_db=tenant_db)
        serializer = BillingPayoutConfigurationSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(success=True, message="Billing payout configuration updated.", data=serializer.data)


class BillingPayoutReadinessView(BillingEmployerContextMixin, APIView):
    permission_classes = [IsAuthenticated, EmployerAccessPermission]
    required_permissions = ["billing.payout.view", "billing.manage"]

    def get(self, request):
        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()
        category = (request.query_params.get("category") or BillingPayout.CATEGORY_PAYROLL).upper()
        if category not in [BillingPayout.CATEGORY_PAYROLL, BillingPayout.CATEGORY_EXPENSE]:
            raise ValidationError("Category must be PAYROLL or EXPENSE.")

        provider = (get_payout_provider(employer_id=employer_id, tenant_db=tenant_db, category=category) or "").upper()
        if provider == "MANUAL":
            return api_response(
                success=True,
                message="Payout readiness retrieved.",
                data={
                    "provider": provider,
                    "ready": True,
                    "total_employees": 0,
                    "ready_employees": 0,
                    "missing_default": 0,
                    "unverified_default": 0,
                },
            )

        employees = Employee.objects.using(tenant_db).filter(employer_id=employer_id)
        total = employees.count()
        default_methods = PayoutMethod.objects.using(tenant_db).filter(
            employee__employer_id=employer_id,
            is_active=True,
            is_default=True,
        )
        ready_ids = default_methods.filter(verification_status="VERIFIED").values_list("employee_id", flat=True)
        ready_count = employees.filter(id__in=ready_ids).count()
        default_count = default_methods.values("employee_id").distinct().count()
        unverified_default = default_methods.exclude(
            verification_status="VERIFIED"
        ).values("employee_id").distinct().count()
        missing_default = max(0, total - default_count)
        return api_response(
            success=True,
            message="Payout readiness retrieved.",
            data={
                "provider": provider,
                "ready": ready_count == total if total else True,
                "total_employees": total,
                "ready_employees": ready_count,
                "missing_default": missing_default,
                "unverified_default": unverified_default,
            },
        )


class FundingMethodViewSet(BillingTenantViewSet):
    queryset = FundingMethod.objects.all()
    serializer_class = FundingMethodSerializer
    permission_map = {
        "list": ["billing.funding.view", "billing.manage"],
        "retrieve": ["billing.funding.view", "billing.manage"],
        "create": ["billing.funding.create", "billing.manage"],
        "update": ["billing.funding.update", "billing.manage"],
        "partial_update": ["billing.funding.update", "billing.manage"],
        "destroy": ["billing.funding.delete", "billing.manage"],
        "set_default": ["billing.funding.update", "billing.manage"],
        "*": ["billing.manage"],
    }

    def perform_create(self, serializer):
        serializer.save(employer_id=self.get_employer_id())

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return api_response(success=True, message="Funding method deleted.", data={})

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        method = self.get_object()
        serializer = FundingDefaultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data["scope"]
        tenant_db = self.get_tenant_db_alias()
        set_default_funding_method(
            method,
            tenant_db=tenant_db,
            scope=scope,
            actor_id=getattr(request.user, "id", None),
            request=request,
        )
        return api_response(success=True, message="Default funding method updated.", data=FundingMethodSerializer(method).data)


class GbPayConnectionViewSet(BillingTenantViewSet):
    queryset = GbPayEmployerConnection.objects.all()
    serializer_class = GbPayConnectionSerializer
    permission_map = {
        "list": ["billing.gbpay.view", "billing.manage"],
        "retrieve": ["billing.gbpay.view", "billing.manage"],
        "create": ["billing.gbpay.manage", "billing.manage"],
        "update": ["billing.gbpay.manage", "billing.manage"],
        "partial_update": ["billing.gbpay.manage", "billing.manage"],
        "destroy": ["billing.gbpay.manage", "billing.manage"],
        "test": ["billing.gbpay.manage", "billing.manage"],
        "enable": ["billing.gbpay.manage", "billing.manage"],
        "disable": ["billing.gbpay.manage", "billing.manage"],
        "*": ["billing.manage"],
    }

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()
        credentials = {
            "api_key": serializer.validated_data.get("api_key"),
            "secret_key": serializer.validated_data.get("secret_key"),
            "scope": serializer.validated_data.get("scope"),
        }
        connection = save_gbpay_connection(
            tenant_db=tenant_db,
            employer_id=employer_id,
            credentials=credentials,
            environment=serializer.validated_data.get("environment") or GbPayEmployerConnection.ENV_PRODUCTION,
            actor_id=getattr(request.user, "id", None),
            label=serializer.validated_data.get("label") or "",
        )
        return api_response(
            success=True,
            message="GbPay connection saved.",
            data=GbPayConnectionSerializer(connection).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        connection = self.get_object()
        self.perform_destroy(connection)
        return api_response(success=True, message="GbPay connection deleted.", data={})

    def update(self, request, *args, **kwargs):
        connection = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()

        credential_fields = {"api_key", "secret_key", "scope"}
        provided = credential_fields.intersection(serializer.validated_data.keys())
        if provided:
            missing = [key for key in ["api_key", "secret_key", "scope"] if not serializer.validated_data.get(key)]
            if missing:
                raise ValidationError("Updating credentials requires api_key, secret_key, and scope.")
            credentials = {
                "api_key": serializer.validated_data.get("api_key"),
                "secret_key": serializer.validated_data.get("secret_key"),
                "scope": serializer.validated_data.get("scope"),
            }
            connection = save_gbpay_connection(
                tenant_db=tenant_db,
                employer_id=employer_id,
                credentials=credentials,
                environment=serializer.validated_data.get("environment") or connection.environment,
                actor_id=getattr(request.user, "id", None),
                connection=connection,
                label=serializer.validated_data.get("label") or connection.label,
            )
        else:
            if "environment" in serializer.validated_data:
                raise ValidationError("Changing environment requires credentials re-validation.")
            if "label" in serializer.validated_data:
                connection.label = serializer.validated_data.get("label") or ""
                connection.save(using=tenant_db, update_fields=["label", "updated_at"])

        return api_response(success=True, message="GbPay connection updated.", data=GbPayConnectionSerializer(connection).data)

    @action(detail=True, methods=["post"], url_path="test")
    def test(self, request, pk=None):
        connection = self.get_object()
        tenant_db = self.get_tenant_db_alias()
        connection = set_connection_active(
            connection=connection,
            tenant_db=tenant_db,
            actor_id=getattr(request.user, "id", None),
            enable=True,
        )
        return api_response(success=True, message="GbPay connection validated.", data=GbPayConnectionSerializer(connection).data)

    @action(detail=True, methods=["post"], url_path="enable")
    def enable(self, request, pk=None):
        connection = self.get_object()
        tenant_db = self.get_tenant_db_alias()
        connection = set_connection_active(
            connection=connection,
            tenant_db=tenant_db,
            actor_id=getattr(request.user, "id", None),
            enable=True,
        )
        return api_response(success=True, message="GbPay connection enabled.", data=GbPayConnectionSerializer(connection).data)

    @action(detail=True, methods=["post"], url_path="disable")
    def disable(self, request, pk=None):
        connection = self.get_object()
        tenant_db = self.get_tenant_db_alias()
        connection = set_connection_active(
            connection=connection,
            tenant_db=tenant_db,
            actor_id=getattr(request.user, "id", None),
            enable=False,
        )
        return api_response(success=True, message="GbPay connection disabled.", data=GbPayConnectionSerializer(connection).data)


class PayoutMethodViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsEmployee]
    serializer_class = PayoutMethodSerializer

    def get_queryset(self):
        tenant_db, employee = resolve_employee_context(self.request)
        if not employee:
            return PayoutMethod.objects.none()
        return PayoutMethod.objects.using(tenant_db).filter(employee=employee, is_active=True)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        tenant_db, employee = resolve_employee_context(self.request)
        context["tenant_db"] = tenant_db
        context["employee"] = employee
        context["actor_id"] = getattr(self.request.user, "id", None)
        return context

    def perform_create(self, serializer):
        tenant_db, employee = resolve_employee_context(self.request)
        if not employee:
            raise PermissionDenied("Employee context required.")
        serializer.save(employee=employee)

    def perform_destroy(self, instance):
        tenant_db, _ = resolve_employee_context(self.request)
        instance.is_active = False
        instance.is_default = False
        instance.save(using=tenant_db, update_fields=["is_active", "is_default", "updated_at"])

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return api_response(success=True, message="Payout method deleted.", data={})

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        method = self.get_object()
        serializer = PayoutDefaultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant_db, _ = resolve_employee_context(request)
        set_default_payout_method(
            method,
            tenant_db=tenant_db,
            actor_id=getattr(request.user, "id", None),
            request=request,
        )
        return api_response(success=True, message="Default payout method updated.", data=PayoutMethodSerializer(method).data)


class GbPayCatalogContextMixin(BillingEmployerContextMixin):
    def resolve_gbpay_context(self):
        user = self.request.user
        if getattr(user, "is_employee", False) and not getattr(user, "employer_profile", None):
            tenant_db, employee = resolve_employee_context(self.request)
            if not employee:
                raise PermissionDenied("Employee context required.")
            employer_id = getattr(employee, "employer_id", None)
            if not employer_id:
                raise PermissionDenied("Employer context required.")
            return tenant_db, employer_id
        return self.get_tenant_db_alias(), self.get_employer_id()

    def get_gbpay_service(self) -> GbPayService:
        tenant_db, employer_id = self.resolve_gbpay_context()
        connection = get_active_connection(employer_id, tenant_db)
        if not connection:
            raise ValidationError("Active GbPay connection not found for employer.")
        ctx = build_gbpay_context(connection)
        return GbPayService(ctx)

    @staticmethod
    def _unwrap_payload(payload):
        if isinstance(payload, dict):
            if "data" in payload:
                return payload.get("data")
            if "content" in payload:
                return payload.get("content")
        return payload

    @staticmethod
    def _pick_field(item, keys):
        if not isinstance(item, dict):
            return None
        for key in keys:
            value = item.get(key)
            if value is not None and value != "":
                return value
        return None

    @staticmethod
    def _normalize_category(category: str) -> str:
        value = (category or "").upper()
        if value in {"BANK", "BANK_ACCOUNT"}:
            return CATEGORY_TYPE_BANK
        if value in {"MOBILE", "MOBILE_MONEY", "MOBILE_WALLET"}:
            return CATEGORY_TYPE_MOBILE
        return value

    @staticmethod
    def _normalize_provider_type(provider_type: str) -> str:
        value = (provider_type or "").upper()
        if value in {"BANK", "BANK_ACCOUNT"}:
            return "BANK_ACCOUNT"
        if value in {"MOBILE", "MOBILE_MONEY", "MOBILE_WALLET"}:
            return "MOBILE_MONEY"
        return value

    def _normalize_countries(self, items):
        output = []
        if not isinstance(items, list):
            return output
        for item in items:
            if not isinstance(item, dict):
                continue
            country_id = self._pick_field(item, ["countryId", "country_id", "id"])
            country_code = self._pick_field(
                item,
                ["countryCode", "country_code", "code", "isoCode", "alpha2Code", "shortCode"],
            )
            name = self._pick_field(item, ["name", "countryName", "label", "displayName"])
            if country_id is None and country_code is None and name is None:
                continue
            output.append({"countryId": country_id, "countryCode": country_code, "name": name})
        return output

    def _normalize_banks(self, items):
        output = []
        if not isinstance(items, list):
            return output
        for item in items:
            if not isinstance(item, dict):
                continue
            bank_code = self._pick_field(item, ["bankCode", "bank_code", "code"])
            name = self._pick_field(item, ["name", "bankName", "bank_name", "label"])
            if bank_code is None and name is None:
                continue
            output.append({"bankCode": bank_code, "name": name})
        return output

    def _normalize_operators(self, items):
        output = []
        if not isinstance(items, list):
            return output
        for item in items:
            if not isinstance(item, dict):
                continue
            operator_code = self._pick_field(item, ["operatorCode", "operator_code", "code"])
            name = self._pick_field(item, ["name", "operatorName", "operator_name", "label"])
            if operator_code is None and name is None:
                continue
            output.append({"operatorCode": operator_code, "name": name})
        return output

    def _normalize_products(self, items):
        output = []
        if not isinstance(items, list):
            return output
        for item in items:
            if not isinstance(item, dict):
                continue
            entity_uuid = self._pick_field(
                item,
                ["entityProduct", "entityProductUuid", "entity_product_uuid", "uuid", "productUuid", "id"],
            )
            name = self._pick_field(item, ["name", "productName", "label", "displayName"])
            if entity_uuid is None and name is None:
                continue
            output.append({"entityProductUuid": entity_uuid, "name": name})
        return output

    def _normalize_currencies(self, items):
        output = []
        if not isinstance(items, list):
            return output
        for item in items:
            if isinstance(item, str):
                output.append(item.upper())
                continue
            if isinstance(item, dict):
                code = self._pick_field(item, ["code", "currency", "value", "name"])
                if code:
                    output.append(str(code).upper())
        return output


class GbPayCountriesView(GbPayCatalogContextMixin, APIView):
    permission_classes = [IsAuthenticated, EmployerOrEmployeeAccessPermission]
    required_permissions = ["billing.gbpay.view", "billing.manage"]

    def get(self, request):
        provider_type = (
            request.query_params.get("provider_type")
            or request.query_params.get("providerType")
            or request.query_params.get("type")
        )
        provider_type = self._normalize_provider_type(provider_type)
        if not provider_type:
            provider_type = "BANK_ACCOUNT"
        try:
            payload = self.get_gbpay_service().getCountries(provider_type)
        except GbPayApiError as exc:
            raise ValidationError(str(exc))
        data = self._normalize_countries(self._unwrap_payload(payload) or [])
        return api_response(success=True, message="GbPay countries retrieved.", data=data)


class GbPayBanksView(GbPayCatalogContextMixin, APIView):
    permission_classes = [IsAuthenticated, EmployerOrEmployeeAccessPermission]
    required_permissions = ["billing.gbpay.view", "billing.manage"]

    def get(self, request):
        country_id = request.query_params.get("country_id") or request.query_params.get("countryId")
        if not country_id:
            raise ValidationError("country_id is required.")
        try:
            payload = self.get_gbpay_service().getSimplifiedBanksByCountry(country_id)
        except GbPayApiError as exc:
            raise ValidationError(str(exc))
        data = self._normalize_banks(self._unwrap_payload(payload) or [])
        return api_response(success=True, message="GbPay banks retrieved.", data=data)


class GbPayOperatorsView(GbPayCatalogContextMixin, APIView):
    permission_classes = [IsAuthenticated, EmployerOrEmployeeAccessPermission]
    required_permissions = ["billing.gbpay.view", "billing.manage"]

    def get(self, request):
        country_id = request.query_params.get("country_id") or request.query_params.get("countryId")
        if not country_id:
            raise ValidationError("country_id is required.")
        try:
            payload = self.get_gbpay_service().getSimplifiedOperatorsByCountry(country_id)
        except GbPayApiError as exc:
            raise ValidationError(str(exc))
        data = self._normalize_operators(self._unwrap_payload(payload) or [])
        return api_response(success=True, message="GbPay operators retrieved.", data=data)


class GbPayProductsView(GbPayCatalogContextMixin, APIView):
    permission_classes = [IsAuthenticated, EmployerOrEmployeeAccessPermission]
    required_permissions = ["billing.gbpay.view", "billing.manage"]

    def get(self, request):
        category = (
            request.query_params.get("category")
            or request.query_params.get("categoryType")
            or request.query_params.get("category_type")
            or ""
        )
        category = self._normalize_category(category)
        country_id = request.query_params.get("country_id") or request.query_params.get("countryId")
        if not category:
            raise ValidationError("category is required.")
        if not country_id:
            raise ValidationError("country_id is required.")
        try:
            payload = self.get_gbpay_service().getCategoryProducts(category, country_id)
        except GbPayApiError as exc:
            raise ValidationError(str(exc))
        data = self._normalize_products(self._unwrap_payload(payload) or [])
        return api_response(success=True, message="GbPay products retrieved.", data=data)


class GbPayCurrenciesView(GbPayCatalogContextMixin, APIView):
    permission_classes = [IsAuthenticated, EmployerOrEmployeeAccessPermission]
    required_permissions = ["billing.gbpay.view", "billing.manage"]

    def get(self, request):
        country_code = request.query_params.get("country_code") or request.query_params.get("countryCode")
        if not country_code:
            raise ValidationError("country_code is required.")
        try:
            payload = self.get_gbpay_service().getSupportedCurrencies(country_code)
        except GbPayApiError as exc:
            raise ValidationError(str(exc))
        data = self._normalize_currencies(self._unwrap_payload(payload) or [])
        return api_response(success=True, message="GbPay currencies retrieved.", data=data)


class BillingPlanViewSet(BillingTenantViewSet):
    queryset = BillingPlan.objects.all()
    serializer_class = BillingPlanSerializer
    permission_map = {
        "list": ["billing.plan.view", "billing.manage"],
        "retrieve": ["billing.plan.view", "billing.manage"],
        "create": ["billing.plan.create", "billing.manage"],
        "update": ["billing.plan.update", "billing.manage"],
        "partial_update": ["billing.plan.update", "billing.manage"],
        "destroy": ["billing.plan.delete", "billing.manage"],
        "*": ["billing.manage"],
    }


class EmployerSubscriptionViewSet(BillingTenantViewSet):
    queryset = EmployerSubscription.objects.all()
    serializer_class = EmployerSubscriptionSerializer
    permission_map = {
        "list": ["billing.subscription.view", "billing.manage"],
        "retrieve": ["billing.subscription.view", "billing.manage"],
        "create": ["billing.subscription.create", "billing.manage"],
        "update": ["billing.subscription.update", "billing.manage"],
        "partial_update": ["billing.subscription.update", "billing.manage"],
        "destroy": ["billing.subscription.update", "billing.manage"],
        "issue_invoice": ["billing.subscription.charge", "billing.manage"],
        "cancel": ["billing.subscription.cancel", "billing.manage"],
        "resume": ["billing.subscription.update", "billing.manage"],
        "*": ["billing.manage"],
    }

    def create(self, request, *args, **kwargs):
        serializer = SubscriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()

        plan = BillingPlan.objects.using(tenant_db).filter(
            id=serializer.validated_data["plan_id"], employer_id=employer_id
        ).first()
        if not plan:
            raise ValidationError("Billing plan not found.")

        start_date = serializer.validated_data.get("start_date") or timezone.now().date()
        funding_method_id = serializer.validated_data.get("funding_method_id")
        funding_method = None
        if funding_method_id:
            funding_method = FundingMethod.objects.using(tenant_db).filter(
                id=funding_method_id,
                employer_id=employer_id,
            ).first()

        status_value = (
            EmployerSubscription.STATUS_TRIALING if plan.trial_days else EmployerSubscription.STATUS_ACTIVE
        )
        current_period_end = start_date + timedelta(days=max(plan.trial_days - 1, 0)) if plan.trial_days else None
        next_billing_date = current_period_end + timedelta(days=1) if current_period_end else None

        subscription = EmployerSubscription.objects.using(tenant_db).create(
            employer_id=employer_id,
            plan=plan,
            status=status_value,
            billing_cycle_anchor=start_date,
            current_period_start=start_date,
            current_period_end=current_period_end,
            next_billing_date=next_billing_date,
            auto_renew=serializer.validated_data.get("auto_renew", True),
            default_funding_method=funding_method,
        )

        output = EmployerSubscriptionSerializer(subscription).data
        return api_response(success=True, message="Subscription created.", data=output, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="issue-invoice")
    def issue_invoice(self, request, pk=None):
        subscription = self.get_object()
        serializer = InvoiceIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invoice = create_invoice_for_subscription(
            subscription=subscription,
            tenant_db=self.get_tenant_db_alias(),
            actor_id=getattr(request.user, "id", None),
            auto_charge=serializer.validated_data.get("auto_charge", True),
            request=request,
        )
        return api_response(
            success=True,
            message="Invoice issued.",
            data=BillingInvoiceSerializer(invoice).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        subscription = self.get_object()
        tenant_db = self.get_tenant_db_alias()
        subscription.status = EmployerSubscription.STATUS_CANCELED
        subscription.canceled_at = timezone.now()
        subscription.save(using=tenant_db, update_fields=["status", "canceled_at", "updated_at"])
        return api_response(success=True, message="Subscription cancelled.", data=EmployerSubscriptionSerializer(subscription).data)

    @action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        subscription = self.get_object()
        tenant_db = self.get_tenant_db_alias()
        subscription.status = EmployerSubscription.STATUS_ACTIVE
        subscription.save(using=tenant_db, update_fields=["status", "updated_at"])
        return api_response(success=True, message="Subscription resumed.", data=EmployerSubscriptionSerializer(subscription).data)


class BillingInvoiceViewSet(BillingTenantViewSet):
    queryset = BillingInvoice.objects.all()
    serializer_class = BillingInvoiceSerializer
    http_method_names = ["get", "head", "options", "post"]
    permission_map = {
        "list": ["billing.invoice.view", "billing.manage"],
        "retrieve": ["billing.invoice.view", "billing.manage"],
        "download": ["billing.invoice.view", "billing.manage"],
        "mark_paid": ["billing.invoice.update", "billing.manage"],
        "mark_failed": ["billing.invoice.update", "billing.manage"],
        "*": ["billing.manage"],
    }

    def create(self, request, *args, **kwargs):
        return api_response(
            success=False,
            message="Invoices are issued via subscriptions.",
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        invoice = self.get_object()
        if not invoice.pdf_file:
            raise Http404("Invoice PDF not found.")
        return FileResponse(invoice.pdf_file.open("rb"), filename=f"{invoice.number}.pdf")

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        invoice = self.get_object()
        serializer = InvoicePaymentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["status"] != "PAID":
            raise ValidationError("Status must be PAID for this action.")
        mark_invoice_paid(
            invoice=invoice,
            tenant_db=self.get_tenant_db_alias(),
            provider_reference=serializer.validated_data.get("provider_reference"),
            actor_id=getattr(request.user, "id", None),
            request=request,
        )
        return api_response(success=True, message="Invoice marked paid.", data=BillingInvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="mark-failed")
    def mark_failed(self, request, pk=None):
        invoice = self.get_object()
        serializer = InvoicePaymentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["status"] != "FAILED":
            raise ValidationError("Status must be FAILED for this action.")
        mark_invoice_failed(
            invoice=invoice,
            tenant_db=self.get_tenant_db_alias(),
            failure_reason=serializer.validated_data.get("failure_reason"),
            actor_id=getattr(request.user, "id", None),
            request=request,
        )
        return api_response(success=True, message="Invoice marked failed.", data=BillingInvoiceSerializer(invoice).data)


class BillingTransactionViewSet(BillingTenantViewSet):
    queryset = BillingTransaction.objects.all()
    serializer_class = BillingTransactionSerializer
    permission_map = {
        "list": ["billing.transaction.view", "billing.manage"],
        "retrieve": ["billing.transaction.view", "billing.manage"],
        "refund": ["billing.transaction.refund", "billing.manage"],
        "*": ["billing.manage"],
    }

    def get_queryset(self):
        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()
        qs = BillingTransaction.objects.using(tenant_db).filter(employer_id=employer_id, account_role="EMPLOYER")
        category = self.request.query_params.get("category")
        status_value = self.request.query_params.get("status")
        direction = self.request.query_params.get("direction")
        if category:
            qs = qs.filter(category=category.upper())
        if status_value:
            qs = qs.filter(status=status_value.upper())
        if direction:
            qs = qs.filter(direction=direction.upper())
        return qs

    @action(detail=True, methods=["post"], url_path="refund")
    def refund(self, request, pk=None):
        txn = self.get_object()
        serializer = TransactionRefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refund_txn = create_refund_transaction(
            original_txn=txn,
            tenant_db=self.get_tenant_db_alias(),
            actor_id=getattr(request.user, "id", None),
            reason=serializer.validated_data.get("reason"),
        )
        if not refund_txn:
            raise ValidationError("Transaction already reversed.")
        return api_response(
            success=True,
            message="Refund created.",
            data=BillingTransactionSerializer(refund_txn).data,
            status=status.HTTP_201_CREATED,
        )


class BillingPayoutBatchViewSet(BillingTenantViewSet):
    queryset = BillingPayoutBatch.objects.all()
    serializer_class = BillingPayoutBatchSerializer
    http_method_names = ["get", "head", "options", "post"]
    permission_map = {
        "list": ["billing.payout.view", "billing.manage"],
        "retrieve": ["billing.payout.view", "billing.manage"],
        "create": ["billing.payout.create", "billing.manage"],
        "start": ["billing.payout.update", "billing.manage"],
        "approve": ["billing.payout.update", "billing.manage"],
        "retry_failed": ["billing.payout.update", "billing.manage"],
        "reconciliation": ["billing.payout.view", "billing.manage"],
        "*": ["billing.manage"],
    }

    def create(self, request, *args, **kwargs):
        serializer = GbPayBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()
        batch = create_payout_batch(
            tenant_db=tenant_db,
            employer_id=employer_id,
            batch_type=serializer.validated_data["batch_type"],
            currency=serializer.validated_data.get("currency") or "XAF",
            planned_date=serializer.validated_data.get("planned_date"),
            items=serializer.validated_data.get("items") or [],
            actor_id=getattr(request.user, "id", None),
        )
        if serializer.validated_data.get("auto_start") and not batch.requires_approval:
            process_batch(
                batch=batch,
                tenant_db=tenant_db,
                actor_id=getattr(request.user, "id", None),
                allow_retry=False,
            )
        return api_response(
            success=True,
            message="Payout batch created.",
            data=BillingPayoutBatchSerializer(batch).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, pk=None):
        batch = self.get_object()
        if batch.requires_approval and not batch.approved_at:
            raise ValidationError("Batch requires approval before processing.")
        result = process_batch(
            batch=batch,
            tenant_db=self.get_tenant_db_alias(),
            actor_id=getattr(request.user, "id", None),
            allow_retry=False,
        )
        message = "Batch processing started."
        if result.get("status") == "manual":
            message = "Batch set to manual processing."
        return api_response(success=True, message=message, data={"status": result.get("status")})

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        batch = self.get_object()
        if not batch.requires_approval:
            return api_response(success=True, message="Batch approval not required.", data=BillingPayoutBatchSerializer(batch).data)
        if batch.approved_at:
            return api_response(success=True, message="Batch already approved.", data=BillingPayoutBatchSerializer(batch).data)
        batch.approved_at = timezone.now()
        batch.approved_by_id = getattr(request.user, "id", None)
        batch.status = BillingPayoutBatch.STATUS_DRAFT
        batch.save(using=self.get_tenant_db_alias(), update_fields=["approved_at", "approved_by_id", "status", "updated_at"])
        return api_response(success=True, message="Batch approved.", data=BillingPayoutBatchSerializer(batch).data)

    @action(detail=True, methods=["post"], url_path="retry-failed")
    def retry_failed(self, request, pk=None):
        batch = self.get_object()
        if batch.requires_approval and not batch.approved_at:
            raise ValidationError("Batch requires approval before retrying.")
        result = process_batch(
            batch=batch,
            tenant_db=self.get_tenant_db_alias(),
            actor_id=getattr(request.user, "id", None),
            allow_retry=True,
        )
        return api_response(success=True, message="Batch retry started.", data={"status": result.get("status")})

    @action(detail=True, methods=["get"], url_path="reconciliation")
    def reconciliation(self, request, pk=None):
        batch = self.get_object()
        tenant_db = self.get_tenant_db_alias()
        fmt = (request.query_params.get("format") or "csv").lower()
        payouts = batch.payouts.select_related("employee", "payout_method").all()
        employer = self._resolve_employer()
        employer_name = getattr(employer, "company_name", None) or str(employer or "")
        if fmt == "pdf":
            content = render_payout_batch_pdf(batch, payouts, employer_name=employer_name)
            filename = f"payout-batch-{batch.id}.pdf"
            return FileResponse(content, filename=filename)
        content = render_payout_batch_csv(batch, payouts)
        filename = f"payout-batch-{batch.id}.csv"
        return FileResponse(ContentFile(content), filename=filename)


class BillingPayoutViewSet(BillingTenantViewSet):
    queryset = BillingPayout.objects.all()
    serializer_class = BillingPayoutSerializer
    permission_map = {
        "list": ["billing.payout.view", "billing.manage"],
        "retrieve": ["billing.payout.view", "billing.manage"],
        "create": ["billing.payout.create", "billing.manage"],
        "update": ["billing.payout.update", "billing.manage"],
        "partial_update": ["billing.payout.update", "billing.manage"],
        "mark_status": ["billing.payout.update", "billing.manage"],
        "execute": ["billing.payout.update", "billing.manage"],
        "retry": ["billing.payout.update", "billing.manage"],
        "receipt": ["billing.payout.view", "billing.manage"],
        "*": ["billing.manage"],
    }

    def create(self, request, *args, **kwargs):
        tenant_db = self.get_tenant_db_alias()
        employer_id = self.get_employer_id()
        employee_id = request.data.get("employee_id")
        if not employee_id:
            raise ValidationError("employee_id is required.")
        employee = Employee.objects.using(tenant_db).filter(id=employee_id, employer_id=employer_id).first()
        if not employee:
            raise ValidationError("Employee not found.")

        amount = request.data.get("amount")
        category = (request.data.get("category") or "").upper()
        currency = request.data.get("currency") or "XAF"
        if category not in ["PAYROLL", "EXPENSE"]:
            raise ValidationError("Category must be PAYROLL or EXPENSE.")
        payout_method_id = request.data.get("payout_method_id")
        payout_method = None
        if payout_method_id:
            payout_method = PayoutMethod.objects.using(tenant_db).filter(id=payout_method_id, employee=employee).first()

        payout = create_payout_with_transactions(
            tenant_db=tenant_db,
            employer_id=employer_id,
            employee=employee,
            amount=amount,
            currency=currency,
            category=category,
            payout_method=payout_method,
            linked_object_type=request.data.get("linked_object_type") or "OTHER",
            linked_object_id=request.data.get("linked_object_id"),
            treasury_payment_line_id=request.data.get("treasury_payment_line_id"),
            treasury_batch_id=request.data.get("treasury_batch_id"),
            actor_id=getattr(request.user, "id", None),
        )
        return api_response(
            success=True,
            message="Payout created.",
            data=BillingPayoutSerializer(payout).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="mark-status")
    def mark_status(self, request, pk=None):
        payout = self.get_object()
        serializer = PayoutStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        update_payout_status(
            payout=payout,
            tenant_db=self.get_tenant_db_alias(),
            status=serializer.validated_data["status"],
            provider_reference=serializer.validated_data.get("provider_reference"),
            failure_reason=serializer.validated_data.get("failure_reason"),
            idempotency_key=serializer.validated_data.get("idempotency_key"),
            actor_id=getattr(request.user, "id", None),
            request=request,
        )
        return api_response(success=True, message="Payout updated.", data=BillingPayoutSerializer(payout).data)

    @action(detail=True, methods=["post"], url_path="execute")
    def execute(self, request, pk=None):
        payout = self.get_object()
        if payout.batch and payout.batch.requires_approval and not payout.batch.approved_at:
            raise ValidationError("Batch requires approval before execution.")
        result = process_payout(
            payout=payout,
            tenant_db=self.get_tenant_db_alias(),
            actor_id=getattr(request.user, "id", None),
            allow_retry=False,
        )
        message = "Payout execution started."
        if result.get("status") == "manual":
            message = "Payout set to manual processing."
        return api_response(success=True, message=message, data=result)

    @action(detail=True, methods=["post"], url_path="retry")
    def retry(self, request, pk=None):
        payout = self.get_object()
        if payout.batch and payout.batch.requires_approval and not payout.batch.approved_at:
            raise ValidationError("Batch requires approval before retrying.")
        result = process_payout(
            payout=payout,
            tenant_db=self.get_tenant_db_alias(),
            actor_id=getattr(request.user, "id", None),
            allow_retry=True,
        )
        return api_response(success=True, message="Payout retry started.", data=result)

    @action(detail=True, methods=["get"], url_path="receipt")
    def receipt(self, request, pk=None):
        payout = self.get_object()
        tenant_db = self.get_tenant_db_alias()
        if payout.status == BillingPayout.STATUS_PAID and not payout.receipt_file:
            generate_payout_receipt(payout=payout, tenant_db=tenant_db)
        if not payout.receipt_file:
            raise Http404("Payout receipt not found.")
        filename = payout.receipt_number or f"payout-{payout.id}"
        return FileResponse(payout.receipt_file.open("rb"), filename=f"{filename}.pdf")


def resolve_employee_context(request):
    tenant_db = get_employee_tenant_db_from_membership(request, require_context=False)
    if not tenant_db:
        return "default", None
    employee = Employee.objects.using(tenant_db).filter(user_id=request.user.id).first()
    return tenant_db, employee


class BillingMyTransactionsView(APIView):
    permission_classes = [IsAuthenticated, IsEmployee]

    def get(self, request):
        tenant_db, employee = resolve_employee_context(request)
        if not employee:
            raise PermissionDenied("Employee context required.")
        qs = BillingTransaction.objects.using(tenant_db).filter(
            employee=employee,
            account_role=BillingTransaction.ROLE_EMPLOYEE,
        )
        category = request.query_params.get("category")
        status_value = request.query_params.get("status")
        if category:
            qs = qs.filter(category=category.upper())
        if status_value:
            qs = qs.filter(status=status_value.upper())
        serializer = BillingTransactionSerializer(qs.order_by("-occurred_at"), many=True)
        return api_response(success=True, message="Transactions retrieved.", data=serializer.data)


class BillingMyPayoutsView(APIView):
    permission_classes = [IsAuthenticated, IsEmployee]

    def get(self, request):
        tenant_db, employee = resolve_employee_context(request)
        if not employee:
            raise PermissionDenied("Employee context required.")
        qs = BillingPayout.objects.using(tenant_db).filter(employee=employee)
        serializer = BillingPayoutSerializer(qs.order_by("-created_at"), many=True)
        return api_response(success=True, message="Payouts retrieved.", data=serializer.data)
