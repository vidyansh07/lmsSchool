import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ListToolbar } from '@/components/list-toolbar';
import { DescriptionItem, DescriptionList } from '@/components/ui/description-list';
import { Toolbar } from '@/components/ui/toolbar';
import { NOT_AVAILABLE, fallback } from '@/lib/format';

/**
 * The two shared primitives the detail and list screens were hand-rolling, and
 * the defect the port uncovered on the way through.
 *
 * The properties pinned here are the ones a later edit could quietly lose: that
 * `DescriptionList` renders a real `<dl>` rather than three divs with the right
 * padding, that it never invents a dash for an absent value (`lib/format.ts`
 * owns that vocabulary and screens may not add to it), and that `className`
 * still comes last so a caller can override the default grid.
 *
 * `ListToolbar` is here for a different reason. It hardcoded `id="list-search"`,
 * which is invisible on the nineteen screens that render one toolbar and wrong
 * on any screen that renders two: the ids collide and the second label points at
 * the first input, so clicking it focuses the wrong box. That regression never
 * had a test.
 */

describe('DescriptionList', () => {
  it('renders a real description list, not three divs', () => {
    const { container } = render(
      <DescriptionList>
        <DescriptionItem term="Batch">Evening — Feb 2026</DescriptionItem>
      </DescriptionList>,
    );

    expect(container.querySelector('dl')).not.toBeNull();
    expect(container.querySelector('dt')?.textContent).toBe('Batch');
    expect(container.querySelector('dd')?.textContent).toBe('Evening — Feb 2026');
  });

  it('renders every pair it is handed', () => {
    render(
      <DescriptionList>
        <DescriptionItem term="Course">Linux administration</DescriptionItem>
        <DescriptionItem term="Trainer">Asha Rao</DescriptionItem>
      </DescriptionList>,
    );

    expect(screen.getByText('Course')).toBeInTheDocument();
    expect(screen.getByText('Trainer')).toBeInTheDocument();
    expect(screen.getByText('Asha Rao')).toBeInTheDocument();
  });

  it('emits a literal grid class for each column count it offers', () => {
    // Tailwind v4 scans source text, so an interpolated `sm:grid-cols-${n}`
    // would emit nothing and the grid would silently collapse to one column.
    for (const columns of [2, 3, 4, 5] as const) {
      const { container, unmount } = render(
        <DescriptionList columns={columns}>
          <DescriptionItem term="Batch">Evening</DescriptionItem>
        </DescriptionList>,
      );
      expect((container.querySelector('dl') as HTMLElement).className).toContain(
        `sm:grid-cols-${columns}`,
      );
      unmount();
    }
  });

  it('merges className and lets it come last', () => {
    const { container } = render(
      <DescriptionList className="sm:grid-cols-1">
        <DescriptionItem term="Batch">Evening</DescriptionItem>
      </DescriptionList>,
    );

    const list = container.querySelector('dl') as HTMLElement;
    expect(list.className).toContain('sm:grid-cols-1');
    expect(list.className.indexOf('sm:grid-cols-1')).toBeGreaterThan(list.className.indexOf('grid'));
  });

  it('renders the format fallback for a null value, never 0 and never NaN', () => {
    render(
      <DescriptionList>
        <DescriptionItem term="Average score">{fallback(null)}</DescriptionItem>
      </DescriptionList>,
    );

    expect(screen.getByText(NOT_AVAILABLE)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bNaN\b/);
    expect(document.body.textContent).not.toMatch(/\b0\b/);
  });

  it('does not invent its own dash for a value the caller omitted', () => {
    // The fallback vocabulary is `lib/format.ts`'s and is fixed. A primitive
    // that substitutes an em dash of its own puts a sixth, untyped member into
    // it, and "—" cannot be told from "not applicable" or "still loading".
    const { container } = render(
      <DescriptionList>
        <DescriptionItem term="Completed on">{null}</DescriptionItem>
      </DescriptionList>,
    );

    expect(container.querySelector('dd')?.textContent).toBe('');
  });
});

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
