# HR: Work Schedule, Attendance Register & Meetings

## Work schedule

Every day an employee is expected to be `physical` (at a work location, GPS-geofenced), `online`, or `off`.
The expected mode for an employee on a date is resolved in this order (first match wins):

1. Employee date override (`work_schedule_overrides.user_id = <employee>`)
2. Company date override (`work_schedule_overrides.user_id IS NULL`) — e.g. public holidays
3. Employee weekly pattern (`work_schedule_days.user_id = <employee>`)
4. Company weekly pattern (`work_schedule_days.user_id IS NULL`); unconfigured weekdays default to
   Mon–Fri `physical` 08:00 start / 11:00 cut-off, weekend `off`

Overrides only change the mode; start and cut-off times always come from the weekly pattern.
The single implementation is `ScheduleResolver` in `services/hr/schedule_service.py`.
All dates use Africa/Nairobi time.

## Clock-in rules

- The mode is taken from the schedule — the employee does not choose it.
- `off` days: clock-in refused. Add an override to open a day.
- After the cut-off time: clock-in refused.
- After the start time (but before cut-off): accepted and flagged `is_late`.
- `physical` days: GPS must be within the radius of the day's work location (the date override's venue, else the default location).

## Work locations

`work_locations` holds the office and any other venues (name, coordinates, check-in radius). Exactly one
active location is the **default**; it applies to every physical day and in-person meeting that doesn't name
another venue. The first location created becomes the default, the default can't be archived, and archived
locations can't be chosen for new meetings or overrides (existing records keep working).
Managed in **Admin → Meetings & Attendance → Schedule & locations** (`/hr/locations`).
Physical date overrides and in-person meetings take an optional `location_id`.

## Attendance register

`GET /hr/attendance/register?start=&end=` (HR admins) and `GET /hr/attendance/me?start=&end=` (employees)
return per-day statuses: `present`, `late`, `absent`, `off`, `upcoming`. Absences are computed — a past
scheduled day (or today after cut-off) without a clock-in is `absent`; nothing is stored for them.
Ranges are limited to 92 days and default to the current month. Summaries include meeting attendance.

## Meetings

- Audience: `all` active employees, by `roles`, or a `custom` list. Resolved into attendee rows on save.
- Invited people get an in-app notification and an email. Updates, cancellations and removals notify the
  affected people; changing time/place/mode resets RSVPs and reminders.
- Employees accept/decline and self check-in from 15 minutes before start until the end.
  In-person (`physical`) meetings require GPS within the radius of the meeting's venue (default location if none chosen).
- HR admins can mark `attended` / `missed` / `excused` for anyone (excused may be set in advance).

## Meeting worker (cron)

`services/hr/meeting_worker.py` must run every 5–10 minutes. It:

1. Sends 24-hour and 1-hour reminders (once per attendee per window; skipped for people who declined,
   or who were invited inside that window and already received the invitation).
2. After a meeting ends, marks every attendee without a mark as `missed` (once per meeting).

Example crontab entry on the Docker host (adjust the container name):

```cron
*/10 * * * * docker exec kapuletu-backend python -m services.hr.meeting_worker >> /var/log/kapuletu/meeting_worker.log 2>&1
```

## Permissions

HR administration endpoints require the `manage_employees` permission (super admins, admins and the CEO
always pass). Employee endpoints are available to every internal role (not treasurers).

## Attendance corrections

HR admins can correct one employee's day from the register (`PUT /hr/attendance/adjustments`):
`present`, `late`, `absent` or `excused`, with a mandatory reason and optional clock times (present/late only).
Corrections can't be future-dated. They take precedence over the computed status but never modify the
employee's own clock-in record; `DELETE /hr/attendance/adjustments/{user_id}/{date}` reverts to it.
Excused days are excluded from scheduled days and all rates. Every correction is audit-logged
(`ATTENDANCE_ADJUSTED`) and the employee gets an in-app notification. Corrected days are flagged `adjusted`
in the register, the employee's calendar, reports and official PDFs.

## Attendance reports

`GET /hr/attendance/summary` (HR admins) returns an aggregated report for a period:
`period=week|month|quarter|year` with an optional `anchor` date inside it (default: today), or
`period=custom&start=&end=` (up to 366 days). Add `user_id` for a single employee's statement (includes a daily log).

The report contains company-wide totals (attendance rate, punctuality, absences, office days, hours worked,
average clock-in, daily-report review status, meeting attendance), a trend (by day for a week, by week for a
month or short custom range, by month for quarters/years), per-employee rows, and highlights.
All figures come from the same `_summarize` function used by the register and the employee's own history.

`GET /hr/attendance/summary/pdf` returns the same report as an official document.

## Official documents

`services/documents/official.py` (`OfficialDocument`) is the single builder for official Kapuletu PDFs:
letterhead on every page, title block with reference number / issue date (EAT) / prepared by / classification,
"Page X of Y" footer, branded tables and figure tiles, and a signature block. Issuing a document writes a
`DOCUMENT_ISSUED` entry to the audit log with its reference.

References follow `KPL/<DEPT>/<TYPE>/<YYYYMM>/<CODE>`:

| Document | Reference | Audited |
|---|---|---|
| Staff attendance report | `KPL/HR/ATT/…` | yes |
| Employee attendance statement | `KPL/HR/ATS/…` | yes |
| Financial transactions export (PDF) | `KPL/FIN/EXP/…` | yes |
| Subscription receipt | `KPL/FIN/RCT/<YYYYMM of payment>/<provider ref>` (stable across downloads) | no |

The letterhead details (name, address, phone, email, website, registration number, KRA PIN) are edited in
**Admin → Settings → Organisation** (`GET/PUT /admin/organization-profile`; super admins, admins and the CEO)
and stored in system config under `organization_profile`.
