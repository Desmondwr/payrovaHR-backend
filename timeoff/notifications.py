from accounts.models import EmployerProfile
from employees.utils import notify_employer_users, notify_employee_user

from .models import TimeOffType


def _get_employer_profile(employer_id):
    return EmployerProfile.objects.filter(id=employer_id).first()


def _get_leave_type_name(employer_id, leave_type_code, db_alias):
    leave_type = (
        TimeOffType.objects.using(db_alias)
        .filter(employer_id=employer_id, code=leave_type_code)
        .first()
    )
    return leave_type.name if leave_type else leave_type_code


def _format_request_period(request_obj):
    if not request_obj.start_at or not request_obj.end_at:
        return ""
    start = request_obj.start_at.date().isoformat()
    end = request_obj.end_at.date().isoformat()
    return start if start == end else f"{start} to {end}"


def notify_timeoff_request_submitted(request_obj, *, actor_id=None):
    employer = _get_employer_profile(request_obj.employer_id)
    if not employer:
        return
    db_alias = request_obj._state.db or "default"
    leave_name = _get_leave_type_name(request_obj.employer_id, request_obj.leave_type_code, db_alias)
    period = _format_request_period(request_obj)
    data = {
        "timeoff_request_id": str(request_obj.id),
        "leave_type_code": request_obj.leave_type_code,
        "status": request_obj.status,
    }
    notify_employer_users(
        employer,
        "Time-off request submitted",
        body=f"{request_obj.employee.full_name} requested {leave_name} ({period}).",
        type="ACTION",
        data=data,
        exclude_user_id=actor_id,
    )
    notify_employee_user(
        request_obj.employee,
        "Time-off request submitted",
        body=f"Your {leave_name} request for {period} was submitted.",
        type="INFO",
        data=data,
        employer_profile=employer,
    )


def notify_timeoff_request_approved(request_obj, *, actor_id=None, auto=False):
    employer = _get_employer_profile(request_obj.employer_id)
    if not employer:
        return
    db_alias = request_obj._state.db or "default"
    leave_name = _get_leave_type_name(request_obj.employer_id, request_obj.leave_type_code, db_alias)
    period = _format_request_period(request_obj)
    data = {
        "timeoff_request_id": str(request_obj.id),
        "leave_type_code": request_obj.leave_type_code,
        "status": request_obj.status,
    }
    suffix = " (auto-approved)" if auto else ""
    notify_employer_users(
        employer,
        "Time-off request approved",
        body=f"{request_obj.employee.full_name}'s request {leave_name} ({period}) was approved{suffix}.",
        type="INFO",
        data=data,
        exclude_user_id=actor_id,
    )
    notify_employee_user(
        request_obj.employee,
        "Time-off request approved",
        body=f"Your {leave_name} request for {period} was approved{suffix}.",
        type="INFO",
        data=data,
        employer_profile=employer,
    )


def notify_timeoff_request_rejected(request_obj, *, actor_id=None):
    employer = _get_employer_profile(request_obj.employer_id)
    if not employer:
        return
    db_alias = request_obj._state.db or "default"
    leave_name = _get_leave_type_name(request_obj.employer_id, request_obj.leave_type_code, db_alias)
    period = _format_request_period(request_obj)
    data = {
        "timeoff_request_id": str(request_obj.id),
        "leave_type_code": request_obj.leave_type_code,
        "status": request_obj.status,
    }
    notify_employer_users(
        employer,
        "Time-off request rejected",
        body=f"{request_obj.employee.full_name}'s request {leave_name} ({period}) was rejected.",
        type="ALERT",
        data=data,
        exclude_user_id=actor_id,
    )
    notify_employee_user(
        request_obj.employee,
        "Time-off request rejected",
        body=f"Your {leave_name} request for {period} was rejected.",
        type="ALERT",
        data=data,
        employer_profile=employer,
    )


def notify_timeoff_request_cancelled(request_obj, *, actor_id=None):
    employer = _get_employer_profile(request_obj.employer_id)
    if not employer:
        return
    db_alias = request_obj._state.db or "default"
    leave_name = _get_leave_type_name(request_obj.employer_id, request_obj.leave_type_code, db_alias)
    period = _format_request_period(request_obj)
    data = {
        "timeoff_request_id": str(request_obj.id),
        "leave_type_code": request_obj.leave_type_code,
        "status": request_obj.status,
    }
    notify_employer_users(
        employer,
        "Time-off request cancelled",
        body=f"{request_obj.employee.full_name}'s request {leave_name} ({period}) was cancelled.",
        type="INFO",
        data=data,
        exclude_user_id=actor_id,
    )
    notify_employee_user(
        request_obj.employee,
        "Time-off request cancelled",
        body=f"Your {leave_name} request for {period} was cancelled.",
        type="INFO",
        data=data,
        employer_profile=employer,
    )


