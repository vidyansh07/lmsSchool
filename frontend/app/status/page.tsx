import type { Metadata } from 'next';

import { StatusPanel } from './status-panel';

export const metadata: Metadata = { title: 'System status' };

export default function StatusPage() {
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">System status</h1>
        <p className="text-sm text-muted-foreground">
          Live readiness of the backend and its dependencies, read from the API by your browser.
          This proves the frontend and backend can talk to each other.
        </p>
      </div>
      <StatusPanel />
    </div>
  );
}
