/**
 * API calls for integrations (`/api/v1/integrations/`): API keys that let
 * Meritto or a website post leads in, and webhooks automation can send to.
 * All of it needs `integration.manage`.
 */

import { apiFetch, apiMutate } from './api';
import type {
  ApiKeyCreated,
  IntegrationApiKey,
  IntegrationPreset,
  LeadIntake,
  Webhook,
  WebhookDelivery,
  WebhookSaved,
} from '@/types/api';

const BASE = '/api/v1/integrations';

/** Where another system posts a lead. */
export function leadEndpoint(origin: string): string {
  return `${origin.replace(/\/$/, '')}${BASE}/leads/`;
}

export function listApiKeys(): Promise<IntegrationApiKey[]> {
  return apiFetch<IntegrationApiKey[]>(`${BASE}/api-keys/`);
}

export function createApiKey(payload: {
  name: string;
  preset: IntegrationPreset;
  branch?: string | null;
  default_source?: string;
  field_map?: Record<string, string>;
}): Promise<ApiKeyCreated> {
  return apiMutate<ApiKeyCreated>(`${BASE}/api-keys/`, { method: 'POST', body: payload });
}

export function updateApiKey(
  id: string,
  payload: { name?: string; branch?: string | null; default_source?: string; field_map?: Record<string, string> },
): Promise<IntegrationApiKey> {
  return apiMutate<IntegrationApiKey>(`${BASE}/api-keys/${id}/`, { method: 'PATCH', body: payload });
}

export function revokeApiKey(id: string): Promise<IntegrationApiKey> {
  return apiMutate<IntegrationApiKey>(`${BASE}/api-keys/${id}/revoke/`, { method: 'POST' });
}

export function listIntakes(id: string): Promise<LeadIntake[]> {
  return apiFetch<LeadIntake[]>(`${BASE}/api-keys/${id}/intakes/`);
}

export function listWebhooks(): Promise<Webhook[]> {
  return apiFetch<Webhook[]>(`${BASE}/webhooks/`);
}

export function createWebhook(payload: {
  name: string;
  preset: IntegrationPreset;
  url: string;
  headers?: Record<string, string>;
}): Promise<WebhookSaved> {
  return apiMutate<WebhookSaved>(`${BASE}/webhooks/`, { method: 'POST', body: payload });
}

export function updateWebhook(
  id: string,
  payload: {
    name?: string;
    url?: string;
    headers?: Record<string, string>;
    is_active?: boolean;
    rotate_secret?: boolean;
  },
): Promise<WebhookSaved> {
  return apiMutate<WebhookSaved>(`${BASE}/webhooks/${id}/`, { method: 'PATCH', body: payload });
}

export function testWebhook(id: string): Promise<WebhookDelivery> {
  return apiMutate<WebhookDelivery>(`${BASE}/webhooks/${id}/test/`, { method: 'POST' });
}

export function listDeliveries(id: string): Promise<WebhookDelivery[]> {
  return apiFetch<WebhookDelivery[]>(`${BASE}/webhooks/${id}/deliveries/`);
}
