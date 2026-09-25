/**
 * The primitives added for the analytics build: the dual-axis combo, the
 * horizontal bar, the radar, the stage funnel, the panel they sit in, and
 * the two opt-in props bolted onto the charts that already existed.
 *
 * Kept in its own file rather than appended to `charts.test.tsx`, because
 * that file's assertions are the guarantee that none of this changed the
 * six original charts' default output. Mixing the two would make it unclear
 * which half a failure came from.
 *
 * Every test renders under `prefers-reduced-motion: reduce`, for the reason
 * `charts.test.tsx` documents at length: Recharts reveals shapes across
 * animation frames and jsdom has no frame clock, so an animated render
 * asserts on a mid-animation DOM rather than the chart's resting state.
 */
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Activity } from 'lucide-react';

import { AreaChart } from '@/components/ui/charts/area-chart';
import { BarChart } from '@/components/ui/charts/bar-chart';
import { HorizontalBarChart } from '@/components/ui/charts/bar-chart-horizontal';
import { ChartCard } from '@/components/ui/charts/chart-card';
import { ComboChart } from '@/components/ui/charts/combo-chart';
import { RadarChart } from '@/components/ui/charts/radar-chart';
import { StageFunnel } from '@/components/ui/charts/stage-funnel';
import { StatStrip } from '@/components/ui/stat-strip';

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

const TREND = [
  { date: '2026-01-05', held: 12, percent: 82 },
  { date: '2026-01-12', held: 9, percent: 76 },
  { date: '2026-01-19', held: 14, percent: 91 },
];

const CATEGORIES = [
  { label: 'Networking Basics', value: 88 },
  { label: 'Cyber Security', value: 74 },
  { label: 'Digital Marketing', value: 61 },
];

describe('ComboChart', () => {
  it('draws both marks against their own axes', () => {
    const { container } = render(
      <ComboChart
        data={TREND}
        bars={[{ key: 'held', label: 'Classes held' }]}
        lines={[{ key: 'percent', label: 'Attendance rate' }]}
        rightAxisKeys={['percent']}
        leftLabel="Classes"
        rightLabel="Percent"
      />,
    );
    expect(container.querySelectorAll('.recharts-bar-rectangle')).toHaveLength(3);
    expect(container.querySelectorAll('.recharts-line')).toHaveLength(1);
  });

  it('names both axes, so neither scale is a guess', () => {
    render(
      <ComboChart
        data={TREND}
        bars={[{ key: 'held', label: 'Classes held' }]}
        lines={[{ key: 'percent', label: 'Attendance rate' }]}
        rightAxisKeys={['percent']}
        leftLabel="Classes"
        rightLabel="Percent"
      />,
    );
    expect(screen.getByText('Classes')).toBeInTheDocument();
    expect(screen.getByText('Percent')).toBeInTheDocument();
  });

  it('carries each series unit into the hidden table', () => {
    render(
      <ComboChart
        data={TREND}
        bars={[{ key: 'held', label: 'Classes held' }]}
        lines={[{ key: 'percent', label: 'Attendance rate' }]}
        rightAxisKeys={['percent']}
        leftLabel="Classes"
        rightLabel="Percent"
      />,
    );
    const table = within(screen.getByRole('table', { hidden: true }));
    expect(table.getByText('Classes held (Classes)')).toBeInTheDocument();
    expect(table.getByText('Attendance rate (Percent)')).toBeInTheDocument();
  });

  it('shows the legend even for a single pair, because two scales are in play', () => {
    const { container } = render(
      <ComboChart
        data={TREND}
        bars={[{ key: 'held', label: 'Classes held' }]}
        leftLabel="Classes"
        rightLabel="Percent"
      />,
    );
    expect(container.querySelector('.recharts-legend-wrapper')).toBeInTheDocument();
  });

  it('renders nothing plottable as an empty state, not an empty axis frame', () => {
    const { container } = render(
      <ComboChart
        data={[{ date: '2026-01-05', held: null }]}
        bars={[{ key: 'held', label: 'Classes held' }]}
        leftLabel="Classes"
        rightLabel="Percent"
      />,
    );
    expect(container.querySelector('svg.recharts-surface')).toBeNull();
  });
});

