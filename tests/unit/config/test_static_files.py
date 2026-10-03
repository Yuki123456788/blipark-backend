from django.conf import settings


def test_whitenoise_serves_collected_static_files():
    security_index = settings.MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
    whitenoise_index = settings.MIDDLEWARE.index("whitenoise.middleware.WhiteNoiseMiddleware")

    assert whitenoise_index == security_index + 1
    assert settings.STATIC_URL == "/static/"
    assert (
        settings.STORAGES["staticfiles"]["BACKEND"]
        == "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )
