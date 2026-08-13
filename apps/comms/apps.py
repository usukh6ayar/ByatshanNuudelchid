"""App configuration for ``apps.comms``.

``verbose_name`` is what the administrator sees as a section heading at
/udirdlaga/. Without it Django titles the section from the module name, so a
kindergarten director reads "Comms" — RFP §611 asks for Mongolian
everywhere a user looks, and the admin is a screen they use.
"""

from django.apps import AppConfig


class CommsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.comms"
    verbose_name = "Мэдэгдэл"
