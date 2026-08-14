from django.urls import path

from . import admin_views, views

app_name = "accounts"

urlpatterns = [
    path("nevtreh/", views.login_view, name="login"),
    path("garah/", views.logout_view, name="logout"),

    # RFP §3.3 — a person maintains their own details. No id in the URL:
    # the subject is always the logged-in user.
    path("minii-burtgel/", views.profile, name="profile"),

    path("nuuts-ug-sergeeh/", views.password_reset_request,
         name="password_reset"),
    path("nuuts-ug-sergeeh/shineelegdlee/", views.password_reset_complete,
         name="password_reset_complete"),
    path("nuuts-ug-sergeeh/<str:token>/", views.password_reset_confirm,
         name="password_reset_confirm"),

    # Account activation — RFP §2.1, §3.5
    path("burtgel-idevhjuuleh/", views.activate_by_code, name="activate"),
    path("burtgel-idevhjuuleh/bolloo/", views.activate_done,
         name="activate_done"),
    path("burtgel-idevhjuuleh/<str:token>/", views.activate_by_token,
         name="activate_by_token"),

    # Administrator screens — RFP §2.1, §3.3. Under /udirdlaga/ to match the
    # sidebar, but the project's own views rather than the admin site.
    path("udirdlaga/bagsh/", admin_views.staff_list, name="staff_list"),
    path("udirdlaga/bagsh/urih/", admin_views.staff_invite,
         name="staff_invite"),
    path("udirdlaga/bagsh/<int:membership_id>/tolov/",
         admin_views.membership_toggle, name="membership_toggle"),
    path("udirdlaga/hereglegch/", admin_views.user_list, name="user_list"),
]
