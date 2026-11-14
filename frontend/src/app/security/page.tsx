import type { Metadata } from "next";

import { SecurityAuditView } from "@/components/screens/security-audit-view";

export const metadata: Metadata = { title: "Security & Audit Logs — ASTRA-MED" };

export default function SecurityAuditPage() {
  return <SecurityAuditView />;
}
