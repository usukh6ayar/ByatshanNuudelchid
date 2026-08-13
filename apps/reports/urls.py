from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("hawtas/<int:child_id>/tailan/", views.report_request, name="request"),
    path("hawtas/<int:child_id>/tailan/<int:job_id>/", views.report_status,
         name="status"),
    path("hawtas/<int:child_id>/tailan/<int:job_id>/tolov/",
         views.report_progress, name="progress"),
    path("hawtas/<int:child_id>/tailan/<int:job_id>/tatah/",
         views.report_download, name="download"),
]
