"""Recuperação (e-mail no console) e troca de senha (D17, CA14)."""

import re

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.contrib.messages import get_messages
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import User
from apps.core.testing import assert_accessible_page, parse_html
from texts import accounts as texts

pytestmark = pytest.mark.django_db

EMAIL = "ana@exemplo.test"
OLD = "senha-antiga-da-ana-1"
NEW = "nova-senha-bem-longa-2"


@pytest.fixture
def user(make_seller, make_user):
    return make_seller(user=make_user(email=EMAIL, password=OLD)).user


def reset_link(message) -> str:
    match = re.search(r"https?://testserver(/senha/redefinir/[^\s]+/)", message.body)
    assert match, "e-mail sem link de redefinição"
    return match.group(1)


# Recuperação ---------------------------------------------------------------------


def test_reset_form_is_accessible(client):
    response = client.get("/senha/recuperar/")
    assert response.status_code == 200
    assert_accessible_page(response)


def test_reset_sends_link_for_existing_account(client, user):
    response = client.post("/senha/recuperar/", {"email": "Ana@Exemplo.test"})
    assert response.status_code == 302
    assert response["Location"] == "/senha/recuperar/enviado/"
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == [EMAIL]
    assert message.subject == texts.PASSWORD_RESET_SUBJECT
    assert OLD not in message.body
    reset_link(message)


def test_reset_does_not_reveal_unknown_email(client, user):
    response = client.post("/senha/recuperar/", {"email": "ninguem@exemplo.test"})
    assert response.status_code == 302
    assert response["Location"] == "/senha/recuperar/enviado/"
    assert mail.outbox == []
    done = client.get("/senha/recuperar/enviado/")
    assert done.status_code == 200
    assert_accessible_page(done)


def test_full_reset_flow(client, user):
    client.post("/senha/recuperar/", {"email": EMAIL})
    link = reset_link(mail.outbox[0])

    form_page = client.get(link, follow=True)
    assert form_page.status_code == 200
    assert_accessible_page(form_page)
    set_url = form_page.redirect_chain[-1][0]

    short = client.post(set_url, {"new_password1": "curta", "new_password2": "curta"})
    assert short.status_code == 200
    error = parse_html(short).find(id="id_new_password1_error")
    assert error is not None and texts.PASSWORD_TOO_SHORT in error.text

    done = client.post(set_url, {"new_password1": NEW, "new_password2": NEW})
    assert done.status_code == 302
    assert done["Location"] == "/senha/redefinida/"
    user.refresh_from_db()
    assert user.check_password(NEW)
    assert client.get("/senha/redefinida/").status_code == 200

    # O link não vale de novo.
    again = client.get(link, follow=True)
    assert "Este link não vale mais" in again.content.decode()


def test_invalid_token_page(client, user):
    response = client.get("/senha/redefinir/MQ/token-invalido/", follow=True)
    assert response.status_code == 200
    assert "Este link não vale mais" in response.content.decode()
    assert parse_html(response).find("input", name="new_password1") is None


def test_reset_limited_to_5_per_hour_per_ip(client, user):
    for _ in range(5):
        client.post("/senha/recuperar/", {"email": EMAIL}, REMOTE_ADDR="10.0.0.9")
    blocked = client.post("/senha/recuperar/", {"email": EMAIL}, REMOTE_ADDR="10.0.0.9")
    assert blocked.status_code == 429
    assert len(mail.outbox) == 5


# Recuperação desligada em produção sem SMTP (S3) ---------------------------------

CONSOLE = "django.core.mail.backends.console.EmailBackend"
SMTP = "django.core.mail.backends.smtp.EmailBackend"
UNAVAILABLE = "A recuperação de senha pelo site não está disponível agora."
NO_CONTACT = "Ainda não há um contato cadastrado para isso."
CONTACT = "contato@exemplo.test"


@pytest.fixture
def console_in_production(settings):
    settings.DEBUG = False
    settings.EMAIL_BACKEND = CONSOLE


def test_reset_is_off_in_production_with_console_backend(
    client, user, console_in_production, capsys
):
    page = client.get("/senha/recuperar/")
    assert page.status_code == 200
    assert UNAVAILABLE in page.content.decode()
    assert parse_html(page).find("input", name="email") is None
    assert_accessible_page(page)

    sent = client.post("/senha/recuperar/", {"email": EMAIL})
    assert sent.status_code == 200
    assert UNAVAILABLE in sent.content.decode()
    # Nada de e-mail com o link no console (que vira log em produção).
    assert "/senha/redefinir/" not in capsys.readouterr().out


