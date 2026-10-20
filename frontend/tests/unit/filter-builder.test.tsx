import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  FilterBuilder,
  fromQuery,
  parameterFor,
  toQuery,
  type FilterFieldSpec,
} from '@/components/filter-builder';

/**
 * A list people can ask their own question of.
 *
 * The round trip is what these mostly check: a condition becomes a query
 * parameter, and a URL carrying that parameter comes back as the same
 * condition. If that breaks, a bookmarked view opens looking unfiltered while
 * the list underneath is narrowed — the discrepancy that makes people stop
 * trusting a filter and start exporting to a spreadsheet.
 */
const FIELDS: FilterFieldSpec[] = [
  {
    name: 'city',
    label: 'City',
    kind: 'text',
    operators: [
      { value: 'exact', label: 'is' },
      { value: 'icontains', label: 'contains' },
      { value: 'isnull', label: 'is empty' },
    ],
  },
  {
    name: 'fee_status',
    label: 'Fee status',
    kind: 'choice',
    operators: [{ value: 'exact', label: 'is' }],
    choices: [
      { value: 'paid', label: 'Paid' },
      { value: 'pending', label: 'Pending' },
    ],
  },
];

describe('turning a condition into a query', () => {
  it('keeps the bare field name for "is"', () => {
    // Every saved link in the product spells it this way, and the server
    // reads it the same.
    expect(parameterFor({ field: 'city', operator: 'exact', value: 'Jaipur' })).toBe('city');
  });

  it('suffixes any other operator', () => {
    expect(parameterFor({ field: 'city', operator: 'icontains', value: 'jai' })).toBe(
      'city__icontains',
    );
  });

  it('leaves out a condition with no value', () => {
    // A half-filled row must not narrow the list to nothing.
    expect(toQuery([{ field: 'city', operator: 'icontains', value: '' }])).toEqual({});
  });
});

describe('reading a query back', () => {
  it('recovers a condition from a bookmarked URL', () => {
    expect(fromQuery({ city__icontains: 'jai' }, FIELDS)).toEqual([
      { field: 'city', operator: 'icontains', value: 'jai' },
    ]);
  });

  it('recovers a bare field name as "is"', () => {
    expect(fromQuery({ fee_status: 'paid' }, FIELDS)).toEqual([
      { field: 'fee_status', operator: 'exact', value: 'paid' },
    ]);
  });

  it('ignores a parameter that is not a filter', () => {
    // `page` and `ordering` share the query with filters and are not ones.
    expect(fromQuery({ page: 2, ordering: '-created_at' }, FIELDS)).toEqual([]);
  });

  it('ignores an operator the server did not offer', () => {
    // The bar must not show a chip for something the list is not doing.
    expect(fromQuery({ city__regex: '.*' }, FIELDS)).toEqual([]);
  });

  it('survives a field name that itself contains an underscore', () => {
    expect(fromQuery({ fee_status: 'paid' }, FIELDS)).toHaveLength(1);
  });
});

describe('the bar', () => {
  it('shows nothing when the server offered no fields', () => {
    // A bar with an empty field list would be a control that cannot do
    // anything.
    const { container } = render(
      <FilterBuilder fields={[]} conditions={[]} onChange={() => {}} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('describes an applied condition in words', () => {
    render(
      <FilterBuilder
        fields={FIELDS}
        conditions={[{ field: 'city', operator: 'icontains', value: 'jai' }]}
        onChange={() => {}}
      />,
    );

    expect(screen.getByText('City contains jai')).toBeInTheDocument();
  });

  it('names a choice by its label, not its stored value', () => {
    render(
      <FilterBuilder
        fields={FIELDS}
        conditions={[{ field: 'fee_status', operator: 'exact', value: 'paid' }]}
        onChange={() => {}}
      />,
    );

    expect(screen.getByText('Fee status is Paid')).toBeInTheDocument();
  });

  it('reads "is empty" as a state rather than a value', () => {
    render(
      <FilterBuilder
        fields={FIELDS}
        conditions={[{ field: 'city', operator: 'isnull', value: 'true' }]}
        onChange={() => {}}
      />,
    );

    expect(screen.getByText('City is empty')).toBeInTheDocument();
  });

  it('removes one condition without touching the others', async () => {
    const onChange = vi.fn();
    render(
      <FilterBuilder
        fields={FIELDS}
        conditions={[
          { field: 'city', operator: 'icontains', value: 'jai' },
          { field: 'fee_status', operator: 'exact', value: 'paid' },
        ]}
        onChange={onChange}
      />,
    );

    await userEvent.click(screen.getByLabelText('Remove the filter City contains jai'));

    expect(onChange).toHaveBeenCalledWith([
      { field: 'fee_status', operator: 'exact', value: 'paid' },
    ]);
  });

  it('clears everything at once', async () => {
    const onChange = vi.fn();
    render(
      <FilterBuilder
        fields={FIELDS}
        conditions={[{ field: 'city', operator: 'icontains', value: 'jai' }]}
        onChange={onChange}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Clear all' }));

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('replaces rather than repeats a condition on the same field', async () => {
    // Two conditions on one field would mean "city is Jaipur and city is
    // Pune", which is always empty — and the parameter cannot carry both.
    const onChange = vi.fn();
    render(
      <FilterBuilder
        fields={FIELDS}
        conditions={[{ field: 'city', operator: 'icontains', value: 'jai' }]}
        onChange={onChange}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Add filter' }));
    await userEvent.selectOptions(screen.getByLabelText(/Field/), 'city');
    await userEvent.type(screen.getByLabelText(/Value/), 'Pune');
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));

    expect(onChange).toHaveBeenCalledWith([
      { field: 'city', operator: 'exact', value: 'Pune' },
    ]);
  });

  it('will not apply a condition with no value', async () => {
    const onChange = vi.fn();
    render(<FilterBuilder fields={FIELDS} conditions={[]} onChange={onChange} />);

    await userEvent.click(screen.getByRole('button', { name: 'Filter' }));

    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('offers a choice field its values instead of a free-text box', async () => {
    render(<FilterBuilder fields={FIELDS} conditions={[]} onChange={() => {}} />);

    await userEvent.click(screen.getByRole('button', { name: 'Filter' }));
    await userEvent.selectOptions(screen.getByLabelText(/Field/), 'fee_status');

    expect(screen.getByRole('option', { name: 'Paid' })).toBeInTheDocument();
  });
});
