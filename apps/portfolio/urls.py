from django.urls import path

from . import views

app_name = "portfolio"

# A shared zone rather than one copy under /bagsh/ and another under
# /etseg-eh/: the portfolio is one artifact both roles write to (§2.3, §4.3),
# and the permission layer already decides who sees what.
urlpatterns = [
    path("hawtas/<int:child_id>/", views.portfolio, name="overview"),
    path("hawtas/<int:child_id>/minii-tuhai/", views.about_me_edit,
         name="about_me_edit"),
    path("hawtas/<int:child_id>/nas/<int:age>/", views.age_profile_edit,
         name="age_profile_edit"),
    path("hawtas/<int:child_id>/torson-odor/<int:age>/",
         views.birthday_note_edit, name="birthday_note_edit"),
]
