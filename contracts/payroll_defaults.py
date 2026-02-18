from __future__ import annotations

from typing import Dict, Iterable, Optional

from django.apps import apps
from django.db import transaction

from .models import CalculationScale, ScaleRange


CAMEROON_IRPP_DEFAULT_SCALE_CODE = "CM-IRPP-DEFAULT"
CAMEROON_IRPP_DEFAULT_SCALE_NAME = "Cameroon IRPP Progressive Default"
CAMEROON_TDL_DEFAULT_SCALE_CODE = "CM-TDL-DEFAULT"
CAMEROON_TDL_DEFAULT_SCALE_NAME = "Cameroon TDL Default"
CAMEROON_RAV_DEFAULT_SCALE_CODE = "CM-RAV-DEFAULT"
CAMEROON_RAV_DEFAULT_SCALE_NAME = "Cameroon RAV/CRTV Default"

PAYROLL_DEFAULT_BASIS_ROWS = [
    ("SAL-BRUT", "Gross Salary Base"),
    ("SAL-NON-TAX", "Non-Taxable Amount Base"),
    ("SAL-BRUT-TAX", "Taxable Gross Salary Base"),
    ("SAL-BRUT-TAX-IRPP", "IRPP Taxable Base"),
    ("SAL-BRUT-COT-AF-PV", "Contribution Base AF/PV"),
    ("SAL-BRUT-COT-AT", "Contribution Base AT"),
    ("SAL-BASE", "Basic Salary Base"),
]

# Annual IRPP progressive bands (Cameroon) used by the payroll progressive algorithm.
# `indice` stores the full tax amount of the bracket when annual taxable income is above it.
CAMEROON_IRPP_DEFAULT_RANGES = [
    {"range1": 0.0, "range2": 2_000_000.0, "coefficient": 10.0, "indice": 200_000.0},
    {"range1": 2_000_000.0, "range2": 3_000_000.0, "coefficient": 15.0, "indice": 150_000.0},
    {"range1": 3_000_000.0, "range2": 5_000_000.0, "coefficient": 25.0, "indice": 500_000.0},
    {"range1": 5_000_000.0, "range2": None, "coefficient": 35.0, "indice": 0.0},
]

# Monthly TDL (Taxe de Developpement Local) fixed amounts by base-salary brackets.
CAMEROON_TDL_DEFAULT_RANGES = [
    {"base": 61_999.0, "indice": 0.0},
    {"base": 75_000.0, "indice": 250.0},
    {"base": 100_000.0, "indice": 500.0},
    {"base": 125_000.0, "indice": 750.0},
    {"base": 150_000.0, "indice": 1_000.0},
    {"base": 200_000.0, "indice": 1_250.0},
    {"base": 250_000.0, "indice": 1_500.0},
    {"base": 300_000.0, "indice": 2_000.0},
    {"base": 500_000.0, "indice": 2_250.0},
    {"base": 999_999_999.0, "indice": 2_500.0},
]

# Monthly RAV (CRTV) fixed amounts by monthly gross brackets.
CAMEROON_RAV_DEFAULT_RANGES = [
    {"base": 50_000.0, "indice": 0.0},
    {"base": 100_000.0, "indice": 750.0},
    {"base": 200_000.0, "indice": 1_950.0},
    {"base": 300_000.0, "indice": 3_250.0},
    {"base": 400_000.0, "indice": 4_550.0},
    {"base": 500_000.0, "indice": 5_850.0},
    {"base": 600_000.0, "indice": 7_150.0},
    {"base": 700_000.0, "indice": 8_450.0},
    {"base": 800_000.0, "indice": 9_750.0},
    {"base": 900_000.0, "indice": 11_050.0},
    {"base": 1_000_000.0, "indice": 12_350.0},
    {"base": 999_999_999.0, "indice": 13_000.0},
]


