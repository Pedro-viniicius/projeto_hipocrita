"""Verificação independente das correções de segurança e infraestrutura (qa, rodada 2).

Cobre S2 (login por par IP + e-mail), S3 (recuperação de senha e log), S4 (privacidade),
S5 (IPv6), S7 (limpeza), S8 (contatos) e S10 (cache de fotos) por caminhos que os testes
de cada área não usam: pela porta da frente, com IPv6 de verdade, com entradas hostis.
"""

import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
import time_machine
from django.test import Client

from apps.accounts.models import User
from apps.core.models import RateLimitCounter
from apps.core.testing import parse_html

pytestmark = pytest.mark.django_db

BASE_DIR = Path(__file__).resolve().parents[3]
EMAIL = "ana@exemplo.test"
SENHA = "senha-certa-da-ana-123"


@pytest.fixture
def ana(make_seller, make_user):
    return make_seller(user=make_user(email=EMAIL, password=SENHA))


def entrar(client, email=EMAIL, senha=SENHA, ip="10.0.0.1"):
    return client.post("/entrar/", {"email": email, "password": senha}, REMOTE_ADDR=ip)


def logado(client) -> bool:
    return "_auth_user_id" in client.session


# S2 + S5: o par IP + e-mail e a rede /64 do IPv6, juntos, pela view de login --------------


def test_ipv6_da_mesma_rede_64_divide_o_limite_de_login(client, ana):
    for i in range(5):
        entrar(client, senha="errada-123456", ip=f"2001:db8:abcd:1::{i + 1:x}")
    # Outro endereço da mesma /64, com a senha certa: continua bloqueado.
    bloqueado = entrar(client, ip="2001:db8:abcd:1:ffff:ffff:ffff:ffff")
    assert bloqueado.status_code == 429
    assert not logado(client)


def test_ipv6_de_outra_rede_64_nao_e_afetado(client, ana):
    for i in range(5):
        entrar(client, senha="errada-123456", ip=f"2001:db8:abcd:1::{i + 1:x}")
    assert entrar(client, ip="2001:db8:abcd:2::1").status_code == 302


def test_ipv4_mapeado_em_ipv6_conta_como_o_ipv4(client, ana):
    for _ in range(5):
        entrar(client, senha="errada-123456", ip="198.51.100.7")
    assert entrar(client, ip="::ffff:198.51.100.7").status_code == 429


@pytest.mark.parametrize("variante", [EMAIL.upper(), f"  {EMAIL}  ", "Ana@Exemplo.TEST"])
def test_variantes_do_mesmo_email_dividem_o_limite_do_par(client, ana, variante, monkeypatch):
    from apps.accounts import views

    monkeypatch.setattr(views, "LOGIN_IP_LIMIT", 1000)  # isola o limite do par
    for _ in range(5):
        entrar(client, senha="errada-123456")
    assert entrar(client, email=variante).status_code == 429
    assert entrar(client, ip="10.0.0.2").status_code == 302  # a dona, de outro IP, entra


def test_bloqueio_e_igual_para_conta_que_existe_e_que_nao_existe(client, ana):
    for _ in range(5):
        entrar(client, email="fantasma@exemplo.test", senha="x", ip="10.1.1.1")
    fantasma = entrar(client, email="fantasma@exemplo.test", senha="x", ip="10.1.1.1")
    for _ in range(5):
        entrar(client, senha="errada-123456", ip="10.2.2.2")
    real = entrar(client, senha="errada-123456", ip="10.2.2.2")
    assert (fantasma.status_code, fantasma["Retry-After"]) == (
        real.status_code,
        real["Retry-After"],
    )
    assert fantasma.content.decode().count("<form") == real.content.decode().count("<form")


def test_429_do_login_escapa_o_email_digitado(client):
    perigoso = '"><script>alert(1)</script>@x.test'
    for _ in range(5):
        entrar(client, email=perigoso, senha="x")
    resposta = entrar(client, email=perigoso, senha="x")
    assert resposta.status_code == 429
    assert "<script>alert(1)</script>" not in resposta.content.decode()


@pytest.mark.parametrize(
    "email", ["a\x00b@exemplo.test", "x" * 5000 + "@exemplo.test", "😀@exemplo.test"]
)
def test_login_com_entrada_hostil_responde_200_sem_500(client, email):
    assert entrar(client, email=email, senha="x").status_code == 200
    # Só HMAC no banco, mesmo com NUL e texto gigante.
    for linha in RateLimitCounter.objects.all():
        assert re.fullmatch(r"[0-9a-f]{64}", linha.key_hash)


def test_o_bloqueio_nao_se_estende_com_novas_tentativas_durante_a_janela(client, ana):
    with time_machine.travel("2026-11-05 10:00:00-03:00", tick=False) as relogio:
        for _ in range(5):
            entrar(client, senha="errada-123456")
        for _ in range(20):  # insistir bloqueado não pode adiar o fim da janela
            assert entrar(client, senha="errada-123456").status_code == 429
        relogio.shift(timedelta(minutes=15))
        assert entrar(client).status_code == 302


