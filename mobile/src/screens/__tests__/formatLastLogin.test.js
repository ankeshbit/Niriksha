const { formatLastLogin } = require('../../services/dateUtils');

describe('formatLastLogin', () => {
  it('returns "Not available" for null, undefined, or empty values', () => {
    expect(formatLastLogin(null)).toBe('Not available');
    expect(formatLastLogin(undefined)).toBe('Not available');
    expect(formatLastLogin('')).toBe('Not available');
    expect(formatLastLogin('   ')).toBe('Not available');
  });

  it('formats a date from today correctly', () => {
    const today = new Date();
    today.setHours(9, 34, 0, 0);
    const result = formatLastLogin(today.toISOString());
    expect(result).toMatch(/^Today, \d{2}:\d{2} [AP]M from Current Device$/);
  });

  it('formats a date from yesterday correctly', () => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    yesterday.setHours(20, 12, 0, 0);
    const result = formatLastLogin(yesterday.toISOString());
    expect(result).toMatch(/^Yesterday, \d{2}:\d{2} [AP]M from Current Device$/);
  });

  it('formats an older date with date, month, year', () => {
    const oldDate = new Date('2025-08-15T14:30:00Z');
    const result = formatLastLogin(oldDate.toISOString());
    expect(result).toContain('15 Aug 2025');
    expect(result).toContain('from Current Device');
  });
});
