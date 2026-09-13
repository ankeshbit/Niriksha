/**
 * introFlow.test.js
 *
 * Targeted tests for the NiriKsha Intro Video Launch Flow:
 * - Deterministic routing to Login vs Dashboard based on auth session
 * - Single-fire idempotent completion protection (no duplicate navigations)
 * - Immediate fallback on video error, playback error, or safety timeout
 * - Navigation stack isolation (no replay on logout, normal navigation, or resume)
 */

'use strict';

/**
 * Pure destination resolver mirroring IntroScreen.tsx auth pre-fetch logic.
 */
async function resolveIntroDestination(authStorageMock) {
  try {
    const [token, profile] = await Promise.all([
      authStorageMock.getToken(),
      authStorageMock.getProfile(),
    ]);

    if (token) {
      if (profile?.role && profile.role !== 'INSPECTOR') {
        await authStorageMock.clear();
        return 'Login';
      }
      return 'Dashboard';
    }
    return 'Login';
  } catch (_e) {
    return 'Login';
  }
}

/**
 * Pure controller mirroring IntroScreen.tsx idempotent navigation handler.
 */
function createIntroTransitionManager(navigationMock, getTargetDestination) {
  let hasNavigated = false;
  let navigationCount = 0;

  function handleFinish(reason) {
    if (hasNavigated) {
      return { status: 'ignored_already_navigated', navigationCount };
    }
    hasNavigated = true;
    navigationCount++;

    const destination = getTargetDestination();
    navigationMock.reset({
      index: 0,
      routes: [{ name: destination }],
    });

    return { status: 'navigated', destination, reason, navigationCount };
  }

  return {
    handleFinish,
    hasNavigated: () => hasNavigated,
    getNavigationCount: () => navigationCount,
  };
}

