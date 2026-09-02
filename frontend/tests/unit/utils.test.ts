import { describe, expect, it } from 'vitest';

import { apiBaseUrl, env } from '@/lib/env';
import { cn } from '@/lib/utils';

describe('cn', () => {
  it('merges conflicting Tailwind utilities, last one winning', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4');
  });

  it('drops falsy values', () => {
    expect(cn('a', false && 'b', undefined, 'c')).toBe('a c');
  });
});

describe('env', () => {
  it('exposes a base URL without a trailing slash', () => {
    expect(env.publicApiBaseUrl.endsWith('/')).toBe(false);
    expect(apiBaseUrl()).toBe(env.internalApiBaseUrl);
  });
});
