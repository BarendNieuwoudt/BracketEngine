from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils import timezone

from .forms import (
    MatchAdminForm,
    TeamAdminForm,
    TeamInlineForm,
    TournamentAdminForm,
    tournament_admin_field_names,
)
from .utilities.match_generation import (
    generate_tournament_matches,
    regenerate_tournament_matches,
)
from .utilities.tournament_roster import (
    roster_team_signature,
    sync_tournament_players_from_roster,
)
from .models import Club, Match, Profile, Team, Tournament, TournamentSetupPhase, TournamentType

User = get_user_model()

admin.site.site_header = "BracketEngine - Tournament Management System"
admin.site.site_title = "BracketEngine"
admin.site.index_title = "Tournament management"


class UUIDOnChangeOnlyMixin:
    """Show uuid read-only at the top after save; visible to staff only."""

    def _fields_with_uuid_first(self, request, obj, fields):
        if obj is not None and request.user.is_staff:
            return ("uuid", *fields)
        return fields

    def get_fields(self, request, obj=None):
        fields = tuple(
            field for field in super().get_fields(request, obj) if field != "uuid"
        )
        return self._fields_with_uuid_first(request, obj, fields)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is None or not request.user.is_staff:
            return tuple(field for field in readonly if field != "uuid")
        if "uuid" not in readonly:
            readonly.append("uuid")
        return tuple(readonly)


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0
    max_num = 1


class UserAdmin(auth_admin.UserAdmin):
    inlines = [*auth_admin.UserAdmin.inlines, ProfileInline]
    filter_horizontal = ("user_permissions",)
    readonly_fields = ("last_login", "date_joined")
    list_display = (*auth_admin.UserAdmin.list_display, "login_as_link")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "user_permissions",
                ),
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<id>/login-as/",
                self.admin_site.admin_view(self.login_as_view),
                name="auth_user_login_as",
            ),
        ]
        return custom_urls + urls

    def login_as_view(self, request, id):
        user = get_object_or_404(User, pk=id)

        if not user.is_active:
            self.message_user(
                request,
                "That user account is inactive.",
                messages.ERROR,
            )
            return redirect("admin:auth_user_changelist")

        if user.is_superuser and not request.user.is_superuser:
            self.message_user(
                request,
                "Only superusers can log in as another superuser.",
                messages.ERROR,
            )
            return redirect("admin:auth_user_changelist")

        backend = settings.AUTHENTICATION_BACKENDS[0]
        login(request, user, backend=backend)
        self.message_user(
            request,
            f"You are now logged in as {user.get_username()} in the player portal.",
            messages.SUCCESS,
        )
        return redirect("dashboard")

    @admin.display(description="Player portal")
    def login_as_link(self, obj):
        url = reverse("admin:auth_user_login_as", args=[obj.pk])
        return format_html('<a href="{}">Log in as user</a>', url)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.unregister(Group)


class MatchInline(admin.TabularInline):
    model = Match
    extra = 0


class TeamInline(admin.TabularInline):
    model = Team
    form = TeamInlineForm
    extra = 1
    fields = ("name", "members")
    filter_horizontal = ("members",)
    verbose_name = "Team"
    verbose_name_plural = "Teams"

    def get_extra(self, request, obj=None, **kwargs):
        if obj and obj.teams.exists():
            return 0
        return 1

    def get_formset(self, request, obj=None, **kwargs):
        parent_club = obj
        BaseForm = self.form

        class TeamForm(BaseForm):
            def __init__(self, *args, **form_kwargs):
                form_kwargs.setdefault("club", parent_club)
                super().__init__(*args, **form_kwargs)

        formset = super().get_formset(request, obj, **kwargs)
        formset.form = TeamForm
        return formset


class ScheduleListFilter(admin.SimpleListFilter):
    title = "schedule"
    parameter_name = "schedule"
    date_field = None

    def lookups(self, request, model_admin):
        return (
            ("upcoming", "Upcoming"),
            ("past", "Past"),
        )

    def queryset(self, request, queryset):
        if not self.date_field:
            return queryset
        now = timezone.now()
        if self.value() == "upcoming":
            return queryset.filter(**{f"{self.date_field}__gte": now})
        if self.value() == "past":
            return queryset.filter(**{f"{self.date_field}__lt": now})
        return queryset


class TournamentScheduleFilter(ScheduleListFilter):
    date_field = "starts_at"


class MatchScheduleFilter(ScheduleListFilter):
    date_field = "scheduled_at"


