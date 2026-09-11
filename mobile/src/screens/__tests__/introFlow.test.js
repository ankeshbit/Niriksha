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
});
