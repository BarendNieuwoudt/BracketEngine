import datetime

from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_match_court_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="starts_at",
            field=models.DateTimeField(
                default=timezone.now,
                help_text="When the tournament begins. Matches are scheduled from this time.",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tournament",
            name="game_duration",
            field=models.DurationField(
                default=datetime.timedelta(minutes=90),
                help_text="Length of each round of play.",
            ),
        ),
        migrations.AddField(
            model_name="tournament",
            name="break_duration",
            field=models.DurationField(
                default=datetime.timedelta(0),
                help_text="Break time between rounds. Leave as 0 for no break.",
            ),
        ),
    ]
