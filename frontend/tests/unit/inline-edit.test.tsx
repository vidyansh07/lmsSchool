import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { InlineEdit } from '@/components/inline-edit';

describe('InlineEdit', () => {
  it('shows the value read-only until activated', () => {
    render(<InlineEdit value="Ada" label="Trainer name" onSave={vi.fn()} />);
    expect(screen.getByText('Ada')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('enters edit mode on click', async () => {
    const user = userEvent.setup();
    render(<InlineEdit value="Ada" label="Trainer name" onSave={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: /Edit Trainer name/ }));
    expect(screen.getByRole('textbox', { name: 'Trainer name' })).toHaveValue('Ada');
  });

  it('enters edit mode on Enter', async () => {
    const user = userEvent.setup();
    render(<InlineEdit value="Ada" label="Trainer name" onSave={vi.fn()} />);

    screen.getByRole('button', { name: /Edit Trainer name/ }).focus();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('textbox', { name: 'Trainer name' })).toBeInTheDocument();
  });

  it('saves on Enter', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<InlineEdit value="Ada" label="Trainer name" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /Edit Trainer name/ }));
    const input = screen.getByRole('textbox', { name: 'Trainer name' });
    await user.clear(input);
    await user.type(input, 'Grace');
    await user.keyboard('{Enter}');

    expect(onSave).toHaveBeenCalledWith('Grace');
  });

  it('saves on blur', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <div>
        <InlineEdit value="Ada" label="Trainer name" onSave={onSave} />
        <button>Elsewhere</button>
      </div>,
    );

    await user.click(screen.getByRole('button', { name: /Edit Trainer name/ }));
    const input = screen.getByRole('textbox', { name: 'Trainer name' });
    await user.clear(input);
    await user.type(input, 'Grace');
    await user.click(screen.getByRole('button', { name: 'Elsewhere' }));

    expect(onSave).toHaveBeenCalledWith('Grace');
  });

  it('does not call onSave when the value is unchanged', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<InlineEdit value="Ada" label="Trainer name" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /Edit Trainer name/ }));
    await user.keyboard('{Enter}');

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText('Ada')).toBeInTheDocument();
  });

  it('cancels on Escape without saving', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<InlineEdit value="Ada" label="Trainer name" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /Edit Trainer name/ }));
    const input = screen.getByRole('textbox', { name: 'Trainer name' });
    await user.clear(input);
    await user.type(input, 'Grace');
    await user.keyboard('{Escape}');

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText('Ada')).toBeInTheDocument();
  });

  it('cancels via the cancel button without committing on blur', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<InlineEdit value="Ada" label="Trainer name" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /Edit Trainer name/ }));
    const input = screen.getByRole('textbox', { name: 'Trainer name' });
    await user.clear(input);
    await user.type(input, 'Grace');
    await user.click(screen.getByRole('button', { name: /Cancel editing/ }));

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText('Ada')).toBeInTheDocument();
  });

  it('rolls back visibly and shows an error on save failure', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue(new Error('That name is already in use.'));
    render(<InlineEdit value="Ada" label="Trainer name" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /Edit Trainer name/ }));
    const input = screen.getByRole('textbox', { name: 'Trainer name' });
    await user.clear(input);
    await user.type(input, 'Grace');
    await user.keyboard('{Enter}');

    expect(await screen.findByRole('alert')).toHaveTextContent('That name is already in use.');
    expect(screen.getByRole('textbox', { name: 'Trainer name' })).toHaveValue('Ada');
  });

  it('formats the read-only display value', () => {
    render(<InlineEdit value="500" label="Fee" onSave={vi.fn()} formatValue={(v) => `₹${v}`} />);
    expect(screen.getByText('₹500')).toBeInTheDocument();
  });
});
