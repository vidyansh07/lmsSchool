import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DashboardGrid, DashboardGridFullRow } from '@/components/dashboard-grid';

describe('DashboardGrid', () => {
  it('renders its children inside a grid', () => {
    render(
      <DashboardGrid>
        <p>Tile one</p>
        <p>Tile two</p>
      </DashboardGrid>,
    );
    expect(screen.getByText('Tile one')).toBeInTheDocument();
    expect(screen.getByText('Tile two')).toBeInTheDocument();
  });

  it('applies a full-row span class to DashboardGridFullRow', () => {
    render(
      <DashboardGrid>
        <DashboardGridFullRow>
          <p>Wide content</p>
        </DashboardGridFullRow>
      </DashboardGrid>,
    );
    const wide = screen.getByText('Wide content').parentElement;
    expect(wide?.className).toMatch(/col-span-4/);
  });
});
