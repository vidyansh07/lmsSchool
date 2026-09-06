import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { RegisterEditor } from '@/components/teaching/register-editor';
import type { AttendanceStatus, RegisterEntry } from '@/types/api';

function entry(overrides: Partial<RegisterEntry> = {}): RegisterEntry {
  return {
    enrollment_id: 'enrol-1',
    student_code: 'GRS-S-00001',
    full_name: 'Ada Lovelace',
    enrollment_status: 'active',
    status: null,
    note: '',
    was_corrected: false,
    ...overrides,
  };
}

function threeStudents(): RegisterEntry[] {
  return [
    entry({ enrollment_id: 'e1', full_name: 'Ada Lovelace', student_code: 'GRS-S-00001' }),
    entry({ enrollment_id: 'e2', full_name: 'Grace Hopper', student_code: 'GRS-S-00002' }),
    entry({ enrollment_id: 'e3', full_name: 'Alan Turing', student_code: 'GRS-S-00003' }),
  ];
}

/** Renders with static, non-reactive marks — for tests that only check
 *  markup, not the effect of an interaction. */
function StaticRegister({
  entries,
  marks = {},
  canMark = true,
}: {
  entries: RegisterEntry[];
  marks?: Record<string, AttendanceStatus>;
  canMark?: boolean;
}) {
  return (
    <RegisterEditor
      entries={entries}
      marks={marks}
      onMark={vi.fn()}
      onMarkAllPresent={vi.fn()}
      canMark={canMark}
    />
  );
}

/** Renders with real state, the way the workspace (which owns `marks`
 *  itself) drives this component — for tests that exercise keyboard/mouse
 *  interaction and check the result. */
function StatefulRegister({ entries, canMark = true }: { entries: RegisterEntry[]; canMark?: boolean }) {
  const [marks, setMarks] = useState<Record<string, AttendanceStatus>>({});
  return (
    <RegisterEditor
      entries={entries}
      marks={marks}
      onMark={(id, status) => setMarks((current) => ({ ...current, [id]: status }))}
      onMarkAllPresent={() =>
        setMarks(Object.fromEntries(entries.map((row) => [row.enrollment_id, 'present'])))
      }
      canMark={canMark}
    />
  );
}

