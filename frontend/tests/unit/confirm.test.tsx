import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Confirm } from '@/components/confirm';

function Harness({ open }: { open: boolean }) {
  const [isOpen, setOpen] = useState(open);
  return (
    <div>
      <button onClick={() => setOpen(true)}>Delete account</button>
      <Confirm
        open={isOpen}
        title="Delete this account?"
        description="This cannot be undone."
        onConfirm={() => setOpen(false)}
        onCancel={() => setOpen(false)}
      />
    </div>
  );
}

describe('Confirm', () => {
  it('renders nothing when closed', () => {
    render(<Confirm open={false} title="Delete?" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('renders the title and description as an alertdialog when open', () => {
    render(
      <Confirm open title="Delete this account?" description="This cannot be undone." onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveAccessibleName('Delete this account?');
    expect(dialog).toHaveAccessibleDescription('This cannot be undone.');
  });

  it('calls onConfirm when the confirm button is clicked', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<Confirm open title="Delete?" confirmLabel="Delete" onConfirm={onConfirm} onCancel={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('calls onCancel on Escape', async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(<Confirm open title="Delete?" onConfirm={vi.fn()} onCancel={onCancel} />);

    await user.keyboard('{Escape}');
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('calls onCancel when clicking the backdrop', async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const { container } = render(<Confirm open title="Delete?" onConfirm={vi.fn()} onCancel={onCancel} />);

    // The outermost fixed-position element is the backdrop.
    await user.click(container.firstElementChild as HTMLElement);
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('moves initial focus to the cancel button, not confirm', () => {
    render(<Confirm open title="Delete?" cancelLabel="Keep it" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Keep it' })).toHaveFocus();
  });

  it('traps Tab focus inside the dialog', async () => {
    const user = userEvent.setup();
    render(<Confirm open title="Delete?" cancelLabel="Keep it" confirmLabel="Delete" onConfirm={vi.fn()} onCancel={vi.fn()} />);

    const cancelButton = screen.getByRole('button', { name: 'Keep it' });
    const confirmButton = screen.getByRole('button', { name: 'Delete' });
    expect(cancelButton).toHaveFocus();

    await user.tab();
    expect(confirmButton).toHaveFocus();

    await user.tab();
    expect(cancelButton).toHaveFocus();

    await user.tab({ shift: true });
    expect(confirmButton).toHaveFocus();
  });

  it('restores focus to the trigger element on close', async () => {
    const user = userEvent.setup();
    render(<Harness open={false} />);

    const trigger = screen.getByRole('button', { name: 'Delete account' });
    await user.click(trigger);
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(trigger).toHaveFocus();
  });

  it('disables both buttons while confirming', () => {
    render(<Confirm open title="Delete?" isConfirming onConfirm={vi.fn()} onCancel={vi.fn()} />);
    for (const button of screen.getAllByRole('button')) {
      expect(button).toBeDisabled();
    }
  });
});
