from django.urls import path

from apps.catalog import views_seller as views

app_name = "seller"

urlpatterns = [
    path("meus-anuncios/", views.dashboard, name="dashboard"),
    path("meus-anuncios/novo/", views.offer_create, name="offer_create"),
    path("meus-anuncios/<int:pk>/editar/", views.offer_edit, name="offer_edit"),
    path("meus-anuncios/<int:pk>/acao/", views.offer_action, name="offer_action"),
    path("perfil/", views.profile, name="profile"),
]
