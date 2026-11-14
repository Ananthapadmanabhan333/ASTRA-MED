# Database schema

Generated from `backend/app/db/models.py` (SQLAlchemy). The schema is owned by Alembic
(`backend/migrations`: `0001` baseline for phases 1–6, `0002` crew self-check). Every measurement row
carries `data_source` (`simulated`, `self_reported`, or the NASA category on space tables).

## Crew and monitoring (phases 1-2)

### `astronauts`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | String(16) | no | PK |
| name | String(120) | no |  |
| role | String(80) | no |  |
| specialty | String(160) | no |  |
| age | Integer | no |  |
| sex | String(8) | no |  |
| height_cm | Integer | no |  |
| mass_kg | Float | no |  |
| blood_type | String(4) | no |  |
| prior_career_dose_msv | Float | no |  |
| sleep_start_hour | Float | no |  |
| sleep_target_hours | Float | no |  |
| exercise_target_minutes | Integer | no |  |
| baseline | JSON | no |  |
| data_source | String(16) | no |  |

### `vital_samples`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | BigInteger | no | PK |
| astronaut_id | String(16) | no | → `astronauts.id` (on delete cascade) |
| ts | UTCDateTime | no |  |
| heart_rate | Float | no |  |
| spo2 | Float | no |  |
| systolic | Float | no |  |
| diastolic | Float | no |  |
| temperature_c | Float | no |  |
| respiratory_rate | Float | no |  |
| activity_state | String(16) | no |  |
| activity_met | Float | no |  |
| rhythm | String(16) | no |  |
| hrv_rmssd_ms | Float | yes |  |
| scenario | String(40) | yes |  |
| data_source | String(16) | no |  |

Indexes and constraints: index `ix_vitals_astronaut_ts` (astronaut_id, ts).

### `sleep_sessions`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | BigInteger | no | PK |
| astronaut_id | String(16) | no | → `astronauts.id` (on delete cascade) |
| night | Date | no |  |
| scheduled_start | UTCDateTime | no |  |
| scheduled_end | UTCDateTime | no |  |
| start | UTCDateTime | no |  |
| end | UTCDateTime | no |  |
| duration_hours | Float | no |  |
| efficiency_pct | Float | no |  |
| data_source | String(16) | no |  |

Indexes and constraints: unique `uq_sleep_night` (astronaut_id, night).

### `radiation_doses`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | BigInteger | no | PK |
| astronaut_id | String(16) | no | → `astronauts.id` (on delete cascade) |
| day | Date | no |  |
| mission_day | Integer | no |  |
| dose_msv | Float | no |  |
| solar_particle_event | Boolean | no |  |
| data_source | String(16) | no |  |

Indexes and constraints: unique `uq_dose_day` (astronaut_id, day).

### `alerts`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | String(32) | no | PK |
| astronaut_id | String(16) | no | → `astronauts.id` (on delete cascade) |
| rule_key | String(48) | no |  |
| category | String(16) | no |  |
| metric | String(32) | no |  |
| direction | String(8) | no |  |
| severity | String(16) | no |  |
| status | String(16) | no |  |
| title | String(120) | no |  |
| message | Text | no |  |
| unit | String(16) | no |  |
| trigger_value | Float | no |  |
| threshold_value | Float | yes |  |
| peak_value | Float | no |  |
| activity_state | String(16) | yes |  |
| scenario | String(40) | yes |  |
| opened_at | UTCDateTime | no |  |
| updated_at | UTCDateTime | no |  |
| condition_cleared_at | UTCDateTime | yes |  |
| acknowledged_at | UTCDateTime | yes |  |
| resolved_at | UTCDateTime | yes |  |
| operator_note | Text | yes |  |
| data_source | String(16) | no |  |

Indexes and constraints: index `ix_alerts_astronaut_id` (astronaut_id); index `ix_alerts_status_opened` (status, opened_at).

### `simulation_events`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | String(40) | no | PK |
| scenario | String(40) | no |  |
| astronaut_id | String(16) | yes | → `astronauts.id` (on delete cascade) |
| intensity | Float | no |  |
| started_at | UTCDateTime | no |  |
| ends_at | UTCDateTime | no |  |
| cancelled_at | UTCDateTime | yes |  |
| triggered_by | String(16) | no |  |

Indexes and constraints: index `ix_simulation_events_astronaut_id` (astronaut_id); index `ix_simulation_events_started_at` (started_at).

## Space environment (phase 4)

