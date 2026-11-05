"""Helpers de teste para HTML acessível e respostas sem rastreio.

Sem dependência externa: um parser mínimo sobre `html.parser` monta uma árvore
de `Element` e as funções `assert_*` verificam as regras da spec (CA3, CA6,
CA14, CA16, CA20). Uso típico:

    from apps.core.testing import assert_accessible_page, parse_html
    response = client.get("/")
    assert_accessible_page(response)
    doc = parse_html(response)
    cards = doc.find_all("article")
"""

import io
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser

from django.http import HttpResponse
from PIL import ExifTags, Image

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "source", "track", "wbr",
}  # fmt: skip
# Campos que precisam de rótulo (input hidden e botões não precisam).
LABELLESS_INPUT_TYPES = {"hidden", "submit", "button", "reset", "image"}


@dataclass
class Element:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list[Element | str] = field(default_factory=list)
    parent: Element | None = field(default=None, repr=False)

    def get(self, name: str, default: str | None = None) -> str | None:
        return self.attrs.get(name, default)

    def has(self, name: str) -> bool:
        return name in self.attrs

    def iter(self) -> Iterator[Element]:
        """Todos os elementos descendentes (pré-ordem), incluindo o próprio."""
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.iter()

    def find_all(self, tag: str | None = None, **attrs: str) -> list[Element]:
        """Descendentes com a tag (ou qualquer tag) e os atributos dados.

        Use `class_` para `class` (casa se a classe estiver na lista).
        """
        found = []
        for el in self.iter():
            if el is self:
                continue
            if tag is not None and el.tag != tag:
                continue
            if all(_attr_matches(el, k, v) for k, v in attrs.items()):
                found.append(el)
        return found

    def find(self, tag: str | None = None, **attrs: str) -> Element | None:
        items = self.find_all(tag, **attrs)
        return items[0] if items else None

    def ancestors(self) -> Iterator[Element]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    @property
    def text(self) -> str:
        """Texto visível do elemento, com espaços colapsados."""
        buf = io.StringIO()
        _collect_text(self, buf)
        return re.sub(r"\s+", " ", buf.getvalue()).strip()


def _attr_matches(el: Element, key: str, value: str) -> bool:
    name = "class" if key == "class_" else key.replace("_", "-")
    if name == "class":
        return value in (el.get("class") or "").split()
    return el.get(name) == value


