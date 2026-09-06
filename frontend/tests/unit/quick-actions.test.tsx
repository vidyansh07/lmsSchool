import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { QuickActions } from '@/components/quick-actions';

describe('QuickActions', () => {
  it('renders nothing for an empty action list', () => {
    const { container } = render(<QuickActions actions={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a link action', () => {
    render(<QuickActions actions={[{ id: '1', label: 'Add student', href: '/admin/students/new' }]} />);
    expect(screen.getByRole('link', { name: /Add student/ })).toHaveAttribute(
      'href',
      '/admin/students/new',
    );
  });

  it('renders a button action and fires its handler', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<QuickActions actions={[{ id: '1', label: 'Start import', onClick }]} />);

    await user.click(screen.getByRole('button', { name: /Start import/ }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('shows a shortcut hint', () => {
    render(<QuickActions actions={[{ id: '1', label: 'New batch', onClick: () => {}, shortcut: 'mod+n' }]} />);
    expect(screen.getByText(/N$/)).toBeInTheDocument();
  });

  it('disables a disabled action', () => {
    render(<QuickActions actions={[{ id: '1', label: 'Locked', onClick: () => {}, disabled: true }]} />);
    expect(screen.getByRole('button', { name: 'Locked' })).toBeDisabled();
  });
});
