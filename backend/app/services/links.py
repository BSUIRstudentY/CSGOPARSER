"""Public marketplace pages for a market-hash name.

These are the same pages a person opens to check the price and buy. They are
not trade or sell links.
"""

import re
from typing import Any
from urllib.parse import quote


def listing_url(slug: str, canonical_name: str, details: dict[str, Any] | None = None) -> str:
    stored = (details or {}).get("item_page")
    if isinstance(stored, str) and stored.startswith("http"):
        return stored
    encoded = quote(canonical_name, safe="")
    if slug == "steam":
        return f"https://steamcommunity.com/market/listings/730/{encoded}"
    if slug == "skinport":
        slug_name = canonical_name.lower().replace("★", " ").replace("™", "")
        slug_name = re.sub(r"[^a-z0-9]+", "-", slug_name).strip("-")
        return f"https://skinport.com/item/csgo/{slug_name}"
    if slug == "dmarket":
        return f"https://dmarket.com/ingame-items/item-list/csgo-skins?title={encoded}"
    if slug == "waxpeer":
        return f"https://waxpeer.com/csgo?search={encoded}"
    if slug == "market_csgo":
        return f"https://market.csgo.com/en/?search={encoded}"
    return ""
