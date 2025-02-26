import "./globals.css";
import Providers from "./providers";
import Sidebar from "./components/Sidebar";

export const metadata = {
  title: "QDash",
  description: "Quantum Dashboard",
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
          <div className="drawer lg:drawer-open">
            <input id="drawer" type="checkbox" className="drawer-toggle" />
            <div className="drawer-content flex flex-col">
              {/* <Navbar /> */}
              <main className="flex-1 overflow-y-auto bg-base-100">
                {children}
              </main>
            </div>
            <Sidebar />
          </div>
        </Providers>
      </body>
    </html>
  );
}
