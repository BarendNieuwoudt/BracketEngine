from django.contrib.auth import get_user_model
from django.test import TestCase

from .match_generation import (
    _match_partnership_key,
    _schedule_pairings,
    build_match_pairings,
    generate_tournament_matches,
    regenerate_tournament_matches,
)
from .models import Sport, Tournament, TournamentType
from django.utils import timezone

User = get_user_model()


class AmericanoPairingTests(TestCase):
    def setUp(self):
        self.players = [
            User.objects.create_user(f"player{i}", password="test")
            for i in range(4)
        ]

    def test_four_player_americano_has_unique_teams_per_match(self):
        tournament = Tournament.objects.create(
            name="Americano test",
            type=TournamentType.AMERICANO,
            sport=Sport.PADEL,
            rounds=3,
        )
        tournament.players.set(self.players)

        pairings = build_match_pairings(tournament)
        partnership_keys = [
            _match_partnership_key(team_a, team_b) for team_a, team_b in pairings
        ]

        self.assertEqual(len(pairings), 3)
        self.assertEqual(len(partnership_keys), len(set(partnership_keys)))


class MatchSchedulingTests(TestCase):
    def setUp(self):
        self.players = [
            User.objects.create_user(f"player{i}", password="test")
            for i in range(4)
        ]

    def test_parallel_matches_use_different_courts_without_shared_players(self):
        tournament = Tournament.objects.create(
            name="Round robin scheduling",
            type=TournamentType.ROUND_ROBIN,
            sport=Sport.PADEL,
            courts=2,
        )
        tournament.players.set(self.players)
        generate_tournament_matches(tournament)

        matches = list(tournament.matches.order_by("scheduled_at", "court_number"))
        slots = {}
        for match in matches:
            slot = slots.setdefault(match.scheduled_at, [])
            slot.append(match)

        for scheduled_at, slot_matches in slots.items():
            courts = [match.court_number for match in slot_matches]
            self.assertEqual(len(courts), len(set(courts)))

            busy_players = set()
            for match in slot_matches:
                match_players = set(
                    match.teams.values_list("members__pk", flat=True).distinct()
                )
                self.assertFalse(busy_players & match_players)
                busy_players |= match_players

    def test_schedule_pairings_assigns_court_numbers(self):
        tournament = Tournament.objects.create(
            name="Temp",
            type=TournamentType.ROUND_ROBIN,
            sport=Sport.PADEL,
            courts=2,
        )
        tournament.players.set(self.players)
        pairings = build_match_pairings(tournament)

        schedule = _schedule_pairings(pairings, courts_count=2, base_time=timezone.now())
        court_numbers = {entry[2] for entry in schedule}
        self.assertTrue(court_numbers.issubset({1, 2}))

    def test_regenerate_matches_when_courts_change(self):
        tournament = Tournament.objects.create(
            name="Regenerate test",
            type=TournamentType.ROUND_ROBIN,
            sport=Sport.PADEL,
            courts=1,
        )
        tournament.players.set(self.players)
        generate_tournament_matches(tournament)
        original_times = list(
            tournament.matches.order_by("scheduled_at").values_list(
                "scheduled_at", flat=True
            )
        )

        tournament.courts = 2
        tournament.save()
        regenerate_tournament_matches(tournament)

        self.assertEqual(tournament.matches.count(), 6)
        new_times = list(
            tournament.matches.order_by("scheduled_at").values_list(
                "scheduled_at", flat=True
            )
        )
        self.assertLess(len(set(new_times)), len(set(original_times)))
