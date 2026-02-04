from django.db import migrations, models


def backfill_contract_stage(apps, schema_editor):
    """Set is_contract_stage=True on any existing 'Contract Proposal' stages."""
    RecruitmentStage = apps.get_model("recruitment", "RecruitmentStage")
    db = schema_editor.connection.alias
    RecruitmentStage.objects.using(db).filter(name="Contract Proposal").update(
        is_contract_stage=True
    )


class Migration(migrations.Migration):

    dependencies = [
        ("recruitment", "0002_phase2"),
    ]

    operations = [
        migrations.AddField(
            model_name="recruitmentstage",
            name="is_contract_stage",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(backfill_contract_stage, migrations.RunPython.noop),
    ]
