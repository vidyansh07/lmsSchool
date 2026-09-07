import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Checkbox } from '@/components/ui/checkbox';

function Controlled() {
  const [checked, setChecked] = useState(false);
  return <Checkbox aria-label="Select row" checked={checked} onCheckedChange={setChecked} />;
}

describe('Checkbox', () => {
  it('renders a native checkbox', () => {
    render(<Checkbox aria-label="Select row" />);
    expect(screen.getByRole('checkbox', { name: 'Select row' })).toBeInTheDocument();
  });

  it('supports uncontrolled usage, toggling on click', async () => {
    const user = userEvent.setup();
    render(<Checkbox aria-label="Select row" defaultChecked={false} />);
    const control = screen.getByRole('checkbox');
    expect(control).not.toBeChecked();

    await user.click(control);
    expect(control).toBeChecked();
  });

  it('supports controlled usage', async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const control = screen.getByRole('checkbox');

    await user.click(control);
    expect(control).toBeChecked();
  });

  it('calls onCheckedChange with the next boolean', async () => {
    const user = userEvent.setup();
    const onCheckedChange = vi.fn();
    render(<Checkbox aria-label="Select row" checked={false} onCheckedChange={onCheckedChange} />);

    await user.click(screen.getByRole('checkbox'));
    expect(onCheckedChange).toHaveBeenCalledWith(true);
  });

  it('sets the indeterminate DOM property, which has no HTML attribute equivalent', () => {
    render(<Checkbox aria-label="Select all" checked="indeterminate" />);
    expect(screen.getByRole('checkbox')).toHaveProperty('indeterminate', true);
  });

  it('toggles from the keyboard with the Space key', async () => {
    const user = userEvent.setup();
    render(<Checkbox aria-label="Select row" defaultChecked={false} />);
    await user.tab();
    expect(screen.getByRole('checkbox')).toHaveFocus();

    await user.keyboard(' ');
    expect(screen.getByRole('checkbox')).toBeChecked();
  });

  it('is non-interactive when disabled', async () => {
    const user = userEvent.setup();
    render(<Checkbox aria-label="Select row" disabled defaultChecked={false} />);
    const control = screen.getByRole('checkbox');
    expect(control).toBeDisabled();

    await user.click(control);
    expect(control).not.toBeChecked();
  });
});
