from datetime import timedelta
from itertools import combinations
from math import ceil, log2

from ..models import Match, Sport, Team, TournamentType


def tournament_type_uses_teams(tournament_type, sport):
    if tournament_type == TournamentType.ROUND_ROBIN:
        return True
    if tournament_type == TournamentType.SINGLE_ELIMINATION:
        return sport == Sport.DODGEBALL
    return False


def _display_name(user):
    first_name = user.first_name.strip()
    if first_name:
        return first_name
    return user.get_username()


def _team_name(members):
    if len(members) == 1:
        return _display_name(members[0])
    return " & ".join(_display_name(member) for member in members)


def _partnership_key(members):
    return frozenset(member.pk for member in members)


def _match_partnership_key(team_a_members, team_b_members):
    return tuple(sorted([_partnership_key(team_a_members), _partnership_key(team_b_members)]))


def _round_robin_roster_pairings(roster_teams):
    teams = list(roster_teams)
    return [
        (
            list(team_a.members.order_by("pk")),
            list(team_b.members.order_by("pk")),
            team_a.name,
            team_b.name,
            team_a,
            team_b,
        )
        for team_a, team_b in combinations(teams, 2)
    ]


def _single_elimination_team_pairings(teams):
    team_list = list(teams)
    bracket_size = 2 ** ceil(log2(len(team_list)))
    seeded = team_list + [None] * (bracket_size - len(team_list))
    pairings = []
    for index in range(0, bracket_size, 2):
        team_a, team_b = seeded[index], seeded[index + 1]
        if team_a and team_b:
            pairings.append(
                (
                    list(team_a.members.order_by("pk")),
                    list(team_b.members.order_by("pk")),
                    team_a.name,
                    team_b.name,
                    team_a,
                    team_b,
                )
            )
    return pairings


def _single_elimination_pairings(players):
    bracket_size = 2 ** ceil(log2(len(players)))
    seeded = list(players) + [None] * (bracket_size - len(players))
    pairings = []
    for index in range(0, bracket_size, 2):
        player_a, player_b = seeded[index], seeded[index + 1]
        if player_a and player_b:
            pairings.append(([player_a], [player_b], None, None, None, None))
    return pairings


def _americano_court_pairing(group, round_variant):
    player_a, player_b, player_c, player_d = group
    if round_variant == 0:
        return ([player_a, player_b], [player_c, player_d])
    if round_variant == 1:
        return ([player_a, player_c], [player_b, player_d])
    return ([player_a, player_d], [player_b, player_c])


def _americano_pairings(tournament, players, *, respect_round_cap=True):
    player_list = list(players)
    player_count = len(player_list)
    if player_count < 4:
        return []

    if respect_round_cap and tournament.rounds > 0:
        round_count = tournament.rounds
    else:
        round_count = max(1, player_count - 1)
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
            pairings.append(
                (team_a_members, team_b_members, None, None, None, None)
            )

    return pairings


def _player_ids(team_a_members, team_b_members):
    return {member.pk for member in team_a_members + team_b_members}


def _tournament_slot_duration(tournament):
    game_duration = tournament.game_duration or timedelta(minutes=90)
    break_duration = tournament.break_duration or timedelta(0)
    return game_duration + break_duration


