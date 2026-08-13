from django.urls import path

from .views import parent, teacher

app_name = "children"

urlpatterns = [
    # Teacher — RFP §2.2
    path("bagsh/huuhded/", teacher.child_list, name="list"),
    path("bagsh/huuhded/shine/", teacher.child_create, name="create"),
    path("bagsh/huuhded/<int:child_id>/", teacher.child_detail, name="detail"),
    path("bagsh/huuhded/<int:child_id>/zasah/", teacher.child_edit, name="edit"),
    path("bagsh/huuhded/<int:child_id>/asran-hamgaalagch/",
         teacher.guardian_add, name="guardian_add"),

    # Guardian — RFP §2.3
    path("etseg-eh/", parent.home, name="parent_home"),
    path("etseg-eh/huuhed/<int:child_id>/", parent.child_detail,
         name="parent_child_detail"),
]
