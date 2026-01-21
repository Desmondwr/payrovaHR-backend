from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0007_merge_20260119_2038'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='Notification',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('title', models.CharField(max_length=255)),
                        ('body', models.TextField(blank=True)),
                        ('type', models.CharField(choices=[('INFO', 'Info'), ('ACTION', 'Action'), ('ALERT', 'Alert')], default='INFO', max_length=20)),
                        ('status', models.CharField(choices=[('UNREAD', 'Unread'), ('READ', 'Read')], db_index=True, default='UNREAD', max_length=20)),
                        ('data', models.JSONField(blank=True, help_text='Additional payload for the frontend', null=True)),
                        ('read_at', models.DateTimeField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('employer_profile', models.ForeignKey(blank=True, help_text='Optional employer context for multi-employer users', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='accounts.employerprofile')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'notifications',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.AddIndex(
                    model_name='notification',
                    index=models.Index(fields=['user', 'status'], name='notification_user_id_13e1f9_idx'),
                ),
                migrations.AddIndex(
                    model_name='notification',
                    index=models.Index(fields=['employer_profile', 'status'], name='notification_employe_77a42c_idx'),
                ),
                migrations.AddIndex(
                    model_name='notification',
                    index=models.Index(fields=['created_at'], name='notification_created_5d4a0e_idx'),
                ),
            ],
        )
    ]
