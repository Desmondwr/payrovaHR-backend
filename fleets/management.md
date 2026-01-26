# Fleet Management Layer (Daily Operations)

This layer focuses on the records HR and fleet managers interact with every day. The frontend is a multi-tab workspace that highlights vehicle lifecycle status, driver availability, contracts, services, and costs.

## Operational entities

| Entity | Key fields | Depends on | Website use |
|---|---|---|---|
| **Vehicle** | `license_plate`, `model_id`, `company_id`, `status` (`requested`, `ordered`, `registered`, `downgraded`, `retired`), `location`, `odometer`, `tags`, `current_driver_id` | `VehicleModel` (and through it Manufacturer & Category) | Acts as the central parent for assignments, contracts, services, and reporting panels. Lifecycle controls the UI buttons shown (e.g., only `requested` vehicles can be ordered). |
| **Driver Assignment** | `vehicle_id`, optional `employee_id`, optional `external_driver_name`, `assignment_type` (current / future), `start_date`, `end_date`, `handover_notes` | `Vehicle`, `Employee` (optional) | Daily view showing availability; list view includes filters for assigned vs. available vehicles, future handovers, and driver-specific costs. |
| **Contract** | `vehicle_id`, `start_date`, `end_date`, `responsible_person_id`, `catalog_value`, `residual_value`, `status` (`active`, `expired`, `terminated`) | `Vehicle`, `Employee` (responsible) | Contracts must be entered whenever a vehicle is ordered or renewed; UI surfaces alerts when `end_date - today <= contract_alert_days` (from Fleet Settings). Only one `active` contract allowed per vehicle. |
| **Service Record** | `vehicle_id`, `service_type_id`, `vendor_id`, `date`, `stage` (`new`, `in_progress`, `completed`, `cancelled`), `odometer`, `cost_estimate`, `cost_final`, `notes`, `attachments` | `Vehicle`, `ServiceType`, `Vendor` | Workflow board that tracks maintenance/repairs; stage controls which actions are available (e.g., "send vendor" for `new`). Each entry appears on vehicle history cards. |
| **Accident Event** | `service_record_ids`, `category` (`driver_fault`, `no_fault`), `total_estimated_cost`, `total_actual_cost`, `notes` | `ServiceRecord`, `Vehicle` (via service records) | Aggregated view for accident-related services; allows cost-tracking across multiple vendors and maintains traceability for insurance or payroll deductions. |

## Business rules & lifecycle flows

- Vehicles depend on models so the UI prevents creating or importing vehicles until the configuration verification succeeds. Vehicles move through statuses (`requested → ordered → registered → downgraded/retired`) and visual chips help managers know what action to take next.
- Driver management supports both internal employees and external drivers. Assignments can be `current` (active) or `future` (planned) and include handover notes so the front desk knows what to expect. Vehicles without a current driver show as “available”.
- Contracts must be attached to a vehicle; the system blocks saving if another `active` contract exists. Frontend shows a countdown using `contract_alert_days` so responsible people get notified in time.
- Services include vendor, type, and odometer to ensure maintenance history is complete. All stages are re-playable if a service is reopened. Accident events reuse service records and aggregate totals so that managers can tie multiple invoices to a single incident and easily see whether it was driver fault or not.

## Reporting & cost analysis

- Daily dashboards surface:
  - Total vehicle cost (sum of contracts + final service costs).
  - Cost per vehicle and per driver (aggregated from services and contracts linked to the assignment history).
  - Monthly/yearly trends with filters for categories, locations, and vendors (leveraging the master data from `configuration`).
  - Alerts for `vehicles nearing contract end` and `drivers with high repair costs`.
  - Leaderboards for most expensive vehicles and costliest drivers.

- Reports reuse the fleet settings (e.g., whether new requests are allowed) to determine what actions actionable cards offer (request new vehicle vs. choose from available ones).

## Frontend structure

- **Vehicle board** – Kanban-style lanes for lifecycle stages, quick filters by location/tags, and cards that link to assignment, contract, and service history.
- **Assignment panel** – Split view showing current driver, future handovers, and vehicle availability; clicking a driver reveals their cost impact and accident records.
- **Contracts & services page** – Table views with batch actions (e.g., send alerts, mark service as completed) and detail drawers showing vendor contact info and attachments.
- **Accident log** – Linked to service records; supports drilling into each repair and seeing vendor/responsible person data.
- **Reporting console** – Pre-built widgets + exportable CSV that surfaces cost totals, contract expirations, and driver cost rankings; settings determine refresh cadence and alert thresholds.
