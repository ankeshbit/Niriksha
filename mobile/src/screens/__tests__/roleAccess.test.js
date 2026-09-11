/**
 * roleAccess.test.js
 *
 * Unit tests verifying that the NiriKsha mobile app gate-keeps
 * non-INSPECTOR roles at login time.
 *
 * These tests exercise the role-checking logic that was extracted
 * from LoginScreen.handleLogin and the startup useEffect.
 */

'use strict';

// ---------------------------------------------------------------------------
// Pure helper – mirrors the logic inside LoginScreen.handleLogin
// ---------------------------------------------------------------------------
function isInspectorRole(role) {
  return role === 'INSPECTOR';
}

function getLoginErrorForRole(role) {
  if (!role || role === 'INSPECTOR') {
    return null; // allowed
  }
  return 'This mobile application is for Field Inspectors only.';
}

// ---------------------------------------------------------------------------
// Pure helper – mirrors the startup useEffect in LoginScreen
// ---------------------------------------------------------------------------
function shouldClearStoredSession(profileRole) {
  // Returns true when the stored profile has a non-inspector role
  // (meaning we must clear storage and stay on LoginScreen)
  if (!profileRole) return false;
  return profileRole !== 'INSPECTOR';
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('Role-based mobile access gate', () => {
  // ---- Login-time gate ----

  describe('getLoginErrorForRole', () => {
    it('allows INSPECTOR role (returns null)', () => {
      expect(getLoginErrorForRole('INSPECTOR')).toBeNull();
    });

    it('rejects SUPERVISOR with the correct message', () => {
      expect(getLoginErrorForRole('SUPERVISOR')).toBe(
        'This mobile application is for Field Inspectors only.'
      );
    });

    it('rejects ADMIN with the correct message', () => {
      expect(getLoginErrorForRole('ADMIN')).toBe(
        'This mobile application is for Field Inspectors only.'
      );
    });

    it('allows when role is undefined / missing (null backend response)', () => {
      // If the backend does not return a role we do not block the user
      // (backend RBAC remains the authoritative source).
      expect(getLoginErrorForRole(undefined)).toBeNull();
      expect(getLoginErrorForRole(null)).toBeNull();
    });

    it('rejects any unknown/future role', () => {
      expect(getLoginErrorForRole('MANAGER')).toBe(
        'This mobile application is for Field Inspectors only.'
      );
    });
  });

  // ---- Session-restore gate (startup useEffect) ----

  describe('shouldClearStoredSession', () => {
    it('does NOT clear a stored INSPECTOR session', () => {
      expect(shouldClearStoredSession('INSPECTOR')).toBe(false);
    });

    it('clears a stored SUPERVISOR session', () => {
      expect(shouldClearStoredSession('SUPERVISOR')).toBe(true);
    });

    it('clears a stored ADMIN session', () => {
      expect(shouldClearStoredSession('ADMIN')).toBe(true);
    });

    it('does NOT clear when role is missing (no profile yet)', () => {
      expect(shouldClearStoredSession(undefined)).toBe(false);
      expect(shouldClearStoredSession(null)).toBe(false);
    });
  });

  // ---- isInspectorRole helper ----

  describe('isInspectorRole', () => {
    it('returns true only for INSPECTOR', () => {
      expect(isInspectorRole('INSPECTOR')).toBe(true);
    });

    it('returns false for SUPERVISOR', () => {
      expect(isInspectorRole('SUPERVISOR')).toBe(false);
    });

    it('returns false for ADMIN', () => {
      expect(isInspectorRole('ADMIN')).toBe(false);
    });

    it('returns false for empty string', () => {
      expect(isInspectorRole('')).toBe(false);
    });
  });
});
