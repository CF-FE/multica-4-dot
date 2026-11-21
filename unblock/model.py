"""Assess a coordinator-confirmed unblock record without performing actions."""

import re
from datetime import datetime, timezone


_SCOPE = ("instance_id", "workspace_id", "project_id", "issue_id")
_IDENTITY = (*_SCOPE, "thread_id", "coordinator_id")
_CORE_ROLES = ("coordinator", "sender", "project_lead", "acceptor", "g8", "disposition")
_RECORD_KEYS = ("ref", "actor_id", "at", "source_scope")
_TARGET_KEYS = ("target_id", "target_version")
_ACTION_KEYS = ("checkpoint_id", "request_id", "step")
_ACCEPTANCE_SCOPES = ("first_item", "issue")
_ROLE_KEY = re.compile(r"[a-z][a-z0-9_]{0,63}")
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?"
    r"(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)


def _object(value, path, required=(), optional=()):
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{path} must be a JSON object")
    missing = set(required) - value.keys()
    if missing:
        raise ValueError(f"{path} is missing {', '.join(sorted(missing))}")
    if optional is not None:
        extra = value.keys() - set(required) - set(optional)
        if extra:
            raise ValueError(f"{path} has unknown fields: {', '.join(sorted(extra))}")
    return value


def _text(value, path):
    if (not isinstance(value, str) or not value or value != value.strip()
            or any(ord(char) < 32 for char in value)):
        raise ValueError(f"{path} must be nonempty single-line text")
    return value


def _integer(value, path, minimum):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{path} must be an integer >= {minimum}")
    return value


def _choice(value, path, choices):
    if value not in choices:
        raise ValueError(f"{path} must be one of {', '.join(choices)}")
    return value


def _time(value, path):
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise ValueError(f"{path} must be an ISO timestamp with a timezone")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{path} must be a valid ISO timestamp") from exc


def _until(value, path, start):
    if value is None:
        return None
    end = _time(value, path)
    if end <= start:
        raise ValueError(f"{path} must be after the start")
    return end


def _index(registration):
    _object(registration, "registration", (*_IDENTITY, "roles", "required_evidence"), optional=None)
    identity = {key: _text(registration[key], f"registration.{key}") for key in _IDENTITY}
    required = registration["required_evidence"]
    if (not isinstance(required, list) or not required
            or any(not isinstance(key, str) or not _ROLE_KEY.fullmatch(key) or key in _CORE_ROLES
                   for key in required)
            or len(required) != len(set(required))):
        raise ValueError("registration.required_evidence must be a nonempty list of unique evidence role keys")
    entries = _object(registration["roles"], "registration.roles", ("coordinator",), optional=None)
    roles = {}
    for key, value in entries.items():
        path = f"registration.roles.{key}"
        if not _ROLE_KEY.fullmatch(key):
            raise ValueError(f"{path} is not a valid role key")
        _object(value, path, ("id", "name", "appointment_ref", "valid_from", "valid_until"))
        start = _time(value["valid_from"], f"{path}.valid_from")
        roles[key] = {
            **{field: _text(value[field], f"{path}.{field}") for field in ("id", "name", "appointment_ref")},
            "valid_from": start,
            "valid_until": _until(value["valid_until"], f"{path}.valid_until", start),
        }
    if roles["coordinator"]["id"] != identity["coordinator_id"]:
        raise ValueError("registration.roles.coordinator.id must match coordinator_id")
    return identity, roles, required


def _role_at(roles, key, when):
    role = roles.get(key)
    if role and role["valid_from"] <= when and (role["valid_until"] is None or when < role["valid_until"]):
        return role
    return None


def _signed_by(record, roles, key):
    return bool(record and record["actor_id"] == (_role_at(roles, key, record["at"]) or {}).get("id"))


