import re
import os
import subprocess
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
BUILD_GRADLE_PATH = ROOT_DIR / "mobile" / "android" / "app" / "build.gradle"
GRADLE_PROPERTIES_PATH = ROOT_DIR / "mobile" / "android" / "gradle.properties"
ROOT_GITIGNORE_PATH = ROOT_DIR / ".gitignore"
ANDROID_GITIGNORE_PATH = ROOT_DIR / "mobile" / "android" / ".gitignore"
EAS_JSON_PATH = ROOT_DIR / "mobile" / "eas.json"


class TestAndroidReleaseSigningConfiguration:
    """Test suite validating secure Android release signing separation and safety invariants."""

    def test_build_gradle_separates_debug_and_release_signing_configs(self):
        """mobile/android/app/build.gradle must have distinct signingConfigs for debug and release."""
        assert BUILD_GRADLE_PATH.exists(), f"Missing {BUILD_GRADLE_PATH}"
        content = BUILD_GRADLE_PATH.read_text(encoding="utf-8")

        # Verify debug block exists
        debug_match = re.search(r"signingConfigs\s*\{[\s\S]*?debug\s*\{[\s\S]*?\}", content)
        assert debug_match is not None, "signingConfigs.debug block not found"
        assert "debug.keystore" in debug_match.group(0)

        # Verify release block exists within signingConfigs
        release_match = re.search(r"signingConfigs\s*\{[\s\S]*?release\s*\{[\s\S]*?\}", content)
        assert release_match is not None, "signingConfigs.release block not found"

    def test_release_build_type_uses_release_signing_config(self):
        """buildTypes.release must NOT use signingConfigs.debug; it must use signingConfigs.release."""
        content = BUILD_GRADLE_PATH.read_text(encoding="utf-8")

        release_build_type = re.search(r"buildTypes\s*\{[\s\S]*?release\s*\{([\s\S]*?)\}", content)
        assert release_build_type is not None, "buildTypes.release block not found"
        release_body = release_build_type.group(1)

        assert "signingConfig signingConfigs.release" in release_body, (
            "buildTypes.release must use signingConfigs.release"
        )
        assert "signingConfig signingConfigs.debug" not in release_body, (
            "CRITICAL: buildTypes.release is still configured with signingConfigs.debug!"
        )

    def test_debug_build_type_uses_debug_signing_config(self):
        """buildTypes.debug must use signingConfigs.debug."""
        content = BUILD_GRADLE_PATH.read_text(encoding="utf-8")
        debug_build_type = re.search(r"buildTypes\s*\{[\s\S]*?debug\s*\{([\s\S]*?)\}", content)
        assert debug_build_type is not None, "buildTypes.debug block not found"
        debug_body = debug_build_type.group(1)

        assert "signingConfig signingConfigs.debug" in debug_body

    def test_release_signing_resolves_secure_environment_and_gradle_variables(self):
        """Release signing must check NIRIKSHA_RELEASE_* env vars and Gradle properties."""
        content = BUILD_GRADLE_PATH.read_text(encoding="utf-8")

        for required_var in [
            "NIRIKSHA_RELEASE_STORE_FILE",
            "NIRIKSHA_RELEASE_STORE_PASSWORD",
            "NIRIKSHA_RELEASE_KEY_ALIAS",
            "NIRIKSHA_RELEASE_KEY_PASSWORD"
        ]:
            assert required_var in content, f"Missing {required_var} reference in build.gradle"

    def test_release_build_fails_safely_when_signing_credentials_are_missing(self):
        """build.gradle must contain an explicit taskGraph guard that throws GradleException when credentials are missing."""
        content = BUILD_GRADLE_PATH.read_text(encoding="utf-8")

        assert "gradle.taskGraph.whenReady" in content, "taskGraph.whenReady hook missing in build.gradle"
        assert "NIRIKSHA ANDROID RELEASE BUILD FAILED" in content, "Clear error message missing in build.gradle"
        assert "GradleException" in content, "GradleException throw statement missing"

    def test_no_keystores_or_private_credentials_in_git(self):
        """Git-tracked files must never include production keystores or signing secrets."""
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            check=True
        )
        tracked_files = res.stdout.splitlines()

        for f in tracked_files:
            if f.endswith((".jks", ".p12", ".pepk")):
                pytest.fail(f"Tracked secret key file found: {f}")
            if f.endswith(".keystore"):
                # Only mobile/android/app/debug.keystore is allowed
                normalized = f.replace("\\", "/")
                assert normalized == "mobile/android/app/debug.keystore", f"Unexpected keystore tracked: {f}"

    def test_gitignore_protects_keystore_files(self):
        """.gitignore files must explicitly ignore *.keystore and *.jks."""
        root_gi = ROOT_GITIGNORE_PATH.read_text(encoding="utf-8")
        assert "*.keystore" in root_gi
        assert "*.jks" in root_gi

        android_gi = ANDROID_GITIGNORE_PATH.read_text(encoding="utf-8")
        assert "*.keystore" in android_gi
        assert "*.jks" in android_gi

    def test_gradle_properties_does_not_contain_plaintext_secrets(self):
        """mobile/android/gradle.properties must not have active plaintext passwords."""
        content = GRADLE_PROPERTIES_PATH.read_text(encoding="utf-8")
        lines = content.splitlines()

        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                assert not stripped.startswith("NIRIKSHA_RELEASE_STORE_PASSWORD="), (
                    "Plaintext password found active in gradle.properties"
                )
                assert not stripped.startswith("NIRIKSHA_RELEASE_KEY_PASSWORD="), (
                    "Plaintext key password found active in gradle.properties"
                )

    def test_eas_json_valid_and_secret_free(self):
        """mobile/eas.json must configure production build and avoid hardcoded signing secrets."""
        assert EAS_JSON_PATH.exists()
        content = EAS_JSON_PATH.read_text(encoding="utf-8")
        assert "production" in content
        assert "password" not in content.lower()
