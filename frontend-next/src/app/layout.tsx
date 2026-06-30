"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import Sidebar from "@/components/Sidebar";
import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <html lang="en">
      <body className="flex h-screen overflow-hidden">
        <QueryClientProvider client={queryClient}>
          <Sidebar />
          <main className="flex-1 flex flex-col overflow-hidden">{children}</main>
        </QueryClientProvider>
      </body>
    </html>
  );
}
