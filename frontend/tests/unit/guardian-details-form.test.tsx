/**
 * Guardian Details — step 2.
 *
 * The behaviour worth fixing in place is the "first guardian": the person the
 * institute rings when it rings one rather than all. Two first guardians is
 * not a state that means anything, so the tick behaves as a radio however
 * many boxes are drawn, and removing the marked one must not leave a student
 * with guardians and nobody to ring.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { GuardianDetailsForm } from '@/app/students/[id]/guardians/page';
import { ApiError } from '@/lib/api';

const listGuardians = vi.hoisted(() => vi.fn());
const setGuardians = vi.hoisted(() => vi.fn());
vi.mock('@/lib/guardians', async () => {
  const actual = await vi.importActual<typeof import('@/lib/guardians')>('@/lib/guardians');
  return { ...actual, listGuardians, setGuardians };
});

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

describe('GuardianDetailsForm', () => {
  beforeEach(() => {
    push.mockReset();
    listGuardians.mockReset().mockResolvedValue([]);
    setGuardians.mockReset().mockResolvedValue([]);
  });

  async function ready() {
    render(<GuardianDetailsForm studentId="student-1" />);
    await screen.findByText('Guardian 1');
  }

  it('opens on one empty guardian with the fields the desk asks for', async () => {
    await ready();
    expect(screen.getByRole('textbox', { name: 'Name' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Relation' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Mobile' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Email' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Occupation' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Ring this one first/ })).toBeChecked();
  });

  it('reads back the guardians a student already has, with the marked one first', async () => {
    listGuardians.mockResolvedValue([
      {
        id: 'g1',
        name: 'Ramesh Sharma',
        relation: 'father',
        relation_label: 'Father',
        mobile: '+919876543210',
        email: '',
        occupation: 'Shopkeeper',
        is_primary: false,
      },
      {
        id: 'g2',
        name: 'Sunita Sharma',
        relation: 'mother',
        relation_label: 'Mother',
        mobile: '',
        email: '',
        occupation: '',
        is_primary: true,
      },
    ]);
    await ready();

    expect(screen.getByText('Guardian 2')).toBeInTheDocument();
    const radios = screen.getAllByRole('radio', { name: /Ring this one first/ });
    expect(radios[0]).not.toBeChecked();
    expect(radios[1]).toBeChecked();
  });

  it('sends the set, with exactly one first guardian', async () => {
    await ready();
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Ramesh Sharma' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Relation' }), { target: { value: 'father' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Mobile' }), { target: { value: '+919876543210' } });

    fireEvent.click(screen.getByRole('button', { name: /Add another guardian/ }));
    const names = screen.getAllByRole('textbox', { name: 'Name' });
    fireEvent.change(names[1]!, { target: { value: 'Sunita Sharma' } });
    fireEvent.click(screen.getAllByRole('radio', { name: /Ring this one first/ })[1]!);

    fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));

    await waitFor(() => expect(setGuardians).toHaveBeenCalled());
    const [studentId, sent] = setGuardians.mock.calls[0]!;
    expect(studentId).toBe('student-1');
    expect(sent).toHaveLength(2);
    expect(sent.filter((row: { is_primary: boolean }) => row.is_primary)).toHaveLength(1);
    expect(sent[1].is_primary).toBe(true);
    expect(sent[0]).toMatchObject({ name: 'Ramesh Sharma', relation: 'father' });
  });

  it('drops a guardian nobody named rather than sending a blank one', async () => {
    await ready();
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Ramesh' } });
    fireEvent.click(screen.getByRole('button', { name: /Add another guardian/ }));

    fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
    await waitFor(() => expect(setGuardians).toHaveBeenCalled());
    expect(setGuardians.mock.calls[0]![1]).toHaveLength(1);
  });

  it('never leaves a student with guardians and nobody to ring', async () => {
    await ready();
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Ramesh' } });
    fireEvent.click(screen.getByRole('button', { name: /Add another guardian/ }));
    fireEvent.change(screen.getAllByRole('textbox', { name: 'Name' })[1]!, { target: { value: 'Sunita' } });
    // Mark the second, then remove it.
    fireEvent.click(screen.getAllByRole('radio', { name: /Ring this one first/ })[1]!);
    fireEvent.click(screen.getByRole('button', { name: 'Remove guardian 2' }));

    fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
    await waitFor(() => expect(setGuardians).toHaveBeenCalled());
    const sent = setGuardians.mock.calls[0]![1];
    expect(sent).toHaveLength(1);
    expect(sent[0].is_primary).toBe(true);
  });

  it('never drops to zero blocks when the last one is removed', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Remove guardian 1' }));
    expect(screen.getByText('Guardian 1')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('');
  });

  it('can be skipped — an adult paying their own fee has no guardian', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));

    expect(setGuardians).not.toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith('/students/student-1/admissions/new');
  });

  it('saves an empty set when every row was left blank', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));

    await waitFor(() => expect(setGuardians).toHaveBeenCalledWith('student-1', []));
    expect(push).toHaveBeenCalledWith('/students/student-1/admissions/new');
  });

  it('shows what the server said and stays put', async () => {
    setGuardians.mockRejectedValue(
      new ApiError(400, 'validation_error', 'No.', 'req-1', {
        guardians: ['Every guardian needs a name.'],
      }),
    );
    await ready();
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Ramesh' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));

    expect(await screen.findByText('Every guardian needs a name.')).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it('shows the five steps with this one current', async () => {
    await ready();
    const bar = screen.getByRole('list', { name: 'Registration steps' });
    expect(bar).toHaveTextContent('2. Guardian Details');
  });
});
