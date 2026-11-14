import type { Metadata } from "next";

import { SignIn } from "@/components/auth/auth-gate";

export const metadata: Metadata = { title: "Authentication" };

export default function LoginPage() {
  return <SignIn />;
}
