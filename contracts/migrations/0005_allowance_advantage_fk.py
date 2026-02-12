from django.db import migrations, models


def link_allowance_advantages(apps, schema_editor):
    Allowance = apps.get_model("contracts", "Allowance")
    Advantage = apps.get_model("payroll", "Advantage")
    db_alias = schema_editor.connection.alias

    qs = Allowance.objects.using(db_alias).select_related("contract").filter(advantage__isnull=True)
    for allowance in qs.iterator():
        contract = getattr(allowance, "contract", None)
        if not contract:
            continue
        code = f"CONTRACT-ALW-{allowance.id}"[:50]
        advantage = Advantage.objects.using(db_alias).filter(
            employer_id=contract.employer_id,
            code=code,
        ).first()
        if advantage:
            allowance.advantage_id = advantage.id
            allowance.save(using=db_alias, update_fields=["advantage"])


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0001_initial"),
        ("contracts", "0004_contracttemplate_version_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="allowance",
            name="advantage",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="contract_allowances",
                to="payroll.advantage",
                help_text="Linked payroll advantage catalog item",
            ),
        ),
        migrations.RunPython(link_allowance_advantages, migrations.RunPython.noop),
    ]

