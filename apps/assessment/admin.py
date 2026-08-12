"""Administrator screens for the assessment configuration — RFP §6.1, §6.2.

This is where "хөгжлийн шалгуур, үнэлгээний мэдээллийг удирдах" (§2.1) and
"түвшний нэр, өнгө болон тайлбарыг администратор тохируулах" (§6.2) actually
happen. Registered on ``admin_site`` (``/udirdlaga/``), never on Django's own.

Scoping differs from the rest of the admin: these tables carry a *nullable*
kindergarten, where NULL means "shared by everyone". ``TenantScopedAdmin``
would filter those rows away, so the queryset below adds them back — a
director must see the system list to know what they are extending, and the
service refuses to let them edit it.
"""

from django.contrib import admin
from django.db.models import Q

from apps.accounts.models import Role
from apps.core.admin import ServiceBackedAdmin, TenantScopedAdmin
from apps.core.admin_site import admin_site

from . import services
from .models import (
    AssessmentLevel,
    AssessmentScale,
    DevelopmentDomain,
    DevelopmentIndicator,
    Term,
    TermReport,
)


class SharedConfigAdmin(ServiceBackedAdmin):
    """Own rows plus the read-only system defaults."""

    def _is_superadmin(self, request) -> bool:
        return request.user.memberships.filter(
            is_active=True, role=Role.SUPERADMIN
        ).exists()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self._is_superadmin(request):
            return qs
        return qs.filter(
            Q(kindergarten__isnull=True)
            | Q(kindergarten_id__in=request.user.kindergarten_ids)
        )

    def has_change_permission(self, request, obj=None) -> bool:
        """A director may not rename the shared list — it belongs to everyone.

        The service enforces this too; doing it here as well means the form
        is read-only rather than raising after the user has typed.
        """
        if obj is not None and obj.kindergarten_id is None:
            return self._is_superadmin(request)
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj is not None and obj.kindergarten_id is None:
            return self._is_superadmin(request)
        return super().has_delete_permission(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "kindergarten" and not self._is_superadmin(request):
            kwargs["queryset"] = db_field.related_model.objects.filter(
                id__in=request.user.kindergarten_ids
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        services.save_config(
            actor=request.user, obj=obj, created=not change, request=request
        )


@admin.register(DevelopmentDomain, site=admin_site)
class DevelopmentDomainAdmin(SharedConfigAdmin):
    """RFP §6.1."""

    list_display = ("name", "code", "kindergarten", "color", "order", "is_active")
    list_filter = ("is_active", "kindergarten")
    search_fields = ("name", "code")
    ordering = ("order", "name")
    list_select_related = ("kindergarten",)

    fieldsets = (
        (None, {"fields": ("kindergarten", "name", "code", "order", "is_active")}),
        ("Харагдац", {"fields": ("color", "description")}),
    )


class AssessmentLevelInline(admin.TabularInline):
    """§6.2 — the levels are edited alongside their scale, never alone."""

    model = AssessmentLevel
    extra = 0
    fields = ("value", "label", "color", "description")
    ordering = ("value",)
    verbose_name = "түвшин"
    verbose_name_plural = "түвшнүүд"


@admin.register(AssessmentScale, site=admin_site)
class AssessmentScaleAdmin(SharedConfigAdmin):
    """RFP §6.2."""

    list_display = ("name", "kindergarten", "is_default", "level_count")
    list_filter = ("is_default", "kindergarten")
    search_fields = ("name",)
    inlines = [AssessmentLevelInline]
    list_select_related = ("kindergarten",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("levels")

    @admin.display(description="Түвшний тоо")
    def level_count(self, obj) -> int:
        return len(obj.levels.all())

    def save_formset(self, request, form, formset, change):
        """Levels belong to the scale, so they inherit its permission check."""
        if formset.model is not AssessmentLevel:
            return super().save_formset(request, form, formset, change)

        from apps.core import services as core_services

        for obj in formset.deleted_objects:
            core_services.soft_delete(actor=request.user, obj=obj,
                                      request=request)
        for obj in formset.save(commit=False):
            obj.scale = form.instance
            core_services.save_record(actor=request.user, obj=obj,
                                      created=obj.pk is None, request=request)
        formset.save_m2m()


@admin.register(DevelopmentIndicator, site=admin_site)
class DevelopmentIndicatorAdmin(ServiceBackedAdmin):
    """Unused in Phase 1 — registered so the table is not invisible."""

    list_display = ("name", "domain", "age_from", "age_to", "order", "is_active")
    list_filter = ("is_active", "domain")
    search_fields = ("name",)
    list_select_related = ("domain",)


@admin.register(Term, site=admin_site)
class TermAdmin(TenantScopedAdmin):
    """RFP §6.4 — the four terms of a school year.

    ``kindergarten`` is set from the school year by the service, so the form
    does not offer it: an administrator picking a mismatched pair would put
    the row in the wrong tenant.
    """

    list_display = ("name", "school_year", "number", "starts_on", "ends_on")
    list_filter = ("school_year",)
    ordering = ("school_year", "number")
    list_select_related = ("school_year", "kindergarten")
    exclude = ("kindergarten",)

    def save_model(self, request, obj, form, change):
        services.save_term(
            actor=request.user, obj=obj, created=not change, request=request
        )


@admin.register(TermReport, site=admin_site)
class TermReportAdmin(TenantScopedAdmin):
    """RFP §6.4. Read-mostly: the narrative is written on the teacher's
    screen, and this exists so an administrator can find and archive one.

    ``ServiceBackedAdmin`` routes save and delete through the services, so
    an admin action still writes an audit row and still soft-deletes
    (CLAUDE.md §2.4, §3.3).
    """

    list_display = ("child", "term", "status", "author", "finalized_at")
    list_filter = ("status", "term")
    search_fields = ("child__last_name", "child__first_name")
    list_select_related = ("child", "term", "author")
    exclude = ("kindergarten",)
