import "./globals.css";
import AppLayout from "./components/AppLayout";
import Providers from "./providers";

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
