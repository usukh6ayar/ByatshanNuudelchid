from django.urls import path

from . import views

app_name = "assessment"

urlpatterns = [
    # Shared: the child's own assessment record, read by both roles.
    path("hawtas/<int:child_id>/unelgee/", views.child_assessment,
         name="child"),
    path("hawtas/<int:child_id>/unelgee/hadgalah/",
         views.child_assessment_save, name="child_save"),
    path("hawtas/<int:child_id>/unelgee/niitleh/", views.publish,
         name="publish"),

    # Teacher only — RFP §6.3's quick assessment of a whole group.
    path("bagsh/bulge/<int:group_id>/turgen-unelgee/", views.group_grid,
         name="group_grid"),
]
