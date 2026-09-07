import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Spinner } from '@/components/ui/spinner';

describe('Spinner', () => {
  it('announces a default label to assistive technology', () => {
    render(<Spinner />);
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('Loading…');
  });

  it('announces a caller-supplied label instead', () => {
    render(<Spinner label="Saving changes…" />);
    expect(screen.getByRole('status')).toHaveTextContent('Saving changes…');
  });

  it('hides the icon itself from assistive technology', () => {
    const { container } = render(<Spinner />);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('spins with an animation class', () => {
    const { container } = render(<Spinner />);
    expect(container.querySelector('svg')).toHaveClass('animate-spin');
  });

  it('applies the requested size', () => {
    const { container } = render(<Spinner size="lg" />);
    expect(container.querySelector('svg')).toHaveClass('size-6');
  });
});
