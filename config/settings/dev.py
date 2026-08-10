from .base import *  # noqa: F403

DEBUG = True

INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405

INTERNAL_IPS = ["127.0.0.1"]


def _show_toolbar(request) -> bool:
    """Read DEBUG at call time, not at import time.

    pytest-django forces ``settings.DEBUG = False`` during tests, but the URL
    conf is loaded once with DEBUG true. A callback that captured the module
    constant would keep injecting the toolbar into test responses, and its
    template would then fail on the unregistered ``djdt`` namespace.
    """
    from django.conf import settings

    return settings.DEBUG


DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": _show_toolbar}

# Object storage. Development runs the same S3 backend as production, against
# the MinIO container in docker-compose, so the signed-URL path in spec
# section 7.1 is the one actually exercised while building. A filesystem
# backend would work locally and then fail the first time production signed a
# URL — which is the failure you find on deployment day.
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("AWS_STORAGE_BUCKET_NAME",  # noqa: F405
                               default="kinder-media"),
            "endpoint_url": env("AWS_S3_ENDPOINT_URL",  # noqa: F405
                                default="http://minio:9000"),
            "region_name": env("AWS_S3_REGION_NAME", default="auto"),  # noqa: F405
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": MEDIA_SIGNED_URL_TTL,  # noqa: F405
            "file_overwrite": False,
        },
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# MinIO signs URLs for the hostname the *application* reaches it on —
# ``minio:9000``, which resolves inside the compose network and nowhere
# else. Redirecting a browser there gives an unresolvable host, so
# development streams the bytes through Django instead. The upload path,
# the bucket, the signing and the permission check are all still the real
# ones; only who moves the file differs, and production redirects.
MEDIA_REDIRECT_SIGNED_URL = False

# HTTPS is not available locally; cookies must not require it.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
