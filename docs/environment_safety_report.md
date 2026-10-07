# Database Environment Safety Report

日期：2026-10-04

## 規則

`validate_database_environment()` 會比對 `APP_ENV`、`SUPABASE_URL`、`SUPABASE_PROJECT_REF` 與 `PRODUCTION_SUPABASE_PROJECT_REF`。

| APP_ENV | 可連資料庫 |
| --- | --- |
| `development` | 僅 DEV project |
| `test` | FakeRepository 或 TEST / DEV project |
| `production` | 僅設定的 Production project |

`development` 或 `test` 指到 Production ref，以及 `production` 指到非 Production ref，皆會拋出 `EnvironmentSafetyError` 並以 exit 1 結束。aggregate import 與 integration-test write 另使用 `require_nonproduction_database_write()`，一律拒絕 Production。

## 本次觀測

本機設定為 `APP_ENV=development`，但 URL project ref 為 `extkwpghjfttamontqkl`（Production）。因此所有 runtime database access、migration、seed、aggregate import 與 integration-test write 現在都被 fail-closed 阻擋。這是預期保護，不是可忽略的 warning。

## 使用方式

- DEV：設定不同於 Production 的 `SUPABASE_URL` 與 `SUPABASE_PROJECT_REF`。
- TEST：優先使用 FakeRepository；若 integration test 寫 DB，須同時設定非 Production 的 `TEST_SUPABASE_URL` / key。
- Production deploy：`APP_ENV=production`，且 project ref 必須等於 `PRODUCTION_SUPABASE_PROJECT_REF`。

Production schema audit 必須由已正確設定為 `production` 的唯讀工作階段執行；不能靠把本機 APP_ENV 改成 development 再連 Production。
