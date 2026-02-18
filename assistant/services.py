import json
import logging
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from difflib import SequenceMatcher

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from accounts.rbac import (
    get_active_employer,
    get_effective_permission_codes,
    is_delegate_user,
)

logger = logging.getLogger(__name__)


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
SPACE_PATTERN = re.compile(r"\s+")
GREETING_TERMS = {
    "hi",
    "hello",
    "hey",
    "yo",
    "hiya",
    "greetings",
    "bonjour",
    "salut",
    "help",
    "start",
    "assist",
}
SMALL_TALK_PATTERNS = {
    "greeting": (
        "hello",
        "hi",
        "hey",
        "hiya",
        "good morning",
        "good afternoon",
        "good evening",
        "bonjour",
        "salut",
    ),
    "wellbeing": (
        "how are you",
        "how are things",
        "how is it going",
        "hows it going",
        "comment ca va",
        "ca va",
    ),
    "thanks": (
        "thank you",
        "thanks",
        "thx",
        "merci",
    ),
    "capabilities": (
        "what can you do",
        "help me",
        "who are you",
        "what are you",
        "how can you help",
        "what can i ask",
        "show modules",
    ),
    "goodbye": (
        "bye",
        "goodbye",
        "see you",
        "a bientot",
        "au revoir",
    ),
}
WORKFLOW_HINT_TERMS = {
    "contract",
    "contracts",
    "attendance",
    "time",
    "leave",
    "expense",
    "expenses",
    "payroll",
    "payslip",
    "recruitment",
    "employee",
    "employees",
    "report",
    "reports",
    "treasury",
    "fleet",
    "front",
    "desk",
    "settings",
    "portal",
    "employer",
    "admin",
    "permission",
}
OUT_OF_SCOPE_TERMS = {
    "lawsuit",
    "sue",
    "court",
    "legal advice",
    "medical advice",
    "diagnosis",
    "investment advice",
    "trading signal",
}
FRENCH_HINTS = {
    "bonjour",
    "salut",
    "merci",
    "comment",
    "puis",
    "aide",
    "contrat",
    "paie",
    "conge",
}
ATTENTION_INTENT_PATTERNS = (
    "what needs my attention now",
    "what needs my attention",
    "needs my attention now",
    "need my attention now",
    "priority tasks",
    "urgent approvals",
    "what is urgent",
    "what is pending for approval",
    "what should i handle now",
    "what should i do next",
    "what needs attention",
    "ce qui demande mon attention",
    "priorites a traiter",
    "elements urgents",
)
WORKFLOW_CONTINUE_PATTERNS = (
    "continue my",
    "continue where i left off",
    "resume my",
    "resume where i left off",
    "pick up where i left off",
    "continue from yesterday",
    "resume from yesterday",
    "continue workflow",
    "resume workflow",
    "continue le workflow",
    "reprendre le workflow",
    "reprendre mon",
    "continuer mon",
)
WORKFLOW_MEMORY_CACHE_TTL_SECONDS = 60 * 60 * 24 * 14
WORKFLOW_MEMORY_MAX_ITEMS = 8


@dataclass(frozen=True)
class AssistantTopic:
    id: str
    portals: tuple
    title: str
    sidebar_label: str
    route: str
    guidance: tuple
    keywords: tuple
    example_question: str
    required_permissions: tuple = ()