def _collect_text(el: Element, buf: io.StringIO) -> None:
    if el.tag in {"script", "style", "template"}:
        return
    for child in el.children:
        if isinstance(child, str):
            buf.write(child)
        else:
            _collect_text(child, buf)
            buf.write(" ")


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("#document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        el = Element(tag, dict(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(el)
        if tag not in VOID_TAGS:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        el = Element(tag, dict(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(el)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _html_of(source: HttpResponse | str | bytes) -> str:
    if isinstance(source, HttpResponse):
        return source.content.decode(source.charset or "utf-8")
    if isinstance(source, bytes):
        return source.decode("utf-8")
    return source


def parse_html(source: HttpResponse | str | bytes) -> Element:
    """Árvore do documento a partir de uma resposta, `str` ou `bytes`."""
    builder = _TreeBuilder()
    builder.feed(_html_of(source))
    builder.close()
    return builder.root


# Asserções -------------------------------------------------------------------


def assert_lang_pt_br(source) -> None:
    html = parse_html(source).find("html")
    assert html is not None, "documento sem <html>"
    assert html.get("lang") == "pt-BR", f'<html lang> deve ser "pt-BR", veio {html.get("lang")!r}'


def assert_single_h1(source) -> None:
    count = len(parse_html(source).find_all("h1"))
    assert count == 1, f"a página deve ter exatamente um <h1>, tem {count}"


def assert_main_landmark(source) -> None:
    mains = parse_html(source).find_all("main")
    assert len(mains) == 1, f"a página deve ter um <main>, tem {len(mains)}"
    assert mains[0].get("id") == "conteudo", '<main> deve ter id="conteudo" (pular para o conteúdo)'


def _needs_label(el: Element) -> bool:
    if el.tag in {"select", "textarea"}:
        return True
    if el.tag == "input":
        return (el.get("type") or "text").lower() not in LABELLESS_INPUT_TYPES
    return False


def assert_fields_have_labels(source) -> None:
    """Todo campo visível tem `id` e um `<label for="id">` com texto."""
    doc = parse_html(source)
    labels = {lab.get("for"): lab for lab in doc.find_all("label") if lab.get("for")}
    problems = []
    for el in doc.iter():
        if not _needs_label(el):
            continue
        name = el.get("name") or el.get("id") or el.tag
        field_id = el.get("id")
        if not field_id:
            problems.append(f"{el.tag}[name={name}] sem id")
        elif field_id not in labels:
            problems.append(f'{el.tag}#{field_id} sem <label for="{field_id}">')
        elif not labels[field_id].text:
            problems.append(f'<label for="{field_id}"> vazio')
    assert not problems, "campos sem rótulo: " + "; ".join(problems)


def assert_images_have_alt(source) -> None:
    """Todo `<img>` tem `alt` (vazio só para imagem decorativa)."""
    missing = [img.get("src") for img in parse_html(source).find_all("img") if not img.has("alt")]
    assert not missing, f"<img> sem alt: {missing}"


def assert_unique_ids(source) -> None:
    seen: dict[str, int] = {}
    for el in parse_html(source).iter():
        if el.get("id"):
            seen[el.get("id")] = seen.get(el.get("id"), 0) + 1
    dupes = sorted(k for k, v in seen.items() if v > 1)
    assert not dupes, f"ids repetidos: {dupes}"


def assert_no_inline_code(source) -> None:
    """Nada que o CSP bloqueia: `style=""`, `<style>`, `<script>` sem `src`, `on*=`."""
    problems = []
    for el in parse_html(source).iter():
        if el.has("style"):
            problems.append(f"<{el.tag} style>")
        if el.tag == "style":
            problems.append("<style>")
        if el.tag == "script" and not el.get("src"):
            problems.append("<script> inline")
        problems.extend(f"<{el.tag} {a}>" for a in el.attrs if a.startswith("on"))
        href = (el.get("href") or "").strip().lower()
        if href.startswith("javascript:"):
            problems.append(f"<{el.tag} href=javascript:>")
    assert not problems, "código inline (bloqueado pelo CSP): " + ", ".join(problems)


def assert_post_forms_have_csrf(source) -> None:
    """Todo `<form method="post">` leva o `csrfmiddlewaretoken`."""
    doc = parse_html(source)
    for form in doc.find_all("form"):
        if (form.get("method") or "get").lower() != "post":
            continue
        token = form.find("input", name="csrfmiddlewaretoken")
        assert token is not None, f"<form action={form.get('action')!r}> POST sem CSRF"


def assert_single_link_per_article(source, *, class_: str | None = None) -> None:
    """Cada `<article>` (ou com a classe dada) tem exatamente um `<a href>` (CA3)."""
    doc = parse_html(source)
    articles = doc.find_all("article", class_=class_) if class_ else doc.find_all("article")
    for article in articles:
        links = [a for a in article.find_all("a") if a.get("href")]
        assert len(links) == 1, f"<article id={article.get('id')!r}> tem {len(links)} links"


def assert_accessible_page(source) -> None:
    """Conjunto mínimo da CA20 para uma página completa."""
    assert_lang_pt_br(source)
    assert_single_h1(source)
    assert_main_landmark(source)
    assert_fields_have_labels(source)
    assert_images_have_alt(source)
    assert_unique_ids(source)
    assert_no_inline_code(source)
    assert_post_forms_have_csrf(source)


def phone_variants(number: str) -> list[str]:
    """Formas comuns de escrever um celular `55DD9XXXXXXXX` (13 dígitos)."""
    digits = re.sub(r"\D", "", number)
    assert len(digits) == 13 and digits.startswith("55"), "use o formato 55DD9XXXXXXXX"
    ddd, local = digits[2:4], digits[4:]
    return [
        digits,
        f"+{digits}",
        ddd + local,
        local,
        f"({ddd}) {local[:5]}-{local[5:]}",
        f"{local[:5]}-{local[5:]}",
        f"{local[:1]} {local[1:5]}-{local[5:]}",
    ]


def assert_phone_absent(source, number: str) -> None:
    """O número (em qualquer formato comum) não aparece no HTML (CA6)."""
    html = _html_of(source)
    found = [v for v in phone_variants(number) if v in html]
    assert not found, f"número de WhatsApp presente no HTML: {found}"


def assert_no_set_cookie(response: HttpResponse) -> None:
    """A resposta não grava cookie nenhum (CA16: visitante não é rastreado)."""
    names = list(response.cookies.keys())
    assert not names, f"resposta grava cookies: {names}"
    assert "Set-Cookie" not in response.headers, "resposta tem cabeçalho Set-Cookie"


def make_image_bytes(
    fmt: str = "JPEG",
    size: tuple[int, int] = (800, 600),
    *,
    noise: bool = False,
    exif: bool = False,
) -> bytes:
    """Imagem gerada em memória com o Pillow.

    `noise=True` gera pixels aleatórios (arquivo grande, útil para testar o
    limite de tamanho com PNG). `exif=True` (só JPEG) grava marca da câmera,
    orientação 6 (girar 90°) e GPS, para testar a remoção de metadados.
    """
    if noise:
        img = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
    else:
        img = Image.new("RGB", size, (31, 65, 113))
    buf = io.BytesIO()
    kwargs = {}
    if exif:
        data = Image.Exif()
        data[ExifTags.Base.Make] = "CameraTeste"
        data[ExifTags.Base.Orientation] = 6
        data[ExifTags.IFD.GPSInfo] = {
            ExifTags.GPS.GPSLatitudeRef: "S",
            ExifTags.GPS.GPSLatitude: (21.0, 14.0, 0.0),
            ExifTags.GPS.GPSLongitudeRef: "W",
            ExifTags.GPS.GPSLongitude: (45.0, 0.0, 0.0),
        }
        kwargs["exif"] = data
    img.save(buf, format=fmt, **kwargs)
    return buf.getvalue()
