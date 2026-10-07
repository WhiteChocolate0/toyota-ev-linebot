# 主辦方補充資料整合報告

日期：2026-10-04

## 已整合

- 建立 `scripts/analyze_organizer_cdp.py` 離線分析流程：支援 UTF-8 / CP950 / Big5、欄名換行與空白、數值清理、交車日期解析、完全重複列偵測、車齡 cohort 及保守 vehicle ID mapping。
- 對 2026 兩份 T 車輛 CSV 完成匿名聚合。本機 staging 產物在 `artifacts/organizer_data_analysis/`：`internal_concern_priorities.csv`、`vehicle_alias_mapping.csv`、`internal_vehicle_service_benchmarks.csv` 及品質 JSON。沒有輸出 raw records，也沒有把 demographic 欄位寫入 aggregate。
- 將 2025 W3 調查轉為內部 concern priority taxonomy。權重只供產品排序，不推論個人偏好，也不在對話顯示調查比例。
- 新增 `InternalInsightsService`，只回 structured aggregate data；強制 vehicle age cohort，樣本數低於 30 時回 `INSUFFICIENT_SAMPLE`，幣值固定標示 `ANONYMIZED_A_CURRENCY`。
- 私聊的不確定探索加入中立 Quick Reply；只顯示疑慮選項、不顯示市場調查比例。群組不自動套用個人探索入口。Concern board 只對實際存在的議題排序。
- Public RAG 僅允許 `PUBLIC` visibility 或明確官方 source type；Organizer research 與 CDP source type 會被拒絕。官方來源仍是規格、價格、保固與政策的唯一證據層。

## 只供內部使用／禁止 user-facing

- `INTERNAL_ORGANIZER_RESEARCH`：疑慮排序、onboarding、FAQ shortcut 與分析。不可呈現報告、原始頁面、完整內部比例或下載連結。
- `INTERNAL_AGGREGATED_CDP`：只供匿名 cohort benchmark 與內部分析。個別資料列不供回答、RAG、推薦或 TCO 使用。
- A 國匿名金額目前只保留相對 benchmark 欄位；不換算新台幣、不使用 `NT$`、不併入正式 TCO。
- demographic 欄位雖存在於來源 CDP，未用於推薦或聚合分群。

## 本次離線品質結果

- 輸入總列數 1,051,612；完全重複列 3,368；去重後 1,048,244。
- 交車日期無法解析 0、未來日期 0；數值欄位無效值 0。
- 只有唯一對應到 active shared profile 的車款才建立 cohort。多個 profile 候選標記 `UNMAPPED_AMBIGUOUS`；無唯一現行目錄對照者標記 `UNMAPPED`。本批 `UNMAPPED_AMBIGUOUS` 包含 bZ4X、C CROSS、CAMRY HV；`UNMAPPED` 包含 RAV4 HV 等沒有唯一 ID 的名稱。完整清單見品質報告與 mapping CSV。
- Benchmark 依 `0-12`、`13-24`、`25-36`、`37-59`、`60+` 個完整月分組；樣本門檻為 30。離群值只標記、不自動刪除。

## 尚未使用／排除

- 沒有用 CDP 維修金額修改正式 TCO，也沒有把 A 國幣值換算成台幣。
- 未唯一對照的車款不納入 vehicle benchmark；不以名稱猜測 ID。
- 尚未匯入任何 Production internal table。依要求先做 schema readiness，結果為 `BLOCKED`，因此不寫入資料庫。

## Production readiness blocker

唯讀 Supabase schema check 指向 `extkwpghjfttamontqkl.supabase.co`，但目前設定 `APP_ENV=development`。檢查發現 `linebot` schema 未被 PostgREST 暴露，Bot state tables 仍由 `public` 回應（LEGACY）；`campaign.campaign_link_tokens`、`public.tax_rules`、`public.energy_prices` 缺失；campaign 實際 token table 名稱也與程式期待不一致。此外，本次 internal insight tables 尚不存在。沒有執行 migration、DB 寫入或 production state 修改。

因此本次成果是本機離線 staging 與程式隔離，不是 Production import。需先確認實際 schema/table contract、API schema exposure 與環境指向，再重跑 readiness；不可僅因 migration 曾執行便匯入或部署。
