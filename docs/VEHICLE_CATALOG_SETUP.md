# TOYOTA 車款目錄設定

請在 Supabase SQL Editor 執行：

`supabase/002_vehicle_profiles.sql`

此表會保存每個官方車款／年式／等級的：動力類型、車價、油耗或電耗、別名、來源網址與驗證日期。

執行 `supabase/006_official_energy_efficiencies.sql` 後，請以每個「車型／年式／等級」為單位填入：

- ICE、HEV：`fuel_efficiency_km_per_l`
- BEV：`electric_efficiency_km_per_kwh`
- PHEV：兩欄都必填

請保留 Toyota 官方規配頁 `source_url` 與 `verified_at`。Bot 只會讀取尚未過期的資料，並先讓使用者確認官方值或改填自己的實際數字。

## 匯入規則

- 僅匯入 TOYOTA 台灣官方規配頁可查證的資料。
- 車名與年式不明時，不以推測值取代；Bot 需追問年式或改用手動模式。
- 價格、規格、油耗／電耗設 `valid_until`，到期後不再自動帶入。
- bZ4X 與既有 TOYOTA 車款皆使用相同 schema，才能安全進行比較。
