'use client';

import { use } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { TemplateBuilder } from '@/components/communication/template-builder';
import { Capability } from '@/lib/capabilities';

export default function TemplateDetailPage({
  params,
}: {
  params: Promise<{ key: string }>;
}) {
  const { key } = use(params);
  return (
    <RequireAuth capability={Capability.templateManage}>
      <TemplateBuilder templateKey={key} />
    </RequireAuth>
  );
}