def notify_allocation_request_submitted(allocation_request, *, actor_id=None):
    employer = _get_employer_profile(allocation_request.employer_id)
    if not employer:
        return
    db_alias = allocation_request._state.db or "default"
    leave_name = _get_leave_type_name(allocation_request.employer_id, allocation_request.leave_type_code, db_alias)
    data = {
        "timeoff_allocation_request_id": str(allocation_request.id),
        "leave_type_code": allocation_request.leave_type_code,
        "status": allocation_request.status,
    }
    notify_employer_users(
        employer,
        "Allocation request submitted",
        body=(
            f"{allocation_request.employee.full_name} requested "
            f"{allocation_request.amount} {allocation_request.unit} of {leave_name}."
        ),
        type="ACTION",
        data=data,
        exclude_user_id=actor_id,
    )
    notify_employee_user(
        allocation_request.employee,
        "Allocation request submitted",
        body=f"Your request for {allocation_request.amount} {allocation_request.unit} of {leave_name} was submitted.",
        type="INFO",
        data=data,
        employer_profile=employer,
    )


def notify_allocation_request_approved(allocation_request, *, actor_id=None):
    employer = _get_employer_profile(allocation_request.employer_id)
    if not employer:
        return
    db_alias = allocation_request._state.db or "default"
    leave_name = _get_leave_type_name(allocation_request.employer_id, allocation_request.leave_type_code, db_alias)
    data = {
        "timeoff_allocation_request_id": str(allocation_request.id),
        "leave_type_code": allocation_request.leave_type_code,
        "status": allocation_request.status,
    }
    notify_employer_users(
        employer,
        "Allocation request approved",
        body=(
            f"{allocation_request.employee.full_name}'s allocation request "
            f"({allocation_request.amount} {allocation_request.unit} {leave_name}) was approved."
        ),
        type="INFO",
        data=data,
        exclude_user_id=actor_id,
    )
    notify_employee_user(
        allocation_request.employee,
        "Allocation request approved",
        body=(
            f"Your allocation request for {allocation_request.amount} {allocation_request.unit} "
            f"of {leave_name} was approved."
        ),
        type="INFO",
        data=data,
        employer_profile=employer,
    )


def notify_allocation_request_rejected(allocation_request, *, actor_id=None):
    employer = _get_employer_profile(allocation_request.employer_id)
    if not employer:
        return
    db_alias = allocation_request._state.db or "default"
    leave_name = _get_leave_type_name(allocation_request.employer_id, allocation_request.leave_type_code, db_alias)
    data = {
        "timeoff_allocation_request_id": str(allocation_request.id),
        "leave_type_code": allocation_request.leave_type_code,
        "status": allocation_request.status,
    }
    notify_employer_users(
        employer,
        "Allocation request rejected",
        body=(
            f"{allocation_request.employee.full_name}'s allocation request "
            f"({allocation_request.amount} {allocation_request.unit} {leave_name}) was rejected."
        ),
        type="ALERT",
        data=data,
        exclude_user_id=actor_id,
    )
    notify_employee_user(
        allocation_request.employee,
        "Allocation request rejected",
        body=(
            f"Your allocation request for {allocation_request.amount} {allocation_request.unit} "
            f"of {leave_name} was rejected."
        ),
        type="ALERT",
        data=data,
        employer_profile=employer,
    )


def notify_allocation_request_cancelled(allocation_request, *, actor_id=None):
    employer = _get_employer_profile(allocation_request.employer_id)
    if not employer:
        return
    db_alias = allocation_request._state.db or "default"
    leave_name = _get_leave_type_name(allocation_request.employer_id, allocation_request.leave_type_code, db_alias)
    data = {
        "timeoff_allocation_request_id": str(allocation_request.id),
        "leave_type_code": allocation_request.leave_type_code,
        "status": allocation_request.status,
    }
    notify_employer_users(
        employer,
        "Allocation request cancelled",
        body=(
            f"{allocation_request.employee.full_name}'s allocation request "
            f"({allocation_request.amount} {allocation_request.unit} {leave_name}) was cancelled."
        ),
        type="INFO",
        data=data,
        exclude_user_id=actor_id,
    )
    notify_employee_user(
        allocation_request.employee,
        "Allocation request cancelled",
        body=(
            f"Your allocation request for {allocation_request.amount} {allocation_request.unit} "
            f"of {leave_name} was cancelled."
        ),
        type="INFO",
        data=data,
        employer_profile=employer,
    )
