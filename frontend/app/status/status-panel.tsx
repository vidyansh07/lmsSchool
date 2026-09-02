'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { useApi } from '@/hooks/use-api';
import { env } from '@/lib/env';
import type { ReadinessResponse } from '@/types/api';

export function StatusPanel() {
  const { data, error, isLoading, reload } = useApi<ReadinessResponse>('/health/ready/');

  if (isLoading) return <LoadingState label="Checking backend status…" rows={4} />;

  if (error) {
    return (
      <ErrorState
        title="Could not reach the backend"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={reload}
      />
    );
  }

  const checks = Object.entries(data?.checks ?? {});
  if (checks.length === 0) {
    return <EmptyState title="No checks registered" description="The backend reported no components." />;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <CardTitle>Overall</CardTitle>
          <Badge variant={data?.status === 'ok' ? 'success' : 'error'}>
            {data?.status === 'ok' ? 'Operational' : 'Degraded'}
          </Badge>
        </CardHeader>
        <CardContent className="space-y-3">
          <dl className="divide-y divide-border">
            {checks.map(([name, check]) => (
              <div key={name} className="flex items-center justify-between gap-4 py-2">
                <dt className="text-sm font-medium capitalize">{name}</dt>
                <dd className="flex items-center gap-3 text-sm text-muted-foreground">
                  <span>{check.duration_ms} ms</span>
                  <Badge variant={check.status === 'ok' ? 'success' : 'error'}>{check.detail}</Badge>
                </dd>
              </div>
            ))}
          </dl>
          <div className="flex items-center justify-between gap-3 pt-1">
            <p className="text-xs text-muted-foreground">
              API: <code className="font-mono">{env.publicApiBaseUrl}</code>
            </p>
            <Button variant="outline" size="sm" onClick={reload}>
              Refresh
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
