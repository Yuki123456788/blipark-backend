from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False

if not SECRET_KEY or SECRET_KEY.startswith("replace-me"):  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production.")

if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")

if not DATABASES["default"]["PASSWORD"] or DATABASES["default"]["PASSWORD"].startswith(  # noqa: F405
    "replace-me"
):
    raise ImproperlyConfigured("POSTGRES_PASSWORD must be set in production.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
