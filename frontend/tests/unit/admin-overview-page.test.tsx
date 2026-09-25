/**
 * The admin overview (`app/admin/overview/page.tsx`) — Phase R2's one
 * application screen. The KPI tiles and metrics list predate this phase and
 * are not re-verified here; the coverage below is specifically that the
 * attendance-by-week trend, still fetched from the same
 * `attendanceTrend()` call it always was, now renders through `AreaChart`
 * with that real data rather than the plain table the page used to render.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import OverviewPage from '@/app/admin/overview/page';
import { ApiError } from '@/lib/api';
import type { AdminDashboard, TrendPoint } from '@/types/api';

const adminDashboard = vi.hoisted(() => vi.fn());
const attendanceTrend = vi.hoisted(() => vi.fn());
// The three chart cards under the attendance card. Empty by default so every
// existing case sees their empty states and nothing else changes.
const deliveryTrend = vi.hoisted(() => vi.fn());
const enrolmentTrend = vi.hoisted(() => vi.fn());
const batchSummaries = vi.hoisted(() => vi.fn());
const useApi = vi.hoisted(() => vi.fn());

vi.mock('@/lib/reporting', () => ({
  adminDashboard,
  attendanceTrend,
  deliveryTrend,
  enrolmentTrend,
  batchSummaries,
}));
vi.mock('@/hooks/use-api', () => ({ useApi }));
vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({
    user: { id: 'u1', role: 'admin', capabilities: [], full_name: 'Priya Sharma', email: 'priya@example.com' },
    isLoading: false,
    can: () => true,
  }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/admin/overview',
}));

function dashboard(overrides: Partial<AdminDashboard> = {}): AdminDashboard {
  return {
    active_students: 120,
    active_trainers: 8,
    published_courses: 14,
    active_batches: 6,
    awaiting_completion_approval: 2,
    certificates_issued: 45,
    metrics: [],
    ...overrides,
  };
}

/** Real, non-mocked shape: exactly what `attendanceTrend()` (via
 *  `GET /api/v1/reports/metrics/attendance-trend/`) returns. */
const realTrend: TrendPoint[] = [
  { week: '2026-W01', counted: 40, attended: 32, percent: 80 },
  { week: '2026-W02', counted: 44, attended: 33, percent: 75 },
  { week: '2026-W03', counted: 38, attended: 34, percent: 89.5 },
];

/** The sr-only text-alternative table the AreaChart wrapper renders —
 *  scoped here because the trend's week labels also appear as SVG axis
 *  ticks, and because the attendance card's own DonutChart (design-pivot
 *  addition, R13) renders a second sr-only table alongside it. Found by its
 *  own "Week" column header, which the donut's Category/Value table does
 *  not have. */
function dataTable(): HTMLElement {
  const tables = screen.getAllByRole('table', { hidden: true });
  const table = tables.find((candidate) => within(candidate).queryByText('Week'));
  if (!table) throw new Error('Could not find the attendance trend data table');
  return table;
}

beforeEach(() => {
  deliveryTrend.mockResolvedValue([]);
  enrolmentTrend.mockResolvedValue([]);
  batchSummaries.mockResolvedValue([]);
  useApi.mockReturnValue({ data: [], error: null, isLoading: false, reload: vi.fn() });
  // Deterministic chart render — see `tests/unit/charts.test.tsx` for why:
  // Recharts reveals a chart's shapes progressively across animation frames,
  // and jsdom has no real frame clock to advance past that first frame.
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: true,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList,
  );
});

