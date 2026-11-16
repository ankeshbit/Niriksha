"""
tests/test_upload_concurrency.py

Verifies that image upload processing runs concurrently via threadpool
without one request stalling another.
"""

import io
import time
import asyncio
import threading
import pytest
from PIL import Image
import httpx

from backend.main import app
from backend.config import settings


def create_test_image(color=(100, 150, 200), width=300, height=300) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_concurrent_image_uploads_do_not_stall(monkeypatch):
    """
    Simulates two simultaneous image uploads.
    Verifies that blocking quality checks execute concurrently in threadpool
    workers without serializing or blocking the event loop.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Login
        login_res = await ac.post("/api/auth/login", json={
            "officer_id": settings.SEED_OFFICER_ID,
            "password": settings.SEED_OFFICER_PASSWORD
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create inspection for upload tests
        create_resp = await ac.post("/api/inspections", json={
            "product_name": "Concurrency Test Product",
            "category": "Packaged Food",
            "location": "Concurrency Test Lab",
            "brand_name": "ConcurrentBrand",
            "inspection_type": "PHYSICAL"
        }, headers=headers)
        assert create_resp.status_code == 201, f"Create inspection failed: {create_resp.text}"
        inspection_id = create_resp.json()["id"]

        # 3. Instrument assess_image_quality with a Barrier(2)
        # If execution were serialized on the main event loop, waiting at the barrier
        # would freeze the loop and cause a BrokenBarrierError timeout.
        # Running in threadpool allows both threads to reach the barrier concurrently.
        import backend.main as main_mod
        original_assess = main_mod.assess_image_quality

        barrier = threading.Barrier(2, timeout=10.0)
        concurrency_stats = {
            "active": 0,
            "max_concurrent": 0,
            "calls": 0
        }

        def instrumented_assess(*args, **kwargs):
            concurrency_stats["active"] += 1
            concurrency_stats["calls"] += 1
            if concurrency_stats["active"] > concurrency_stats["max_concurrent"]:
                concurrency_stats["max_concurrent"] = concurrency_stats["active"]

            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass

            try:
                return original_assess(*args, **kwargs)
            finally:
                concurrency_stats["active"] -= 1

        monkeypatch.setattr(main_mod, "assess_image_quality", instrumented_assess)

        # 4. Prepare two distinct image upload payloads
        img1 = create_test_image(color=(255, 0, 0))
        img2 = create_test_image(color=(0, 255, 0))

        t0 = time.time()
        res1, res2 = await asyncio.gather(
            ac.post(
                f"/api/inspections/{inspection_id}/images",
                files={"file": ("front.jpg", img1, "image/jpeg")},
                data={"view_type": "front"},
                headers=headers
            ),
            ac.post(
                f"/api/inspections/{inspection_id}/images",
                files={"file": ("back.jpg", img2, "image/jpeg")},
                data={"view_type": "back"},
                headers=headers
            )
        )
        total_duration = time.time() - t0

    # 5. Assert both requests succeeded
    assert res1.status_code == 201, f"Upload 1 failed: {res1.text}"
    assert res2.status_code == 201, f"Upload 2 failed: {res2.text}"

    # 6. Assert concurrency: both executed at the same time in separate threads
    assert concurrency_stats["calls"] == 2
    assert concurrency_stats["max_concurrent"] >= 2, (
        f"Expected concurrent execution (max_concurrent >= 2), but got {concurrency_stats['max_concurrent']}. "
        "Uploads appear to be serialized."
    )

    print(f"\n[OK] Concurrent uploads completed in {total_duration:.2f}s (max_concurrent={concurrency_stats['max_concurrent']})")
