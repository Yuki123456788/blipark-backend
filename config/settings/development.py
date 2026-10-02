from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")  # noqa: F405

if not SECRET_KEY or SECRET_KEY.startswith("replace-me"):  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set. Copy .env.example to .env.")

if not DATABASES["default"]["PASSWORD"] or DATABASES["default"]["PASSWORD"].startswith(  # noqa: F405
    "replace-me"
):
    raise ImproperlyConfigured("POSTGRES_PASSWORD must be set. Copy .env.example to .env.")
