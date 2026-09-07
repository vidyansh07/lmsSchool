import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

function Basic(props: { defaultValue?: string; value?: string; onValueChange?: (value: string) => void }) {
  return (
    <Tabs defaultValue={props.defaultValue} value={props.value} onValueChange={props.onValueChange}>
      <TabsList>
        <TabsTrigger value="overview">Overview</TabsTrigger>
        <TabsTrigger value="students">Students</TabsTrigger>
        <TabsTrigger value="settings" disabled>
          Settings
        </TabsTrigger>
      </TabsList>
      <TabsContent value="overview">Overview panel</TabsContent>
      <TabsContent value="students">Students panel</TabsContent>
      <TabsContent value="settings">Settings panel</TabsContent>
    </Tabs>
  );
}

describe('Tabs', () => {
  it('renders only the active panel', () => {
    render(<Basic defaultValue="overview" />);
    expect(screen.getByText('Overview panel')).toBeInTheDocument();
    expect(screen.queryByText('Students panel')).not.toBeInTheDocument();
  });

  it('switches panels when a different tab is clicked', async () => {
    const user = userEvent.setup();
    render(<Basic defaultValue="overview" />);

    await user.click(screen.getByRole('tab', { name: 'Students' }));
    expect(screen.getByText('Students panel')).toBeInTheDocument();
    expect(screen.queryByText('Overview panel')).not.toBeInTheDocument();
  });

  it('marks the active tab with aria-selected and a 0 tabIndex', () => {
    render(<Basic defaultValue="overview" />);
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tab', { name: 'Students' })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('tab', { name: 'Students' })).toHaveAttribute('tabindex', '-1');
  });

  it('supports controlled usage', async () => {
    const user = userEvent.setup();
    const onValueChange = vi.fn();
    function Controlled() {
      const [value, setValue] = useState('overview');
      return (
        <Basic
          value={value}
          onValueChange={(next) => {
            setValue(next);
            onValueChange(next);
          }}
        />
      );
    }
    render(<Controlled />);

    await user.click(screen.getByRole('tab', { name: 'Students' }));
    expect(onValueChange).toHaveBeenCalledWith('students');
    expect(screen.getByText('Students panel')).toBeInTheDocument();
  });

  it('moves to and activates the next tab with ArrowRight, skipping the panel', async () => {
    const user = userEvent.setup();
    render(<Basic defaultValue="overview" />);

    screen.getByRole('tab', { name: 'Overview' }).focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'Students' })).toHaveFocus();
    expect(screen.getByText('Students panel')).toBeInTheDocument();
  });

  it('wraps from the last tab to the first with ArrowRight', async () => {
    const user = userEvent.setup();
    render(<Basic defaultValue="students" />);

    screen.getByRole('tab', { name: 'Students' }).focus();
    await user.keyboard('{ArrowRight}'); // Settings is disabled, skip straight to Overview
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveFocus();
  });

  it('jumps to the first and last tabs with Home and End', async () => {
    const user = userEvent.setup();
    render(<Basic defaultValue="overview" />);

    screen.getByRole('tab', { name: 'Overview' }).focus();
    await user.keyboard('{End}');
    expect(screen.getByRole('tab', { name: 'Students' })).toHaveFocus();

    await user.keyboard('{Home}');
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveFocus();
  });

  it('does not activate a disabled tab', () => {
    render(<Basic defaultValue="overview" />);
    expect(screen.getByRole('tab', { name: 'Settings' })).toBeDisabled();
  });
});