TOPICS = (
    AssistantTopic(
        id="employee_contracts",
        portals=("employee",),
        title="Employee Contracts",
        sidebar_label="Contracts",
        route="/employee/contracts",
        guidance=(
            "Open Contracts from the employee sidebar.",
            "Use View to read full contract details and status.",
            "Use Sign when the contract is pending signature and your user signature is already saved.",
            "Use Download document to export the professional contract file.",
        ),
        keywords=(
            "contract",
            "sign",
            "signature",
            "download contract",
            "agreement",
            "renewal",
            "termination",
        ),
        example_question="How do I sign and download my contract?",
    ),
    AssistantTopic(
        id="employee_attendance",
        portals=("employee",),
        title="Employee Attendance",
        sidebar_label="Attendance",
        route="/employee/attendance",
        guidance=(
            "Open Attendance from the employee sidebar.",
            "Use Check-in when your shift starts and Check-out when your shift ends.",
            "Review your attendance logs for date, work duration, and approval status.",
            "If a record is wrong, contact your manager or HR through your employer process.",
        ),
        keywords=(
            "attendance",
            "check in",
            "check out",
            "timesheet",
            "late",
            "hours worked",
            "clock",
        ),
        example_question="How do I check in and check out correctly?",
    ),
    AssistantTopic(
        id="employee_timeoff",
        portals=("employee",),
        title="Employee Time Off",
        sidebar_label="Time Off",
        route="/employee/time-off",
        guidance=(
            "Open Time Off from the employee sidebar.",
            "Create a new leave request with type, dates, and reason.",
            "Submit the request and monitor status updates in the same module.",
            "Cancel requests that are still pending if your schedule changes.",
        ),
        keywords=(
            "time off",
            "leave",
            "vacation",
            "sick leave",
            "request leave",
            "cancel leave",
        ),
        example_question="How do I submit a leave request?",
    ),
    AssistantTopic(
        id="employee_expenses",
        portals=("employee",),
        title="Employee Expenses",
        sidebar_label="My Expenses",
        route="/employee/expenses",
        guidance=(
            "Open My Expenses from the employee sidebar.",
            "Create a claim with category, amount, date, and supporting details.",
            "Submit the expense for approval when all fields are complete.",
            "Track approval and payment state from the expense list.",
        ),
        keywords=(
            "expense",
            "reimbursement",
            "claim",
            "receipt",
            "submit expense",
            "my expenses",
        ),
        example_question="How do I submit and track an expense claim?",
    ),
    AssistantTopic(
        id="employee_jobs",
        portals=("employee",),
        title="Internal Opportunities",
        sidebar_label="Opportunities",
        route="/employee/jobs",
        guidance=(
            "Open Opportunities from the employee sidebar.",
            "Filter internal openings and open the role details page.",
            "Use Apply and complete the required application fields.",
            "Track your application progress in the same module.",
        ),
        keywords=(
            "jobs",
            "opportunity",
            "internal job",
            "apply",
            "application",
            "career",
        ),
        example_question="How can I apply for an internal job?",
    ),
    AssistantTopic(
        id="employee_payslips",
        portals=("employee",),
        title="Employee Payslips",
        sidebar_label="Payslips",
        route="/employee/payslips",
        guidance=(
            "Open Payslips from the employee sidebar.",
            "Filter by month and year to find the target payroll period.",
            "Use View to inspect gross, deductions, and net salary details.",
            "Refresh after payroll validation if a new period is expected.",
        ),
        keywords=(
            "payslip",
            "salary slip",
            "payroll",
            "net salary",
            "gross salary",
            "deduction",
        ),
        example_question="Where can I view my payslip details?",
    ),
    AssistantTopic(
        id="employee_profile",
        portals=("employee",),
        title="Employee Profile Completion",
        sidebar_label="My Profile",
        route="/employee/profile",
        guidance=(
            "Open My Profile to review your personal and work details.",
            "Fill all required fields requested by your employer configuration.",
            "Upload any missing required documents if prompted.",
            "Save changes and recheck completion state.",
        ),
        keywords=(
            "profile",
            "complete profile",
            "missing fields",
            "documents",
            "employee profile",
        ),
        example_question="How do I complete my employee profile?",
    ),
    AssistantTopic(
        id="employer_employees",
        portals=("employer",),
        title="Employer Employee Management",
        sidebar_label="Employees",
        route="/employer/employees",
        guidance=(
            "Open Employees to create, update, and review employee records.",
            "Use employee configuration for required fields, numbering, and policy settings.",
            "Use invitations to connect employees to user accounts when needed.",
            "Use status actions for termination or reactivation workflows.",
        ),
        keywords=(
            "employee",
            "staff",
            "add employee",
            "invite employee",
            "terminate employee",
            "department",
            "branch",
        ),
        example_question="How do I add and manage employees?",
        required_permissions=("employees.employee.view", "employees.manage"),
    ),
    AssistantTopic(
        id="employer_recruitment",
        portals=("employer",),
        title="Employer Recruitment",
        sidebar_label="Recruitment",
        route="/employer/recruitment",
        guidance=(
            "Open Recruitment to create or manage job openings.",
            "Publish jobs when role details are complete.",
            "Move candidates through pipeline stages and make decisions.",
            "When hiring is confirmed, follow your onboarding steps for employee creation.",
        ),
        keywords=(
            "recruitment",
            "job posting",
            "candidate",
            "pipeline",
            "hiring",
            "applicant",
        ),
        example_question="How do I publish a job and move applicants in pipeline?",
        required_permissions=("employees.employee.view", "employees.manage"),
    ),
    AssistantTopic(
        id="employer_contracts",
        portals=("employer",),
        title="Employer Contracts",
        sidebar_label="Contracts",
        route="/employer/contracts",
        guidance=(
            "Open Contracts to prepare new contracts from templates.",
            "Fill contract parties, compensation, terms, and document fields.",
            "Send for approval and signature according to status workflow.",
            "Generate the contract document after validation for official use.",
        ),
        keywords=(
            "contracts",
            "template",
            "send for signature",
            "approve contract",
            "contract document",
            "signatures",
        ),
        example_question="How do I create and send a contract for signature?",
        required_permissions=("contracts.contract.view", "contracts.manage"),
    ),
    AssistantTopic(
        id="employer_payroll",
        portals=("employer",),
        title="Employer Payroll",
        sidebar_label="Payroll",
        route="/employer/payroll",
        guidance=(
            "Open Payroll to configure legal bases and payroll settings first.",
            "Run simulation or generation for the selected month and year.",
            "Review generated payslips and validate once figures are correct.",
            "Archive closed payroll periods when your process requires it.",
        ),
        keywords=(
            "payroll",
            "run payroll",
            "simulate payroll",
            "generate payslip",
            "validate payslip",
            "archive payroll",
        ),
        example_question="How do I run and validate monthly payroll?",
        required_permissions=("payroll.manage",),
    ),
    AssistantTopic(
        id="employer_attendance",
        portals=("employer",),
        title="Employer Attendance",
        sidebar_label="Attendance",
        route="/employer/attendance",
        guidance=(
            "Open Attendance to configure policies, schedules, and stations.",
            "Monitor employee records and exceptions in real time.",
            "Approve or reject records that need manager action.",
            "Use reports for lateness, missing checkout, and work-hour control.",
        ),
        keywords=(
            "attendance",
            "policy",
            "schedule",
            "approve attendance",
            "attendance report",
            "kiosk",
        ),
        example_question="How do I configure and approve attendance records?",
        required_permissions=("attendance.record.view", "attendance.manage"),
    ),
    AssistantTopic(
        id="employer_timeoff",
        portals=("employer",),
        title="Employer Time Off Management",
        sidebar_label="Time Off",
        route="/employer/time-off",
        guidance=(
            "Open Time Off to configure leave types and annual policies.",
            "Review employee requests and use approve or reject actions.",
            "Track leave balances and allocation history.",
            "Use bulk allocation tools where your policy requires annual grants.",
        ),
        keywords=(
            "time off",
            "leave type",
            "approve leave",
            "leave balance",
            "allocation",
        ),
        example_question="How do I approve leave requests and manage balances?",
        required_permissions=("timeoff.request.view", "timeoff.manage"),
    ),
    AssistantTopic(
        id="employer_expenses",
        portals=("employer",),
        title="Employer Expense and Income",
        sidebar_label="Expense & Income",
        route="/employer/expenses",
        guidance=(
            "Open Expense and Income to configure categories and budgets.",
            "Review submitted expense and income records.",
            "Approve, reject, or mark paid according to your workflow.",
            "Use budget summary views for control and variance tracking.",
        ),
        keywords=(
            "expense",
            "income",
            "budget",
            "approve expense",
            "mark paid",
            "category",
        ),
        example_question="How do I approve expenses and track budgets?",
        required_permissions=("income_expense.expense.view", "income_expense.manage"),
    ),
    AssistantTopic(
        id="employer_treasury",
        portals=("employer",),
        title="Employer Treasury",
        sidebar_label="Treasury",
        route="/employer/treasury",
        guidance=(
            "Open Treasury to manage bank accounts, cash desks, and payment batches.",
            "Submit batches for approval before execution when required.",
            "Update payment line status and reconcile statement imports.",
            "Review sessions and liquidity movements for audit consistency.",
        ),
        keywords=(
            "treasury",
            "bank",
            "cash desk",
            "batch",
            "payment line",
            "reconcile",
        ),
        example_question="How do I process treasury payment batches?",
        required_permissions=("treasury.account.view", "treasury.manage"),
    ),
    AssistantTopic(
        id="employer_fleets",
        portals=("employer",),
        title="Employer Fleet Operations",
        sidebar_label="Fleets",
        route="/employer/fleet-operations",
        guidance=(
            "Open Fleets to configure vehicles, vendors, and service types.",
            "Create assignments and contracts for fleet resources.",
            "Log services and incidents for maintenance history.",
            "Use fleet reports to monitor utilization and operational costs.",
        ),
        keywords=(
            "fleet",
            "vehicle",
            "assignment",
            "service",
            "accident",
            "vendor",
        ),
        example_question="How do I track vehicle assignments and services?",
        required_permissions=("fleets.vehicle.view", "fleets.manage"),
    ),
    AssistantTopic(
        id="employer_frontdesk",
        portals=("employer",),
        title="Employer Front Desk",
        sidebar_label="Front Desk",
        route="/employer/front-desk",
        guidance=(
            "Open Front Desk to configure stations and responsible hosts.",
            "Register visitor check-ins and check-outs from visits.",
            "Use kiosk links when self-service visitor flow is enabled.",
            "Review visit logs for security and audit records.",
        ),
        keywords=(
            "front desk",
            "visitor",
            "check in visitor",
            "kiosk",
            "station",
        ),
        example_question="How do I configure and use the front desk visitor flow?",
        required_permissions=("frontdesk.visit.view", "frontdesk.manage"),
    ),
    AssistantTopic(
        id="employer_reports",
        portals=("employer",),
        title="Employer Reports",
        sidebar_label="Reports",
        route="/employer/reports",
        guidance=(
            "Open Reports to access analytics for core HR modules.",
            "Filter by period, department, or branch where available.",
            "Use module reports to support payroll, attendance, and finance reviews.",
            "Export reports if your report screen provides export actions.",
        ),
        keywords=(
            "report",
            "analytics",
            "dashboard report",
            "export",
            "metrics",
        ),
        example_question="Where can I find and filter HR reports?",
        required_permissions=("reports.view",),
    ),
    AssistantTopic(
        id="admin_dashboard",
        portals=("admin",),
        title="Admin Dashboard",
        sidebar_label="Dashboard",
        route="/admin/dashboard",
        guidance=(
            "Open Admin Dashboard for platform-level statistics.",
            "Review employers, employees, jobs, and operations totals.",
            "Use this page to identify tenant health and activity trends.",
        ),
        keywords=(
            "admin dashboard",
            "platform stats",
            "system statistics",
            "global dashboard",
        ),
        example_question="What does the admin dashboard show?",
    ),
    AssistantTopic(
        id="admin_employers",
        portals=("admin",),
        title="Manage Employers",
        sidebar_label="Employers",
        route="/admin/employers",
        guidance=(
            "Open Employers to list all employer accounts.",
            "Review profile and activation state for each employer.",
            "Use status actions to enable or disable employer access when required.",
        ),
        keywords=(
            "employer list",
            "disable employer",
            "enable employer",
            "manage employers",
            "tenant",
        ),
        example_question="How do I enable or disable an employer account?",
    ),
    AssistantTopic(
        id="admin_users",
        portals=("admin",),
        title="Manage Users",
        sidebar_label="Users",
        route="/admin/users",
        guidance=(
            "Open Users to inspect all platform users.",
            "Use role and status fields to verify account state.",
            "Cross-check last active employer and profile completion where needed.",
        ),
        keywords=(
            "users",
            "admin users",
            "role",
            "account status",
            "platform user",
        ),
        example_question="Where do I review all users in the platform?",
    ),
    AssistantTopic(
        id="shared_security",
        portals=("admin", "employer", "employee"),
        title="Account Security and Access",
        sidebar_label="Settings",
        route="/settings/account",
        guidance=(
            "Open Settings for account security actions.",
            "Enable two-factor authentication in your profile settings.",
            "Use Change Password when rotating credentials.",
            "If access fails after role changes, log out and log in again.",
        ),
        keywords=(
            "password",
            "2fa",
            "two factor",
            "security",
            "settings",
            "login",
        ),
        example_question="How do I enable 2FA and change password?",
    ),
    AssistantTopic(
        id="shared_portals",
        portals=("employer", "employee"),
        title="Portal and Employer Switching",
        sidebar_label="Portal Switcher",
        route="/select-employer",
        guidance=(
            "Use Employer Switcher to change active employer context.",
            "Use Portal Switcher to move between employee and employer portals when available.",
            "If data appears wrong, verify active employer and refresh the current page.",
        ),
        keywords=(
            "switch employer",
            "portal",
            "wrong employer",
            "context",
            "delegate",
            "permissions",
        ),
        example_question="How do I switch employer or portal mode?",
    ),
)


