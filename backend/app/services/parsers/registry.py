"""Parser lookup. Adding a marketplace starts by registering a client here."""

from app.services.parsers.base import MarketplaceParser
from app.services.parsers.dmarket import DMarketParser
from app.services.parsers.market_csgo import MarketCsgoParser
from app.services.parsers.skinport import SkinportParser
from app.services.parsers.steam import SteamParser
from app.services.parsers.waxpeer import WaxpeerParser

PARSERS: dict[str, MarketplaceParser] = {
    parser.slug: parser
    for parser in (
        SkinportParser(),
        DMarketParser(),
        WaxpeerParser(),
        SteamParser(),
        MarketCsgoParser(),
    )
}


def get_parser(slug: str) -> MarketplaceParser | None:
    return PARSERS.get(slug)
