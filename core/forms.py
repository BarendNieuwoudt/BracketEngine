from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .models import Club, Tournament

User = get_user_model()


class TournamentAdminForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "players" not in self.fields:
            return

        club = self._resolve_club()
        if club:
            self.fields["players"].queryset = club.members.order_by("username")
            self.fields["players"].help_text = (
                f"Only members of {club.name} can be selected."
            )
        else:
            self.fields["players"].queryset = User.objects.order_by("username")
            self.fields["players"].help_text = (
                "If a club is selected, only that club's members can be chosen."
            )

    def _resolve_club(self):
        club_id = self.data.get("club")
        if club_id:
            return Club.objects.filter(pk=club_id).first()
        if self.instance.pk and self.instance.club_id:
            return self.instance.club
        return None

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance._state.adding:
            return cleaned_data

        players = cleaned_data.get("players")
        if not players or players.count() < 2:
            raise ValidationError(
                "Select at least 2 players when creating a tournament."
            )

        club = cleaned_data.get("club")
        if club and players:
            member_ids = set(club.members.values_list("pk", flat=True))
            invalid_players = [player for player in players if player.pk not in member_ids]
            if invalid_players:
                names = ", ".join(player.get_username() for player in invalid_players)
                raise ValidationError(
                    f"These players are not members of {club.name}: {names}"
                )

        return cleaned_data
