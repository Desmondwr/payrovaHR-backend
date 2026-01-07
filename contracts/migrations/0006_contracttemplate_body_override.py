from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0005_contractdocument'),
    ]

    operations = [
        migrations.AddField(
            model_name='contracttemplate',
            name='body_override',
            field=models.TextField(blank=True, null=True),
        ),
    ]
