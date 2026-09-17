import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useList } from '@/hooks/use-list';
import { ApiError } from '@/lib/api';
import type { ListQuery } from '@/lib/people';
import type { Paginated } from '@/types/api';

function paginated<T>(results: T[]): Paginated<T> {
  return {
    count: results.length,
    page: 1,
    page_size: 20,
    total_pages: 1,
    next: null,
    previous: null,
    results,
  };
}

describe('useList', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('resolves data on success', async () => {
    const fetcher = vi.fn().mockResolvedValue(paginated([{ id: 1 }]));
    const { result } = renderHook(() => useList(fetcher));

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.data).toEqual(paginated([{ id: 1 }]));
    expect(result.current.error).toBeNull();
  });

  it('passes an AbortSignal to the fetcher', () => {
    const fetcher = vi.fn().mockImplementation(() => new Promise(() => {}));
    renderHook(() => useList(fetcher));

    expect(fetcher).toHaveBeenCalledTimes(1);
    const [, signal] = fetcher.mock.calls[0] as [ListQuery, AbortSignal];
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal.aborted).toBe(false);
  });

  it('aborts the previous request when the query key changes, not just ignores its response', () => {
    const abortSpy = vi.spyOn(AbortController.prototype, 'abort');
    const signals: AbortSignal[] = [];
    const fetcher = vi.fn().mockImplementation((_query: ListQuery, signal?: AbortSignal) => {
      signals.push(signal!);
      return new Promise(() => {});
    });

    const { result } = renderHook(() => useList(fetcher));
    expect(signals).toHaveLength(1);
    expect(signals[0]!.aborted).toBe(false);

    act(() => {
      result.current.setPage(2);
    });

    // The superseded page-1 request's own controller was aborted — the
    // network call itself is cancelled, not just its result discarded.
    expect(abortSpy).toHaveBeenCalledTimes(1);
    expect(signals[0]!.aborted).toBe(true);
    expect(signals[1]!.aborted).toBe(false);
  });

  it('aborts the in-flight request on unmount', () => {
    const signals: AbortSignal[] = [];
    const fetcher = vi.fn().mockImplementation((_query: ListQuery, signal?: AbortSignal) => {
      signals.push(signal!);
      return new Promise(() => {});
    });

    const { unmount } = renderHook(() => useList(fetcher));
    unmount();

    expect(signals[0]!.aborted).toBe(true);
  });

  it('does not surface a cancelled request as a visible error', async () => {
    const rejectors: Array<(cause: unknown) => void> = [];
    const fetcher = vi
      .fn()
      .mockImplementation(() => new Promise((_resolve, reject) => rejectors.push(reject)));

    const { result } = renderHook(() => useList(fetcher));

    act(() => {
      result.current.setPage(2);
    });

    rejectors[0]!(new ApiError(0, 'cancelled', '', ''));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.error).toBeNull();
  });
});
