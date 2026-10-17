'use client';

/**
 * Integrations: leads coming in (API keys for Meritto, a website form) and
 * events going out (webhooks an automation rule sends to). Administrators
 * only (`integration.manage`).
 */

import { ApiKeysTab } from '@/components/integrations/api-keys-tab';
import { WebhooksTab } from '@/components/integrations/webhooks-tab';
import { RequireAuth } from '@/components/require-auth';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Capability } from '@/lib/capabilities';

function Integrations() {
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
        <p className="text-sm text-ink-muted">
          Connect Meritto, your website and other systems: leads come in through an API key, and
          automation rules send events out through a webhook.
        </p>
      </div>
      <Tabs defaultValue="keys">
        <TabsList>
          <TabsTrigger value="keys">Lead API keys</TabsTrigger>
          <TabsTrigger value="webhooks">Webhooks</TabsTrigger>
        </TabsList>
        <TabsContent value="keys">
          <ApiKeysTab />
        </TabsContent>
        <TabsContent value="webhooks">
          <WebhooksTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function IntegrationsPage() {
  return (
    <RequireAuth capability={Capability.integrationManage}>
      <Integrations />
    </RequireAuth>
  );
}
