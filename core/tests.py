from django.contrib.auth import get_user_model
from django.test import TestCase

from .match_generation import _match_partnership_key, build_match_pairings
from .models import Sport, Tournament, TournamentType

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
