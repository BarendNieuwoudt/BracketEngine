from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from .forms import TournamentAdminForm
from .match_generation import (
    _match_partnership_key,
    _schedule_pairings,
    build_match_pairings,
    generate_tournament_matches,
    regenerate_tournament_matches,
)
from django.urls import reverse
from .models import Club, Sport, Tournament, TournamentType
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
            starts_at=timezone.now() + timedelta(days=1),
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
        self.starts_at = timezone.now() + timedelta(days=1)

    def _create_tournament(self, **kwargs):
        defaults = {
            "sport": Sport.PADEL,
            "starts_at": self.starts_at,
        }
        defaults.update(kwargs)
        return Tournament.objects.create(**defaults)

    def test_parallel_matches_use_different_courts_without_shared_players(self):
        tournament = self._create_tournament(
            name="Round robin scheduling",
            type=TournamentType.ROUND_ROBIN,
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
        tournament = self._create_tournament(
            name="Temp",
            type=TournamentType.ROUND_ROBIN,
            courts=2,
        )
        tournament.players.set(self.players)
        pairings = build_match_pairings(tournament)

        schedule = _schedule_pairings(
            pairings,
            courts_count=2,
            base_time=timezone.now(),
            slot_duration=timedelta(hours=1),
        )
        court_numbers = {entry[2] for entry in schedule}
        self.assertTrue(court_numbers.issubset({1, 2}))

    def test_matches_scheduled_from_tournament_start(self):
        game_duration = timedelta(minutes=60)
        break_duration = timedelta(minutes=15)
        tournament = self._create_tournament(
            name="Start time",
            type=TournamentType.ROUND_ROBIN,
            courts=1,
            game_duration=game_duration,
            break_duration=break_duration,
        )
        tournament.players.set(self.players)
        generate_tournament_matches(tournament)

        matches = list(tournament.matches.order_by("scheduled_at"))
        self.assertEqual(matches[0].scheduled_at, self.starts_at)
        self.assertEqual(
            matches[1].scheduled_at,
            self.starts_at + game_duration + break_duration,
        )

    def test_regenerate_matches_when_courts_change(self):
        tournament = self._create_tournament(
            name="Regenerate test",
            type=TournamentType.ROUND_ROBIN,
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

    def test_rounds_set_to_number_of_scheduled_time_slots(self):
        tournament = self._create_tournament(
            name="Rounds sync",
            type=TournamentType.ROUND_ROBIN,
            courts=2,
            rounds=0,
        )
        tournament.players.set(self.players)
        generate_tournament_matches(tournament)
        tournament.refresh_from_db()

        distinct_slots = tournament.matches.values("scheduled_at").distinct().count()
        self.assertEqual(tournament.rounds, distinct_slots)
        self.assertEqual(tournament.rounds, 3)

    def test_rounds_equals_match_count_with_one_court(self):
        tournament = self._create_tournament(
            name="Single court rounds",
            type=TournamentType.ROUND_ROBIN,
            courts=1,
            rounds=0,
        )
        tournament.players.set(self.players)
        generate_tournament_matches(tournament)
        tournament.refresh_from_db()

        self.assertEqual(tournament.matches.count(), 6)
        self.assertEqual(tournament.rounds, 6)

    def test_generated_matches_and_teams_inherit_tournament_club(self):
        club = Club.objects.create(
            name="Padel Club",
            email="club@example.com",
        )
        club.members.set(self.players)
        tournament = self._create_tournament(
            name="Club tournament",
            type=TournamentType.ROUND_ROBIN,
            courts=1,
            club=club,
        )
        tournament.players.set(self.players)
        generate_tournament_matches(tournament)

        for match in tournament.matches.all():
            self.assertEqual(match.club_id, club.pk)
            for team in match.teams.all():
                self.assertEqual(team.club_id, club.pk)


class TournamentAdminFormTests(TestCase):
    def test_time_fields_convert_to_duration_on_save(self):
        from datetime import time

        tournament = Tournament(
            name="Form test",
            type=TournamentType.ROUND_ROBIN,
            sport=Sport.PADEL,
            starts_at=timezone.now() + timedelta(days=1),
            courts=1,
        )
        form = TournamentAdminForm(
            data={
                "name": "Form test",
                "club": "",
                "type": TournamentType.ROUND_ROBIN,
                "sport": Sport.PADEL,
                "starts_at": tournament.starts_at.strftime("%Y-%m-%dT%H:%M"),
                "game_duration": "01:30",
                "break_duration": "00:15",
                "courts": 1,
                "rounds": 0,
            },
            instance=tournament,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.game_duration, timedelta(hours=1, minutes=30))
        self.assertEqual(saved.break_duration, timedelta(minutes=15))


class PlayerViewTests(TestCase):
    def setUp(self):
        self.starts_at = timezone.now() + timedelta(days=1)
        self.player = User.objects.create_user(
            "player1",
            password="pass12345",
            first_name="Alice",
        )
        self.other_player = User.objects.create_user(
            "player2",
            password="pass12345",
        )
        self.club = Club.objects.create(
            name="Padel Club",
            email="club@example.com",
            location="Cape Town",
        )
        self.club.members.add(self.player)
        self.tournament = Tournament.objects.create(
            name="Summer Cup",
            type=TournamentType.ROUND_ROBIN,
            sport=Sport.PADEL,
            starts_at=self.starts_at,
            courts=1,
            club=self.club,
        )
        self.tournament.players.set([self.player, self.other_player])
        generate_tournament_matches(self.tournament)
        self.match = self.tournament.matches.first()

    def test_home_redirects_authenticated_users_to_dashboard(self):
        self.client.login(username="player1", password="pass12345")
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("dashboard"))

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, f"{reverse('login')}?next=/dashboard/")

    def test_dashboard_shows_player_matches_and_clubs(self):
        self.client.login(username="player1", password="pass12345")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Summer Cup")
        self.assertContains(response, "Padel Club")
        self.assertContains(response, str(self.match))

    def test_player_can_view_own_match_detail(self):
        self.client.login(username="player1", password="pass12345")
        response = self.client.get(
            reverse("match_detail", kwargs={"uuid": self.match.uuid})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Court")
        self.assertContains(response, "Alice")

    def test_dashboard_links_to_tournament_detail(self):
        self.client.login(username="player1", password="pass12345")
        response = self.client.get(reverse("dashboard"))
        self.assertContains(
            response,
            reverse("tournament_detail", kwargs={"uuid": self.tournament.uuid}),
        )

    def test_player_can_view_registered_tournament_detail(self):
        self.client.login(username="player1", password="pass12345")
        response = self.client.get(
            reverse("tournament_detail", kwargs={"uuid": self.tournament.uuid})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Summer Cup")
        self.assertContains(response, "Round Robin")
        self.assertContains(response, str(self.match))

    def test_dashboard_links_to_club_detail(self):
        self.client.login(username="player1", password="pass12345")
        response = self.client.get(reverse("dashboard"))
        self.assertContains(
            response,
            reverse("club_detail", kwargs={"uuid": self.club.uuid}),
        )

    def test_player_can_view_their_club_detail(self):
        member_only = User.objects.create_user("secretmember", password="pass12345")
        self.club.members.add(member_only)
        self.client.login(username="player1", password="pass12345")
        response = self.client.get(
            reverse("club_detail", kwargs={"uuid": self.club.uuid})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Padel Club")
        self.assertContains(response, "Cape Town")
        self.assertContains(response, "Members")
        self.assertContains(response, '<span class="info-label">Members</span>')
        self.assertContains(response, '<span class="info-value">2</span>')
        self.assertNotContains(response, "secretmember")

    def test_player_cannot_view_club_they_are_not_in(self):
        outsider = User.objects.create_user("outsider", password="pass12345")
        self.client.login(username="outsider", password="pass12345")
        response = self.client.get(
            reverse("club_detail", kwargs={"uuid": self.club.uuid})
        )
        self.assertEqual(response.status_code, 404)

    def test_player_cannot_view_tournament_they_are_not_in(self):
        outsider = User.objects.create_user("outsider", password="pass12345")
        self.client.login(username="outsider", password="pass12345")
        response = self.client.get(
            reverse("tournament_detail", kwargs={"uuid": self.tournament.uuid})
        )
        self.assertEqual(response.status_code, 404)

    def test_player_cannot_view_match_they_are_not_in(self):
        outsider = User.objects.create_user("outsider", password="pass12345")
        self.client.login(username="outsider", password="pass12345")
        response = self.client.get(
            reverse("match_detail", kwargs={"uuid": self.match.uuid})
        )
        self.assertEqual(response.status_code, 404)

    def test_profile_update_nickname(self):
        self.client.login(username="player1", password="pass12345")
        response = self.client.post(
            reverse("profile"),
            {"nickname": "Ace"},
        )
        self.assertRedirects(response, reverse("profile"))
        self.player.profile.refresh_from_db()
        self.assertEqual(self.player.profile.nickname, "Ace")
