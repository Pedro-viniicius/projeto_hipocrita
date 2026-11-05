"""Busca sem acento e com prioridade (D13)."""

from apps.catalog.domain.search import match_tier, normalize, split_terms


def test_normalize():
    assert normalize("  Pão   de  AÇÚCAR ") == "pao de acucar"
    assert normalize("") == ""


def test_split_terms_limits():
    assert split_terms("Brigadeiro  de  Pão") == ["brigadeiro", "de", "pao"]
    assert split_terms("a b cd") == ["cd"]
    assert split_terms("um dois tres quatro cinco seis sete oito") == [
        "um", "dois", "tres", "quatro", "cinco", "seis",
    ]  # fmt: skip
    assert split_terms("cd cd CD") == ["cd"]
    assert split_terms("   ") == []


def test_split_terms_truncates_query():
    q = "x" * 79 + " abc"
    assert split_terms(q) == ["x" * 79]


def test_tiers():
    terms = split_terms("brownie")
    assert match_tier(terms, "Brownie de nozes", "Ana", "") == 0
    assert match_tier(split_terms("ana"), "Brownie", "Doces da Ana", "") == 1
    assert match_tier(terms, "Doce", "Ana", "Brownie caseiro") == 2
    assert match_tier(terms, "Doce", "Ana", "Cookie") is None


def test_all_terms_required_and_can_span_fields():
    assert match_tier(split_terms("brownie ana"), "Brownie", "Doces da Ana", "") == 1
    assert match_tier(split_terms("brownie xyz"), "Brownie", "Ana", "") is None
    assert match_tier(split_terms("brownie nozes"), "Brownie", "Ana", "com nozes") == 2


def test_accents_and_case_ignored():
    assert match_tier(split_terms("PAO"), "Pão de mel", "", "") == 0
    assert match_tier(split_terms("pão"), "PAO", "", "") == 0


def test_no_terms_matches_everything():
    assert match_tier([], "Qualquer", "", "") == 0
