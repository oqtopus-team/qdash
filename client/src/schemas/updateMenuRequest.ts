/**
 * Generated by orval v7.5.0 🍺
 * Do not edit manually.
 * QDash Server
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import type { UpdateMenuRequestExpList } from "./updateMenuRequestExpList";
import type { UpdateMenuRequestTags } from "./updateMenuRequestTags";

export interface UpdateMenuRequest {
  name: string;
  description: string;
  one_qubit_calib_plan: number[][];
  two_qubit_calib_plan: [number, number][][];
  mode: string;
  notify_bool?: boolean;
  flow: string[];
  exp_list?: UpdateMenuRequestExpList;
  tags?: UpdateMenuRequestTags;
}
