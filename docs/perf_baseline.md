# Performance Baseline

Measured on: 2026-11-16 13:51:43 UTC
Iterations per endpoint: 20
Target host: http://127.0.0.1:8000

| Endpoint | p50 (ms) | p95 (ms) | Mean (ms) | Min (ms) | Max (ms) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `upload image` | **8907.17** | **10227.62** | 9147.35 | 8379.38 | 12196.52 | OK |
| `start OCR` | **3241.38** | **3809.93** | 3378.05 | 2474.07 | 5779.06 | OK |
| `GET compliance-summary` | **5065.41** | **6073.22** | 5085.35 | 4100.32 | 7304.65 | OK |
| `GET /api/inspections` | **10456.41** | **13104.33** | 10828.32 | 9418.49 | 13279.89 | OK |
| `GET /api/repository/products` | **1840.78** | **2302.13** | 1936.07 | 1642.66 | 3493.81 | OK |
| `GET /api/dashboard/summary` | **1482.34** | **2150.87** | 1540.80 | 1237.51 | 2161.71 | OK |

### Endpoint Details
1. **upload image**: `POST /api/inspections/{id}/images` (Multi-part image upload with OpenCV quality check in threadpool)
2. **start OCR**: `POST /api/inspections/{id}/ocr` (Non-blocking async OCR job dispatch returning 202/200)
3. **GET compliance-summary**: `GET /api/inspections/{id}/compliance-summary` (Aggregate compliance calculation with cached declaration matrix)
4. **GET /api/inspections**: `GET /api/inspections` (Inspection listing using `selectinload` and count subqueries)
5. **GET /api/repository/products**: `GET /api/repository/products` (Product catalog with SQL-level grouping and pagination)
6. **GET /api/dashboard/summary**: `GET /api/dashboard/summary` (Conditional aggregation via `func.count().filter(...)`)
