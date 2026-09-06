import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useSavedFilters } from '@/hooks/use-saved-filters';

describe('useSavedFilters', () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('starts empty when nothing is stored', () => {
    const { result } = renderHook(() => useSavedFilters<{ status: string }>('admin-users'));
    expect(result.current.savedFilters).toEqual([]);
  });

  it('saves a named filter and persists it to localStorage', () => {
    const { result } = renderHook(() => useSavedFilters<{ status: string }>('admin-users'));

    act(() => result.current.save('Active staff', { status: 'active' }));

    expect(result.current.savedFilters).toHaveLength(1);
    expect(result.current.savedFilters[0]).toMatchObject({
      name: 'Active staff',
      filters: { status: 'active' },
    });

    const stored = JSON.parse(window.localStorage.getItem('grras.filters.admin-users') ?? '[]');
    expect(stored).toHaveLength(1);
  });

  it('loads previously saved filters for the same scope', () => {
    window.localStorage.setItem(
      'grras.filters.admin-users',
      JSON.stringify([{ id: '1', name: 'Existing', filters: { status: 'paid' } }]),
    );

    const { result } = renderHook(() => useSavedFilters<{ status: string }>('admin-users'));
    expect(result.current.savedFilters).toHaveLength(1);
    expect(result.current.savedFilters[0]?.name).toBe('Existing');
  });

  it('keeps scopes independent', () => {
    const users = renderHook(() => useSavedFilters<{ status: string }>('admin-users'));
    const students = renderHook(() => useSavedFilters<{ status: string }>('admin-students'));

    act(() => users.result.current.save('Users filter', { status: 'active' }));

    expect(users.result.current.savedFilters).toHaveLength(1);
    expect(students.result.current.savedFilters).toHaveLength(0);
  });

  it('replaces an existing preset saved under the same name', () => {
    const { result } = renderHook(() => useSavedFilters<{ status: string }>('admin-users'));

    act(() => result.current.save('Mine', { status: 'active' }));
    act(() => result.current.save('Mine', { status: 'paid' }));

    expect(result.current.savedFilters).toHaveLength(1);
    expect(result.current.savedFilters[0]?.filters).toEqual({ status: 'paid' });
  });

  it('ignores a blank name', () => {
    const { result } = renderHook(() => useSavedFilters<{ status: string }>('admin-users'));
    act(() => result.current.save('   ', { status: 'active' }));
    expect(result.current.savedFilters).toEqual([]);
  });

  it('removes a saved filter by id', () => {
    const { result } = renderHook(() => useSavedFilters<{ status: string }>('admin-users'));
    act(() => result.current.save('Mine', { status: 'active' }));
    const id = result.current.savedFilters[0]?.id as string;

    act(() => result.current.remove(id));
    expect(result.current.savedFilters).toEqual([]);
  });

  it('does not throw and returns an empty list when localStorage.getItem throws', () => {
    vi.spyOn(window.localStorage.__proto__, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });

    const { result } = renderHook(() => useSavedFilters<{ status: string }>('admin-users'));
    expect(result.current.savedFilters).toEqual([]);
  });

  it('does not throw when localStorage.setItem throws', () => {
    vi.spyOn(window.localStorage.__proto__, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded');
    });

    const { result } = renderHook(() => useSavedFilters<{ status: string }>('admin-users'));
    expect(() => act(() => result.current.save('Mine', { status: 'active' }))).not.toThrow();
    // The in-memory state still updates even though persistence failed.
    expect(result.current.savedFilters).toHaveLength(1);
  });

  it('recovers from corrupted stored JSON by treating it as empty', () => {
    window.localStorage.setItem('grras.filters.admin-users', '{not valid json');
    const { result } = renderHook(() => useSavedFilters<{ status: string }>('admin-users'));
    expect(result.current.savedFilters).toEqual([]);
  });
});
