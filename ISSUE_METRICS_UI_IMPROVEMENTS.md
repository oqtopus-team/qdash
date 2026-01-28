# Issue: Metrics UI Improvements

## Overview
Enhancement request for the Metrics page UI to improve usability and functionality.

## Requirements

### 1. Add "All Time" Option to Metrics Time Range Selector

**Description:**  
Currently, the metrics page only offers time range filters for "Last 1 Day", "Last 7 Days", and "Last 30 Days". Users should be able to view metrics data across all available time periods without any time constraints.

**Current Behavior:**
- Time range options: 1D, 7D, 30D
- Located in: `ui/src/components/features/metrics/MetricsPageContent.tsx`

**Proposed Change:**
- Add a new "All Time" button to the time range selector
- When selected, fetch metrics data without the `within_hours` parameter restriction
- Update the `TimeRange` type to include `"all"` as a valid option
- Update the time range calculation logic to support undefined `withinHours` when "All Time" is selected

**Technical Details:**
- File to modify: `ui/src/components/features/metrics/MetricsPageContent.tsx`
- Type definition change: `type TimeRange = "1d" | "7d" | "30d" | "all";`
- API parameter: Set `within_hours` to `undefined` when timeRange is `"all"`

### 2. Categorize Metrics Dropdown Menu

**Description:**  
The current metrics dropdown menu displays all metrics in a flat list, making it difficult to navigate when there are many metrics. The dropdown should be organized into logical categories for better user experience.

**Current Behavior:**
- All metrics (both qubit and coupling) are shown in a single flat list
- No visual grouping or categorization

**Proposed Change:**
- Group metrics into logical categories based on their function
- Use React-Select's grouped options feature to display categorized metrics
- Maintain separate categorization for Qubit and Coupling metric types

**Suggested Categories:**

#### For Qubit Metrics:
1. **Frequency**
   - Resonator Frequency
   - Qubit Frequency
   - Anharmonicity

2. **Coherence Times**
   - T1 (Energy Relaxation Time)
   - T2 Echo (Dephasing Time)
   - T2 Star (Free Induction Decay)

3. **Fidelity**
   - Average Gate Fidelity
   - X90 Gate Fidelity
   - X180 Gate Fidelity

4. **Readout**
   - Average Readout Fidelity

5. **Gate Control**
   - HPI Amplitude
   - HPI Length

#### For Coupling Metrics:
1. **Gate Fidelity**
   - ZX90 Gate Fidelity
   - Bell State Fidelity

2. **Interaction**
   - Static ZZ Interaction

**Technical Details:**
- File to modify: `ui/src/components/features/metrics/MetricsPageContent.tsx`
- Update the `groupedMetricOptions` useMemo to create proper category groups
- The categories should match the metric types defined in `config/metrics.yaml`
- Use React-Select's `GroupBase` type for proper type safety

**Example Implementation Structure:**
```typescript
const groupedMetricOptions: GroupBase<MetricOption>[] = useMemo(() => {
  if (metricType === "qubit") {
    return [
      {
        label: "Frequency",
        options: [/* frequency metrics */]
      },
      {
        label: "Coherence Times",
        options: [/* coherence metrics */]
      },
      // ... other categories
    ];
  } else {
    return [
      {
        label: "Gate Fidelity",
        options: [/* gate fidelity metrics */]
      },
      {
        label: "Interaction",
        options: [/* interaction metrics */]
      }
    ];
  }
}, [metricType, metricsConfig]);
```

## Benefits

1. **All Time Filter:** Allows users to view historical trends across the entire dataset, useful for long-term analysis and identifying patterns
2. **Categorized Dropdown:** Improves discoverability and reduces cognitive load when selecting metrics
3. **Better UX:** Makes the interface more intuitive and professional

## Implementation Considerations

- Ensure the "All Time" option handles large datasets efficiently
- Consider adding loading indicators for large time ranges
- Maintain backwards compatibility with existing metric selection behavior
- Test with both Qubit and Coupling metric types
- Verify that the categorization aligns with the CDF groups defined in `config/metrics.yaml`

## Related Files

- `ui/src/components/features/metrics/MetricsPageContent.tsx` - Main metrics page component
- `ui/src/hooks/useMetricsConfig.ts` - Metrics configuration hook
- `config/metrics.yaml` - Metrics metadata and configuration
- `ui/src/client/metrics/metrics.ts` - API client for metrics data

## Acceptance Criteria

- [ ] "All Time" button is visible in the time range selector
- [ ] Clicking "All Time" fetches metrics data without time restrictions
- [ ] Metrics dropdown menu shows categorized groups
- [ ] Categories are clearly labeled and logically organized
- [ ] All existing functionality continues to work as expected
- [ ] UI remains responsive and performant
- [ ] Changes work for both Qubit and Coupling metric types
