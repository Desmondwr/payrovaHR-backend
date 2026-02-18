import uuid

from django.db.models import Q
from django.utils import timezone

from employees.models import Employee

from .models import (
    Communication,
    CommunicationAuditLog,
    CommunicationRecipient,
    CommunicationTarget,
)


def _normalize_values(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _json_safe(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(val) for key, val in value.items()}
    return value


def _build_rule_q(rule_type, values, *, employer_id, tenant_db):
    values = _normalize_values(values)
    if rule_type == CommunicationTarget.RULE_ALL:
        return Q()

    if rule_type == CommunicationTarget.RULE_DEPARTMENT:
        return Q(department_id__in=values)

    if rule_type == CommunicationTarget.RULE_BRANCH:
        return Q(branch_id__in=values)

    if rule_type == CommunicationTarget.RULE_LOCATION:
        return (
            Q(city__in=values)
            | Q(state_region__in=values)
            | Q(country__in=values)
            | Q(branch__name__in=values)
            | Q(branch__code__in=values)
        )

    if rule_type == CommunicationTarget.RULE_JOB_TITLE:
        return Q(job_title__in=values)

    if rule_type == CommunicationTarget.RULE_EMPLOYMENT_STATUS:
        return Q(employment_status__in=values)

    if rule_type == CommunicationTarget.RULE_EMPLOYEE_ID:
        return Q(id__in=values) | Q(employee_id__in=values)

    if rule_type == CommunicationTarget.RULE_RBAC_ROLE:
        from accounts.models import EmployeeRole, Role

        role_ids = []
        for raw in values:
            if not raw:
                continue
            if str(raw).count("-") >= 4:
                role_ids.append(str(raw))
            else:
                role_ids.extend(
                    Role.objects.filter(employer_id=employer_id, name__iexact=str(raw)).values_list("id", flat=True)
                )

        employee_ids = []
        if role_ids:
            employee_ids = list(
                EmployeeRole.objects.filter(employer_id=employer_id, role_id__in=role_ids).values_list(
                    "employee_id", flat=True
                )
            )
        return Q(id__in=employee_ids)

    return Q()


def resolve_target_employees(*, employer_id, tenant_db, targets):
    qs = Employee.objects.using(tenant_db).filter(employer_id=employer_id)
    include_q = Q()
    exclude_q = Q()
    has_include = False

    for target in targets:
        rule_type = target.rule_type if hasattr(target, "rule_type") else target.get("rule_type")
        rule_value = target.rule_value if hasattr(target, "rule_value") else target.get("rule_value")
        include = target.include if hasattr(target, "include") else target.get("include", True)

        if rule_type == CommunicationTarget.RULE_ALL and include:
            has_include = True
            include_q |= Q()
            continue

        q = _build_rule_q(rule_type, rule_value, employer_id=employer_id, tenant_db=tenant_db)
        if include:
            has_include = True
            include_q |= q
        else:
            exclude_q |= q

    if has_include:
        qs = qs.filter(include_q)

    if exclude_q:
        qs = qs.exclude(exclude_q)

    return qs


def materialize_recipients(*, communication, employees, tenant_db):
    now = timezone.now()
    recipients = []
    for employee in employees:
        metadata = _json_safe(
            {
                "employee_id": getattr(employee, "employee_id", None),
                "department_id": getattr(employee, "department_id", None),
                "branch_id": getattr(employee, "branch_id", None),
                "employment_status": getattr(employee, "employment_status", None),
                "job_title": getattr(employee, "job_title", None),
            }
        )

        recipients.append(
            CommunicationRecipient(
                communication=communication,
                employee=employee,
                user_id=getattr(employee, "user_id", None),
                recipient_role=CommunicationRecipient.ROLE_EMPLOYEE,
                delivery_status=CommunicationRecipient.DELIVERY_SENT,
                delivered_at=now,
                last_notified_at=now,
                ack_required=communication.requires_ack,
                response_required=communication.allow_response,
                state=CommunicationRecipient.STATE_SENT,
                metadata=metadata,
            )
        )

    if recipients:
        CommunicationRecipient.objects.using(tenant_db).bulk_create(recipients, ignore_conflicts=True)

    return recipients


def create_audit_log(
    *,
    communication,
    action,
    actor_user_id=None,
    actor_employee_id=None,
    request=None,
    metadata=None,
    tenant_db="default",
):
    meta = metadata or {}
    ip_address = None
    user_agent = None
    if request:
        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT")

    return CommunicationAuditLog.objects.using(tenant_db).create(
        communication=communication,
        action=action,
        actor_user_id=actor_user_id,
        actor_employee_id=actor_employee_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=meta,
    )


def send_communication(*, communication, employer, tenant_db, actor_user_id=None, request=None):
    from employees.utils import notify_employee_user

    targets = list(communication.targets.all())
    employees = resolve_target_employees(
        employer_id=communication.employer_id,
        tenant_db=tenant_db,
        targets=targets,
    ).select_related("department", "branch")

    recipients = materialize_recipients(
        communication=communication,
        employees=employees,
        tenant_db=tenant_db,
    )

    sent_at = timezone.now()
    communication.status = Communication.STATUS_SENT
    communication.sent_at = sent_at
    communication.updated_by_id = actor_user_id
    communication.save(using=tenant_db, update_fields=["status", "sent_at", "updated_by_id", "updated_at"])

    for employee in employees:
        try:
            notify_employee_user(
                employee,
                title=communication.title,
                body=communication.body[:180] if communication.body else "",
                type="ACTION" if communication.requires_ack else "INFO",
                data={
                    "event": "communications.sent",
                    "communication_id": str(communication.id),
                    "type": communication.type,
                    "priority": communication.priority,
                    "requires_ack": communication.requires_ack,
                    "allow_response": communication.allow_response,
                    "path": f"/employee/communications/{communication.id}",
                },
                employer_profile=employer,
            )
        except Exception:
            continue

    create_audit_log(
        communication=communication,
        action="SENT",
        actor_user_id=actor_user_id,
        request=request,
        metadata={"recipient_count": employees.count()},
        tenant_db=tenant_db,
    )

    return recipients
