"""Admin screens for organizational data — RFP §2.1.

Registered on ``admin_site`` (``/udirdlaga/``), not on Django's default site.
"""

from django.contrib import admin
from django.db.models import Count

from apps.accounts.models import Role
from apps.core import services as core_services
from apps.core.admin import ServiceBackedAdmin, TenantScopedAdmin
from apps.core.admin_site import admin_site

from . import services
from .models import Group, GroupTeacher, Kindergarten, SchoolYear


class SchoolYearInline(admin.TabularInline):
    model = SchoolYear
    extra = 0
    fields = ("name", "starts_on", "ends_on", "is_current")


@admin.register(Kindergarten, site=admin_site)
class KindergartenAdmin(ServiceBackedAdmin):
    list_display = ("name", "phone", "email", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "address", "phone", "email")
    inlines = [SchoolYearInline]

    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        ("Холбоо барих", {"fields": ("address", "phone", "email")}),
        ("Танилцуулга", {"fields": ("description",)}),
    )

    def save_model(self, request, obj, form, change):
        services.save_kindergarten(
            actor=request.user, obj=obj, created=not change, request=request
        )

    def _is_superadmin(self, request) -> bool:
        return request.user.memberships.filter(
            is_active=True, role=Role.SUPERADMIN
        ).exists()

    def get_queryset(self, request):
        """A director sees only their own kindergarten — RFP §3.2."""
        qs = super().get_queryset(request)
        if self._is_superadmin(request):
            return qs
        return qs.filter(id__in=request.user.kindergarten_ids)

    def has_add_permission(self, request) -> bool:
        """Only a superadmin registers a kindergarten — RFP §2.1."""
        return self._is_superadmin(request)


@admin.register(SchoolYear, site=admin_site)
class SchoolYearAdmin(TenantScopedAdmin):
    list_display = ("name", "kindergarten", "starts_on", "ends_on", "is_current")
    list_filter = ("is_current", "kindergarten")
    search_fields = ("name",)
    ordering = ("-starts_on",)
    list_select_related = ("kindergarten",)

    def save_model(self, request, obj, form, change):
        services.save_school_year(
            actor=request.user, obj=obj, created=not change, request=request
        )


class GroupTeacherInline(admin.TabularInline):
    model = GroupTeacher
    extra = 0
    fields = ("teacher_membership", "role", "started_on", "ended_on")
    autocomplete_fields = ("teacher_membership",)
    verbose_name = "хариуцсан багш"
    verbose_name_plural = "хариуцсан багш нар"


@admin.register(Group, site=admin_site)
class GroupAdmin(TenantScopedAdmin):
    list_display = ("name", "school_year", "age_category", "teacher_names",
                    "child_count", "status")
    list_filter = ("status", "school_year", "kindergarten")
    search_fields = ("name", "age_category")
    inlines = [GroupTeacherInline]

    fieldsets = (
        (None, {"fields": ("kindergarten", "school_year", "name",
                           "age_category", "status")}),
        ("Дэлгэрэнгүй", {"fields": ("timetable", "rules")}),
    )

    def get_queryset(self, request):
        # CLAUDE.md §3.5 — the list shows teachers and a child count, so
        # without these two the page issues a query per row.
        return (
            super()
            .get_queryset(request)
            .select_related("school_year", "kindergarten")
            .prefetch_related("teacher_assignments__teacher_membership__user")
            .annotate(_child_count=Count("enrollments"))
        )

    @admin.display(description="Хариуцсан багш")
    def teacher_names(self, obj) -> str:
        names = [str(a.teacher_membership.user)
                 for a in obj.teacher_assignments.all()]
        return ", ".join(names) or "—"

    @admin.display(description="Хүүхдийн тоо", ordering="_child_count")
    def child_count(self, obj) -> int:
        return obj._child_count

    def save_model(self, request, obj, form, change):
        services.save_group(
            actor=request.user, obj=obj, created=not change, request=request
        )

    def save_formset(self, request, form, formset, change):
        """Teacher assignments must go through the service.

        The inline form has no ``kindergarten`` field — the base
        ``save_formset`` would fail on the not-null column — and, more
        importantly, assigning a teacher is an authorization change that has
        to be validated and audited.
        """
        if formset.model is not GroupTeacher:
            return super().save_formset(request, form, formset, change)

        for obj in formset.deleted_objects:
            core_services.soft_delete(actor=request.user, obj=obj, request=request)

        for obj in formset.save(commit=False):
            obj.group = form.instance
            services.save_group_teacher(
                actor=request.user, obj=obj, created=obj.pk is None, request=request
            )
        formset.save_m2m()


@admin.register(GroupTeacher, site=admin_site)
class GroupTeacherAdmin(TenantScopedAdmin):
    list_display = ("teacher_membership", "group", "role", "started_on", "ended_on")
    list_filter = ("role", "kindergarten")
    autocomplete_fields = ("teacher_membership",)
    list_select_related = ("group", "teacher_membership__user")

    def save_model(self, request, obj, form, change):
        services.save_group_teacher(
            actor=request.user, obj=obj, created=not change, request=request
        )
