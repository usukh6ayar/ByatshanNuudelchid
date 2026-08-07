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

# HTTPS is not available locally; cookies must not require it.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
