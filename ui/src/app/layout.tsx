import "./globals.css";
import NextTopLoader from "nextjs-toploader";
import Providers from "./providers";

import AppLayout from "@/components/layout/AppLayout";

export const metadata = {
  title: "QDash",
  description: "Quantum Dashboard",
  icons: {
    icon: "/favicon.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
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
