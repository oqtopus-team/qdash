# Dashboards

Use **Dashboards** to arrange the metric maps and frequency-collision checks you look at
together on one page, keep that arrangement, and share it with the other members of your project.

**Overview** shows every configured metric for one chip in a fixed order. A dashboard shows
only the panels you add, in the layout you choose, so a team can agree on one view for a
recurring question such as "which couplers are close to a Type1A collision after this cool-down".

## Create a Dashboard

Project editors and owners can create dashboards; viewers can open the dashboards shared with
them.

1. Open **Dashboards** and select **New dashboard**.
2. Enter a name and an optional description.
3. Under **Start from**, choose **Blank dashboard** or the **Frequency Collision Map**
   template. The template copies a how-to note, a qubit frequency map, and the Type0A, Type0B,
   Type1A, Type3A, Type1C, and Type2C collision checks into the new dashboard. The copy is yours:
   later changes to the template do not alter dashboards created from it.
4. Choose **Private** to keep the dashboard to yourself or **Shared with project** to show it to
   every project member. You can change this later.
5. Choose the default chip. Viewers can switch to another chip while they look at the dashboard
   without changing the saved default.
6. Select **Create dashboard**. The new dashboard opens; select **Edit** to add, remove, or
   reconfigure panels, for example to tighten a threshold before you share it.

Change the name, description, visibility, or default chip later under **Dashboard settings**.

## Add Panels

In edit mode, select **Add panel**, give the panel a title, and choose its type.

| Panel | Shows | Settings |
| --- | --- | --- |
| Qubit metric | One qubit metric on the chip topology, with the same colour scale as **Overview** | Metric |
| Coupling metric | One coupling metric on the chip topology | Metric |
| Collision check | One frequency-collision check as coloured qubits or directed coupler edges | Check, hop range, parameters |
| Markdown | Free text, for example the purpose of the dashboard or the decision rule the team applies | Content |

Each panel sits on a 12-column grid. Use the panel menu to move it, make it wider or narrower,
taller or shorter, duplicate it, or remove it. On a narrow screen every panel spans the full width.

Changes stay local until you select **Save**; **Discard** returns to the saved layout and
**Done** leaves edit mode. The
dashboard remembers the layout, the chip, and the panel settings. It does not store measured
values: every time someone opens it, the panels read the current accepted values of the selected
chip.

## Read a Collision Check Panel

A collision check panel evaluates one of the qubex frequency-collision conditions for every
qubit or every directed coupler pair of the chip, from the chip's current qubit frequency,
anharmonicity, resonator frequency, T1, T2 echo, and measured coupling strength.

| Check | Condition |
| --- | --- |
| Type0A | Qubit quality: frequency inside the allowed window, T1 and T2 above the minimum |
| Type0B | Excessive detuning between the pair |
| Type1A | GE–GE proximity |
| Type1B | CR selectivity against spectators in the target's MUX |
| Type1C | CR drive causes a GE transition |
| Type2A | Two-photon GF transition |
| Type2B | FG–GE collision (qubex formula) |
| Type2C | Two-photon e0–f1 detuning of the control qubit and its resonator, a screening value in MHz |
| Type3A | EF–GE proximity |
| Type3B | CR drive causes an EF transition |
| Type7 | Spectator FG–GE collision |
| Type8 | Stark-shifted GE–GE crossing |
| Type9 | Stark-shifted GE–EF crossing |

For every check except Type2C the value is the ratio of the estimate to its limit: blue is below
one, orange is exactly on the boundary, and red exceeds the limit. Type2C shows the signed
two-photon detuning in MHz and colours by the **|δ₂γ| window** instead; a small absolute value
means the pair is close to resonance. Grey marks a target that could not be evaluated, for
example because a frequency is missing.

Solid edges connect adjacent qubits; dashed edges connect qubits two hops apart in the same MUX,
which only Type1A and Type3A evaluate. Each direction of a pair is its own edge because the
first qubit is the control; switch between **Both**, **Forward**, and **Reverse** to show one
direction at a time. The legend counts the targets in each colour.

Select a qubit or an edge to open its details: the verdict, every term that went into the
ratio, and the list of defaults and estimates the check used, such as a default coupling when
no coupling strength is measured or an anharmonicity estimated from the qubit frequency. Use
**Copy all** to paste these into a note or a forum post.

The parameters of a check, such as the CNOT time, the adiabatic limit, or the default coupling,
are edited in the panel settings and saved with the dashboard. The panel footer shows the values
in effect. The defaults match the qubex collision checker; the Type2C window of 10 MHz is a
display aid, not a calibrated tolerance.

## Share and Reuse

A dashboard set to **Shared with project** appears under **Shared with project** on
**Dashboards** for every member of the project. Members can open it, switch its chip
for themselves, and use **Copy link** to send the page to a colleague, who needs access to the
same project to open it.

Only the owner and project owners can edit, re-share, or delete a dashboard. Any editor can
select **Duplicate** to get a private copy to change independently. Dashboards belong to the
project in which they were created and are not visible from other projects; see
[Projects and Data Sharing](./projects-and-data-sharing.md).

How this works: [Custom Dashboards architecture](../developer-guide/architecture/custom-dashboards.md).
