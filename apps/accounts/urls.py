from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("cadastrar/", views.signup, name="signup"),
    path("entrar/", views.login, name="login"),
    path("sair/", views.logout, name="logout"),
    path("senha/recuperar/", views.password_reset, name="password_reset"),
    path("senha/recuperar/enviado/", views.password_reset_done, name="password_reset_done"),
    path(
        "senha/redefinir/<uidb64>/<token>/",
        views.password_reset_confirm,
        name="password_reset_confirm",
    ),
    path("senha/redefinida/", views.password_reset_complete, name="password_reset_complete"),
    path("perfil/senha/", views.password_change, name="password_change"),
    path("perfil/excluir-conta/", views.delete_account, name="delete"),
]
