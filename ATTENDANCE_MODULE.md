# Attendance Module (Relational, No JSON)

## Migrations
- `attendance/migrations/0001_initial.py` (config, sites, Wi-Fi, schedules, records)
- `employees/migrations/0009_employee_pin_hash_employee_rfid_tag_id_and_more.py` (badge/RFID/PIN/schedule columns + unique constraints)

## Tables/Entities
- `attendance_configurations`: one active per employer, kiosk flags, enforcement toggles, kiosk token, anomaly thresholds.
- `attendance_location_sites`: geofence sites with lat/long + radius, optionally scoped to a branch.
- `attendance_allowed_wifi`: allowed SSID/BSSID rows (optionally scoped to site and/or branch).
- `attendance_kiosk_stations`: branch-scoped kiosk stations with their own token.
- `attendance_working_schedules` + `attendance_working_schedule_days`: relational working schedules (per weekday minutes).
- `attendance_records`: portal/kiosk/manual records with geo/Wi-Fi/IP metadata, overtime, status, anomaly reason.
- `employees`: adds `rfid_tag_id`, `pin_hash`, `user_account_id`, `working_schedule_id`; badge/RFID unique constraints.

## Core Validation (pseudocode)
### check-in (portal/kiosk)
```
config = ensure_attendance_configuration(employer_id)
if not config.is_enabled: error
assert employee.active
assert no open attendance_record for employee
    enforce_geo = config.enforce_geofence (unless kiosk bypass)
    enforce_wifi = config.enforce_wifi (unless kiosk bypass)
    site = match_site(lat, lon, branch=employee.branch_id) if geo required else optional match
    wifi = match_wifi(ssid, bssid, site, branch=employee.branch_id) if wifi required
if geo required and no site: error "You are not within the allowed company area"
if wifi required and no match: error "Connect to company Wi-Fi before checking in"
create attendance_record(status=approved, mode=portal/kiosk, check_in_at=device_time or now,
    check_in_site=site, check_in_wifi=wifi, check_in_ip=request_ip)
```

### check-out (portal/kiosk)
```
config = ensure_attendance_configuration(employer_id)
if not config.is_enabled: error
record = open attendance_record for employee; if none -> error
    enforce_geo = config.enforce_geofence_on_checkout (unless kiosk bypass)
    enforce_wifi = config.enforce_wifi_on_checkout (unless kiosk bypass)
    site = match_site(lat, lon, branch=employee.branch_id) if geo required else optional match
    wifi = match_wifi(ssid, bssid, site, branch=employee.branch_id) if wifi required
if geo required and no site: error
if wifi required and no match: error
expected = resolve_expected_minutes(employee, record.check_in_at)
record.check_out_at = device_time or now
record.worked_minutes = minutes_between(check_in_at, check_out_at)
record.expected_minutes = expected
record.overtime_worked_minutes = max(worked - expected, 0)
if config.auto_flag_anomalies and worked > max_daily_work_minutes_before_flag:
    record.status = to_approve; record.anomaly_reason = "Excessive hours"
save record with geo/wifi/ip checkout context
```

### geofence distance
```
distance_meters = haversine(lat1, lon1, site.lat, site.lon)
within = distance_meters <= site.radius_meters
```

### Wi-Fi match
```
query allowed_wifi where employer_id + is_active (+ site or global)
if bssid provided: prefer exact bssid match; fallback to SSID match if none found
else match ssid when bssid null
```

## API Endpoints (examples)
- `GET /api/attendance/config/` – list current employer/employee config
- `PUT /api/attendance/config/{id}/` – update config (employer)
- `POST /api/attendance/sites/` / `PUT /api/attendance/sites/{id}/`
- `POST /api/attendance/wifi/` / `PUT /api/attendance/wifi/{id}/`
- `POST /api/attendance/check-in` (portal) body:
  ```json
  {"employee_id": "emp-uuid", "latitude": 4.0510567, "longitude": 9.7678687, "wifi_ssid": "CompanyNet", "wifi_bssid": "AA:BB", "device_time": "2026-01-17T10:00:00Z"}
  ```
- `POST /api/attendance/check-out` (portal) same fields minus device_time optional.
- `POST /api/attendance/kiosk/check` (unauth) body:
  ```json
  {"employee_identifier": "BADGE123", "pin": "1234", "kiosk_token": "<branch_kiosk_token>", "wifi_ssid": "CompanyNet"}
  ```
  (Toggles check-in/out based on open record, mode=`kiosk`. Token must match a branch kiosk station; employee branch must match station branch.)
- `POST /api/attendance/kiosk-stations/` (employer) create branch kiosk stations; `GET/PATCH/DELETE` supported via ViewSet.
- `GET /api/attendance/records/to-approve` (employer)
- `POST /api/attendance/records/{id}/approve|refuse|partial-approve`
- `POST /api/attendance/manual-create` (employer) body:
  ```json
  {"employee_id": "emp-uuid", "check_in_at": "2026-01-17T08:00:00Z", "check_out_at": "2026-01-17T18:30:00Z", "overtime_approved_minutes": 60}
  ```
- `GET /api/attendance/report?from=2026-01-01&to=2026-01-31&group_by=month&measures=worked,expected,difference,balance`

## Indexes & Constraints
- `attendance_configurations`: unique active per employer (`is_enabled=True`).
- `attendance_location_sites`: unique (employer_id, name); indexes on (employer_id,is_active) and lat/long.
- `attendance_allowed_wifi`: unique (employer_id, ssid, bssid); indexes on employer+ssid/bssid.
- `attendance_working_schedules`: unique (employer_id, name); unique default schedule per employer.
- `attendance_working_schedule_days`: unique (schedule, weekday); check end_time > start_time.
- `attendance_records`: unique open record per employee (check_out_at is null); check check_out_at > check_in_at; indexes on employer+employee, status, mode, check_in_at.
- `employees`: unique badge_id and rfid_tag_id when non-empty; new columns pin_hash, user_account_id, working_schedule_id.

## Operational Notes
- Wi-Fi validation relies on SSID/BSSID sent by client; server cannot detect network directly.
- Geofence requires latitude/longitude from client; if permission denied and enforcement is enabled, check-in/out is blocked.
- Kiosk flows respect bypass flags (`kiosk_bypass_geofence`, `kiosk_bypass_wifi`) and optional PIN.
- Geofence/Wi-Fi matches are branch-aware: employee.branch_id must match the site/Wi-Fi branch (unless the site/Wi-Fi is global/null branch).
- Overtime can be partially approved via `overtime_approved_minutes`; anomalies auto-flag when duration exceeds `max_daily_work_minutes_before_flag`.
