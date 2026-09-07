import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

function Basic({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete this batch?</DialogTitle>
          <DialogDescription>This cannot be undone.</DialogDescription>
        </DialogHeader>
        <p>Body content</p>
        <DialogFooter>
          <DialogClose>Cancel</DialogClose>
          <Button>Confirm</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setOpen(true)}>Open dialog</button>
      <Basic open={open} onOpenChange={setOpen} />
    </div>
  );
}

describe('Dialog', () => {
  it('renders nothing when closed', () => {
    render(<Basic open={false} onOpenChange={vi.fn()} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders as a labelled, described modal dialog when open', () => {
    render(<Basic open onOpenChange={vi.fn()} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleName('Delete this batch?');
    expect(dialog).toHaveAccessibleDescription('This cannot be undone.');
  });

  it('has no dangling aria-describedby when there is no DialogDescription', () => {
    render(
      <Dialog open onOpenChange={vi.fn()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Untitled action</DialogTitle>
          </DialogHeader>
        </DialogContent>
      </Dialog>,
    );
    expect(screen.getByRole('dialog')).not.toHaveAttribute('aria-describedby');
  });

  it('moves initial focus inside the dialog', () => {
    render(<Basic open onOpenChange={vi.fn()} />);
    expect(screen.getByRole('dialog')).toContainElement(document.activeElement as HTMLElement);
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

  it('does not close when content inside the dialog is clicked', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<Basic open onOpenChange={onOpenChange} />);

    await user.click(screen.getByText('Body content'));
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('closes via the built-in close button and the DialogClose footer button', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<Basic open onOpenChange={onOpenChange} />);

    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);

    onOpenChange.mockClear();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('hides the built-in close button when asked', () => {
    render(
      <Dialog open onOpenChange={vi.fn()}>
        <DialogContent hideCloseButton>
          <DialogTitle>No close button</DialogTitle>
        </DialogContent>
      </Dialog>,
    );
    expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument();
  });

  it('traps Tab focus inside the dialog', async () => {
    const user = userEvent.setup();
    render(<Basic open onOpenChange={vi.fn()} />);

    const closeButton = screen.getByRole('button', { name: 'Close' });
    const cancelButton = screen.getByRole('button', { name: 'Cancel' });
    const confirmButton = screen.getByRole('button', { name: 'Confirm' });
    expect(closeButton).toHaveFocus();

    await user.tab();
    expect(cancelButton).toHaveFocus();
    await user.tab();
    expect(confirmButton).toHaveFocus();
    await user.tab();
    expect(closeButton).toHaveFocus();
    await user.tab({ shift: true });
    expect(confirmButton).toHaveFocus();
  });

  it('restores focus to the trigger element on close', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const trigger = screen.getByRole('button', { name: 'Open dialog' });
    await user.click(trigger);
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('locks page scroll while open and restores it on close', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(document.body.style.overflow).not.toBe('hidden');

    await user.click(screen.getByRole('button', { name: 'Open dialog' }));
    expect(document.body.style.overflow).toBe('hidden');

    await user.keyboard('{Escape}');
    await waitFor(() => expect(document.body.style.overflow).not.toBe('hidden'));
  });

  it('unmounts only after the exit animation delay', async () => {
    render(<Harness />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Open dialog' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('throws a clear error when a subcomponent is used outside <Dialog>', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<DialogTitle>Oops</DialogTitle>)).toThrow(/must be rendered inside <Dialog>/);
    spy.mockRestore();
  });
});
