from django.db import migrations, models


def dedupe_global_contract_configurations(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    ContractConfiguration = apps.get_model("contracts", "ContractConfiguration")

    configs = (
        ContractConfiguration.objects.using(db_alias)
        .filter(contract_type__isnull=True)
        .order_by("employer_id", "-updated_at", "-created_at", "-id")
    )

    to_delete_ids = []
    current_employer = None
    for config in configs.iterator():
        if config.employer_id != current_employer:
            current_employer = config.employer_id
            continue
        to_delete_ids.append(config.id)

    if to_delete_ids:
        chunk_size = 500
        for idx in range(0, len(to_delete_ids), chunk_size):
            ContractConfiguration.objects.using(db_alias).filter(
                id__in=to_delete_ids[idx : idx + chunk_size]
            ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0010_backfill_contractelement_recurring_period"),
    ]

    operations = [
        migrations.RunPython(
            dedupe_global_contract_configurations, migrations.RunPython.noop
        ),
        migrations.AddConstraint(
            model_name="contractconfiguration",
            constraint=models.UniqueConstraint(
                fields=["employer_id"],
                condition=models.Q(contract_type__isnull=True),
                name="uniq_contract_config_global_per_employer",
            ),
        ),
    ]
