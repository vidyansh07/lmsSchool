/**
 * The Reports screen.
 *
 * The property worth pinning: **the tiles are the server's figures, shown as
 * they arrive**. Nothing on this screen adds anything up. A report whose
 * header totals more than its rows is the failure that matters here, and the
 * only way to avoid it is to never compute either half in the browser.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ReportsScreen } from '@/app/reports/page';
import { ApiError } from '@/lib/api';

const getAdmissionReport = vi.hoisted(() => vi.fn());
vi.mock('@/lib/admission-reports', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/admission-reports')>('@/lib/admission-reports');
  return { ...actual, getAdmissionReport };
});

const listAcademicYears = vi.hoisted(() => vi.fn());
vi.mock('@/lib/academic-years', () => ({ listAcademicYears }));

const listCourses = vi.hoisted(() => vi.fn());
vi.mock('@/lib/courses', () => ({ listCourses }));

const OVERALL = {
  tiles: {
    admissions: 34,
    total: '910000.00',
    received: '225400.00',
    cleared: '225400.00',
    uncleared: '0.00',
    balance: '660600.00',
    refund: '0.00',
    cancelled: '24000.00',
  },
  rows: [
    {
      id: 'a1',
      admission_date: '2026-10-01',
      student_name: 'Chintu Yadav',
      courses: 'Advance Python (2026), Data Science (2026)',
      total: '34000.00',
      paid: '1000.00',
      uncleared: '0.00',
      refund: '0.00',
      balance: '33000.00',
    },
  ],
};

describe('ReportsScreen', () => {
  beforeEach(() => {
    getAdmissionReport.mockReset().mockResolvedValue(OVERALL);
    listAcademicYears.mockReset().mockResolvedValue([
      { id: 'y1', name: '2026', starts_on: null, ends_on: null, is_current: true, is_closed: false },
    ]);
    listCourses.mockReset().mockResolvedValue({
      count: 1,
      results: [
        {
          id: 'c1',
          code: 'DA',
          slug: 'da',
          title: 'Data Analytics',
          short_description: '',
          category_name: 'Data',
          category_slug: 'data',
          difficulty: 'beginner',
          default_fee: '30000.00',
          estimated_duration_minutes: null,
          status: 'published',
          visibility: 'public',
          thumbnail_url: null,
          module_count: 0,
          lesson_count: 0,
          published_at: null,
          created_at: '2026-01-01',
        },
      ],
    });
  });

  it('shows the five tabs the desk knows', async () => {
    render(<ReportsScreen />);
    const tabs = screen.getByRole('navigation', { name: 'Reports' });
    for (const label of [
      'Overall admissions',
      'Discount',
      'Admission Expiry',
      'Additional Fees',
      'Coursewise Admission',
    ]) {
      expect(within(tabs).getByRole('button', { name: label })).toBeInTheDocument();
    }
    expect(within(tabs).getByRole('button', { name: 'Overall admissions' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('shows the eight figures of the overall tab, exactly as they arrived', async () => {
    render(<ReportsScreen />);

    expect(await screen.findByText('34')).toBeInTheDocument();
    expect(screen.getByText('Rs. 9,10,000')).toBeInTheDocument();
    expect(screen.getByText('Rs. 6,60,600')).toBeInTheDocument();
    expect(screen.getByText('Rs. 24,000')).toBeInTheDocument();
    // Scoped to the tiles: "Total", "Balance" and "Uncleared" are also
    // column headings below, and an unscoped query cannot tell them apart.
    const tiles = within(screen.getByRole('list', { name: 'Report totals' }));
    for (const label of ['Admissions', 'Total', 'Received', 'Cleared', 'Uncleared', 'Balance', 'Refund', 'Cancelled']) {
      expect(tiles.getByText(label)).toBeInTheDocument();
    }
  });

  it('lists the rows under the right headings', async () => {
    render(<ReportsScreen />);

    expect(await screen.findByText('Chintu Yadav')).toBeInTheDocument();
    expect(
      screen.getByText('Advance Python (2026), Data Science (2026)'),
    ).toBeInTheDocument();
    const table = screen.getByRole('table');
    for (const header of ['Admission Date', 'Name', 'Courses', 'Total', 'Paid', 'Uncleared', 'Refund', 'Balance']) {
      expect(within(table).getByText(header)).toBeInTheDocument();
    }
  });

  it('asks the server again, with the tab, when a tab is chosen', async () => {
    getAdmissionReport.mockResolvedValue({
      tiles: { courses: 2, admissions: 3, total: '50000.00' },
      rows: [{ course_id: 'c1', course: 'Data Analytics', admissions: 3, total: '50000.00', received: '0.00', balance: '50000.00' }],
    });
    render(<ReportsScreen />);
    await screen.findByRole('button', { name: 'Coursewise Admission' });

    fireEvent.click(screen.getByRole('button', { name: 'Coursewise Admission' }));

    await waitFor(() =>
      expect(getAdmissionReport).toHaveBeenCalledWith('coursewise', expect.anything()),
    );
    expect(
      await within(screen.getByRole('list', { name: 'Report totals' })).findByText('Courses'),
    ).toBeInTheDocument();
  });

  it('sends a filter rather than narrowing the rows itself', async () => {
    render(<ReportsScreen />);
    await screen.findByText('Chintu Yadav');

    fireEvent.change(screen.getByLabelText('Start Date'), { target: { value: '2026-10-01' } });

    await waitFor(() =>
      expect(getAdmissionReport).toHaveBeenLastCalledWith(
        'overall',
        expect.objectContaining({ start_date: '2026-10-01' }),
      ),
    );
  });

  it('clears every filter at once', async () => {
    render(<ReportsScreen />);
    await screen.findByText('Chintu Yadav');
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'cancelled' } });
    await waitFor(() =>
      expect(getAdmissionReport).toHaveBeenLastCalledWith(
        'overall',
        expect.objectContaining({ status: 'cancelled' }),
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    await waitFor(() => expect(getAdmissionReport).toHaveBeenLastCalledWith('overall', {}));
  });

  it('says so plainly when a range holds nothing', async () => {
    getAdmissionReport.mockResolvedValue({ tiles: OVERALL.tiles, rows: [] });
    render(<ReportsScreen />);

    expect(await screen.findByText('Nothing in this range')).toBeInTheDocument();
  });

  it('offers a retry when the report fails', async () => {
    getAdmissionReport.mockRejectedValue(new ApiError(500, 'server_error', 'Down.', 'req-1'));
    render(<ReportsScreen />);

    expect(await screen.findByText('Down.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(getAdmissionReport).toHaveBeenCalledTimes(2));
  });

  it('leaves Standard and Subject out — nothing here maps to them', async () => {
    render(<ReportsScreen />);
    await screen.findByText('Chintu Yadav');

    expect(screen.queryByLabelText('Standard')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Subject')).not.toBeInTheDocument();
  });
});
