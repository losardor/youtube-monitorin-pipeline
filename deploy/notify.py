"""VENDORED COPY -- do not edit in place.

Source : gdelt-server:/data/home/infosphere/gdelt_dagster/gdelt_dagster/notify.py
md5    : c3e6e14c17932f4f1e066f5ac526893b
Copied : 2026-09-16

Copied rather than imported so the ytmon deployment does not depend on the
GDELT project's tree staying where it is, and so a change there cannot alter
ytmon's alerting silently. If the source changes and the change matters, copy
it again and update the md5 above.

Reads credentials and recipient from ~/.taiwa_notify_secrets
(TAIWA_SMTP_USER / TAIWA_SMTP_APP_PASSWORD / TAIWA_ALERT_TO), the same file
the GDELT jobs use. ytmon sets its own subject prefix and thread_key at the
call site; nothing below is modified.
"""

"""Notification transport for monitor + run-failure alerts — FAIL-SOFT email.

Sends via Gmail SMTP (smtp.gmail.com:587, STARTTLS — the proven path). Credentials
are read DIRECTLY from ~/.taiwa_notify_secrets (same pattern as the DB secrets) so
the module is testable standalone; matching env vars override the file if set.

FAIL-SOFT contract: email is best-effort. A missing/placeholder app password OR any
send exception is swallowed — logged as WARNING and recorded in a durable alert log
under DAGSTER_HOME (alerts.log) — so a mail outage can NEVER take down the daemon.
Every alert is appended to alerts.log regardless of email outcome (permanent audit
trail). The app password is redacted in every log path.

THREADING (thread_key): callers may pass a thread_key so related alerts collapse
into one mail conversation instead of one conversation per message. See the
"alert threading" block below for why it is built the way it is. Threading is
cosmetic and strictly subordinate to the fail-soft contract: nothing about header
construction may prevent or abort a send. thread_key=None reproduces the exact
headers this module emitted before threading existed.
"""
import json
import logging
import os
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email import policy as _email_policy
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

log = logging.getLogger(__name__)

SECRETS_PATH = os.path.expanduser("~/.taiwa_notify_secrets")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
_SECRET_KEYS = ("TAIWA_SMTP_USER", "TAIWA_SMTP_APP_PASSWORD", "TAIWA_ALERT_TO")
# App-password values that mean "not configured" — trigger the fail-soft skip.
_PLACEHOLDERS = {"", "changeme", "xxxx", "xxxxxxxxxxxxxxxx", "placeholder", "your-app-password"}

# --------------------------------------------------------------------------
# alert threading
# --------------------------------------------------------------------------
# Measured 2026-08-27, both directions:
#   * when the client sets NO Message-ID, smtp.gmail.com assigns one
#     ("Message-ID: <...@mx.google.com>") and smtplib never reports it back;
#   * when the client DOES set one, Gmail preserves it verbatim.
# Either way, capture-and-reference threading is the wrong shape here: the FIRST
# alert of a conversation has no prior message to reference, so it would still need
# a synthetic root, and remembering the previous id across processes would require
# persistent state that the monitor (fresh process per timer fire) and the daemon do
# not share.
#
# Instead every alert sharing a thread_key points In-Reply-To and References at the
# SAME deterministic synthetic anchor, including the first alert. No message with
# that ID ever exists; clients group on the shared References root regardless. This
# keeps the whole mechanism STATELESS — no thread-state file, no locking, no
# read/write failure mode.
#
# Gmail additionally groups on byte-identical subjects — measured, not assumed: two
# threads in the production mailbox each collapsed five alerts that shared the
# subject "[TAIWA ERROR] Dagster run FAILED: m2_slot_job" and carried NO References
# or In-Reply-To header at all. That is why callers pass a FIXED subject per alert
# class and move all varying detail (slot, lag, counts, timestamps) into the body.
# Behaviour in non-Gmail clients: # not measured.
THREAD_DOMAIN = "infosphere.taiwa"
_THREAD_KEY_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")

# Python's default header registry maps Message-ID to MessageIDHeader but leaves
# In-Reply-To and References as UNSTRUCTURED headers. An unstructured header too
# long for the fold width with no internal whitespace to fold at gets RFC-2047
# encoded-word encoded, which destroys the message-id. Measured 2026-08-27 on
# CPython 3.10.12: the 84-char runfail anchor came out as
#     In-Reply-To: =?utf-8?q?=3Ctaiwa=2Ealerts=2Erunfail=2Egdelt=5Fdownload...?=
# while the 49-char wm-lag anchor was emitted intact — so the breakage is
# length-dependent and would have silently hit only the longest-keyed (and
# highest-volume) alert class. Mapping both headers to MessageIDHeader emits them
# verbatim on one line. Built defensively: if this policy cannot be constructed
# the module must still import, because every alert path depends on it.
try:
    from email.headerregistry import HeaderRegistry as _HeaderRegistry
    from email.headerregistry import MessageIDHeader as _MessageIDHeader

    _HEADER_REGISTRY = _HeaderRegistry()
    _HEADER_REGISTRY.map_to_type("in-reply-to", _MessageIDHeader)
    _HEADER_REGISTRY.map_to_type("references", _MessageIDHeader)
    _MSG_POLICY = _email_policy.default.clone(header_factory=_HEADER_REGISTRY)
