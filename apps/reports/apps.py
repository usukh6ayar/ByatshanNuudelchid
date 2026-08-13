"""App configuration for ``apps.reports``.

``verbose_name`` is what the administrator sees as a section heading at
/udirdlaga/. Without it Django titles the section from the module name, so a
kindergarten director reads "Reports" — RFP §611 asks for Mongolian
everywhere a user looks, and the admin is a screen they use.
"""

from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reports"
    verbose_name = "Тайлан, PDF"
