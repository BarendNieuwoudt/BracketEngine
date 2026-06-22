def sync_tournament_players_from_roster(tournament):
    """Keep tournament.players in sync with selected club team members."""
    if not tournament.uses_teams():
        return
    member_ids = tournament.teams.values_list("members__pk", flat=True).distinct()
    tournament.players.set(member_ids)


def roster_team_signature(tournament):
    """Stable signature of selected teams and members for change detection."""
    parts = []
    for team in tournament.teams.prefetch_related("members").order_by("pk"):
        member_ids = tuple(
            team.members.order_by("pk").values_list("pk", flat=True)
        )
        parts.append((team.pk, team.name, member_ids))
    return tuple(parts)