def _normalize(value):
    return (value or "").strip().lower()


def _tokenize(value):
    return TOKEN_PATTERN.findall(_normalize(value))


def _compact_text(value):
    lowered = _normalize(value)
    flattened = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return SPACE_PATTERN.sub(" ", flattened).strip()


def _collect_module_labels(topics, limit=8):
    labels = []
    seen = set()
    for topic in topics:
        label = topic.sidebar_label or topic.title
        key = _normalize(label)
        if not key or key in seen:
            continue
        seen.add(key)
        labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def _detect_small_talk_intent(message):
    compact = _compact_text(message)
    if not compact:
        return "greeting"

    message_terms = set(_tokenize(compact))
    for intent, patterns in SMALL_TALK_PATTERNS.items():
        for pattern in patterns:
            normalized_pattern = _compact_text(pattern)
            if normalized_pattern and normalized_pattern in compact:
                if intent == "capabilities" and (message_terms & WORKFLOW_HINT_TERMS):
                    continue
                return intent

    if message_terms & WORKFLOW_HINT_TERMS:
        return None

    if message_terms & GREETING_TERMS and len(message_terms) <= 5:
        return "greeting"
    if {"how", "are", "you"}.issubset(message_terms):
        return "wellbeing"
    if {"comment", "ca", "va"}.issubset(message_terms):
        return "wellbeing"
    return None


def _build_capabilities_reply(context, topics, language="en"):
    modules = _collect_module_labels(topics, limit=10)
    module_text = ", ".join(modules) if modules else "your available modules"

    if language == "fr":
        return (
            f"Je suis Payrova Bot pour le portail {context['portal_mode']}.\n"
            f"Je couvre les modules suivants selon vos acces: {module_text}.\n"
            "Je peux vous aider sur la navigation, les actions autorisees par role, "
            "les etapes detaillees, les controles avant validation, et le depannage.\n"
            "Demandez une tache precise avec ce format: module + action + resultat attendu."
        )

    return (
        f"I am Payrova Bot for the {context['portal_mode']} portal.\n"
        f"I currently cover these modules for your access: {module_text}.\n"
        "I can help with navigation, role-allowed actions, step-by-step workflows, "
        "validation checks, and troubleshooting.\n"
        "Ask with this format: module + action + expected result."
    )


def _build_small_talk_reply(intent, context, topics, language="en"):
    if intent == "capabilities":
        return _build_capabilities_reply(context, topics, language=language)

    if language == "fr":
        if intent == "wellbeing":
            return (
                "Je vais bien et je suis pret a vous aider sur PayrovaHR.\n"
                "Indiquez la tache a accomplir et je vous donne les etapes exactes."
            )
        if intent == "thanks":
            return "Avec plaisir. Je peux vous guider sur la prochaine etape si vous voulez."
        if intent == "goodbye":
            return "Tres bien. Je reste disponible quand vous revenez."
        return (
            "Bonjour, je suis Payrova Bot.\n"
            "Posez votre question sur un workflow PayrovaHR et je vous guide etape par etape."
        )

    if intent == "wellbeing":
        return (
            "I am doing well and ready to help with PayrovaHR.\n"
            "Tell me the task you want to complete and I will give exact steps."
        )
    if intent == "thanks":
        return "You are welcome. I can guide your next step whenever you are ready."
    if intent == "goodbye":
        return "Understood. I will be here when you need help again."
    return (
        "Hello, I am Payrova Bot.\n"
        "Ask any PayrovaHR workflow question and I will guide you step by step."
    )


def _permissions_allow_topic(topic, permission_codes):
    if not topic.required_permissions:
        return True
    granted = set(permission_codes or [])
    return any(code in granted for code in topic.required_permissions)


def _resolve_assistant_context(request, requested_portal_mode=None):
    user = request.user
    requested = _normalize(requested_portal_mode)
    employer = None

    try:
        employer = get_active_employer(request, require_context=False)
    except PermissionDenied as exc:
        if requested == "employer":
            raise PermissionDenied(str(exc))

    has_admin_portal = bool(user.is_admin or user.is_superuser)
    has_employee_portal = bool(getattr(user, "is_employee", False))
    has_employer_owner_portal = bool(getattr(user, "employer_profile", None))
    has_delegate_employer_portal = False
    permission_codes = []

    if employer:
        permission_codes = get_effective_permission_codes(user, employer.id)
        has_delegate_employer_portal = is_delegate_user(user, employer.id)

    has_employer_portal = has_employer_owner_portal or has_delegate_employer_portal

    available_portals = []
    if has_admin_portal:
        available_portals.append("admin")
    if has_employer_portal:
        available_portals.append("employer")
    if has_employee_portal:
        available_portals.append("employee")

    if not available_portals:
        raise PermissionDenied("No assistant portal is available for this user.")

    if requested:
        if requested not in {"admin", "employer", "employee"}:
            raise PermissionDenied("Unsupported assistant portal mode.")
        if requested not in available_portals:
            raise PermissionDenied("You do not have access to this portal.")
        portal_mode = requested
    else:
        if has_employer_portal:
            portal_mode = "employer"
        elif has_employee_portal:
            portal_mode = "employee"
        else:
            portal_mode = "admin"

    return {
        "portal_mode": portal_mode,
        "available_portals": available_portals,
        "employer": employer,
        "permission_codes": permission_codes,
        "is_employer_owner": has_employer_owner_portal,
        "is_admin": has_admin_portal,
    }


def _available_topics_for_context(context):
    portal_mode = context["portal_mode"]
    can_bypass_permissions = context["is_admin"] or context["is_employer_owner"]
    permission_codes = context["permission_codes"]

    allowed = []
    for topic in TOPICS:
        if portal_mode not in topic.portals:
            continue
        if portal_mode == "employer" and not can_bypass_permissions:
            if not _permissions_allow_topic(topic, permission_codes):
                continue
        allowed.append(topic)
    return allowed


def _topic_document(topic):
    text_parts = [
        topic.title,
        topic.sidebar_label,
        topic.route,
        " ".join(topic.guidance),
        " ".join(topic.keywords),
        topic.example_question,
    ]
    return " ".join(part for part in text_parts if part)


