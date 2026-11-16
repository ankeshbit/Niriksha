# Android Production Release Signing Guide

This guide details the procedure for generating, securing, and configuring production release signing keys for the Niriksha Android mobile application.

---

## 1. Security Invariants

1. **Never Commit Production Credentials**: Private keystores (`*.jks`, `*.keystore`), key aliases, and passwords must never be committed to Git.
2. **Debug vs Release Isolation**: Debug builds automatically use `debug.keystore` with standard public credentials (`android` / `androiddebugkey`). Release builds must strictly use an authoritative production keystore and will safely fail if release credentials are absent.
3. **Immutability of Signing Keys**: An Android application published to Google Play or distributed to enforcement agencies cannot change its signing key without triggering package signature mismatches and breaking updates. Keystores must be securely backed up.

---

## 2. Generating a Production Keystore

Use the standard JDK `keytool` utility to generate an RSA 2048-bit (or 4096-bit) signing key with a 10,000-day validity:

```bash
keytool -genkeypair \
  -v \
  -keystore niriksha-release.keystore \
  -alias niriksha-release-key \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 \
  -storetype PKCS12
```

When prompted:
- Specify a strong, random password for the keystore and key.
- Provide the organizational details (e.g., Department of Consumer Affairs, Legal Metrology Division).
- Securely store the output file (`niriksha-release.keystore`).

---

## 3. Secure Storage and Backup

- **Cold Storage**: Store encrypted copies of `niriksha-release.keystore` in a hardware security module (HSM) or organization-approved enterprise secret manager (e.g., AWS Secrets Manager, HashiCorp Vault, Google Cloud Secret Manager).
- **Password Vault**: Record the store password, key alias, and key password in the official organizational password vault with role-based access.

---

## 4. Local Build Configuration

To build a signed release APK or Android App Bundle (AAB) locally, configure the following environment variables (preferred):

### Option A: Environment Variables (Recommended)
```bash
# In Bash / CI
export NIRIKSHA_RELEASE_STORE_FILE="/path/to/niriksha-release.keystore"
export NIRIKSHA_RELEASE_STORE_PASSWORD="<store-password>"
export NIRIKSHA_RELEASE_KEY_ALIAS="niriksha-release-key"
export NIRIKSHA_RELEASE_KEY_PASSWORD="<key-password>"

# In PowerShell
$env:NIRIKSHA_RELEASE_STORE_FILE="C:\secure\niriksha-release.keystore"
$env:NIRIKSHA_RELEASE_STORE_PASSWORD="<store-password>"
$env:NIRIKSHA_RELEASE_KEY_ALIAS="niriksha-release-key"
$env:NIRIKSHA_RELEASE_KEY_PASSWORD="<key-password>"
```

### Option B: User-Level Gradle Properties
Alternatively, set the properties in your user-level Gradle directory (`~/.gradle/gradle.properties`), which is outside the Git repository:

```properties
NIRIKSHA_RELEASE_STORE_FILE=/Users/user/.signing/niriksha-release.keystore
NIRIKSHA_RELEASE_STORE_PASSWORD=<store-password>
NIRIKSHA_RELEASE_KEY_ALIAS=niriksha-release-key
NIRIKSHA_RELEASE_KEY_PASSWORD=<key-password>
```

---

## 5. EAS (Expo Application Services) Cloud Builds

When using EAS to build Niriksha in the cloud:
1. Run `eas credentials` in the `mobile/` directory.
2. Select **Android** -> **production** / **preview**.
3. Choose to either let EAS manage and encrypt the keystore on remote secure storage, or upload your existing `niriksha-release.keystore`.
4. EAS injects the credentials at build time into Gradle without exposing passwords in source code.

---

## 6. Verification and Build Tests

### Debug Build (No release credentials needed):
```bash
cd mobile/android
./gradlew assembleDebug
```
*Expected: SUCCESS (uses debug.keystore).*

### Release Build Without Credentials:
```bash
cd mobile/android
./gradlew assembleRelease
```
*Expected: FAILS clearly with `[NIRIKSHA ANDROID RELEASE BUILD FAILED] Missing production release signing credentials`.*

### Release Build With Credentials:
```bash
cd mobile/android
NIRIKSHA_RELEASE_STORE_FILE="..." NIRIKSHA_RELEASE_STORE_PASSWORD="..." NIRIKSHA_RELEASE_KEY_ALIAS="..." NIRIKSHA_RELEASE_KEY_PASSWORD="..." ./gradlew assembleRelease
```
*Expected: SUCCESS (produces signed release APK/AAB).*
