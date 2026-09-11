"""
tests/test_api_host_safety.py

Static analysis verification ensuring mobile/src/services/api.ts contains no hardcoded
personal development LAN IP addresses and properly supports EXPO_PUBLIC_API_URL.
"""

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
API_TS_PATH = BASE_DIR / "mobile" / "src" / "services" / "api.ts"

def test_api_ts_no_hardcoded_private_lan_ip():
    """Verify api.ts has no hardcoded LAN IP like 10.185.115.213 or any private IP range."""
    assert API_TS_PATH.exists(), f"File {API_TS_PATH} not found"
    content = API_TS_PATH.read_text(encoding="utf-8")

    # Specifically check for old hardcoded IP
    assert "10.185.115.213" not in content, "Found hardcoded personal laptop IP 10.185.115.213 in api.ts!"

    # Regex for IPv4 addresses (non-capturing groups)
    ip_pattern = re.compile(r'\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3})\b')
    matches = ip_pattern.findall(content)

    for ip in matches:
        # 10.0.2.2 is the official standard Android Emulator loopback host, which is permitted
        if ip != "10.0.2.2":
            raise AssertionError(f"Forbidden hardcoded private LAN IP address '{ip}' found in mobile/src/services/api.ts!")

def test_api_ts_uses_expo_public_api_url():
    """Verify api.ts reads process.env.EXPO_PUBLIC_API_URL for configuration."""
    content = API_TS_PATH.read_text(encoding="utf-8")
    assert "EXPO_PUBLIC_API_URL" in content, "mobile/src/services/api.ts must reference EXPO_PUBLIC_API_URL for configurable API endpoint."

def test_api_ts_android_emulator_default():
    """Verify api.ts includes 10.0.2.2 default for Android emulator."""
    content = API_TS_PATH.read_text(encoding="utf-8")
    assert "10.0.2.2:8000" in content, "mobile/src/services/api.ts must default to 10.0.2.2:8000 on Android when EXPO_PUBLIC_API_URL is unset."
