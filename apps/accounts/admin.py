"""Admin screens for users and memberships — RFP §2.1, §3.3."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.core.admin import ServiceBackedAdmin, TenantScopedAdmin
from apps.core.admin_site import admin_site

from .models import (
    GuardianProfile,
    Membership,
    Role,
    TeacherProfile,
    User,
)


class MembershipInline(admin.TabularInline):
    model = Membership
    fk_name = "user"
    extra = 0
    fields = ("kindergarten", "role", "is_active", "started_on")
    verbose_name = "эрх"
    verbose_name_plural = "эрхүүд"


class TeacherProfileInline(admin.StackedInline):
    model = TeacherProfile
    # BaseModel adds created_by / updated_by / deleted_by, so there are four
    # FKs to User and Django cannot pick one on its own.
    fk_name = "user"
    extra = 0
    can_delete = False
    verbose_name_plural = "багшийн профайл"


@admin.register(User, site=admin_site)
class UserAdmin(ServiceBackedAdmin):
    """RFP §3.1 — three identifier types on one account.

    Deliberately not Django's ``UserAdmin``: that one is built around a single
    ``username`` and around ``is_staff`` / ``is_superuser`` checkboxes, which
    here would hand out access to ``/django-admin/`` as a side effect of
    creating a teacher.
    """

    list_display = ("__str__", "username", "email", "phone",
                    "role_summary", "is_active", "last_login_at")
    list_filter = ("is_active", "memberships__role", "memberships__kindergarten")
    search_fields = ("username", "email", "phone", "last_name", "first_name")
    ordering = ("last_name", "first_name")
    inlines = [MembershipInline, TeacherProfileInline]

    fieldsets = (
        ("Нэвтрэх мэдээлэл", {
            "fields": ("username", "email", "phone"),
            "description": "Дор хаяж нэгийг бөглөнө. Гурвуулаа давхцахгүй байна.",
        }),
        ("Хувийн мэдээлэл", {"fields": ("last_name", "first_name")}),
        ("Төлөв", {"fields": ("is_active",)}),
    )

    def get_queryset(self, request):
        # CLAUDE.md §3.5 — role_summary reads memberships for every row.
        return super().get_queryset(request).prefetch_related(
            "memberships__kindergarten"
        )

    @admin.display(description="Эрх")
    def role_summary(self, obj) -> str:
        parts = [
            f"{m.get_role_display()}"
            + (f" ({m.kindergarten.name})" if m.kindergarten else "")
            for m in obj.memberships.all() if m.is_active
        ]
        return ", ".join(parts) or "—"

    def get_readonly_fields(self, request, obj=None):
        """Only a superadmin may reach Django's own permission flags.

        They are not exposed in ``fieldsets`` at all; this is the second lock.
        """
        base = super().get_readonly_fields(request, obj)
        return (*base, "last_login_at", "date_joined")

    def has_change_password_permission(self, request, obj=None) -> bool:
        """RFP §2.1 — an administrator may reset a password when necessary."""
        return True


@admin.register(Membership, site=admin_site)
class MembershipAdmin(TenantScopedAdmin):
    """Registered separately so ``autocomplete_fields`` can target it."""

    list_display = ("user", "kindergarten", "role", "is_active", "started_on")
    list_filter = ("role", "is_active", "kindergarten")
    search_fields = ("user__last_name", "user__first_name", "user__username",
                     "user__email", "user__phone")
    list_select_related = ("user", "kindergarten")
    autocomplete_fields = ("user",)

    def get_queryset(self, request):
        """A superadmin membership has no kindergarten, so the base filter
        on ``kindergarten__in`` would hide it from the person who holds it.
        """
        qs = admin.ModelAdmin.get_queryset(self, request)
        if self._is_superadmin(request):
            return qs.select_related("user", "kindergarten")
        return qs.filter(
            kindergarten__in=request.user.kindergarten_ids
        ).select_related("user", "kindergarten")

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        """A director must not be able to mint a superadmin — RFP §2.1."""
        if db_field.name == "role" and not self._is_superadmin(request):
            kwargs["choices"] = [
                choice for choice in db_field.choices
                if choice[0] != Role.SUPERADMIN
            ]
        return super().formfield_for_choice_field(db_field, request, **kwargs)


@admin.register(GuardianProfile, site=admin_site)
class GuardianProfileAdmin(ServiceBackedAdmin):
    list_display = ("user",)
    search_fields = ("user__last_name", "user__first_name", "user__phone")
    autocomplete_fields = ("user",)


# Django's own site keeps its stock user admin for superusers only:
# emergency access when the product screens cannot be reached.
admin.site.register(User, DjangoUserAdmin)
admin.site.register(Membership)
