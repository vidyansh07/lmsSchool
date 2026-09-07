/**
 * The institution's branding, as the settings screen sees it.
 *
 * Separate from `lib/brand.ts`, which is the runtime *application* of a colour
 * to the document. This module is the API surface: read the stored value, write
 * a new one. Keeping them apart means the code that paints the page has no
 * network dependency and the code that talks to the server has no opinion about
 * CSS.
 */

import { apiFetch, apiMutate } from './api';

export interface Branding {
  brand_color: string | null;
  display_name: string | null;
}

export async function getBranding(): Promise<Branding> {
  return apiFetch<Branding>('/api/v1/branding/');
}

export async function updateBranding(changes: Partial<Branding>): Promise<Branding> {
  return apiMutate<Branding>('/api/v1/branding/', { method: 'PATCH', body: changes });
}
