from django.urls import path

from apps.catalog import views_public as views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("oferta/<int:pk>/", views.offer_detail, name="offer_detail"),
    path("oferta/<int:pk>/whatsapp/", views.offer_whatsapp, name="offer_whatsapp"),
    path("vendedor/<slug:slug>/", views.seller_detail, name="seller_detail"),
]
