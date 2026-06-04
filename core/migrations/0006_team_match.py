import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_team"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="match",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="teams",
                to="core.match",
            ),
        ),
        migrations.AlterField(
            model_name="team",
            name="match",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="teams",
                to="core.match",
            ),
        ),
    ]
