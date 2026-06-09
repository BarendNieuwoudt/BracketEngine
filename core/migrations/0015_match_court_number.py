import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_tournament_club"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="court_number",
            field=models.PositiveIntegerField(
                default=1,
                validators=[django.core.validators.MinValueValidator(1)],
            ),
            preserve_default=False,
        ),
    ]
