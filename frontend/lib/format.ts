/**
 * The null-handling contract for the whole app.
 *
 * The brief this file exists to satisfy is absolute: never let `undefined`,
 * `NaN` or `Invalid Date` reach the screen. An ERP renders numbers and dates
 * that came from a database column that is nullable, a report that has not
 * run yet, or a field nobody filled in — and every one of those must become a
 * short, honest sentence instead of a blank cell or the literal text
 * "Invalid Date". Every function below is total: it takes `unknown`, not the
 * narrower type an API response promises, because that promise is only as
 * good as the backend's diligence, and a `null` slipping through a `string`
 * field is exactly the bug this file exists to make structurally impossible.
 *
 * One decision worth calling out: the date/name/relative formatters take the
 * fallback label as a plain second argument, because call sites reach for
 * them constantly and a bare string reads better than an options object at
 * the call site. `formatNumber`, `formatPercent`, `formatDuration` and
 * `formatCount` take an options object instead, because they also need a
 * digits/unit/plural knob and two optional positional strings invite the
 * wrong one being passed in the wrong order.
 */

export const NOT_AVAILABLE = 'Not available';
export const NOT_ASSIGNED = 'Not assigned';
export const NOT_SUBMITTED = 'Not submitted';
export const NO_DATA = 'No data';
export const UNKNOWN = 'Unknown';

/** The fixed vocabulary of fallback labels. Screens should not invent their own. */
export type FallbackLabel =
  | typeof NOT_AVAILABLE
  | typeof NOT_ASSIGNED
  | typeof NOT_SUBMITTED
  | typeof NO_DATA
  | typeof UNKNOWN;

/**
 * Coerce anything to a trimmed display string, or `label` when there is
 * nothing worth showing (`null`, `undefined`, an empty/whitespace string, or a
 * non-finite number). This is the primitive the rest of the file is built on,
 * and it is also exported directly for the plain "optional text field" case
 * that does not need a number or date parsed out of it.
 */
