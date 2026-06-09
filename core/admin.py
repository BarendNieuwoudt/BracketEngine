from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from .forms import TeamAdminForm, TeamInlineForm, TournamentAdminForm
from .match_generation import generate_tournament_matches, regenerate_tournament_matches
from .models import Club, Match, Profile, Team, Tournament
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
    form = TeamInlineForm
    extra = 0


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
    filter_horizontal = ("players",)

    def get_fields(self, request, obj=None):
        scheduling = ("starts_at", "game_duration", "break_duration")
        if obj is None:
            return ("name", "club", "type", "sport", *scheduling, "courts", "rounds")
        return self._fields_with_uuid_first(
            request,
            obj,
            (
                "name",
                "club",
                "type",
                "sport",
                *scheduling,
                "courts",
                "rounds",
                "players",
            ),
        )

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
                previous.courts != obj.courts
                or previous.rounds != obj.rounds
                or previous.starts_at != obj.starts_at
                or previous.game_duration != obj.game_duration
                or previous.break_duration != obj.break_duration
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
                tournament.rounds = 0
                tournament.save(update_fields=["rounds"])
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
    inlines = [TeamInline]

    def get_fields(self, request, obj=None):
        fields = ("tournament", "match_number", "court_number", "scheduled_at")
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

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, Team):
                instance.club = form.instance.club or form.instance.tournament.club
            instance.save()
        formset.save_m2m()
        for instance in formset.deleted_objects:
            instance.delete()

    @admin.display(description="Match", ordering="match_number")
    def match_name(self, obj):
        return str(obj)


@admin.register(Team)
class TeamAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    form = TeamAdminForm
    list_display = ("name", "club", "tournament_name", "match", "member_count")
    list_filter = ("club", "match__tournament")
    search_fields = ("name", "uuid")
    filter_horizontal = ("members",)

    def get_fields(self, request, obj=None):
        fields = ("match", "name", "members")
        if obj is not None:
            fields = ("club", *fields)
        return self._fields_with_uuid_first(request, obj, fields)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None and "club" not in readonly:
            readonly.append("club")
        return tuple(readonly)

    def save_model(self, request, obj, form, change):
        if obj.match_id:
            obj.club = obj.match.club or obj.match.tournament.club
        super().save_model(request, obj, form, change)

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
