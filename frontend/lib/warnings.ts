/** Warnings for the signed-in staff member (`/api/v1/warnings/`), most urgent first. */

import { apiFetch } from './api';
import type { StaffWarning } from '@/types/api';

export async function getWarnings(): Promise<StaffWarning[]> {
  return apiFetch<StaffWarning[]>('/api/v1/warnings/');
}