def _keyword_phrase_score(topic, message_text, query_terms, page_path=""):
    score = 0.0
    message_lower = _normalize(message_text)
    query_set = set(query_terms)

    for keyword in topic.keywords:
        kw = _normalize(keyword)
        if not kw:
            continue
        if " " in kw and kw in message_lower:
            score += 2.5
        elif kw in query_set:
            score += 1.5

    label = _normalize(topic.sidebar_label)
    if label and label in message_lower:
        score += 1.0

    route = topic.route or ""
    if page_path and route and page_path.startswith(route):
        score += 2.0
    return score


def _bm25_score(topic, query_terms, topic_docs, idf_map, avg_doc_len):
    if not query_terms:
        return 0.0

    tokens = topic_docs[topic.id]["tokens"]
    tf = topic_docs[topic.id]["tf"]
    doc_len = max(topic_docs[topic.id]["doc_len"], 1)
    k1 = 1.2
    b = 0.75
    score = 0.0

    for term in query_terms:
        term_freq = tf.get(term, 0)
        if term_freq <= 0:
            continue
        denom = term_freq + k1 * (1 - b + b * (doc_len / max(avg_doc_len, 1)))
        score += idf_map.get(term, 0.0) * ((term_freq * (k1 + 1)) / max(denom, 1e-9))
    return score


def _rank_topics(message, history, topics, page_path=""):
    prior_user = _extract_last_user_message(history)
    query_terms = _tokenize(message) + _tokenize(prior_user)
    if not query_terms:
        return []

    topic_docs = {}
    document_frequency = Counter()
    for topic in topics:
        doc_tokens = _tokenize(_topic_document(topic))
        tf = Counter(doc_tokens)
        token_set = set(doc_tokens)
        topic_docs[topic.id] = {
            "tokens": token_set,
            "tf": tf,
            "doc_len": len(doc_tokens),
        }
        for token in token_set:
            document_frequency[token] += 1

    num_docs = max(len(topics), 1)
    avg_doc_len = sum(doc["doc_len"] for doc in topic_docs.values()) / num_docs
    idf_map = {
        term: math.log((num_docs - df + 0.5) / (df + 0.5) + 1.0)
        for term, df in document_frequency.items()
    }

    ranked = []
    for topic in topics:
        score = _bm25_score(topic, query_terms, topic_docs, idf_map, avg_doc_len)
        score += _keyword_phrase_score(topic, message, query_terms, page_path=page_path)
        if score > 0:
            ranked.append((score, topic))

    ranked.sort(key=lambda row: row[0], reverse=True)
    return ranked


def _extract_last_user_message(history):
    if not history:
        return ""
    for item in reversed(history):
        if item.get("role") == "user":
            return item.get("content", "")
    return ""


def _extract_last_assistant_message(history):
    if not history:
        return ""
    for item in reversed(history):
        if item.get("role") == "assistant":
            return item.get("content", "")
    return ""


def _is_attention_copilot_request(message):
    compact = _compact_text(message)
    if not compact:
        return False

    for pattern in ATTENTION_INTENT_PATTERNS:
        if _compact_text(pattern) in compact:
            return True

    terms = set(_tokenize(compact))
    if "attention" in terms and {"now", "urgent", "priority", "pending"} & terms:
        return True
    if {"approval", "approvals"} & terms and {"urgent", "pending", "deadline"} & terms:
        return True
    return False


def _is_workflow_continue_request(message):
    compact = _compact_text(message)
    if not compact:
        return False

    for pattern in WORKFLOW_CONTINUE_PATTERNS:
        if _compact_text(pattern) in compact:
            return True

    terms = set(_tokenize(compact))
    continue_terms = {"continue", "resume", "reprendre", "continuer", "workflow"}
    time_terms = {"yesterday", "today", "task", "setup", "hier", "tache"}
    return bool(terms & continue_terms and (terms & WORKFLOW_HINT_TERMS or terms & time_terms))


def _topic_from_page_path(page_path, topics):
    if not page_path:
        return None

    best = None
    best_len = -1
    for topic in topics:
        route = (topic.route or "").strip()
        if not route:
            continue
        if page_path.startswith(route) and len(route) > best_len:
            best = topic
            best_len = len(route)
    return best


def _workflow_memory_cache_key(user_id, context):
    employer = context.get("employer")
    employer_id = getattr(employer, "id", 0) or 0
    portal_mode = context.get("portal_mode", "employee")
    return f"assistant:workflow-memory:{user_id}:{portal_mode}:{employer_id}"


def _load_workflow_memory(user_id, context):
    if not user_id:
        return []

    payload = cache.get(_workflow_memory_cache_key(user_id, context), [])
    if not isinstance(payload, list):
        return []

    cleaned = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        topic_id = (item.get("topic_id") or "").strip()
        if not topic_id:
            continue
        cleaned.append(
            {
                "topic_id": topic_id,
                "topic_title": (item.get("topic_title") or "").strip(),
                "route": (item.get("route") or "").strip(),
                "page_path": (item.get("page_path") or "").strip(),
                "message": (item.get("message") or "").strip(),
                "captured_at": (item.get("captured_at") or "").strip(),
            }
        )
        if len(cleaned) >= WORKFLOW_MEMORY_MAX_ITEMS:
            break
    return cleaned


def _save_workflow_memory(*, user_id, context, topic, page_path="", message=""):
    if not user_id or not topic:
        return

    message_text = (message or "").strip()
    if not message_text and not page_path:
        return

    existing = _load_workflow_memory(user_id, context)
    entry = {
        "topic_id": topic.id,
        "topic_title": topic.title,
        "route": topic.route or "",
        "page_path": (page_path or "").strip(),
        "message": message_text[:220],
        "captured_at": timezone.now().strftime("%Y-%m-%d %H:%M"),
    }

    deduped = []
    for item in existing:
        if item.get("topic_id") == entry["topic_id"] and item.get("page_path") == entry["page_path"]:
            continue
        deduped.append(item)

    payload = [entry] + deduped[: WORKFLOW_MEMORY_MAX_ITEMS - 1]
    cache.set(
        _workflow_memory_cache_key(user_id, context),
        payload,
        timeout=WORKFLOW_MEMORY_CACHE_TTL_SECONDS,
    )


def _select_workflow_memory_entry(memory_items, matched_topics=None, page_path=""):
    if not memory_items:
        return None

    preferred_ids = {topic.id for topic in (matched_topics or [])}
    if preferred_ids:
        for item in memory_items:
            if item.get("topic_id") in preferred_ids:
                return item

    if page_path:
        for item in memory_items:
            route = (item.get("route") or "").strip()
            if route and page_path.startswith(route):
                return item

    return memory_items[0]


def _build_workflow_memory_reply(memory_entry, topic, language="en"):
    if not memory_entry:
        if language == "fr":
            return (
                "Je n'ai pas encore d'historique exploitable pour reprendre un workflow. "
                "Demandez une tache detaillee d'abord, puis je pourrai la reprendre ensuite."
            )
        return (
            "I do not have a usable previous workflow checkpoint yet. "
            "Start one detailed task first, then I can continue it for you."
        )

    route = memory_entry.get("route") or (topic.route if topic else "")
    topic_title = memory_entry.get("topic_title") or (topic.title if topic else "workflow")
    captured_at = memory_entry.get("captured_at") or ""
    previous_message = memory_entry.get("message") or ""

    steps = []
    if topic and topic.guidance:
        steps = list(topic.guidance[:3])

    if language == "fr":
        lines = [f"Reprise de votre workflow precedent: {topic_title}."]
        if captured_at:
            lines.append(f"Dernier point: {captured_at}.")
        if previous_message:
            lines.append(f"Votre derniere demande: \"{previous_message}\".")
        if steps:
            lines.append("Prochaines etapes recommandees:")
            for index, step in enumerate(steps, start=1):
                lines.append(f"{index}. {step}")
        if route:
            lines.append(f"Ouvrez: {route}")
        lines.append("Donnez-moi l'etape bloquante exacte et je continue a partir de la.")
        return "\n".join(lines)

    lines = [f"Continuing your previous workflow: {topic_title}."]
    if captured_at:
        lines.append(f"Last checkpoint: {captured_at}.")
    if previous_message:
        lines.append(f"Your previous request: \"{previous_message}\".")
    if steps:
        lines.append("Recommended next steps:")
        for index, step in enumerate(steps, start=1):
            lines.append(f"{index}. {step}")
    if route:
        lines.append(f"Open: {route}")
    lines.append("Tell me the exact blocked step and I will continue from there.")
    return "\n".join(lines)


