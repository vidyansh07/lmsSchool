import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { KpiTile } from '@/components/kpi-tile';

describe('KpiTile', () => {
  it('renders a numeric value', () => {
    render(<KpiTile label="Active students" value={1234} />);
    expect(screen.getByText('Active students')).toBeInTheDocument();
    expect(screen.getByText('1,234')).toBeInTheDocument();
  });

  it('renders a fallback for a null value instead of a blank', () => {
    render(<KpiTile label="Average score" value={null} />);
    expect(screen.getByText('Not available')).toBeInTheDocument();
  });

  it('renders a fallback for undefined', () => {
    render(<KpiTile label="Average score" value={undefined} />);
    expect(screen.getByText('Not available')).toBeInTheDocument();
  });

  it('renders a string value through the default passthrough', () => {
    render(<KpiTile label="Status" value="On track" />);
    expect(screen.getByText('On track')).toBeInTheDocument();
  });

  it('shows an upward trend with an accessible sentence, not colour alone', () => {
    render(
      <KpiTile
        label="Attendance"
        value={92}
        trend={{ delta: 4, comparedTo: 'vs last week' }}
      />,
    );
    expect(screen.getByText('Up 4 vs last week', { exact: false })).toBeInTheDocument();
  });

  it('marks a positive delta as bad news when positiveIsGood is false', () => {
    render(
      <KpiTile
        label="Dropouts"
        value={12}
        trend={{ delta: 3, comparedTo: 'vs last month', positiveIsGood: false }}
      />,
    );
    const trend = screen.getByText('Up 3 vs last month', { exact: false });
    expect(trend.closest('p')).toHaveClass('text-destructive');
  });

  it('describes no change without implying a direction', () => {
    render(<KpiTile label="Enrolments" value={50} trend={{ delta: 0, comparedTo: 'vs yesterday' }} />);
    expect(screen.getByText('No change 0 vs yesterday', { exact: false })).toBeInTheDocument();
  });

  it('renders a sparkline when given a series', () => {
    const { container } = render(<KpiTile label="Trend" value={5} sparkline={[1, 2, 3]} />);
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('omits the sparkline when no series is given', () => {
    const { container } = render(<KpiTile label="Trend" value={5} />);
    expect(container.querySelector('svg')).not.toBeInTheDocument();
  });
});
