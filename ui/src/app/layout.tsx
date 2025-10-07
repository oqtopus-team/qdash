import "./globals.css";
import Navbar from "./components/Navbar";
import Sidebar from "./components/Sidebar";
import Providers from "./providers";
import { SidebarProvider } from "./contexts/SidebarContext";

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
          <SidebarProvider>
            <div className="flex w-full">
              <Sidebar />
              <div className="flex-1 flex flex-col min-h-screen w-0">
                <Navbar />
                <main className="flex-1 overflow-y-auto bg-base-100">
                  {children}
                </main>
              </div>
            </div>
          </SidebarProvider>
        </Providers>
      </body>
    </html>
  );
}
