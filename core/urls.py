from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.PlayerLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("clubs/<uuid:uuid>/", views.club_detail, name="club_detail"),
    path("tournaments/<uuid:uuid>/", views.tournament_detail, name="tournament_detail"),
    path("matches/<uuid:uuid>/", views.match_detail, name="match_detail"),
    path("profile/", views.profile, name="profile"),
]
