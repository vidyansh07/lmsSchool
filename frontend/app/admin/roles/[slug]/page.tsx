"use client";

import { use } from "react";

import { RequireAuth } from "@/components/require-auth";
import { Capability } from "@/lib/capabilities";
import { RoleBuilder } from "@/components/roles/role-builder";

export default function EditRolePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return (
    <RequireAuth capability={Capability.roleView}>
      <RoleBuilder slug={slug} />
    </RequireAuth>
  );
}