def test_reset_link_does_not_work_in_production_with_console_backend(
    client, user, console_in_production
):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    response = client.get(f"/senha/redefinir/{uid}/{token}/", follow=True)
    assert UNAVAILABLE in response.content.decode()
    assert parse_html(response).find("input", name="new_password1") is None
    client.post(
        f"/senha/redefinir/{uid}/set-password/",
        {"new_password1": NEW, "new_password2": NEW},
    )
    user.refresh_from_db()
    assert user.check_password(OLD)


def test_login_hides_reset_link_when_reset_is_off(client, console_in_production):
    response = client.get("/entrar/")
    doc = parse_html(response)
    assert doc.find("a", href="/senha/recuperar/") is None
    assert_accessible_page(response)


def test_login_with_reset_off_shows_the_contact_as_a_link(client, console_in_production, settings):
    settings.PRIVACY_CONTACT_EMAIL = CONTACT
    response = client.get("/entrar/")
    link = parse_html(response).find("a", href=f"mailto:{CONTACT}")
    assert link is not None
    assert link.text == CONTACT
    assert "ainda não há um contato" not in response.content.decode()
    assert_accessible_page(response)


def test_login_with_reset_off_is_honest_without_contact(client, console_in_production, settings):
    settings.PRIVACY_CONTACT_EMAIL = ""
    response = client.get("/entrar/")
    html = response.content.decode()
    assert "ainda não há um contato cadastrado" in html
    assert "fale com a administração" not in html
    assert "mailto:" not in html
    assert_accessible_page(response)


def test_login_with_reset_on_does_not_show_the_contact(client, settings):
    settings.PRIVACY_CONTACT_EMAIL = CONTACT
    response = client.get("/entrar/")
    assert parse_html(response).find("a", href="/senha/recuperar/") is not None
    assert "mailto:" not in response.content.decode()


def test_unavailable_reset_shows_the_contact_as_a_link(client, console_in_production, settings):
    settings.PRIVACY_CONTACT_EMAIL = CONTACT
    response = client.get("/senha/recuperar/")
    link = parse_html(response).find("a", href=f"mailto:{CONTACT}")
    assert link is not None
    assert link.text == CONTACT
    html = response.content.decode()
    assert UNAVAILABLE in html
    assert "Ela pode definir uma senha nova para você." in html
    assert NO_CONTACT not in html
    assert_accessible_page(response)


def test_unavailable_reset_is_honest_without_contact(client, console_in_production, settings):
    settings.PRIVACY_CONTACT_EMAIL = ""
    response = client.get("/senha/recuperar/")
    html = response.content.decode()
    assert UNAVAILABLE in html
    assert NO_CONTACT in html
    assert "fale com a administração" not in html
    assert "mailto:" not in html
    assert_accessible_page(response)


@pytest.mark.parametrize(("debug", "backend"), [(False, SMTP), (True, CONSOLE)])
def test_reset_is_on_with_smtp_or_in_debug(client, settings, debug, backend):
    settings.DEBUG = debug
    settings.EMAIL_BACKEND = backend
    page = client.get("/senha/recuperar/")
    assert parse_html(page).find("input", name="email") is not None
    assert UNAVAILABLE not in page.content.decode()
    assert parse_html(client.get("/entrar/")).find("a", href="/senha/recuperar/") is not None


# Troca de senha ----------------------------------------------------------------


def test_change_requires_login(client):
    response = client.get("/perfil/senha/")
    assert response.status_code == 302
    assert response["Location"].startswith("/entrar/?next=/perfil/senha/")


def test_change_page_is_accessible(client, user):
    client.force_login(user)
    response = client.get("/perfil/senha/")
    assert response.status_code == 200
    assert_accessible_page(response)


def test_change_with_wrong_old_password(client, user):
    client.force_login(user)
    response = client.post(
        "/perfil/senha/",
        {"old_password": "nao-e-essa", "new_password1": NEW, "new_password2": NEW},
    )
    assert response.status_code == 200
    assert parse_html(response).find(id="id_old_password_error") is not None
    user.refresh_from_db()
    assert user.check_password(OLD)


def test_change_success_keeps_session(client, user):
    client.force_login(user)
    response = client.post(
        "/perfil/senha/",
        {"old_password": OLD, "new_password1": NEW, "new_password2": NEW},
    )
    assert response.status_code == 302
    assert response["Location"] == "/perfil/"
    assert [str(m) for m in get_messages(response.wsgi_request)] == [texts.PASSWORD_CHANGED]
    user.refresh_from_db()
    assert user.check_password(NEW)
    assert client.session["_auth_user_id"] == str(user.pk)


def test_change_mismatch(client, user):
    client.force_login(user)
    response = client.post(
        "/perfil/senha/",
        {"old_password": OLD, "new_password1": NEW, "new_password2": NEW + "x"},
    )
    assert response.status_code == 200
    assert parse_html(response).find(id="id_new_password2_error") is not None
    assert User.objects.get(pk=user.pk).check_password(OLD)
