import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { Tooltip } from '@/components/ui/tooltip';

function Basic() {
  return (
    <Tooltip content="Publish this course">
      <button>Publish</button>
    </Tooltip>
  );
}

describe('Tooltip', () => {
  it('is not shown initially', () => {
    render(<Basic />);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('shows immediately on keyboard focus', async () => {
    const user = userEvent.setup();
    render(<Basic />);

    await user.tab();
    expect(screen.getByRole('button')).toHaveFocus();
    expect(screen.getByRole('tooltip')).toHaveTextContent('Publish this course');
  });

  it('hides on blur', async () => {
    const user = userEvent.setup();
    render(
      <div>
        <Basic />
        <button>Elsewhere</button>
      </div>,
    );

    await user.tab();
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    await user.tab();
    await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument());
  });

  it('does not show the instant the pointer enters — only after the hover-intent delay', async () => {
    const user = userEvent.setup();
    render(<Basic />);

    await user.hover(screen.getByRole('button'));
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole('tooltip')).toBeInTheDocument());
  });

  it('hides much faster than the 300ms open-intent delay once the pointer leaves', async () => {
    const user = userEvent.setup();
    render(<Basic />);

    await user.hover(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByRole('tooltip')).toBeInTheDocument());

    await user.unhover(screen.getByRole('button'));
    // Bounded well under the 300ms show delay: if hiding used the same
    // asymmetric timer as showing, this would time out.
    await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument(), { timeout: 250 });
  });

  it('links the trigger to the tooltip with aria-describedby only while shown', async () => {
    const user = userEvent.setup();
    render(<Basic />);
    const trigger = screen.getByRole('button');
    expect(trigger).not.toHaveAttribute('aria-describedby');

    await user.tab();
    const tooltip = screen.getByRole('tooltip');
    expect(trigger).toHaveAttribute('aria-describedby', tooltip.id);
  });

  it('dismisses on Escape', async () => {
    const user = userEvent.setup();
    render(<Basic />);

    await user.tab();
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument());
  });
});
