insert into knowledge_sources (id, publisher, title, url, category, content, verified_at, valid_until)
values (
  'src_ev_commodity_tax_exemption', '財政部稅務入口網', '免徵及退稅規定',
  'https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-saving-manual/national/commodity-tax/0kPmZDo',
  'POLICY',
  '依《貨物稅條例》第 12 條之 3，自 2017/1/28 至 2030/12/31，購買完全以電能為動力的電動車輛並完成新領牌照登記者，可免徵其應徵貨物稅。但電動小客車免徵金額，以完稅價格新臺幣 140 萬元計算的稅額為限；超過部分不予免徵。140 萬元是完稅價格的計算基準上限，並不是直接減免 140 萬元。',
  timestamptz '2026-09-26 00:00:00+08', timestamptz '2030-12-31 23:59:59+08'
)
on conflict (id) do update set publisher = excluded.publisher, title = excluded.title, url = excluded.url,
  category = excluded.category, content = excluded.content, verified_at = excluded.verified_at, valid_until = excluded.valid_until;
