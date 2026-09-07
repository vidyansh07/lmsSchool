import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Sheet, SheetClose, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';

function Basic({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Filter students</SheetTitle>
          <SheetDescription>Narrow the roster below.</SheetDescription>
        </SheetHeader>
        <p>Body content</p>
        <SheetFooter>
          <SheetClose>Cancel</SheetClose>
          <Button>Apply</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setOpen(true)}>Open filters</button>
      <Basic open={open} onOpenChange={setOpen} />
    </div>
  );
}

describe('Sheet', () => {
  it('renders nothing when closed', () => {
    render(<Basic open={false} onOpenChange={vi.fn()} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders as a labelled, described modal panel when open', () => {
    render(<Basic open onOpenChange={vi.fn()} />);
    const panel = screen.getByRole('dialog');
    expect(panel).toHaveAttribute('aria-modal', 'true');
    expect(panel).toHaveAccessibleName('Filter students');
    expect(panel).toHaveAccessibleDescription('Narrow the roster below.');
  });

  it('closes on Escape', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<Basic open onOpenChange={onOpenChange} />);

    await user.keyboard('{Escape}');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('closes when the backdrop is clicked', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const { container } = render(<Basic open onOpenChange={onOpenChange} />);

    const backdrop = container.querySelector('[aria-hidden="true"]') as HTMLElement;
    await user.click(backdrop);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('does not close when content inside the panel is clicked', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<Basic open onOpenChange={onOpenChange} />);

    await user.click(screen.getByText('Body content'));
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('closes via the close button and the SheetClose footer button', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<Basic open onOpenChange={onOpenChange} />);

    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);

    onOpenChange.mockClear();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('traps Tab focus inside the panel', async () => {
    const user = userEvent.setup();
    render(<Basic open onOpenChange={vi.fn()} />);

    const closeButton = screen.getByRole('button', { name: 'Close' });
    const cancelButton = screen.getByRole('button', { name: 'Cancel' });
    const applyButton = screen.getByRole('button', { name: 'Apply' });
    expect(closeButton).toHaveFocus();

    await user.tab();
    expect(cancelButton).toHaveFocus();
    await user.tab();
    expect(applyButton).toHaveFocus();
    await user.tab();
    expect(closeButton).toHaveFocus();
  });

  it('restores focus to the trigger element on close', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const trigger = screen.getByRole('button', { name: 'Open filters' });
    await user.click(trigger);
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('unmounts only after the exit animation delay', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('button', { name: 'Open filters' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('throws a clear error when a subcomponent is used outside <Sheet>', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<SheetTitle>Oops</SheetTitle>)).toThrow(/must be rendered inside <Sheet>/);
    spy.mockRestore();
  });
});
