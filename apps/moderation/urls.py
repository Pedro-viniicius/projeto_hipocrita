"""Rotas da administração, montadas em `/admin/` (o Django admin não é instalado)."""

from django.urls import path

from apps.moderation import views

app_name = "moderation"

urlpatterns = [
    path("", views.approvals, name="approvals"),
    path("anuncios/", views.offers, name="offers"),
    path("anuncios/<int:pk>/", views.offer_preview, name="offer_preview"),
    path("anuncios/<int:pk>/aprovar/", views.offer_approve, name="offer_approve"),
    path("anuncios/<int:pk>/ocultar/", views.offer_hide, name="offer_hide"),
    path("anuncios/<int:pk>/mostrar/", views.offer_show, name="offer_show"),
    path("denuncias/", views.reports, name="reports"),
    path("denuncias/<int:pk>/tratar/", views.report_resolve, name="report_resolve"),
    path("categorias/", views.categories, name="categories"),
    path("categorias/<int:pk>/", views.category_update, name="category_update"),
]
