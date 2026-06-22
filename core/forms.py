from datetime import time, timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .utilities.match_generation import tournament_type_uses_teams
from .models import Match, Profile, Sport, Team, Tournament, TournamentSetupPhase, TournamentType

User = get_user_model()


def tournament_admin_field_names(tournament):
    scheduling = ("starts_at", "game_duration", "break_duration")
    details = ("type", *scheduling, "courts", "rounds")
    if not tournament.pk:
        return ("name", "club", "sport")
    phase = tournament.setup_phase()
    if phase == TournamentSetupPhase.DETAILS:
        return ("name", "club", "sport", *details)
    fields = ("name", "club", "sport", *details)
    if tournament.uses_teams():
        return (*fields, "teams")
    return (*fields, "players")


def duration_to_time(duration):
    if duration is None:
        return time(0, 0)
    total_minutes = int(duration.total_seconds()) // 60
    return time(total_minutes // 60, total_minutes % 60)


def time_to_duration(value):
    if value is None:
        return timedelta(0)
    return timedelta(hours=value.hour, minutes=value.minute)


class HMTimeInput(forms.TimeInput):
    format = "%H:%M"

    def __init__(self, attrs=None):
        super().__init__(
            attrs={"type": "time", "step": "60", **(attrs or {})},
            format="%H:%M",
        )

    def format_value(self, value):
        if isinstance(value, timedelta):
            value = duration_to_time(value)
        return super().format_value(value)


class TournamentAdminForm(forms.ModelForm):
    game_duration = forms.TimeField(
        label="Game duration",
        help_text="Hours and minutes (HH:MM).",
        widget=HMTimeInput(),
        initial=time(1, 30),
        required=False,
    )
    break_duration = forms.TimeField(
        label="Break duration",
        help_text="Hours and minutes (HH:MM). Use 00:00 for no break.",
        widget=HMTimeInput(),
        required=False,
        initial=time(0, 0),
    )

    class Meta:
        model = Tournament
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        visible_fields = set(tournament_admin_field_names(self.instance))
        for field_name in list(self.fields.keys()):
            if field_name not in visible_fields:
                del self.fields[field_name]

        if "game_duration" in self.fields:
            self.initial["game_duration"] = duration_to_time(
                self.instance.game_duration
            )
        if "break_duration" in self.fields:
            self.initial["break_duration"] = duration_to_time(
                self.instance.break_duration
            )

        sport = self.data.get("sport") or (
            self.instance.sport if self.instance.pk else None
        )
        phase = (
            self.instance.setup_phase()
            if self.instance.pk
            else TournamentSetupPhase.SETUP
        )

        if phase == TournamentSetupPhase.DETAILS and sport == Sport.DODGEBALL and "type" in self.fields:
            self.fields["type"].choices = [
                choice
                for choice in TournamentType.choices
                if choice[0] != TournamentType.AMERICANO
            ]

        if phase == TournamentSetupPhase.ROSTER and self.instance.uses_teams():
            if "teams" in self.fields:
                club = self.instance.club
                if club:
                    self.fields["teams"].queryset = club.teams.order_by("name")
                    self.fields["teams"].help_text = (
                        f"Select teams from {club.name}. Create teams under the club first."
                    )
                else:
                    self.fields["teams"].queryset = Team.objects.none()
                    self.fields["teams"].help_text = (
                        "This tournament has no club, so no teams can be selected."
                    )
            return

        if "players" not in self.fields:
            return

        club = self.instance.club if self.instance.pk else None
        if club:
            self.fields["players"].queryset = club.members.order_by("username")
            self.fields["players"].help_text = (
                f"Only members of {club.name} can be selected."
            )
        else:
            self.fields["players"].queryset = User.objects.none()
            self.fields["players"].help_text = (
                "This tournament has no club, so no players can be selected."
            )

    def _get_validation_exclusions(self):
        exclude = super()._get_validation_exclusions()
        exclude |= {"game_duration", "break_duration"}
        phase = (
            self.instance.setup_phase()
            if self.instance.pk
            else TournamentSetupPhase.SETUP
        )
        if phase == TournamentSetupPhase.SETUP:
            exclude |= {
                "type",
                "starts_at",
                "courts",
                "rounds",
                "players",
                "teams",
            }
        elif phase == TournamentSetupPhase.DETAILS:
            exclude |= {"players", "teams"}
        return exclude

    def _post_clean(self):
        super()._post_clean()
        if not hasattr(self, "cleaned_data"):
            return
        if "game_duration" in self.cleaned_data:
            self.instance.game_duration = time_to_duration(
                self.cleaned_data["game_duration"]
            )
        if "break_duration" in self.cleaned_data:
            self.instance.break_duration = time_to_duration(
                self.cleaned_data.get("break_duration")
            )

    def clean(self):
        cleaned_data = super().clean()
        sport = cleaned_data.get("sport") or self.instance.sport
        tournament_type = cleaned_data.get("type") or self.instance.type
        phase = (
            self.instance.setup_phase()
            if self.instance.pk
            else TournamentSetupPhase.SETUP
        )

        if sport == Sport.DODGEBALL and tournament_type == TournamentType.AMERICANO:
            raise ValidationError(
                "Americano tournaments are not supported for dodgeball."
            )

        if phase == TournamentSetupPhase.SETUP:
            return cleaned_data

        if phase == TournamentSetupPhase.DETAILS:
            errors = {}
            if "type" in self.fields and not tournament_type:
                errors["type"] = "Select a tournament type."
            if "starts_at" in self.fields and not cleaned_data.get("starts_at"):
                errors["starts_at"] = "Enter when the tournament starts."
            if errors:
                raise ValidationError(errors)
            return cleaned_data

        club = self.instance.club
        uses_teams = tournament_type_uses_teams(tournament_type, sport)

        if uses_teams:
            if "teams" not in self.fields:
                return cleaned_data
            teams = cleaned_data.get("teams")
            if teams and teams.count() < 2:
                raise ValidationError("Select at least 2 teams.")
            if club and teams:
                invalid_teams = [
                    team for team in teams if team.club_id != club.pk
                ]
                if invalid_teams:
                    names = ", ".join(team.name for team in invalid_teams)
                    raise ValidationError(
                        f"These teams do not belong to {club.name}: {names}"
                    )
            return cleaned_data

        if "players" not in self.fields:
            return cleaned_data

        players = cleaned_data.get("players")

        if players and players.count() < 2:
            raise ValidationError("Select at least 2 players.")

        if club and players:
            member_ids = set(club.members.values_list("pk", flat=True))
            invalid_players = [
                player for player in players if player.pk not in member_ids
            ]
            if invalid_players:
                names = ", ".join(player.get_username() for player in invalid_players)
                raise ValidationError(
                    f"These players are not members of {club.name}: {names}"
                )

        return cleaned_data


def configure_team_members_field(form, team, club=None):
    if club is None and team.club_id:
        club = team.club
    if club:
        form.fields["members"].queryset = club.members.order_by("username")
        form.fields["members"].help_text = (
            f"Only members of {club.name} can be selected."
        )
    else:
        form.fields["members"].queryset = User.objects.none()
        form.fields["members"].help_text = (
            "Select a club before adding team members."
        )


class TeamAdminForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ("club", "name", "members")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "members" in self.fields:
            configure_team_members_field(self, self.instance)

    def clean(self):
        cleaned_data = super().clean()
        members = cleaned_data.get("members")
        club = cleaned_data.get("club") or self.instance.club

        if club and members:
            member_ids = set(club.members.values_list("pk", flat=True))
            invalid_members = [
                member for member in members if member.pk not in member_ids
            ]
            if invalid_members:
                names = ", ".join(
                    member.get_username() for member in invalid_members
                )
                raise ValidationError(
                    f"These players are not members of {club.name}: {names}"
                )

        return cleaned_data


class TeamInlineForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ("name", "members")

    def __init__(self, *args, club=None, **kwargs):
        super().__init__(*args, **kwargs)
        if club is None and self.instance.club_id:
            club = self.instance.club
        configure_team_members_field(self, self.instance, club=club)

    def clean(self):
        cleaned_data = super().clean()
        members = cleaned_data.get("members")
        club = self.instance.club if self.instance.club_id else None
        if club and members:
            member_ids = set(club.members.values_list("pk", flat=True))
            invalid_members = [
                member for member in members if member.pk not in member_ids
            ]
            if invalid_members:
                names = ", ".join(
                    member.get_username() for member in invalid_members
                )
                raise ValidationError(
                    f"These players are not members of {club.name}: {names}"
                )
        return cleaned_data


class MatchAdminForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "teams" not in self.fields:
            return

        club = None
        if self.instance.pk:
            club = self.instance.club
        if club is None and self.instance.tournament_id:
            club = self.instance.tournament.club

        if club:
            queryset = Team.objects.filter(club=club).order_by("name")
            if self.instance.pk:
                queryset = queryset | self.instance.teams.all()
            self.fields["teams"].queryset = queryset.distinct()
            self.fields["teams"].help_text = (
                f"Teams from {club.name} playing in this match."
            )
        else:
            self.fields["teams"].queryset = Team.objects.none()


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("nickname",)
        labels = {
            "nickname": "Display name",
        }
        help_texts = {
            "nickname": "Optional name shown on your profile.",
        }
