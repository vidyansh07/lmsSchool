'use client';

/**
 * The Communication Center (ERP Phase 19, ADR-12,
 * `docs/erp/COMMUNICATION_CATALOG.md`) — templates, the delivery log, and
 * manual send, under one admin-only section like Forms/Policies/Automation.
 */

import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { DeliveriesTab } from '@/components/communication/deliveries-tab';
import { ManualSend } from '@/components/communication/manual-send';
import { TemplatesTab } from '@/components/communication/templates-tab';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Capability, can } from '@/lib/capabilities';

function CommunicationCenter() {
  const { user } = useAuth();
  const mayViewDeliveries = can(user?.capabilities, Capability.communicationViewAny);
  const mayManageDeliveries = can(user?.capabilities, Capability.communicationSend);
  const maySend = can(user?.capabilities, Capability.communicationSend);

  return (
    <div className="animate-rise-in space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Communication</h1>
        <p className="text-sm text-muted-foreground">
          Templates for what the platform says on your behalf, what has actually gone out, and a
          way to reach a batch, a role or specific students directly.
        </p>
      </div>

      <Tabs defaultValue="templates">
        <TabsList>
          <TabsTrigger value="templates">Templates</TabsTrigger>
          {mayViewDeliveries ? <TabsTrigger value="deliveries">Delivery log</TabsTrigger> : null}
          {maySend ? <TabsTrigger value="send">Send</TabsTrigger> : null}
        </TabsList>
        <TabsContent value="templates">
          <TemplatesTab />
        </TabsContent>
        {mayViewDeliveries ? (
          <TabsContent value="deliveries">
            <DeliveriesTab canAct={mayManageDeliveries} />
          </TabsContent>
        ) : null}
        {maySend ? (
          <TabsContent value="send">
            <ManualSend />
          </TabsContent>
        ) : null}
      </Tabs>
    </div>
  );
}

export default function CommunicationPage() {
  return (
    <RequireAuth capability={Capability.templateManage}>
      <CommunicationCenter />
    </RequireAuth>
  );
}
