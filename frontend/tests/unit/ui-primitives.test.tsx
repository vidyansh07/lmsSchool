import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ListToolbar } from '@/components/list-toolbar';
import { Toolbar } from '@/components/ui/toolbar';

/**
 * The shared toolbar primitives the list screens are built from.
 *
 * `Toolbar`'s properties pinned here are the ones a later edit could quietly
 * lose: that `className` still comes last, so a caller can override the
 * default gap rather than ending up with both.
 *
 * `ListToolbar` is here for a different reason. It hardcoded
 * `id="list-search"`, which is invisible on the nineteen screens that render
 * one toolbar and wrong on any screen that renders two: the ids collide and
 * the second label points at the first input, so clicking it focuses the
 * wrong box. That regression never had a test.
 *
 * The `DescriptionList` block that used to live here went with the component
 * -- it was ported but never adopted, and nothing outside its own test ever
 * imported it.
 */

describe('Toolbar', () => {
  it('renders its children', () => {
    render(
      <Toolbar>
        <button type="button">Export</button>
      </Toolbar>,
    );
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
  });

  it('merges className and lets it come last', () => {
    const { container } = render(<Toolbar className="justify-between">x</Toolbar>);
    const toolbar = container.firstElementChild as HTMLElement;
    expect(toolbar.className).toContain('justify-between');
    expect(toolbar.className.indexOf('justify-between')).toBeGreaterThan(
      toolbar.className.indexOf('flex'),
    );
  });

  it('lets a caller override the default gap rather than carrying both', () => {
    // `ListToolbar` depends on this: it keeps the `gap-3` its nineteen screens
    // already ship. If `cn` ever stops resolving the conflict both classes
    // land and the cascade decides by source order instead of by call order.
    const { container } = render(<Toolbar className="gap-3">x</Toolbar>);
    const className = (container.firstElementChild as HTMLElement).className;
    expect(className).toContain('gap-3');
    expect(className).not.toContain('gap-2');
  });
});

describe('ListToolbar', () => {
  it('gives two toolbars on one page two different input ids', () => {
    render(
      <>
        <ListToolbar search="" onSearchChange={vi.fn()} />
        <ListToolbar search="" onSearchChange={vi.fn()} />
      </>,
    );

    const [first, second] = screen.getAllByLabelText('Search');
    expect(first?.id).toBeTruthy();
    expect(second?.id).toBeTruthy();
    expect(first?.id).not.toBe(second?.id);
  });

  it('points each label at the input beside it, not at the first one', () => {
    render(
      <>
        <ListToolbar search="" onSearchChange={vi.fn()} placeholder="Search students…" />
        <ListToolbar search="" onSearchChange={vi.fn()} placeholder="Search trainers…" />
      </>,
    );

    const [students, trainers] = screen.getAllByLabelText('Search');
    expect(students).toHaveAttribute('placeholder', 'Search students…');
    expect(trainers).toHaveAttribute('placeholder', 'Search trainers…');
  });

  it('still labels its search box and still debounces the callback', async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    render(<ListToolbar search="" onSearchChange={onSearchChange} />);

    const input = screen.getByLabelText('Search');
    await user.type(input, 'asha');
    expect(onSearchChange).not.toHaveBeenCalled();

    await waitFor(() => expect(onSearchChange).toHaveBeenCalledWith('asha'));
    expect(onSearchChange).toHaveBeenCalledTimes(1);
  });

  it('renders the filter slot it is given', () => {
    render(
      <ListToolbar search="" onSearchChange={vi.fn()}>
        <button type="button">Status</button>
      </ListToolbar>,
    );
    expect(screen.getByRole('button', { name: 'Status' })).toBeInTheDocument();
  });
});
