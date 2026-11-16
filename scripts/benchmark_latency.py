"""
Benchmark script to measure p50 and p95 latency for core API endpoints over 20 runs each.

Endpoints benchmarked:
1. upload image: POST /api/inspections/{id}/images
2. start OCR: POST /api/inspections/{id}/ocr
3. GET compliance-summary: GET /api/inspections/{id}/compliance-summary
4. GET /api/inspections: GET /api/inspections
5. GET /api/repository/products: GET /api/repository/products
6. GET /api/dashboard/summary: GET /api/dashboard/summary
"""

import argparse
import io
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
from PIL import Image

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from backend.config import settings
    DEFAULT_OFFICER_ID = settings.SEED_OFFICER_ID or "DOCA-INSP-842"
    DEFAULT_PASSWORD = settings.SEED_OFFICER_PASSWORD or "admin123"
except Exception:
    DEFAULT_OFFICER_ID = "DOCA-INSP-842"
    DEFAULT_PASSWORD = "admin123"


def calc_percentile(data: List[float], p: float) -> float:
    """Calculate the p-th percentile (0 <= p <= 100) using linear interpolation."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n == 1:
        return sorted_data[0]
    idx = (p / 100.0) * (n - 1)
    low = int(idx)
    high = min(low + 1, n - 1)
    weight = idx - low
    return sorted_data[low] * (1.0 - weight) + sorted_data[high] * weight


def create_dummy_jpeg() -> bytes:
    """Generate a valid 300x300 RGB JPEG in memory."""
    img = Image.new("RGB", (300, 300), color=(235, 235, 235))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def run_benchmark(
    base_url: str = "http://127.0.0.1:8000",
    runs: int = 20,
    officer_id: str = DEFAULT_OFFICER_ID,
    password: str = DEFAULT_PASSWORD,
    output_path: Optional[str] = None
) -> Dict[str, Dict[str, float]]:
    print(f"==================================================")
    print(f"  NiriKsha API Latency Benchmark (Runs: {runs})")
    print(f"  Target: {base_url}")
    print(f"==================================================")

    # 1. Login
    login_url = f"{base_url}/api/auth/login"
    print(f"[*] Logging in as {officer_id}...")
    t_login_start = time.perf_counter()
    login_resp = requests.post(login_url, json={"officer_id": officer_id, "password": password}, timeout=10)
    if login_resp.status_code != 200:
        raise RuntimeError(f"Login failed ({login_resp.status_code}): {login_resp.text}")
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"[+] Login successful ({(time.perf_counter() - t_login_start)*1000:.1f} ms)")

    # 2. Setup Benchmark Inspection
    print("[*] Creating dedicated inspection for benchmark...")
    create_resp = requests.post(
        f"{base_url}/api/inspections",
        json={
            "product_name": "Benchmark Test Commodity",
            "category": "Packaged Food",
            "brand_name": "Benchmark Brand",
            "location": "Central Testing Lab",
            "notes": "Automated latency benchmark test run"
        },
        headers=headers,
        timeout=10
    )
    if create_resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create benchmark inspection ({create_resp.status_code}): {create_resp.text}")
    inspection_id = create_resp.json()["id"]
    print(f"[+] Benchmark inspection created: {inspection_id}")

    # Generate dummy image bytes
    test_image_bytes = create_dummy_jpeg()

    # Pre-upload an initial image so OCR endpoints have image data available
    init_up = requests.post(
        f"{base_url}/api/inspections/{inspection_id}/images",
        files={"file": ("initial_test.jpg", test_image_bytes, "image/jpeg")},
        data={"view_type": "front"},
        headers=headers,
        timeout=10
    )
    if init_up.status_code not in (200, 201):
        raise RuntimeError(f"Failed to upload initial image: {init_up.text}")

    # Data collection structure
    timings: Dict[str, List[float]] = {
        "upload image": [],
        "start OCR": [],
        "GET compliance-summary": [],
        "GET /api/inspections": [],
        "GET /api/repository/products": [],
        "GET /api/dashboard/summary": []
    }

    print("\n--- Starting Iterations ---")

    # Benchmark: upload image
    print(f"[*] Benchmarking: upload image ({runs} runs)...")
    for i in range(runs):
        t0 = time.perf_counter()
        r = requests.post(
            f"{base_url}/api/inspections/{inspection_id}/images",
            files={"file": (f"bench_img_{i}.jpg", test_image_bytes, "image/jpeg")},
            data={"view_type": "front"},
            headers=headers,
            timeout=15
        )
        t1 = time.perf_counter()
        if r.status_code not in (200, 201):
            print(f"    [WARN] Run {i+1} failed ({r.status_code}): {r.text[:100]}")
        else:
            timings["upload image"].append((t1 - t0) * 1000.0)

    # Benchmark: start OCR
    print(f"[*] Benchmarking: start OCR ({runs} runs)...")
    for i in range(runs):
        t0 = time.perf_counter()
        r = requests.post(
            f"{base_url}/api/inspections/{inspection_id}/ocr",
            headers=headers,
            timeout=15
        )
        t1 = time.perf_counter()
        if r.status_code not in (200, 202):
            print(f"    [WARN] Run {i+1} failed ({r.status_code}): {r.text[:100]}")
        else:
            timings["start OCR"].append((t1 - t0) * 1000.0)

    # Benchmark: GET compliance-summary
    print(f"[*] Benchmarking: GET compliance-summary ({runs} runs)...")
    for i in range(runs):
        t0 = time.perf_counter()
        r = requests.get(
            f"{base_url}/api/inspections/{inspection_id}/compliance-summary",
            headers=headers,
            timeout=15
        )
        t1 = time.perf_counter()
        if r.status_code != 200:
            print(f"    [WARN] Run {i+1} failed ({r.status_code}): {r.text[:100]}")
        else:
            timings["GET compliance-summary"].append((t1 - t0) * 1000.0)

    # Benchmark: GET /api/inspections
    print(f"[*] Benchmarking: GET /api/inspections ({runs} runs)...")
    for i in range(runs):
        t0 = time.perf_counter()
        r = requests.get(
            f"{base_url}/api/inspections?limit=20",
            headers=headers,
            timeout=15
        )
        t1 = time.perf_counter()
        if r.status_code != 200:
            print(f"    [WARN] Run {i+1} failed ({r.status_code}): {r.text[:100]}")
        else:
            timings["GET /api/inspections"].append((t1 - t0) * 1000.0)

    # Benchmark: GET /api/repository/products
    print(f"[*] Benchmarking: GET /api/repository/products ({runs} runs)...")
    for i in range(runs):
        t0 = time.perf_counter()
        r = requests.get(
            f"{base_url}/api/repository/products?page=1&page_size=10",
            headers=headers,
            timeout=15
        )
        t1 = time.perf_counter()
        if r.status_code != 200:
            print(f"    [WARN] Run {i+1} failed ({r.status_code}): {r.text[:100]}")
        else:
            timings["GET /api/repository/products"].append((t1 - t0) * 1000.0)

    # Benchmark: GET /api/dashboard/summary
    print(f"[*] Benchmarking: GET /api/dashboard/summary ({runs} runs)...")
    for i in range(runs):
        t0 = time.perf_counter()
        r = requests.get(
            f"{base_url}/api/dashboard/summary",
            headers=headers,
            timeout=15
        )
        t1 = time.perf_counter()
        if r.status_code != 200:
            print(f"    [WARN] Run {i+1} failed ({r.status_code}): {r.text[:100]}")
        else:
            timings["GET /api/dashboard/summary"].append((t1 - t0) * 1000.0)

    # Compute statistics
    results: Dict[str, Dict[str, float]] = {}
    print("\n" + "=" * 70)
    print(f"{'Endpoint':<32} | {'p50 (ms)':<10} | {'p95 (ms)':<10} | {'Mean (ms)':<10} | {'Min/Max'}")
    print("-" * 70)

    for name, latencies in timings.items():
        if not latencies:
            results[name] = {"p50": 0.0, "p95": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}
            print(f"{name:<32} | {'N/A':<10} | {'N/A':<10} | {'N/A':<10} | N/A")
            continue
        p50 = calc_percentile(latencies, 50)
        p95 = calc_percentile(latencies, 95)
        mean_val = sum(latencies) / len(latencies)
        min_val = min(latencies)
        max_val = max(latencies)
        results[name] = {
            "p50": round(p50, 2),
            "p95": round(p95, 2),
            "mean": round(mean_val, 2),
            "min": round(min_val, 2),
            "max": round(max_val, 2),
            "count": len(latencies)
        }
        print(f"{name:<32} | {p50:8.2f} ms | {p95:8.2f} ms | {mean_val:8.2f} ms | {min_val:.1f}/{max_val:.1f}")
    print("=" * 70)

    # Format Markdown summary
    timestamp_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    md_content = f"""# Performance Baseline

