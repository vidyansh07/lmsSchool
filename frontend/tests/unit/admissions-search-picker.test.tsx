import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { SearchPicker, type PickerOption } from '@/components/admissions/search-picker';

const OPTIONS: PickerOption[] = [
  { value: '1', label: 'Linux Essentials', hint: 'GRS-C-001' },
  { value: '2', label: 'Linux Advanced', hint: 'GRS-C-002' },
];

function Harness({
  options = OPTIONS,
  onSelect,
  emptyMessage,
}: {
  options?: PickerOption[];
  onSelect: (o: PickerOption) => void;
  emptyMessage?: string;
}) {
  const [query, setQuery] = useState('');
  return (
    <SearchPicker
      label="Course"
      query={query}
      onQueryChange={setQuery}
      options={options}
      selected=""
      onSelect={onSelect}
      emptyMessage={emptyMessage}
    />
  );
}

describe('SearchPicker', () => {
  it('shows a labelled search field', () => {
    render(<Harness onSelect={vi.fn()} />);
    expect(screen.getByLabelText('Course')).toBeInTheDocument();
  });

  it('lists every option as a keyboard-reachable listbox entry', () => {
    render(<Harness onSelect={vi.fn()} />);
    expect(screen.getByRole('option', { name: /Linux Essentials/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Linux Advanced/ })).toBeInTheDocument();
  });

  it('shows the hint alongside the label', () => {
    render(<Harness onSelect={vi.fn()} />);
    expect(screen.getByText(/Linux Essentials — GRS-C-001/)).toBeInTheDocument();
  });

  it('selects the only match when Enter is pressed', async () => {
    const onSelect = vi.fn();
    render(<Harness options={[OPTIONS[0]!]} onSelect={onSelect} />);
    await userEvent.type(screen.getByLabelText('Course'), 'Essentials{Enter}');
    expect(onSelect).toHaveBeenCalledWith(OPTIONS[0]);
  });

  it('does not guess when Enter is pressed with more than one match', async () => {
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    await userEvent.type(screen.getByLabelText('Course'), 'Linux{Enter}');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('moves focus into the results list on ArrowDown', async () => {
    render(<Harness onSelect={vi.fn()} />);
    const input = screen.getByLabelText('Course');
    input.focus();
    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getByLabelText('Course results')).toHaveFocus();
  });

  it('calls onSelect when an option is chosen from the list', async () => {
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    await userEvent.selectOptions(screen.getByLabelText('Course results'), '2');
    expect(onSelect).toHaveBeenCalledWith(OPTIONS[1]);
  });

  it('shows a message instead of a list when there are no options', () => {
    render(<Harness options={[]} onSelect={vi.fn()} />);
    expect(screen.getByText('No matches.')).toBeInTheDocument();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('shows a searching indicator while loading, not the empty message', () => {
    render(
      <SearchPicker
        label="Course"
        query="linux"
        onQueryChange={vi.fn()}
        options={[]}
        selected=""
        onSelect={vi.fn()}
        isLoading
      />,
    );
    expect(screen.getAllByText('Searching…').length).toBeGreaterThan(0);
    expect(screen.queryByText('No matches.')).not.toBeInTheDocument();
  });
});
