import type { Metadata } from "next";
import { AppGate } from "@/components/app/gate";

export const metadata: Metadata = {
  title: { default: "Workspace", template: "%s · VELTRANE" },
};

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return <AppGate>{children}</AppGate>;
}
