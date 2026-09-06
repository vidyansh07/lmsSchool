import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Sparkline } from '@/components/sparkline';

describe('Sparkline', () => {
  it('renders nothing for an empty series', () => {
    const { container } = render(<Sparkline values={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when every value is non-finite', () => {
    const { container } = render(<Sparkline values={[NaN, Infinity]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a single point as a mark, not a line', () => {
    const { container } = render(<Sparkline values={[42]} />);
    expect(container.querySelector('circle')).toBeInTheDocument();
    expect(container.querySelector('polyline')).not.toBeInTheDocument();
  });

  it('renders a polyline for a multi-point series', () => {
    const { container } = render(<Sparkline values={[1, 5, 2, 8, 3]} />);
    const polyline = container.querySelector('polyline');
    expect(polyline).toBeInTheDocument();
    expect(polyline?.getAttribute('points')?.split(' ')).toHaveLength(5);
  });

  it('does not crash on a flat series (zero range)', () => {
    const { container } = render(<Sparkline values={[4, 4, 4]} />);
    expect(container.querySelector('polyline')).toBeInTheDocument();
  });

  it('exposes an accessible label when given one', () => {
    const { getByRole } = render(<Sparkline values={[1, 2, 3]} label="Enrolments this month" />);
    expect(getByRole('img', { name: 'Enrolments this month' })).toBeInTheDocument();
  });

  it('is presentational (no accessible role) without a label', () => {
    const { container } = render(<Sparkline values={[1, 2, 3]} />);
    expect(container.querySelector('svg')).toHaveAttribute('role', 'presentation');
  });
});
