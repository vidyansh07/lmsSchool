import { render, screen } from '@testing-library/react';
import { Ghost } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import { Empty, EmptyActions, EmptyDescription, EmptyIcon, EmptyTitle } from '@/components/ui/empty';
import { Button } from '@/components/ui/button';

describe('Empty', () => {
  it('renders an icon, title, description and actions', async () => {
    render(
      <Empty>
        <EmptyIcon>
          <Ghost />
        </EmptyIcon>
        <EmptyTitle>No results</EmptyTitle>
        <EmptyDescription>Try a different search.</EmptyDescription>
        <EmptyActions>
          <Button>Clear search</Button>
        </EmptyActions>
      </Empty>,
    );

    expect(screen.getByText('No results')).toBeInTheDocument();
    expect(screen.getByText('Try a different search.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear search' })).toBeInTheDocument();
  });

  it('hides the icon from assistive technology', () => {
    const { container } = render(
      <Empty>
        <EmptyIcon>
          <Ghost />
        </EmptyIcon>
        <EmptyTitle>No results</EmptyTitle>
      </Empty>,
    );
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  });

  it('works with only a title, no description or actions', () => {
    render(
      <Empty>
        <EmptyTitle>Nothing here yet</EmptyTitle>
      </Empty>,
    );
    expect(screen.getByText('Nothing here yet')).toBeInTheDocument();
  });
});
