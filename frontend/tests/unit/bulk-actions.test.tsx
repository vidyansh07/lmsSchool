import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { BulkActionsBar } from '@/components/bulk-actions';

describe('BulkActionsBar', () => {
  it('renders nothing when nothing is selected', () => {
    const { container } = render(
      <BulkActionsBar selectedCount={0} onClear={vi.fn()} actions={[]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('states the selected count in plain words', () => {
    render(<BulkActionsBar selectedCount={3} onClear={vi.fn()} actions={[]} itemNoun="student" />);
    expect(screen.getByText('3 students selected')).toBeInTheDocument();
  });

  it('offers "select all matching" only when the total exceeds the page selection', () => {
    const onSelectAllMatching = vi.fn();
    render(
      <BulkActionsBar
        selectedCount={20}
        totalMatchingCount={4000}
        onSelectAllMatching={onSelectAllMatching}
        onClear={vi.fn()}
        actions={[]}
      />,
    );
    expect(screen.getByText('Select all 4000 matching this filter')).toBeInTheDocument();
  });

  it('does not offer "select all matching" when the page already covers everything', () => {
    render(
      <BulkActionsBar
        selectedCount={5}
        totalMatchingCount={5}
        onSelectAllMatching={vi.fn()}
        onClear={vi.fn()}
        actions={[]}
      />,
    );
    expect(screen.queryByText(/Select all/)).not.toBeInTheDocument();
  });

  it('clicking "select all matching" invokes the handler', async () => {
    const user = userEvent.setup();
    const onSelectAllMatching = vi.fn();
    render(
      <BulkActionsBar
        selectedCount={20}
        totalMatchingCount={4000}
        onSelectAllMatching={onSelectAllMatching}
        onClear={vi.fn()}
        actions={[]}
      />,
    );

    await user.click(screen.getByText('Select all 4000 matching this filter'));
    expect(onSelectAllMatching).toHaveBeenCalledOnce();
  });

  it('makes the "all matching" state explicit and distinct from a page selection', () => {
    render(
      <BulkActionsBar
        selectedCount={20}
        totalMatchingCount={4000}
        selectAllMatching
        onClear={vi.fn()}
        actions={[]}
        itemNoun="student"
      />,
    );
    expect(screen.getByText('All 4,000 students matching the current filter are selected')).toBeInTheDocument();
    expect(screen.getByText(/apply to every matching row/)).toBeInTheDocument();
  });

  it('renders each action and fires its handler', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <BulkActionsBar
        selectedCount={2}
        onClear={vi.fn()}
        actions={[{ id: 'archive', label: 'Archive', onClick }]}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Archive' }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('clears the selection', async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    render(<BulkActionsBar selectedCount={2} onClear={onClear} actions={[]} />);

    await user.click(screen.getByRole('button', { name: 'Clear selection' }));
    expect(onClear).toHaveBeenCalledOnce();
  });

  it('disables an action when told to', () => {
    render(
      <BulkActionsBar
        selectedCount={2}
        onClear={vi.fn()}
        actions={[{ id: 'archive', label: 'Archive', onClick: vi.fn(), disabled: true }]}
      />,
    );
    expect(screen.getByRole('button', { name: 'Archive' })).toBeDisabled();
  });
});