def _record(value, path, identity, recorded_at, text_fields=(), other_fields=(), optional=(), *, action=False):
    _object(value, path, (*_RECORD_KEYS, *text_fields, *other_fields), (*optional, *_ACTION_KEYS) if action else optional)
    scope = _object(value["source_scope"], f"{path}.source_scope", _SCOPE, ("thread_id",) if action else ())
    for key in _SCOPE:
        if scope[key] != identity[key]:
            raise ValueError(f"{path}.source_scope.{key} does not match registration")
    result = dict(value)
    if action:
        if "thread_id" in scope:
            _text(scope["thread_id"], f"{path}.source_scope.thread_id")
        for field in value.keys() & (*_ACTION_KEYS, *_TARGET_KEYS):
            _text(value[field], f"{path}.{field}")
    for field in ("ref", "actor_id", *text_fields):
        result[field] = _text(value[field], f"{path}.{field}")
    result["at"] = _time(value["at"], f"{path}.at")
    if result["at"] > recorded_at:
        raise ValueError(f"{path}.at is after recorded_at")
    return result


def _people(snapshot, key, fields, required):
    entries = _object(snapshot.get(key, {}), f"snapshot.{key}", optional=required)
    people = {}
    for kind, entry in entries.items():
        path = f"snapshot.{key}.{kind}"
        _object(entry, path, fields)
        people[kind] = {field: _text(entry[field], f"{path}.{field}") for field in fields}
    return people


def _matches_target(record, target):
    return record["target_id"] == target["id"] and record["target_version"] == target["version"]


def _action_binding(record, target, thread_id, checkpoint_id, *, match_request=True):
    """Partial historical evidence can need reconciliation; evidence for another action cannot sign for this one."""
    if record is None:
        return "missing"
    original_thread = record["source_scope"].get("thread_id")
    expected = {"target_id": target["id"], "target_version": target["version"],
                "checkpoint_id": checkpoint_id, "step": target["step"]}
    if match_request:
        expected["request_id"] = target.get("request_id")
    if ((original_thread is not None and original_thread != thread_id)
            or any(record[key] != expected[key] for key in expected if key in record)):
        return "different_action"
    if original_thread is None or any(key not in record for key in _TARGET_KEYS):
        return "unbound"
    if (match_request and "request_id" in record) or ("checkpoint_id" in record and "step" in record):
        return "matched"
    return "unbound"


def _gate_status(record, roles, kind, target, when):
    if not record or when < record["at"]:
        return "missing"
    if not _matches_target(record, target):
        return "target_mismatch"
    if not _signed_by(record, roles, kind) or not _role_at(roles, kind, when):
        return "authority_unverified"
    if record["valid_until"] is not None and when >= record["valid_until"]:
        return "expired"
    return record["result"]


def _g8_records(snapshot, registration, parse):
    mailbox = registration.get("mailbox")
    job_id = None
    if "mailbox" in registration:
        _object(mailbox, "registration.mailbox", ("job_id",), optional=None)
        job_id = _text(mailbox["job_id"], "registration.mailbox.job_id")
    if "mailbox_result_version" in snapshot or mailbox is not None:
        _integer(snapshot.get("mailbox_result_version"), "snapshot.mailbox_result_version", 0)
    request = parse("g8_request", ("request_id",), optional=("job_id", "read_ack_ref", *_TARGET_KEYS), action=True)
    if request:
        if ("job_id" in request or job_id is not None) and (
            _text(request.get("job_id"), "snapshot.g8_request.job_id") != job_id
        ):
            raise ValueError("snapshot.g8_request.job_id does not match registration.mailbox")
        if "read_ack_ref" in request:
            _text(request["read_ack_ref"], "snapshot.g8_request.read_ack_ref")
    receipt = parse("g8_acceptance", ("request_id", "next_owner_id"),
                    optional=("next_check_at", "next_check_event"))
    if receipt:
        if not request or receipt["request_id"] != request["request_id"]:
            raise ValueError("snapshot.g8_acceptance.request_id must match g8_request")
        if receipt["at"] < request["at"]:
            raise ValueError("snapshot.g8_acceptance.at is before g8_request.at")
        if "next_check_at" in receipt:
            receipt["next_check_at"] = _until(receipt["next_check_at"], "snapshot.g8_acceptance.next_check_at",
                                              receipt["at"])
        if "next_check_event" in receipt:
            _text(receipt["next_check_event"], "snapshot.g8_acceptance.next_check_event")
        if receipt.get("next_check_at") is None and "next_check_event" not in receipt:
            raise ValueError("snapshot.g8_acceptance requires next_check_at or next_check_event")
    return request, receipt


