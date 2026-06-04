import uuid

from django.conf import settings
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
    
    scheduled_at = models.DateTimeField()

    class Meta:
        verbose_name_plural = "matches"
        ordering = ["tournament", "match_number"]

    def __str__(self):
        return f"Match {self.match_number} ({self.tournament.name})"


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


class Club(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    name = models.CharField(max_length=200)
    
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="clubs",
        blank=True,
    )

    class Meta:
        ordering = ["name"]

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
