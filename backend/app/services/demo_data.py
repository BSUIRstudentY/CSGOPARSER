"""Deterministic demo prices so the dashboard works with no marketplace access.

Spreads are invented. They illustrate the pipeline; they are not live quotes.
"""

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.normalization import build_canonical_name, parse_market_hash_name
from app.services.parsers.base import Listing

# weapon, skin, wear, stattrak, souvenir, base USD ask
CATALOG: list[tuple[str, str, str, bool, bool, str]] = [
    ("AK-47", "Redline", "FT", False, False, "14.50"),
    ("AK-47", "Asiimov", "FT", False, False, "28.00"),
    ("AK-47", "Vulcan", "MW", False, False, "420.00"),
    ("AK-47", "Bloodsport", "MW", False, False, "85.00"),
    ("AK-47", "Neon Revolution", "FT", True, False, "32.00"),
    ("M4A4", "Asiimov", "FT", False, False, "95.00"),
    ("M4A4", "The Emperor", "MW", False, False, "180.00"),
    ("M4A4", "Desolate Space", "FT", False, False, "22.00"),
    ("M4A1-S", "Printstream", "FT", False, False, "210.00"),
    ("M4A1-S", "Hyper Beast", "MW", False, False, "48.00"),
    ("M4A1-S", "Decimator", "FT", True, False, "18.00"),
    ("AWP", "Asiimov", "FT", False, False, "62.00"),
    ("AWP", "Dragon Lore", "FN", False, False, "9800.00"),
    ("AWP", "Wildfire", "MW", False, False, "55.00"),
    ("AWP", "Neo-Noir", "FT", False, False, "26.00"),
    ("AWP", "Gungnir", "FT", False, False, "4200.00"),
    ("USP-S", "Kill Confirmed", "MW", False, False, "72.00"),
    ("USP-S", "Cortex", "FT", False, False, "9.50"),
    ("Glock-18", "Fade", "FN", False, False, "310.00"),
    ("Glock-18", "Water Elemental", "FT", False, False, "6.40"),
    ("Desert Eagle", "Blaze", "FN", False, False, "540.00"),
    ("Desert Eagle", "Printstream", "MW", False, False, "95.00"),
    ("Desert Eagle", "Code Red", "FT", True, False, "28.00"),
    ("P250", "See Ya Later", "MW", False, False, "12.00"),
    ("SSG 08", "Blood in the Water", "MW", False, False, "38.00"),
    ("FAMAS", "Commemoration", "FT", False, False, "7.20"),
    ("Galil AR", "Chatterbox", "FT", False, False, "11.00"),
    ("MP9", "Starlight Protector", "MW", False, False, "16.00"),
    ("MAC-10", "Neon Rider", "MW", False, False, "8.50"),
    ("P90", "Asiimov", "FT", False, False, "5.80"),
    ("★ Karambit", "Doppler", "FN", False, False, "1450.00"),
    ("★ Karambit", "Fade", "FN", False, False, "2100.00"),
    ("★ Karambit", "Doppler", "FN", True, False, "1680.00"),
    ("★ Butterfly Knife", "Doppler", "FN", False, False, "2300.00"),
    ("★ M9 Bayonet", "Marble Fade", "FN", False, False, "980.00"),
    ("★ Sport Gloves", "Vice", "MW", False, False, "3200.00"),
    ("★ Specialist Gloves", "Crimson Kimono", "FT", False, False, "410.00"),
    ("★ Driver Gloves", "King Snake", "MW", False, False, "260.00"),
    ("AK-47", "Redline", "FT", False, True, "48.00"),
    ("AWP", "Dragon Lore", "MW", False, True, "6400.00"),
]

SITE_BIAS: dict[str, Decimal] = {
    "skinport": Decimal("1.00"),
    "dmarket": Decimal("0.94"),
    "waxpeer": Decimal("1.04"),
    "steam": Decimal("1.13"),
    "market_csgo": Decimal("0.97"),
}


def canonical_names() -> list[str]:
    names: list[str] = []
    for weapon, skin, wear, stattrak, souvenir, _base in CATALOG:
        names.append(
            build_canonical_name(
                weapon=weapon,
                skin_name=skin,
                wear=wear,
                stattrak=stattrak,
                souvenir=souvenir,
            )
        )
    return names


def quote(base: Decimal, slug: str, item_index: int, tick: int) -> Decimal:
    """Stable per item/site/tick price with a few deliberate underpriced buys."""
    rng = random.Random(item_index * 997 + tick * 13 + sum(ord(c) for c in slug))
    noise = Decimal(str(round(0.96 + rng.random() * 0.08, 4)))
    price = base * SITE_BIAS.get(slug, Decimal("1")) * noise
    # Every 5th skin is cheap on DMarket and rich on Waxpeer so profit is obvious.
    if item_index % 5 == 0 and slug == "dmarket":
        price *= Decimal("0.84")
    if item_index % 5 == 0 and slug == "waxpeer":
        price *= Decimal("1.06")
    if item_index % 7 == 0 and slug == "market_csgo":
        price *= Decimal("0.90")
    return price.quantize(Decimal("0.01"))


def listings_for_site(slug: str, tick: int = 0) -> list[Listing]:
    rows: list[Listing] = []
    for index, (weapon, skin, wear, stattrak, souvenir, base_raw) in enumerate(CATALOG):
        name = build_canonical_name(
            weapon=weapon,
            skin_name=skin,
            wear=wear,
            stattrak=stattrak,
            souvenir=souvenir,
        )
        parsed = parse_market_hash_name(name)
        assert parsed is not None
        price = quote(Decimal(base_raw), slug, index, tick)
        rows.append(
            Listing(
                raw_name=name,
                price=price,
                currency="USD",
                listings_count=12 + (index * 3) % 40,
                volume_24h=4 + index % 15,
                bid=(price * Decimal("0.93")).quantize(Decimal("0.01")),
                metadata={"source": "demo"},
            )
        )
    return rows


def history_ticks(days: int = 14) -> list[tuple[datetime, int]]:
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    return [(now - timedelta(days=days - offset), offset) for offset in range(days + 1)]
