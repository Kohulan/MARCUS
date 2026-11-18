import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createQueryClient } from "./queries";

// One query cache for the tool. Loaded with the tool routes only (AppRoutes), so the
// pre-rendered pages do not carry TanStack Query.
const client = createQueryClient();

export default function QueryProvider({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
