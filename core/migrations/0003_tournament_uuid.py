import uuid

from django.db import migrations, models


def populate_tournament_uuids(apps, schema_editor):
    Tournament = apps.get_model("core", "Tournament")
    for tournament in Tournament.objects.filter(uuid__isnull=True):
        tournament.uuid = uuid.uuid4()
        tournament.save(update_fields=["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_alter_tournament_rounds"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="uuid",
            field=models.UUIDField(null=True),
        ),
        migrations.RunPython(populate_tournament_uuids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tournament",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