export function fallback(value: unknown, label: FallbackLabel = NOT_AVAILABLE): string {
  if (value === null || value === undefined) return label;
  if (typeof value === 'number' && !Number.isFinite(value)) return label;
  // A `Date` is a legitimate thing to hand this function (it is the generic
  // "make this presentable" escape hatch), but `String(new Date(NaN))` is the
  // literal text "Invalid Date" — precisely what this file exists to forbid.
  if (value instanceof Date && Number.isNaN(value.getTime())) return label;
  const text = String(value).trim();
  return text.length > 0 ? text : label;
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function toValidDate(value: unknown): Date | null {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  if (typeof value === 'string' || typeof value === 'number') {
    if (value === '') return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  return null;
}

/** A locale-formatted number, or the fallback for anything that is not one. */
export function formatNumber(
  value: unknown,
  options: { fallbackLabel?: FallbackLabel; maximumFractionDigits?: number } = {},
): string {
  const number = toFiniteNumber(value);
  if (number === null) return options.fallbackLabel ?? NOT_AVAILABLE;
  return number.toLocaleString(undefined, {
    maximumFractionDigits: options.maximumFractionDigits ?? 2,
  });
}

/** `value` treated as a plain number already scaled to 0–100, e.g. 82 → "82%". */
/**
 * A rupee amount: `"12500.00"` → `"₹12,500"`. The API sends decimals as
 * strings, so this takes the string, the number, or nothing, and only ever
 * produces a currency or the fallback — never `₹NaN`.
 *
 * Whole rupees by default: a fee is agreed in round figures and the paise
 * are noise in a table. Pass `decimals: 2` on a screen that needs them.
 */
export function formatCurrency(
  value: unknown,
  { label = NOT_AVAILABLE, decimals = 0 }: { label?: FallbackLabel; decimals?: number } = {},
): string {
  const number = toFiniteNumber(value);
  if (number === null) return label;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(number);
}

export function formatPercent(
  value: unknown,
  options: { fallbackLabel?: FallbackLabel; maximumFractionDigits?: number } = {},
): string {
  const number = toFiniteNumber(value);
  if (number === null) return options.fallbackLabel ?? NOT_AVAILABLE;
  const digits = options.maximumFractionDigits ?? 0;
  return `${number.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  })}%`;
}

/** "3 Mar 2026" from anything that parses to a valid date, else the fallback. */
export function formatDate(value: unknown, label: FallbackLabel = NOT_AVAILABLE): string {
  const date = toValidDate(value);
  if (!date) return label;
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

/** `formatDate` plus a time of day. */
export function formatDateTime(value: unknown, label: FallbackLabel = NOT_AVAILABLE): string {
  const date = toValidDate(value);
  if (!date) return label;
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * "2 hours ago" / "in 3 days" / "now", via `Intl.RelativeTimeFormat` so
 * pluralisation and locale are handled by the platform rather than by hand.
 * `now` defaults to the current time but takes an explicit value so a test
 * (or a screen holding a frozen "as of" moment) does not depend on the clock.
 */
export function formatRelative(
  value: unknown,
  label: FallbackLabel = NOT_AVAILABLE,
  now: unknown = Date.now(),
): string {
  const date = toValidDate(value);
  if (!date) return label;
  const reference = toValidDate(now) ?? new Date();

  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  const divisions: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, 'second'],
    [60, 'minute'],
    [24, 'hour'],
    [7, 'day'],
    [4.34524, 'week'],
    [12, 'month'],
    [Number.POSITIVE_INFINITY, 'year'],
  ];

  let duration = (date.getTime() - reference.getTime()) / 1000;
  for (const [amount, unit] of divisions) {
    if (Math.abs(duration) < amount) return rtf.format(Math.round(duration), unit);
    duration /= amount;
  }
  return rtf.format(Math.round(duration), 'year');
}

/**
 * "1h 45m" from a duration. `unit` says what `value` is measured in — most of
 * the app's APIs report minutes, so that is the default.
 */
export function formatDuration(
  value: unknown,
  options: { fallbackLabel?: FallbackLabel; unit?: 'minutes' | 'seconds' } = {},
): string {
  const number = toFiniteNumber(value);
  if (number === null || number < 0) return options.fallbackLabel ?? NOT_AVAILABLE;
  const totalMinutes = options.unit === 'seconds' ? number / 60 : number;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = Math.round(totalMinutes % 60);
  if (hours === 0) return `${minutes}m`;
  if (minutes === 0) return `${hours}h`;
  return `${hours}h ${minutes}m`;
}

/** The shape `formatName` reads from — a subset of the API's various "person" types. */
export interface NameLike {
  full_name?: unknown;
  first_name?: unknown;
  last_name?: unknown;
  email?: unknown;
}

/**
 * A display name for a person, trying `full_name`, then first + last name,
 * then email, in that order — the same order the backend itself falls back
 * through when it renders a name for an audit log.
 */
export function formatName(person: NameLike | null | undefined, label: FallbackLabel = UNKNOWN): string {
  if (!person || typeof person !== 'object') return label;
  const full = typeof person.full_name === 'string' ? person.full_name.trim() : '';
  if (full) return full;
  const first = typeof person.first_name === 'string' ? person.first_name.trim() : '';
  const last = typeof person.last_name === 'string' ? person.last_name.trim() : '';
  const combined = [first, last].filter(Boolean).join(' ');
  if (combined) return combined;
  const email = typeof person.email === 'string' ? person.email.trim() : '';
  if (email) return email;
  return label;
}

/**
 * "1 seat" / "4 seats" — a count paired with the noun it counts, pluralised.
 * `plural` defaults to `${singular}s`, which covers most of the app's
 * vocabulary; pass it explicitly for the exceptions ("child" → "children").
 */
export function formatCount(
  value: unknown,
  singular: string,
  plural: string = `${singular}s`,
  label: FallbackLabel = NO_DATA,
): string {
  const number = toFiniteNumber(value);
  if (number === null || number < 0) return label;
  return `${number.toLocaleString()} ${number === 1 ? singular : plural}`;
}
