from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    # Teacher only — нэмэлт.md §1. Under /bagsh/bulge/ beside the assessment
    # grid, because it is the same shape of screen: one group, one day, every
    # child at once.
    path("bagsh/bulge/<int:group_id>/irts/", views.group_register,
         name="group_register"),
]
