import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
class TournamentType(models.TextChoices):
    AMERICANO = "americano", "Americano"
    ROUND_ROBIN = "round-robin", "Round Robin"
    SINGLE_ELIMINATION = "single-elimination", "Single Elimination"


class Sport(models.TextChoices):
    PADEL = "padel", "Padel"


class Tournament(models.Model):

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        null=False,
        blank=False,
    )

    name = models.CharField(
        max_length=200,
        default="My Tournament",
        null=False,
        blank=False,
    )

    type = models.CharField(
        max_length=32,
        choices=TournamentType.choices,
        null=False,
        blank=False,
    )

    sport = models.CharField(
        max_length=32,
        choices=Sport.choices,
        null=False,
        blank=False,
    )

    courts = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        null=False,
        blank=False,
    )

    rounds = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        null=False,
        blank=False,
        help_text=(
            "Leave as 0 for no maximum number of rounds."
        ),
    )

    club = models.ForeignKey(
        "Club",
        on_delete=models.SET_NULL,
        related_name="tournaments",
        null=True,
        blank=True,
    )

    players = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="tournaments",
        blank=True,
        help_text="Selected after the tournament is created. Used to generate matches.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Match(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.CASCADE,
        related_name="matches",
    )
    
    match_number = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    court_number = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    scheduled_at = models.DateTimeField()

    class Meta:
        verbose_name_plural = "matches"
        ordering = ["tournament", "match_number"]

    def __str__(self):
        team_names = list(self.teams.order_by("pk").values_list("name", flat=True))
        if len(team_names) >= 2:
            return f"{team_names[0]} vs {team_names[1]}"
        if len(team_names) == 1:
            return f"{team_names[0]} vs TBD"
        return f"Match {self.match_number}"


class Team(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    match = models.ForeignKey(
        Match,
        on_delete=models.CASCADE,
        related_name="teams",
    )
    
    name = models.CharField(max_length=200)
    
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="teams",
        blank=True,
    )

    class Meta:
        ordering = ["match", "name"]

    def __str__(self):
        return self.name


class ClubVisibility(models.TextChoices):
    PRIVATE = "private", "Private"
    PUBLIC = "public", "Public"


class Club(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    name = models.CharField(max_length=200)
    
    visibility = models.CharField(
        max_length=16,
        choices=ClubVisibility.choices,
        default=ClubVisibility.PUBLIC,
        help_text=(
            "Public clubs can be joined by users (coming soon). "
            "Private clubs are invite-only."
        ),
    )

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    location = models.CharField(
        max_length=100,
        blank=True,
        help_text='Optional. Town or city, e.g. "Cape Town" or "Durbanville".',
    )

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="clubs",
        blank=True,
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(email="", phone=""),
                name="club_requires_email_or_phone",
            ),
        ]

    def clean(self):
        super().clean()
        email = (self.email or "").strip()
        phone = (self.phone or "").strip()
        if not email and not phone:
            raise ValidationError(
                "Provide at least one contact method: email or phone number."
            )

    def __str__(self):
        return self.name


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    nickname = models.CharField(max_length=100, blank=True)

    def __str__(self):
        if self.nickname:
            return f"{self.user} ({self.nickname})"
        return str(self.user)
