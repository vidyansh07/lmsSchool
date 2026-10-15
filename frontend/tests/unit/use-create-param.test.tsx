/**
 * `?create=1` opens a screen's add dialog — on arrival, and also when the
 * parameter is added to a page that is already open (the command palette
 * used from the screen it points at).
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useCreateParam } from '@/hooks/use-create-param';

const params = vi.hoisted(() => ({ value: new URLSearchParams() }));
vi.mock('next/navigation', () => ({ useSearchParams: () => params.value }));

describe('useCreateParam', () => {
  it('opens when ?create=1 arrives on an open page, and clears it on close', () => {
    params.value = new URLSearchParams();
    window.history.replaceState(null, '', '/admin/users');
    const { result, rerender } = renderHook(() => useCreateParam(true));
    expect(result.current[0]).toBe(false);

    params.value = new URLSearchParams('create=1');
    window.history.replaceState(null, '', '/admin/users?create=1&role=manager');
    rerender();
    expect(result.current[0]).toBe(true);

    act(() => result.current[1](false));
    expect(result.current[0]).toBe(false);
    expect(window.location.search).toBe('?role=manager');
  });

  it('never opens for someone who may not create', () => {
    params.value = new URLSearchParams('create=1');
    const { result } = renderHook(() => useCreateParam(false));
    expect(result.current[0]).toBe(false);
  });
});
