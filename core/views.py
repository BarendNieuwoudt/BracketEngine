from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ProfileForm
from .models import Club, Match, Tournament


def _format_duration(duration):
    if duration is None:
        return "0m"
    total_minutes = int(duration.total_seconds()) // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def _user_clubs(user):
    return user.clubs.all()


def _user_tournaments(user):
    return user.tournaments.select_related("club")


def _user_matches(user):
    return (
        Match.objects.filter(teams__members=user)
        .distinct()
        .select_related("tournament", "tournament__club", "club")
        .prefetch_related("teams", "teams__members")
    )


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "core/home.html")


class PlayerLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True


@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")


@login_required
def dashboard(request):
    now = timezone.now()
    matches = _user_matches(request.user)
    upcoming_matches = matches.filter(scheduled_at__gte=now).order_by("scheduled_at")
    past_matches = matches.filter(scheduled_at__lt=now).order_by("-scheduled_at")[:10]
    tournaments = _user_tournaments(request.user).order_by("-starts_at")
    clubs = _user_clubs(request.user).order_by("name")

    return render(
        request,
        "core/dashboard.html",
        {
            "upcoming_matches": upcoming_matches,
            "past_matches": past_matches,
            "tournaments": tournaments,
            "clubs": clubs,
        },
    )


@login_required
def tournament_detail(request, uuid):
    tournament = get_object_or_404(_user_tournaments(request.user), uuid=uuid)
    matches = tournament.matches.select_related("club").order_by(
        "scheduled_at", "match_number"
    )
    user_match_uuids = set(
        _user_matches(request.user)
        .filter(tournament=tournament)
        .values_list("uuid", flat=True)
    )
    now = timezone.now()
    upcoming_matches = [m for m in matches if m.scheduled_at >= now]
    past_matches = [m for m in matches if m.scheduled_at < now]

    return render(
        request,
        "core/tournament_detail.html",
        {
            "tournament": tournament,
            "upcoming_matches": upcoming_matches,
            "past_matches": past_matches,
            "user_match_uuids": user_match_uuids,
            "game_duration_display": _format_duration(tournament.game_duration),
            "break_duration_display": _format_duration(tournament.break_duration),
        },
    )


@login_required
def club_detail(request, uuid):
    club = get_object_or_404(_user_clubs(request.user), uuid=uuid)
    now = timezone.now()
    tournaments = _user_tournaments(request.user).filter(club=club).order_by(
        "-starts_at"
    )
    matches = _user_matches(request.user).filter(club=club)
    upcoming_matches = matches.filter(scheduled_at__gte=now).order_by("scheduled_at")
    past_matches = matches.filter(scheduled_at__lt=now).order_by("-scheduled_at")

    return render(
        request,
        "core/club_detail.html",
        {
            "club": club,
            "member_count": club.members.count(),
            "tournaments": tournaments,
            "upcoming_matches": upcoming_matches,
            "past_matches": past_matches,
        },
    )


@login_required
def match_detail(request, uuid):
    match = get_object_or_404(_user_matches(request.user), uuid=uuid)
    teams = list(match.teams.order_by("pk"))
    return render(
        request,
        "core/match_detail.html",
        {
            "match": match,
            "teams": teams,
        },
    )


@login_required
def profile(request):
    profile_obj = request.user.profile
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=profile_obj)

    return render(
        request,
        "core/profile.html",
        {
            "form": form,
        },
    )
