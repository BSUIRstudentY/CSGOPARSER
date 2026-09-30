"""Parse Steam market-hash names into one canonical item identity.

Exact identity is the normalized match key. Fuzzy matching only suggests a link
when the key is new and an existing key is very close; low-confidence hits are
flagged for a person to confirm instead of being merged automatically.
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

WEAR_LABELS: dict[str, str] = {
    "FN": "Factory New",
    "MW": "Minimal Wear",
    "FT": "Field-Tested",
    "WW": "Well-Worn",
    "BS": "Battle-Scarred",
}
WEAR_FROM_LABEL: dict[str, str] = {label: code for code, label in WEAR_LABELS.items()}

_WEAR_RE = re.compile(r"\((Factory New|Minimal Wear|Field-Tested|Well-Worn|Battle-Scarred)\)\s*$")
_STATTRAK_PREFIXES = ("StatTrak™ ", "StatTrak ")


@dataclass(frozen=True)
class ParsedItem:
    weapon: str
    skin_name: str
    wear: str | None
    stattrak: bool
    souvenir: bool
    canonical_name: str
    match_key: str


@dataclass(frozen=True)
class MatchDecision:
    """item_key is an existing match_key. create_new means mint a catalog row."""

    item_key: str | None
    method: str
    confidence: float
    needs_review: bool
    create_new: bool


def build_canonical_name(
    *,
    weapon: str,
    skin_name: str,
    wear: str | None,
    stattrak: bool,
    souvenir: bool,
) -> str:
    star = weapon.startswith("★")
    weapon_body = weapon[1:].strip() if star else weapon.strip()
    tokens: list[str] = []
    if star:
        tokens.append("★")
    if souvenir:
        tokens.append("Souvenir")
    if stattrak:
        tokens.append("StatTrak™")
    tokens.append(weapon_body)
    left = " ".join(tokens)
    base = f"{left} | {skin_name.strip()}" if skin_name.strip() else left
    if wear:
        label = WEAR_LABELS.get(wear, wear)
        base = f"{base} ({label})"
    return base


def make_match_key(canonical_name: str) -> str:
    text = canonical_name.lower().replace("™", "").replace("★", " star ")
    text = re.sub(r"[^a-z0-9|]+", " ", text)
    text = re.sub(r"\s*\|\s*", " | ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_market_hash_name(raw: str) -> ParsedItem | None:
    name = " ".join(raw.replace("StatTrakTM", "StatTrak").split())
    if not name:
        return None

    stattrak = False
    souvenir = False
    star = False
    progressed = True
    while progressed:
        progressed = False
        if name.startswith("★"):
            star = True
            name = name[1:].strip()
            progressed = True
        if name.startswith("Souvenir "):
            souvenir = True
            name = name[len("Souvenir ") :].strip()
            progressed = True
        for prefix in _STATTRAK_PREFIXES:
            if name.startswith(prefix):
                stattrak = True
                name = name[len(prefix) :].strip()
                progressed = True
                break

    wear: str | None = None
    wear_match = _WEAR_RE.search(name)
    if wear_match:
        wear = WEAR_FROM_LABEL[wear_match.group(1)]
        name = name[: wear_match.start()].strip()

    if "|" in name:
        weapon, skin_name = (part.strip() for part in name.split("|", 1))
    else:
        weapon, skin_name = name.strip(), ""
    if not weapon:
        return None
    if star:
        weapon = f"★ {weapon}"

    canonical = build_canonical_name(
        weapon=weapon,
        skin_name=skin_name,
        wear=wear,
        stattrak=stattrak,
        souvenir=souvenir,
    )
    return ParsedItem(
        weapon=weapon,
        skin_name=skin_name,
        wear=wear,
        stattrak=stattrak,
        souvenir=souvenir,
        canonical_name=canonical,
        match_key=make_match_key(canonical),
    )


class CatalogMatcher:
    def __init__(
        self,
        keys: list[str],
        *,
        auto_threshold: float,
        review_threshold: float,
        fuzzy_budget: int,
    ) -> None:
        self._keys = set(keys)
        self._key_list = list(keys)
        self._auto = auto_threshold
        self._review = review_threshold
        self.budget = fuzzy_budget

    def add_key(self, key: str) -> None:
        if key not in self._keys:
            self._keys.add(key)
            self._key_list.append(key)

    def match(self, parsed: ParsedItem) -> MatchDecision:
        if parsed.match_key in self._keys:
            return MatchDecision(parsed.match_key, "canonical", 1.0, False, False)
        if self.budget <= 0 or not self._key_list:
            return MatchDecision(None, "created", 1.0, False, True)
        self.budget -= 1
        # token_sort_ratio tolerates swapped tokens; ratio catches small typos.
        hit = process.extractOne(
            parsed.match_key,
            self._key_list,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=self._review,
        )
        if hit is None:
            return MatchDecision(None, "created", 1.0, False, True)
        key, score, _index = hit
        confidence = float(score) / 100.0
        if score >= self._auto:
            return MatchDecision(str(key), "fuzzy", confidence, False, False)
        # Close but not safe to merge. Caller stores a suggestion and skips the price.
        return MatchDecision(str(key), "fuzzy", confidence, True, False)
