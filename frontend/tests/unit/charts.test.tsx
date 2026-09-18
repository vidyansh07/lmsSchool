/**
 * The wrappers in `components/ui/charts/`: rendering with real data, the
 * empty state when there is none, and — per this session's own dataviz
 * guidance — that every plotted value also exists as ordinary text, since a
 * chart must never be the only way to read a number. `AreaChart` shares
 * nearly all of `LineChart`'s implementation, so its own assertions here
 * focus on what actually differs (the fill) rather than repeating every
 * case.
 *
 * Every test renders under `prefers-reduced-motion: reduce`
 * (`preferReducedMotion`, the same helper `motion-primitives.test.tsx`
 * already uses for `NumberTicker`/`StatCard`). It is not only a convenience:
 * Recharts' own entrance animation reveals a `Pie`'s sectors progressively
 * across animation frames, and jsdom has no real frame clock to advance, so
 * an animated render here would assert on a mid-animation DOM a real browser
 * shows for a few hundred milliseconds, not the chart's resting state. This
 * incidentally exercises the reduced-motion branch of every wrapper's own
 * `isAnimationActive` prop as a side effect, but determinism is the reason.
 */
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AreaChart } from '@/components/ui/charts/area-chart';
import { BarChart } from '@/components/ui/charts/bar-chart';
import { DonutChart } from '@/components/ui/charts/donut-chart';
import { LineChart } from '@/components/ui/charts/line-chart';

function preferReducedMotion(reduce: boolean) {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: reduce,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList,
  );
}

beforeEach(() => {
  preferReducedMotion(true);
});

/** The visually-hidden text-alternative table every wrapper renders
 *  alongside its plot (`ChartDataTable`) — scoped queries here, rather than
 *  `screen.getByText`, because a category/date also appears as an axis tick
 *  label in the SVG itself and would otherwise collide. */
function dataTable(): HTMLElement {
  return screen.getByRole('table', { hidden: true });
}

const trend = [
  { date: 'Week 1', value: 82 },
  { date: 'Week 2', value: 91 },
  { date: 'Week 3', value: 76 },
];

describe('LineChart', () => {
  it('renders a line for each series with real data', () => {
    const { container } = render(<LineChart data={trend} ariaLabel="Attendance rate by week" />);
    expect(container.querySelectorAll('.recharts-line')).toHaveLength(1);
  });

  it('renders the empty state, not a blank axis frame, with no data', () => {
    const { container } = render(<LineChart data={[]} emptyMessage="No data yet" />);
    expect(screen.getByText('No data yet')).toBeInTheDocument();
    expect(container.querySelector('svg.recharts-surface')).not.toBeInTheDocument();
  });

  it('shows the loading skeleton instead of the plot while data is loading', () => {
    render(<LineChart data={[]} loading />);
    expect(screen.getByRole('status')).toHaveTextContent(/loading chart/i);
  });

  it('every plotted value also exists as plain text (the text alternative table)', () => {
    render(<LineChart data={trend} valueFormatter={(value) => `${value}%`} ariaLabel="Attendance" />);
    const table = within(dataTable());
    expect(table.getByText('82%')).toBeInTheDocument();
    expect(table.getByText('91%')).toBeInTheDocument();
    expect(table.getByText('76%')).toBeInTheDocument();
    expect(table.getByText('Week 1')).toBeInTheDocument();
  });

  it('shows a legend once there is more than one series, and none for a single one', () => {
    const { container, rerender } = render(<LineChart data={trend} />);
    expect(container.querySelector('.recharts-legend-wrapper')).not.toBeInTheDocument();

    rerender(
      <LineChart
        data={[
          { date: 'Week 1', enrolled: 10, attended: 8 },
          { date: 'Week 2', enrolled: 12, attended: 9 },
        ]}
        series={[
          { key: 'enrolled', label: 'Enrolled' },
          { key: 'attended', label: 'Attended' },
        ]}
      />,
    );
    expect(screen.getAllByText('Enrolled').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Attended').length).toBeGreaterThan(0);
  });
});

describe('AreaChart', () => {
  it('renders a filled area with real data', () => {
    const { container } = render(<AreaChart data={trend} ariaLabel="Attendance rate by week" />);
    expect(container.querySelectorAll('.recharts-area')).toHaveLength(1);
  });

  it('renders the empty state with no data', () => {
    render(<AreaChart data={[]} emptyMessage="No registers taken yet." />);
    expect(screen.getByText('No registers taken yet.')).toBeInTheDocument();
  });

  it('every plotted value also exists as plain text', () => {
    render(<AreaChart data={trend} valueFormatter={(value) => `${value}%`} />);
    const table = within(dataTable());
    expect(table.getByText('82%')).toBeInTheDocument();
    expect(table.getByText('91%')).toBeInTheDocument();
    expect(table.getByText('76%')).toBeInTheDocument();
  });
});

describe('BarChart', () => {
  const categories = [
    { label: 'Linux Essentials', value: 42 },
    { label: 'Python Basics', value: 28 },
  ];

  it('renders one bar per category with real data', () => {
    const { container } = render(<BarChart data={categories} />);
    expect(container.querySelectorAll('.recharts-bar-rectangle')).toHaveLength(2);
  });

  it('renders the empty state with no data', () => {
    render(<BarChart data={[]} emptyMessage="No enrolments yet" />);
    expect(screen.getByText('No enrolments yet')).toBeInTheDocument();
  });

  it('every plotted value also exists as plain text', () => {
    render(<BarChart data={categories} />);
    const table = within(dataTable());
    expect(table.getByText('42')).toBeInTheDocument();
    expect(table.getByText('28')).toBeInTheDocument();
    expect(table.getByText('Linux Essentials')).toBeInTheDocument();
  });
});

describe('DonutChart', () => {
  const composition = [
    { label: 'Active', value: 60 },
    { label: 'Completed', value: 30 },
    { label: 'Dropped', value: 10 },
  ];

  it('renders one slice per category with real data', () => {
    const { container } = render(<DonutChart data={composition} />);
    expect(container.querySelectorAll('.recharts-pie-sector')).toHaveLength(3);
  });

  it('renders the empty state with no data', () => {
    render(<DonutChart data={[]} emptyMessage="No students yet" />);
    expect(screen.getByText('No students yet')).toBeInTheDocument();
  });

  it('renders the empty state when every value is zero', () => {
    render(<DonutChart data={[{ label: 'Active', value: 0 }]} emptyMessage="No students yet" />);
    expect(screen.getByText('No students yet')).toBeInTheDocument();
  });

  it('warns in development past the category threshold instead of dropping data or throwing', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const many = Array.from({ length: 7 }, (_, i) => ({ label: `Category ${i + 1}`, value: 10 }));

    render(<DonutChart data={many} />);

    expect(warn).toHaveBeenCalledTimes(1);
    // A soft warning, not a hard check: every category still rendered.
    const table = within(dataTable());
    expect(table.getAllByRole('row')).toHaveLength(many.length + 1); // + header row
  });

  it('shows the total in the centre and every category as plain text', () => {
    render(<DonutChart data={composition} centerLabel="Students" />);
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.getByText('Students')).toBeInTheDocument();
    const table = within(dataTable());
    expect(table.getByText('Active')).toBeInTheDocument();
    expect(table.getByText('Completed')).toBeInTheDocument();
    expect(table.getByText('Dropped')).toBeInTheDocument();
  });
});
