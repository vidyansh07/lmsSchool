/**
 * The command palette (ERP Phase 11, DESIGN_DECISIONS.md "Navigation"):
 * local navigation items filter client-side with no fetch, `GET /search/`
 * results only fire once the query reaches the backend's own 2-character
 * minimum (debounced), and ArrowUp/ArrowDown/Enter drive selection across
 * both sources as one flat, keyboard-only list.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CommandPalette } from '@/components/command-palette';
import type { SearchResponse } from '@/types/api';

const runSearch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/search', () => ({ search: runSearch }));

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

// A deterministic, two-item local nav instead of the real sidebar, so
// filtering assertions do not depend on the product's current link list.
vi.mock('@/components/navigation', () => ({
  navFor: () => [
    {
      items: [
        { href: '/activities', label: 'Activities', icon: () => null },
        { href: '/dsr', label: 'Daily reports', icon: () => null },
      ],
    },
  ],
  STAFF_ROLES: ['manager', 'trainer', 'counsellor', 'admin'],
  STUDENT_NAV: [],
  isVisible: () => true,
}));

function searchResponse(): SearchResponse {
  return {
    groups: [
      {
        type: 'student',
        label: 'Students',
        total: 1,
        results: [{ id: 's1', title: 'Asha Rao', subtitle: 'STU-001', href: '/students/s1' }],
      },
    ],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({
    user: { id: 'u1', role: 'manager', capabilities: ['search.global'] },
    can: (capability: string) => capability === 'search.global',
  });
});

describe('CommandPalette', () => {
  it('lists local navigation items with no fetch when the query is empty', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />);

    expect(screen.getByRole('option', { name: /Activities/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Daily reports/ })).toBeInTheDocument();
    expect(runSearch).not.toHaveBeenCalled();
  });

  it('moves the highlight with ArrowDown/ArrowUp and selects with Enter', () => {
    const onOpenChange = vi.fn();
    render(<CommandPalette open onOpenChange={onOpenChange} />);

    const input = screen.getByRole('combobox', { name: 'Command palette' });
    expect(screen.getByRole('option', { name: /Activities/ })).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(screen.getByRole('option', { name: /Daily reports/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('option', { name: /Activities/ })).toHaveAttribute('aria-selected', 'false');

    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(screen.getByRole('option', { name: /Activities/ })).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(push).toHaveBeenCalledWith('/activities');
  });

  it('does not search below the backend-pinned 2-character minimum', async () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />);
    const input = screen.getByRole('combobox', { name: 'Command palette' });

    fireEvent.change(input, { target: { value: 'a' } });
    expect(await screen.findByText('Keep typing to search records…')).toBeInTheDocument();

    // Past the debounce delay, a single character still never reaches `search()`.
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(runSearch).not.toHaveBeenCalled();
  });

  it('searches once debounced input reaches the minimum, and renders grouped results', async () => {
    runSearch.mockResolvedValue(searchResponse());
    render(<CommandPalette open onOpenChange={vi.fn()} />);
    const input = screen.getByRole('combobox', { name: 'Command palette' });

    fireEvent.change(input, { target: { value: 'as' } });
    // Not called immediately — the debounce has not elapsed yet.
    expect(runSearch).not.toHaveBeenCalled();

    await waitFor(() => expect(runSearch).toHaveBeenCalledWith({ q: 'as' }), { timeout: 1000 });
    expect(await screen.findByText('Asha Rao')).toBeInTheDocument();
    expect(screen.getByText('Students')).toBeInTheDocument();
  });

  it('never fetches on hover — only a keyboard chord or click selects a row', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />);
    const row = screen.getByRole('option', { name: /Daily reports/ });

    fireEvent.mouseOver(row);
    fireEvent.mouseEnter(row);

    expect(runSearch).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it('renders nothing for a signed-out visitor', () => {
    useAuth.mockReturnValue({ user: null, can: () => false });
    const { container } = render(<CommandPalette open onOpenChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
