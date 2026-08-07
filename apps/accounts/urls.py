from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("nevtreh/", views.login_view, name="login"),
    path("garah/", views.logout_view, name="logout"),
    path("nuuts-ug-sergeeh/", views.password_reset_request,
         name="password_reset"),
    path("nuuts-ug-sergeeh/shineelegdlee/", views.password_reset_complete,
         name="password_reset_complete"),
    path("nuuts-ug-sergeeh/<str:token>/", views.password_reset_confirm,
         name="password_reset_confirm"),
]
