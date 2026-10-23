import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StageTrail, type StageTrailStep } from '@/components/ui/stage-trail';

const STEPS: StageTrailStep[] = [
  { key: 'new', label: 'New' },
  { key: 'contacted', label: 'Contacted' },
  { key: 'interested', label: 'Interested' },
  { key: 'registered', label: 'Registered' },
];

function stages() {
  return within(screen.getByRole('list')).getAllByRole('listitem');
}

describe('StageTrail', () => {
  it('fills up to the stage it is on and marks that one current', () => {
    render(<StageTrail steps={STEPS} current="interested" label="Lead stage" />);

    const [first, second, third, fourth] = stages();
    expect(first).toHaveClass('bg-success-wash');
    expect(second).toHaveClass('bg-success-wash');
    expect(third).toHaveClass('bg-success-wash');
    expect(third).toHaveAttribute('aria-current', 'step');
    // Not reached yet is not a warning, just not there: the muted fill.
    expect(fourth).not.toHaveClass('bg-success-wash');
    expect(fourth).not.toHaveAttribute('aria-current');
  });

  it('says where it stands for a screen reader, which cannot see a filled chevron', () => {
    render(<StageTrail steps={STEPS} current="contacted" label="Lead stage" />);
    expect(screen.getByRole('list', { name: 'Lead stage: now Contacted' })).toBeInTheDocument();
  });

  it('draws a record that stopped short as stopped, not as part-way along', () => {
    render(<StageTrail steps={STEPS} current="not_interested" endedLabel="Not interested" />);

    expect(screen.getByText('Not interested')).toBeInTheDocument();
    // A lead that went nowhere is not half-way to enrolling.
    for (const stage of stages()) {
      expect(stage).not.toHaveClass('bg-success-wash');
    }
  });

  it('leaves the trail unfilled for a stage it does not know', () => {
    render(<StageTrail steps={STEPS} current="something-else" />);
    for (const stage of stages()) {
      expect(stage).not.toHaveClass('bg-success-wash');
    }
  });

  it('is not operable, because a stage is not set by tapping it', () => {
    render(<StageTrail steps={STEPS} current="new" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
  });
});
