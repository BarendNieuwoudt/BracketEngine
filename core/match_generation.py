from datetime import timedelta
from itertools import combinations
from math import ceil, log2

from django.utils import timezone

from .models import Match, Team, TournamentType


def _display_name(user):
    full_name = user.get_full_name().strip()
    if full_name:
        return full_name
    return user.get_username()


def _team_name(members):
    if len(members) == 1:
        return _display_name(members[0])
    return " / ".join(_display_name(member) for member in members)


def _partnership_key(members):
    return frozenset(member.pk for member in members)


def _match_partnership_key(team_a_members, team_b_members):
    return tuple(sorted([_partnership_key(team_a_members), _partnership_key(team_b_members)]))


def _round_robin_pairings(players):
    return [([player_a], [player_b]) for player_a, player_b in combinations(players, 2)]


def _single_elimination_pairings(players):
    bracket_size = 2 ** ceil(log2(len(players)))
    seeded = list(players) + [None] * (bracket_size - len(players))
    pairings = []
    for index in range(0, bracket_size, 2):
        player_a, player_b = seeded[index], seeded[index + 1]
        if player_a and player_b:
            pairings.append(([player_a], [player_b]))
    return pairings


def _americano_court_pairing(group, round_variant):
    player_a, player_b, player_c, player_d = group
    if round_variant == 0:
        return ([player_a, player_b], [player_c, player_d])
    if round_variant == 1:
        return ([player_a, player_c], [player_b, player_d])
    return ([player_a, player_d], [player_b, player_c])


def _americano_pairings(tournament, players):
    player_list = list(players)
    player_count = len(player_list)
    if player_count < 4:
        return []

    round_count = (
        tournament.rounds if tournament.rounds > 0 else max(1, player_count - 1)
    )
    pairings = []
    seen_partnerships = set()

    for round_index in range(round_count):
        rotated = (
            [player_list[0]]
            + player_list[1 + round_index : player_count]
            + player_list[1 : 1 + round_index]
        )
        playing_count = (player_count // 4) * 4
        round_variant = round_index % 3

        for court_index in range(0, playing_count, 4):
            group = rotated[court_index : court_index + 4]
            team_a_members, team_b_members = _americano_court_pairing(group, round_variant)
            match_key = _match_partnership_key(team_a_members, team_b_members)
            if match_key in seen_partnerships:
                continue
            seen_partnerships.add(match_key)
            pairings.append((team_a_members, team_b_members))

    return pairings


def build_match_pairings(tournament):
    players = list(tournament.players.order_by("pk"))
    if len(players) < 2:
        return []

    if tournament.type == TournamentType.ROUND_ROBIN:
        return _round_robin_pairings(players)
    if tournament.type == TournamentType.SINGLE_ELIMINATION:
        return _single_elimination_pairings(players)
    if tournament.type == TournamentType.AMERICANO:
        return _americano_pairings(tournament, players)
    return []


def generate_tournament_matches(tournament):
    if tournament.matches.exists():
        return 0

    pairings = build_match_pairings(tournament)
    if not pairings:
        return 0

    base_time = timezone.now()
    for match_number, (team_a_members, team_b_members) in enumerate(pairings, start=1):
        match = Match.objects.create(
            tournament=tournament,
            match_number=match_number,
            scheduled_at=base_time + timedelta(hours=match_number - 1),
        )
        team_a = Team.objects.create(match=match, name=_team_name(team_a_members))
        team_b = Team.objects.create(match=match, name=_team_name(team_b_members))
        team_a.members.set(team_a_members)
        team_b.members.set(team_b_members)

    return len(pairings)
