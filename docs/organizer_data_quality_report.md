# 主辦方補充資料品質報告

本報告只列匿名聚合與品質計數。CSV 原始列與 demographic 欄位不會寫入輸出。金額欄位以 `ANONYMIZED_A_CURRENCY` 標記，不視為新台幣。

## 資料範圍

- 總輸入列數：1,051,612
- 完全重複列：3,368
- 去重後列數：1,048,244
- `2026 AI黑客松CDP 電動車主補充資料資料 (T車輛).csv`：3,037 列，cp950，12 欄
- `2026 AI黑客松CDP資料 (T車輛).csv`：1,048,575 列，cp950，12 欄

## 車款與 cohort

| 原始車款名稱 | 列數 | Mapping 狀態 |
| --- | ---: | --- |
| ALTIS | 242,518 | UNMAPPED |
| RAV4 | 148,088 | MAPPED |
| YARIS | 103,373 | UNMAPPED |
| C CROSS | 82,910 | UNMAPPED_AMBIGUOUS |
| VIOS | 80,009 | MAPPED |
| C CROSS HV | 58,984 | MAPPED |
| WISH | 55,987 | UNMAPPED |
| CAMRY-L | 50,856 | UNMAPPED |
| SIENTA | 45,843 | UNMAPPED |
| RAV4 HV | 43,802 | UNMAPPED |
| Y CROSS | 27,247 | UNMAPPED |
| ALTIS HV | 17,333 | MAPPED |
| INNOVA | 17,099 | UNMAPPED |
| CAMRY-h | 12,625 | UNMAPPED |
| C-HR | 12,208 | UNMAPPED |
| CAMRY | 9,347 | MAPPED |
| COROLLA SP | 6,232 | UNMAPPED |
| CAMRY HV | 5,821 | UNMAPPED_AMBIGUOUS |
| PRIUS | 5,778 | UNMAPPED |
| PRIUS C | 5,629 | UNMAPPED |
| AURIS | 4,326 | UNMAPPED |
| CROWN HV | 3,414 | UNMAPPED |
| bZ4X | 3,036 | UNMAPPED_AMBIGUOUS |
| PRIUS PHV | 2,445 | UNMAPPED |
| PRIUS α | 2,091 | UNMAPPED |
| COROLLA X | 1,241 | UNMAPPED |
| COROLLA | 2 | UNMAPPED |

年齡區間採交車日期至 snapshot date 的完整月數；為避免 60 個月同時落入兩區，區間定為 37–59 與 60+。樣本小於門檻者狀態為 `INSUFFICIENT_SAMPLE`，不輸出 benchmark 統計。

| Vehicle ID | 車齡 cohort | 樣本數 | 狀態 |
| --- | --- | ---: | --- |
| `2eb06cdc-08ed-4b23-9154-768c469fcd42` | 0-12 | 1,584 | READY |
| `2eb06cdc-08ed-4b23-9154-768c469fcd42` | 13-24 | 2,367 | READY |
| `2eb06cdc-08ed-4b23-9154-768c469fcd42` | 25-36 | 3,567 | READY |
| `2eb06cdc-08ed-4b23-9154-768c469fcd42` | 37-59 | 6,522 | READY |
| `2eb06cdc-08ed-4b23-9154-768c469fcd42` | 60+ | 65,969 | READY |
| `69963994-f5e4-4736-aa72-dbbd1d651ba2` | 0-12 | 10,176 | READY |
| `69963994-f5e4-4736-aa72-dbbd1d651ba2` | 13-24 | 14,649 | READY |
| `69963994-f5e4-4736-aa72-dbbd1d651ba2` | 25-36 | 8,876 | READY |
| `69963994-f5e4-4736-aa72-dbbd1d651ba2` | 37-59 | 17,119 | READY |
| `69963994-f5e4-4736-aa72-dbbd1d651ba2` | 60+ | 8,164 | READY |
| `9da059ab-1668-4ad9-8db4-58b24a96bb8f` | 0-12 | 1,073 | READY |
| `9da059ab-1668-4ad9-8db4-58b24a96bb8f` | 13-24 | 1,199 | READY |
| `9da059ab-1668-4ad9-8db4-58b24a96bb8f` | 25-36 | 902 | READY |
| `9da059ab-1668-4ad9-8db4-58b24a96bb8f` | 37-59 | 2,731 | READY |
| `9da059ab-1668-4ad9-8db4-58b24a96bb8f` | 60+ | 3,442 | READY |
| `d05b58dc-8017-4071-a72c-903f5c83f78a` | 0-12 | 2,324 | READY |
| `d05b58dc-8017-4071-a72c-903f5c83f78a` | 13-24 | 6,609 | READY |
| `d05b58dc-8017-4071-a72c-903f5c83f78a` | 25-36 | 8,604 | READY |
| `d05b58dc-8017-4071-a72c-903f5c83f78a` | 37-59 | 15,674 | READY |
| `d05b58dc-8017-4071-a72c-903f5c83f78a` | 60+ | 114,877 | READY |
| `fdef4449-9b1d-4f0e-a384-40204e73a828` | 0-12 | 964 | READY |
| `fdef4449-9b1d-4f0e-a384-40204e73a828` | 13-24 | 1,335 | READY |
| `fdef4449-9b1d-4f0e-a384-40204e73a828` | 25-36 | 1,953 | READY |
| `fdef4449-9b1d-4f0e-a384-40204e73a828` | 37-59 | 4,550 | READY |
| `fdef4449-9b1d-4f0e-a384-40204e73a828` | 60+ | 8,531 | READY |

## 缺漏與無效值

| 欄位 | 缺漏數 | 缺漏率 |
| --- | ---: | ---: |
| service_amount | 0 | 0.00% |
| service_visits | 0 | 0.00% |
| paid_service_visits | 0 | 0.00% |
| scheduled_visits | 0 | 0.00% |
| maintenance_amount | 0 | 0.00% |
| repair_visits | 0 | 0.00% |
| vehicle_model | 0 | 0.00% |
| delivery_date | 0 | 0.00% |

交車日期無法解析：0；未來交車日期：0。

### 無效數值

- 未發現無效數值。

## 疑似離群值

離群值以各欄位 1.5×IQR 作品質提示，不自動刪除。金額只保留 A 國匿名幣值名稱，不換算、不進 TCO。

- service_amount：54,996 筆
- service_visits：24,017 筆
- paid_service_visits：15,168 筆
- scheduled_visits：6,138 筆
- maintenance_amount：25,187 筆
- repair_visits：31,228 筆

## Mapping 限制

名稱若對應多個目前 active `vehicle_profiles` 車型/trim，標記 `UNMAPPED_AMBIGUOUS`；沒有精確候選則標記 `UNMAPPED`。不以品牌、車系或人口特徵猜測 ID。
