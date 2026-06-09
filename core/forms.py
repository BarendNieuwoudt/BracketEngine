from datetime import time, timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .models import Profile, Team, Tournament

User = get_user_model()


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
        self.initial["game_duration"] = duration_to_time(
            self.instance.game_duration
        )
        self.initial["break_duration"] = duration_to_time(
            self.instance.break_duration
        )

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
        return exclude | {"game_duration", "break_duration"}

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
        if self.instance._state.adding or "players" not in self.fields:
            return cleaned_data

        players = cleaned_data.get("players")
        club = self.instance.club

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


def resolve_team_club(team):
    if team.club_id:
        return team.club
    if team.match_id:
        match = team.match
        if match.club_id:
            return match.club
        return match.tournament.club
    return None


def configure_team_members_field(form, team):
    club = resolve_team_club(team)
    if club:
        form.fields["members"].queryset = club.members.order_by("username")
        form.fields["members"].help_text = (
            f"Only members of {club.name} can be selected."
        )
    else:
        form.fields["members"].queryset = User.objects.none()
        form.fields["members"].help_text = (
            "This team has no club, so no members can be selected."
        )


class TeamAdminForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ("match", "name", "members")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "members" not in self.fields:
            return

        team = self.instance
        if not team.match_id and self.data.get("match"):
            team = Team(match_id=self.data.get("match"))
        configure_team_members_field(self, team)

    def clean(self):
        cleaned_data = super().clean()
        if "members" not in self.fields:
            return cleaned_data

        members = cleaned_data.get("members")
        match = cleaned_data.get("match") or self.instance.match
        club = resolve_team_club(self.instance)
        if club is None and match is not None:
            club = match.club or match.tournament.club

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configure_team_members_field(self, self.instance)

    def clean(self):
        cleaned_data = super().clean()
        members = cleaned_data.get("members")
        club = resolve_team_club(self.instance)
        if club is None and self.instance.match_id:
            match = self.instance.match
            club = match.club or match.tournament.club

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
