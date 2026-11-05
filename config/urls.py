"""Rotas do site. Congeladas na etapa 1: as etapas seguintes só preenchem as views."""

from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("", include("apps.catalog.urls_public")),
    path("", include("apps.moderation.urls_public")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.catalog.urls_seller")),
    path("admin/metricas/", include("apps.metrics.urls")),
    path("admin/", include("apps.moderation.urls")),
]

handler400 = "apps.core.views.bad_request"
handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.page_not_found"
handler500 = "apps.core.views.server_error"
