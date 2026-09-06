import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { StepIndicator, type WizardStep } from '@/components/admissions/step-indicator';

const STEPS: WizardStep[] = [
  { key: 'student', label: 'Student' },
  { key: 'course', label: 'Course' },
  { key: 'batch', label: 'Batch' },
];

describe('StepIndicator', () => {
  it('marks the current step for assistive technology', () => {
    render(<StepIndicator steps={STEPS} current="course" completed={new Set()} onJump={vi.fn()} />);
    expect(screen.getByRole('button', { name: /Course/ })).toHaveAttribute('aria-current', 'step');
  });

  it('lets you jump back to a completed step', async () => {
    const onJump = vi.fn();
    render(
      <StepIndicator
        steps={STEPS}
        current="batch"
        completed={new Set(['student', 'course'])}
        onJump={onJump}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /Student/ }));
    expect(onJump).toHaveBeenCalledWith('student');
  });

  it('disables a step that has not been reached yet', () => {
    render(<StepIndicator steps={STEPS} current="student" completed={new Set()} onJump={vi.fn()} />);
    expect(screen.getByRole('button', { name: /Batch/ })).toBeDisabled();
  });

  it('does not disable the current step even before anything is completed', () => {
    render(<StepIndicator steps={STEPS} current="student" completed={new Set()} onJump={vi.fn()} />);
    expect(screen.getByRole('button', { name: /Student/ })).toBeEnabled();
  });
});
