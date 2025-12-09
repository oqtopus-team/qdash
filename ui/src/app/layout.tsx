import "./globals.css";
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
        <Providers>
          <AppLayout>{children}</AppLayout>
        </Providers>
      </body>
    </html>
  );
}