describe('OverviewPage — attendance trend', () => {
  it('renders the real attendance-trend data through AreaChart, not the old plain table', async () => {
    adminDashboard.mockResolvedValue(dashboard());
    attendanceTrend.mockResolvedValue(realTrend);

    render(<OverviewPage />);

    await screen.findByText('Attendance by week');

    // The fetch is unchanged — same function, same call shape.
    expect(attendanceTrend).toHaveBeenCalledWith({ weeks: 12 });

    // It renders as a real chart now: a Recharts area plot, not a <table>
    // of the trend rows sitting directly in the card. The chart mounts one
    // React commit after the heading above (its own `ResizeObserver` effect
    // resolves the plot's size asynchronously), so this waits rather than
    // asserting the instant the heading appears.
    await waitFor(() => expect(screen.getByTestId('attendance-trend-card').querySelector('.recharts-area')).toBeInTheDocument());

    // Every real fetched value still exists as text — the chart's own
    // visually-hidden data table, not a mock/placeholder series.
    const table = within(dataTable());
    expect(table.getByText('2026-W01')).toBeInTheDocument();
    expect(table.getByText('80%')).toBeInTheDocument();
    expect(table.getByText('75%')).toBeInTheDocument();
    expect(table.getByText('90%')).toBeInTheDocument();
  });

  it('shows the chart empty state, not a blank frame, when no registers have been taken', async () => {
    adminDashboard.mockResolvedValue(dashboard());
    attendanceTrend.mockResolvedValue([]);

    render(<OverviewPage />);

    await screen.findByText('Attendance by week');
    expect(screen.getByText('No registers taken yet.')).toBeInTheDocument();
    expect(screen.getByTestId('attendance-trend-card').querySelector('.recharts-area')).not.toBeInTheDocument();
  });

  it('lets an admin switch to the exact counted/attended figures the chart does not plot', async () => {
    adminDashboard.mockResolvedValue(dashboard());
    attendanceTrend.mockResolvedValue(realTrend);

    render(<OverviewPage />);

    await screen.findByText('Attendance by week');
    await waitFor(() => expect(screen.getByTestId('attendance-trend-card').querySelector('.recharts-area')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Show exact figures' }));

    // The chart is gone, replaced by the real table with the counted/attended
    // columns the chart itself never plots.
    expect(screen.getByTestId('attendance-trend-card').querySelector('.recharts-area')).not.toBeInTheDocument();
    // The donut's own sr-only data table (design-pivot addition, R13) also
    // matches `getByRole('table')`, so the real visible table is found by
    // its own "Counted" column header instead of assuming there is only one.
    const visibleTable = screen.getAllByRole('table').find((candidate) => within(candidate).queryByText('Counted'));
    if (!visibleTable) throw new Error('Could not find the visible attendance figures table');
    const table = within(visibleTable);
    expect(table.getByText('40')).toBeInTheDocument(); // counted, week 1
    expect(table.getByText('32')).toBeInTheDocument(); // attended, week 1

    fireEvent.click(screen.getByRole('button', { name: 'Show chart' }));
    await waitFor(() => expect(screen.getByTestId('attendance-trend-card').querySelector('.recharts-area')).toBeInTheDocument());
  });

  it('still shows the page-level error state when the fetch itself fails — untouched by this phase', async () => {
    adminDashboard.mockRejectedValue(new ApiError(500, 'server_error', 'Overview is down.', 'req-1'));
    attendanceTrend.mockResolvedValue(realTrend);

    render(<OverviewPage />);

    expect(await screen.findByText('Overview is down.')).toBeInTheDocument();
    expect(screen.queryByText('Attendance by week')).not.toBeInTheDocument();
  });

  it('keeps the KPI tiles and metrics on screen when only the attendance trend fails — a local error, not a page-level one', async () => {
    adminDashboard.mockResolvedValue(dashboard({ active_students: 120 }));
    attendanceTrend.mockRejectedValue(
      new ApiError(503, 'server_error', 'The trend is temporarily unavailable.', 'req-2'),
    );

    render(<OverviewPage />);

    // The dashboard's own figures loaded fine and stay on screen.
    await screen.findByText('Overview');
    expect(await screen.findAllByTestId('headline-figure')).toHaveLength(6);
    expect(screen.getByText('120')).toBeInTheDocument();

    // Only the attendance card reports the failure — the rest of the page
    // is not replaced by a full-page error.
    expect(await screen.findByText('The trend is temporarily unavailable.')).toBeInTheDocument();
    expect(screen.getByText('Attendance by week')).toBeInTheDocument();
    expect(screen.queryByText('Overview is down.')).not.toBeInTheDocument();

    // Retrying only re-fetches the trend, not the whole dashboard. Earlier
    // tests in this file share the same hoisted mocks with no reset between
    // them, so this asserts the *increase* in call counts rather than an
    // absolute number.
    const trendCallsBeforeRetry = attendanceTrend.mock.calls.length;
    const dashboardCallsBeforeRetry = adminDashboard.mock.calls.length;
    attendanceTrend.mockResolvedValueOnce(realTrend);
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() =>
      expect(attendanceTrend.mock.calls.length).toBe(trendCallsBeforeRetry + 1),
    );
    expect(adminDashboard.mock.calls.length).toBe(dashboardCallsBeforeRetry);
  });
});

/** The design-pivot additions (R13): a time-of-day greeting, a real
 *  `attendance_rate`-backed gauge, and a real attended/not-attended donut —
 *  all derived from data this page already fetches, no new endpoint. */
describe('OverviewPage — design pivot additions', () => {
  it('greets the signed-in viewer by name, derived from the mocked useAuth() user', async () => {
    adminDashboard.mockResolvedValue(dashboard());
    attendanceTrend.mockResolvedValue(realTrend);

    render(<OverviewPage />);

    await screen.findByText('Overview');
    expect(screen.getByText(/Priya Sharma/)).toBeInTheDocument();
  });

  it('renders a RadialProgress gauge for the real attendance_rate metric, against the 75% target this page already uses', async () => {
    adminDashboard.mockResolvedValue(
      dashboard({
        metrics: [
          {
            key: 'attendance_rate',
            label: 'Attendance rate',
            definition: 'Attended sessions over sessions counted.',
            unit: 'percent',
            value: 62,
            numerator: 234,
            denominator: 300,
          },
        ],
      }),
    );
    attendanceTrend.mockResolvedValue(realTrend);

    render(<OverviewPage />);

    await screen.findByText('Attendance by week');
    const gauge = await screen.findByTestId('attendance-rate-gauge');
    expect(within(gauge).getByText('62%')).toBeInTheDocument();
    expect(within(gauge).getByText(/of 75% target/)).toBeInTheDocument();
    expect(within(gauge).getAllByText(/234 of 300/).length).toBeGreaterThan(0);
  });

  it('does not render the gauge when the dashboard has no attendance_rate metric — a real data gap, not a fabricated 0', async () => {
    adminDashboard.mockResolvedValue(dashboard({ metrics: [] }));
    attendanceTrend.mockResolvedValue(realTrend);

    render(<OverviewPage />);

    await screen.findByText('Attendance by week');
    expect(screen.queryByTestId('attendance-rate-gauge')).not.toBeInTheDocument();
  });

  it('adds three chart cards below the attendance card, each stating what it plots', async () => {
    adminDashboard.mockResolvedValue(dashboard);
    attendanceTrend.mockResolvedValue(realTrend);
    deliveryTrend.mockResolvedValue([
      { week: '2026-W01', scheduled: 12, held: 10, cancelled: 1, registers_outstanding: 2 },
      { week: '2026-W02', scheduled: 11, held: 11, cancelled: 0, registers_outstanding: 0 },
    ]);
    enrolmentTrend.mockResolvedValue([
      { week: '2026-W01', started: 30, active: 28, completed: 2, cancelled: 0 },
      { week: '2026-W02', started: 18, active: 18, completed: 0, cancelled: 0 },
    ]);
    batchSummaries.mockResolvedValue([
      { id: 'b1', code: 'B-1', name: 'One', course_title: 'Linux', status: 'active', students: 9, attendance_percent: 91 },
      { id: 'b2', code: 'B-2', name: 'Two', course_title: 'Linux', status: 'active', students: 7, attendance_percent: 62 },
    ]);
    render(<OverviewPage />);

    const combo = await screen.findByTestId('delivery-combo-card');
    const enrol = screen.getByTestId('enrolment-trend-card');
    const byBatch = screen.getByTestId('attendance-by-batch-card');
    for (const card of [combo, enrol, byBatch]) {
      expect(within(card).getByTestId('chart-definition')).not.toHaveTextContent('');
    }

    // Each draws -- scoped to its own card, so a chart added elsewhere on
    // this page cannot break these.
    await waitFor(() => expect(combo.querySelector('.recharts-line')).toBeInTheDocument());
    await waitFor(() => expect(enrol.querySelector('.recharts-area')).toBeInTheDocument());
    await waitFor(() =>
      expect(byBatch.querySelectorAll('.recharts-bar-rectangle')).toHaveLength(2),
    );

    // And the attendance card's own chart is untouched by their presence.
    expect(
      screen.getByTestId('attendance-trend-card').querySelector('.recharts-area'),
    ).toBeInTheDocument();
  });

  it('renders a DonutChart of attended vs. not-attended sessions, summed from the already-fetched trend weeks', async () => {
    adminDashboard.mockResolvedValue(dashboard());
    attendanceTrend.mockResolvedValue(realTrend);

    render(<OverviewPage />);

    await screen.findByText('Attendance by week');
    await waitFor(() => expect(screen.getByTestId('attendance-trend-card').querySelector('.recharts-pie')).toBeInTheDocument());

    // attended: 32 + 33 + 34 = 99; counted: 40 + 44 + 38 = 122; not attended: 23
    const tables = screen.getAllByRole('table', { hidden: true });
    const donutTable = tables.find((table) => within(table).queryByText('Attended'));
    expect(donutTable).toBeTruthy();
    const scoped = within(donutTable as HTMLElement);
    expect(scoped.getByText('99')).toBeInTheDocument();
    expect(scoped.getByText('Not attended')).toBeInTheDocument();
    expect(scoped.getByText('23')).toBeInTheDocument();
  });
});
