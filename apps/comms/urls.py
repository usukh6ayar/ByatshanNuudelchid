from django.urls import path

from . import views

app_name = "comms"

# One zone, both roles — RFP §8.1 is a single artifact a teacher writes and a
# family reads. The selector decides which announcements each one sees, so
# the URL does not have to.
urlpatterns = [
    path("medegdel/", views.announcement_list, name="list"),
    path("medegdel/shine/", views.announcement_form, name="create"),
    path("medegdel/<int:announcement_id>/", views.announcement_detail,
         name="detail"),
    path("medegdel/<int:announcement_id>/zasah/", views.announcement_form,
         name="edit"),
    path("medegdel/<int:announcement_id>/niitleh/",
         views.announcement_publish, name="publish"),
    path("medegdel/<int:announcement_id>/arhivlah/",
         views.announcement_delete, name="delete"),
    path("medegdel/<int:announcement_id>/unshsan/", views.mark_read,
         name="mark_read"),
]
