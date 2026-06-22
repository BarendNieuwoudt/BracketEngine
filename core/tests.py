from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from .forms import TournamentAdminForm
from .utilities.match_generation import (
    _match_partnership_key,
    _schedule_pairings,
    build_match_pairings,
    generate_tournament_matches,
    regenerate_tournament_matches,
)
from django.urls import reverse
from .models import Club, Sport, Team, Tournament, TournamentSetupPhase, TournamentType
from .utilities.tournament_roster import sync_tournament_players_from_roster
from django.utils import timezone

User = get_user_model()


def _register_club_teams(tournament, member_groups, names=None):
    if tournament.club_id is None:
        club = Club.objects.create(name="Test Club", email="test@example.com")
        all_members = [member for group in member_groups for member in group]
        club.members.set(all_members)
        tournament.club = club
        tournament.save(update_fields=["club"])
    team_ids = []
    for index, members in enumerate(member_groups):
        team = Team.objects.create(
            club=tournament.club,
            name=names[index] if names else f"Team {index + 1}",
        )
        team.members.set(members)
        team_ids.append(team.pk)
    tournament.teams.set(team_ids)
    sync_tournament_players_from_roster(tournament)


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
            _match_partnership_key(pairing[0], pairing[1]) for pairing in pairings
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
        _register_club_teams(tournament, [[p] for p in self.players])
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
        _register_club_teams(tournament, [[p] for p in self.players])
        pairings = build_match_pairings(tournament)

        schedule = _schedule_pairings(
            pairings,
            courts_count=2,
            base_time=timezone.now(),
            slot_duration=timedelta(hours=1),
        )
        court_numbers = {entry[6] for entry in schedule}
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
        _register_club_teams(
            tournament,
            [[self.players[0]], [self.players[1]], [self.players[2]]],
        )
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
        _register_club_teams(tournament, [[p] for p in self.players])
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
        _register_club_teams(tournament, [[p] for p in self.players])
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
        _register_club_teams(tournament, [[p] for p in self.players])
        generate_tournament_matches(tournament)
        tournament.refresh_from_db()

        self.assertEqual(tournament.matches.count(), 6)
        self.assertEqual(tournament.rounds, 6)

    def test_round_robin_match_teams_use_roster_names(self):
        tournament = self._create_tournament(
            name="Named teams",
            type=TournamentType.ROUND_ROBIN,
            courts=1,
        )
        _register_club_teams(
            tournament,
            [[self.players[0], self.players[1]], [self.players[2], self.players[3]]],
            names=["Alice & Bob", "Carol & Dave"],
        )
        generate_tournament_matches(tournament)

        match = tournament.matches.first()
        team_names = list(match.teams.order_by("pk").values_list("name", flat=True))
        self.assertEqual(set(team_names), {"Alice & Bob", "Carol & Dave"})

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
        _register_club_teams(tournament, [[p] for p in self.players])
        generate_tournament_matches(tournament)

        for match in tournament.matches.all():
            self.assertEqual(match.club_id, club.pk)
            for team in match.teams.all():
                self.assertEqual(team.club_id, club.pk)


