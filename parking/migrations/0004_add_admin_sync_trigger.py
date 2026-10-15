from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("parking", "0003_scope_source_references")]

    operations = [
        migrations.AlterField(
            model_name="syncrun",
            name="trigger",
            field=models.CharField(
                choices=[
                    ("manual_cli", "Manual CLI"),
                    ("manual_admin", "Manual Django Admin"),
                ],
                max_length=16,
            ),
        ),
    ]
