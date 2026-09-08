/**
 * The animated layer.
 *
 * Motion is the easiest thing in an interface to get wrong in a way nobody
 * notices until it matters, so what is pinned here is not "does it move" but
 * the four things that would make it a defect:
 *
 * - it never puts `NaN`, `undefined` or `Invalid Date` on screen;
 * - it obeys a stated preference for reduced motion;
 * - the accessible name is the *final* value, not the frame the reader caught;
 * - nothing it draws is the only carrier of meaning.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { NumberTicker } from '@/components/ui/motion/number-ticker';
import { ProgressRing } from '@/components/ui/motion/progress-ring';
import { Sparkline } from '@/components/ui/motion/sparkline';
import { StatCard } from '@/components/ui/motion/stat-card';

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

describe('NumberTicker', () => {
  it('lands on the value it was given', async () => {
    render(<NumberTicker value={1234} />);
    expect(await screen.findByText('1,234')).toBeInTheDocument();
  });

  it('is at the value immediately when motion is reduced', () => {
    preferReducedMotion(true);
    render(<NumberTicker value={42} suffix="%" />);
    // No `findBy`: a reduced-motion reader gets the number on first paint,
    // not an animation played quickly.
    expect(screen.getByText('42%')).toBeInTheDocument();
  });

  it('announces the final value rather than a frame of the count', () => {
    preferReducedMotion(true);
    render(<NumberTicker value={87.5} decimals={1} suffix="%" />);
    expect(screen.getByLabelText('87.5%')).toBeInTheDocument();
  });

  it.each([null, undefined, Number.NaN, Infinity, 'not a number', ''])(
    'renders the fallback rather than %p',
    (value) => {
      render(<NumberTicker value={value as number} />);
      expect(screen.getByText('Not available')).toBeInTheDocument();
      expect(screen.queryByText(/NaN|undefined|Infinity/)).not.toBeInTheDocument();
    },
  );

  it('keeps the value as one text node so it can be found on the page', async () => {
    render(<NumberTicker value={90} suffix="%" prefix="~" />);
    // Three sibling nodes would defeat both `getByText` and the browser's own
    // find-on-page, for a string a person can plainly see.
    expect(await screen.findByText('~90%')).toBeInTheDocument();
  });
});

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

describe('ProgressRing', () => {
  it('renders nothing rather than an arc of NaN', () => {
    const { container } = render(<ProgressRing value={null} />);
    expect(container.querySelector('svg')).toBeNull();
  });

  it('clamps a value outside 0–100 instead of overdrawing the circle', () => {
    const { container } = render(<ProgressRing value={140} />);
    const offset = container.querySelectorAll('circle')[1]?.getAttribute('stroke-dashoffset');
    expect(Number(offset)).toBeCloseTo(0, 5);
  });
});

describe('StatCard', () => {
  it('says which direction is good in words, not only in colour', async () => {
    render(<StatCard label="Students at risk" value={6} delta={12} deltaIntent="down-is-good" />);
    // A rise in a risk count is bad news, and the sentence has to say so —
    // colour alone fails WCAG and fails anyone reading a printout.
    expect(await screen.findByText(/worse than last period/i)).toBeInTheDocument();
  });

  it('reads a rise as good when a rise is good', async () => {
    render(<StatCard label="Active students" value={25} delta={8} />);
    expect(await screen.findByText(/better than last period/i)).toBeInTheDocument();
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
});