### `space_weather_events`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | BigInteger | no | PK |
| source_id | String(32) | no |  |
| event_type | String(16) | no |  |
| external_id | String(128) | no |  |
| category | String(16) | no |  |
| start_time | UTCDateTime | no |  |
| peak_time | UTCDateTime | yes |  |
| end_time | UTCDateTime | yes |  |
| classification | Text | yes |  |
| scale | String(8) | yes |  |
| severity | Integer | yes |  |
| magnitude | Float | yes |  |
| magnitude_unit | String(64) | yes |  |
| location | String(64) | yes |  |
| description | Text | yes |  |
| instruments | JSON | no |  |
| linked_ids | JSON | no |  |
| notification_ids | JSON | no |  |
| model_derived | Boolean | no |  |
| link | String(255) | yes |  |
| version | Integer | no |  |
| submitted_at | UTCDateTime | yes |  |
| retrieved_at | UTCDateTime | no |  |
| endpoint | String(64) | no |  |
| raw | JSON | no |  |

Indexes and constraints: index `ix_swx_start` (start_time); index `ix_swx_type_start` (event_type, start_time); unique `uq_swx_event` (source_id, external_id).

### `space_notifications`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | BigInteger | no | PK |
| source_id | String(32) | no |  |
| message_id | String(64) | no |  |
| message_type | String(32) | no |  |
| issue_time | UTCDateTime | no |  |
| url | String(255) | yes |  |
| summary | Text | yes |  |
| body | Text | no |  |
| retrieved_at | UTCDateTime | no |  |
| endpoint | String(64) | no |  |

Indexes and constraints: index `ix_swx_notification_time` (issue_time); unique `uq_swx_notification` (source_id, message_id).

### `osdr_studies`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| accession | String(32) | no | PK |
| title | Text | no |  |
| description | Text | yes |  |
| organism | String(255) | yes |  |
| project_type | String(64) | yes |  |
| flight_program | String(128) | yes |  |
| mission_name | String(128) | yes |  |
| mission_start | UTCDateTime | yes |  |
| mission_end | UTCDateTime | yes |  |
| assay_type | String(255) | yes |  |
| material_type | String(255) | yes |  |
| platform | String(128) | yes |  |
| release_date | UTCDateTime | yes |  |
| data_source_accession | String(64) | yes |  |
| link | String(255) | no |  |
| topics | JSON | no |  |
| retrieved_at | UTCDateTime | no |  |
| endpoint | String(64) | no |  |

### `data_sync_runs`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | BigInteger | no | PK |
| source_id | String(32) | no |  |
| task | String(160) | no |  |
| started_at | UTCDateTime | no |  |
| finished_at | UTCDateTime | yes |  |
| status | String(16) | no |  |
| endpoint | String(64) | yes |  |
| records_received | Integer | no |  |
| records_new | Integer | no |  |
| records_updated | Integer | no |  |
| duplicates | Integer | no |  |
| invalid | Integer | no |  |
| error | Text | yes |  |
| detail | JSON | no |  |

Indexes and constraints: index `ix_sync_source_started` (source_id, started_at).

## Medical decision support and security (phase 5)

### `twin_daily`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | BigInteger | no | PK |
| astronaut_id | String(16) | no | → `astronauts.id` (on delete cascade) |
| day | Date | no |  |
| mission_day | Integer | no |  |
| stage | String(32) | no |  |
| basis | String(16) | no |  |
| complete | Boolean | no |  |
| metrics | JSON | no |  |
| activity | JSON | no |  |
| sleep | JSON | yes |  |
| radiation | JSON | yes |  |
| events | JSON | no |  |
| coverage | JSON | no |  |
| computed_at | UTCDateTime | no |  |
| data_source | String(16) | no |  |

Indexes and constraints: index `ix_twin_daily_astronaut_id` (astronaut_id); unique `uq_twin_day` (astronaut_id, day).

### `emergency_runs`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | String(32) | no | PK |
| scenario | String(48) | no |  |
| label | String(120) | no |  |
| astronaut_id | String(16) | yes | → `astronauts.id` (on delete cascade) |
| severity | String(16) | no |  |
| intensity | Float | no |  |
| duration_s | Integer | no |  |
| started_at | UTCDateTime | no |  |
| ends_at | UTCDateTime | no |  |
| cancelled_at | UTCDateTime | yes |  |
| created_by | String(64) | yes |  |
| components | JSON | no |  |
| overlay | JSON | no |  |
| analyses | JSON | no |  |
| data_source | String(16) | no |  |

Indexes and constraints: index `ix_emergency_runs_astronaut_id` (astronaut_id); index `ix_emergency_started` (started_at).

### `incident_reports`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | String(32) | no | PK |
| title | String(200) | no |  |
| astronaut_id | String(16) | no | → `astronauts.id` (on delete cascade) |
| alert_id | String(32) | yes |  |
| run_id | String(32) | yes |  |
| occurred_at | UTCDateTime | no |  |
| created_at | UTCDateTime | no |  |
| updated_at | UTCDateTime | no |  |
| created_by | String(64) | no |  |
| review_status | String(24) | no |  |
| review_history | JSON | no |  |
| content | JSON | no |  |
| content_sha256 | String(64) | no |  |
| data_source | String(16) | no |  |

