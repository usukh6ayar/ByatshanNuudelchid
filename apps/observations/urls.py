from django.urls import path

from . import views

app_name = "observations"

# Shared between the two roles for the same reason the portfolio is
# (``apps/portfolio/urls.py``): one artifact, one set of rules. A guardian
# reads here and, from Day 7, submits their own; the permission layer
# decides which, not the URL prefix.
urlpatterns = [
    path("hawtas/<int:child_id>/ajiglalt/", views.observation_list,
         name="list"),
    path("hawtas/<int:child_id>/ajiglalt/shine/", views.observation_create,
         name="create"),
    # §5.4 — the guardian's own submission, and the teacher's queue for them.
    path("hawtas/<int:child_id>/ajiglalt/minii/",
         views.parent_observation_create, name="parent_create"),
    path("bagsh/ajiglalt/hyanah/", views.review_queue, name="review_queue"),
    path("hawtas/<int:child_id>/ajiglalt/<int:observation_id>/",
         views.observation_detail, name="detail"),
    path("hawtas/<int:child_id>/ajiglalt/<int:observation_id>/zasah/",
         views.observation_edit, name="edit"),
    path("hawtas/<int:child_id>/ajiglalt/<int:observation_id>/arhivlah/",
         views.observation_delete, name="delete"),
    path("hawtas/<int:child_id>/ajiglalt/<int:observation_id>/hyanah/",
         views.observation_review, name="review"),
]
