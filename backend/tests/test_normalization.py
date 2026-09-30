from app.services.normalization import (
    CatalogMatcher,
    build_canonical_name,
    make_match_key,
    parse_market_hash_name,
)


def test_roundtrip_common_names() -> None:
    samples = [
        "AK-47 | Redline (Field-Tested)",
        "StatTrak™ AK-47 | Asiimov (Field-Tested)",
        "Souvenir AWP | Dragon Lore (Factory New)",
        "★ Karambit | Doppler (Factory New)",
        "★ StatTrak™ Karambit | Doppler (Factory New)",
        "★ Sport Gloves | Vice (Minimal Wear)",
        "Sticker | Hello",
    ]
    for raw in samples:
        parsed = parse_market_hash_name(raw)
        assert parsed is not None
        again = parse_market_hash_name(parsed.canonical_name)
        assert again is not None
        assert again.canonical_name == parsed.canonical_name
        assert again.match_key == parsed.match_key


def test_stattrak_symbol_collapses_to_one_key() -> None:
    with_symbol = parse_market_hash_name("StatTrak™ AK-47 | Redline (Field-Tested)")
    without = parse_market_hash_name("StatTrak AK-47 | Redline (Field-Tested)")
    assert with_symbol is not None and without is not None
    assert with_symbol.match_key == without.match_key
    assert with_symbol.stattrak is True
    assert with_symbol.wear == "FT"
    assert with_symbol.weapon == "AK-47"
    assert with_symbol.skin_name == "Redline"


def test_knife_flags() -> None:
    parsed = parse_market_hash_name("★ StatTrak™ Butterfly Knife | Fade (Factory New)")
    assert parsed is not None
    assert parsed.weapon == "★ Butterfly Knife"
    assert parsed.stattrak is True
    assert parsed.souvenir is False
    assert parsed.wear == "FN"
    assert parsed.canonical_name.startswith("★ StatTrak™ Butterfly Knife")


def test_builder_matches_parser() -> None:
    name = build_canonical_name(
        weapon="★ Karambit",
        skin_name="Doppler",
        wear="FN",
        stattrak=True,
        souvenir=False,
    )
    parsed = parse_market_hash_name(name)
    assert parsed is not None
    assert parsed.canonical_name == name
    assert parsed.match_key == make_match_key(name)


def test_exact_key_does_not_spend_fuzzy_budget() -> None:
    parsed = parse_market_hash_name("AWP | Asiimov (Field-Tested)")
    assert parsed is not None
    matcher = CatalogMatcher(
        [parsed.match_key],
        auto_threshold=97,
        review_threshold=90,
        fuzzy_budget=1,
    )
    decision = matcher.match(parsed)
    assert decision.method == "canonical"
    assert decision.create_new is False
    assert matcher.budget == 1


def test_fuzzy_suggestion_is_not_auto_merged_when_score_is_mid() -> None:
    existing = parse_market_hash_name("AK-47 | Redline (Field-Tested)")
    typo = parse_market_hash_name("AK-47 | Redlnie (Field-Tested)")
    assert existing is not None and typo is not None
    matcher = CatalogMatcher(
        [existing.match_key],
        auto_threshold=99.5,
        review_threshold=80,
        fuzzy_budget=5,
    )
    decision = matcher.match(typo)
    assert decision.item_key == existing.match_key
    assert decision.needs_review is True
    assert decision.create_new is False


def test_empty_name_is_rejected() -> None:
    assert parse_market_hash_name("   ") is None