describe('RegisterEditor', () => {
  it('renders one row per student', () => {
    render(<StaticRegister entries={threeStudents()} />);
    expect(screen.getByRole('row', { name: /Ada Lovelace/ })).toBeInTheDocument();
    expect(screen.getByRole('row', { name: /Grace Hopper/ })).toBeInTheDocument();
    expect(screen.getByRole('row', { name: /Alan Turing/ })).toBeInTheDocument();
  });

  it('shows an empty state for a class with no students', () => {
    render(<StaticRegister entries={[]} />);
    expect(screen.getByText('No students on this register')).toBeInTheDocument();
  });

  it('marks the focused row present on "p"', async () => {
    const user = userEvent.setup();
    render(<StatefulRegister entries={threeStudents()} />);
    screen.getByRole('row', { name: /Ada Lovelace/ }).focus();
    await user.keyboard('p');
    expect(screen.getByRole('row', { name: /Ada Lovelace, Present/ })).toBeInTheDocument();
  });

  it('marks absent on "a", late on "l", excused on "e"', async () => {
    const user = userEvent.setup();
    render(<StatefulRegister entries={threeStudents()} />);
    screen.getByRole('row', { name: /Ada Lovelace/ }).focus();
    await user.keyboard('a');
    expect(screen.getByRole('row', { name: /Ada Lovelace, Absent/ })).toBeInTheDocument();

    screen.getByRole('row', { name: /Grace Hopper/ }).focus();
    await user.keyboard('l');
    expect(screen.getByRole('row', { name: /Grace Hopper, Late/ })).toBeInTheDocument();

    screen.getByRole('row', { name: /Alan Turing/ }).focus();
    await user.keyboard('e');
    expect(screen.getByRole('row', { name: /Alan Turing, Excused/ })).toBeInTheDocument();
  });

  it('the running counts update live as rows are marked', async () => {
    const user = userEvent.setup();
    render(<StatefulRegister entries={threeStudents()} />);

    screen.getByRole('row', { name: /Ada Lovelace/ }).focus();
    await user.keyboard('p');
    screen.getByRole('row', { name: /Grace Hopper/ }).focus();
    await user.keyboard('p');
    screen.getByRole('row', { name: /Alan Turing/ }).focus();
    await user.keyboard('a');

    const region = document.querySelector('[aria-live="polite"]');
    expect(region).not.toBeNull();
    expect(region).toHaveTextContent('2');
    expect(region).toHaveTextContent('present');
    expect(region).toHaveTextContent('1');
    expect(region).toHaveTextContent('absent');
  });

  it('arrow keys move focus down and up the list, without running off either end', async () => {
    const user = userEvent.setup();
    render(<StatefulRegister entries={threeStudents()} />);
    screen.getByRole('row', { name: /Ada Lovelace/ }).focus();

    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('row', { name: /Grace Hopper/ })).toHaveFocus();

    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('row', { name: /Alan Turing/ })).toHaveFocus();

    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('row', { name: /Alan Turing/ })).toHaveFocus();

    await user.keyboard('{ArrowUp}');
    expect(screen.getByRole('row', { name: /Grace Hopper/ })).toHaveFocus();
  });

  it('Home and End jump to the first and last row', async () => {
    const user = userEvent.setup();
    render(<StatefulRegister entries={threeStudents()} />);
    screen.getByRole('row', { name: /Grace Hopper/ }).focus();

    await user.keyboard('{End}');
    expect(screen.getByRole('row', { name: /Alan Turing/ })).toHaveFocus();

    await user.keyboard('{Home}');
    expect(screen.getByRole('row', { name: /Ada Lovelace/ })).toHaveFocus();
  });

  it('"Mark all present" marks every row, and a correction fixes just the one exception', async () => {
    const user = userEvent.setup();
    render(<StatefulRegister entries={threeStudents()} />);

    await user.click(screen.getByRole('button', { name: 'Mark all present' }));
    expect(screen.getByRole('row', { name: /Ada Lovelace, Present/ })).toBeInTheDocument();
    expect(screen.getByRole('row', { name: /Grace Hopper, Present/ })).toBeInTheDocument();
    expect(screen.getByRole('row', { name: /Alan Turing, Present/ })).toBeInTheDocument();

    screen.getByRole('row', { name: /Grace Hopper/ }).focus();
    await user.keyboard('a');

    expect(screen.getByRole('row', { name: /Ada Lovelace, Present/ })).toBeInTheDocument();
    expect(screen.getByRole('row', { name: /Grace Hopper, Absent/ })).toBeInTheDocument();
    expect(screen.getByRole('row', { name: /Alan Turing, Present/ })).toBeInTheDocument();
  });

  it('a held modifier key does not mark the row (Ctrl+P is not "present")', async () => {
    const user = userEvent.setup();
    render(<StatefulRegister entries={threeStudents()} />);
    screen.getByRole('row', { name: /Ada Lovelace/ }).focus();

    await user.keyboard('{Control>}p{/Control}');
    expect(screen.getByRole('row', { name: /Ada Lovelace, unmarked/ })).toBeInTheDocument();
  });

  it('clicking a status button also marks the row (the mouse alternative)', async () => {
    const user = userEvent.setup();
    render(<StatefulRegister entries={threeStudents()} />);
    const row = screen.getByRole('row', { name: /Ada Lovelace/ });
    await user.click(within(row).getByRole('radio', { name: 'Excused' }));
    expect(screen.getByRole('row', { name: /Ada Lovelace, Excused/ })).toBeInTheDocument();
  });

  it('keypresses do nothing once the register can no longer be marked', async () => {
    const user = userEvent.setup();
    render(<StatefulRegister entries={threeStudents()} canMark={false} />);
    screen.getByRole('row', { name: /Ada Lovelace/ }).focus();
    await user.keyboard('p');
    expect(screen.getByRole('row', { name: /Ada Lovelace, unmarked/ })).toBeInTheDocument();
    expect(screen.getByText(/cannot be marked right now/i)).toBeInTheDocument();
  });

  it('renders a fallback for a student with no name or code rather than blank or "undefined"', () => {
    render(<StaticRegister entries={[entry({ enrollment_id: 'e9', full_name: '', student_code: '' })]} />);
    expect(screen.getByText('Unknown')).toBeInTheDocument();
    expect(screen.getByText('Not available')).toBeInTheDocument();
    expect(screen.queryByText('undefined')).not.toBeInTheDocument();
  });

  it('shows a "Corrected" badge for a previously-corrected mark', () => {
    render(<StaticRegister entries={[entry({ was_corrected: true })]} />);
    expect(screen.getByText('Corrected')).toBeInTheDocument();
  });

  it('shows the enrolment status when it is not active', () => {
    render(<StaticRegister entries={[entry({ enrollment_status: 'suspended' })]} />);
    expect(screen.getByText('Suspended')).toBeInTheDocument();
  });

  it('shows the honest "not available" fallback for online/offline rather than a fabricated count', () => {
    render(<StaticRegister entries={threeStudents()} />);
    expect(screen.getByText(/Online: Not available/)).toBeInTheDocument();
    expect(screen.getByText(/Offline: Not available/)).toBeInTheDocument();
  });

  it('exposes the running counts in an aria-live polite region', () => {
    render(<StaticRegister entries={threeStudents()} />);
    expect(document.querySelector('[aria-live="polite"]')).toHaveAttribute('aria-live', 'polite');
  });
});
