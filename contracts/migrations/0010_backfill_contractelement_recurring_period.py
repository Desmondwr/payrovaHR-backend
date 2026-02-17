from django.db import migrations


def backfill_recurring_elements(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    ContractElement = apps.get_model("contracts", "ContractElement")

    elements = (
        ContractElement.objects.using(db_alias)
        .select_related("contract", "advantage", "deduction")
        .all()
    )

    updates = []
    for element in elements.iterator():
        target = element.advantage or element.deduction
        contract = element.contract
        if not target or not contract:
            continue

        target_year = str(getattr(target, "year", "") or "").strip()
        target_month = str(getattr(target, "month", "") or "").strip()
        if target_year or target_month:
            continue

        current_year = str(getattr(element, "year", "") or "").strip()
        current_month = str(getattr(element, "month", "") or "").strip()
        if current_year == "__" and current_month == "__":
            continue

        start_date = getattr(contract, "start_date", None)
        if not start_date:
            continue

        expected_year = str(start_date.year)
        expected_month = f"{start_date.month:02d}"
        if current_month == str(start_date.month):
            current_month = expected_month

        if current_year != expected_year or current_month != expected_month:
            continue

        element.year = "__"
        element.month = "__"
        updates.append(element)

    if updates:
        ContractElement.objects.using(db_alias).bulk_update(updates, ["year", "month"])


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0009_calculationscale_scalerange_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_recurring_elements, migrations.RunPython.noop),
    ]
