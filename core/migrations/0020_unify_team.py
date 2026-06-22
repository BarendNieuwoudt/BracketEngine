import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models

SAVED_TOURNAMENT_TEAM_LINKS = []
CLUBTEAM_TO_TEAM = {}


def link_teams_to_matches(apps, schema_editor):
    Team = apps.get_model("core", "Team")
    Match = apps.get_model("core", "Match")
    for team in Team.objects.exclude(match_id__isnull=True).iterator():
        match_id = team.match_id
        if match_id is None:
            continue
        match = Match.objects.select_related("tournament").get(pk=match_id)
        if team.club_id is None:
            club_id = match.club_id or match.tournament.club_id
            if club_id:
                team.club_id = club_id
                team.save(update_fields=["club_id"])
        match.teams.add(team)


def prepare_club_teams(apps, schema_editor):
    global SAVED_TOURNAMENT_TEAM_LINKS, CLUBTEAM_TO_TEAM
    TournamentTeams = apps.get_model("core", "Tournament_teams")
    SAVED_TOURNAMENT_TEAM_LINKS = list(
        TournamentTeams.objects.values_list("tournament_id", "clubteam_id")
    )

    ClubTeam = apps.get_model("core", "ClubTeam")
    Team = apps.get_model("core", "Team")
    for club_team in ClubTeam.objects.all().iterator():
        team = Team.objects.create(
            uuid=club_team.uuid,
            club_id=club_team.club_id,
            name=club_team.name,
        )
        member_ids = list(
            club_team.members.values_list("pk", flat=True)
        )
        team.members.set(member_ids)
        CLUBTEAM_TO_TEAM[club_team.pk] = team.pk


def restore_tournament_team_links(apps, schema_editor):
    TournamentTeams = apps.get_model("core", "Tournament_teams")
    for tournament_id, clubteam_id in SAVED_TOURNAMENT_TEAM_LINKS:
        team_id = CLUBTEAM_TO_TEAM.get(clubteam_id)
        if team_id is None:
            continue
        TournamentTeams.objects.create(
            tournament_id=tournament_id,
            team_id=team_id,
        )


def ensure_team_clubs(apps, schema_editor):
    Team = apps.get_model("core", "Team")
    Match = apps.get_model("core", "Match")
    MatchTeams = apps.get_model("core", "Match_teams")
    for team in Team.objects.filter(club__isnull=True).order_by("pk"):
        link = MatchTeams.objects.filter(team_id=team.pk).first()
        if link is None:
            team.delete()
            continue
        match = Match.objects.select_related("tournament").get(pk=link.match_id)
        club_id = match.club_id or match.tournament.club_id
        if club_id:
            team.club_id = club_id
            team.save(update_fields=["club_id"])
        else:
            team.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_club_team"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="teams",
            field=models.ManyToManyField(
                blank=True,
                related_name="matches",
                to="core.team",
            ),
        ),
        migrations.RunPython(link_teams_to_matches, migrations.RunPython.noop),
        migrations.RunPython(prepare_club_teams, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="tournament",
            name="teams",
        ),
        migrations.AddField(
            model_name="tournament",
            name="teams",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "Round-robin only. Select existing club teams after "
                    "creating the tournament."
                ),
                related_name="tournaments",
                to="core.team",
            ),
        ),
        migrations.RunPython(
            restore_tournament_team_links,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="team",
            name="match",
        ),
        migrations.AlterModelOptions(
            name="team",
            options={"ordering": ["club", "name"]},
        ),
        migrations.RunPython(ensure_team_clubs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="team",
            name="club",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="teams",
                to="core.club",
            ),
        ),
        migrations.DeleteModel(
            name="ClubTeam",
        ),
    ]
