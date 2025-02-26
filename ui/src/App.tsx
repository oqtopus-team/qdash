import "./App.css";
import { BrowserRouter as Router } from "react-router-dom";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import Navbar from "./components/Navbar";
import Sidebar from "./components/Sidebar";
import AppRoutes from "./routes";

function App() {
  // const { _, textClass, _ } = useTheme();
  const queryClient = new QueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <div className="bg-base-100 drawer lg:drawer-open">
          <input id="drawer" type="checkbox" className="drawer-toggle" />
          <div className="drawer-content">
            <Navbar />
            <AppRoutes />
          </div>
          <Sidebar />
        </div>
      </Router>
    </QueryClientProvider>
  );
}

export default App;
