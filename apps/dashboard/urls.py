from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("bagsh/", views.teacher_dashboard, name="teacher"),
    # Not under /udirdlaga/: that prefix is the admin site's, and it would
    # swallow this path before the include ever ran.
    path("hyanalt/", views.admin_dashboard, name="admin"),
]
