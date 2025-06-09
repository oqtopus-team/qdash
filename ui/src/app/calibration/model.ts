import type {
  ExecuteCalibRequest,
  ListMenuResponse,
  ScheduleCalibResponse,
  CreateMenuRequestSchedule,
} from "@/schemas";

export type Menu = {
  name: string;
  chip_id: string;
  username: string;
  description: string;
  schedule: CreateMenuRequestSchedule;
  notify_bool: boolean;
  tasks?: string[];
  tags?: string[];
};

export const mapListMenuResponseToListMenu = (
  response: ListMenuResponse,
): Menu[] => {
  return response.menus.map((item) => ({
    name: item.name,
    chip_id: item.chip_id,
    username: item.username,
    description: item.description,
    schedule: item.schedule,
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
