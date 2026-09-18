import { describe, expect, it } from 'vitest';

import { greeting, timeOfDayGreeting } from '@/lib/greeting';

describe('timeOfDayGreeting', () => {
  it('says good morning before noon', () => {
    expect(timeOfDayGreeting(6)).toBe('Good morning');
    expect(timeOfDayGreeting(11)).toBe('Good morning');
  });

  it('says good afternoon from noon to before 5pm', () => {
    expect(timeOfDayGreeting(12)).toBe('Good afternoon');
    expect(timeOfDayGreeting(16)).toBe('Good afternoon');
  });

  it('says good evening from 5pm onward', () => {
    expect(timeOfDayGreeting(17)).toBe('Good evening');
    expect(timeOfDayGreeting(23)).toBe('Good evening');
  });
});

describe('greeting', () => {
  it('appends the name when one is available', () => {
    expect(greeting('Priya Sharma', 9)).toBe('Good morning, Priya Sharma');
  });

  it('degrades to a plain greeting rather than rendering "undefined"', () => {
    expect(greeting(null, 9)).toBe('Good morning');
    expect(greeting(undefined, 9)).toBe('Good morning');
    expect(greeting('', 9)).toBe('Good morning');
  });
});