def _append_attention_item(items, *, key, count, title, route, priority):
    if not count or count <= 0:
        return
    items.append(
        {
            "key": key,
            "count": int(count),
            "title": title,
            "route": route,
            "priority": int(priority),
        }
    )


def _resolve_employee_for_context(request, context):
    employer = context.get("employer")
    if not employer:
        return None

    user = request.user
    try:
        profile = getattr(user, "employee_profile", None)
    except Exception:
        profile = None

    if profile and getattr(profile, "employer_id", None) == employer.id:
        return profile

    try:
        from employees.models import Employee

        employee = Employee.objects.filter(employer_id=employer.id, user_id=user.id).first()
        if employee:
            return employee
        return Employee.objects.filter(employer_id=employer.id, user_account_id=user.id).first()
    except Exception as exc:
        logger.debug("Assistant employee resolution failed: %s", exc)
        return None


def _build_attention_snapshot(request, context):
    employer = context.get("employer")
    if not employer:
        return {
            "has_employer_context": False,
            "items": [],
            "total": 0,
        }

    today = timezone.now().date()
    horizon = today + timedelta(days=14)
    employer_id = employer.id
    portal_mode = context.get("portal_mode")
    employee = _resolve_employee_for_context(request, context) if portal_mode == "employee" else None
    items = []

    try:
        from timeoff.models import TimeOffAllocationRequest, TimeOffRequest

        if portal_mode == "employee":
            if employee:
                leave_pending = TimeOffRequest.objects.filter(
                    employer_id=employer_id,
                    employee=employee,
                    status__in=["SUBMITTED", "PENDING"],
                ).count()
                _append_attention_item(
                    items,
                    key="employee_leave_pending",
                    count=leave_pending,
                    title="leave requests pending approval",
                    route="/employee/time-off",
                    priority=4,
                )
        else:
            leave_pending = TimeOffRequest.objects.filter(
                employer_id=employer_id,
                status__in=["SUBMITTED", "PENDING"],
            ).count()
            _append_attention_item(
                items,
                key="leave_pending",
                count=leave_pending,
                title="leave requests pending approval",
                route="/employer/time-off",
                priority=5,
            )

            allocation_pending = TimeOffAllocationRequest.objects.filter(
                employer_id=employer_id,
                status="PENDING",
            ).count()
            _append_attention_item(
                items,
                key="allocation_pending",
                count=allocation_pending,
                title="allocation requests pending approval",
                route="/employer/time-off",
                priority=4,
            )
    except Exception as exc:
        logger.debug("Assistant timeoff attention snapshot failed: %s", exc)

    try:
        from contracts.models import Contract

        contract_status_scope = ["SIGNED", "ACTIVE", "APPROVED", "PENDING_SIGNATURE"]
        if portal_mode == "employee":
            if employee:
                pending_signature = Contract.objects.filter(
                    employer_id=employer_id,
                    employee=employee,
                    status="PENDING_SIGNATURE",
                ).count()
                _append_attention_item(
                    items,
                    key="employee_contract_pending_signature",
                    count=pending_signature,
                    title="contracts waiting for your signature",
                    route="/employee/contracts",
                    priority=5,
                )

                expiring_soon = Contract.objects.filter(
                    employer_id=employer_id,
                    employee=employee,
                    end_date__isnull=False,
                    end_date__gte=today,
                    end_date__lte=horizon,
                    status__in=contract_status_scope,
                ).count()
                _append_attention_item(
                    items,
                    key="employee_contract_expiring_soon",
                    count=expiring_soon,
                    title="contracts ending within 14 days",
                    route="/employee/contracts",
                    priority=3,
                )
        else:
            pending_approval = Contract.objects.filter(
                employer_id=employer_id,
                status="PENDING_APPROVAL",
            ).count()
            _append_attention_item(
                items,
                key="contract_pending_approval",
                count=pending_approval,
                title="contracts pending approval",
                route="/employer/contracts",
                priority=5,
            )

            pending_signature = Contract.objects.filter(
                employer_id=employer_id,
                status="PENDING_SIGNATURE",
            ).count()
            _append_attention_item(
                items,
                key="contract_pending_signature",
                count=pending_signature,
                title="contracts pending signature",
                route="/employer/contracts",
                priority=4,
            )

            expiring_soon = Contract.objects.filter(
                employer_id=employer_id,
                end_date__isnull=False,
                end_date__gte=today,
                end_date__lte=horizon,
                status__in=contract_status_scope,
            ).count()
            _append_attention_item(
                items,
                key="contract_expiring_soon",
                count=expiring_soon,
                title="contracts ending within 14 days",
                route="/employer/contracts",
                priority=3,
            )
    except Exception as exc:
        logger.debug("Assistant contract attention snapshot failed: %s", exc)

    try:
        from payroll.models import Salary

        if portal_mode == "employee":
            if employee:
                payslip_count = Salary.objects.filter(
                    employee=employee,
                    year=today.year,
                    month=today.month,
                ).count()
                _append_attention_item(
                    items,
                    key="employee_payslips_available_this_month",
                    count=payslip_count,
                    title="payslips available for this month",
                    route="/employee/payslips",
                    priority=2,
                )
        else:
            generated_count = Salary.objects.filter(
                employer_id=employer_id,
                year=today.year,
                month=today.month,
                status=Salary.STATUS_GENERATED,
            ).count()
            _append_attention_item(
                items,
                key="payroll_generated_pending_validation",
                count=generated_count,
                title="payslips generated and waiting validation",
                route="/employer/payroll",
                priority=5,
            )

            simulated_count = Salary.objects.filter(
                employer_id=employer_id,
                year=today.year,
                month=today.month,
                status=Salary.STATUS_SIMULATED,
            ).count()
            _append_attention_item(
                items,
                key="payroll_simulated_not_generated",
                count=simulated_count,
                title="simulated payslips not generated yet",
                route="/employer/payroll",
                priority=3,
            )
    except Exception as exc:
        logger.debug("Assistant payroll attention snapshot failed: %s", exc)

    if portal_mode != "employee":
        try:
            from employees.models import TerminationApproval

            termination_pending = TerminationApproval.objects.filter(
                employee__employer_id=employer_id,
                status="PENDING",
            ).count()
            _append_attention_item(
                items,
                key="termination_pending_approval",
                count=termination_pending,
                title="termination requests pending approval",
                route="/employer/employees",
                priority=4,
            )
        except Exception as exc:
            logger.debug("Assistant termination attention snapshot failed: %s", exc)

    items.sort(key=lambda row: (row["priority"], row["count"]), reverse=True)
    return {
        "has_employer_context": True,
        "items": items,
        "total": sum(item["count"] for item in items),
    }


def _find_attention_item(snapshot, keys):
    lookup = set(keys or [])
    for item in snapshot.get("items", []):
        if item.get("key") in lookup:
            return item
    return None


