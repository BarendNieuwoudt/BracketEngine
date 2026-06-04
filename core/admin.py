from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import get_user_model

from .models import Club, Match, Profile, Team, Tournament

User = get_user_model()


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


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


class MatchInline(admin.TabularInline):
    model = Match
    extra = 0


class TeamInline(admin.TabularInline):
    model = Team
    extra = 0


@admin.register(Tournament)
class TournamentAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "uuid", "type", "sport", "courts", "rounds")
    list_filter = ("type", "sport")
    search_fields = ("name", "uuid")

    def get_inlines(self, request, obj=None):
        # Hide match inlines until the tournament is saved (add form has obj=None).
        if obj is None:
            return []
        return [MatchInline]


@admin.register(Match)
class MatchAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    list_display = ("match_number", "tournament", "scheduled_at", "uuid")
    list_filter = ("tournament",)
    inlines = [TeamInline]


@admin.register(Team)
class TeamAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "match", "member_count", "uuid")
    list_filter = ("match",)
    search_fields = ("name", "uuid")
    filter_horizontal = ("members",)

    @admin.display(description="Members")
    def member_count(self, obj):
        return obj.members.count()


@admin.register(Club)
class ClubAdmin(UUIDOnChangeOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "member_count", "uuid")
    search_fields = ("name", "uuid")
    filter_horizontal = ("members",)

    @admin.display(description="Members")
    def member_count(self, obj):
        return obj.members.count()
