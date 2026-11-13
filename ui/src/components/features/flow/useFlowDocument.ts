"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { GetFlowResponse, SaveFlowRequest } from "@/schemas";

import { useGetCurrentUser } from "@/client/auth/auth";
import { useListChips } from "@/client/chip/chip";
import { getFlow, getListFlowsQueryKey, saveFlow } from "@/client/flow/flow";
import type { JourneyContext } from "@/components/features/first-calibration/useFirstCalibrationJourney";
import { useToast } from "@/components/ui/Toast";

/**
 * One workflow open in an editor pane: its saved source, the draft being edited, its
 * properties, and the save that writes them back. The workflow editor holds one per pane,
 * so each pane edits and saves its own workflow.
 */
export interface FlowDocument {
  /** The workflow this document is for, or null for an empty pane. */
  name: string | null;
  /** The saved workflow, once it has loaded for `name`. */
  flow: GetFlowResponse | undefined;
  isLoading: boolean;
  error: unknown;
  /**
   * The draft and properties below belong to `name`. False while another workflow's values
   * are still in state, so nothing is shown, edited or saved under the wrong name.
   */
  isReady: boolean;
  code: string;
  setCode: (code: string) => void;
  description: string;
  setDescription: (value: string) => void;
  flowFunctionName: string;
  setFlowFunctionName: (value: string) => void;
  username: string;
  setUsername: (value: string) => void;
  chipId: string;
  setChipId: (value: string) => void;
  tags: string;
  setTags: (value: string) => void;
  folder: string;
  setFolder: (value: string) => void;
  defaultInterval: string;
  setDefaultInterval: (value: string) => void;
  /** The draft differs from the saved source. */
  isDirty: boolean;
  /** Save the draft and properties under `name`; false when there is nothing ready to save. */
  save: (context: JourneyContext) => boolean;
  isSaving: boolean;
  saveError: unknown;
  resetSave: () => void;
}

export function useFlowDocument(name: string | null): FlowDocument {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data: userData } = useGetCurrentUser();
  const { data: chipsData } = useListChips();

  const [loadedName, setLoadedName] = useState<string | null>(null);
  // Read by a save that answers later, to tell whether the pane still shows the saved workflow.
  const loadedNameRef = useRef<string | null>(null);
  // Counts each time a workflow is opened, so a save that answers after the pane reopened its
  // workflow does not move the new draft's baseline.
  const openCountRef = useRef(0);
  const [description, setDescription] = useState("");
  const [code, setCode] = useState("");
  const [originalCode, setOriginalCode] = useState("");
  const [flowFunctionName, setFlowFunctionName] = useState("");
  const [username, setUsername] = useState("");
  const [chipId, setChipId] = useState("");
  const [tags, setTags] = useState("");
  const [folder, setFolder] = useState("");
  const [defaultInterval, setDefaultInterval] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["flow", name],
    queryFn: () => getFlow(name as string),
    enabled: Boolean(name),
  });
  const flow = name ? data?.data : undefined;

  // The signed-in user, read when a workflow loads without a saved username.
  const currentUsername = useRef<string | undefined>(undefined);
  useEffect(() => {
    currentUsername.current = userData?.data?.username;
  });

  // Load the saved workflow into the draft only when it is opened. A refetch of the open
  // workflow, such as the one after a save, never replaces the draft, so edits made while a save
  // was pending survive. When the query drops its data (a project switch resets it), the next
  // answer opens the workflow again.
  useEffect(() => {
    if (!name || !flow) {
      if (loadedNameRef.current !== null) {
        loadedNameRef.current = null;
        setLoadedName(null);
      }
      return;
    }
    if (loadedNameRef.current === name) return;
    setDescription(flow.description);
    setCode(flow.code);
    setOriginalCode(flow.code);
    setFlowFunctionName(flow.flow_function_name);

    // Set username from flow or fallback to current user
    const flowUsername = (flow.default_parameters?.username as string) || "";
    setUsername(flowUsername || currentUsername.current || "");

    setChipId(flow.chip_id);
    setTags(flow.tags?.join(", ") || "");
    setFolder(flow.folder ?? "");
    const runParams = flow.default_run_parameters as
      | Record<string, { value?: string | number }>
      | undefined;
    setDefaultInterval(runParams?.interval?.value != null ? String(runParams.interval.value) : "");
    openCountRef.current += 1;
    loadedNameRef.current = name;
    setLoadedName(name);
  }, [name, flow]);

  // Set default username if not set by flow data
  useEffect(() => {
    if (userData?.data?.username && !username && !flow) {
      setUsername(userData.data.username);
    }
  }, [userData, username, flow]);

  // Set default chip_id if not set by flow data
  useEffect(() => {
    if (chipsData?.data?.chips && chipsData.data.chips.length > 0 && !chipId && !flow) {
      // Get the latest chip (sort by installed_at descending)
      const sortedChips = [...chipsData.data.chips].sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      });
      setChipId(sortedChips[0].chip_id);
    }
  }, [chipsData, chipId, flow]);

  const isReady = Boolean(name && flow && loadedName === name);

  // A save answers for the user and project it was submitted in; one that lands after a
  // project switch is dropped. The submitted source becomes the baseline only while the pane
  // still holds the draft it was submitted from, so edits made after submitting stay unsaved.
  const saveMutation = useMutation({
    mutationFn: ({
      request,
    }: {
      request: SaveFlowRequest;
      context: JourneyContext;
      openCount: number;
    }) => saveFlow(request),
    onSuccess: (_response, { request, context, openCount }) => {
      if (!context.isCurrent()) return;
      queryClient.invalidateQueries({ queryKey: ["flow", request.name] });
      // The Workflow page lists under ["flows"]; the editor's Explorer uses the generated key.
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: getListFlowsQueryKey() });
      queryClient.invalidateQueries({ queryKey: ["execution-availability"] });
      if (loadedNameRef.current === request.name && openCountRef.current === openCount) {
        setOriginalCode(request.code);
      }
      toast.success(`${request.name} saved successfully!`);
    },
  });
  const mutateSave = saveMutation.mutate;

  const save = useCallback(
    (context: JourneyContext) => {
      if (!name || !isReady) return false;
      if (!username.trim()) {
        toast.error("Please enter a username");
        return false;
      }
      const request: SaveFlowRequest = {
        name,
        description: description.trim(),
        code,
        flow_function_name: flowFunctionName.trim() || undefined,
        chip_id: chipId.trim(),
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        folder: folder.trim(),
        default_parameters: {
          username: username.trim(),
          chip_id: chipId.trim(),
        },
        default_run_parameters: defaultInterval.trim()
          ? {
              interval: {
                value: defaultInterval.trim(),
                value_type: "int",
                unit: "ns",
              },
            }
          : {},
      };
      mutateSave({ request, context, openCount: openCountRef.current });
      return true;
    },
    [
      name,
      isReady,
      username,
      description,
      code,
      flowFunctionName,
      chipId,
      tags,
      folder,
      defaultInterval,
      mutateSave,
      toast,
    ],
  );

  return {
    name,
    flow,
    isLoading: Boolean(name) && isLoading,
    error: name ? error : null,
    isReady,
    code,
    setCode,
    description,
    setDescription,
    flowFunctionName,
    setFlowFunctionName,
    username,
    setUsername,
    chipId,
    setChipId,
    tags,
    setTags,
    folder,
    setFolder,
    defaultInterval,
    setDefaultInterval,
    isDirty: isReady && code !== originalCode,
    save,
    isSaving: saveMutation.isPending,
    saveError: saveMutation.error,
    resetSave: saveMutation.reset,
  };
}
