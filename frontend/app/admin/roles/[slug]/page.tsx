"use client";

import { use } from "react";

import { RequireAuth } from "@/components/require-auth";
import { RoleBuilder } from "@/components/roles/role-builder";

export default function EditRolePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return (
    <RequireAuth>
      <RoleBuilder slug={slug} />
    </RequireAuth>
  );
}
