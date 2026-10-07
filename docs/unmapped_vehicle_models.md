# Unmapped CDP Vehicle Models

Only `MAPPED` rows with a unique canonical active `vehicle_profiles.id` can enter aggregate benchmarks. This list is generated from the current offline run; no model is guessed.

| Raw model | Rows | Status | Candidate canonical vehicles |
| --- | ---: | --- | --- |
| ALTIS | 242,518 | UNMAPPED | — |
| AURIS | 4,326 | UNMAPPED | — |
| bZ4X | 3,036 | UNMAPPED_AMBIGUOUS | Active bZ4X profiles; exact ID review required |
| C CROSS | 82,910 | UNMAPPED_AMBIGUOUS | Active Corolla Cross family profiles; exact ID review required |
| C-HR | 12,208 | UNMAPPED | — |
| CAMRY HV | 5,821 | UNMAPPED_AMBIGUOUS | Active Camry HEV profiles; exact ID review required |
| CAMRY-h | 12,625 | UNMAPPED | — |
| CAMRY-L | 50,856 | UNMAPPED | — |
| COROLLA | 2 | UNMAPPED | — |
| COROLLA SP | 6,232 | UNMAPPED | — |
| COROLLA X | 1,241 | UNMAPPED | — |
| CROWN HV | 3,414 | UNMAPPED | — |
| INNOVA | 17,099 | UNMAPPED | — |
| PRIUS | 5,778 | UNMAPPED | — |
| PRIUS C | 5,629 | UNMAPPED | — |
| PRIUS PHV | 2,445 | UNMAPPED | — |
| PRIUS α | 2,091 | UNMAPPED | — |
| RAV4 HV | 43,802 | UNMAPPED | — |
| SIENTA | 45,843 | UNMAPPED | — |
| WISH | 55,987 | UNMAPPED | — |
| Y CROSS | 27,247 | UNMAPPED | — |
| YARIS | 103,373 | UNMAPPED | — |

The authoritative complete list and row counts are in `artifacts/organizer_data_analysis/vehicle_alias_mapping.csv`. A data owner must provide a canonical vehicle ID to resolve any row; editing an alias mapping is a reviewed data operation, not an automatic inference.
