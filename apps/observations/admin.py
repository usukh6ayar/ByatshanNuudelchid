"""Administrator screen for observation types — RFP §5.2.

"Ажиглалтын төрлийг администратор тохируулж нэмэх боломжтой байвал давуу
тал болно." Same nullable-kindergarten shape as the assessment
configuration, so it reuses that admin's scoping.
"""

from django.contrib import admin

from apps.assessment.admin import SharedConfigAdmin
from apps.assessment.services import save_config
from apps.core.admin_site import admin_site

from .models import ObservationType


@admin.register(ObservationType, site=admin_site)
class ObservationTypeAdmin(SharedConfigAdmin):
    list_display = ("name", "code", "kindergarten", "order", "is_active")
    list_filter = ("is_active", "kindergarten")
    search_fields = ("name", "code")
    ordering = ("order", "name")
    list_select_related = ("kindergarten",)

    def save_model(self, request, obj, form, change):
        save_config(
            actor=request.user, obj=obj, created=not change, request=request
        )
