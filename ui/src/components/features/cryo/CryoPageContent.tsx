"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AlertCircle, CircleDot, Cpu, Plus, Refrigerator, RotateCcw, X } from "lucide-react";

import { useListChips } from "@/client/chip/chip";
import {
  getListCooldownsQueryKey,
  useCreateCooldown,
  useListCooldowns,
} from "@/client/cooldown/cooldown";
import {
  getListCryostatsQueryKey,
  useCreateCryostat,
  useListCryostats,
} from "@/client/cryostat/cryostat";
import { EmptyState } from "@/components/ui/EmptyState";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { useQueryClient } from "@tanstack/react-query";

import { CryostatCard } from "./CryostatCard";

export function CryoPageContent() {
  const queryClient = useQueryClient();
  const {
    data: cryostatsData,
    isLoading: cryostatsLoading,
    isError: cryostatsError,
    refetch: refetchCryostats,
  } = useListCryostats();
  const {
    data: cooldownsData,
    isLoading: cooldownsLoading,
    isError: cooldownsError,
    refetch: refetchCooldowns,
  } = useListCooldowns();
  const { data: chipsData } = useListChips();

  const cryostats = useMemo(() => cryostatsData?.data?.cryostats ?? [], [cryostatsData]);
  const cooldowns = useMemo(() => cooldownsData?.data?.cooldowns ?? [], [cooldownsData]);
  const chips = useMemo(() => chipsData?.data?.chips ?? [], [chipsData]);

  const cooldownsByCryo = useMemo(() => {
    const map: Record<string, typeof cooldowns> = {};
    cooldowns.forEach((c) => {
      if (!map[c.cryo_id]) map[c.cryo_id] = [];
      map[c.cryo_id].push(c);
    });
    return map;
  }, [cooldowns]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: getListCryostatsQueryKey() });
    queryClient.invalidateQueries({ queryKey: getListCooldownsQueryKey() });
  };

  const [newCryostatOpen, setNewCryostatOpen] = useState(false);
  const [newCooldownFor, setNewCooldownFor] = useState<string | null>(null);

  const isLoading = cryostatsLoading || cooldownsLoading;
  const isError = cryostatsError || cooldownsError;
  const showNewCryostatHeaderBtn = cryostats.length > 0;

  const overview = useMemo(() => {
    const activeCooldowns = cooldowns.filter((cooldown) => !cooldown.ended_at);
    return {
      activeCooldowns: activeCooldowns.length,
      loadedChips: new Set(activeCooldowns.flatMap((cooldown) => cooldown.chip_ids)).size,
      attentionCryostats: cryostats.filter((cryo) => cryo.status !== "active").length,
    };
  }, [cooldowns, cryostats]);

  const retry = () => {
    void refetchCryostats();
    void refetchCooldowns();
  };

  return (
    <PageContainer>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <PageHeader
            title="Cryostats & Cool-downs"
            description="Manage cryostats and their cool-down cycles. Assign chips to a cool-down so calibration data gets tagged at write time."
            className="mb-0"
          />
          {showNewCryostatHeaderBtn && (
            <button
              className="btn btn-primary btn-sm gap-1"
              onClick={() => setNewCryostatOpen(true)}
            >
              <Plus className="h-4 w-4" />
              New cryostat
            </button>
          )}
        </div>

        {isLoading ? (
          <CryoLoadingSkeleton />
        ) : isError ? (
          <div className="alert alert-error" role="alert">
            <AlertCircle className="h-5 w-5" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <div className="font-medium">Failed to load cryogenic operations</div>
              <div className="text-sm opacity-80">
                Cryostats or cool-down history could not be retrieved. Existing data has not been
                changed.
              </div>
            </div>
            <button type="button" className="btn btn-sm btn-ghost gap-1" onClick={retry}>
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              Retry
            </button>
          </div>
        ) : cryostats.length === 0 ? (
          <EmptyState
            title="No cryostats yet"
            description="Register your fridge to start tracking cool-down cycles. Each cool-down tags calibration writes with its cooldown_id."
            emoji="snowflake"
            size="lg"
            action={
              <button
                className="btn btn-primary btn-sm gap-1 mt-3"
                onClick={() => setNewCryostatOpen(true)}
              >
                <Plus className="h-4 w-4" />
                New cryostat
              </button>
            }
          />
        ) : (
          <div className="space-y-6">
            <CryoOverview
              cryostats={cryostats.length}
              activeCooldowns={overview.activeCooldowns}
              loadedChips={overview.loadedChips}
              attentionCryostats={overview.attentionCryostats}
            />
            <div className="divide-y divide-base-300">
              {cryostats.map((cryo) => (
                <CryostatCard
                  key={cryo.cryo_id}
                  cryo={cryo}
                  cooldowns={cooldownsByCryo[cryo.cryo_id] ?? []}
                  allChips={chips.map((c) => c.chip_id)}
                  onChange={invalidate}
                  onCreateCooldown={() => setNewCooldownFor(cryo.cryo_id)}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {newCryostatOpen && (
        <NewCryostatModal onClose={() => setNewCryostatOpen(false)} onCreated={invalidate} />
      )}
      {newCooldownFor && (
        <NewCooldownModal
          cryoId={newCooldownFor}
          onClose={() => setNewCooldownFor(null)}
          onCreated={invalidate}
        />
      )}
    </PageContainer>
  );
}

function CryoOverview({
  cryostats,
  activeCooldowns,
  loadedChips,
  attentionCryostats,
}: {
  cryostats: number;
  activeCooldowns: number;
  loadedChips: number;
  attentionCryostats: number;
}) {
  const items = [
    { label: "Cryostats", value: cryostats, icon: Refrigerator },
    { label: "Cooling now", value: activeCooldowns, icon: CircleDot, active: true },
    { label: "Chips loaded", value: loadedChips, icon: Cpu },
    {
      label: "Need attention",
      value: attentionCryostats,
      icon: AlertCircle,
      warning: attentionCryostats > 0,
    },
  ];

  return (
    <section
      aria-label="Cryogenic operations overview"
      className="grid grid-cols-2 lg:grid-cols-4 gap-2"
    >
      {items.map(({ label, value, icon: Icon, active, warning }) => (
        <div key={label} className="rounded-xl border border-base-300 bg-base-100 px-3 py-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-medium text-base-content/60">{label}</span>
            <Icon
              className={`h-4 w-4 ${
                warning
                  ? "text-warning"
                  : active && value > 0
                    ? "text-success"
                    : "text-base-content/35"
              }`}
              aria-hidden="true"
            />
          </div>
          <div className="mt-1 text-2xl font-medium tabular-nums">{value}</div>
        </div>
      ))}
    </section>
  );
}

function CryoLoadingSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      {/* Header skeleton */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <div className="h-5 w-5 rounded bg-base-300" />
          <div className="h-6 w-24 rounded bg-base-300" />
          <div className="h-5 w-16 rounded-full bg-base-300" />
        </div>
        <div className="flex flex-wrap gap-1.5">
          <div className="h-5 w-24 rounded-full bg-base-300" />
          <div className="h-5 w-32 rounded-full bg-base-300" />
          <div className="h-5 w-28 rounded-full bg-base-300" />
        </div>
      </div>
      {/* Active banner skeleton */}
      <div className="h-16 rounded-xl bg-base-200/60" />
      {/* Timeline skeleton */}
      <div>
        <div className="h-3 w-20 rounded bg-base-300 mb-2" />
        <div className="h-20 rounded-md bg-base-200/60" />
      </div>
      {/* Detail panel skeleton */}
      <div className="h-64 rounded-xl bg-base-200/40" />
    </div>
  );
}

/** Zod schema for the new cryostat form; limits mirror the backend CryostatCreateRequest. */
const newCryostatSchema = z.object({
  cryoId: z
    .string()
    .trim()
    .min(1, "Cryo ID is required")
    .max(100, "Cryo ID must be 100 characters or fewer"),
  name: z.string().trim().max(200, "Name must be 200 characters or fewer"),
  manufacturer: z.string().trim().max(200, "Manufacturer must be 200 characters or fewer"),
  model: z.string().trim().max(200, "Model must be 200 characters or fewer"),
  location: z.string().trim().max(200, "Location must be 200 characters or fewer"),
});

type NewCryostatFormValues = z.infer<typeof newCryostatSchema>;

/** Modal form for registering a new cryostat. */
export function NewCryostatModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const create = useCreateCryostat();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<NewCryostatFormValues>({
    resolver: zodResolver(newCryostatSchema),
    defaultValues: {
      cryoId: "",
      name: "",
      manufacturer: "",
      model: "",
      location: "",
    },
  });

  /** Creates the cryostat and surfaces API failures as a server error. */
  const submit = async (values: NewCryostatFormValues) => {
    setServerError(null);
    try {
      await create.mutateAsync({
        data: {
          cryo_id: values.cryoId,
          name: values.name,
          location: values.location,
          manufacturer: values.manufacturer,
          model: values.model,
          status: "active",
        },
      });
      onCreated();
      onClose();
    } catch (err) {
      setServerError(getApiErrorMessage(err, "Failed to create cryostat"));
    }
  };

  /** Returns the input class names, adding the error style when invalid. */
  const inputClass = (invalid: boolean) =>
    `input input-sm input-bordered w-full${invalid ? " input-error" : ""}`;

  return (
    <ModalShell title="New cryostat" onClose={onClose} pending={create.isPending}>
      <form onSubmit={handleSubmit(submit)} noValidate>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Cryo ID" required htmlFor="cryostat-cryo-id">
            <input
              id="cryostat-cryo-id"
              className={inputClass(Boolean(errors.cryoId))}
              {...register("cryoId")}
              aria-invalid={Boolean(errors.cryoId)}
              aria-describedby={errors.cryoId ? "cryostat-cryo-id-error" : undefined}
              disabled={create.isPending}
              placeholder="K-101"
              autoFocus
            />
            {errors.cryoId && (
              <p id="cryostat-cryo-id-error" className="mt-1 text-xs text-error">
                {errors.cryoId.message}
              </p>
            )}
          </Field>
          <Field label="Name" htmlFor="cryostat-name">
            <input
              id="cryostat-name"
              className={inputClass(Boolean(errors.name))}
              {...register("name")}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={errors.name ? "cryostat-name-error" : undefined}
              disabled={create.isPending}
              placeholder="Triton XL #2"
            />
            {errors.name && (
              <p id="cryostat-name-error" className="mt-1 text-xs text-error">
                {errors.name.message}
              </p>
            )}
          </Field>
          <Field label="Manufacturer" htmlFor="cryostat-manufacturer">
            <input
              id="cryostat-manufacturer"
              className={inputClass(Boolean(errors.manufacturer))}
              {...register("manufacturer")}
              aria-invalid={Boolean(errors.manufacturer)}
              aria-describedby={errors.manufacturer ? "cryostat-manufacturer-error" : undefined}
              disabled={create.isPending}
              placeholder="Oxford Instruments"
            />
            {errors.manufacturer && (
              <p id="cryostat-manufacturer-error" className="mt-1 text-xs text-error">
                {errors.manufacturer.message}
              </p>
            )}
          </Field>
          <Field label="Model" htmlFor="cryostat-model">
            <input
              id="cryostat-model"
              className={inputClass(Boolean(errors.model))}
              {...register("model")}
              aria-invalid={Boolean(errors.model)}
              aria-describedby={errors.model ? "cryostat-model-error" : undefined}
              disabled={create.isPending}
              placeholder="Triton 200"
            />
            {errors.model && (
              <p id="cryostat-model-error" className="mt-1 text-xs text-error">
                {errors.model.message}
              </p>
            )}
          </Field>
          <Field label="Location" wide htmlFor="cryostat-location">
            <input
              id="cryostat-location"
              className={inputClass(Boolean(errors.location))}
              {...register("location")}
              aria-invalid={Boolean(errors.location)}
              aria-describedby={errors.location ? "cryostat-location-error" : undefined}
              disabled={create.isPending}
              placeholder="Lab B-204"
            />
            {errors.location && (
              <p id="cryostat-location-error" className="mt-1 text-xs text-error">
                {errors.location.message}
              </p>
            )}
          </Field>
        </div>
        {serverError && (
          <div className="alert alert-error mt-3 py-2 text-xs" role="alert">
            <span>{serverError}</span>
          </div>
        )}
        <ModalFooter
          onCancel={onClose}
          submitLabel="Create cryostat"
          disabled={create.isPending}
          pending={create.isPending}
        />
      </form>
    </ModalShell>
  );
}

function NewCooldownModal({
  cryoId,
  onClose,
  onCreated,
}: {
  cryoId: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const create = useCreateCooldown();
  const [cooldownId, setCooldownId] = useState("");

  const handleCreate = async () => {
    if (!cooldownId.trim()) return;
    await create.mutateAsync({
      data: {
        cooldown_id: cooldownId.trim(),
        cryo_id: cryoId,
        started_at: new Date().toISOString(),
      },
    });
    onCreated();
    onClose();
  };

  return (
    <ModalShell title={`New cool-down · ${cryoId}`} onClose={onClose} pending={create.isPending}>
      <Field label="Cooldown ID" required>
        <input
          className="input input-sm input-bordered w-full"
          value={cooldownId}
          onChange={(e) => setCooldownId(e.target.value)}
          placeholder="2026-001"
          autoFocus
        />
      </Field>
      <p className="text-xs text-base-content/50 mt-2">
        Started now. Edit dates, description, and load chips from the detail panel after creation.
      </p>
      <ModalFooter
        onCancel={onClose}
        onSubmit={handleCreate}
        submitLabel="Create cool-down"
        disabled={!cooldownId.trim() || create.isPending}
        pending={create.isPending}
      />
    </ModalShell>
  );
}

function ModalShell({
  title,
  onClose,
  children,
  pending = false,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  pending?: boolean;
}) {
  return (
    <Dialog open onOpenChange={(open) => !open && !pending && onClose()}>
      <DialogContent className="max-w-2xl">
        <div className="flex items-center justify-between mb-3">
          <DialogTitle>{title}</DialogTitle>
          <button
            type="button"
            className="btn btn-ghost btn-sm btn-square"
            onClick={onClose}
            disabled={pending}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </DialogContent>
    </Dialog>
  );
}

/** Labeled form field wrapper used by the cryo modals. */
function Field({
  label,
  required,
  wide,
  htmlFor,
  children,
}: {
  label: string;
  required?: boolean;
  wide?: boolean;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={wide ? "sm:col-span-2" : ""}>
      <label htmlFor={htmlFor} className="block text-xs text-base-content/60 mb-1">
        {label}
        {required && <span className="text-error ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}

/** Cancel and submit buttons shared by the cryo modals. */
function ModalFooter({
  onCancel,
  onSubmit,
  submitLabel,
  disabled,
  pending,
}: {
  onCancel: () => void;
  onSubmit?: () => void;
  submitLabel: string;
  disabled: boolean;
  pending: boolean;
}) {
  return (
    <div className="modal-action mt-4">
      <button type="button" className="btn btn-sm btn-ghost" onClick={onCancel} disabled={pending}>
        Cancel
      </button>
      <button
        type={onSubmit ? "button" : "submit"}
        className="btn btn-sm btn-primary"
        onClick={onSubmit}
        disabled={disabled}
      >
        {pending ? "Creating…" : submitLabel}
      </button>
    </div>
  );
}
