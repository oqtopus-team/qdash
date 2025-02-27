import type {
  ExecuteCalibRequest,
  ListMenuResponse,
  OneQubitCalibResponse,
  ScheduleCalibResponse,
  TwoQubitCalibResponse,
  OneQubitCalibData,
  TwoQubitCalibData,
} from "@/schemas";

export type Session = {
  labrad_hostname: string;
  labrad_username: string;
  labrad_password: string;
  cooling_down_id: string;
  experiment_username: string;
  package_name: string;
};

export type Menu = {
  name: string;
  description: string;
  one_qubit_calib_plan: number[][];
  two_qubit_calib_plan: [number, number][][];
  mode: string;
  notify_bool: boolean;
  flow: string[];
  tags?: string[];
  exp_list?: string[];
};

export const mapListMenuResponseToListMenu = (
  data: ListMenuResponse[],
): Menu[] => {
  return data.map((item) => ({
    name: item.name,
    description: item.description,
    one_qubit_calib_plan: item.one_qubit_calib_plan as number[][],
    two_qubit_calib_plan: item.two_qubit_calib_plan as [number, number][][],
    mode: item.mode,
    notify_bool: item.notify_bool ?? false,
    flow: item.flow,
    tags: (item.tags ?? []).filter(
      (tag): tag is string => tag !== null && tag !== "",
    ),
    exp_list: (item.exp_list ?? []).filter(
      (exp): exp is string => exp !== null && exp !== "",
    ),
  }));
};

export type DataFormat = {
  value: number;
  unit: string;
  type: string;
};

export type TwoQubitCalibration = {
  name: string;
  label: string;
  description: string;
  status: string;
  one_qubit_calib_plan: [number, number][][];
  qpu_name: string;
  wiring_info_name: string;
  _id: string;
  qubit_index_list: [number, number][];
  two_qubit_calib_plan: [number, number][][];
  cooling_down_id: string;
  mode: string;
  notify_bool: boolean;
  flow: string[];
  experiment_username: string;
  node_info: {
    fill: string;
    position: {
      x: number;
      y: number;
    };
  };
  two_qubit_calib_data: TwoQubitCalibData;
  created_at: string;
  updated_at: string;
};

export type TwoQubitCalib = {
  id: string;
  source: string;
  target: string;
  label: string;
  data: {
    status: string;
    two_qubit_calib_data: TwoQubitCalibData;
  };
  size: number;
  fill: string;
};

export const mapTwoQubitCalibResponseToTwoQubitCalibration = (
  data: TwoQubitCalibResponse[],
): TwoQubitCalib[] => {
  return data.map((item) => ({
    id: item.label,
    source: item.edge_info.source,
    target: item.edge_info.target,
    label: item.label,
    data: {
      status: item.status,
      two_qubit_calib_data: item.two_qubit_calib_data ?? {},
    },
    size: item.edge_info.size,
    fill: item.edge_info.fill,
  }));
};

export type OneQubitCalibration = {
  label: string;
  status: string;
  one_qubit_calib_plan: [number, number][][];
  qpu_name: string;
  wiring_info_name: string;
  _id: string;
  qubit_index_list: [number, number][];
  two_qubit_calib_plan: [number, number][][];
  cooling_down_id: string;
  mode: string;
  notify_bool: boolean;
  flow: string[];
  experiment_username: string;
  node_info: {
    fill: string;
    position: {
      x: number;
      y: number;
    };
  };
  one_qubit_calib_data: OneQubitCalibData;
  created_at: string;
  updated_at: string;
};

export type OneQubitCalib = {
  id: string;
  label: string;
  fill: string;
  data: {
    status: string;
    position: { x: number; y: number };
    one_qubit_calib_data: OneQubitCalibData;
  };
};

export const mapOneQubitCalibResponseToOneQubitCalibration = (
  data: OneQubitCalibResponse[],
): OneQubitCalib[] => {
  return data.map((item) => ({
    id: item.label,
    label: item.label,
    fill: item.node_info.fill,
    data: {
      status: item.status,
      position: {
        x: item.node_info.position.x,
        y: item.node_info.position.y,
      },
      one_qubit_calib_data: item.one_qubit_calib_data ?? {},
    },
  }));
};

export type Schedule = {
  idx: number;
  name: string;
  description: string;
  cron: string;
  timezone: string;
  scheduled: string;
  active: boolean;
};

export type CalibSchedule = {
  menu_name: string;
  menu: ExecuteCalibRequest;
  description: string;
  note: string;
  timezone: string;
  scheduled_time: string;
  flow_run_id: string;
};

export type CalibrationSchedule = {
  menu_name: string;
  menu: Menu;
  description: string;
  note: string;
  timezone: string;
  scheduled_time: string;
  flow_run_id: string;
};

export const mapScheduleCalibResponsetoCalibSchedule = (
  data: ScheduleCalibResponse[],
): CalibSchedule[] => {
  return data.map((item) => ({
    description: item.description,
    flow_run_id: item.flow_run_id,
    menu: item.menu,
    menu_name: item.menu_name,
    note: item.note,
    scheduled_time: item.scheduled_time,
    timezone: item.timezone,
  }));
};