def _schedule_pairings(pairings, courts_count, base_time, slot_duration):
    """
    Assign each match to a time slot and court. Matches in the same slot run
    concurrently only when they use different courts and share no players.
    """
    slots = []
    scheduled = []

    for pairing_index, pairing in enumerate(pairings):
        team_a_members, team_b_members = pairing[0], pairing[1]
        match_players = _player_ids(team_a_members, team_b_members)
        assigned = False

        for slot_index, slot in enumerate(slots):
            busy_players = set()
            used_courts = set()
            for entry in slot:
                busy_players |= entry["players"]
                used_courts.add(entry["court"])

            if match_players & busy_players:
                continue

            for court in range(1, courts_count + 1):
                if court not in used_courts:
                    slot.append({"court": court, "players": match_players})
                    scheduled.append((pairing_index, slot_index, court))
                    assigned = True
                    break
            if assigned:
                break

        if not assigned:
            slots.append([{"court": 1, "players": match_players}])
            scheduled.append((pairing_index, len(slots) - 1, 1))

    return [
        (
            pairings[pairing_index][0],
            pairings[pairing_index][1],
            pairings[pairing_index][2] if len(pairings[pairing_index]) > 2 else None,
            pairings[pairing_index][3] if len(pairings[pairing_index]) > 3 else None,
            pairings[pairing_index][4] if len(pairings[pairing_index]) > 4 else None,
            pairings[pairing_index][5] if len(pairings[pairing_index]) > 5 else None,
            court_number,
            base_time + slot_duration * slot_index,
        )
        for pairing_index, slot_index, court_number in scheduled
    ]


def _has_enough_participants(tournament):
    if tournament.uses_teams():
        return tournament.teams.count() >= 2
    return tournament.players.count() >= 2


def build_match_pairings(tournament, *, respect_round_cap=True):
    if tournament.uses_teams():
        selected_teams = tournament.teams.prefetch_related("members")
        if selected_teams.count() < 2:
            return []
        if tournament.type == TournamentType.ROUND_ROBIN:
            return _round_robin_roster_pairings(selected_teams)
        if tournament.type == TournamentType.SINGLE_ELIMINATION:
            return _single_elimination_team_pairings(selected_teams)
        return []

    players = list(tournament.players.order_by("pk"))
    if len(players) < 2:
        return []

    if tournament.type == TournamentType.SINGLE_ELIMINATION:
        return _single_elimination_pairings(players)
    if tournament.type == TournamentType.AMERICANO:
        return _americano_pairings(
            tournament, players, respect_round_cap=respect_round_cap
        )
    return []


def _sync_tournament_round_count(tournament):
    round_count = tournament.matches.values("scheduled_at").distinct().count()
    tournament.rounds = round_count
    tournament.save(update_fields=["rounds"])


def _create_matches(tournament, pairings):
    base_time = tournament.starts_at
    slot_duration = _tournament_slot_duration(tournament)
    schedule = _schedule_pairings(
        pairings, tournament.courts, base_time, slot_duration
    )

    for match_number, (
        team_a_members,
        team_b_members,
        team_a_name,
        team_b_name,
        team_a_entity,
        team_b_entity,
        court_number,
        scheduled_at,
    ) in enumerate(schedule, start=1):
        match = Match.objects.create(
            tournament=tournament,
            club=tournament.club,
            match_number=match_number,
            court_number=court_number,
            scheduled_at=scheduled_at,
        )
        if team_a_entity and team_b_entity:
            match.teams.add(team_a_entity, team_b_entity)
        else:
            team_a = Team.objects.create(
                club=tournament.club,
                name=team_a_name or _team_name(team_a_members),
            )
            team_b = Team.objects.create(
                club=tournament.club,
                name=team_b_name or _team_name(team_b_members),
            )
            team_a.members.set(team_a_members)
            team_b.members.set(team_b_members)
            match.teams.add(team_a, team_b)

    _sync_tournament_round_count(tournament)
    return len(schedule)


def generate_tournament_matches(tournament):
    if tournament.matches.exists():
        return 0

    pairings = build_match_pairings(tournament, respect_round_cap=True)
    if not pairings:
        return 0

    return _create_matches(tournament, pairings)


def regenerate_tournament_matches(tournament):
    tournament.matches.all().delete()

    if not _has_enough_participants(tournament):
        tournament.rounds = 0
        tournament.save(update_fields=["rounds"])
        return 0

    pairings = build_match_pairings(tournament, respect_round_cap=False)
    if not pairings:
        tournament.rounds = 0
        tournament.save(update_fields=["rounds"])
        return 0

    return _create_matches(tournament, pairings)
