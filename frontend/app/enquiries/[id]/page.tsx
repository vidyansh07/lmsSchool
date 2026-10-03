"use client";

import { use } from "react";

import { EnquiryScreen } from "@/components/enquiries/enquiry-screen";
import { RequireAuth } from "@/components/require-auth";
import { Capability } from "@/lib/capabilities";

export default function EnquiryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequireAuth capability={Capability.enquiryViewAny}>
      <EnquiryScreen id={id} />
    </RequireAuth>
  );
}
