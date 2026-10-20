/**
 * Opening a row is for clicks on the row, not on the controls inside it: a
 * select changing a value, a button, a link. Checked once in DataTable rather
 * than trusting every cell to stop its own click.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { DataTable } from '@/components/data-table';

type Row = { id: string; name: string };

describe('DataTable row activation', () => {
  it('opens the row from a plain cell, never from a control inside it', async () => {
    const onRowActivate = vi.fn();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <DataTable<Row>
        caption="People"
        rows={[{ id: 'r1', name: 'Asha' }]}
        getRowId={(row) => row.id}
        isLoading={false}
        error={null}
        onRowActivate={onRowActivate}
        columns={[
          { key: 'name', header: 'Name', render: (row) => row.name },
          {
            key: 'fee',
            header: 'Fee',
            render: () => (
              <select aria-label="Fee status" onChange={onChange} defaultValue="due">
                <option value="due">Due</option>
                <option value="paid">Paid</option>
              </select>
            ),
          },
          { key: 'act', header: 'Act', render: () => <button type="button">Remind</button> },
        ]}
      />,
    );

    await user.selectOptions(screen.getByLabelText('Fee status'), 'paid');
    await user.click(screen.getByRole('button', { name: 'Remind' }));
    expect(onChange).toHaveBeenCalled();
    expect(onRowActivate).not.toHaveBeenCalled();

    await user.click(screen.getByText('Asha'));
    expect(onRowActivate).toHaveBeenCalledWith({ id: 'r1', name: 'Asha' });
  });
});
