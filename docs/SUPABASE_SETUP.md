# Supabase 設定｜LINE Bot MVP
## 你需要完成的操作

1. 建立一個新的 Supabase project，區域選擇距離主要使用者較近的亞洲區域。
2. 在 **SQL Editor** 依序貼上並執行：
   - `supabase/001_initial_schema.sql`
   - `supabase/002_vehicle_profiles.sql`
   - `supabase/003_reference_parameters.sql`
   - `supabase/006_official_energy_efficiencies.sql`
   - `supabase/009_cost_calculations.sql`
   - `supabase/010_conversation_flows.sql`
   - `supabase/011_cost_calculations_compatibility.sql`
   - `supabase/012_vehicle_features.sql`
   - `supabase/013_official_vehicle_catalog_2026q3.sql`
   - `supabase/014_database_cleanup.sql`
3. 到 **Project Settings → API** 取得 Project URL 與 `service_role` key。
4. 在專案 `.env` 加入以下兩行；不要把內容貼到聊天室或提交版本控制：

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
```

5. 回覆「Supabase schema 已執行」即可。我會先用不顯示憑證的方式確認設定，再把 webhook 的記憶體去重改為資料庫去重。

`003_reference_parameters.sql` 會建立共用的外部參數快取。成本試算會先取用當天同步的中油 95 無鉛牌價；沒有才查中油官方並回寫。中油暫時不可用時，會採用資料庫最新一筆並在結果中標示為快取備援。

`006_official_energy_efficiencies.sql` 將官方公告的油耗與用電效率分開保存；PHEV 必須同時填寫兩者。

`013_official_vehicle_catalog_2026q3.sql` 匯入已核對的官方售價與效率資料、設定季度複核日期與資料到期日，並建立 `vehicle_profile_quality_issues` 品質檢核 view。

`014_database_cleanup.sql` 移除未使用的早期 TCO 規則表與 `group_summaries`、清除未設有效期限的 2026-09-20 舊車款種子資料，並補回受治理的 COROLLA CROSS 汽油車型。正式上線前請依 [官方車款資料驗收](VEHICLE_CATALOG_ACCEPTANCE.md) 完成資料庫、LINE 與程式驗收。

## 安全檢查

- `service_role` key 只能放在後端 `.env`，絕不可放進前端、LIFF、分享連結或 Git。
- 資料表已啟用 RLS；未設定瀏覽器端存取 policy，匿名使用者無法直接讀取資料。
- `conversation_events.summary` 只應保存結構化摘要，不保存無關的群組原文。
