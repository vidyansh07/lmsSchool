/**
 * What a list is narrowed by, in words, removable one at a time or all at
 * once — so an empty table is never mistaken for "there is nothing".
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ActiveFilters } from '@/components/active-filters';

describe('ActiveFilters', () => {
  it('says each active filter in words and removes one or all', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ActiveFilters
        query={{ search: 'asha', role: 'manager', is_active: '', page: 2 }}
        onChange={onChange}
        filters={[
          { key: 'search', label: 'Search' },
          { key: 'role', label: 'Role', display: (value) => (value === 'manager' ? 'Manager' : value) },
          { key: 'is_active', label: 'Status' },
        ]}
      />,
    );

    expect(screen.getByText('Manager')).toBeInTheDocument();
    expect(screen.queryByText('Status:')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Remove filter Role: Manager' }));
    expect(onChange).toHaveBeenLastCalledWith({ role: undefined });
    await user.click(screen.getByRole('button', { name: 'Clear all' }));
    expect(onChange).toHaveBeenLastCalledWith({ search: undefined, role: undefined });
  });

  it('renders nothing when the list is not narrowed', () => {
    const { container } = render(
      <ActiveFilters query={{ page: 1 }} onChange={vi.fn()} filters={[{ key: 'search', label: 'Search' }]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
