# Datetime Handling

Store UTC timestamps and convert them only for display or calendar labels.

## Backend (Python)

Use `src/qdash/common/utils/datetime.py`:

| Helper | Use |
| --- | --- |
| `now()`, `now_iso()` | Current UTC timestamp |
| `local_now()` | Calendar labels in the configured server timezone |
| `ensure_timezone()` | Treat naive MongoDB timestamps as UTC |
| `to_datetime()`, `format_iso()` | Parse and serialize timestamps |
| `parse_elapsed_time()`, `format_elapsed_time()` | Convert durations |

MongoDB stores native datetimes; the API returns ISO8601 UTC strings. Store elapsed time as
seconds, then format it as `H:MM:SS`. Server calendar labels default to Asia/Tokyo through
`src/qdash/config.py`; this does not change timestamp storage.

## Frontend (TypeScript)

Use `ui/src/lib/utils/datetime.ts`, not `toLocaleString()`:

| Helper | Display |
| --- | --- |
| `formatDateTime()` | Date and time |
| `formatDate()` | Date |
| `formatTime()` | Time |
| `formatDateTimeCompact()` | Compact date and time |

The default timezone is `NEXT_PUBLIC_TIMEZONE`, falling back to Asia/Tokyo. Missing timestamps
render as `-`. Use `dateToDateInput()`, `dateToDateTimeLocal()`, or `toDateTimeLocal()` for native
inputs, and `toIsoSeconds()` when submitting `datetime-local` values so the offset is explicit.

Test timezone boundaries, naive database values, and missing timestamps when changing these helpers.
