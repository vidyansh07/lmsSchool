import { describe, expect, it } from 'vitest';

import { Capability, can } from '@/lib/capabilities';

describe('can', () => {
  it('is true only when the capability is present', () => {
    const capabilities = [Capability.profileViewOwn, Capability.studentViewAny];
    expect(can(capabilities, Capability.studentViewAny)).toBe(true);
    expect(can(capabilities, Capability.userCreate)).toBe(false);
  });

  it('is false when the user has no capability list', () => {
    expect(can(undefined, Capability.profileViewOwn)).toBe(false);
    expect(can([], Capability.profileViewOwn)).toBe(false);
  });
});
