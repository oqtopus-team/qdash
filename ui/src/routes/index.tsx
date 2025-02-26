import { Routes, Route } from "react-router-dom";

import Calibration from "../pages/CalibrationPage";
import ExperimentPage from "@/pages/ExperimentPage";
import ExecutionPage from "@/pages/ExecutionPage";
import ExecutionExperimentPage from "@/pages/ExecutionPage/ExecutionExperimentPage";
import FridgePage from "../pages/FridgePage";
import Home from "../pages/HomePage";
import { NotFoundPage } from "../pages/NotFoundPage";
import SettingsPage from "../pages/SettingsPage";
import QpuPage from "@/pages/QpuPage";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/experiment" element={<ExperimentPage />} />
      <Route path="/execution" element={<ExecutionPage />} />
      <Route
        path="/execution/:execution_id/experiment"
        element={<ExecutionExperimentPage />}
      />
      <Route path="/fridge" element={<FridgePage />} />
      <Route path="/calibration" element={<Calibration />} />
      <Route path="/qpu" element={<QpuPage />} />
      <Route path="/setting" element={<SettingsPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