def assess(registration: dict, snapshot: dict, now: datetime, *, pickup_source_verified=True) -> dict:
    """Validate a trusted registration and native-verified snapshot, then recommend a next step."""
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    now = now.astimezone(timezone.utc)
    identity, roles, required = _index(registration)
    _object(
        snapshot, "snapshot",
        (*_IDENTITY, "checkpoint_id", "revision", "recorded_at", "due_at", "target", "activity", "evidence"),
        ("decision_due_at", "next_check_event", "pickup", "contacts", "pursuers", "g8_request", "g8_acceptance",
         "execution", "acceptance", "disposition", "no_local_action", "mailbox_result_version"),
    )
    for key, value in identity.items():
        if snapshot[key] != value:
            raise ValueError(f"snapshot.{key} does not match registration")
    checkpoint_id = _text(snapshot["checkpoint_id"], "snapshot.checkpoint_id")
    if "checkpoint_id" in registration and checkpoint_id != _text(
        registration["checkpoint_id"], "registration.checkpoint_id"
    ):
        raise ValueError("snapshot.checkpoint_id does not match pinned registration")
    revision = _integer(snapshot["revision"], "snapshot.revision", 1)
    recorded_at = _time(snapshot["recorded_at"], "snapshot.recorded_at")
    if recorded_at > now:
        raise ValueError("snapshot.recorded_at is in the future")
    if not _role_at(roles, "coordinator", recorded_at) or not _role_at(roles, "coordinator", now):
        raise ValueError("snapshot.recorded_at and now must be covered by the coordinator appointment")
    due_at = None if snapshot["due_at"] is None else _time(snapshot["due_at"], "snapshot.due_at")
    next_check_event = snapshot.get("next_check_event")
    if next_check_event is not None:
        _text(next_check_event, "snapshot.next_check_event")
    decision_due_at = snapshot.get("decision_due_at")
    if decision_due_at is not None:
        decision_due_at = _time(decision_due_at, "snapshot.decision_due_at")
    no_local_action = snapshot.get("no_local_action", False)
    if type(no_local_action) is not bool:
        raise ValueError("snapshot.no_local_action must be a boolean")
    activity = _choice(snapshot["activity"], "snapshot.activity",
                       ("clear", "unknown", "in_flight", "artifact_unconfirmed"))

    target = _object(snapshot["target"], "snapshot.target", ("id", "version", "step", "acceptance_scope"),
                     ("request_id", "executor_id", "expected_evidence"))
    for field in ("id", "version", "step"):
        _text(target[field], f"snapshot.target.{field}")
    scope = _choice(target["acceptance_scope"], "snapshot.target.acceptance_scope", _ACCEPTANCE_SCOPES)
    if "request_id" in target:
        _text(target["request_id"], "snapshot.target.request_id")
    if "expected_evidence" in target:
        _text(target["expected_evidence"], "snapshot.target.expected_evidence")
    lead_id = roles.get("project_lead", {}).get("id")
    executor_id = target.get("executor_id", lead_id)
    if executor_id is not None:
        _text(executor_id, "snapshot.target.executor_id")

    def parse(key, text_fields=(), other_fields=(), optional=(), *, action=False):
        if key not in snapshot:
            return None
        return _record(snapshot[key], f"snapshot.{key}", identity, recorded_at, text_fields, other_fields,
                       optional, action=action)

    pickup = parse("pickup", optional=_TARGET_KEYS, action=True)
    leads = _people(snapshot, "contacts", ("name", "ref"), required)
    pursuers = _people(snapshot, "pursuers", ("id", "name", "ref"), required)
    observed = _object(snapshot["evidence"], "snapshot.evidence", optional=required)
    gates = {}
    for kind, value in observed.items():
        path = f"snapshot.evidence.{kind}"
        record = _record(value, path, identity, recorded_at, _TARGET_KEYS, ("valid_until", "result"))
        record["valid_until"] = _until(record["valid_until"], f"{path}.valid_until", record["at"])
        _choice(record["result"], f"{path}.result", ("confirmed", "rejected"))
        gates[kind] = record

    request, receipt = _g8_records(snapshot, registration, parse)
    request_binding = _action_binding(request, target, identity["thread_id"], checkpoint_id, match_request=False)
    request_verified = request_binding == "matched" and _signed_by(request, roles, "coordinator")
    receipt_verified = request_verified and _signed_by(receipt, roles, "g8")
    execution = parse("execution", (*_TARGET_KEYS, "run_id", "artifact_id"), action=True)
    acceptance = parse("acceptance", (*_TARGET_KEYS, "run_id", "artifact_id"), ("scope", "result"), action=True)
    if acceptance:
        _choice(acceptance["scope"], "snapshot.acceptance.scope", _ACCEPTANCE_SCOPES)
        _choice(acceptance["result"], "snapshot.acceptance.result", ("accepted", "rejected"))
    disposition = parse("disposition", (*_TARGET_KEYS, "reason"), ("status",), ("resume_condition",))
    if disposition:
        _choice(disposition["status"], "snapshot.disposition.status", ("paused", "cancelled"))
        if disposition["status"] == "paused" or "resume_condition" in disposition:
            _text(disposition.get("resume_condition"), "snapshot.disposition.resume_condition")
    disposed = _signed_by(disposition, roles, "disposition") and _matches_target(disposition, target)

    current_roles = {key: role for key in roles if (role := _role_at(roles, key, now))}
    evidence = {
        kind: {
            "status": _gate_status(gates.get(kind), roles, kind, target, now),
            "ref": gates.get(kind, {}).get("ref"),
            "authority": current_roles.get(kind, {}).get("id"),
            "contact": leads.get(kind),
            "pursuer_id": pursuers.get(kind, {}).get("id", identity["coordinator_id"]),
            "pursuer": pursuers.get(kind),
        }
        for kind in required
    }
    missing = [kind for kind, item in evidence.items() if item["status"] != "confirmed"]
    pickup_binding = _action_binding(pickup, target, identity["thread_id"], checkpoint_id)
    execution_binding = _action_binding(execution, target, identity["thread_id"], checkpoint_id)
    acceptance_binding = _action_binding(acceptance, target, identity["thread_id"], checkpoint_id)
    pickup_verified = (
        pickup_binding == "matched" and pickup_source_verified is True
        and pickup["actor_id"] == executor_id
        and (executor_id != lead_id or _signed_by(pickup, roles, "project_lead"))
    )
    picked_up = pickup_verified and (executor_id != lead_id or "project_lead" in current_roles)
    recovered = (
        pickup_verified
        and _signed_by(execution, roles, "project_lead")
        and pickup["at"] <= execution["at"]
        and execution_binding == "matched"
        and all(_gate_status(gates.get(kind), roles, kind, target, execution["at"]) == "confirmed"
                for kind in required)
    )
    acceptance_verified = (
        recovered and _signed_by(acceptance, roles, "acceptor")
        and acceptance_binding == "matched"
        and acceptance["at"] >= execution["at"]
        and (scope == "issue" or acceptance["scope"] == scope)
        and all(acceptance[key] == execution[key] for key in ("run_id", "artifact_id"))
    )
    accepted_scope = (
        acceptance["scope"] if acceptance_verified and acceptance["result"] == "accepted" else None
    )
    scope_accepted = accepted_scope == scope
    issue_accepted = scope_accepted and scope == "issue"
    g8_next_check_at = receipt.get("next_check_at") if receipt_verified else None
    effective_due_at = g8_next_check_at if receipt_verified else due_at
    checkpoint_due = effective_due_at is not None and effective_due_at <= now
    decision_overdue = decision_due_at is not None and decision_due_at <= now

    state = "recovered" if recovered else "blocked" if picked_up else "awaiting_pickup"
    action = "collect_evidence"
    owner = identity["coordinator_id"]
    g8_pending = False
    if disposed:
        action = "hold" if disposition["status"] == "paused" else "close_cancelled"
    elif disposition:
        action = "reconcile_disposition"
    elif activity != "clear":
        action = "reconcile_activity"
    elif recovered:
        owner = current_roles.get("acceptor", {}).get("id", owner)
        if scope_accepted:
            action = "record_issue_acceptance" if issue_accepted else "return_to_delivery"
        elif acceptance_verified and acceptance["result"] == "rejected":
            action = "review_affected_scope"
        else:
            action = "seek_acceptance"
    elif execution_binding in ("matched", "unbound") or acceptance_binding in ("matched", "unbound"):
        action = "reconcile_execution"
    elif not picked_up:
        action = "reconcile_pickup"
        if executor_id is not None:
            owner = current_roles.get("sender", {}).get("id", owner)
    elif not missing and "project_lead" not in current_roles:
        action = "request_g8_review"
        g8_pending = True
    elif not missing:
        action = "verify_and_resume"
        owner = current_roles["project_lead"]["id"]
    elif receipt_verified:
        action = "recheck_g8_plan" if checkpoint_due else "follow_g8_plan"
        owner = receipt["next_owner_id"]
    elif request_verified:
        action = "reconcile_g8_pickup"
        g8_pending = True
    elif decision_overdue or no_local_action or any(evidence[kind]["authority"] is None for kind in missing):
        action = "request_g8_review"
        g8_pending = True
    elif checkpoint_due:
        action = "recheck_evidence"

    return {
        **identity,
        "checkpoint_id": checkpoint_id,
        "revision": revision,
        "state": state,
        "next_action": action,
        "owner_id": owner,
        "g8_pending": g8_pending,
        "g8_status": (
            "accepted" if receipt_verified else "requested" if request_verified
            else "unverified" if request else "not_requested"
        ),
        "g8_request_ref": request["ref"] if request else None,
        "g8_acceptance_ref": receipt["ref"] if receipt_verified else None,
        "g8_next_check_at": g8_next_check_at.isoformat() if g8_next_check_at else None,
        "g8_next_check_event": receipt.get("next_check_event") if receipt_verified else None,
        "checkpoint_due": checkpoint_due,
        "next_check_at": effective_due_at.isoformat() if effective_due_at else None,
        "next_check_event": receipt.get("next_check_event") if receipt_verified else next_check_event,
        "decision_overdue": decision_overdue,
        "notification_open": not disposed and not scope_accepted,
        "disposition": disposition["status"] if disposed else "unverified" if disposition else "active",
        "disposition_ref": disposition["ref"] if disposition else None,
        "resume_condition": disposition.get("resume_condition") if disposed else None,
        "target": dict(target),
        "evidence": evidence,
        "executor_id": executor_id,
        "pickup_status": "accepted" if picked_up or recovered else "awaiting_pickup",
        "pickup_binding": pickup_binding,
        "pickup_ref": pickup["ref"] if picked_up or recovered else None,
        "recorded_pickup_ref": pickup["ref"] if pickup else None,
        "activity": activity,
        "execution_ref": execution["ref"] if execution else None,
        "acceptance_ref": acceptance["ref"] if acceptance_verified else None,
        "acceptance_scope": acceptance["scope"] if acceptance_verified else None,
        "accepted_scope": accepted_scope,
        "issue_accepted": issue_accepted,
    }
