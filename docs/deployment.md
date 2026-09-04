# NiriKsha Deployment

NiriKsha is an Expo/React Native mobile app backed by a FastAPI service. A store-ready deployment needs both a public HTTPS backend and an Android/iOS build configured with that backend URL.

## 1. Deploy the backend

Use a Python host such as Render, Railway, or an equivalent service. Configure the service to run from the repository root with:

```text
Build: pip install -r backend/requirements.txt
Start: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Set production environment variables on the host. At minimum, use a strong `SECRET_KEY`, set `ENVIRONMENT=production` and `DEBUG=False`, and configure a persistent PostgreSQL database with `DATABASE_URL`. For production image/report storage, configure Supabase using `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_BUCKET_IMAGES`, and `SUPABASE_BUCKET_REPORTS`.

Verify the deployed URL before building the app:

```text
https://your-api.example.com/api/health
```

Do not put `SUPABASE_KEY` or any other backend secret in the mobile app.

## 2. Install EAS and authenticate

From `mobile/`:

```powershell
npm install
npm install --global eas-cli
eas login
eas build:configure
```

The repository includes `mobile/eas.json` with two profiles:

- `preview`: internal Android APK for direct installation and testing.
- `production`: Android AAB for Google Play and an iOS device build.

## 3. Build with the production API URL

Set the public API URL for the build. This value is compiled into the JavaScript bundle and must use HTTPS:

```powershell
$env:EXPO_PUBLIC_API_URL = "https://your-api.example.com"
eas build --platform android --profile preview
```

For a Play Store release:

```powershell
$env:EXPO_PUBLIC_API_URL = "https://your-api.example.com"
eas build --platform android --profile production
```

Download the generated APK for testing, or submit the AAB with:

```powershell
eas submit --platform android --profile production
```

The first EAS build will ask to create or select the Expo project and Android signing credentials. Keep those credentials backed up in the EAS account.

## 4. Local checks

```powershell
npm run ts:check
npx expo config --type public
```

The local native Android build additionally requires JDK 17 and Android SDK API 34. EAS cloud builds do not require the Android SDK on this workstation.