"""Rotas congeladas na etapa 1: nomes, caminhos e controle de acesso dos stubs."""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

ROUTES = [
    # (nome, kwargs, caminho)
    ("catalog:home", {}, "/"),
    ("catalog:offer_detail", {"pk": 7}, "/oferta/7/"),
    ("catalog:offer_whatsapp", {"pk": 7}, "/oferta/7/whatsapp/"),
    ("catalog:seller_detail", {"slug": "doces-da-ana"}, "/vendedor/doces-da-ana/"),
    ("report:create", {"pk": 7}, "/oferta/7/denunciar/"),
    ("report:done", {"pk": 7}, "/oferta/7/denunciar/enviada/"),
    ("core:privacy", {}, "/privacidade/"),
    ("core:robots", {}, "/robots.txt"),
    ("core:healthz", {}, "/healthz"),
    ("core:media", {"path": "offers/a-card.webp"}, "/media/offers/a-card.webp"),
    ("core:styleguide", {}, "/_estilos/"),
    ("accounts:signup", {}, "/cadastrar/"),
    ("accounts:login", {}, "/entrar/"),
    ("accounts:logout", {}, "/sair/"),
    ("accounts:password_reset", {}, "/senha/recuperar/"),
    ("accounts:password_reset_done", {}, "/senha/recuperar/enviado/"),
    (
        "accounts:password_reset_confirm",
        {"uidb64": "MQ", "token": "abc-123"},
        "/senha/redefinir/MQ/abc-123/",
    ),
    ("accounts:password_reset_complete", {}, "/senha/redefinida/"),
    ("accounts:password_change", {}, "/perfil/senha/"),
    ("accounts:delete", {}, "/perfil/excluir-conta/"),
    ("seller:dashboard", {}, "/meus-anuncios/"),
    ("seller:offer_create", {}, "/meus-anuncios/novo/"),
    ("seller:offer_edit", {"pk": 7}, "/meus-anuncios/7/editar/"),
    ("seller:offer_action", {"pk": 7}, "/meus-anuncios/7/acao/"),
    ("seller:profile", {}, "/perfil/"),
    ("moderation:approvals", {}, "/admin/"),
    ("moderation:offers", {}, "/admin/anuncios/"),
    ("moderation:offer_preview", {"pk": 7}, "/admin/anuncios/7/"),
    ("moderation:offer_approve", {"pk": 7}, "/admin/anuncios/7/aprovar/"),
    ("moderation:offer_hide", {"pk": 7}, "/admin/anuncios/7/ocultar/"),
    ("moderation:offer_show", {"pk": 7}, "/admin/anuncios/7/mostrar/"),
    ("moderation:reports", {}, "/admin/denuncias/"),
    ("moderation:report_resolve", {"pk": 7}, "/admin/denuncias/7/tratar/"),
    ("moderation:categories", {}, "/admin/categorias/"),
    ("moderation:category_update", {"pk": 7}, "/admin/categorias/7/"),
    ("metrics:dashboard", {}, "/admin/metricas/"),
]


@pytest.mark.parametrize(("name", "kwargs", "path"), ROUTES)
def test_route_names_and_paths(name, kwargs, path):
    assert reverse(name, kwargs=kwargs) == path


PUBLIC_GET = ["/", "/oferta/7/", "/oferta/7/whatsapp/", "/vendedor/ana/"]
PUBLIC_GET += ["/oferta/7/denunciar/", "/oferta/7/denunciar/enviada/"]
# Rotas de contas: implementadas na etapa 3 (não são mais stubs).
ACCOUNTS_GET = ["/cadastrar/", "/entrar/", "/senha/recuperar/", "/senha/recuperar/enviado/"]
ACCOUNTS_GET += ["/senha/redefinir/MQ/abc/", "/senha/redefinida/"]


# Todas as rotas já foram implementadas (etapas 3 a 6): nenhum stub 501 deve sobrar.
# Com o banco vazio, a oferta 7 e o vendedor "ana" não existem: 404, nunca 500 nem 501.
@pytest.mark.parametrize("path", PUBLIC_GET)
def test_public_routes_are_implemented(client, path):
    response = client.get(path)
    # "/denunciar/enviada/" é 200 de propósito: confirma e volta ao início se a oferta saiu.
    expected = 200 if path in ("/", "/oferta/7/denunciar/enviada/") else 404
    assert response.status_code == expected


@pytest.mark.parametrize("path", ACCOUNTS_GET)
def test_public_account_pages_answer_200(client, path):
    response = client.get(path, follow=True)
    assert response.status_code == 200


def test_home_with_all_params_is_200_not_500(client):
    response = client.get("/?q=bolo&cat=bebidas&hoje=1&pagina=2")
    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers


SELLER_GET = ["/meus-anuncios/", "/meus-anuncios/novo/", "/meus-anuncios/7/editar/", "/perfil/"]
STAFF_GET = ["/admin/", "/admin/anuncios/", "/admin/anuncios/7/", "/admin/denuncias/"]
STAFF_GET += ["/admin/categorias/", "/admin/metricas/"]
LOGIN_GET = ["/perfil/senha/", "/perfil/excluir-conta/"]


@pytest.mark.parametrize("path", SELLER_GET + STAFF_GET + LOGIN_GET)
def test_private_routes_redirect_anonymous_to_login(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert response["Location"].startswith(f"/entrar/?next={path}")


@pytest.mark.parametrize("path", SELLER_GET)
def test_seller_routes_are_implemented_for_seller(seller_client, path):
    # O anúncio 7 não existe (ou não é do vendedor): 404.
    expected = 404 if "/7/" in path else 200
    assert seller_client.get(path).status_code == expected


@pytest.mark.parametrize("path", SELLER_GET)
def test_seller_routes_forbidden_without_seller_profile(staff_client, path):
    assert staff_client.get(path).status_code == 403


@pytest.mark.parametrize("path", STAFF_GET)
def test_staff_routes_are_implemented_for_staff(staff_client, path):
    expected = 404 if "/7/" in path else 200
    assert staff_client.get(path).status_code == expected


@pytest.mark.parametrize("path", STAFF_GET)
def test_staff_routes_forbidden_for_seller(seller_client, path):
    response = seller_client.get(path)
    assert response.status_code == 403


POST_ONLY = [
    "/sair/",
    "/meus-anuncios/7/acao/",
    "/admin/anuncios/7/aprovar/",
    "/admin/anuncios/7/ocultar/",
    "/admin/anuncios/7/mostrar/",
    "/admin/denuncias/7/tratar/",
    "/admin/categorias/7/",
]


@pytest.mark.parametrize("path", POST_ONLY)
def test_mutations_refuse_get(staff_client, path):
    assert staff_client.get(path).status_code == 405


@pytest.mark.parametrize("path", POST_ONLY[2:])
def test_staff_mutations_forbidden_for_seller(seller_client, path):
    assert seller_client.post(path).status_code == 403


def test_seller_action_post_on_missing_offer_is_404(seller_client):
    assert seller_client.post("/meus-anuncios/7/acao/", {"action": "pause"}).status_code == 404


def test_django_admin_not_installed(staff_client):
    # /admin/ é a área própria; não existe login do Django admin.
    assert staff_client.get("/admin/login/").status_code == 404
