import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { DuplicateMatch } from '@/components/admissions/duplicate-match';
import type { StudentDuplicateMatch } from '@/types/api';

function match(overrides: Partial<StudentDuplicateMatch> = {}): StudentDuplicateMatch {
  return {
    id: 's1',
    name: 'Priya Shah',
    student_id: 'GRS-S-00001',
    batch_code: 'MERN-02',
    created_at: '2026-08-03T00:00:00Z',
    ...overrides,
  };
}

describe('DuplicateMatch', () => {
  it('renders nothing when there are no matches', () => {
    const { container } = render(
      <DuplicateMatch matches={[]} onConfirmDifferentPerson={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('names the match by name, student ID, batch and registration date', () => {
    render(<DuplicateMatch matches={[match()]} onConfirmDifferentPerson={vi.fn()} />);
    expect(screen.getByText('Possible existing student found')).toBeInTheDocument();
    expect(screen.getByText(/Priya Shah/)).toBeInTheDocument();
    expect(screen.getByText(/GRS-S-00001/)).toBeInTheDocument();
    expect(screen.getByText(/MERN-02/)).toBeInTheDocument();
  });

  it('pluralises the heading for more than one match', () => {
    render(
      <DuplicateMatch
        matches={[match(), match({ id: 's2', student_id: 'GRS-S-00002' })]}
        onConfirmDifferentPerson={vi.fn()}
      />,
    );
    expect(screen.getByText('2 possible existing students found')).toBeInTheDocument();
  });

  it('links to the existing record instead of forcing a new one', () => {
    render(<DuplicateMatch matches={[match()]} onConfirmDifferentPerson={vi.fn()} />);
    expect(screen.getByRole('link', { name: 'Open that record' })).toHaveAttribute(
      'href',
      '/admissions/s1',
    );
  });

  it('keeps the continue action disabled until a reason is typed', async () => {
    const onConfirmDifferentPerson = vi.fn();
    render(<DuplicateMatch matches={[match()]} onConfirmDifferentPerson={onConfirmDifferentPerson} />);
    const continueButton = screen.getByRole('button', { name: /continue registering/i });
    expect(continueButton).toBeDisabled();

    await userEvent.click(continueButton);
    expect(onConfirmDifferentPerson).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText(/this is a different person/i), 'Different phone owner');
    expect(continueButton).toBeEnabled();

    await userEvent.click(continueButton);
    expect(onConfirmDifferentPerson).toHaveBeenCalledWith('Different phone owner');
  });
});
