import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';

function Basic(props: { onSelectEdit?: () => void; onSelectDelete?: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger>Actions</DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel>Batch</DropdownMenuLabel>
        <DropdownMenuItem onSelect={props.onSelectEdit}>Edit</DropdownMenuItem>
        <DropdownMenuItem disabled>Archive</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem destructive onSelect={props.onSelectDelete}>
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

describe('DropdownMenu', () => {
  it('is closed by default', () => {
    render(<Basic />);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Actions' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('opens on trigger click and shows its items', async () => {
    const user = userEvent.setup();
    render(<Basic />);

    await user.click(screen.getByRole('button', { name: 'Actions' }));
    expect(screen.getByRole('menu')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Actions' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('menuitem', { name: 'Edit' })).toBeInTheDocument();
  });

  it('renders its own trigger as a real button, and the caller\'s element via asChild', () => {
    render(<Basic />);
    expect(screen.getByRole('button', { name: 'Actions' }).tagName).toBe('BUTTON');

    render(
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline">Custom trigger</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>Only item</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    const trigger = screen.getByRole('button', { name: 'Custom trigger' });
    expect(trigger).toHaveClass('border'); // Button's outline variant, proving no extra wrapper swallowed it
  });

  it('calls onSelect and closes when an item is chosen', async () => {
    const user = userEvent.setup();
    const onSelectEdit = vi.fn();
    render(<Basic onSelectEdit={onSelectEdit} />);

    await user.click(screen.getByRole('button', { name: 'Actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Edit' }));

    expect(onSelectEdit).toHaveBeenCalledOnce();
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });

  it('moves focus between items with ArrowDown, skipping disabled ones', async () => {
    const user = userEvent.setup();
    render(<Basic />);

    await user.click(screen.getByRole('button', { name: 'Actions' }));
    expect(screen.getByRole('menuitem', { name: 'Edit' })).toHaveFocus();

    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toHaveFocus();
  });

  it('wraps from the last item to the first with ArrowDown', async () => {
    const user = userEvent.setup();
    render(<Basic />);

    await user.click(screen.getByRole('button', { name: 'Actions' }));
    await user.keyboard('{ArrowDown}'); // Edit -> Delete (Archive is disabled)
    await user.keyboard('{ArrowDown}'); // wraps back to Edit
    expect(screen.getByRole('menuitem', { name: 'Edit' })).toHaveFocus();
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    const user = userEvent.setup();
    render(<Basic />);
    const trigger = screen.getByRole('button', { name: 'Actions' });

    await user.click(trigger);
    await user.keyboard('{Escape}');
    expect(trigger).toHaveFocus();
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });

  it('closes on an outside click', async () => {
    const user = userEvent.setup();
    render(
      <div>
        <Basic />
        <button>Elsewhere</button>
      </div>,
    );

    await user.click(screen.getByRole('button', { name: 'Actions' }));
    expect(screen.getByRole('menu')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Elsewhere' }));
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });

  it('supports controlled open state', async () => {
    function Controlled() {
      const [open, setOpen] = useState(false);
      return (
        <DropdownMenu open={open} onOpenChange={setOpen}>
          <DropdownMenuTrigger>Actions</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem>Only item</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      );
    }
    const user = userEvent.setup();
    render(<Controlled />);

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Actions' }));
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });

  it('does not activate a disabled item', async () => {
    const user = userEvent.setup();
    const onSelectEdit = vi.fn();
    render(<Basic onSelectEdit={onSelectEdit} />);

    await user.click(screen.getByRole('button', { name: 'Actions' }));
    expect(screen.getByRole('menuitem', { name: 'Archive' })).toBeDisabled();
  });
});