def _build_attention_copilot_reply(snapshot, context, language="en"):
    if not snapshot.get("has_employer_context"):
        if language == "fr":
            return (
                "Je ne peux pas calculer les priorites sans contexte employeur actif. "
                "Selectionnez d'abord un employeur, puis relancez la commande."
            )
        return (
            "I cannot compute priorities without an active employer context. "
            "Select an employer first, then run this command again."
        )

    items = snapshot.get("items", [])
    if not items:
        if language == "fr":
            return "Aucune alerte urgente detectee pour le moment. Vous etes a jour."
        return "No urgent approvals or deadline alerts found right now. You are up to date."

    top_items = items[:4]
    first_route = top_items[0].get("route")

    if language == "fr":
        lines = ["Resume de priorite pour maintenant:"]
        for index, item in enumerate(top_items, start=1):
            lines.append(f"{index}. {item['count']} {item['title']} ({item['route']})")
        if first_route:
            lines.append(f"Prochaine action recommandee: ouvrir {first_route}.")
        return "\n".join(lines)

    lines = ["Priority summary for right now:"]
    for index, item in enumerate(top_items, start=1):
        lines.append(f"{index}. {item['count']} {item['title']} ({item['route']})")
    if first_route:
        lines.append(f"Recommended next action: open {first_route}.")
    return "\n".join(lines)


def _select_nudge_step_for_page(topic, page_path=""):
    guidance = list(topic.guidance or ())
    if not guidance:
        return None

    route = (topic.route or "").strip()
    on_topic_page = bool(route and page_path and page_path.startswith(route))
    if not on_topic_page:
        return guidance[0]

    # If user is already on this module page, skip navigation-only prompts like "Open ...".
    for step in guidance:
        normalized_step = _normalize(step)
        if normalized_step.startswith("open "):
            continue
        if normalized_step.startswith("ouvrez "):
            continue
        if normalized_step.startswith("go to "):
            continue
        if normalized_step.startswith("accedez "):
            continue
        return step

    return guidance[1] if len(guidance) > 1 else guidance[0]


def _build_proactive_nudge_reply(*, context, topics, page_path, language, snapshot):
    page_topic = _topic_from_page_path(page_path, topics)
    module_item = None

    if "/time-off" in page_path:
        module_item = _find_attention_item(snapshot, {"leave_pending", "allocation_pending", "employee_leave_pending"})
    elif "/contracts" in page_path:
        module_item = _find_attention_item(
            snapshot,
            {
                "contract_pending_approval",
                "contract_pending_signature",
                "contract_expiring_soon",
                "employee_contract_pending_signature",
                "employee_contract_expiring_soon",
            },
        )
    elif "/payroll" in page_path or "/payslip" in page_path:
        module_item = _find_attention_item(
            snapshot,
            {
                "payroll_generated_pending_validation",
                "payroll_simulated_not_generated",
                "employee_payslips_available_this_month",
            },
        )
    elif "/employees" in page_path:
        module_item = _find_attention_item(snapshot, {"termination_pending_approval"})

    if not module_item:
        module_item = (snapshot.get("items") or [None])[0]

    if module_item:
        if language == "fr":
            return (
                f"Nudge: {module_item['count']} {module_item['title']}. "
                f"Prochaine action: ouvrez {module_item['route']}."
            )
        return (
            f"Nudge: {module_item['count']} {module_item['title']}. "
            f"Next best action: open {module_item['route']}."
        )

    if page_topic and page_topic.guidance:
        first_step = _select_nudge_step_for_page(page_topic, page_path=page_path) or page_topic.guidance[0]
        if language == "fr":
            return f"Nudge: Dans {page_topic.sidebar_label}, commencez par: {first_step}"
        return f"Nudge: In {page_topic.sidebar_label}, start with: {first_step}"

    if language == "fr":
        return "Nudge: ouvrez votre module principal et je peux vous proposer la prochaine action utile."
    return "Nudge: open your main module and I can suggest the next best action."


