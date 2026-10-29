-- Phase 12. Apply only after the owner approves Supabase provisioning.
-- Local SQLite IDs are stable source IDs; cloud receipt time never replaces source time.
create table public.devices (
  device_id text primary key check (device_id ~ '^[A-Za-z0-9]([A-Za-z0-9._-]{0,30}[A-Za-z0-9])?$'),
  owner_id uuid not null references auth.users(id) on delete restrict,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  unique (device_id, owner_id)
);
create index devices_owner_idx on public.devices (owner_id, device_id);

create table public.sensor_readings (
  device_id text not null,
  owner_id uuid not null,
  event_id text not null check (event_id ~ '^sensor:[1-9][0-9]*$'),
  source_id bigint not null check (source_id > 0),
  timestamp timestamptz not null,
  received_at timestamptz not null,
  cloud_received_at timestamptz not null default now(),
  accel_x double precision not null check (abs(accel_x) <= 1000),
  accel_y double precision not null check (abs(accel_y) <= 1000),
  accel_z double precision not null check (abs(accel_z) <= 1000),
  gyro_x double precision not null check (abs(gyro_x) <= 1000),
  gyro_y double precision not null check (abs(gyro_y) <= 1000),
  gyro_z double precision not null check (abs(gyro_z) <= 1000),
  primary key (device_id, event_id),
  unique (device_id, source_id),
  foreign key (device_id, owner_id) references public.devices(device_id, owner_id)
);
create index sensor_owner_time_idx on public.sensor_readings (owner_id, device_id, received_at desc);

create table public.activity_predictions (
  device_id text not null,
  owner_id uuid not null,
  event_id text not null check (event_id ~ '^prediction:[1-9][0-9]*$'),
  source_id bigint not null check (source_id > 0),
  activity_label text not null check (activity_label in ('IDLE', 'WALKING', 'RUNNING')),
  activity_code smallint not null check (
    (activity_label = 'IDLE' and activity_code = 0) or
    (activity_label = 'WALKING' and activity_code = 1) or
    (activity_label = 'RUNNING' and activity_code = 2)
  ),
  detection_method text not null check (
    (activity_label = 'IDLE' and detection_method = 'RULE_BASED') or
    (activity_label <> 'IDLE' and detection_method = 'DECISION_TREE')
  ),
  model_version text not null,
  window_start_timestamp timestamptz not null,
  window_end_timestamp timestamptz not null,
  created_at timestamptz not null,
  experimental boolean not null check (experimental = true),
  cloud_received_at timestamptz not null default now(),
  primary key (device_id, event_id),
  unique (device_id, source_id),
  foreign key (device_id, owner_id) references public.devices(device_id, owner_id)
);
create index prediction_owner_time_idx on public.activity_predictions (owner_id, device_id, window_end_timestamp desc);

create table public.device_status (
  device_id text primary key,
  owner_id uuid not null,
  backend_observed_at timestamptz not null,
  backend_online boolean not null,
  mqtt_connected boolean not null,
  inference_status text not null check (length(inference_status) <= 40),
  model_loaded boolean not null,
  last_sensor_received_at timestamptz,
  last_successful_sync_at timestamptz not null default now(),
  foreign key (device_id, owner_id) references public.devices(device_id, owner_id)
);
create index device_status_owner_idx on public.device_status (owner_id, device_id);

alter table public.devices enable row level security;
alter table public.sensor_readings enable row level security;
alter table public.activity_predictions enable row level security;
alter table public.device_status enable row level security;
revoke all on public.devices, public.sensor_readings, public.activity_predictions, public.device_status from anon, authenticated;
grant select on public.devices, public.sensor_readings, public.activity_predictions, public.device_status to authenticated;
grant all on public.devices, public.sensor_readings, public.activity_predictions, public.device_status to service_role;

create policy devices_owner_read on public.devices for select to authenticated
  using (owner_id = (select auth.uid()));
create policy sensor_owner_read on public.sensor_readings for select to authenticated
  using (owner_id = (select auth.uid()));
create policy prediction_owner_read on public.activity_predictions for select to authenticated
  using (owner_id = (select auth.uid()));
create policy status_owner_read on public.device_status for select to authenticated
  using (owner_id = (select auth.uid()));
