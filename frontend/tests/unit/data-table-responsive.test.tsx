/**
 * A table does not become readable on a phone by shrinking.
 *
 * Both behaviours here come from the same measured failure: on a 390px screen,
 * a roster with a pinned id column and a pinned actions column gave almost its
 * whole width to those two, and the column saying *who the row is about* was
 * crushed to a few pixels. Ids and buttons and no names.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DataTable } from '@/components/data-table';

type Row = { id: string; name: string; city: string };

const ROWS: Row[] = [{ id: 'r1', name: 'Asha Rao', city: 'Jaipur' }];

function renderTable(hideBelow?: 'sm' | 'md' | 'lg') {
  return render(
    <DataTable<Row>
      caption="People"
      rows={ROWS}
      getRowId={(row) => row.id}
      isLoading={false}
      error={null}
      columns={[
        { key: 'name', header: 'Name', sticky: 'start', render: (row) => row.name },
        { key: 'city', header: 'City', hideBelow, render: (row) => row.city },
        { key: 'actions', header: 'Actions', sticky: 'end', render: () => <span>Open</span> },
      ]}
    />,
  );
}

describe('a table on a narrow screen', () => {
  it('pins a sticky column only from sm upwards', () => {
    renderTable();

    const header = screen.getByRole('columnheader', { name: /Name/ });
    // Static on a phone, sticky on a desk: everything stays reachable by
    // scrolling rather than being pinned into a few pixels.
    expect(header.className).toContain('max-sm:static');
    expect(header.className).toContain('sm:sticky');
  });

  it('pins the trailing column the same way', () => {
    renderTable();

    const header = screen.getByRole('columnheader', { name: 'Actions' });
    expect(header.className).toContain('max-sm:static');
    expect(header.className).toContain('sm:right-0');
  });

  it('leaves a column out below its breakpoint', () => {
    renderTable('md');

    const header = screen.getByRole('columnheader', { name: 'City' });
    expect(header.className).toContain('hidden');
    expect(header.className).toContain('md:table-cell');
  });

  it('hides the body cell with its header, not one without the other', () => {
    // A header hidden while its cells stay would shift every column after it.
    renderTable('md');

    const cell = screen.getByText('Jaipur');
    expect(cell.className).toContain('hidden');
    expect(cell.className).toContain('md:table-cell');
  });

  it('keeps a column that did not ask to be hidden', () => {
    renderTable();

    const header = screen.getByRole('columnheader', { name: 'City' });
    expect(header.className).not.toContain('hidden');
  });

  it('still renders the hidden column, so it is there when the screen is wide', () => {
    // Hidden by CSS, not dropped from the DOM: this is about what is worth a
    // phone's width, not about withholding data.
    renderTable('md');

    expect(screen.getByText('Jaipur')).toBeInTheDocument();
  });
});
