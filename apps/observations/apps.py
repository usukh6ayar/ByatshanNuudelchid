"""App configuration for ``apps.observations``.

``verbose_name`` is what the administrator sees as a section heading at
/udirdlaga/. Without it Django titles the section from the module name, so a
kindergarten director reads "Observations" — RFP §611 asks for Mongolian
everywhere a user looks, and the admin is a screen they use.
"""

from django.apps import AppConfig


class ObservationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.observations"
    verbose_name = "Багшийн ажиглалт"
