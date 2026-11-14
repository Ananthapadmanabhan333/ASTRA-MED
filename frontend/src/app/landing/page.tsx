import type { Metadata } from "next";

import { LandingPageView } from "@/components/screens/landing-page";

export const metadata: Metadata = { title: "Landing Page" };

export default function LandingPage() {
  return <LandingPageView />;
}