# S1: cadastro --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "email",
    [
        "alguem@exemplo.invalid",
        "ALGUEM@EXEMPLO.INVALID",
        "demo-ana@exemplo.invalid",
        "alguem@sub.dominio.invalid",
        "alguem@invalid.invalid",
    ],
)
def test_cadastro_recusa_dominio_invalid(client, email):
    resposta = client.post(
        "/cadastrar/",
        {
            "display_name": "Alguém",
            "email": email,
            "password": "pao-de-queijo-quentinho",
            "whatsapp": "(35) 91234-5678",
        },
    )
    assert resposta.status_code == 200
    assert not User.objects.exists()


@pytest.mark.parametrize("email", ["alguem@invalid.com", "alguem@exemplo.invalidos.com"])
def test_cadastro_aceita_dominio_que_apenas_parece_invalid(client, email):
    resposta = client.post(
        "/cadastrar/",
        {
            "display_name": "Alguém",
            "email": email,
            "password": "pao-de-queijo-quentinho",
            "whatsapp": "(35) 91234-5678",
        },
    )
    assert resposta.status_code == 302
    assert User.objects.filter(email=email).exists()


@pytest.mark.parametrize("valor", ["-1", "abc", "1.5"])
def test_signups_per_day_invalido_impede_o_app_de_subir(valor):
    ambiente = {k: v for k, v in os.environ.items() if k not in {"SECRET_KEY", "DEBUG"}}
    ambiente.update(DEBUG="true", SIGNUPS_PER_DAY=valor)
    resultado = subprocess.run(  # noqa: S603  (comando fixo)
        [sys.executable, "-c", "import config.settings"],
        cwd=BASE_DIR,
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode != 0
    assert "SIGNUPS_PER_DAY" in resultado.stderr


def test_teto_diario_de_cadastros_nao_conta_o_cadastro_recusado_por_email_repetido(
    settings, make_user
):
    settings.SIGNUPS_PER_DAY = 1
    make_user(email="ja@exemplo.test")
    dados = {
        "display_name": "Repetida",
        "email": "ja@exemplo.test",
        "password": "pao-de-queijo-quentinho",
        "whatsapp": "(35) 91234-5678",
    }
    assert Client().post("/cadastrar/", dados, REMOTE_ADDR="10.3.0.1").status_code == 200
    dados["email"] = "nova@exemplo.test"
    assert Client().post("/cadastrar/", dados, REMOTE_ADDR="10.3.0.2").status_code == 302


# S10: fotos servidas pela view de mídia ---------------------------------------------------


def test_media_304_e_head_mantem_o_cache_curto(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "f.webp").write_bytes(b"RIFF....WEBP")
    primeira = client.get("/media/f.webp")
    assert primeira["Cache-Control"] == "public, max-age=86400"
    assert "immutable" not in primeira["Cache-Control"]
    condicional = client.get(
        "/media/f.webp", headers={"If-Modified-Since": primeira["Last-Modified"]}
    )
    assert condicional.status_code == 304
    assert condicional["Cache-Control"] == "public, max-age=86400"
    assert client.head("/media/f.webp")["Cache-Control"] == "public, max-age=86400"


@pytest.mark.parametrize(
    "caminho", ["../x.webp", "a/../../x.webp", "a%5c..%5cx.webp", "x.WEBP.html"]
)
def test_media_recusa_caminhos_hostis(client, settings, tmp_path, caminho):
    settings.MEDIA_ROOT = tmp_path / "midia"
    (tmp_path / "midia").mkdir()
    (tmp_path / "x.webp").write_bytes(b"segredo")
    resposta = client.get(f"/media/{caminho}")
    assert resposta.status_code == 404


def test_foto_apagada_deixa_de_ser_servida_e_o_404_nao_tem_cache_publico(
    client, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    arquivo = tmp_path / "f.webp"
    arquivo.write_bytes(b"RIFF....WEBP")
    assert client.get("/media/f.webp").status_code == 200
    arquivo.unlink()
    depois = client.get("/media/f.webp")
    assert depois.status_code == 404
    assert "max-age=86400" not in depois.get("Cache-Control", "")


# S8: o 302 do contato não pode ficar de fora do limite por nenhum método ------------------


def test_so_get_e_head_chegam_ao_contato(client, make_offer):
    oferta = make_offer()
    url = f"/oferta/{oferta.pk}/whatsapp/"
    assert client.options(url).status_code == 405
    assert client.delete(url).status_code == 405


# S4: a página de privacidade tem de dizer o que o código faz com o IP de quem só visita ---


def test_privacidade_diz_que_tocar_em_consultar_no_whatsapp_guarda_um_codigo_do_ip(client):
    texto = parse_html(client.get("/privacidade/")).text
    item = re.search(r"Limite de tentativas:.*?(?=Buscas sem resultado)", texto)
    assert item is not None
    assert "WhatsApp" in item.group(0) or "contato" in item.group(0)
