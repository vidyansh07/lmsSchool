"use client";

import { use } from "react";

import { DirectFillScreen } from "@/components/forms/direct-fill-screen";
import { RequireAuth } from "@/components/require-auth";
import { Capability } from "@/lib/capabilities";

export default function FillFormPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return (
    <RequireAuth capability={Capability.formAssign}>
      <DirectFillScreen slug={slug} />
    </RequireAuth>
  );
}