describe('HorizontalBarChart', () => {
  it('lays its category axis down the side', () => {
    const { container } = render(<HorizontalBarChart data={CATEGORIES} />);
    expect(container.querySelectorAll('.recharts-bar-rectangle')).toHaveLength(3);
    expect(screen.getByRole('table', { hidden: true })).toBeInTheDocument();
  });

  it('gives each bar its own colour when asked', () => {
    const { container } = render(<HorizontalBarChart data={CATEGORIES} colorPerBar />);
    const fills = new Set(
      Array.from(container.querySelectorAll('.recharts-bar-rectangle path')).map((p) =>
        p.getAttribute('fill'),
      ),
    );
    expect(fills.size).toBe(3);
  });

  it('ignores colorPerBar for more than one series, and says so', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    render(
      <HorizontalBarChart
        data={[{ label: 'A', one: 1, two: 2 }]}
        series={[
          { key: 'one', label: 'One' },
          { key: 'two', label: 'Two' },
        ]}
        colorPerBar
      />,
    );
    expect(warn).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });
});

describe('RadarChart', () => {
  const DIMENSIONS = [
    { label: 'Attendance', value: 88, expected: 75 },
    { label: 'Assessments', value: 64, expected: 70 },
    { label: 'Assignments', value: 92, expected: 80 },
    { label: 'Projects', value: 40, expected: 60 },
  ];

  it('draws one shape per series', () => {
    const { container } = render(
      <RadarChart
        data={DIMENSIONS}
        series={[
          { key: 'value', label: 'Actual' },
          { key: 'expected', label: 'Expected' },
        ]}
      />,
    );
    expect(container.querySelectorAll('.recharts-radar')).toHaveLength(2);
  });

  it('refuses to draw a shape from fewer than three dimensions', () => {
    // Two spokes is a line, not a shape, and the honest rendering of two
    // numbers is two numbers.
    const { container } = render(
      <RadarChart data={[{ label: 'Attendance', value: 88 }, { label: 'Projects', value: 40 }]} />,
    );
    expect(container.querySelector('svg.recharts-surface')).toBeNull();
  });

  it('warns past two overlapping series', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    render(
      <RadarChart
        data={DIMENSIONS}
        series={[
          { key: 'value', label: 'A' },
          { key: 'expected', label: 'B' },
          { key: 'value', label: 'C' },
        ]}
      />,
    );
    expect(warn).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });
});

describe('StageFunnel', () => {
  const STAGES = [
    { key: 'created', label: 'Registered', count: 200 },
    { key: 'enrolled', label: 'Enrolled', count: 150 },
    { key: 'paid', label: 'Paid', count: 90 },
  ];

  it('states each stage conversion against the one above it', () => {
    render(<StageFunnel stages={STAGES} />);
    expect(screen.getByText(/75% of registered/i)).toBeInTheDocument();
    expect(screen.getByText(/60% of enrolled/i)).toBeInTheDocument();
  });

  it('gives the first stage no conversion, having nothing to convert from', () => {
    render(<StageFunnel stages={STAGES} />);
    expect(screen.queryByText(/% of paid/i)).not.toBeInTheDocument();
    // Three stages, two conversions.
    expect(screen.getAllByText(/% of /i)).toHaveLength(2);
  });

  it('shows no rate rather than 0% when the stage above is empty', () => {
    // "0 of 0" is undefined, not zero -- the same rule the backend's
    // `_percent` follows.
    render(
      <StageFunnel
        stages={[
          { key: 'a', label: 'First', count: 0 },
          { key: 'b', label: 'Second', count: 0 },
        ]}
      />,
    );
    expect(screen.queryByText(/% of first/i)).not.toBeInTheDocument();
  });
});

