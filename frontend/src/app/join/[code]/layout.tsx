import { Suspense } from "react";
import { Splash } from "@/components/app-gate";

export default function JoinLayout({ children }: LayoutProps<"/join/[code]">) {
  return <Suspense fallback={<Splash />}>{children}</Suspense>;
}
