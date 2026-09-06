import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SavedFilters } from '@/components/saved-filters';

describe('SavedFilters', () => {
  beforeEach(() => window.localStorage.clear());

  it('renders no chips initially', () => {
    render(<SavedFilters scope="admin-users" currentFilters={{ status: 'active' }} onApply={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /Remove saved filter/ })).not.toBeInTheDocument();
  });

  it('saves the current filters under a name', async () => {
    const user = userEvent.setup();
    render(<SavedFilters scope="admin-users" currentFilters={{ status: 'active' }} onApply={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: 'Save current filters' }));
    await user.type(screen.getByLabelText('Name this filter'), 'Active staff');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(screen.getByText('Active staff')).toBeInTheDocument();
  });

  it('applies a saved filter when its chip is clicked', async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();
    render(<SavedFilters scope="admin-users" currentFilters={{ status: 'active' }} onApply={onApply} />);

    await user.click(screen.getByRole('button', { name: 'Save current filters' }));
    await user.type(screen.getByLabelText('Name this filter'), 'Active staff');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await user.click(screen.getByRole('button', { name: 'Active staff' }));
    expect(onApply).toHaveBeenCalledWith({ status: 'active' });
  });

  it('removes a saved filter', async () => {
    const user = userEvent.setup();
    render(<SavedFilters scope="admin-users" currentFilters={{ status: 'active' }} onApply={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: 'Save current filters' }));
    await user.type(screen.getByLabelText('Name this filter'), 'Active staff');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await user.click(screen.getByRole('button', { name: 'Remove saved filter Active staff' }));
    expect(screen.queryByText('Active staff')).not.toBeInTheDocument();
  });

  it('cancels naming on Escape without saving', async () => {
    const user = userEvent.setup();
    render(<SavedFilters scope="admin-users" currentFilters={{ status: 'active' }} onApply={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: 'Save current filters' }));
    await user.type(screen.getByLabelText('Name this filter'), 'Draft');
    await user.keyboard('{Escape}');

    expect(screen.queryByText('Draft')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save current filters' })).toBeInTheDocument();
  });

  it('does not save a blank name', async () => {
    const user = userEvent.setup();
    render(<SavedFilters scope="admin-users" currentFilters={{ status: 'active' }} onApply={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: 'Save current filters' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(screen.queryByRole('button', { name: /Remove saved filter/ })).not.toBeInTheDocument();
  });
});