class DodgeballTournamentTests(TestCase):
    def setUp(self):
        self.players = [
            User.objects.create_user(f"player{i}", password="test")
            for i in range(8)
        ]

    def test_americano_rejected_for_dodgeball(self):
        tournament = Tournament(
            name="Invalid",
            type=TournamentType.AMERICANO,
            sport=Sport.DODGEBALL,
            starts_at=timezone.now() + timedelta(days=1),
            courts=1,
        )
        form = TournamentAdminForm(
            data={
                "name": "Invalid",
                "club": "",
                "type": TournamentType.AMERICANO,
                "sport": Sport.DODGEBALL,
                "starts_at": tournament.starts_at.strftime("%Y-%m-%dT%H:%M"),
                "game_duration": "01:30",
                "break_duration": "00:00",
                "courts": 1,
                "rounds": 0,
            },
            instance=tournament,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Americano", str(form.errors))

    def test_single_elimination_uses_registered_teams(self):
        tournament = Tournament.objects.create(
            name="Dodgeball bracket",
            type=TournamentType.SINGLE_ELIMINATION,
            sport=Sport.DODGEBALL,
            starts_at=timezone.now() + timedelta(days=1),
            courts=1,
        )
        _register_club_teams(
            tournament,
            [[p] for p in self.players[:4]],
            names=["A", "B", "C", "D"],
        )
        generate_tournament_matches(tournament)

        self.assertEqual(tournament.matches.count(), 2)
        match = tournament.matches.first()
        team_names = set(match.teams.values_list("name", flat=True))
        self.assertEqual(len(team_names), 2)
        self.assertTrue(team_names.issubset({"A", "B", "C", "D"}))


class TournamentAdminFormTests(TestCase):
    def test_dodgeball_does_not_support_americano(self):
        tournament = Tournament(
            name="Rules",
            type=TournamentType.ROUND_ROBIN,
            sport=Sport.DODGEBALL,
            starts_at=timezone.now() + timedelta(days=1),
            courts=1,
        )
        self.assertFalse(tournament.supports_americano())
        self.assertTrue(tournament.uses_teams())

    def test_padel_single_elimination_uses_players(self):
        tournament = Tournament(
            name="Padel SE",
            type=TournamentType.SINGLE_ELIMINATION,
            sport=Sport.PADEL,
            starts_at=timezone.now() + timedelta(days=1),
            courts=1,
        )
        self.assertFalse(tournament.uses_teams())

    def test_setup_phases(self):
        tournament = Tournament.objects.create(
            name="Phased",
            sport=Sport.PADEL,
        )
        self.assertEqual(tournament.setup_phase(), TournamentSetupPhase.DETAILS)

        tournament.type = TournamentType.ROUND_ROBIN
        tournament.starts_at = timezone.now() + timedelta(days=1)
        tournament.save()
        self.assertEqual(tournament.setup_phase(), TournamentSetupPhase.ROSTER)

    def test_phase_one_create_form_accepts_basics_only(self):
        from django.test import RequestFactory
        from django.contrib.admin.sites import AdminSite
        from core.admin import TournamentAdmin

        site = AdminSite()
        admin = TournamentAdmin(Tournament, site)
        request = RequestFactory().get("/")
        form_class = admin.get_form(request, obj=None)
        form = form_class(
            data={"name": "Summer Cup", "club": "", "sport": Sport.PADEL}
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_time_fields_convert_to_duration_on_save(self):
        from datetime import time

        tournament = Tournament(
            name="Form test",
            type=TournamentType.ROUND_ROBIN,
            sport=Sport.PADEL,
            starts_at=timezone.now() + timedelta(days=1),
            courts=1,
        )
        tournament.save()
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
        self.club.members.add(self.player, self.other_player)
        self.tournament = Tournament.objects.create(
            name="Summer Cup",
            type=TournamentType.ROUND_ROBIN,
            sport=Sport.PADEL,
            starts_at=self.starts_at,
            courts=1,
            club=self.club,
        )
        team_a = Team.objects.create(club=self.club, name="Alice")
        team_a.members.set([self.player])
        team_b = Team.objects.create(club=self.club, name="Player 2")
        team_b.members.set([self.other_player])
        self.tournament.teams.set([team_a, team_b])
        sync_tournament_players_from_roster(self.tournament)
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
        self.assertContains(response, '<span class="info-value">3</span>')
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


class UserAdminLoginAsTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            "staffuser",
            password="staffpass",
            is_staff=True,
        )
        self.player = User.objects.create_user("portaluser", password="playerpass")

    def test_staff_can_login_as_user_from_admin(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("admin:auth_user_login_as", args=[self.player.pk])
        )
        self.assertRedirects(response, reverse("dashboard"))
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_inactive_user_cannot_be_impersonated(self):
        self.player.is_active = False
        self.player.save()
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("admin:auth_user_login_as", args=[self.player.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("admin:auth_user_changelist"))

    def test_non_staff_cannot_use_login_as(self):
        outsider = User.objects.create_user("outsider", password="pass")
        self.client.force_login(outsider)
        response = self.client.get(
            reverse("admin:auth_user_login_as", args=[self.player.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)
