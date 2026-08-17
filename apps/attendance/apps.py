"""App configuration for ``apps.attendance`` — нэмэлт.md §1."""

from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.attendance"
    verbose_name = "Ирцийн бүртгэл"
