# TOYOTA 電車解惑所 LINE Bot

以 LINE 協助個人與家庭用可查證資訊討論純電、油電與燃油車。Bot 不替使用者做決定；它整理官方資訊、使用情境與成本假設，協助釐清下一步。

目前 Bot 為 MVP / demo 系統，webhook：`https://toyota-ev-linebot-two.vercel.app/webhook`。共用的 Supabase project `extkwpghjfttamontqkl` 是 **MVP / DEVELOPMENT DB，不是正式 Production**。Challenge Site 已獨立完成 Production 部署與 runtime smoke verification；Bot 本輪沒有部署。

## 目前狀態

- Supabase schema readiness：21/21 READY；Bot state 仍使用 `public`，不在競賽前搬表。
- Campaign handoff：Challenge Site 端已部署；Bot RPC 目前仍回傳舊的 `invalid` 狀態。Canonical RPC function-body 更新與 DB integration tests 因 CLI 帳號無法存取 MVP project 而尚未執行，**handoff DB verification 尚未完成**。
- RPC 更新 SQL、目前 blocker 與後續步驟：[`docs/dev_schema_verification_report.md`](docs/dev_schema_verification_report.md)、[`docs/campaign_linebot_integration_contract.md`](docs/campaign_linebot_integration_contract.md)、[`sql/apply_campaign_handoff_rpc_body.sql`](sql/apply_campaign_handoff_rpc_body.sql)。

## 功能

| 使用情境 | 支援內容 |
| --- | --- |
| 自由問答 | 電池、充電、續航、安全、保養、政策與 TOYOTA 車款；適用時附公開來源。 |
| 選車與比較 | 依預算、空間、家庭、通勤與動力需求承接車款比較。 |
| 成本試算 | 快速／精準能源成本、完整 TCO 與情境分析；區分官方資料、使用者輸入及未知假設。 |
| EV Fit | 依每日里程、長途、車位與補電條件整理適配因素及後續問題。 |
| 家庭群組 | 低干擾回覆、成員各自的 flow、疑慮看板與摘要；避免保存無關聊天原文。 |

可直接試問：`電池可以用多久？`、`RAV4 跟 bZ4X 怎麼比較？`、`成本試算`、`我適合開電動車嗎？`。私聊輸入 `功能`、`選單` 或 `help` 可開啟功能入口；群組成本試算與 EV Fit 綁定啟動者，不會被其他成員接手。

## 系統架構

```text
LINE webhook → 簽章驗證／事件去重 → 對話路由與群組隔離
→ FAQ／選車／比較／成本／EV Fit → 來源與數值檢核
→ Text、Quick Reply 或 Flex Message
```

| 層級 | 技術與責任 |
| --- | --- |
| API | Python 3.12、FastAPI、Vercel Serverless Functions。 |
| LINE | Messaging API、Webhook、Quick Reply、Postback、Flex Message。 |
| Database | Supabase；shared reference、campaign 與 Bot state 按責任隔離。 |
| AI | Gemini 為可選語意／語氣輔助；輸出仍需經 schema、來源與數字檢核。 |

## Database Architecture

目前以實際 MVP schema 為準，不把未來目標誤當現況：

- `public`：shared reference data 與 Bot state tables。Bot state 使用 `BOT_STATE_SCHEMA=public`；目前不建立第二份車款／知識目錄，也不搬動既有 state tables。
- `campaign`：活動網站管理 quiz sessions、answers、results、share results 與 `campaign.link_tokens`。Bot 不查完整 `quiz_answers`，只透過 `public.consume_campaign_handoff(p_token_hash text)` 取得必要摘要。
- Internal organizer data：使用 `internal_*` tables，由 Bot backend 讀取；不得進 public RAG 或直接提供原始調查／CDP 資料給使用者。
- 自動化 conversation tests 使用 FakeRepository，不連 Supabase。任何 DB write、fixture 或 import 都必須先通過 environment safety，且只允許核准的 MVP/DEVELOPMENT project。

正式 Production project 尚未建立。未來正式上線時應另建 Production DB、審核並套用遷移；不得直接將 MVP DB 升格。

## Campaign Handoff

Challenge API 以 participant/session ownership 驗證結果後建立短效 token；DB 只保存 SHA-256 hash。使用者透過 LINE OA deep link 將 raw `campaign_token` 送進 1 對 1 聊天，Bot 再雜湊並呼叫 consume RPC。Group/room 來源不會 consume token；handoff context 只保存短期必要摘要，不保存 raw token、token hash 或 quiz answers。

**目前狀態：DB contract 尚未完成驗證。** Read-only probe 顯示現行 RPC 對未知 token 回傳 `invalid`，尚未符合 canonical error contract。Function-body-only SQL 已備妥，但 CLI 尚無目標 project 存取權；RPC apply 與 DB integration tests 尚未執行。請先閱讀上方 readiness report，取得 project 權限後再套用，禁止用 service-role REST 呼叫繞過 DDL 權限。

## 本機開發

需求：Python 3.12、LINE Messaging API channel，以及核准的 MVP/DEV 設定。單元與 conversation tests 不需要 Supabase 或 Gemini。

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.development.example .env.development
# 在 .env.development 填入核准的 MVP/DEV URL、project ref 與 backend key
.venv/bin/python scripts/check_test_environment.py
.venv/bin/uvicorn app.main:app --reload
```

設定使用 `APP_ENV=development`、`DATABASE_ROLE=development`、`CURRENT_SUPABASE_PROJECT_REF=extkwpghjfttamontqkl`。目前環境優先讀 `.env.development`；test 使用 `.env.test`；Production 只讀 hosting environment 或 `.env.production`。環境專屬檔不存在時，development/test 才會回退 `.env`，仍會經 project-ref safety check。不要提交 `.env*`、API token 或 service-role key；若 safety check 失敗，必須停止，不可繞過。

## 測試與部署 Gate

```sh
.venv/bin/python -m pytest -q
make test-conversations
make predeploy
```

Conversation suite 以 Fake LINE 與 in-memory repository 驅動真實 `EventProcessor`，涵蓋 flow、context、entity carry-over、群組隔離、來源與 UX rules；不連真實 LINE、Gemini 或 Production DB。部署前須確認核心 golden regression 的 `P0 PRODUCT_FAILURE = 0`。DB integration tests 是另一類測試，必須只用明確核准的 MVP/DEV fixtures，並在結束後清理。

## Organizer Supplemental Data

主辦方品牌研究與 CDP 僅用於內部疑慮排序、FAQ shortcut 與匿名聚合洞察，不代表任何個人的偏好。官方規格、價格、保固及政策以 `PUBLIC_OFFICIAL` 為準。原始 CDP 保留離線，aggregate benchmark 需符合唯一車款 mapping、車齡 cohort 與至少 30 筆樣本門檻；年齡、性別、縣市不得作推薦特徵。A 國匿名幣值不是新台幣，不得標示 `NT$` 或納入 TCO。

品質與 mapping 細節見 [`docs/organizer_data_quality_report.md`](docs/organizer_data_quality_report.md)、[`docs/organizer_data_integration_report.md`](docs/organizer_data_integration_report.md) 與 [`docs/unmapped_vehicle_models.md`](docs/unmapped_vehicle_models.md)。

## Database Changes

手動 migration 與安全順序見 [`docs/manual_migration_runbook.md`](docs/manual_migration_runbook.md)。套用前先確認 project ref、環境 safety 與當前 schema report。禁止執行歷史草稿 `supabase/linebot_001_shared_boundary.sql`，也不得 drop、truncate 或搬動既有 Bot state tables。
