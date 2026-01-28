# How to Create GitHub Issue

## Automated Method (Using the Template)

A GitHub issue template has been created at:
`.github/ISSUE_TEMPLATE/METRICS_UI_IMPROVEMENTS.yaml`

Once this template is merged to the main branch, you can create the issue by:

1. Go to: https://github.com/oqtopus-team/qdash/issues/new/choose
2. Select "Metrics UI Improvements" from the available templates
3. The form will be pre-filled with all the details
4. Click "Submit new issue"

## Manual Method (Copy & Paste)

Alternatively, you can create the issue manually:

1. Go to: https://github.com/oqtopus-team/qdash/issues/new
2. Copy the content from `ISSUE_METRICS_UI_IMPROVEMENTS.md`
3. Paste it into the issue description
4. Set the title to: **[Feature]: Metrics UI Improvements - All Time Filter and Categorized Dropdown**
5. Add labels: `enhancement`, `ui`, `frontend`
6. Click "Submit new issue"

## Issue Summary

The issue covers two main UI improvements:

1. **Add "All Time" Time Range Filter**
   - Adds a fourth time range option to view all available metrics data
   - Located in: `ui/src/components/features/metrics/MetricsPageContent.tsx`

2. **Categorize Metrics Dropdown Menu**
   - Organizes metrics into logical categories (Frequency, Coherence, Fidelity, etc.)
   - Uses React-Select's grouped options for better UX
   - Separate categories for Qubit and Coupling metrics

## Related Files

- `ISSUE_METRICS_UI_IMPROVEMENTS.md` - Detailed specification document
- `.github/ISSUE_TEMPLATE/METRICS_UI_IMPROVEMENTS.yaml` - GitHub issue template
