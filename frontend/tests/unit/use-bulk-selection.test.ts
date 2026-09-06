import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useBulkSelection } from '@/hooks/use-bulk-selection';

const PAGE = ['a', 'b', 'c', 'd', 'e'];

describe('useBulkSelection', () => {
  it('starts with nothing selected', () => {
    const { result } = renderHook(() => useBulkSelection<string>('filter-1'));
    expect(result.current.selectedCount).toBe(0);
    expect(result.current.selectAllMatching).toBe(false);
  });

  it('toggles a single row', () => {
    const { result } = renderHook(() => useBulkSelection<string>('filter-1'));

    act(() => result.current.toggle('b', 1, PAGE));
    expect(result.current.isSelected('b')).toBe(true);
    expect(result.current.selectedCount).toBe(1);

    act(() => result.current.toggle('b', 1, PAGE));
    expect(result.current.isSelected('b')).toBe(false);
    expect(result.current.selectedCount).toBe(0);
  });

  it('shift-clicking a second row selects the range between the two', () => {
    const { result } = renderHook(() => useBulkSelection<string>('filter-1'));

    act(() => result.current.toggle('b', 1, PAGE));
    act(() => result.current.toggle('d', 3, PAGE, true));

    expect(result.current.selectedIds).toEqual(new Set(['b', 'c', 'd']));
  });

  it('a shift-click range can also deselect', () => {
    const { result } = renderHook(() => useBulkSelection<string>('filter-1'));

    act(() => result.current.toggleAll(PAGE));
    expect(result.current.selectedCount).toBe(5);

    // First click establishes the anchor by deselecting 'b'...
    act(() => result.current.toggle('b', 1, PAGE));
    // ...then shift-click 'd' extends that deselection across the range.
    act(() => result.current.toggle('d', 3, PAGE, true));

    expect(result.current.selectedIds).toEqual(new Set(['a', 'e']));
  });

  it('toggleAll selects every row on the page, then clears on a second call', () => {
    const { result } = renderHook(() => useBulkSelection<string>('filter-1'));

    act(() => result.current.toggleAll(PAGE));
    expect(result.current.selectedCount).toBe(PAGE.length);
    expect(result.current.pageSelectionState(PAGE)).toBe('all');

    act(() => result.current.toggleAll(PAGE));
    expect(result.current.selectedCount).toBe(0);
    expect(result.current.pageSelectionState(PAGE)).toBe('none');
  });

  it('reports a partial page selection state', () => {
    const { result } = renderHook(() => useBulkSelection<string>('filter-1'));
    act(() => result.current.toggle('a', 0, PAGE));
    expect(result.current.pageSelectionState(PAGE)).toBe('some');
  });

  it('keeps select-all-matching distinct from selecting every row on the page', () => {
    const { result } = renderHook(() => useBulkSelection<string>('filter-1'));

    act(() => result.current.toggleAll(PAGE));
    expect(result.current.selectAllMatching).toBe(false);

    act(() => result.current.selectAllMatchingFilter());
    expect(result.current.selectAllMatching).toBe(true);
  });

  it('clears the page selection when selecting a single row after "select all matching"', () => {
    const { result } = renderHook(() => useBulkSelection<string>('filter-1'));

    act(() => result.current.selectAllMatchingFilter());
    act(() => result.current.toggle('a', 0, PAGE));

    expect(result.current.selectAllMatching).toBe(false);
  });

  it('clear() resets both the row selection and the matching flag', () => {
    const { result } = renderHook(() => useBulkSelection<string>('filter-1'));

    act(() => result.current.toggleAll(PAGE));
    act(() => result.current.selectAllMatchingFilter());
    act(() => result.current.clear());

    expect(result.current.selectedCount).toBe(0);
    expect(result.current.selectAllMatching).toBe(false);
  });

  it('clears the selection when the filter key changes', () => {
    const { result, rerender } = renderHook(({ key }) => useBulkSelection<string>(key), {
      initialProps: { key: 'filter-1' },
    });

    act(() => result.current.toggleAll(PAGE));
    expect(result.current.selectedCount).toBe(5);

    rerender({ key: 'filter-2' });
    expect(result.current.selectedCount).toBe(0);
    expect(result.current.selectAllMatching).toBe(false);
  });
});
