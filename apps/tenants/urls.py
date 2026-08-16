from django.urls import path

from . import views

app_name = "tenants"

# Administrator only — RFP §2.1. Under /udirdlaga/ so the URL matches the
# sidebar the director already reads, but these are the project's own views,
# not the Django admin site mounted beside them.
urlpatterns = [
    path("udirdlaga/tsetserleg/", views.kindergarten_list,
         name="kindergarten_list"),
    path("udirdlaga/tsetserleg/shine/", views.kindergarten_form,
         name="kindergarten_create"),
    path("udirdlaga/tsetserleg/<int:kindergarten_id>/", views.kindergarten_form,
         name="kindergarten_edit"),

    path("udirdlaga/bulguud/", views.group_list, name="group_list"),
    path("udirdlaga/bulguud/shine/", views.group_form, name="group_create"),
    path("udirdlaga/bulguud/<int:group_id>/", views.group_form,
         name="group_edit"),
]
