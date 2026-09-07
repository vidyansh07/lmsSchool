import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';

function ThreeOptions(props: { onValueChange?: (value: string) => void; defaultValue?: string }) {
  return (
    <RadioGroup aria-label="Difficulty" {...props}>
      <RadioGroupItem value="beginner" aria-label="Beginner" />
      <RadioGroupItem value="intermediate" aria-label="Intermediate" />
      <RadioGroupItem value="advanced" aria-label="Advanced" />
    </RadioGroup>
  );
}

function Controlled() {
  const [value, setValue] = useState('beginner');
  return (
    <RadioGroup aria-label="Difficulty" value={value} onValueChange={setValue}>
      <RadioGroupItem value="beginner" aria-label="Beginner" />
      <RadioGroupItem value="advanced" aria-label="Advanced" />
    </RadioGroup>
  );
}

describe('RadioGroup', () => {
  it('renders a radiogroup of mutually exclusive radios', () => {
    render(<ThreeOptions />);
    expect(screen.getByRole('radiogroup', { name: 'Difficulty' })).toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(3);
  });

  it('supports uncontrolled usage: clicking one selects only that one', async () => {
    const user = userEvent.setup();
    render(<ThreeOptions defaultValue="beginner" />);

    await user.click(screen.getByRole('radio', { name: 'Advanced' }));
    expect(screen.getByRole('radio', { name: 'Advanced' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Beginner' })).not.toBeChecked();
  });

  it('supports controlled usage', async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    expect(screen.getByRole('radio', { name: 'Beginner' })).toBeChecked();

    await user.click(screen.getByRole('radio', { name: 'Advanced' }));
    expect(screen.getByRole('radio', { name: 'Advanced' })).toBeChecked();
  });

  it('calls onValueChange when a different option is chosen', async () => {
    const user = userEvent.setup();
    const onValueChange = vi.fn();
    render(<ThreeOptions defaultValue="beginner" onValueChange={onValueChange} />);

    await user.click(screen.getByRole('radio', { name: 'Intermediate' }));
    expect(onValueChange).toHaveBeenCalledWith('intermediate');
  });

  it('moves selection with ArrowDown and wraps at the end', async () => {
    const user = userEvent.setup();
    render(<ThreeOptions defaultValue="advanced" />);

    screen.getByRole('radio', { name: 'Advanced' }).focus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('radio', { name: 'Beginner' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Beginner' })).toHaveFocus();
  });

  it('moves selection with ArrowUp and wraps at the start', async () => {
    const user = userEvent.setup();
    render(<ThreeOptions defaultValue="beginner" />);

    screen.getByRole('radio', { name: 'Beginner' }).focus();
    await user.keyboard('{ArrowUp}');
    expect(screen.getByRole('radio', { name: 'Advanced' })).toBeChecked();
  });

  it('only the checked item is a Tab stop once something is selected', () => {
    render(<ThreeOptions defaultValue="intermediate" />);
    expect(screen.getByRole('radio', { name: 'Beginner' })).toHaveAttribute('tabindex', '-1');
    expect(screen.getByRole('radio', { name: 'Intermediate' })).toHaveAttribute('tabindex', '0');
  });

  it('is non-interactive when disabled at the group level', async () => {
    const user = userEvent.setup();
    render(
      <RadioGroup aria-label="Difficulty" disabled defaultValue="beginner">
        <RadioGroupItem value="beginner" aria-label="Beginner" />
        <RadioGroupItem value="advanced" aria-label="Advanced" />
      </RadioGroup>,
    );
    expect(screen.getByRole('radio', { name: 'Advanced' })).toBeDisabled();

    await user.click(screen.getByRole('radio', { name: 'Advanced' }));
    expect(screen.getByRole('radio', { name: 'Advanced' })).not.toBeChecked();
  });
});