Indexes and constraints: index `ix_incident_reports_astronaut_id` (astronaut_id); index `ix_report_created` (created_at).

### `users`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | String(32) | no | PK |
| username | String(64) | no |  |
| display_name | String(120) | no |  |
| role | String(32) | no |  |
| password_hash | String(255) | no |  |
| active | Boolean | no |  |
| created_at | UTCDateTime | no |  |
| password_changed_at | UTCDateTime | no |  |
| last_login_at | UTCDateTime | yes |  |
| failed_logins | Integer | no |  |
| locked_until | UTCDateTime | yes |  |

Indexes and constraints: index `ix_users_username` (username).

### `auth_sessions`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | String(32) | no | PK |
| token_hash | String(64) | no |  |
| user_id | String(32) | no | → `users.id` (on delete cascade) |
| csrf_token | String(64) | no |  |
| created_at | UTCDateTime | no |  |
| expires_at | UTCDateTime | no |  |
| last_seen_at | UTCDateTime | no |  |
| revoked_at | UTCDateTime | yes |  |
| ip | String(64) | yes |  |
| user_agent | String(200) | yes |  |

Indexes and constraints: index `ix_auth_sessions_token_hash` (token_hash); index `ix_auth_sessions_user_id` (user_id).

### `audit_log`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | BigInteger | no | PK |
| ts | UTCDateTime | no |  |
| user_id | String(32) | yes |  |
| username | String(64) | yes |  |
| role | String(32) | yes |  |
| action | String(64) | no |  |
| resource_type | String(48) | yes |  |
| resource_id | String(128) | yes |  |
| outcome | String(16) | no |  |
| status_code | Integer | yes |  |
| ip | String(64) | yes |  |
| request_id | String(32) | yes |  |
| detail | JSON | no |  |

Indexes and constraints: index `ix_audit_ts` (ts); index `ix_audit_user_ts` (user_id, ts).

## Mission control (phase 6)

### `mission_events`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | String(20) | no | PK |
| fingerprint | String(40) | no |  |
| source | String(32) | no |  |
| kind | String(48) | no |  |
| category | String(32) | no |  |
| severity | String(16) | no |  |
| priority | Integer | no |  |
| priority_score | Float | no |  |
| title | String(200) | no |  |
| summary | Text | yes |  |
| astronaut_id | String(16) | yes |  |
| context | String(16) | no |  |
| simulation_id | String(32) | yes |  |
| data_origin | String(16) | no |  |
| experimental | Boolean | no |  |
| confidence | Float | yes |  |
| ref_type | String(32) | yes |  |
| ref_id | String(96) | yes |  |
| occurred_at | UTCDateTime | no |  |
| received_at | UTCDateTime | no |  |
| last_seen_at | UTCDateTime | no |  |
| clock_skew_s | Float | yes |  |
| occurrences | Integer | no |  |
| payload | JSON | no |  |

Indexes and constraints: index `ix_mevents_astronaut` (astronaut_id, occurred_at); index `ix_mevents_context_sim` (context, simulation_id, occurred_at); index `ix_mevents_fingerprint` (fingerprint, last_seen_at); index `ix_mevents_occurred` (occurred_at).

### `mission_alerts`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | String(20) | no | PK |
| source | String(32) | no |  |
| source_ref | String(96) | no |  |
| event_id | String(20) | yes |  |
| astronaut_id | String(16) | yes |  |
| context | String(16) | no |  |
| simulation_id | String(32) | yes |  |
| data_origin | String(16) | no |  |
| category | String(32) | no |  |
| classification | String(32) | no |  |
| severity | String(16) | no |  |
| priority | Integer | no |  |
| title | String(200) | no |  |
| summary | Text | yes |  |
| status | String(16) | no |  |
| created_at | UTCDateTime | no |  |
| updated_at | UTCDateTime | no |  |
| received_at | UTCDateTime | no |  |
| measurements | JSON | no |  |
| explanation | JSON | no |  |
| confidence | Float | yes |  |
| confidence_level | String(16) | yes |  |
| uncertainty | JSON | no |  |
| correlations | JSON | no |  |
| condition_cleared_at | UTCDateTime | yes |  |
| acknowledged_at | UTCDateTime | yes |  |
| acknowledged_by | String(64) | yes |  |
| ack_note | Text | yes |  |
| resolved_at | UTCDateTime | yes |  |
| resolved_by | String(64) | yes |  |
| resolution_notes | Text | yes |  |
| occurrences | Integer | no |  |

Indexes and constraints: index `ix_malerts_astronaut` (astronaut_id, created_at); index `ix_malerts_context_sim` (context, simulation_id); index `ix_malerts_status_created` (status, created_at); unique `uq_malert_source_ref` (source, source_ref).

