/**
 * The message matrix (`/api/v1/notifications/message-settings/`): who hears
 * about what, and how.
 *
 * The server sends the *shape* with the data — the tabs, their events in
 * order, the recipients and the channels — so this screen never carries its
 * own copy of the list. A screen that hardcodes the events drifts the moment
 * one is added, and the first anybody knows is a message nobody can turn off.
 */

import { apiFetch, apiMutate } from './api';

export interface MessageRule {
  event: string;
  recipient: string;
  channel: string;
  is_enabled: boolean;
}

export interface MessageMatrix {
  tabs: { title: string; events: { key: string; label: string }[] }[];
  recipients: { key: string; label: string }[];
  channels: { key: string; label: string }[];
  rules: MessageRule[];
}

export function getMessageSettings(): Promise<MessageMatrix> {
  return apiFetch<MessageMatrix>('/api/v1/notifications/message-settings/');
}

/** Only the cells that moved — the screen has thirty and a person changes
 *  one. */
export function setMessageRules(rules: MessageRule[]): Promise<MessageMatrix> {
  return apiMutate<MessageMatrix>('/api/v1/notifications/message-settings/', {
    method: 'PUT',
    body: { rules },
  });
}
