from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .models import Tournament

User = get_user_model()


class TournamentAdminForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