def _build_suggestions(matched_topics, all_topics, language="en", portal_mode="employee", page_path=""):
    labels = []
    seen_labels = set()

    source = list(matched_topics)
    if page_path:
        source += [topic for topic in all_topics if topic.route and page_path.startswith(topic.route)]
    source += list(all_topics)

    for topic in source:
        label = (topic.sidebar_label or topic.title or "").strip()
        if not label:
            continue
        key = label.lower()
        if key in seen_labels:
            continue
        seen_labels.add(key)
        labels.append(label)
        if len(labels) >= 2:
            break

    suggestions = []

    if labels:
        main = labels[0]
        secondary = labels[1] if len(labels) > 1 else labels[0]
        if language == "fr":
            suggestions.extend(
                [
                    f"Comment finaliser rapidement une tache dans {main} ?",
                    f"Montre-moi les actions prioritaires dans {main}.",
                    f"Reprends mon workflow precedent dans {main}.",
                    f"Ou trouver {secondary} dans mon menu ?",
                ]
            )
        else:
            suggestions.extend(
                [
                    f"How do I complete key tasks in {main}?",
                    f"What needs attention in {main} right now?",
                    f"Continue my previous {main} workflow.",
                    f"Where can I find {secondary} in my menu?",
                ]
            )

    if language == "fr":
        portal_defaults = {
            "admin": [
                "Qu'est-ce qui demande mon attention maintenant ?",
                "Comment controler rapidement les comptes employeurs ?",
            ],
            "employer": [
                "Qu'est-ce qui demande mon attention maintenant ?",
                "Comment approuver vite les demandes de conge ?",
            ],
            "employee": [
                "Ou verifier mon bulletin de paie ce mois-ci ?",
                "Comment signer rapidement mon contrat ?",
            ],
        }
        suggestions.extend(portal_defaults.get(portal_mode, portal_defaults["employee"]))
        suggestions.append("Reprendre mon workflow d'hier.")
    else:
        portal_defaults = {
            "admin": [
                "What needs my attention now?",
                "How do I quickly review employer accounts?",
            ],
            "employer": [
                "What needs my attention now?",
                "How do I quickly approve leave requests?",
            ],
            "employee": [
                "Where can I view my payslip for this month?",
                "How do I sign and download my contract?",
            ],
        }
        suggestions.extend(portal_defaults.get(portal_mode, portal_defaults["employee"]))
        suggestions.append("Continue my workflow from yesterday.")

    result = []
    seen = set()
    for text in suggestions:
        cleaned = (text or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if len(result) >= 4:
            break
    return result


def _build_references(matched_topics):
    references = []
    seen = set()
    for topic in matched_topics:
        key = topic.id
        if key in seen:
            continue
        seen.add(key)
        references.append(
            {
                "title": topic.title,
                "route": topic.route,
                "menu_label": topic.sidebar_label,
            }
        )
        if len(references) >= 4:
            break
    return references


def _detect_language(message, locale="", history=None):
    if _normalize(locale).startswith("fr"):
        return "fr"

    probe = f"{message} {_extract_last_user_message(history or [])}".lower()
    if any(word in probe for word in FRENCH_HINTS):
        return "fr"
    return "en"


def _build_intro_reply(context, topics, language="en"):
    base = _build_capabilities_reply(context, topics, language=language)
    examples = []
    seen = set()
    for topic in topics:
        question = (topic.example_question or "").strip()
        key = _normalize(question)
        if not key or key in seen:
            continue
        seen.add(key)
        examples.append(question)
        if len(examples) >= 3:
            break

    if not examples:
        return base

    if language == "fr":
        return f"{base}\nExemples utiles: " + " | ".join(examples)
    return f"{base}\nUseful examples: " + " | ".join(examples)


def _find_related_topics(message, topics, page_path="", limit=4):
    query = _compact_text(message)
    query_terms = set(_tokenize(query))

    ranked = []
    for topic in topics:
        doc = _compact_text(_topic_document(topic))
        doc_terms = set(_tokenize(doc))
        overlap = len(query_terms & doc_terms)
        ratio = SequenceMatcher(None, query, doc).ratio() if query else 0.0
        score = (overlap * 1.25) + ratio
        if page_path and topic.route and page_path.startswith(topic.route):
            score += 2.2
        if score > 0.20:
            ranked.append((score, topic))

    ranked.sort(key=lambda row: row[0], reverse=True)
    return [topic for _, topic in ranked[:limit]]


def _build_knowledge_scope(topics, limit=18):
    scope = []
    seen = set()
    for topic in topics:
        key = topic.id
        if key in seen:
            continue
        seen.add(key)
        scope.append(
            {
                "title": topic.title,
                "menu_label": topic.sidebar_label,
                "route": topic.route,
                "example_question": topic.example_question,
            }
        )
        if len(scope) >= limit:
            break
    return scope


def _build_rule_based_reply(*, message, matched_topics, all_topics, context, language="en", page_path=""):
    requires_employer_context = context.get("portal_mode") in {"employee", "employer"}

    if not matched_topics:
        related = _find_related_topics(message, all_topics, page_path=page_path, limit=4)
        if language == "fr":
            lines = [
                "Je n'ai pas encore associe votre demande a un seul workflow.",
                "Je peux quand meme vous guider avec precision si vous donnez: module + action + resultat attendu.",
                "Exemples: Contrats + signer + statut en attente; Paie + generer + mois/annee.",
            ]
            if related:
                lines.append("Modules proches dans votre portail:")
                for index, topic in enumerate(related, start=1):
                    lines.append(f"{index}. {topic.sidebar_label} ({topic.route})")
            lines.extend(
                [
                    "Verification rapide:",
                    "2. Verifiez les permissions de votre role pour ce menu.",
                    "3. Copiez le message d'erreur exact pour un diagnostic cible.",
                ]
            )
            if requires_employer_context:
                lines.insert(len(lines) - 2, "1. Verifiez le bon portail et le bon employeur actif.")
            else:
                lines.insert(len(lines) - 2, "1. Verifiez le bon portail et le bon role actif.")
            return "\n".join(lines)

        lines = [
            "I could not map your request to a single workflow yet.",
            "I can still guide you precisely if you provide: module + action + expected result.",
            "Examples: Contracts + sign + pending status; Payroll + generate + month/year.",
        ]
        if related:
            lines.append("Closest modules in your portal:")
            for index, topic in enumerate(related, start=1):
                lines.append(f"{index}. {topic.sidebar_label} ({topic.route})")
        lines.extend(
            [
                "Rapid checks:",
                "2. Confirm your role permissions for this menu.",
                "3. Share the exact error message for targeted troubleshooting.",
            ]
        )
        if requires_employer_context:
            lines.insert(len(lines) - 2, "1. Confirm the correct portal and active employer context.")
        else:
            lines.insert(len(lines) - 2, "1. Confirm the correct portal and active role context.")
        return "\n".join(lines)

    sections = []
    for topic in matched_topics[:2]:
        if language == "fr":
            lines = [
                topic.title,
                f"Module: {topic.sidebar_label}",
                f"Route: {topic.route}",
                "Plan d'execution:",
            ]
        else:
            lines = [
                topic.title,
                f"Module: {topic.sidebar_label}",
                f"Route: {topic.route}",
                "Execution plan:",
            ]
        for index, step in enumerate(topic.guidance, start=1):
            lines.append(f"{index}. {step}")

        if language == "fr":
            lines.extend(
                [
                    "Controles avant validation:",
                    "1. Verifiez vos permissions et l'etat de la demande.",
                    "2. Verifiez les champs obligatoires avant soumission.",
                ]
            )
            if requires_employer_context:
                lines.append("3. Verifiez le bon contexte employeur avant toute action sensible.")
            else:
                lines.append("3. Verifiez les restrictions de role avant toute action sensible.")
        else:
            lines.extend(
                [
                    "Pre-validation checks:",
                    "1. Confirm your permissions and workflow status.",
                    "2. Confirm required fields are fully completed before submitting.",
                ]
            )
            if requires_employer_context:
                lines.append("3. Confirm the correct employer context before sensitive actions.")
            else:
                lines.append("3. Confirm role scope before sensitive actions.")
        sections.append("\n".join(lines))

    if language == "fr":
        closing = (
            "Si cela echoue encore, envoyez l'erreur exacte et le bouton clique. "
            "Je vous donnerai un plan de correction cible."
        )
    else:
        closing = (
            "If this still fails, send the exact error text and the button you clicked. "
            "I will provide a targeted fix path."
        )

    return "\n\n".join(sections + [closing])


def _safe_json_dumps(value):
    try:
        return json.dumps(value, ensure_ascii=True)
    except Exception:
        return "{}"


def _llm_settings():
    enable_llm = bool(getattr(settings, "ASSISTANT_ENABLE_LLM", False))
    api_key = getattr(settings, "ASSISTANT_OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    model = getattr(settings, "ASSISTANT_OPENAI_MODEL", "gpt-4.1-mini")
    temperature = float(getattr(settings, "ASSISTANT_OPENAI_TEMPERATURE", 0.2))
    max_tokens = int(getattr(settings, "ASSISTANT_OPENAI_MAX_TOKENS", 700))
    return {
        "enabled": enable_llm and bool(api_key),
        "api_key": api_key,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


def _extract_openai_text(response):
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = getattr(response, "output", None) or []
    chunks = []
    for item in output:
        content_items = getattr(item, "content", None) or []
        for content in content_items:
            text = getattr(content, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    return "\n".join(chunks).strip()


def _build_llm_prompts(*, context, language, page_path, message, history, matched_topics, all_topics, out_of_scope):
    references = []
    for topic in matched_topics[:4]:
        references.append(
            {
                "title": topic.title,
                "menu_label": topic.sidebar_label,
                "route": topic.route,
                "guidance": list(topic.guidance),
                "keywords": list(topic.keywords),
            }
        )

    if language == "fr":
        language_instruction = "Reponds en francais simple et professionnel."
    else:
        language_instruction = "Respond in clear professional English."

    system_prompt = (
        "You are Payrova Assistant, an advanced in-app product assistant for the PayrovaHR platform.\n"
        f"{language_instruction}\n"
        "Primary objective: explain exactly how to use the system based on the provided context and references.\n"
        "Hard rules:\n"
        "- Respect role and portal scope. Never suggest unauthorized actions.\n"
        "- If unsure, say so and ask one clarifying question.\n"
        "- Do not provide legal, medical, or investment advice.\n"
        "- Keep answers actionable: route/menu, then step-by-step actions.\n"
        "- If issue seems access-related, include employer context and permission checks.\n"
        "- Avoid hallucinating modules that are not in the knowledge scope.\n"
        "Output style:\n"
        "- Start with a direct answer sentence.\n"
        "- Then provide numbered steps.\n"
        "- End with one short 'If this still fails' troubleshooting line when relevant."
    )

    runtime_context = {
        "portal_mode": context["portal_mode"],
        "available_portals": context["available_portals"],
        "page_path": page_path,
        "employer": {
            "id": context["employer"].id,
            "name": context["employer"].company_name,
        }
        if context["employer"]
        else None,
        "permission_codes": context["permission_codes"],
        "out_of_scope_triggered": bool(out_of_scope),
        "references": references,
        "knowledge_scope": _build_knowledge_scope(all_topics),
        "assistant_capabilities": [
            "module_navigation",
            "role_based_guidance",
            "step_by_step_workflows",
            "validation_checks",
            "troubleshooting_paths",
        ],
    }

    chat_history = []
    for item in (history or [])[-8:]:
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        text = (item.get("content") or "").strip()
        if not text:
            continue
        chat_history.append({"role": role, "content": text[:1600]})

    user_prompt = (
        "Runtime context:\n"
        f"{_safe_json_dumps(runtime_context)}\n\n"
        f"Current user question:\n{message}\n\n"
        f"Recent conversation:\n{_safe_json_dumps(chat_history)}"
    )
    return system_prompt, user_prompt


def _generate_with_openai(*, context, language, page_path, message, history, matched_topics, all_topics, out_of_scope):
    llm_cfg = _llm_settings()
    if not llm_cfg["enabled"]:
        return None, "disabled_or_missing_key"

    try:
        from openai import OpenAI
    except Exception:
        return None, "openai_package_missing"

    system_prompt, user_prompt = _build_llm_prompts(
        context=context,
        language=language,
        page_path=page_path,
        message=message,
        history=history,
        matched_topics=matched_topics,
        all_topics=all_topics,
        out_of_scope=out_of_scope,
    )

    messages = [{"role": "system", "content": system_prompt}]
    for item in (history or [])[-8:]:
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        text = (item.get("content") or "").strip()
        if not text:
            continue
        messages.append({"role": role, "content": text[:1600]})
    messages.append({"role": "user", "content": user_prompt})

    try:
        client = OpenAI(api_key=llm_cfg["api_key"])
        response = client.responses.create(
            model=llm_cfg["model"],
            input=messages,
            temperature=llm_cfg["temperature"],
            max_output_tokens=llm_cfg["max_tokens"],
        )
        text = _extract_openai_text(response)
        if not text:
            return None, "empty_response"
        return text, "ok"
    except Exception as exc:
        logger.warning("Assistant LLM generation failed: %s", exc)
        return None, "llm_error"


def _confidence_from_rank(ranked):
    if not ranked:
        return 0.25
    top = ranked[0][0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    gap = max(top - second, 0.0)
    base = min(0.92, 0.35 + (top / (top + 6.0)))
    boost = min(0.08, gap / 10.0)
    return round(min(0.98, base + boost), 2)


def generate_assistant_reply(request, validated_payload):
    message = (validated_payload.get("message") or "").strip()
    history = validated_payload.get("history") or []
    page_path = (validated_payload.get("page_path") or "").strip()
    locale = (validated_payload.get("locale") or "").strip()
    interaction_type = _normalize(validated_payload.get("interaction_type") or "chat")
    if interaction_type not in {"chat", "nudge"}:
        interaction_type = "chat"

    context = _resolve_assistant_context(
        request,
        requested_portal_mode=validated_payload.get("portal_mode"),
    )
    topics = _available_topics_for_context(context)
    if not topics:
        raise PermissionDenied("No assistant topics are available for your access level.")

    language = _detect_language(message, locale=locale, history=history)
    lowered_message = _normalize(message)
    out_of_scope = any(term in lowered_message for term in OUT_OF_SCOPE_TERMS)
    attention_intent = _is_attention_copilot_request(message)
    continue_intent = _is_workflow_continue_request(message)
    small_talk_intent = _detect_small_talk_intent(message)

    ranked = _rank_topics(message, history, topics, page_path=page_path)
    matched_topics = [row[1] for row in ranked[:4]]
    page_topic = _topic_from_page_path(page_path, topics)
    references = _build_references(matched_topics)
    if not references:
        references = _build_references(_find_related_topics(message, topics, page_path=page_path, limit=3))
    confidence = _confidence_from_rank(ranked)

    mode = "knowledge"
    llm_status = "not_used"
    attention_snapshot = None
    memory_items = []

    if interaction_type == "nudge":
        attention_snapshot = _build_attention_snapshot(request, context)
        nudge_topics = []
        if page_topic:
            nudge_topics.append(page_topic)
        if matched_topics:
            if nudge_topics:
                nudge_topics.extend([topic for topic in matched_topics if topic.id != nudge_topics[0].id])
            else:
                nudge_topics.extend(matched_topics)
        if nudge_topics:
            references = _build_references(nudge_topics[:3])

        reply = _build_proactive_nudge_reply(
            context=context,
            topics=topics,
            page_path=page_path,
            language=language,
            snapshot=attention_snapshot,
        )
        mode = "nudge"
        confidence = max(confidence, 0.88)
    elif out_of_scope:
        if language == "fr":
            reply = (
                "Je peux vous aider a utiliser PayrovaHR, mais je ne peux pas fournir de conseils "
                "juridiques, medicaux ou d'investissement. Merci de consulter un professionnel qualifie."
            )
        else:
            reply = (
                "I can help you use PayrovaHR features, but I cannot provide legal, medical, "
                "or investment advice. Please consult a qualified professional."
            )
    elif attention_intent:
        attention_snapshot = _build_attention_snapshot(request, context)
        reply = _build_attention_copilot_reply(attention_snapshot, context, language=language)
        mode = "copilot"
        confidence = max(confidence, 0.9)

        copilot_topics = []
        for item in (attention_snapshot.get("items") or [])[:4]:
            route = (item.get("route") or "").strip()
            if not route:
                continue
            topic = _topic_from_page_path(route, topics)
            if not topic:
                continue
            if topic.id in {row.id for row in copilot_topics}:
                continue
            copilot_topics.append(topic)
        if copilot_topics:
            references = _build_references(copilot_topics)
    elif continue_intent:
        memory_items = _load_workflow_memory(request.user.id, context)
        memory_entry = _select_workflow_memory_entry(
            memory_items,
            matched_topics=matched_topics,
            page_path=page_path,
        )
        topic_lookup = {topic.id: topic for topic in topics}
        memory_topic = None
        if memory_entry:
            memory_topic = topic_lookup.get(memory_entry.get("topic_id"))
        if not memory_topic and page_topic:
            memory_topic = page_topic
        reply = _build_workflow_memory_reply(memory_entry, memory_topic, language=language)
        mode = "memory"
        confidence = max(confidence, 0.88 if memory_entry else 0.5)
        if memory_topic:
            references = _build_references([memory_topic])
    elif small_talk_intent:
        if small_talk_intent == "capabilities":
            reply = _build_intro_reply(context, topics, language=language)
        else:
            reply = _build_small_talk_reply(small_talk_intent, context, topics, language=language)
        mode = "conversation"
        confidence = max(confidence, 0.9)
    else:
        llm_reply, llm_status = _generate_with_openai(
            context=context,
            language=language,
            page_path=page_path,
            message=message,
            history=history,
            matched_topics=matched_topics,
            all_topics=topics,
            out_of_scope=out_of_scope,
        )
        if llm_reply:
            reply = llm_reply
            mode = "llm"
        else:
            mode = "knowledge"
            reply = _build_rule_based_reply(
                message=message,
                matched_topics=matched_topics[:2],
                all_topics=topics,
                context=context,
                language=language,
                page_path=page_path,
            )

    if interaction_type == "chat" and mode not in {"conversation", "memory"} and not out_of_scope:
        topic_for_memory = matched_topics[0] if matched_topics else page_topic
        if topic_for_memory:
            _save_workflow_memory(
                user_id=request.user.id,
                context=context,
                topic=topic_for_memory,
                page_path=page_path,
                message=message,
            )
            if not memory_items:
                memory_items = _load_workflow_memory(request.user.id, context)

    employer = context["employer"]
    employer_payload = None
    if employer:
        employer_payload = {"id": employer.id, "name": employer.company_name}

    suggestion_topics = matched_topics
    if interaction_type == "nudge" and page_topic:
        suggestion_topics = [page_topic] + [topic for topic in matched_topics if topic.id != page_topic.id]

    suggestions = _build_suggestions(
        suggestion_topics,
        topics,
        language=language,
        portal_mode=context["portal_mode"],
        page_path=page_path,
    )
    last_assistant = _extract_last_assistant_message(history)

    return {
        "reply": reply,
        "portal_mode": context["portal_mode"],
        "available_portals": context["available_portals"],
        "suggestions": suggestions,
        "references": references,
        "language": language,
        "mode": mode,
        "confidence": confidence,
        "employer": employer_payload,
        "context": {
            "current_page": page_path or None,
            "history_used": len(history),
            "had_previous_assistant_reply": bool(last_assistant),
            "llm_status": llm_status,
            "small_talk_intent": small_talk_intent,
            "knowledge_topics": len(topics),
            "interaction_type": interaction_type,
            "attention_items": (attention_snapshot or {}).get("total", 0),
            "workflow_memory_items": len(memory_items),
        },
    }
