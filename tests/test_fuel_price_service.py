import httpx

from app.services.fuel_price_service import FuelPriceQuote, FuelPriceService


class FakeReferenceRepository:
    def __init__(self, today: dict | None = None, latest: dict | None = None) -> None:
        self.today = today
        self.latest = latest
        self.saved: list[dict] = []

    def get_today_reference_parameter(self, parameter_key: str) -> dict | None:
        return self.today

    def get_latest_reference_parameter(self, parameter_key: str) -> dict | None:
        return self.latest

    def save_reference_parameter(self, **record: object) -> None:
        self.saved.append(record)


def test_parses_95_unleaded_from_cpc_xml() -> None:
    xml = """<Dataset>
      <Table><產品名稱>92無鉛汽油</產品名稱><銷售對象>一般自用客戶</銷售對象><交貨地點>中油自營站</交貨地點><參考牌價_金額>31.2</參考牌價_金額><牌價生效日期>1150921</牌價生效日期></Table>
      <Table><產品名稱>95無鉛汽油</產品名稱><銷售對象>一般自用客戶 </銷售對象><交貨地點>中油自營站</交貨地點><參考牌價_金額>32.7000</參考牌價_金額><牌價生效日期>1150921</牌價生效日期></Table>
    </Dataset>"""

    quote = FuelPriceService._parse_quote(xml)

    assert quote.price_per_liter == 32.7
    assert quote.effective_date == "2026-09-21"


def test_uses_todays_database_price_without_an_official_request() -> None:
    repository = FakeReferenceRepository(today={"value_numeric": "32.7", "effective_date": "2026-09-21", "source_url": "https://example.com"})
    service = FuelPriceService(repository=repository)
    service._fetch_official_quote = lambda: (_ for _ in ()).throw(AssertionError())

    quote = service.latest_95_unleaded()

    assert quote is not None
    assert quote.origin == "database_today"
    assert quote.price_per_liter == 32.7


def test_uses_latest_database_record_when_official_source_is_unavailable() -> None:
    repository = FakeReferenceRepository(latest={"value_numeric": "32.7", "effective_date": "2026-09-21", "source_url": "https://example.com"})
    service = FuelPriceService(repository=repository)
    service._fetch_official_quote = lambda: (_ for _ in ()).throw(httpx.ConnectError("offline"))

    quote = service.latest_95_unleaded()

    assert quote is not None
    assert quote.origin == "database_fallback"


def test_does_not_write_shared_official_quote_from_a_chat_request() -> None:
    repository = FakeReferenceRepository()
    service = FuelPriceService(repository=repository)
    service._fetch_official_quote = lambda: FuelPriceQuote(32.7, "2026-09-21")

    service.latest_95_unleaded()

    assert repository.saved == []
