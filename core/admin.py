from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .forms import TournamentAdminForm
from .match_generation import generate_tournament_matches, regenerate_tournament_matches
from .models import Club, Match, Profile, Team, Tournament
User = get_user_model()

admin.site.site_header = "BracketEngine - Tournament Management System"
admin.site.site_title = "BracketEngine"
admin.site.index_title = "Tournament management"


class UUIDOnChangeOnlyMixin:
    """Show uuid as read-only only after the object has been saved."""

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is None:
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


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.unregister(Group)


class MatchInline(admin.TabularInline):
    model = Match
    extra = 0


class TeamInline(admin.TabularInline):
    model = Team
    extra = 0


@admin.register(Tournament)
class TournamentAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    form = TournamentAdminForm
    list_display = ("name", "club", "type", "sport", "courts", "rounds", "player_count")
    list_filter = ("type", "sport", "club")
    search_fields = ("name", "uuid")
    filter_horizontal = ("players",)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("name", "club", "type", "sport", "courts", "rounds")
        return ("uuid", "name", "club", "type", "sport", "courts", "rounds", "players")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            for field in ("club", "sport", "type"):
                if field not in readonly:
                    readonly.append(field)
        return tuple(readonly)

    def get_inlines(self, request, obj=None):
        if obj is None or not obj.players.exists():
            return []
        return [MatchInline]

    def save_model(self, request, obj, form, change):
        if change and obj.pk:
            previous = Tournament.objects.get(pk=obj.pk)
            self._old_player_ids = set(
                previous.players.values_list("pk", flat=True)
            )
            self._schedule_fields_changed = (
                previous.courts != obj.courts or previous.rounds != obj.rounds
            )
        else:
            self._old_player_ids = set()
            self._schedule_fields_changed = False
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if not change:
            return

        tournament = form.instance
        new_player_ids = set(tournament.players.values_list("pk", flat=True))
        players_changed = self._old_player_ids != new_player_ids
        schedule_fields_changed = self._schedule_fields_changed

        if not players_changed and not schedule_fields_changed:
            match_count = generate_tournament_matches(tournament)
            if match_count:
                self.message_user(
                    request,
                    f"Generated {match_count} matches from the selected players.",
                    messages.SUCCESS,
                )
            return

        if tournament.players.count() < 2:
            if tournament.matches.exists():
                tournament.matches.all().delete()
                self.message_user(
                    request,
                    "Matches removed because fewer than 2 players are selected.",
                    messages.WARNING,
                )
            return

        match_count = regenerate_tournament_matches(tournament)
        if match_count:
            self.message_user(
                request,
                f"Regenerated {match_count} matches.",
                messages.SUCCESS,
            )

    @admin.display(description="Players")
    def player_count(self, obj):
        return obj.players.count()


@admin.register(Match)
class MatchAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    list_display = ("match_name", "match_number", "court_number", "tournament", "scheduled_at")
    list_filter = ("tournament",)
    search_fields = (
        "tournament__name",
        "teams__name",
        "teams__members__username",
        "teams__members__first_name",
        "teams__members__last_name",
    )
    inlines = [TeamInline]

    @admin.display(description="Match", ordering="match_number")
    def match_name(self, obj):
        return str(obj)


@admin.register(Team)
class TeamAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "tournament_name", "match", "member_count")
    list_filter = ("match__tournament",)
    search_fields = ("name", "uuid")
    filter_horizontal = ("members",)

    @admin.display(description="Tournament", ordering="match__tournament__name")
    def tournament_name(self, obj):
        return obj.match.tournament.name

    @admin.display(description="Members")
    def member_count(self, obj):
        return obj.members.count()


@admin.register(Club)
class ClubAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "visibility", "location", "member_count")
    list_filter = ("visibility",)
    search_fields = ("name", "email", "phone", "location", "uuid")
    filter_horizontal = ("members",)

    @admin.display(description="Members")
    def member_count(self, obj):
        return obj.members.count()
