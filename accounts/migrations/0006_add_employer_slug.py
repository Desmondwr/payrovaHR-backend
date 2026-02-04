# Generated manually for slug field addition

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_reintroduce_rbac"),
    ]

    operations = [
        migrations.AddField(
            model_name="employerprofile",
            name="slug",
            field=models.SlugField(
                blank=True,
                help_text="URL-friendly identifier for public pages",
                max_length=100,
                null=True,
                unique=True,
            ),
        ),
    ]
