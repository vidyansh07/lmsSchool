/**
 * Message Setting — the matrix of who hears about what, and how.
 *
 * Two things these tests hold in place:
 *
 * 1. the screen draws **what the server sent** — tabs, events, recipients
 *    and channels all arrive with the data, so adding an event on the server
 *    adds a row here without anybody editing the page;
 * 2. SMS is **labelled honestly**. The rules store and the audience resolves,
 *    and no provider is wired — an institute that believes texts are going
 *    out when they are not is the failure this warning exists to prevent.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MessageSettingsScreen } from '@/app/admin/settings/messages/page';
import { ApiError } from '@/lib/api';
import type { MessageMatrix } from '@/lib/message-settings';

const getMessageSettings = vi.hoisted(() => vi.fn());
const setMessageRules = vi.hoisted(() => vi.fn());
vi.mock('@/lib/message-settings', () => ({ getMessageSettings, setMessageRules }));

function matrix(overrides: Partial<MessageMatrix> = {}): MessageMatrix {
  return {
    tabs: [
      { title: 'Student', events: [{ key: 'student.birthday', label: 'Birthday' }] },
      {
        title: 'Payment',
        events: [
          { key: 'payment.made', label: 'Payment made' },
          { key: 'payment.cheque_bounced', label: 'Cheque bounced' },
        ],
      },
    ],
    recipients: [
      { key: 'student', label: 'Student' },
      { key: 'guardian', label: 'Guardian' },
      { key: 'owner', label: 'Owner' },
    ],
    channels: [
      { key: 'sms', label: 'SMS' },
      { key: 'email', label: 'E-Mail' },
      { key: 'push', label: 'Notification' },
    ],
    rules: [
      { event: 'payment.made', recipient: 'student', channel: 'sms', is_enabled: true },
      { event: 'payment.made', recipient: 'student', channel: 'push', is_enabled: true },
      { event: 'payment.made', recipient: 'guardian', channel: 'sms', is_enabled: false },
    ],
    ...overrides,
  };
}

describe('MessageSettingsScreen', () => {
  beforeEach(() => {
    getMessageSettings.mockReset().mockResolvedValue(matrix());
    setMessageRules.mockReset().mockResolvedValue(matrix());
  });

  it('draws the tabs the server sent, in its order', async () => {
    render(<MessageSettingsScreen />);
    const tabs = await screen.findByRole('navigation', { name: 'Message settings' });

    expect(within(tabs).getByRole('button', { name: 'Student' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(tabs).getByRole('button', { name: 'Payment' })).toBeInTheDocument();
  });

  it('draws a row per recipient under each event, and a box per channel', async () => {
    render(<MessageSettingsScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Payment' }));

    expect(screen.getByText('Payment made')).toBeInTheDocument();
    expect(screen.getByText('Cheque bounced')).toBeInTheDocument();
    // Two events, three recipients, three channels.
    expect(screen.getAllByRole('checkbox')).toHaveLength(18);
    expect(
      screen.getByRole('checkbox', { name: 'Payment made: Student by SMS' }),
    ).toBeChecked();
    expect(
      screen.getByRole('checkbox', { name: 'Payment made: Guardian by SMS' }),
    ).not.toBeChecked();
  });

  it('saves a box the moment it is clicked, sending only that cell', async () => {
    render(<MessageSettingsScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Payment' }));

    fireEvent.click(screen.getByRole('checkbox', { name: 'Payment made: Guardian by SMS' }));

    await waitFor(() =>
      expect(setMessageRules).toHaveBeenCalledWith([
        { event: 'payment.made', recipient: 'guardian', channel: 'sms', is_enabled: true },
      ]),
    );
  });

  it('turns one off again', async () => {
    render(<MessageSettingsScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Payment' }));

    fireEvent.click(screen.getByRole('checkbox', { name: 'Payment made: Student by SMS' }));

    await waitFor(() =>
      expect(setMessageRules).toHaveBeenCalledWith([
        { event: 'payment.made', recipient: 'student', channel: 'sms', is_enabled: false },
      ]),
    );
  });

  it('says plainly that SMS is not connected', async () => {
    render(<MessageSettingsScreen />);
    expect(
      await screen.findByText(/no SMS provider is connected yet/),
    ).toBeInTheDocument();
  });

  it('grows a row when the server grows an event, without being edited', async () => {
    getMessageSettings.mockResolvedValue(
      matrix({
        tabs: [
          {
            title: 'Payment',
            events: [
              { key: 'payment.made', label: 'Payment made' },
              { key: 'payment.invented_later', label: 'Something added later' },
            ],
          },
        ],
      }),
    );
    render(<MessageSettingsScreen />);

    expect(await screen.findByText('Something added later')).toBeInTheDocument();
    expect(
      screen.getByRole('checkbox', { name: 'Something added later: Owner by E-Mail' }),
    ).toBeInTheDocument();
  });

  it('keeps the table on screen and says so when a save fails', async () => {
    setMessageRules.mockRejectedValue(
      new ApiError(400, 'validation_error', 'No such event.', 'req-1'),
    );
    render(<MessageSettingsScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Payment' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Payment made: Owner by SMS' }));

    expect(await screen.findByText('No such event.')).toBeInTheDocument();
    expect(screen.getByText('Payment made')).toBeInTheDocument();
  });

  it('offers a retry when the matrix will not load at all', async () => {
    getMessageSettings.mockRejectedValue(new ApiError(500, 'server_error', 'Down.', 'req-1'));
    render(<MessageSettingsScreen />);

    expect(await screen.findByText('Down.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(getMessageSettings).toHaveBeenCalledTimes(2));
  });
});
