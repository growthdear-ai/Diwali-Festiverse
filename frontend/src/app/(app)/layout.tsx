import { Suspense } from "react";
import { AppGate, Splash } from "@/components/app-gate";

// Auth, rooms and the shell are client-side (JWT lives in localStorage), so they stream in under Suspense.
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <Suspense fallback={<Splash />}>
      <AppGate>{children}</AppGate>
    </Suspense>
  );
}
