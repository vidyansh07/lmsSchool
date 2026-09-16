"use client";

import { use } from "react";

import { RequireAuth } from "@/components/require-auth";
import { FormDetail } from "@/components/forms/form-detail";
import { Capability } from "@/lib/capabilities";

export default function FormDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return (
    <RequireAuth capability={Capability.formView}>
      <FormDetail slug={slug} />
    </RequireAuth>
  );
}
