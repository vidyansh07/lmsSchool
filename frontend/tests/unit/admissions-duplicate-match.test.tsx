import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { DuplicateMatch } from '@/components/admissions/duplicate-match';
import type { StudentListRow } from '@/types/api';

function student(overrides: Partial<StudentListRow> = {}): StudentListRow {
  return {
    id: 's1',
    student_id: 'GRS-S-00001',
    user_id: 'u1',
    email: 'priya@example.com',
    full_name: 'Priya Shah',
    city: 'Jaipur',
    qualification: 'bachelors',
    fee_status: 'pending',
    fee_amount: null,
    institution: '',
    roll_number: '',
    institution_kind: '',
    referred_by: null,
    is_active: true,
    is_email_verified: true,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('DuplicateMatch', () => {
  it('renders nothing when there are no matches', () => {
    const { container } = render(<DuplicateMatch matches={[]} onContinueAnyway={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('names the match by name, email and student ID', () => {
    render(<DuplicateMatch matches={[student()]} onContinueAnyway={vi.fn()} />);
    expect(screen.getByText('This looks like an existing student')).toBeInTheDocument();
    expect(screen.getByText(/Priya Shah/)).toBeInTheDocument();
    expect(screen.getByText(/priya@example.com/)).toBeInTheDocument();
    expect(screen.getByText(/GRS-S-00001/)).toBeInTheDocument();
  });

  it('pluralises the heading for more than one match', () => {
    render(
      <DuplicateMatch
        matches={[student(), student({ id: 's2', student_id: 'GRS-S-00002' })]}
        onContinueAnyway={vi.fn()}
      />,
    );
    expect(screen.getByText('2 existing students look like a match')).toBeInTheDocument();
  });

  it('links to the existing record instead of forcing a new one', () => {
    render(<DuplicateMatch matches={[student()]} onContinueAnyway={vi.fn()} />);
    expect(screen.getByRole('link', { name: 'Open this record' })).toHaveAttribute(
      'href',
      '/admissions/s1',
    );
  });

  it('lets the counsellor continue past the warning', async () => {
    const onContinueAnyway = vi.fn();
    render(<DuplicateMatch matches={[student()]} onContinueAnyway={onContinueAnyway} />);
    await userEvent.click(screen.getByRole('button', { name: /continue registering/i }));
    expect(onContinueAnyway).toHaveBeenCalledOnce();
  });
});
