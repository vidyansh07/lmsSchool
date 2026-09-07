import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Separator } from '@/components/ui/separator';

describe('Separator', () => {
  it('is hidden from assistive technology by default', () => {
    render(<Separator data-testid="rule" />);
    const rule = screen.getByTestId('rule');
    expect(rule).toHaveAttribute('aria-hidden', 'true');
    expect(rule).not.toHaveAttribute('role');
  });

  it('renders horizontal orientation classes by default', () => {
    render(<Separator data-testid="rule" />);
    expect(screen.getByTestId('rule')).toHaveClass('w-full', 'h-px');
  });

  it('renders vertical orientation classes when asked', () => {
    render(<Separator orientation="vertical" data-testid="rule" />);
    expect(screen.getByTestId('rule')).toHaveClass('h-full', 'w-px');
  });

  it('exposes role="separator" and its orientation when not decorative', () => {
    render(<Separator decorative={false} orientation="vertical" />);
    const rule = screen.getByRole('separator');
    expect(rule).toHaveAttribute('aria-orientation', 'vertical');
    expect(rule).not.toHaveAttribute('aria-hidden');
  });
});
