# Fleet Management Feature Overview

This feature explains how Payrova HR tracks vehicles across the fleet lifecycle. The experience is split into two frontend sections: **Configuration** for the stable master data and **Fleet Management** for daily operations. The supporting backend models are organized around these two scopes and highlight the dependencies between entities.

## Frontend separation
- **Configuration** – setup screens where administrators manage manufacturers, models, vendors, service types, category tags, and global rules (alerts, request policies). This is low-frequency but foundational data, so the UI focuses on scanning, searching, and validating dependent records before saving.
- **Fleet Management** – dashboards and workflows HR/fleet managers use for vehicle requests, assignments, contracts, services, and reporting. This part surfaces real-time lifecycle data, alerts (contract expiration, costly repairs), and filters tied to operational states (location, driver, vehicle status).

Configuration and Fleet Management are decoupled visually but share the same backend models; each change in Configuration cascades through the management workflows.

Refer to `configuration.md` for the master-data model and `management.md` for the operational flows, including business rules and reporting touchpoints.
