-- Run once as the Multica database owner. Supply a SCRAM verifier, never a plaintext password.
\set ON_ERROR_STOP on
BEGIN;
CREATE ROLE multica_report_view_owner NOLOGIN NOINHERIT;
CREATE ROLE multica_report_reader LOGIN NOINHERIT CONNECTION LIMIT 4
  PASSWORD :'reader_verifier';
ALTER ROLE multica_report_reader SET default_transaction_read_only = on;
ALTER ROLE multica_report_reader SET statement_timeout = '3s';
ALTER ROLE multica_report_reader SET timezone = 'UTC';

CREATE SCHEMA run_reporter AUTHORIZATION multica_report_view_owner;
CREATE TABLE run_reporter.registrations (
    issue_id uuid NOT NULL,
    run_id uuid PRIMARY KEY
);
ALTER TABLE run_reporter.registrations OWNER TO multica_report_view_owner;

GRANT USAGE ON SCHEMA public TO multica_report_view_owner;
GRANT SELECT (id, workspace_id, project_id) ON public.issue TO multica_report_view_owner;
GRANT SELECT (id, workspace_id) ON public.project, public.agent TO multica_report_view_owner;
GRANT SELECT (id, issue_id, agent_id, status, completed_at, error, escalation_for_task_id, started_at)
    ON public.agent_task_queue TO multica_report_view_owner;

CREATE VIEW run_reporter.issues WITH (security_barrier = true) AS
SELECT i.id, i.workspace_id, i.project_id
FROM public.issue i
JOIN public.project p ON p.id = i.project_id AND p.workspace_id = i.workspace_id
WHERE i.workspace_id = :'workspace_id'::uuid AND i.project_id = :'project_id'::uuid
  AND EXISTS (SELECT 1 FROM run_reporter.registrations w WHERE w.issue_id = i.id);

CREATE VIEW run_reporter.runs WITH (security_barrier = true) AS
SELECT r.id, r.issue_id, i.workspace_id, r.status, r.completed_at, coalesce(r.error <> '', false) AS has_error
FROM run_reporter.registrations w
JOIN run_reporter.issues i ON i.id = w.issue_id
JOIN public.agent_task_queue r ON r.id = w.run_id AND r.issue_id = i.id
JOIN public.agent a ON a.id = r.agent_id AND a.workspace_id = i.workspace_id
WHERE NOT (r.escalation_for_task_id IS NOT NULL AND r.started_at IS NULL
           AND r.status IN ('deferred', 'cancelled'));

ALTER VIEW run_reporter.issues OWNER TO multica_report_view_owner;
ALTER VIEW run_reporter.runs OWNER TO multica_report_view_owner;
GRANT USAGE ON SCHEMA run_reporter TO multica_report_reader;
GRANT SELECT ON run_reporter.issues, run_reporter.runs TO multica_report_reader;
COMMIT;