describe('AreaChart gradient fills', () => {
  it('draws no gradient by default, so the existing charts are untouched', () => {
    const { container } = render(<AreaChart data={TREND} series={[{ key: 'held', label: 'Held' }]} />);
    expect(container.querySelectorAll('linearGradient')).toHaveLength(0);
  });

  it('gives two gradient charts on one page different ids', () => {
    // A shared id would make the second chart repaint the first from its own
    // data, which looks like a data bug rather than a rendering one.
    const { container } = render(
      <>
        <AreaChart data={TREND} series={[{ key: 'held', label: 'Held' }]} gradient />
        <AreaChart data={TREND} series={[{ key: 'percent', label: 'Rate' }]} gradient />
      </>,
    );
    const ids = Array.from(container.querySelectorAll('linearGradient')).map((g) => g.id);
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
    expect(ids.every((id) => /^[a-zA-Z][a-zA-Z0-9_-]*$/.test(id))).toBe(true);
  });
});

describe('BarChart colorPerBar', () => {
  it('uses one colour for the series by default', () => {
    const { container } = render(<BarChart data={CATEGORIES} />);
    const fills = new Set(
      Array.from(container.querySelectorAll('.recharts-bar-rectangle path')).map((p) =>
        p.getAttribute('fill'),
      ),
    );
    expect(fills.size).toBe(1);
  });

  it('gives each bar its own palette step when asked', () => {
    const { container } = render(<BarChart data={CATEGORIES} colorPerBar />);
    const fills = new Set(
      Array.from(container.querySelectorAll('.recharts-bar-rectangle path')).map((p) =>
        p.getAttribute('fill'),
      ),
    );
    expect(fills.size).toBe(3);
  });
});

describe('ChartCard', () => {
  it('always renders the definition of what it is plotting', () => {
    render(
      <ChartCard title="Attendance by week" subtitle="Registers taken, as a percentage">
        <div>plot</div>
      </ChartCard>,
    );
    expect(screen.getByTestId('chart-definition')).toHaveTextContent(
      'Registers taken, as a percentage',
    );
  });

  it('exposes a handle a page test can scope its queries to', () => {
    render(
      <ChartCard title="A" subtitle="B" testId="attendance-card">
        <div>plot</div>
      </ChartCard>,
    );
    expect(screen.getByTestId('attendance-card')).toBeInTheDocument();
  });

  it('renders its legend, actions and footer when given them', () => {
    render(
      <ChartCard
        title="A"
        subtitle="B"
        icon={Activity}
        iconTone="success"
        legend={[{ label: 'Held', color: 'var(--color-chart-1)', value: '12' }]}
        actions={<button type="button">Switch</button>}
        footer={<a href="/admin/reports">View the rows</a>}
      >
        <div>plot</div>
      </ChartCard>,
    );
    expect(screen.getByText('Held')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Switch' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View the rows' })).toBeInTheDocument();
  });

  it('takes a heading level, so a section never skips one', () => {
    render(
      <ChartCard title="Nested" subtitle="B" as="h3">
        <div>plot</div>
      </ChartCard>,
    );
    expect(screen.getByRole('heading', { level: 3, name: 'Nested' })).toBeInTheDocument();
  });
});

describe('StatStrip', () => {
  const ITEMS = [
    { label: 'Active students', value: 412 },
    { label: 'Active batches', value: 18 },
    { label: 'Attendance', value: 82, suffix: '%' },
  ];

  it('renders one figure per column', () => {
    render(<StatStrip items={ITEMS} />);
    expect(screen.getAllByTestId('headline-figure')).toHaveLength(3);
    expect(screen.getByText('412')).toBeInTheDocument();
    expect(screen.getByText('82%')).toBeInTheDocument();
  });

  it('shows the fallback for a figure that is not a number', () => {
    render(<StatStrip items={[{ label: 'Attendance', value: null }]} />);
    expect(screen.getByText('Not available')).toBeInTheDocument();
  });

  it('keeps each figure as one text node, so it can be found on the page', () => {
    render(<StatStrip items={[{ label: 'Collected', value: 1250, prefix: '₹' }]} />);
    expect(screen.getByText('₹1,250')).toBeInTheDocument();
  });

  it('links a column only when it has somewhere to go', () => {
    const { rerender } = render(<StatStrip items={ITEMS} />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();

    rerender(<StatStrip items={[{ label: 'Active students', value: 412, href: '/admin/students' }]} />);
    expect(screen.getByRole('link')).toHaveAttribute('href', '/admin/students');
  });

  it('renders nothing at all for no items', () => {
    const { container } = render(<StatStrip items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