def _ensure_scale(
    *,
    employer_id: int,
    tenant_db: str,
    user_id: Optional[int],
    scale_code: str,
    scale_name: str,
    ranges: Iterable[dict],
) -> CalculationScale:
    with transaction.atomic(using=tenant_db):
        scale = (
            CalculationScale.objects.using(tenant_db)
            .filter(employer_id=employer_id, code__iexact=scale_code)
            .first()
        )

        if not scale:
            scale = CalculationScale.objects.using(tenant_db).create(
                employer_id=employer_id,
                code=scale_code,
                name=scale_name,
                year="__",
                is_enable=True,
                user_id=user_id,
            )
        elif not scale.is_enable:
            scale.is_enable = True
            if user_id and not scale.user_id:
                scale.user_id = user_id
            scale.save(using=tenant_db, update_fields=["is_enable", "user_id", "updated_at"])

        has_ranges = ScaleRange.objects.using(tenant_db).filter(
            employer_id=employer_id,
            calculation_scale=scale,
        ).exists()
        if not has_ranges:
            ScaleRange.objects.using(tenant_db).bulk_create(
                [
                    ScaleRange(
                        employer_id=employer_id,
                        calculation_scale=scale,
                        range1=row.get("range1"),
                        range2=row.get("range2"),
                        coefficient=row.get("coefficient"),
                        indice=row.get("indice"),
                        base=row.get("base"),
                        year="__",
                        is_enable=True,
                        user_id=user_id,
                    )
                    for row in ranges
                ]
            )

        return scale


def ensure_cameroon_irpp_default_scale(
    *,
    employer_id: int,
    tenant_db: str = "default",
    user_id: Optional[int] = None,
) -> CalculationScale:
    """
    Ensure a baseline Cameroon IRPP scale exists per employer.
    This is intentionally non-destructive: it creates missing defaults but does not overwrite user data.
    """
    return _ensure_scale(
        employer_id=employer_id,
        tenant_db=tenant_db,
        user_id=user_id,
        scale_code=CAMEROON_IRPP_DEFAULT_SCALE_CODE,
        scale_name=CAMEROON_IRPP_DEFAULT_SCALE_NAME,
        ranges=CAMEROON_IRPP_DEFAULT_RANGES,
    )


def ensure_cameroon_tdl_default_scale(
    *,
    employer_id: int,
    tenant_db: str = "default",
    user_id: Optional[int] = None,
) -> CalculationScale:
    return _ensure_scale(
        employer_id=employer_id,
        tenant_db=tenant_db,
        user_id=user_id,
        scale_code=CAMEROON_TDL_DEFAULT_SCALE_CODE,
        scale_name=CAMEROON_TDL_DEFAULT_SCALE_NAME,
        ranges=CAMEROON_TDL_DEFAULT_RANGES,
    )


def ensure_cameroon_rav_default_scale(
    *,
    employer_id: int,
    tenant_db: str = "default",
    user_id: Optional[int] = None,
) -> CalculationScale:
    return _ensure_scale(
        employer_id=employer_id,
        tenant_db=tenant_db,
        user_id=user_id,
        scale_code=CAMEROON_RAV_DEFAULT_SCALE_CODE,
        scale_name=CAMEROON_RAV_DEFAULT_SCALE_NAME,
        ranges=CAMEROON_RAV_DEFAULT_RANGES,
    )


def ensure_cameroon_default_scales(
    *,
    employer_id: int,
    tenant_db: str = "default",
    user_id: Optional[int] = None,
) -> Dict[str, CalculationScale]:
    return {
        "irpp": ensure_cameroon_irpp_default_scale(
            employer_id=employer_id,
            tenant_db=tenant_db,
            user_id=user_id,
        ),
        "tdl": ensure_cameroon_tdl_default_scale(
            employer_id=employer_id,
            tenant_db=tenant_db,
            user_id=user_id,
        ),
        "rav": ensure_cameroon_rav_default_scale(
            employer_id=employer_id,
            tenant_db=tenant_db,
            user_id=user_id,
        ),
    }


def ensure_payroll_default_bases(
    *,
    employer_id: int,
    tenant_db: str = "default",
) -> Dict[str, object]:
    """
    Ensure required payroll calculation bases exist and are active per employer.
    This is non-destructive: it only creates missing rows and re-enables disabled defaults.
    """
    calculation_basis_model = apps.get_model("payroll", "CalculationBasis")
    defaults: Dict[str, object] = {}

    with transaction.atomic(using=tenant_db):
        for code, name in PAYROLL_DEFAULT_BASIS_ROWS:
            basis = (
                calculation_basis_model.objects.using(tenant_db)
                .filter(employer_id=employer_id, code__iexact=code)
                .order_by("created_at", "id")
                .first()
            )

            if not basis:
                basis = calculation_basis_model.objects.using(tenant_db).create(
                    employer_id=employer_id,
                    code=code,
                    name=name,
                    is_active=True,
                )
            else:
                update_fields = []
                if not basis.is_active:
                    basis.is_active = True
                    update_fields.append("is_active")
                if not str(basis.name or "").strip():
                    basis.name = name
                    update_fields.append("name")
                if update_fields:
                    update_fields.append("updated_at")
                    basis.save(using=tenant_db, update_fields=update_fields)

            defaults[code] = basis

    return defaults
