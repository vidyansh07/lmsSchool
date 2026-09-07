import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { Popover, PopoverContent, PopoverHeading, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';

function Basic() {
  return (
    <Popover>
      <PopoverTrigger>Filters</PopoverTrigger>
      <PopoverContent data-testid="panel">
        <PopoverHeading>Filter by status</PopoverHeading>
        <p>Panel body</p>
      </PopoverContent>
    </Popover>
  );
}

describe('Popover', () => {
  it('is closed by default', () => {
    render(<Basic />);
    expect(screen.queryByTestId('panel')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Filters' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('opens on trigger click', async () => {
    const user = userEvent.setup();
    render(<Basic />);

    await user.click(screen.getByRole('button', { name: 'Filters' }));
    expect(screen.getByTestId('panel')).toBeInTheDocument();
    expect(screen.getByText('Panel body')).toBeInTheDocument();
  });

  it('renders the caller\'s own element as the trigger via asChild', async () => {
    const user = userEvent.setup();
    render(
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline">Custom trigger</Button>
        </PopoverTrigger>
        <PopoverContent data-testid="panel">Content</PopoverContent>
      </Popover>,
    );
    const trigger = screen.getByRole('button', { name: 'Custom trigger' });
    expect(trigger).toHaveClass('border');

    await user.click(trigger);
    expect(screen.getByTestId('panel')).toBeInTheDocument();
  });

  it('labels the panel from PopoverHeading', async () => {
    const user = userEvent.setup();
    render(<Basic />);

    await user.click(screen.getByRole('button', { name: 'Filters' }));
    const panel = screen.getByTestId('panel');
    const heading = screen.getByText('Filter by status');
    expect(panel).toHaveAttribute('aria-labelledby', heading.id);
  });

  it('moves focus into the panel on open', async () => {
    const user = userEvent.setup();
    render(<Basic />);

    await user.click(screen.getByRole('button', { name: 'Filters' }));
    expect(screen.getByTestId('panel')).toHaveFocus();
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    const user = userEvent.setup();
    render(<Basic />);
    const trigger = screen.getByRole('button', { name: 'Filters' });

    await user.click(trigger);
    await user.keyboard('{Escape}');
    expect(trigger).toHaveFocus();
    await waitFor(() => expect(screen.queryByTestId('panel')).not.toBeInTheDocument());
  });

  it('closes on an outside click', async () => {
    const user = userEvent.setup();
    render(
      <div>
        <Basic />
        <button>Elsewhere</button>
      </div>,
    );

    await user.click(screen.getByRole('button', { name: 'Filters' }));
    expect(screen.getByTestId('panel')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Elsewhere' }));
    await waitFor(() => expect(screen.queryByTestId('panel')).not.toBeInTheDocument());
  });

  it('supports controlled open state', async () => {
    function Controlled() {
      const [open, setOpen] = useState(true);
      return (
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger>Filters</PopoverTrigger>
          <PopoverContent data-testid="panel">Content</PopoverContent>
        </Popover>
      );
    }
    render(<Controlled />);
    expect(screen.getByTestId('panel')).toBeInTheDocument();
  });
});