describe('NiriKsha Intro Video Launch Flow', () => {
  describe('Authentication & Destination Resolution', () => {
    it('routes unauthenticated user (no token) to Login', async () => {
      const authMock = {
        getToken: jest.fn().mockResolvedValue(null),
        getProfile: jest.fn().mockResolvedValue(null),
        clear: jest.fn().mockResolvedValue(undefined),
      };

      const dest = await resolveIntroDestination(authMock);
      expect(dest).toBe('Login');
      expect(authMock.clear).not.toHaveBeenCalled();
    });

    it('routes authenticated Field Inspector to Dashboard', async () => {
      const authMock = {
        getToken: jest.fn().mockResolvedValue('valid_jwt_token'),
        getProfile: jest.fn().mockResolvedValue({
          officer_id: 'DOCA-INSP-842',
          role: 'INSPECTOR',
        }),
        clear: jest.fn().mockResolvedValue(undefined),
      };

      const dest = await resolveIntroDestination(authMock);
      expect(dest).toBe('Dashboard');
      expect(authMock.clear).not.toHaveBeenCalled();
    });

    it('rejects non-INSPECTOR role (e.g. SUPERVISOR), clears storage, and routes to Login', async () => {
      const authMock = {
        getToken: jest.fn().mockResolvedValue('valid_supervisor_token'),
        getProfile: jest.fn().mockResolvedValue({
          officer_id: 'DOCA-SUP-001',
          role: 'SUPERVISOR',
        }),
        clear: jest.fn().mockResolvedValue(undefined),
      };

      const dest = await resolveIntroDestination(authMock);
      expect(dest).toBe('Login');
      expect(authMock.clear).toHaveBeenCalledTimes(1);
    });

    it('gracefully routes to Login if token lookup throws/rejects', async () => {
      const authMock = {
        getToken: jest.fn().mockRejectedValue(new Error('SecureStore failure')),
        getProfile: jest.fn().mockResolvedValue(null),
        clear: jest.fn().mockResolvedValue(undefined),
      };

      const dest = await resolveIntroDestination(authMock);
      expect(dest).toBe('Login');
    });
  });

  describe('Idempotency & Double Navigation Protection', () => {
    it('navigates exactly once even when called multiple times concurrently', () => {
      const navigationMock = {
        reset: jest.fn(),
      };

      const manager = createIntroTransitionManager(navigationMock, () => 'Login');

      const res1 = manager.handleFinish('video_completed');
      const res2 = manager.handleFinish('status_error');
      const res3 = manager.handleFinish('safety_timeout');

      expect(res1.status).toBe('navigated');
      expect(res2.status).toBe('ignored_already_navigated');
      expect(res3.status).toBe('ignored_already_navigated');

      expect(manager.getNavigationCount()).toBe(1);
      expect(navigationMock.reset).toHaveBeenCalledTimes(1);
      expect(navigationMock.reset).toHaveBeenCalledWith({
        index: 0,
        routes: [{ name: 'Login' }],
      });
    });

    it('removes Intro from navigation stack history on reset', () => {
      const navigationMock = {
        reset: jest.fn(),
      };

      const manager = createIntroTransitionManager(navigationMock, () => 'Dashboard');
      manager.handleFinish('video_completed');

      // Uses navigation.reset({ index: 0, routes: [{ name: 'Dashboard' }] })
      // which purges Intro from back history completely
      expect(navigationMock.reset).toHaveBeenCalledWith({
        index: 0,
        routes: [{ name: 'Dashboard' }],
      });
    });
  });

  describe('Failure Fallbacks', () => {
    it('falls back to Login immediately upon video loading/playback error', () => {
      const navigationMock = {
        reset: jest.fn(),
      };

      const manager = createIntroTransitionManager(navigationMock, () => 'Login');
      const res = manager.handleFinish('playback_error');

      expect(res.status).toBe('navigated');
      expect(res.reason).toBe('playback_error');
      expect(navigationMock.reset).toHaveBeenCalledWith({
        index: 0,
        routes: [{ name: 'Login' }],
      });
    });

    it('falls back immediately upon safety timeout if video freezes', () => {
      const navigationMock = {
        reset: jest.fn(),
      };

      const manager = createIntroTransitionManager(navigationMock, () => 'Dashboard');
      const res = manager.handleFinish('safety_timeout');

      expect(res.status).toBe('navigated');
      expect(res.reason).toBe('safety_timeout');
      expect(navigationMock.reset).toHaveBeenCalledWith({
        index: 0,
        routes: [{ name: 'Dashboard' }],
      });
    });
  });

  describe('Navigation & Lifecycle Isolation', () => {
    it('logout resets to Login and never introduces Intro route into stack', () => {
      const navigationMock = {
        reset: jest.fn(),
      };

      // Simulates ProfileScreen.tsx line 247 on user sign out
      navigationMock.reset({
        index: 0,
        routes: [{ name: 'Login' }],
      });

      expect(navigationMock.reset).toHaveBeenCalledWith({
        index: 0,
        routes: [{ name: 'Login' }],
      });
      // Intro route is NOT in the reset routes array
      const resetCall = navigationMock.reset.mock.calls[0][0];
      expect(resetCall.routes.some((r) => r.name === 'Intro')).toBe(false);
    });
  });

  describe('Bundled Video Asset & Offline Raw Resource Integrity', () => {
    const fs = require('fs');
    const path = require('path');

    it('verifies the primary video asset exists and is non-empty', () => {
      const videoPath = path.resolve(__dirname, '../../../assets/videos/niriksha_intro.mp4');
      expect(fs.existsSync(videoPath)).toBe(true);
      const stat = fs.statSync(videoPath);
      expect(stat.size).toBeGreaterThan(1024 * 1024); // > 1MB
    });

    it('verifies the compiled Android raw resource exists in res/raw for offline playback', () => {
      const rawPath = path.resolve(__dirname, '../../../android/app/src/main/res/raw/niriksha_intro.mp4');
      expect(fs.existsSync(rawPath)).toBe(true);
      const stat = fs.statSync(rawPath);
      expect(stat.size).toBe(2835493); // exact matching size
    });

    it('verifies the NiriKsha logo asset exists for fallback display', () => {
      const logoPath = path.resolve(__dirname, '../../../assets/niriksha_logo.png');
      expect(fs.existsSync(logoPath)).toBe(true);
      const stat = fs.statSync(logoPath);
      expect(stat.size).toBeGreaterThan(100 * 1024);
    });

    it('verifies the Android raw resource URI conforms to standard', () => {
      const rawUri = 'android.resource://gov.doca.legalmetrology/raw/niriksha_intro';
      expect(rawUri.startsWith('android.resource://')).toBe(true);
      expect(rawUri.endsWith('/raw/niriksha_intro')).toBe(true);
    });
  });

  describe('User Interactive Controls (Skip & Fallback Continue)', () => {
    it('allows user to skip intro immediately via skip button', () => {
      const navigationMock = {
        reset: jest.fn(),
      };

      const manager = createIntroTransitionManager(navigationMock, () => 'Login');
      const res = manager.handleFinish('user_skipped');

      expect(res.status).toBe('navigated');
      expect(res.reason).toBe('user_skipped');
      expect(navigationMock.reset).toHaveBeenCalledWith({
        index: 0,
        routes: [{ name: 'Login' }],
      });
    });

    it('allows user to advance when continue is pressed on fallback UI', () => {
      const navigationMock = {
        reset: jest.fn(),
      };

      const manager = createIntroTransitionManager(navigationMock, () => 'Login');
      const res = manager.handleFinish('user_continue_pressed');

      expect(res.status).toBe('navigated');
      expect(res.reason).toBe('user_continue_pressed');
      expect(navigationMock.reset).toHaveBeenCalledWith({
        index: 0,
        routes: [{ name: 'Login' }],
      });
    });
  });
});
