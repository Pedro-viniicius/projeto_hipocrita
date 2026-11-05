"""Página de privacidade (LGPD art. 9) e aviso de deploy sem responsável (S4)."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.core import checks

from apps.core import retention
from apps.core.testing import assert_accessible_page, parse_html

pytestmark = pytest.mark.django_db

URL = "/privacidade/"


def page_text(response) -> str:
    return " ".join(parse_html(response).find("main").text.split())


def test_without_controller_shows_to_be_defined(client, settings):
    settings.PRIVACY_CONTROLLER_NAME = ""
    settings.PRIVACY_CONTACT_EMAIL = ""
    response = client.get(URL)
    assert response.status_code == 200
    assert_accessible_page(response)
    text = page_text(response)
    assert "Responsável: a definir" in text
    assert "Contato: a definir" in text
    assert parse_html(response).find("a", href="mailto:") is None


def test_with_controller_shows_name_and_contact(client, settings):
    settings.PRIVACY_CONTROLLER_NAME = "Coletivo Pão de Cada Dia"
    settings.PRIVACY_CONTACT_EMAIL = "privacidade@exemplo.test"
    response = client.get(URL)
    text = page_text(response)
    assert "Responsável: Coletivo Pão de Cada Dia" in text
    assert "a definir" not in text
    link = parse_html(response).find("a", href="mailto:privacidade@exemplo.test")
    assert link is not None
    assert_accessible_page(response)


def test_controller_values_are_escaped(client, settings):
    settings.PRIVACY_CONTROLLER_NAME = "<script>alert(1)</script>"
    response = client.get(URL)
    assert "<script>alert(1)</script>" not in response.content.decode()


def test_text_matches_what_the_code_does(client):
    text = page_text(client.get(URL))
    expected = [
        # finalidade e base legal
        "consentimento",
        "execução do serviço",
        "legítimo interesse",
        # retenção (ver apps/core/retention.py e cleanup_data)
        "até 24 horas",
        "inclusive de quem denuncia",
        "90 dias",
        "180 dias",
        "sessões vencidas são apagadas",
        "política do servidor",
        # código do IP e do e-mail
        "pseudonimização",
        "continua sendo dado pessoal",
        # direitos sem login e exclusão
        "sem precisar entrar na conta",
        "Excluir minha conta",
    ]
    for snippet in expected:
        assert snippet in text, snippet


def test_retention_numbers_come_from_the_code(client, monkeypatch):
    from apps.core import retention

    monkeypatch.setattr(retention, "SEARCH_MISS_DAYS", 30)
    monkeypatch.setattr(retention, "REPORT_DETAILS_DAYS", 60)
    text = page_text(client.get(URL))
    assert "30 dias" in text
    assert "60 dias" in text


def test_says_that_touching_whatsapp_keeps_a_code_of_the_ip(client):
    # S4: quem só visita também guarda o código ao tocar no botão, e a seção de quem só
    # visita precisa dizer isso, porque as contagens dela não têm IP.
    text = page_text(client.get(URL))
    visit = text.split("Se você só visita")[1].split("Se você vende")[0]
    assert "Essas contagens não têm IP" in visit
    assert "toca em “Consultar no WhatsApp”, guardamos por pouco tempo um código do seu IP" in visit
    retention_section = text.split("Por quanto tempo guardamos")[1].split("Buscas sem resultado")[0]
    assert "até 24 horas" in retention_section
    assert "enviam formulário ou tocam em “Consultar no WhatsApp”" in retention_section


def test_says_the_hosting_company_logs_accesses_on_its_own(client):
    # Etapa 4 (publicar-vercel): a hospedagem registra por conta própria, com prazo curto.
    text = page_text(client.get(URL))
    section = text.split("Por quanto tempo guardamos")[1].split("O código do IP e do e-mail")[0]
    assert (
        "a empresa que hospeda o site registra, por conta própria, cada acesso "
        "(endereço da página, inclusive o termo buscado, navegador e IP) e apaga esses "
        "registros no prazo dela, que é curto (na hospedagem atual, até 1 dia)"
    ) in section
    # quem faz o quê: os registros do próprio site seguem sem IP
    assert "os registros que o nosso site mesmo faz não guardam IP" in section
    sharing = text.split("Com quem compartilhamos")[1].split("Denúncias")[0]
    assert "empresa de hospedagem" in sharing
    # S2: a ressalva vale para a hospedagem (Vercel) e para as fotos (Cloudflare R2).
    assert (
        "A empresa de hospedagem e o serviço de armazenamento de fotos podem processar "
        "os dados fora do Brasil, como nos Estados Unidos."
    ) in sharing


def test_says_how_long_counters_last_if_the_scheduled_cleanup_fails(client):
    # R1/S1: o GitHub Actions pode atrasar, descartar ou ser desligado; a página continua
    # verdadeira com só o cron diário da Vercel.
    text = page_text(client.get(URL))
    retention_section = text.split("Por quanto tempo guardamos")[1].split("Buscas sem resultado")[0]
    assert (
        "Limite de tentativas: apagamos em até 24 horas; se a limpeza automática falhar, "
        "em até 2 dias."
    ) in retention_section
    code_section = text.split("O código do IP e do e-mail")[1].split("Com quem compartilhamos")[0]
    assert (
        "apagado em até 24 horas (em até 2 dias, se a limpeza automática falhar)"
    ) in code_section


def test_fallback_limit_comes_from_the_code_rounded_up_to_days(client, monkeypatch):
    monkeypatch.setattr(retention, "RATE_LIMIT_MAX_HOURS_IF_SCHEDULER_FAILS", 50)
    text = page_text(client.get(URL))
    assert "se a limpeza automática falhar, em até 3 dias" in text


def test_fallback_limit_covers_the_daily_vercel_cron():
    # Pior caso só com o cron diário: o contador vence com RATE_LIMIT_PURGE_HOURS logo
    # depois de uma rodada e espera a próxima. No Hobby a rodada cai em qualquer minuto da
    # hora marcada, então o intervalo entre duas rodadas é de até 24 h 59 min (< 25 h).
    vercel = json.loads((Path(django_settings.BASE_DIR) / "vercel.json").read_text())
    (cron,) = vercel["crons"]
    minute, hour, *rest = cron["schedule"].split()
    assert minute.isdigit() and hour.isdigit() and rest == ["*", "*", "*"]  # 1 vez por dia
    worst = timedelta(hours=retention.RATE_LIMIT_PURGE_HOURS) + timedelta(hours=25)
    assert worst <= timedelta(hours=retention.RATE_LIMIT_MAX_HOURS_IF_SCHEDULER_FAILS)


def test_explains_the_code_without_jargon_or_false_promise(client):
    # D1, S4 da rodada 1: sem o nome do algoritmo e sem prometer que não dá para reverter.
    text = page_text(client.get(URL))
    assert "HMAC" not in text
    assert "código embaralhado" in text
    assert "Quem tem a chave do site ainda conseguiria descobrir o original" in text
    assert "Não dá para voltar" not in text
    section = text.split("O código do IP e do e-mail")[1].split("Com quem compartilhamos")[0]
    assert "apagado em até 24 horas" in section
    assert "desfazer" not in section


def test_legal_basis_comes_after_a_plain_sentence(client):
    # D2: frase simples primeiro, termo legal entre parênteses.
    text = page_text(client.get(URL))
    assert "Por que usamos seus dados" in text
    assert "com qual base legal" not in text
    assert "porque você autorizou (consentimento)" in text
    assert "o que você pediu ao se cadastrar (execução do serviço)" in text
    assert "Mantemos a vitrine segura e funcionando (legítimo interesse)" in text


def test_page_has_no_draft_notice(client):
    # D3: a pendência do rascunho fica em docs/produto/decisoes.md, não na página.
    text = page_text(client.get(URL))
    assert "Rascunho" not in text
    assert "revisão do dono" not in text
    assert "Guardamos só o necessário para a vitrine funcionar." in text


# System check com --deploy -------------------------------------------------------


def _privacy_warnings():
    return [m for m in checks.run_checks(include_deployment_checks=True) if m.id == "core.W001"]


def test_deploy_check_warns_without_controller(settings):
    settings.PRIVACY_CONTROLLER_NAME = ""
    settings.PRIVACY_CONTACT_EMAIL = "privacidade@exemplo.test"
    warnings = _privacy_warnings()
    assert len(warnings) == 1
    assert "PRIVACY_CONTROLLER_NAME" in warnings[0].msg
    settings.PRIVACY_CONTROLLER_NAME = "Coletivo"
    settings.PRIVACY_CONTACT_EMAIL = ""
    assert "PRIVACY_CONTACT_EMAIL" in _privacy_warnings()[0].msg


def test_deploy_check_quiet_when_filled(settings):
    settings.PRIVACY_CONTROLLER_NAME = "Coletivo"
    settings.PRIVACY_CONTACT_EMAIL = "privacidade@exemplo.test"
    assert _privacy_warnings() == []


def test_check_only_runs_with_deploy(settings):
    settings.PRIVACY_CONTROLLER_NAME = ""
    settings.PRIVACY_CONTACT_EMAIL = ""
    assert not [m for m in checks.run_checks() if m.id == "core.W001"]
