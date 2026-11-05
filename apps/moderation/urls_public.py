from django.urls import path

from apps.moderation import views_public as views

app_name = "report"

urlpatterns = [
    path("oferta/<int:pk>/denunciar/", views.create, name="create"),
    path("oferta/<int:pk>/denunciar/enviada/", views.done, name="done"),
]
