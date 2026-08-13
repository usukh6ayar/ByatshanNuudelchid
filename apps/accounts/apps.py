"""App configuration for ``apps.accounts``.

``verbose_name`` is what the administrator sees as a section heading at
/udirdlaga/. Without it Django titles the section from the module name, so a
kindergarten director reads "Accounts" — RFP §611 asks for Mongolian
everywhere a user looks, and the admin is a screen they use.
"""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Хэрэглэгч ба эрх"
