import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ProgressBar } from '@/components/progress-bar';

describe('ProgressBar', () => {
  it('exposes the value to assistive technology', () => {
    render(<ProgressBar percent={40} label="4 of 10 lessons" />);
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '40');
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
    expect(screen.getByText('4 of 10 lessons')).toBeInTheDocument();
  });

  it('clamps values outside 0–100', () => {
    const { rerender } = render(<ProgressBar percent={-20} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');

    rerender(<ProgressBar percent={250} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
  });
});
