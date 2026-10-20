/**
 * Saved views: a person's named list queries, kept on the server. Applying
 * one replaces every key it owns; saving needs a filter to save; rename and
 * delete are per chip; a failed load is said.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ListToolbar } from '@/components/list-toolbar';
import { SavedViews } from '@/components/saved-views';
import type { ListQuery } from '@/lib/people';

const listSavedFilters = vi.hoisted(() => vi.fn());
const createSavedFilter = vi.hoisted(() => vi.fn());
const deleteSavedFilter = vi.hoisted(() => vi.fn());
vi.mock('@/lib/saved-filters', () => ({ listSavedFilters, createSavedFilter, deleteSavedFilter }));

const KEYS = ['search', 'ordering', 'role', 'is_active'] as const;

function Harness({ initial = {} }: { initial?: ListQuery }) {
  const [query, setQuery] = useState<ListQuery>(initial);
  return (
    <>
      <SavedViews
        screen="admin-users"
        keys={KEYS}
        query={query}
        onApply={(changes) => setQuery((current) => ({ ...current, ...changes }))}
      />
      <ListToolbar
        search={String(query.search ?? '')}
        onSearchChange={(value) => setQuery((current) => ({ ...current, search: value }))}
      />
      <output data-testid="query">{JSON.stringify(query)}</output>
    </>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listSavedFilters.mockResolvedValue([
    {
      id: 'v1',
      screen: 'admin-users',
      name: 'Inactive managers',
      filters: { role: 'manager', is_active: 'false', search: 'ra' },
      created_at: '2026-10-15T00:00:00Z',
    },
  ]);
});

describe('SavedViews', () => {
  it('applies a view, replacing every key it owns, and the search box shows it', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ role: 'admin', ordering: 'email' }} />);

    await user.click(await screen.findByRole('button', { name: 'Inactive managers' }));
    const query = JSON.parse(screen.getByTestId('query').textContent ?? '{}') as ListQuery;
    expect(query).toMatchObject({ role: 'manager', is_active: 'false', search: 'ra' });
    expect(query.ordering).toBeUndefined();
    expect(screen.getByLabelText('Search')).toHaveValue('ra');
    // And the box does not write the old (empty) search back after its debounce.
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(JSON.parse(screen.getByTestId('query').textContent ?? '{}')).toMatchObject({ search: 'ra' });
  });

  it('saves the current query under a name', async () => {
    createSavedFilter.mockImplementation(async (payload: { name: string; filters: object }) => ({
      id: 'v2',
      screen: 'admin-users',
      created_at: '2026-10-15T00:00:00Z',
      ...payload,
    }));
    const user = userEvent.setup();
    render(<Harness initial={{ role: 'counsellor', page: 3 }} />);

    await user.click(await screen.findByRole('button', { name: 'Save this view' }));
    await user.type(screen.getByLabelText('Name this view'), 'Counsellors{Enter}');
    await waitFor(() =>
      expect(createSavedFilter).toHaveBeenCalledWith({
        screen: 'admin-users',
        name: 'Counsellors',
        filters: { role: 'counsellor' },
      }),
    );
    expect(await screen.findByRole('button', { name: 'Counsellors' })).toBeInTheDocument();
  });

  it('renames and removes a view', async () => {
    createSavedFilter.mockImplementation(async (payload: { name: string; filters: object }) => ({
      id: 'v3',
      screen: 'admin-users',
      created_at: '2026-10-15T00:00:00Z',
      ...payload,
    }));
    deleteSavedFilter.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(await screen.findByRole('button', { name: 'Rename saved view Inactive managers' }));
    const box = screen.getByLabelText('New name for this view');
    await user.clear(box);
    await user.type(box, 'Dormant managers{Enter}');
    await waitFor(() => expect(deleteSavedFilter).toHaveBeenCalledWith('v1'));
    expect(await screen.findByRole('button', { name: 'Dormant managers' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Remove saved view Dormant managers' }));
    await waitFor(() => expect(deleteSavedFilter).toHaveBeenCalledWith('v3'));
  });

  it('says when the views could not be loaded', async () => {
    listSavedFilters.mockRejectedValue(new Error('offline'));
    render(<Harness />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load your saved views|went wrong/i);
  });
});
