/**
 * Generated by orval v7.6.0 🍺
 * Do not edit manually.
 * QDash API
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import type { MuxDetailResponseDetail } from "./muxDetailResponseDetail";

/**
 * MuxDetailResponse is a Pydantic model that represents the response for fetching the multiplexer details.
 */
export interface MuxDetailResponse {
  mux_id: number;
  detail: MuxDetailResponseDetail;
}
