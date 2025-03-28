import type {
  ExecuteCalibRequest,
  ListMenuResponse,
  ScheduleCalibResponse,
} from "@/schemas";

export type Menu = {
  name: string;
  username: string;
  description: string;
  qids: string[][];
  notify_bool: boolean;
  tasks?: string[];
  tags?: string[];
};

export const mapListMenuResponseToListMenu = (
  response: ListMenuResponse,
): Menu[] => {
  return response.menus.map((item) => ({
    name: item.name,
    username: item.username,
    description: item.description,
    qids: item.qids,
    notify_bool: item.notify_bool ?? false,
    tasks: item.tasks ?? [],
    tags: item.tags ?? [],
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
