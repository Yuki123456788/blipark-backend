from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-only-not-a-real-secret"
ALLOWED_HOSTS = ["testserver"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Unit and HTTP contract tests must not require a running PostGIS service.
# GIS model and spatial-query tests will use a dedicated PostGIS integration-test setup.
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "django.contrib.gis"]  # noqa: F405
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