@admin.register(Tournament)
class TournamentAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    form = TournamentAdminForm
    list_display = (
        "name",
        "starts_at",
        "club",
        "type",
        "sport",
        "courts",
        "rounds",
        "player_count",
    )
    list_filter = (TournamentScheduleFilter, "type", "sport", "club")
    search_fields = ("name", "uuid")
    filter_horizontal = ("players", "teams")

    def get_fields(self, request, obj=None):
        tournament = obj or Tournament()
        return self._fields_with_uuid_first(
            request, obj, tournament_admin_field_names(tournament)
        )

    def get_filter_horizontal(self, request, obj=None):
        if obj and obj.setup_phase() == TournamentSetupPhase.ROSTER and obj.uses_teams():
            return ("teams",)
        if obj and obj.setup_phase() == TournamentSetupPhase.ROSTER:
            return ("players",)
        return ()

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            for field in ("club", "sport"):
                if field not in readonly:
                    readonly.append(field)
            if obj.setup_phase() == TournamentSetupPhase.ROSTER and "type" not in readonly:
                readonly.append("type")
        return tuple(readonly)

    def get_inlines(self, request, obj=None):
        if obj is None or obj.setup_phase() != TournamentSetupPhase.ROSTER:
            return []
        if obj.uses_teams():
            if obj.teams.exists():
                return [MatchInline]
            return []
        if obj.players.exists():
            return [MatchInline]
        return []

    def save_model(self, request, obj, form, change):
        if change and obj.pk:
            previous = Tournament.objects.get(pk=obj.pk)
            if previous.uses_teams():
                self._old_roster_signature = roster_team_signature(previous)
                self._old_player_ids = set()
            else:
                self._old_roster_signature = ()
                self._old_player_ids = set(
                    previous.players.values_list("pk", flat=True)
                )
            self._schedule_fields_changed = (
                previous.courts != obj.courts
                or previous.rounds != obj.rounds
                or previous.starts_at != obj.starts_at
                or previous.game_duration != obj.game_duration
                or previous.break_duration != obj.break_duration
            )
        else:
            self._old_player_ids = set()
            self._old_roster_signature = ()
            self._schedule_fields_changed = False
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if not change:
            return

        tournament = form.instance
        if tournament.setup_phase() != TournamentSetupPhase.ROSTER:
            return

        schedule_fields_changed = self._schedule_fields_changed

        if tournament.uses_teams():
            sync_tournament_players_from_roster(tournament)
            roster_changed = (
                self._old_roster_signature != roster_team_signature(tournament)
            )
            participants_changed = roster_changed
            min_participants = tournament.teams.count() >= 2
            empty_message = (
                "Matches removed because fewer than 2 teams are registered."
            )
            generate_message = "Generated {count} matches from the registered teams."
            regenerate_message = "Regenerated {count} matches."
        else:
            new_player_ids = set(tournament.players.values_list("pk", flat=True))
            participants_changed = self._old_player_ids != new_player_ids
            min_participants = tournament.players.count() >= 2
            empty_message = (
                "Matches removed because fewer than 2 players are selected."
            )
            generate_message = "Generated {count} matches from the selected players."
            regenerate_message = "Regenerated {count} matches."

        if not participants_changed and not schedule_fields_changed:
            match_count = generate_tournament_matches(tournament)
            if match_count:
                self.message_user(
                    request,
                    generate_message.format(count=match_count),
                    messages.SUCCESS,
                )
            return

        if not min_participants:
            if tournament.matches.exists():
                tournament.matches.all().delete()
                tournament.rounds = 0
                tournament.save(update_fields=["rounds"])
                self.message_user(request, empty_message, messages.WARNING)
            return

        match_count = regenerate_tournament_matches(tournament)
        if match_count:
            self.message_user(
                request,
                regenerate_message.format(count=match_count),
                messages.SUCCESS,
            )

    @admin.display(description="Players")
    def player_count(self, obj):
        return obj.players.count()


@admin.register(Match)
class MatchAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    form = MatchAdminForm
    list_display = (
        "match_name",
        "match_number",
        "court_number",
        "club",
        "tournament",
        "scheduled_at",
    )
    list_filter = (MatchScheduleFilter, "tournament", "club")
    search_fields = (
        "tournament__name",
        "teams__name",
        "teams__members__username",
        "teams__members__first_name",
        "teams__members__last_name",
    )
    filter_horizontal = ("teams",)

    def get_fields(self, request, obj=None):
        fields = ("tournament", "match_number", "court_number", "scheduled_at", "teams")
        if obj is not None:
            fields = ("club", *fields)
        return self._fields_with_uuid_first(request, obj, fields)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None and "club" not in readonly:
            readonly.append("club")
        return tuple(readonly)

    def save_model(self, request, obj, form, change):
        if obj.tournament_id:
            obj.club = obj.tournament.club
        super().save_model(request, obj, form, change)

    @admin.display(description="Match", ordering="match_number")
    def match_name(self, obj):
        return str(obj)


@admin.register(Team)
class TeamAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    form = TeamAdminForm
    list_display = ("name", "club", "member_count", "match_count")
    list_filter = ("club",)
    search_fields = ("name", "uuid", "members__username")
    filter_horizontal = ("members",)

    def get_fields(self, request, obj=None):
        return self._fields_with_uuid_first(request, obj, ("club", "name", "members"))

    @admin.display(description="Members")
    def member_count(self, obj):
        return obj.members.count()

    @admin.display(description="Matches")
    def match_count(self, obj):
        return obj.matches.count()


@admin.register(Club)
class ClubAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "visibility", "location", "member_count", "team_count")
    list_filter = ("visibility",)
    search_fields = ("name", "email", "phone", "location", "uuid")
    filter_horizontal = ("members",)
    inlines = [TeamInline]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, Team) and not instance.club_id:
                instance.club = form.instance
            instance.save()
        formset.save_m2m()
        for instance in formset.deleted_objects:
            instance.delete()

    @admin.display(description="Members")
    def member_count(self, obj):
        return obj.members.count()

    @admin.display(description="Teams")
    def team_count(self, obj):
        return obj.teams.count()
