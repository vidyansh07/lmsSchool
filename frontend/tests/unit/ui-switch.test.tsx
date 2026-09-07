import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Switch } from '@/components/ui/switch';

function Controlled() {
  const [checked, setChecked] = useState(false);
  return <Switch aria-label="Email notifications" checked={checked} onCheckedChange={setChecked} />;
}

describe('Switch', () => {
  it('renders as a switch with aria-checked reflecting its state', () => {
    render(<Switch aria-label="Email notifications" defaultChecked />);
    expect(screen.getByRole('switch', { name: 'Email notifications' })).toHaveAttribute('aria-checked', 'true');
  });

  it('supports uncontrolled usage, toggling on click', async () => {
    const user = userEvent.setup();
    render(<Switch aria-label="Email notifications" defaultChecked={false} />);
    const control = screen.getByRole('switch');
    expect(control).toHaveAttribute('aria-checked', 'false');

    await user.click(control);
    expect(control).toHaveAttribute('aria-checked', 'true');
  });

  it('supports controlled usage', async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const control = screen.getByRole('switch');
    expect(control).toHaveAttribute('aria-checked', 'false');

    await user.click(control);
    expect(control).toHaveAttribute('aria-checked', 'true');
  });

  it('calls onCheckedChange without moving a controlled switch until the prop changes', async () => {
    const user = userEvent.setup();
    const onCheckedChange = vi.fn();
    render(<Switch aria-label="Email notifications" checked={false} onCheckedChange={onCheckedChange} />);

    await user.click(screen.getByRole('switch'));
    expect(onCheckedChange).toHaveBeenCalledWith(true);
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
  });

  it('toggles from the keyboard with the Space key', async () => {
    const user = userEvent.setup();
    render(<Switch aria-label="Email notifications" defaultChecked={false} />);
    await user.tab();
    expect(screen.getByRole('switch')).toHaveFocus();

    await user.keyboard(' ');
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
  });

  it('is non-interactive when disabled', async () => {
    const user = userEvent.setup();
    render(<Switch aria-label="Email notifications" disabled defaultChecked={false} />);
    const control = screen.getByRole('switch');
    expect(control).toBeDisabled();

    await user.click(control);
    expect(control).toHaveAttribute('aria-checked', 'false');
  });
});
