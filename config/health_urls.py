from django.urls import path

from config.health_views import live, ready

urlpatterns = [
    path("live", live, name="health-live"),
    path("ready", ready, name="health-ready"),
]
