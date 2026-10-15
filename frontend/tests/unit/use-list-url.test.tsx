/**
 * A main list keeps its search, sort, page and filters in the address bar,
 * so a refresh, Back from a record, or a pasted link returns to the same rows.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useList } from '@/hooks/use-list';
import type { ListQuery } from '@/lib/people';
import type { Paginated } from '@/types/api';

function emptyPage(_query: ListQuery, _signal?: AbortSignal): Promise<Paginated<never>> {
  return Promise.resolve({
    count: 0,
    page: 1,
    page_size: 20,
    total_pages: 1,
    next: null,
    previous: null,
    results: [],
  } as Paginated<never>);
}

describe('useList with urlKeys', () => {
  it('starts from the address bar and writes changes back to it', async () => {
    window.history.replaceState(null, '', '/admin/users?role=manager&search=asha&page=3&tab=keep');
    const fetcher = vi.fn(emptyPage);
    const { result } = renderHook(() => useList(fetcher, {}, { urlKeys: ['role', 'is_active'] }));

    await waitFor(() => expect(fetcher).toHaveBeenCalled());
    expect(fetcher.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({ role: 'manager', search: 'asha', page: 3 }),
    );
    // A parameter the list does not own is neither read nor removed.
    expect(fetcher.mock.calls[0]?.[0]).not.toHaveProperty('tab');

    act(() => result.current.setQuery({ is_active: 'false', role: '' }));
    await waitFor(() =>
      expect(window.location.search).toBe('?search=asha&tab=keep&is_active=false'),
    );
  });

  it('leaves the address bar alone for a list that did not opt in', async () => {
    window.history.replaceState(null, '', '/somewhere?search=other');
    const fetcher = vi.fn(emptyPage);
    const { result } = renderHook(() => useList(fetcher));
    await waitFor(() => expect(fetcher).toHaveBeenCalled());
    expect(fetcher.mock.calls[0]?.[0]).not.toHaveProperty('search');
    act(() => result.current.setQuery({ search: 'mine' }));
    expect(window.location.search).toBe('?search=other');
  });
});