except Exception as _e:  # noqa: BLE001 — never let this break module import
    _MSG_POLICY = None
    log.warning("notify: message-id header policy unavailable (%s: %s); "
                "threading headers may be encoded-word folded", type(_e).__name__, _e)


def thread_anchor(thread_key) -> str:
    """Deterministic, RFC-5322-valid message-id for a thread key.

    Never sent as a real message — it exists only as the shared References root.
    Same key always yields the same anchor, which is what makes this stateless.
    """
    safe = _THREAD_KEY_UNSAFE.sub("-", str(thread_key)).strip("-")[:180] or "unkeyed"
    return "<taiwa.alerts.%s@%s>" % (safe, THREAD_DOMAIN)


def _build_message(subject: str, body: str, severity: str, thread_key,
                   user: str, to: str) -> EmailMessage:
    """Compose the alert message.

    Split out from notify() so header correctness can be verified offline with no
    SMTP connection and no credentials. Threading headers are wrapped in their own
    try/except: a bad thread_key degrades to an UNTHREADED message that still
    sends, rather than aborting the send.
    """
    msg = EmailMessage(policy=_MSG_POLICY) if _MSG_POLICY else EmailMessage()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = f"[TAIWA {severity}] {subject}"
    msg.set_content(body)
    if thread_key:
        try:
            anchor = thread_anchor(thread_key)
            msg["In-Reply-To"] = anchor
            msg["References"] = anchor
            # Unique per send. Gmail rewrites it; harmless, and correct for any
            # relay that does not.
            msg["Message-ID"] = make_msgid(domain=THREAD_DOMAIN)
        except Exception as e:  # noqa: BLE001 — threading must never block a send
            log.warning("notify: thread header construction failed (sending "
                        "unthreaded): %s: %s", type(e).__name__, e)
    return msg


def _alert_log_path() -> Path:
    """Durable alert log under DAGSTER_HOME (on /data); ~/dagster_home_prod fallback."""
    dh = os.environ.get("DAGSTER_HOME") or str(Path.home() / "dagster_home_prod")
    return Path(dh) / "alerts.log"


def _read_secrets() -> dict:
    """Direct read of ~/.taiwa_notify_secrets (KEY=VALUE lines); env overrides."""
    s = {}
    try:
        with open(SECRETS_PATH) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    s[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    for k in _SECRET_KEYS:
        if os.environ.get(k):
            s[k] = os.environ[k]
    return s


def _redact(text, pw: str) -> str:
    t = str(text)
    if pw:
        t = t.replace(pw, "<REDACTED_APP_PW>")
    return t


def _append_alert_log(record: dict) -> None:
    """Append one JSON line; never raise (this IS the fail-soft fallback)."""
    try:
        p = _alert_log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:  # noqa: BLE001 — audit log must never take down the caller
        log.warning("notify: could not write alert log: %s", e)


def notify(subject: str, body: str, severity: str = "ERROR", thread_key=None) -> dict:
    """Fail-soft alert: attempt email, always append to alerts.log, never raise.

    thread_key groups related alerts into one mail conversation (see the threading
    block above). It is OPTIONAL: thread_key=None sends exactly the headers this
    function sent before threading existed, so an un-migrated caller is unaffected.

    Returns the alert record with an added "email" outcome: sent|skipped|failed.
    """
    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "severity": severity,
        "subject": subject,
        "body": body,
    }
    if thread_key:
        # Recorded so a deploy can be verified from alerts.log alone, without
        # reaching into a mailbox.
        record["thread_key"] = str(thread_key)
        try:
            record["thread_anchor"] = thread_anchor(thread_key)
        except Exception as e:  # noqa: BLE001 — audit detail, never load-bearing
            log.warning("notify: thread anchor failed for %r: %s", thread_key, e)

    s = _read_secrets()
    user = s.get("TAIWA_SMTP_USER", "")
    pw = s.get("TAIWA_SMTP_APP_PASSWORD", "")
    to = s.get("TAIWA_ALERT_TO", "")

    # --- fail-soft precheck: no usable credentials -> skip email, log, return ---
    if not user or not to or pw.strip().lower() in _PLACEHOLDERS:
        record["email"] = "skipped"
        record["note"] = "email skipped: missing/placeholder credentials"
        log.warning("notify: %s (subject=%r)", record["note"], subject)
        _append_alert_log(record)
        return record

    # --- attempt real send; ANY failure is swallowed (fail-soft) ---
    try:
        msg = _build_message(subject, body, severity, thread_key, user, to)
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as srv:
            srv.starttls(context=ctx)
            srv.login(user, pw)
            refused = srv.send_message(msg)
        record["email"] = "sent"
        if refused:
            record["refused"] = {k: str(v) for k, v in refused.items()}
            log.warning("notify: recipients refused: %s", record["refused"])
        log.info("notify: email sent to %s (subject=%r)", to, subject)
    except Exception as e:  # noqa: BLE001 — email must never crash the daemon
        record["email"] = "failed"
        record["note"] = f"email send failed: {type(e).__name__}: {_redact(e, pw)}"
        log.warning("notify: %s", record["note"])

    _append_alert_log(record)
    return record
