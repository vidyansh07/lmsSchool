/**
 * The institution's own lists on the settings screen: academic years,
 * payment categories, banks and taxes.
 *
 * What is worth pinning is the behaviour the lists exist for — one current
 * year, at most one default, nothing deleted — and that a failure is said
 * out loud rather than leaving somebody believing a switch took.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AcademicYearsCard } from '@/components/settings/academic-years-card';
import { NamedListCard } from '@/components/settings/named-list-card';
import { ApiError } from '@/lib/api';
import type { AcademicYear } from '@/lib/academic-years';

const createAcademicYear = vi.hoisted(() => vi.fn());
const updateAcademicYear = vi.hoisted(() => vi.fn());
vi.mock('@/lib/academic-years', async () => {
  const actual = await vi.importActual<typeof import('@/lib/academic-years')>(
    '@/lib/academic-years',
  );
  return { ...actual, createAcademicYear, updateAcademicYear };
});

const YEARS: AcademicYear[] = [
  {
    id: 'y-1',
    name: '2025-26',
    starts_on: '2025-04-01',
    ends_on: '2026-03-31',
    is_current: true,
    is_closed: false,
  },
  {
    id: 'y-2',
    name: '2026-27',
    starts_on: null,
    ends_on: null,
    is_current: false,
    is_closed: false,
  },
];

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AcademicYearsCard', () => {
  it('moves the current year rather than offering to switch it off', () => {
    render(<AcademicYearsCard years={YEARS} canManage onChanged={vi.fn()} />);

    // The year that already holds it cannot be un-held: the institute always
    // has one, and the way to move it is to set it on another year.
    expect(screen.getByRole('switch', { name: '2025-26 is the current year' })).toBeDisabled();
    expect(screen.getByRole('switch', { name: '2026-27 is the current year' })).toBeEnabled();
  });

  it('makes another year current', async () => {
    const onChanged = vi.fn();
    updateAcademicYear.mockResolvedValue({ ...YEARS[1]!, is_current: true });
    render(<AcademicYearsCard years={YEARS} canManage onChanged={onChanged} />);

    fireEvent.click(screen.getByRole('switch', { name: '2026-27 is the current year' }));
    await waitFor(() =>
      expect(updateAcademicYear).toHaveBeenCalledWith('y-2', { is_current: true }),
    );
    expect(onChanged).toHaveBeenCalled();
  });

  it('closes a year to new admissions without deleting anything', async () => {
    updateAcademicYear.mockResolvedValue({ ...YEARS[0]!, is_closed: true });
    render(<AcademicYearsCard years={YEARS} canManage onChanged={vi.fn()} />);

    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('switch', { name: '2025-26 takes new admissions' }));
    await waitFor(() =>
      expect(updateAcademicYear).toHaveBeenCalledWith('y-1', { is_closed: true }),
    );
  });

  it('adds a year with its dates', async () => {
    createAcademicYear.mockResolvedValue(YEARS[1]);
    render(<AcademicYearsCard years={YEARS} canManage onChanged={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Year'), { target: { value: '2027-28' } });
    fireEvent.change(screen.getByLabelText('Starts on'), { target: { value: '2027-04-01' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() =>
      expect(createAcademicYear).toHaveBeenCalledWith({
        name: '2027-28',
        starts_on: '2027-04-01',
        ends_on: null,
      }),
    );
  });

  it('says what went wrong instead of leaving the switch looking moved', async () => {
    updateAcademicYear.mockRejectedValue(
      new ApiError(409, 'conflict', 'That year is closed.', 'req-1'),
    );
    render(<AcademicYearsCard years={YEARS} canManage onChanged={vi.fn()} />);

    fireEvent.click(screen.getByRole('switch', { name: '2026-27 is the current year' }));
    expect(await screen.findByText('That year is closed.')).toBeInTheDocument();
  });

  it('offers nothing to change to somebody who may only read it', () => {
    render(<AcademicYearsCard years={YEARS} canManage={false} onChanged={vi.fn()} />);
    expect(screen.getByRole('switch', { name: '2026-27 is the current year' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument();
  });
});

describe('NamedListCard', () => {
  const rows = [
    { id: 'c-1', name: 'Fees', is_default: true, is_active: true },
    { id: 'c-2', name: 'Registration', is_default: false, is_active: true },
  ];

  it('moves the default rather than adding a second one', async () => {
    const onUpdate = vi.fn().mockResolvedValue({});
    render(
      <NamedListCard
        title="Payment Categories"
        description="What a payment is for."
        rows={rows}
        defaultLabel="Default"
        canManage
        onCreate={vi.fn()}
        onUpdate={onUpdate}
        onChanged={vi.fn()}
      />,
    );

    expect(screen.getByRole('switch', { name: 'Fees is the default' })).toBeDisabled();
    fireEvent.click(screen.getByRole('switch', { name: 'Registration is the default' }));
    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith('c-2', { is_default: true }));
  });

  it('retires a row instead of deleting it', async () => {
    const onUpdate = vi.fn().mockResolvedValue({});
    render(
      <NamedListCard
        title="Bank"
        description="Banks a cheque came through."
        rows={[{ id: 'b-1', name: 'HDFC Bank', is_active: true }]}
        defaultLabel={null}
        canManage
        onCreate={vi.fn()}
        onUpdate={onUpdate}
        onChanged={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('switch', { name: 'HDFC Bank is in use' }));
    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith('b-1', { is_active: false }));
  });

  it('refuses to add something with no name', async () => {
    const onCreate = vi.fn();
    render(
      <NamedListCard
        title="Tax"
        description="Named taxes."
        rows={[]}
        canManage
        onCreate={onCreate}
        onUpdate={vi.fn()}
        onChanged={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(await screen.findByText('Give it a name first.')).toBeInTheDocument();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it('adds one and clears the box', async () => {
    const onCreate = vi.fn().mockResolvedValue({});
    render(
      <NamedListCard
        title="Tax"
        description="Named taxes."
        rows={[]}
        canManage
        onCreate={onCreate}
        onUpdate={vi.fn()}
        onChanged={vi.fn()}
      />,
    );

    const box = screen.getByLabelText('Add to tax');
    fireEvent.change(box, { target: { value: 'GST 18%' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(onCreate).toHaveBeenCalledWith({ name: 'GST 18%' }));
    await waitFor(() => expect(box).toHaveValue(''));
  });

  it('says a list is empty rather than showing an empty table', () => {
    const { container } = render(
      <NamedListCard
        title="Bank"
        description="Banks a cheque came through."
        rows={[]}
        canManage={false}
        onCreate={vi.fn()}
        onUpdate={vi.fn()}
        onChanged={vi.fn()}
      />,
    );
    expect(screen.getByText('Nothing on this list yet.')).toBeInTheDocument();
    expect(within(container).queryByRole('table')).not.toBeInTheDocument();
  });
});
