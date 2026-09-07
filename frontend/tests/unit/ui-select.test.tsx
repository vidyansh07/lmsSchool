import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { Select, SelectGroup } from '@/components/ui/select';
import { Select as SelectFromInput } from '@/components/ui/input';

function Controlled() {
  const [value, setValue] = useState('draft');
  return (
    <Select aria-label="Status" value={value} onChange={(event) => setValue(event.target.value)}>
      <option value="draft">Draft</option>
      <option value="published">Published</option>
    </Select>
  );
}

describe('Select', () => {
  it('renders a native select with its options', () => {
    render(
      <Select aria-label="Status" defaultValue="draft">
        <option value="draft">Draft</option>
        <option value="published">Published</option>
      </Select>,
    );
    const select = screen.getByRole('combobox', { name: 'Status' });
    expect(select).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Published' })).toBeInTheDocument();
  });

  it('supports controlled usage', async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const select = screen.getByRole('combobox', { name: 'Status' }) as HTMLSelectElement;
    expect(select.value).toBe('draft');

    await user.selectOptions(select, 'published');
    expect(select.value).toBe('published');
  });

  it('supports uncontrolled usage via defaultValue', () => {
    render(
      <Select aria-label="Status" defaultValue="published">
        <option value="draft">Draft</option>
        <option value="published">Published</option>
      </Select>,
    );
    expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('published');
  });

  it('is non-interactive when disabled', () => {
    render(
      <Select aria-label="Status" disabled>
        <option value="draft">Draft</option>
      </Select>,
    );
    expect(screen.getByRole('combobox')).toBeDisabled();
  });

  it('applies the requested control size', () => {
    render(
      <Select aria-label="Status" uiSize="sm">
        <option value="draft">Draft</option>
      </Select>,
    );
    expect(screen.getByRole('combobox')).toHaveClass('h-8');
  });

  it('groups options with SelectGroup', () => {
    render(
      <Select aria-label="Status">
        <SelectGroup label="Active">
          <option value="draft">Draft</option>
        </SelectGroup>
      </Select>,
    );
    expect(screen.getByRole('group', { name: 'Active' })).toBeInTheDocument();
  });

  it('is re-exported unchanged from components/ui/input for existing call sites', () => {
    expect(SelectFromInput).toBe(Select);
  });
});
