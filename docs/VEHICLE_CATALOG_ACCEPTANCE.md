# 官方車款資料｜正式驗收

本驗收的目的，是確認 LINE Bot 只會自動採用可追溯、尚未過期，且符合車款動力型態的 TOYOTA 台灣官方資料。

## 前置條件

1. 已依序執行 `001` 至 `012` migration。
2. 在 Supabase SQL Editor 執行 `supabase/013_official_vehicle_catalog_2026q3.sql`。
3. 後端環境變數已設定 Supabase 與 LINE 憑證；本機服務可用 `.venv/bin/uvicorn app.main:app --reload --port 8000` 啟動。
4. 測試前確認目前日期早於 migration 的 `valid_until`；此版為 `2026-12-31 23:59:59+08`。若已到期，先完成新的官方資料審核與版本更新，不可延長舊資料有效期。

## A. 資料庫驗收

1. 在 SQL Editor 執行：

   ```sql
   select * from vehicle_profile_quality_issues where issue is not null;
   ```

   預期：**0 筆**。若有任何資料列，禁止將該資料列當成自動帶入資料。

2. 檢查本次核心車款的來源、期限與效率欄位：

   ```sql
   select model_name, trim_name, drivetrain, purchase_price_ntd,
          fuel_efficiency_km_per_l, electric_efficiency_km_per_kwh,
          source_url, verified_at, valid_until, review_due_at
   from vehicle_profiles
   where is_active = true
     and model_name in ('COROLLA CROSS', 'YARiS CROSS', 'bZ4X',
                        'URBAN CRUISER', 'PRIUS PHEV', 'RAV4')
   order by model_name, trim_name;
   ```

   預期：每列都有 `https://www.toyota.com.tw/` 來源、`verified_at`、`valid_until` 與 `review_due_at`；BEV 具 `electric_efficiency_km_per_kwh`，PHEV 同時具油耗與電耗。

3. 比對官方頁面：逐一開啟查詢結果中的 `source_url`，確認車名、等級、建議售價與效率和資料表完全一致。不可只比較車系名稱；必須比較到等級。

4. 失效保護測試（測完須復原）：

   ```sql
   update vehicle_profiles
   set valid_until = now() - interval '1 minute'
   where model_name = 'bZ4X' and trim_name = 'bZ4X';
   ```

   接著在 LINE 成本試算選 bZ4X，預期 Bot 不顯示該過期卡片／不自動帶入 6.7 km/kWh；若使用者以文字選到該車，必須要求手動電耗。完成後重新執行 `013` 恢復資料，再執行步驟 1，預期回到 0 筆。

5. 停用保護測試（測完須復原）：將同一車列 `is_active` 改為 `false`，重做上一步 LINE 選車，預期同樣不會被 Carousel 或 ID 查詢選到。再執行 `013` 恢復。

## B. LINE 實機驗收

1. 在 1:1 對話輸入「成本試算」，依序選「油電車」→「COROLLA CROSS」→「純電車」→「bZ4X」→「快速試算」→每月 `1200` km→`5 年`。

   預期：車款卡分別帶入 COROLLA CROSS HYBRID 23.5 km/L、bZ4X 6.7 km/kWh；結果卡顯示官方效率與車價，不要求手動輸入效率。

2. 重做試算，選「插電式油電車」→「PRIUS PHEV」→任一比較車。 

   預期：PHEV 車卡可選，流程保留 PHEV 用電比例題；不應將 PHEV 當成單一油耗或單一電耗車款。

3. 重做試算，選「純電車」→「URBAN CRUISER」。

   預期：車卡顯示 6.8 km/kWh 與 NT$1,270,000；快速試算不要求手動電耗。

4. 在群組讓 A 啟動試算並停在選車階段；B 點選 A 的車款卡。

   預期：B 的 postback 不得改變 A 的流程。B 自己輸入「成本試算」後才能得到自己的選車卡。

5. 任一結果卡點「看完整成本」，確認完整 TCO 仍沿用該車款的官方車價與能耗；若使用者輸入不同成交價，只覆蓋該次試算，不得修改 `vehicle_profiles`。

## C. 程式驗收

在專案根目錄執行：

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

預期：全數通過，至少包含 `test_vehicle_catalog_governance.py`、車款 Carousel、成本流程、PHEV 與資料過期保護的既有測試。

## 維護節奏與處置

- 每季、任何 Toyota 台灣價格／規格異動公告後，以及 `review_due_at` 到期前，重新對照官方規配表。
- 新資料先以新的 catalog version 建檔，完成本文件 A～C 驗收後才標記 `is_active=true`。
- 舊資料須設定 `is_active=false` 或保留已過期的 `valid_until`，不可覆寫其來源時間，才能保留試算審計軌跡。
