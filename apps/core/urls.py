from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("_tarefas/limpeza/", views.cleanup_cron, name="cleanup_cron"),
    path("robots.txt", views.robots_txt, name="robots"),
    path("privacidade/", views.privacy, name="privacy"),
    path("media/<path:path>", views.media, name="media"),
    path("_estilos/", views.styleguide, name="styleguide"),
]
