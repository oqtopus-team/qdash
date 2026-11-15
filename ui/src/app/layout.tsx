import "./globals.css";
import type { Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import NextTopLoader from "nextjs-toploader";
import Providers from "./providers";

import { AppLayout } from "@/components/layout/AppLayout";

export const metadata = {
  title: "QDash",
  description: "Quantum Dashboard",
  icons: {
    icon: "/favicon.png",
  },
};

// `viewport-fit=cover` exposes the safe-area insets that the app chrome and the
// mobile tab bar pad themselves by.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body suppressHydrationWarning>
        <NextTopLoader
          color="oklch(var(--p))"
          height={3}
          showSpinner={false}
          shadow="0 0 10px oklch(var(--p)),0 0 5px oklch(var(--p))"
        />
        <Providers>
          <AppLayout>{children}</AppLayout>
        </Providers>
      </body>
    </html>
  );
}
