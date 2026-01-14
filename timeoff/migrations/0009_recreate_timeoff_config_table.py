from django.db import migrations


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS timeoff_configurations (
    id uuid PRIMARY KEY,
    employer_id integer NOT NULL,
    tenant_id integer NULL,
    schema_version integer NOT NULL DEFAULT 2,
    default_time_unit varchar(10) NOT NULL DEFAULT 'DAYS',
    working_hours_per_day integer NOT NULL DEFAULT 8,
    minimum_request_unit numeric(5,2) NOT NULL DEFAULT 0.50,
    leave_year_type varchar(10) NOT NULL DEFAULT 'CALENDAR',
    leave_year_start_month integer NOT NULL DEFAULT 1,
    holiday_calendar_source varchar(20) NOT NULL DEFAULT 'DEFAULT',
    time_zone_handling varchar(30) NOT NULL DEFAULT 'EMPLOYER_LOCAL',
    reservation_policy varchar(30) NOT NULL DEFAULT 'RESERVE_ON_SUBMIT',
    rounding_unit varchar(20) NOT NULL DEFAULT 'MINUTES',
    rounding_increment_minutes integer NOT NULL DEFAULT 30,
    rounding_method varchar(10) NOT NULL DEFAULT 'NEAREST',
    weekend_days jsonb DEFAULT '[]'::jsonb,
    module_enabled boolean NOT NULL DEFAULT true,
    allow_backdated_requests boolean NOT NULL DEFAULT true,
    allow_future_dated_requests boolean NOT NULL DEFAULT true,
    allow_negative_balance boolean NOT NULL DEFAULT false,
    negative_balance_limit integer NOT NULL DEFAULT 0,
    allow_overlapping_requests boolean NOT NULL DEFAULT false,
    backdated_limit_days integer NOT NULL DEFAULT 30,
    future_window_days integer NOT NULL DEFAULT 180,
    max_request_length_days integer NULL,
    max_requests_per_month integer NULL,
    auto_reset_date date NULL,
    auto_carry_forward_date date NULL,
    year_end_auto_reset_enabled boolean NOT NULL DEFAULT false,
    year_end_auto_carryover_enabled boolean NOT NULL DEFAULT false,
    year_end_process_on_month_day varchar(5) NOT NULL DEFAULT '01-01',
    request_history_years integer NOT NULL DEFAULT 7,
    ledger_history_years integer NOT NULL DEFAULT 7,
    configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp with time zone NOT NULL DEFAULT NOW(),
    updated_at timestamp with time zone NOT NULL DEFAULT NOW()
);

-- Backfill/align columns for existing tables (idempotent, safe for tenants)
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS tenant_id integer NULL;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS schema_version integer NOT NULL DEFAULT 2;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS default_time_unit varchar(10) NOT NULL DEFAULT 'DAYS';
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS working_hours_per_day integer NOT NULL DEFAULT 8;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS minimum_request_unit numeric(5,2) NOT NULL DEFAULT 0.50;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS leave_year_type varchar(10) NOT NULL DEFAULT 'CALENDAR';
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS leave_year_start_month integer NOT NULL DEFAULT 1;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS holiday_calendar_source varchar(20) NOT NULL DEFAULT 'DEFAULT';
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS time_zone_handling varchar(30) NOT NULL DEFAULT 'EMPLOYER_LOCAL';
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS reservation_policy varchar(30) NOT NULL DEFAULT 'RESERVE_ON_SUBMIT';
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS rounding_unit varchar(20) NOT NULL DEFAULT 'MINUTES';
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS rounding_increment_minutes integer NOT NULL DEFAULT 30;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS rounding_method varchar(10) NOT NULL DEFAULT 'NEAREST';
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS weekend_days jsonb DEFAULT '[]'::jsonb;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS module_enabled boolean NOT NULL DEFAULT true;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS allow_backdated_requests boolean NOT NULL DEFAULT true;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS allow_future_dated_requests boolean NOT NULL DEFAULT true;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS allow_negative_balance boolean NOT NULL DEFAULT false;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS negative_balance_limit integer NOT NULL DEFAULT 0;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS allow_overlapping_requests boolean NOT NULL DEFAULT false;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS backdated_limit_days integer NOT NULL DEFAULT 30;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS future_window_days integer NOT NULL DEFAULT 180;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS max_request_length_days integer NULL;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS max_requests_per_month integer NULL;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS auto_reset_date date NULL;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS auto_carry_forward_date date NULL;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS year_end_auto_reset_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS year_end_auto_carryover_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS year_end_process_on_month_day varchar(5) NOT NULL DEFAULT '01-01';
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS request_history_years integer NOT NULL DEFAULT 7;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS ledger_history_years integer NOT NULL DEFAULT 7;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS configuration jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS created_at timestamp with time zone NOT NULL DEFAULT NOW();
ALTER TABLE timeoff_configurations ADD COLUMN IF NOT EXISTS updated_at timestamp with time zone NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = 'timeoff_configurations_employer_id_key'
    ) THEN
        CREATE UNIQUE INDEX timeoff_configurations_employer_id_key ON timeoff_configurations(employer_id);
    END IF;
END
$$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("timeoff", "0008_timeoffapprovalstep_timeofftype_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_TABLE_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