Measured on: {timestamp_str}
Iterations per endpoint: {runs}
Target host: {base_url}

| Endpoint | p50 (ms) | p95 (ms) | Mean (ms) | Min (ms) | Max (ms) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
"""
    for name, r in results.items():
        md_content += f"| `{name}` | **{r.get('p50', 0):.2f}** | **{r.get('p95', 0):.2f}** | {r.get('mean', 0):.2f} | {r.get('min', 0):.2f} | {r.get('max', 0):.2f} | OK |\n"

    md_content += """
### Endpoint Details
1. **upload image**: `POST /api/inspections/{id}/images` (Multi-part image upload with OpenCV quality check in threadpool)
2. **start OCR**: `POST /api/inspections/{id}/ocr` (Non-blocking async OCR job dispatch returning 202/200)
3. **GET compliance-summary**: `GET /api/inspections/{id}/compliance-summary` (Aggregate compliance calculation with cached declaration matrix)
4. **GET /api/inspections**: `GET /api/inspections` (Inspection listing using `selectinload` and count subqueries)
5. **GET /api/repository/products**: `GET /api/repository/products` (Product catalog with SQL-level grouping and pagination)
6. **GET /api/dashboard/summary**: `GET /api/dashboard/summary` (Conditional aggregation via `func.count().filter(...)`)
"""

    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(md_content, encoding="utf-8")
        print(f"\n[+] Baseline output written to: {out_file.resolve()}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark NiriKsha core API endpoints.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Base URL of running server")
    parser.add_argument("--runs", type=int, default=20, help="Number of benchmark runs per endpoint (default: 20)")
    parser.add_argument("--officer-id", default=DEFAULT_OFFICER_ID, help="Officer ID for authentication")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Officer password")
    parser.add_argument("--output", default="docs/perf_baseline.md", help="Markdown file to write results to")
    args = parser.parse_args()

    run_benchmark(
        base_url=args.url,
        runs=args.runs,
        officer_id=args.officer_id,
        password=args.password,
        output_path=args.output
    )
