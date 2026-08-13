from django.urls import path

from . import views

app_name = "assessment"

urlpatterns = [
    # Shared: the child's own assessment record, read by both roles.
    path("hawtas/<int:child_id>/unelgee/", views.child_assessment,
         name="child"),
    path("hawtas/<int:child_id>/unelgee/hadgalah/",
         views.child_assessment_save, name="child_save"),
    # RFP §6.4's narrative report. Finalizing it is also what opens the
    # term's assessments to the guardians, so there is no separate publish
    # route: two ways to publish the same term is how the two drift apart.
    path("hawtas/<int:child_id>/unelgee/tailan/<int:term_id>/",
         views.term_report, name="term_report"),

    # Teacher only — RFP §6.3's quick assessment of a whole group.
    path("bagsh/bulge/<int:group_id>/turgen-unelgee/", views.group_grid,
         name="group_grid"),
]
