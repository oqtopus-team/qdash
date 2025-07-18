/**
 * Generated by orval v7.10.0 🍺
 * Do not edit manually.
 * QDash API
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import type { Qubit } from "./qubit";
import type { Coupling } from "./coupling";

/**
 * Device information.
 */
export interface Device {
  name: string;
  device_id: string;
  qubits: Qubit[];
  couplings: Coupling[];
  calibrated_at: string;
}
