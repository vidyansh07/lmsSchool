import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { DateRangePicker } from '@/components/date-range-picker';
import { localIsoDate } from '@/lib/format';

/**
 * The *local* date, which is what the picker uses (`localIsoDate`).
 *
 * This used to be `new Date().toISOString().slice(0, 10)` — UTC. In IST that
 * is the previous day for the first five and a half hours of every morning,
 * so these tests passed all afternoon and failed from midnight to half past
 * five. A test that is only true for part of the day is worse than no test:
 * it fails for a reason that has nothing to do with the change in front of
 * whoever is reading it.
 */
function today(): string {
  return localIsoDate();
}

describe('DateRangePicker', () => {
  it('renders the standard presets', () => {
    render(<DateRangePicker value={{ start: '', end: '' }} onChange={vi.fn()} />);
    for (const label of ['Today', 'This week', 'Last 7 days', 'Last 30 days', 'This month']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
  });

  it('does not show "This term" unless a term range is supplied', () => {
    render(<DateRangePicker value={{ start: '', end: '' }} onChange={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'This term' })).not.toBeInTheDocument();
  });

  it('shows "This term" when given a term range', () => {
    render(
      <DateRangePicker
        value={{ start: '', end: '' }}
        onChange={vi.fn()}
        termRange={{ start: '2026-06-01', end: '2026-12-01' }}
      />,
    );
    expect(screen.getByRole('button', { name: 'This term' })).toBeInTheDocument();
  });

  it('clicking "Today" emits a single-day range for today', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<DateRangePicker value={{ start: '', end: '' }} onChange={onChange} />);

    await user.click(screen.getByRole('button', { name: 'Today' }));
    expect(onChange).toHaveBeenCalledWith({ start: today(), end: today() });
  });

  it('clicking "Last 7 days" ends today and spans a week', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<DateRangePicker value={{ start: '', end: '' }} onChange={onChange} />);

    await user.click(screen.getByRole('button', { name: 'Last 7 days' }));
    const range = onChange.mock.calls[0]?.[0] as { start: string; end: string };
    expect(range.end).toBe(today());
    const days = (new Date(range.end).getTime() - new Date(range.start).getTime()) / 86_400_000;
    expect(days).toBe(6);
  });

  it('marks the active preset as pressed, not only as a different colour', () => {
    render(<DateRangePicker value={{ start: today(), end: today() }} onChange={vi.fn()} />);
    // This used to assert a `bg-primary` class, which pinned one token name
    // from a page test and told a screen reader nothing.
    expect(screen.getByRole('button', { name: 'Today', pressed: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Last 7 days', pressed: false })).toBeInTheDocument();
  });

  it('toggles the custom range inputs open, starting from a matched preset', async () => {
    const user = userEvent.setup();
    render(<DateRangePicker value={{ start: today(), end: today() }} onChange={vi.fn()} />);

    expect(screen.queryByLabelText('From')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Custom range' }));
    expect(screen.getByLabelText('From')).toBeInTheDocument();
    expect(screen.getByLabelText('To')).toBeInTheDocument();
  });

  it('shows custom inputs by default when the value matches no preset', () => {
    render(<DateRangePicker value={{ start: '2020-01-01', end: '2020-01-15' }} onChange={vi.fn()} />);
    expect(screen.getByLabelText('From')).toHaveValue('2020-01-01');
  });

  it('changing the custom "From" date updates the range', () => {
    const onChange = vi.fn();
    render(<DateRangePicker value={{ start: '2020-01-01', end: '2020-01-15' }} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2020-02-01' } });
    expect(onChange).toHaveBeenLastCalledWith({ start: '2020-02-01', end: '2020-01-15' });
  });
});
