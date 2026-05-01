"use client";

import { useMemo, useState } from "react";

import { Plus, X } from "lucide-react";

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
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useQueryClient } from "@tanstack/react-query";

import { CryostatCard } from "./CryostatCard";

export function CryoPageContent() {
  const queryClient = useQueryClient();
  const { data: cryostatsData, isLoading: cryostatsLoading } =
    useListCryostats();
  const { data: cooldownsData, isLoading: cooldownsLoading } =
    useListCooldowns();
  const { data: chipsData } = useListChips();

  const cryostats = cryostatsData?.data?.cryostats ?? [];
  const cooldowns = cooldownsData?.data?.cooldowns ?? [];
  const chips = chipsData?.data?.chips ?? [];

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

  if (cryostatsLoading || cooldownsLoading) {
    return (
      <PageContainer>
        <div className="text-base-content/60">Loading…</div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <PageHeader
            title="Cryostats & Cool-downs"
            description="Manage cryostats and their cool-down cycles. Assign chips to a cool-down so calibration data gets tagged at write time."
            className="mb-0"
          />
          <button
            className="btn btn-primary btn-sm gap-1"
            onClick={() => setNewCryostatOpen(true)}
          >
            <Plus className="h-4 w-4" />
            New cryostat
          </button>
        </div>

        {cryostats.length === 0 ? (
          <EmptyState
            title="No cryostats yet"
            description="Create one above to start tracking cool-downs."
            emoji="snowflake"
            size="lg"
          />
        ) : (
          <div className="grid grid-cols-1 gap-4">
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
        )}
      </div>

      {newCryostatOpen && (
        <NewCryostatModal
          onClose={() => setNewCryostatOpen(false)}
          onCreated={invalidate}
        />
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

function NewCryostatModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const create = useCreateCryostat();
  const [cryoId, setCryoId] = useState("");
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [model, setModel] = useState("");

  const handleCreate = async () => {
    if (!cryoId.trim()) return;
    await create.mutateAsync({
      data: {
        cryo_id: cryoId.trim(),
        name,
        location,
        manufacturer,
        model,
        status: "active",
      },
    });
    onCreated();
    onClose();
  };

  return (
    <ModalShell title="New cryostat" onClose={onClose}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Cryo ID" required>
          <input
            className="input input-sm input-bordered w-full"
            value={cryoId}
            onChange={(e) => setCryoId(e.target.value)}
            placeholder="K-101"
            autoFocus
          />
        </Field>
        <Field label="Name">
          <input
            className="input input-sm input-bordered w-full"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Triton XL #2"
          />
        </Field>
        <Field label="Manufacturer">
          <input
            className="input input-sm input-bordered w-full"
            value={manufacturer}
            onChange={(e) => setManufacturer(e.target.value)}
            placeholder="Oxford Instruments"
          />
        </Field>
        <Field label="Model">
          <input
            className="input input-sm input-bordered w-full"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="Triton 200"
          />
        </Field>
        <Field label="Location" wide>
          <input
            className="input input-sm input-bordered w-full"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="Lab B-204"
          />
        </Field>
      </div>
      <ModalFooter
        onCancel={onClose}
        onSubmit={handleCreate}
        submitLabel="Create cryostat"
        disabled={!cryoId.trim() || create.isPending}
        pending={create.isPending}
      />
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
    <ModalShell title={`New cool-down · ${cryoId}`} onClose={onClose}>
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
        Started now. Edit dates, description, and load chips from the detail
        panel after creation.
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
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="modal modal-open"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-box w-full max-w-2xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold">{title}</h3>
          <button
            className="btn btn-ghost btn-sm btn-square"
            onClick={onClose}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Field({
  label,
  required,
  wide,
  children,
}: {
  label: string;
  required?: boolean;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={wide ? "sm:col-span-2" : ""}>
      <label className="block text-xs text-base-content/60 mb-1">
        {label}
        {required && <span className="text-error ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}

function ModalFooter({
  onCancel,
  onSubmit,
  submitLabel,
  disabled,
  pending,
}: {
  onCancel: () => void;
  onSubmit: () => void;
  submitLabel: string;
  disabled: boolean;
  pending: boolean;
}) {
  return (
    <div className="modal-action mt-4">
      <button className="btn btn-sm btn-ghost" onClick={onCancel}>
        Cancel
      </button>
      <button
        className="btn btn-sm btn-primary"
        onClick={onSubmit}
        disabled={disabled}
      >
        {pending ? "Creating…" : submitLabel}
      </button>
    </div>
  );
}
