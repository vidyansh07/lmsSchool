"use client";

import { use } from "react";

import { FormAssignmentScreen } from "@/components/forms/form-assignment-screen";
import { RequireAuth } from "@/components/require-auth";

export default function FormAssignmentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequireAuth>
      <FormAssignmentScreen id={id} />
    </RequireAuth>
  );
}
