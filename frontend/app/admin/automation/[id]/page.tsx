"use client";

import { use } from "react";

import { RequireAuth } from "@/components/require-auth";
import { RuleBuilder } from "@/components/automation/rule-builder";
import { Capability } from "@/lib/capabilities";

export default function AutomationRuleDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <RequireAuth capability={Capability.automationManage}>
      <RuleBuilder id={id} />
    </RequireAuth>
  );
}
