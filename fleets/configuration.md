# Configuration Layer (Master Data)

This section captures the stable data that must exist before vehicles can be created or serviced. The frontend exposes managed lists, detail forms, and validation hints so administrators can prepare the fleet catalogue and policies once per business cycle.

## Core entities

| Entity | Key fields | Depends on | Usage |
|---|---|---|---|
| **Manufacturer** | `name`, optional `logo_url`, status (active/suspended) | None | Controls which brands appear when adding models and drives filtering in reporting. |
| **Model Category** | `name`, `description`, optional `priority` | None | Tags models for filtering; used by HR to surface groups such as "Executive" or "Bike". |
| **Vehicle Model** | `name`, `manufacturer_id`, `vehicle_type` (`Car`/`Bike`), `category_id`, `seating_capacity`, `doors`, `fuel_type`, `transmission`, `power_source`, optional `co2_emissions` | Requires Manufacturer and Category | Serves as the immutable blueprint for every `Vehicle` record; drives validation when vehicles are created. |
| **Service Type** | `name`, `description`, `severity`, `default_stage` | None | Reused across `ServiceRecord` entries and accident tracking; stage helps determine which workflows a service enters immediately. |
| **Vendor** | `name`, `vendor_type` (dealer, garage, etc.), contact info, `service_type_ids` | None | Attached to contracts, service records, and accident repairs. |
| **Fleet Settings** | `contract_alert_days`, `allow_new_requests`, optional `default_vendor`, notification channels | None (company scoped) | Drives UI hints (e.g., banner warning when `allow_new_requests` is false) and triggers alerts before contracts expire. |

## Relationships and rules

- Manufacturers must exist before associating a `VehicleModel`. Frontend enforces this by blocking new models until at least one manufacturer is active.
- Vehicle models require both a manufacturer and a category, ensuring every vehicle inherits manufacturer metadata and a business-friendly bucket (e.g., Small car, Bike).
- Service types and vendors are reused but can be edited without forcing other workflow changes. The frontend surfaces warning when a service type is modified and already linked to historical records.
- Fleet settings are company-scoped singletons; any UI updates do not affect historic data but do refresh alert thresholds and request logic in the management workflows.

## Frontend structure

- **Administrators screen** includes:
  - Sidebar list (Manufacturers, Models, Categories, Service Types, Vendors, Settings).
  - Detail panels showing dependency counts (e.g., number of models per manufacturer) to prevent deletions with active links.
  - A “Validation matrix” card that shows whether required master records (manufacturer + model + category) are ready before allowing vehicle creation.

- Changes are audited, but the operational UI reflects only approved/active entries.
