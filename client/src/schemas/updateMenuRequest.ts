/**
 * Generated by orval v7.3.0 🍺
 * Do not edit manually.
 * QDash Server
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import type { UpdateMenuRequestExpList } from "./updateMenuRequestExpList";
import type { UpdateMenuRequestTags } from "./updateMenuRequestTags";

export interface UpdateMenuRequest {
  description: string;
  exp_list?: UpdateMenuRequestExpList;
  flow: string[];
  mode: string;
  name: string;
  notify_bool?: boolean;
  one_qubit_calib_plan: number[][];
  tags?: UpdateMenuRequestTags;
  two_qubit_calib_plan: [number, number][][];
}
