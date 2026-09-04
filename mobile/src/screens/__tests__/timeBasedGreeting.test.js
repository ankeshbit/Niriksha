const { getTimeBasedGreeting } = require('../../services/dateUtils');

describe('getTimeBasedGreeting', () => {
  // Helper to create date at specified local hours and minutes
  const createLocalDate = (hours, minutes) => {
    const d = new Date();
    d.setHours(hours, minutes, 0, 0);
    return d;
  };

  it('returns "Good morning" at 12:00 AM (midnight)', () => {
    const midnight = createLocalDate(0, 0);
    expect(getTimeBasedGreeting(midnight)).toBe('Good morning');
  });

  it('returns "Good morning" at 11:59 AM', () => {
    const morningEnd = createLocalDate(11, 59);
    expect(getTimeBasedGreeting(morningEnd)).toBe('Good morning');
  });

  it('returns "Good afternoon" at 12:00 PM (noon)', () => {
    const noon = createLocalDate(12, 0);
    expect(getTimeBasedGreeting(noon)).toBe('Good afternoon');
  });

  it('returns "Good afternoon" at 4:59 PM', () => {
    const afternoonEnd = createLocalDate(16, 59);
    expect(getTimeBasedGreeting(afternoonEnd)).toBe('Good afternoon');
  });

  it('returns "Good evening" at 5:00 PM', () => {
    const eveningStart = createLocalDate(17, 0);
    expect(getTimeBasedGreeting(eveningStart)).toBe('Good evening');
  });

  it('returns "Good evening" at 11:59 PM', () => {
    const nightEnd = createLocalDate(23, 59);
    expect(getTimeBasedGreeting(nightEnd)).toBe('Good evening');
  });

  it('defaults to current time without throwing when no date argument is passed', () => {
    const greeting = getTimeBasedGreeting();
    expect(['Good morning', 'Good afternoon', 'Good evening']).toContain(greeting);
  });
});
