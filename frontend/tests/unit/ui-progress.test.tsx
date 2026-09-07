import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Progress } from '@/components/ui/progress';

describe('Progress', () => {
  it('exposes value, min and max on the progressbar role', () => {
    render(<Progress value={30} max={50} label="Import progress" />);
    const bar = screen.getByRole('progressbar', { name: 'Import progress' });
    expect(bar).toHaveAttribute('aria-valuenow', '30');
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '50');
  });

  it('defaults max to 100', () => {
    render(<Progress value={25} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuemax', '100');
  });

  it('scales the fill with a transform, not a width, so it never forces layout', () => {
    const { container } = render(<Progress value={40} max={100} />);
    const fill = container.querySelector('[style]');
    expect(fill).toHaveStyle({ transform: 'scaleX(0.4)' });
    expect(fill).not.toHaveStyle({ width: '40%' });
  });

  it('omits aria-valuenow and pulses when indeterminate', () => {
    render(<Progress />);
    const bar = screen.getByRole('progressbar');
    expect(bar).not.toHaveAttribute('aria-valuenow');
    expect(bar.firstElementChild).toHaveClass('animate-pulse');
  });

  it('clamps out-of-range values into the fill fraction', () => {
    const { container } = render(<Progress value={999} max={100} />);
    const fill = container.querySelector('[style]');
    expect(fill).toHaveStyle({ transform: 'scaleX(1)' });
  });
});
