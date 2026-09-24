/**
 * The dashboard tile, and the one drawing left inside it.
 *
 * What is pinned here is not "does it look right" but the things that would
 * make it a defect:
 *
 * - it never puts `NaN`, `undefined` or `Invalid Date` on screen;
 * - nothing it draws is the only carrier of meaning — a delta says which way
 *   is good in words, because colour alone fails WCAG and fails anyone
 *   reading a printout;
 * - the figure stays one text node, so find-on-page and a test locate the
 *   number a person can actually see.
 *
 * Replaces `motion-primitives.test.tsx`. The `NumberTicker` and
 * `ProgressRing` blocks went with their components: the counting animation
 * was removed, and `RadialProgress` already covered the ring.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Sparkline } from '@/components/ui/charts/sparkline';
import { StatCard } from '@/components/ui/stat';

describe('Sparkline', () => {
  it('renders nothing for a series too short to be a trend', () => {
    const { container } = render(<Sparkline values={[5]} />);
    expect(container.querySelector('svg')).toBeNull();
  });

  it('ignores nulls rather than drawing a broken path', () => {
    const { container } = render(<Sparkline values={[1, null, 3, undefined, 5]} />);
    const path = container.querySelector('path');
    expect(path?.getAttribute('d')).not.toMatch(/NaN/);
  });

  it('draws a flat series down the middle instead of dividing by zero', () => {
    const { container } = render(<Sparkline values={[7, 7, 7]} />);
    const path = container.querySelector('path');
    expect(path?.getAttribute('d')).not.toMatch(/NaN|Infinity/);
  });

  it('carries a text label, because a line alone says nothing to a screen reader', () => {
    render(<Sparkline values={[1, 2, 3]} label="Attendance trend" />);
    expect(screen.getByRole('img', { name: 'Attendance trend' })).toBeInTheDocument();
  });
});

describe('StatCard', () => {
  it('says which direction is good in words, not only in colour', () => {
    render(<StatCard label="Students at risk" value={6} delta={12} deltaIntent="down-is-good" />);
    // A rise in a risk count is bad news, and the sentence has to say so.
    expect(screen.getByText(/worse than last period/i)).toBeInTheDocument();
  });

  it('reads a rise as good when a rise is good', () => {
    render(<StatCard label="Active students" value={25} delta={8} />);
    expect(screen.getByText(/better than last period/i)).toBeInTheDocument();
  });

  it('shows the fallback for a missing figure without inventing a delta', () => {
    render(<StatCard label="Attendance" value={null} delta={null} />);
    expect(screen.getByText('Not available')).toBeInTheDocument();
    expect(screen.queryByText(/than last period/i)).not.toBeInTheDocument();
  });

  it('is a link only when it has somewhere to go', () => {
    const { rerender } = render(<StatCard label="Batches" value={4} />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();

    rerender(<StatCard label="Batches" value={4} href="/admin/batches" />);
    expect(screen.getByRole('link')).toHaveAttribute('href', '/admin/batches');
  });

  it('shows the period beside the label when given one, and nothing extra when not', () => {
    const { rerender } = render(<StatCard label="Total batches" value={42} period="All-time" />);
    expect(screen.getByText(/All-time/)).toBeInTheDocument();

    rerender(<StatCard label="Total batches" value={42} />);
    expect(screen.queryByText(/All-time/)).not.toBeInTheDocument();
  });

  it('keeps the figure as one text node so it can be found on the page', () => {
    // Three siblings would mean no `getByText('₹1,250')` matches the thing a
    // person plainly sees, in a test or in the browser's own find-on-page.
    render(<StatCard label="Collected" value={1250} prefix="₹" />);
    expect(screen.getByText('₹1,250')).toBeInTheDocument();
  });

  it('renders a figure immediately rather than counting up to it', () => {
    // The old tile animated from zero on mount, so the first frame stated a
    // number that was false. There is nothing to wait for now.
    render(<StatCard label="Messages sent" value={600} />);
    expect(screen.getByText('600')).toBeInTheDocument();
  });

  it('shows the fallback rather than a string that is not a figure', () => {
    // "not a number" rendered in the largest type on the page states
    // something false where a metric belongs.
    render(<StatCard label="Reply rate" value="pending" />);
    expect(screen.queryByText('pending')).not.toBeInTheDocument();
    expect(screen.getByText('Not available')).toBeInTheDocument();
  });
});
