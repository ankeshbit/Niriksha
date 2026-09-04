/**
 * Formats a UTC last-login timestamp into a human-readable string in the user's local timezone.
 *
 * Examples:
 * - "Today, 09:34 AM from Current Device"
 * - "Yesterday, 08:12 PM from Current Device"
 * - "02 Sep 2026, 07:45 PM from Current Device"
 * - "Not available" (if missing, null, or invalid)
 */
export const formatLastLogin = (lastLoginAt?: string | Date | null): string => {
  if (!lastLoginAt) return 'Not available';

  let date: Date;
  if (typeof lastLoginAt === 'string') {
    let dateStr = lastLoginAt.trim();
    if (!dateStr) return 'Not available';

    // If timestamp string is ISO-like without explicit timezone offset, treat as UTC
    if (dateStr.includes('T') && !dateStr.endsWith('Z') && !/[+-]\d{2}:?\d{2}$/.test(dateStr)) {
      dateStr += 'Z';
    } else if (dateStr.includes(' ') && !dateStr.includes('T') && !/[+-]\d{2}:?\d{2}$/.test(dateStr)) {
      dateStr = dateStr.replace(' ', 'T') + 'Z';
    }
    date = new Date(dateStr);
  } else {
    date = new Date(lastLoginAt);
  }

  if (isNaN(date.getTime())) return 'Not available';

  const now = new Date();

  // Compare calendar days in the user's local timezone
  const todayMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const targetMidnight = new Date(date.getFullYear(), date.getMonth(), date.getDate());

  const diffMs = todayMidnight.getTime() - targetMidnight.getTime();
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));

  // 12-hour format with AM/PM in user's local timezone
  const hours = date.getHours();
  const minutes = date.getMinutes();
  const ampm = hours >= 12 ? 'PM' : 'AM';
  const displayHours = hours % 12 || 12;
  const pad = (n: number) => (n < 10 ? '0' + n : String(n));
  const timeStr = `${pad(displayHours)}:${pad(minutes)} ${ampm}`;

  if (diffDays === 0) {
    return `Today, ${timeStr} from Current Device`;
  } else if (diffDays === 1) {
    return `Yesterday, ${timeStr} from Current Device`;
  } else {
    const day = pad(date.getDate());
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = monthNames[date.getMonth()];
    const year = date.getFullYear();
    return `${day} ${month} ${year}, ${timeStr} from Current Device`;
  }
};

/**
 * Returns a dynamic greeting based on the local time:
 * - Before 12:00 PM (00:00 - 11:59): "Good morning"
 * - 12:00 PM through 4:59 PM (12:00 - 16:59): "Good afternoon"
 * - 5:00 PM onward (17:00 - 23:59): "Good evening"
 *
 * @param date Optional Date instance for deterministic evaluation/testing (defaults to new Date())
 */
export const getTimeBasedGreeting = (date: Date = new Date()): string => {
  const hours = date.getHours();
  if (hours < 12) {
    return 'Good morning';
  } else if (hours < 17) {
    return 'Good afternoon';
  } else {
    return 'Good evening';
  }
};

