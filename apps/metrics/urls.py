from django.urls import path

from apps.metrics import views

app_name = "metrics"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
]
