# GitHub Issue Creation - Summary

## What Was Done

I've prepared everything needed to create a GitHub issue for the metrics UI improvements. Since I cannot directly create GitHub issues through the API, I've created the necessary files and templates.

## Files Created

### 1. ISSUE_METRICS_UI_IMPROVEMENTS.md (4.8KB)
- Complete issue specification in markdown format
- Can be copied directly into a GitHub issue
- Contains all technical details and requirements

### 2. .github/ISSUE_TEMPLATE/METRICS_UI_IMPROVEMENTS.yaml (6.7KB)
- GitHub issue form template following the repository's standard
- Once merged, will appear in the issue creation menu
- Pre-fills all fields with the specification

### 3. GITHUB_ISSUE_INSTRUCTIONS.md (1.6KB)
- Step-by-step guide for creating the issue
- Explains both automated (template) and manual methods

## How to Create the Issue

### Method 1: Using the Template (After PR Merge)
Once this PR is merged to main:
1. Go to: https://github.com/oqtopus-team/qdash/issues/new/choose
2. Select "Metrics UI Improvements" template
3. Review the pre-filled form
4. Click "Submit new issue"

### Method 2: Manual Creation (Available Now)
Before the PR is merged:
1. Go to: https://github.com/oqtopus-team/qdash/issues/new
2. Open `ISSUE_METRICS_UI_IMPROVEMENTS.md` in this repository
3. Copy the entire content
4. Paste into the issue description
5. Set title: `[Feature]: Metrics UI Improvements - All Time Filter and Categorized Dropdown`
6. Add labels: `enhancement`, `ui`, `frontend`
7. Click "Submit new issue"

## Issue Overview

The issue requests two UI enhancements for the metrics page:

### 1. Add "All Time" Time Range Filter
- Add a fourth option to view metrics across all available time
- Currently limited to: 1D, 7D, 30D
- Change required in: `ui/src/components/features/metrics/MetricsPageContent.tsx`

### 2. Categorize Metrics Dropdown Menu
- Organize metrics into logical groups for better UX
- Categories for Qubit Metrics:
  - Frequency (Resonator, Qubit, Anharmonicity)
  - Coherence Times (T1, T2 Echo, T2 Star)
  - Fidelity (Average Gate, X90, X180)
  - Readout (Average Readout Fidelity)
  - Gate Control (HPI Amplitude, HPI Length)
- Categories for Coupling Metrics:
  - Gate Fidelity (ZX90, Bell State)
  - Interaction (Static ZZ)

## Technical Details Included

Each requirement includes:
- Current behavior description
- Proposed changes
- Implementation examples with code snippets
- Files that need modification
- Benefits and considerations
- Acceptance criteria checklist

## Next Steps

1. Review this PR and merge if approved
2. After merge, use Method 1 (template) to create the issue
3. Or use Method 2 (manual) to create the issue immediately

## Note

I cannot create GitHub issues directly due to API limitations. The template and documentation files in this PR provide everything needed for someone with repository access to create the issue.
