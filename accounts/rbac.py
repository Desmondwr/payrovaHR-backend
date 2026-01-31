"""RBAC helpers for employer delegate access and scoped permissions."""
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from accounts.models import (
    EmployerProfile,
    EmployeeMembership,
    EmployeeRole,
    Permission,
    RolePermission,
    UserPermissionOverride,
)


def _get_employer_id_from_request(request):
    header_value = None
    if hasattr(request, "headers"):
        header_value = request.headers.get("X-Employer-Id") or request.headers.get("x-employer-id")
    query_params = getattr(request, "query_params", None) or getattr(request, "GET", {})
    query_value = query_params.get("employer_id") if query_params is not None else None
    raw = header_value or query_value
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise PermissionDenied("Invalid employer context.")


def get_active_employer(request, require_context=False):
    """Resolve employer profile for employer owners or employee delegates."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    # Employer owners use their own profile
    if getattr(user, "employer_profile", None):
        return user.employer_profile

    # Admins may access any employer by header
    employer_id = _get_employer_id_from_request(request)
    if (user.is_admin or user.is_staff or user.is_superuser) and employer_id:
        employer = EmployerProfile.objects.filter(id=employer_id).first()
        if employer:
            return employer

    # Employee delegates: must have active membership
    employer_id = employer_id or getattr(user, "last_active_employer_id", None)
    if not employer_id:
        if require_context:
            raise PermissionDenied("Employer context required.")
        return None

    membership = (
        EmployeeMembership.objects.filter(
            user_id=user.id,
            employer_profile_id=employer_id,
            status=EmployeeMembership.STATUS_ACTIVE,
        )
        .select_related("employer_profile")
        .first()
    )
    if not membership:
        raise PermissionDenied("You do not have access to the requested employer.")
    return membership.employer_profile


def _get_membership_employee_id(user, employer_id):
    if not user or not user.is_authenticated:
        return None
    membership = (
        EmployeeMembership.objects.filter(
            user_id=user.id,
            employer_profile_id=employer_id,
            status=EmployeeMembership.STATUS_ACTIVE,
        )
        .only("tenant_employee_id")
        .first()
    )
    if not membership or not membership.tenant_employee_id:
        return None
    return str(membership.tenant_employee_id)


def _get_employee_role_queryset(user, employer_id):
    if not user or not user.is_authenticated:
        return EmployeeRole.objects.none()
    membership_employee_id = _get_membership_employee_id(user, employer_id)
    filters = Q(user_id=user.id)
    if membership_employee_id:
        filters |= Q(employee_id=str(membership_employee_id))
    return EmployeeRole.objects.filter(employer_id=employer_id).filter(filters)


def get_employee_roles_for_user(user, employer_id):
    """Return employee roles for user within employer, resolving by user_id or tenant employee_id."""
    return _get_employee_role_queryset(user, employer_id)


def is_delegate_user(user, employer_id):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "employer_profile", None):
        return False
    if not getattr(user, "is_employee", False):
        return False
    return _get_employee_role_queryset(user, employer_id).exists()


def get_effective_permissions(user, employer_id):
    """Return queryset of effective permissions for user within employer."""
    if not user or not user.is_authenticated:
        return Permission.objects.none()

    if user.is_superuser or user.is_admin:
        return Permission.objects.filter(is_active=True)

    if getattr(user, "employer_profile", None) and user.employer_profile.id == employer_id:
        return Permission.objects.filter(is_active=True)

    roles = (
        _get_employee_role_queryset(user, employer_id)
        .filter(role__is_active=True)
        .values_list("role_id", flat=True)
    )
    if not roles:
        return Permission.objects.none()

    base_perms = Permission.objects.filter(
        is_active=True,
        role_permissions__role_id__in=roles,
    ).distinct()

    overrides = UserPermissionOverride.objects.filter(
        employer_id=employer_id,
        user_id=user.id,
    ).select_related("permission")

    if not overrides:
        return base_perms

    base_codes = {perm.code for perm in base_perms}
    allow_codes = {o.permission.code for o in overrides if o.effect == UserPermissionOverride.EFFECT_ALLOW}
    deny_codes = {o.permission.code for o in overrides if o.effect == UserPermissionOverride.EFFECT_DENY}

    effective_codes = (base_codes | allow_codes) - deny_codes
    return Permission.objects.filter(code__in=effective_codes, is_active=True)


def get_effective_permission_codes(user, employer_id):
    return list(get_effective_permissions(user, employer_id).values_list("code", flat=True))


def user_has_permission(user, employer_id, required):
    if not required:
        return True
    if isinstance(required, str):
        required_codes = {required}
    else:
        required_codes = set(required)

    effective_codes = set(get_effective_permission_codes(user, employer_id))
    return bool(required_codes & effective_codes)


def get_delegate_scope(user, employer_id):
    """Aggregate scope from assigned roles for branch/department filtering."""
    scope = {
        "company": False,
        "branch_ids": set(),
        "department_ids": set(),
        "self_employee_ids": set(),
    }
    if not user or not user.is_authenticated:
        return scope

    roles = _get_employee_role_queryset(user, employer_id)
    if not roles.exists():
        return scope

    for role in roles:
        if role.scope_type == EmployeeRole.SCOPE_COMPANY:
            scope["company"] = True
        elif role.scope_type == EmployeeRole.SCOPE_BRANCH:
            if role.scope_id:
                scope["branch_ids"].add(str(role.scope_id))
        elif role.scope_type == EmployeeRole.SCOPE_DEPARTMENT:
            if role.scope_id:
                scope["department_ids"].add(str(role.scope_id))
        elif role.scope_type == EmployeeRole.SCOPE_SELF:
            membership = EmployeeMembership.objects.filter(
                user_id=user.id,
                employer_profile_id=employer_id,
            ).first()
            if membership and membership.tenant_employee_id:
                scope["self_employee_ids"].add(str(membership.tenant_employee_id))

    return scope


def apply_scope_filter(
    queryset,
    scope,
    *,
    branch_field=None,
    department_field=None,
    self_field=None,
):
    """Apply branch/department/self scope filters to queryset."""
    if scope.get("company"):
        return queryset

    filters = Q()

    branch_ids = scope.get("branch_ids") or set()
    department_ids = scope.get("department_ids") or set()
    self_employee_ids = scope.get("self_employee_ids") or set()

    if branch_field and branch_ids:
        filters |= Q(**{f"{branch_field}__in": list(branch_ids)})
    if department_field and department_ids:
        filters |= Q(**{f"{department_field}__in": list(department_ids)})
    if self_field and self_employee_ids:
        filters |= Q(**{f"{self_field}__in": list(self_employee_ids)})

    if not filters:
        return queryset.none()

    return queryset.filter(filters)
