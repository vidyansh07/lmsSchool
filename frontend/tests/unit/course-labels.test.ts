import { describe, expect, it } from 'vitest';

import { formatBytes, formatDuration } from '@/lib/course-labels';

describe('formatDuration', () => {
  it('renders minutes, hours, and both', () => {
    expect(formatDuration(45)).toBe('45m');
    expect(formatDuration(120)).toBe('2h');
    expect(formatDuration(105)).toBe('1h 45m');
  });

  it('renders a dash when there is nothing to show', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(0)).toBe('—');
  });
});

describe('formatBytes', () => {
  it('scales to the right unit', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB');
  });

  it('renders a dash for a missing size', () => {
    expect(formatBytes(null)).toBe('—');
  });
});
