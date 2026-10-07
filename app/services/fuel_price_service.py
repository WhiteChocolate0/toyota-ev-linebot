"""Latest official Taiwan CPC 95-unleaded retail price lookup."""

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from xml.etree import ElementTree

import httpx

from app.services.shared_reference_repository import SharedReferenceRepository
from app.services.linebot_repository import get_repository
from app.services.environment_safety import EnvironmentSafetyError

logger = logging.getLogger(__name__)

CPC_PRICE_URL = "https://vipmbr.cpc.com.tw/CPCSTN/ListPriceWebService.asmx/getCPCMainProdListPrice_XML"


@dataclass(frozen=True)
class FuelPriceQuote:
    price_per_liter: float
    effective_date: str
    source_url: str = CPC_PRICE_URL
    origin: str = "official"


class FuelPriceService:
    """Fetches and short-term caches the official 95-unleaded list price."""

    _cache_ttl = timedelta(hours=6)

    parameter_key = "cpc_95_unleaded_self_service"

    def __init__(self, repository: SharedReferenceRepository | None = None) -> None:
        self._cached_quote: FuelPriceQuote | None = None
        self._cached_at: datetime | None = None
        self._repository = repository

    def latest_95_unleaded(self) -> FuelPriceQuote | None:
        now = datetime.now(UTC)
        if self._cached_quote and self._cached_at and now - self._cached_at < self._cache_ttl:
            return self._cached_quote

        try:
            linebot_repository = get_repository() if self._repository is None else None
        except EnvironmentSafetyError:
            # A local calculation may still use the public official fallback,
            # but must not reach a misconfigured database.
            logger.warning("Skipped database fuel-price lookup due to environment safety guard")
            linebot_repository = None
        repository = self._repository or (linebot_repository.shared if linebot_repository else None)
        if repository:
            today_quote = self._quote_from_record(repository.get_today_reference_parameter(self.parameter_key))
            if today_quote:
                self._remember(today_quote)
                return today_quote

        try:
            quote = self._fetch_official_quote()
        except (httpx.HTTPError, ElementTree.ParseError, ValueError, AttributeError):
            logger.warning("Official CPC fuel-price lookup failed")
            if repository:
                fallback_quote = self._quote_from_record(
                    repository.get_latest_reference_parameter(self.parameter_key), origin="database_fallback"
                )
                if fallback_quote:
                    self._remember(fallback_quote)
                    return fallback_quote
            return self._cached_quote
        # Shared reference data is maintained by an admin ingestion job, never
        # by a user-triggered LINE conversation.
        self._remember(quote)
        return quote

    @staticmethod
    def _quote_from_record(record: dict | None, origin: str = "database_today") -> FuelPriceQuote | None:
        if not record:
            return None
        try:
            return FuelPriceQuote(
                price_per_liter=float(record["value_numeric"]),
                effective_date=str(record["effective_date"]),
                source_url=str(record["source_url"]),
                origin=origin,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _fetch_official_quote(self) -> FuelPriceQuote:
        response = httpx.get(CPC_PRICE_URL, timeout=5.0)
        response.raise_for_status()
        return self._parse_quote(response.text)

    def _remember(self, quote: FuelPriceQuote) -> None:
        self._cached_quote = quote
        self._cached_at = datetime.now(UTC)

    @staticmethod
    def _parse_quote(xml_text: str) -> FuelPriceQuote:
        root = ElementTree.fromstring(xml_text)
        for row in root.findall("Table"):
            if (row.findtext("產品名稱") or "").strip() != "95無鉛汽油":
                continue
            if (row.findtext("銷售對象") or "").strip() != "一般自用客戶":
                continue
            if (row.findtext("交貨地點") or "").strip() != "中油自營站":
                continue
            price = float(row.findtext("參考牌價_金額") or "")
            date = FuelPriceService._format_roc_date(row.findtext("牌價生效日期") or "")
            return FuelPriceQuote(price_per_liter=price, effective_date=date)
        raise ValueError("95 unleaded price was absent from CPC response")

    @staticmethod
    def _format_roc_date(value: str) -> str:
        if len(value) != 7 or not value.isdigit():
            raise ValueError("Invalid CPC effective date")
        return f"{int(value[:3]) + 1911:04d}-{value[3:5]}-{value[5:]}"


fuel_price_service = FuelPriceService()
