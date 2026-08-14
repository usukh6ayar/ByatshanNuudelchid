from django.urls import path

from . import admin_views, views

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

    # Administrator configuration — RFP §6.1, §6.4. Under /udirdlaga/ to
    # match the sidebar; included before the admin site in config/urls.py.
    path("udirdlaga/uliral/", admin_views.term_list, name="admin_term_list"),
    path("udirdlaga/uliral/uusgeh/", admin_views.term_create_defaults,
         name="admin_term_defaults"),
    path("udirdlaga/uliral/<int:term_id>/", admin_views.term_edit,
         name="admin_term_edit"),

    path("udirdlaga/chiglel/", admin_views.domain_list,
         name="admin_domain_list"),
    path("udirdlaga/chiglel/shine/", admin_views.domain_form,
         name="admin_domain_create"),
    path("udirdlaga/chiglel/<int:domain_id>/", admin_views.domain_form,
         name="admin_domain_edit"),
]
