import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useApi } from '@/hooks/use-api';
import { ApiError } from '@/lib/api';

const apiFetch = vi.fn();

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetch(...args) };
});

describe('useApi', () => {
  afterEach(() => {
    apiFetch.mockReset();
  });

  it('resolves data on success', async () => {
    apiFetch.mockResolvedValue({ ok: true });
    const { result } = renderHook(() => useApi<{ ok: boolean }>('/a/'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toEqual({ ok: true });
    expect(result.current.error).toBeNull();
  });

  it('passes an AbortSignal to apiFetch', () => {
    apiFetch.mockImplementation(() => new Promise(() => {}));
    renderHook(() => useApi('/a/'));

    expect(apiFetch).toHaveBeenCalledTimes(1);
    const [, options] = apiFetch.mock.calls[0] as [string, { signal?: AbortSignal }];
    expect(options.signal).toBeInstanceOf(AbortSignal);
    expect(options.signal!.aborted).toBe(false);
  });

  it('aborts the previous request when the path changes, not just ignores its response', () => {
    const abortSpy = vi.spyOn(AbortController.prototype, 'abort');
    const signals: AbortSignal[] = [];
    apiFetch.mockImplementation((_path: string, options?: { signal?: AbortSignal }) => {
      signals.push(options!.signal!);
      return new Promise(() => {});
    });

    const { rerender } = renderHook(({ path }) => useApi(path), { initialProps: { path: '/a/' } });
    expect(signals).toHaveLength(1);
    expect(signals[0]!.aborted).toBe(false);

    rerender({ path: '/b/' });

    // The old request's own controller was aborted — the network call is
    // actually cancelled, not merely superseded in state.
    expect(abortSpy).toHaveBeenCalledTimes(1);
    expect(signals[0]!.aborted).toBe(true);
    expect(signals[1]!.aborted).toBe(false);

    abortSpy.mockRestore();
  });

  it('aborts the in-flight request on unmount', () => {
    const signals: AbortSignal[] = [];
    apiFetch.mockImplementation((_path: string, options?: { signal?: AbortSignal }) => {
      signals.push(options!.signal!);
      return new Promise(() => {});
    });

    const { unmount } = renderHook(() => useApi('/a/'));
    unmount();

    expect(signals[0]!.aborted).toBe(true);
  });

  it('does not surface a cancelled request as a visible error', async () => {
    const rejectors: Array<(cause: unknown) => void> = [];
    apiFetch.mockImplementation(
      () => new Promise((_resolve, reject) => rejectors.push(reject)),
    );

    const { result, rerender } = renderHook(({ path }) => useApi(path), {
      initialProps: { path: '/a/' },
    });
    rerender({ path: '/b/' });

    // Simulate the superseded request's fetch rejecting with the abort it was
    // just given, after the newer render has already taken over.
    rejectors[0]!(new ApiError(0, 'cancelled', '', ''));
    await Promise.resolve();
    await Promise.resolve();

    expect(result.current.error).toBeNull();
  });
});
