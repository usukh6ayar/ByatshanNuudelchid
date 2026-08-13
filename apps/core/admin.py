"""Base admin classes — CLAUDE.md §2.4.

Django Admin writes to the database directly. Left alone it would skip the
audit log (RFP §15) and hard-delete rows (RFP §3.4). Every ModelAdmin in this
project therefore inherits from here.
"""

from django.contrib import admin

from apps.accounts.models import Role
from apps.core import services


class ServiceBackedAdmin(admin.ModelAdmin):
    """Routes every write through ``services`` — CLAUDE.md §2.4."""

    # ---------------------------------------------------------- permissions
    # Django Admin normally asks ``user.has_perm("app.change_model")``. This
    # project keeps authorization in ``Membership`` (spec section 4.1), so a
    # director with no Django permission rows would otherwise reach the site
    # and find every section empty. Deferring to the admin site's own check
    # keeps one source of truth rather than mirroring roles into
    # ``auth.Permission``.

    def has_module_permission(self, request) -> bool:
        return self.admin_site.has_permission(request)

    def has_view_permission(self, request, obj=None) -> bool:
        return self.admin_site.has_permission(request)

    def has_add_permission(self, request) -> bool:
        return self.admin_site.has_permission(request)

    def has_change_permission(self, request, obj=None) -> bool:
        return self.admin_site.has_permission(request)

    def has_delete_permission(self, request, obj=None) -> bool:
        return self.admin_site.has_permission(request)

    # Object-level scoping is handled by ``get_queryset``: Django looks the
    # object up through it, so anything outside the user's kindergartens
    # returns 404 rather than 403 — RFP §21.4.

    # ---------------------------------------------------------- writes

    def save_model(self, request, obj, form, change):
        services.save_record(
            actor=request.user, obj=obj, created=not change, request=request
        )

    def delete_model(self, request, obj):
        services.soft_delete(actor=request.user, obj=obj, request=request)

    def delete_queryset(self, request, queryset):
        # The bulk action bypasses delete_model, so it needs its own override
        # or "delete selected" would hard-delete everything.
        for obj in queryset:
            services.soft_delete(actor=request.user, obj=obj, request=request)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            services.soft_delete(actor=request.user, obj=obj, request=request)
        for obj in instances:
            services.save_record(
                actor=request.user, obj=obj, created=obj.pk is None, request=request
            )
        formset.save_m2m()


class TenantScopedAdmin(ServiceBackedAdmin):
    """Restricts every list to the kindergartens the user belongs to.

    RFP §3.2 and §21.4: the director of one kindergarten must not see, edit
    or even enumerate another's records. Filtering here rather than in each
    subclass means a new model cannot forget it.

    Subclasses set ``kindergarten_lookup`` when the field is reached through
    a relation (e.g. ``"group__kindergarten"``).
    """

    kindergarten_lookup = "kindergarten"

    def _is_superadmin(self, request) -> bool:
        return request.user.memberships.filter(
            is_active=True, role=Role.SUPERADMIN
        ).exists()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self._is_superadmin(request):
            return qs
        return qs.filter(
            **{f"{self.kindergarten_lookup}__in": request.user.kindergarten_ids}
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Keep other kindergartens out of the dropdowns too.

        Without this the list is scoped but a director could still attach a
        group to another kindergarten by picking it from a select box.
        """
        if not self._is_superadmin(request):
            ids = request.user.kindergarten_ids
            if db_field.name == "kindergarten":
                kwargs["queryset"] = db_field.related_model.objects.filter(id__in=ids)
            elif db_field.name in {"school_year", "group"}:
                kwargs["queryset"] = db_field.related_model.objects.filter(
                    kindergarten_id__in=ids
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