### `mission_alert_actions`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | BigInteger | no | PK |
| alert_id | String(20) | no |  |
| ts | UTCDateTime | no |  |
| action | String(24) | no |  |
| from_status | String(16) | yes |  |
| to_status | String(16) | yes |  |
| actor | String(64) | no |  |
| actor_role | String(32) | yes |  |
| note | Text | yes |  |
| detail | JSON | no |  |

Indexes and constraints: index `ix_malert_actions_alert` (alert_id, ts).

### `mission_simulations`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | String(16) | no | PK |
| name | String(120) | no |  |
| preset | String(48) | yes |  |
| crew | JSON | no |  |
| status | String(16) | no |  |
| speed | Float | no |  |
| seed | Integer | no |  |
| sim_start | UTCDateTime | no |  |
| sim_time | UTCDateTime | no |  |
| sim_end | UTCDateTime | no |  |
| wall_started_at | UTCDateTime | no |  |
| wall_updated_at | UTCDateTime | no |  |
| wall_ended_at | UTCDateTime | yes |  |
| created_by | String(64) | no |  |
| config | JSON | no |  |
| injections | JSON | no |  |
| analyses | JSON | no |  |
| stats | JSON | no |  |
| error | Text | yes |  |
| data_source | String(16) | no |  |

Indexes and constraints: index `ix_msim_started` (wall_started_at).

### `mission_sim_samples`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | BigInteger | no | PK |
| simulation_id | String(16) | no | → `mission_simulations.id` (on delete cascade) |
| astronaut_id | String(16) | no |  |
| ts | UTCDateTime | no |  |
| heart_rate | Float | no |  |
| spo2 | Float | no |  |
| systolic | Float | no |  |
| diastolic | Float | no |  |
| temperature_c | Float | no |  |
| respiratory_rate | Float | no |  |
| activity_state | String(16) | no |  |
| activity_met | Float | no |  |
| rhythm | String(16) | no |  |
| hrv_rmssd_ms | Float | yes |  |
| scenario | String(40) | yes |  |
| source | String(16) | no |  |
| data_source | String(16) | no |  |

Indexes and constraints: index `ix_simsamples_run_ast_ts` (simulation_id, astronaut_id, ts).

## Crew self-check (phase 8)

### `crew_self_reports`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | String(32) | no | PK |
| astronaut_id | String(16) | no | → `astronauts.id` (on delete cascade) |
| recorded_at | UTCDateTime | no |  |
| created_at | UTCDateTime | no |  |
| created_by | String(64) | no |  |
| glucose_mg_dl | Float | yes |  |
| glucose_context | String(16) | yes |  |
| mood | Integer | yes |  |
| symptoms_checked | Boolean | no |  |
| symptoms | JSON | no |  |
| note | Text | yes |  |
| data_source | String(16) | no |  |

Indexes and constraints: index `ix_selfreports_ast_recorded` (astronaut_id, recorded_at).

## Other tables

### `env_measurements`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| id | BigInteger | no | PK |
| mission | String(32) | no | → `env_missions.name` (on delete cascade) |
| quantity | String(32) | no |  |
| platform | String(16) | no |  |
| ts | UTCDateTime | no |  |
| resolution | String(8) | no |  |
| value | Float | no |  |
| min_value | Float | yes |  |
| max_value | Float | yes |  |
| n | Integer | no |  |
| unit | String(16) | no |  |
| approximate | Boolean | no |  |
| category | String(16) | no |  |

Indexes and constraints: index `ix_env_mission_quantity` (mission, quantity, platform, ts); unique `uq_env_measurement` (mission, quantity, platform, ts).

### `env_missions`

| Column | Type | Null | Key / reference |
| --- | --- | --- | --- |
| name | String(32) | no | PK |
| source_id | String(32) | no |  |
| title | String(255) | no |  |
| description | Text | yes |  |
| link | String(255) | yes |  |
| start_time | UTCDateTime | yes |  |
| end_time | UTCDateTime | yes |  |
| milestones | JSON | no |  |
| quality | JSON | no |  |
| retrieved_at | UTCDateTime | no |  |
| telemetry_synced_at | UTCDateTime | yes |  |
| radiation_synced_at | UTCDateTime | yes |  |
| space_weather_synced_at | UTCDateTime | yes |  |

## Relationships

- Every crew-scoped table references `astronauts.id` with `ON DELETE CASCADE`.
- `auth_sessions.user_id` → `users.id`; the audit log keeps usernames as text so entries survive account changes.
- `mission_sim_samples.simulation_id` → `mission_simulations.id` (cascade): the sandbox owns only its own rows.
- `mission_alerts` mirrors rule alerts by `(source, source_ref)` (unique); actions are kept in `mission_alert_actions`.
