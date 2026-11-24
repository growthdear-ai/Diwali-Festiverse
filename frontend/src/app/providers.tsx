"use client";

import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/auth";
import { PrefsProvider } from "@/lib/prefs";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <PrefsProvider>
        {children}
        <Toaster
          theme="light"
          position="top-center"
          toastOptions={{ style: { background: "#fff", border: "1px solid #E8E6E1", color: "#0F172A", boxShadow: "0 12px 32px -12px rgb(15 23 42 / 0.25)" } }}
        />
      </PrefsProvider>
    </AuthProvider>
  );
}
