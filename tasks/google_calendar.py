"""
Google Calendar integration.

- Push: local schedule → Google when you press Update calendar.
- Pull: Google events → local busy blocks (automatic, throttled).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, time, timezone as dt_timezone
from typing import Optional
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from .models import (
    CalendarEventMapping,
    GoogleCalendarConnection,
    ImportedCalendarEvent,
    ScheduleSettings,
    Task,
)
from .services import build_schedule

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CALENDAR_TZ = ZoneInfo(getattr(settings, "GOOGLE_CALENDAR_TIMEZONE", "Asia/Jakarta"))
OWN_SOURCE = "health_aware_task_manager"


def google_oauth_configured() -> bool:
    return bool(
        getattr(settings, "GOOGLE_CLIENT_ID", "").strip()
        and getattr(settings, "GOOGLE_CLIENT_SECRET", "").strip()
    )


def get_redirect_uri(request=None) -> str:
    """
    OAuth redirect must match Google Cloud Console exactly.
    When a request is available, build from the current host (local vs
    PythonAnywhere). Otherwise fall back to GOOGLE_REDIRECT_URI / localhost.
    """
    if request is not None:
        host = request.get_host()
        host_name = host.split(":")[0].lower()
        scheme = request.scheme
        if request.is_secure() or host_name.endswith("pythonanywhere.com"):
            scheme = "https"
        return f"{scheme}://{host}/google/callback/"

    configured = getattr(settings, "GOOGLE_REDIRECT_URI", "").strip()
    return configured or "http://127.0.0.1:8000/google/callback/"


def _flow(redirect_uri: str | None = None):
    from google_auth_oauthlib.flow import Flow
    from pathlib import Path

    if not google_oauth_configured():
        raise RuntimeError(
            "Google OAuth is not configured. Place credentials.json in the project root "
            "or set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )

    creds_path = Path(getattr(settings, "GOOGLE_CREDENTIALS_FILE", "") or "")
    redirect_uri = redirect_uri or get_redirect_uri()
    # Explicit True: from_client_config() otherwise passes None and disables PKCE
    # generation, while some environments still send a challenge → invalid_grant.
    flow_kwargs = {"autogenerate_code_verifier": True}

    if creds_path.is_file():
        # Supports both "web" and "installed" Google client JSON downloads.
        flow = Flow.from_client_secrets_file(str(creds_path), scopes=SCOPES, **flow_kwargs)
    else:
        client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }
        flow = Flow.from_client_config(client_config, scopes=SCOPES, **flow_kwargs)

    flow.redirect_uri = redirect_uri
    return flow


def get_authorization_url(state: str, request=None):
    redirect_uri = get_redirect_uri(request)
    flow = _flow(redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    # PKCE: code_verifier must be reused on the callback token exchange.
    return auth_url, redirect_uri, flow.code_verifier


def exchange_code_for_tokens(
    code: str,
    redirect_uri: str | None = None,
    code_verifier: str | None = None,
) -> dict:
    flow = _flow(redirect_uri)
    # Don't generate a new verifier for token exchange — reuse the one from connect.
    flow.autogenerate_code_verifier = False
    flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    credentials = flow.credentials
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes or SCOPES),
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
    }


def _credentials_from_connection(connection: GoogleCalendarConnection):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    data = json.loads(connection.token_json)
    expiry = None
    if data.get("expiry"):
        expiry = datetime.fromisoformat(data["expiry"])
        if timezone.is_naive(expiry):
            expiry = timezone.make_aware(expiry, dt_timezone.utc)

    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id") or settings.GOOGLE_CLIENT_ID,
        client_secret=data.get("client_secret") or settings.GOOGLE_CLIENT_SECRET,
        scopes=data.get("scopes") or SCOPES,
    )
    if expiry:
        creds.expiry = expiry.replace(tzinfo=None) if expiry.tzinfo else expiry

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        connection.token_json = json.dumps({
            "token": creds.token,
            "refresh_token": creds.refresh_token or data.get("refresh_token"),
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or SCOPES),
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        })
        connection.save(update_fields=["token_json", "updated_at"])

    return creds


def _calendar_service(connection: GoogleCalendarConnection):
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=_credentials_from_connection(connection), cache_discovery=False)


def _aware(dt: datetime) -> datetime:
    """Treat naive schedule datetimes as local calendar timezone."""
    if timezone.is_naive(dt):
        return dt.replace(tzinfo=CALENDAR_TZ)
    return dt.astimezone(CALENDAR_TZ)


def _desired_slots(items: list, schedule_date: date) -> dict:
    """
    Stable keys (not wall-clock times) so a reshuffled slot PATCHes one event
    instead of delete+create for every item.
    """
    task_counts: dict[object, int] = {}
    break_counts: dict[str, int] = {}
    desired = {}
    for item in items:
        # Never push imported Google events back to Google.
        if item.get("is_external"):
            continue
        if item.get("is_break"):
            kind = item.get("break_type") or "break"
            n = break_counts.get(kind, 0)
            break_counts[kind] = n + 1
            key = f"{schedule_date.isoformat()}:break:{kind}:{n}"
        else:
            tid = item.get("task_id") if item.get("task_id") is not None else "anon"
            n = task_counts.get(tid, 0)
            task_counts[tid] = n + 1
            key = f"{schedule_date.isoformat()}:task:{tid}:{n}"
        desired[key] = item
    return desired


def _event_body(item: dict) -> dict:
    start = _aware(item["start_time"])
    end = _aware(item["end_time"])
    if item.get("is_break"):
        break_type = (item.get("break_type") or "break").title()
        summary = f"Break · {break_type}"
        description = item.get("break_description") or ""
        color_id = "5"  # banana / soft yellow
    else:
        summary = item.get("task_name") or "Task"
        bits = []
        if item.get("task_priority"):
            bits.append(f"Priority: {item['task_priority']}")
        if item.get("task_type"):
            bits.append(f"Type: {item['task_type']}")
        if item.get("task_description"):
            bits.append(item["task_description"])
        description = "\n".join(bits)
        color_id = "9"  # blueberry

    return {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": str(CALENDAR_TZ)},
        "end": {"dateTime": end.isoformat(), "timeZone": str(CALENDAR_TZ)},
        "colorId": color_id,
        "extendedProperties": {
            "private": {
                "man_source": "health_aware_task_manager",
            }
        },
    }


def _content_hash(body: dict) -> str:
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_own_pushed_event(event: dict, own_ids: set[str]) -> bool:
    if event.get("id") in own_ids:
        return True
    private = (event.get("extendedProperties") or {}).get("private") or {}
    return private.get("man_source") == OWN_SOURCE


def _parse_event_window(event: dict) -> tuple[datetime, datetime, bool, date] | None:
    """Return (start, end, is_all_day, schedule_date) in CALENDAR_TZ, or None."""
    start_info = event.get("start") or {}
    end_info = event.get("end") or {}

    if start_info.get("date") and end_info.get("date"):
        start_day = date.fromisoformat(start_info["date"])
        end_day = date.fromisoformat(end_info["date"])
        # Google all-day end is exclusive.
        start = datetime.combine(start_day, time(0, 0), tzinfo=CALENDAR_TZ)
        end = datetime.combine(end_day, time(0, 0), tzinfo=CALENDAR_TZ)
        return start, end, True, start_day

    start_raw = start_info.get("dateTime")
    end_raw = end_info.get("dateTime")
    if not start_raw or not end_raw:
        return None

    start = datetime.fromisoformat(start_raw.replace("Z", "+00:00")).astimezone(CALENDAR_TZ)
    end = datetime.fromisoformat(end_raw.replace("Z", "+00:00")).astimezone(CALENDAR_TZ)
    if end <= start:
        return None
    return start, end, False, start.date()


def pull_user_events(user, days_ahead: Optional[int] = None) -> dict:
    """
    Pull Google Calendar events into ImportedCalendarEvent (busy blocks).
    Skips events this app pushed. Triggers schedule_adjust when anything changed.
    """
    try:
        connection = GoogleCalendarConnection.objects.get(user=user)
    except GoogleCalendarConnection.DoesNotExist:
        return {"ok": False, "skipped": True, "reason": "not_connected"}

    if not connection.is_connected or not connection.pull_enabled:
        return {"ok": False, "skipped": True, "reason": "disabled"}

    if not google_oauth_configured():
        return {"ok": False, "skipped": True, "reason": "oauth_not_configured"}

    days = days_ahead if days_ahead is not None else int(
        getattr(settings, "GOOGLE_CALENDAR_SYNC_DAYS", 7)
    )
    today = datetime.now(CALENDAR_TZ).date()
    time_min = datetime.combine(today, time(0, 0), tzinfo=CALENDAR_TZ)
    time_max = datetime.combine(
        today + timedelta(days=days + 1),
        time(0, 0),
        tzinfo=CALENDAR_TZ,
    )

    try:
        service = _calendar_service(connection)
        calendar_id = connection.calendar_id or "primary"
        own_ids = set(
            CalendarEventMapping.objects.filter(user=user).values_list("google_event_id", flat=True)
        )

        events: list[dict] = []
        page_token = None
        while True:
            kwargs = {
                "calendarId": calendar_id,
                "timeMin": time_min.isoformat(),
                "timeMax": time_max.isoformat(),
                "singleEvents": True,
                "orderBy": "startTime",
                "showDeleted": True,
                "maxResults": 250,
            }
            if page_token:
                kwargs["pageToken"] = page_token
            result = _execute_with_retry(service.events().list(**kwargs))
            events.extend(result.get("items") or [])
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        seen_ids: set[str] = set()
        created = updated = deleted = skipped = 0
        changed_dates: set[date] = set()

        for event in events:
            event_id = event.get("id")
            if not event_id:
                continue
            if _is_own_pushed_event(event, own_ids):
                skipped += 1
                continue

            status = (event.get("status") or "confirmed").lower()
            if status == "cancelled":
                removed, _ = ImportedCalendarEvent.objects.filter(
                    user=user, google_event_id=event_id
                ).delete()
                if removed:
                    deleted += removed
                    # Approximate: mark today window dirty
                    changed_dates.add(today)
                continue

            # Free / transparent events should not block the schedule.
            if (event.get("transparency") or "").lower() == "transparent":
                removed, _ = ImportedCalendarEvent.objects.filter(
                    user=user, google_event_id=event_id
                ).delete()
                if removed:
                    deleted += removed
                continue

            parsed = _parse_event_window(event)
            if not parsed:
                continue
            start_at, end_at, is_all_day, schedule_date = parsed
            seen_ids.add(event_id)

            summary = (event.get("summary") or "Google event")[:500]
            description = event.get("description") or ""
            etag = event.get("etag") or ""
            digest = _content_hash({
                "summary": summary,
                "start": start_at.isoformat(),
                "end": end_at.isoformat(),
                "status": status,
                "all_day": is_all_day,
            })

            existing = ImportedCalendarEvent.objects.filter(
                user=user, google_event_id=event_id
            ).first()
            if existing and existing.content_hash == digest:
                skipped += 1
                continue

            _, was_created = ImportedCalendarEvent.objects.update_or_create(
                user=user,
                google_event_id=event_id,
                defaults={
                    "calendar_id": calendar_id,
                    "summary": summary,
                    "description": description,
                    "start_at": start_at,
                    "end_at": end_at,
                    "is_all_day": is_all_day,
                    "status": status,
                    "schedule_date": schedule_date,
                    "etag": etag[:128],
                    "content_hash": digest,
                },
            )
            changed_dates.add(schedule_date)
            if was_created:
                created += 1
            else:
                updated += 1

        # Drop stale imports in the pull window that Google no longer returns.
        stale_qs = ImportedCalendarEvent.objects.filter(
            user=user,
            schedule_date__gte=today,
            schedule_date__lte=today + timedelta(days=days),
        ).exclude(google_event_id__in=seen_ids)
        for stale in stale_qs:
            changed_dates.add(stale.schedule_date)
            stale.delete()
            deleted += 1

        connection.last_pulled_at = timezone.now()
        connection.last_pull_ok = True
        connection.last_pull_error = ""
        connection.save(update_fields=[
            "last_pulled_at", "last_pull_ok", "last_pull_error", "updated_at",
        ])

        adjust = {"unpinned": 0}
        if changed_dates:
            from .schedule_adjust import on_constraints_changed
            adjust = on_constraints_changed(user, sorted(changed_dates), reason="google_pull")

        return {
            "ok": True,
            "created": created,
            "updated": updated,
            "deleted": deleted,
            "skipped": skipped,
            "changed": bool(changed_dates),
            "adjust": adjust,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Google Calendar pull failed for user %s", user.pk)
        connection.last_pulled_at = timezone.now()
        connection.last_pull_ok = False
        connection.last_pull_error = str(exc)[:2000]
        connection.save(update_fields=[
            "last_pulled_at", "last_pull_ok", "last_pull_error", "updated_at",
        ])
        return {"ok": False, "error": str(exc)}


def maybe_pull_user_events(user, *, min_interval_seconds: Optional[int] = None) -> dict:
    """Pull if connected and last pull is older than the interval (default 60s)."""
    interval = min_interval_seconds
    if interval is None:
        interval = int(getattr(settings, "GOOGLE_CALENDAR_PULL_INTERVAL_SECONDS", 60) or 60)

    try:
        connection = GoogleCalendarConnection.objects.get(user=user)
    except GoogleCalendarConnection.DoesNotExist:
        return {"ok": False, "skipped": True, "reason": "not_connected"}

    if not connection.is_connected or not connection.pull_enabled:
        return {"ok": False, "skipped": True, "reason": "disabled"}

    if connection.last_pulled_at:
        age = (timezone.now() - connection.last_pulled_at).total_seconds()
        if age < max(5, interval):
            return {"ok": True, "skipped": True, "reason": "fresh", "age": age}

    return pull_user_events(user)


def _execute_with_retry(request, *, retries: int = 4):
    """Retry Calendar API calls on rate-limit / transient errors."""
    import time
    from googleapiclient.errors import HttpError

    delay = 1.5
    last_exc = None
    for attempt in range(retries):
        try:
            return request.execute()
        except HttpError as exc:
            last_exc = exc
            status = getattr(exc.resp, "status", None)
            if status not in (403, 429, 500, 503) or attempt == retries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 20)
    raise last_exc  # pragma: no cover


def sync_user_schedule(user, days_ahead: Optional[int] = None) -> dict:
    """
    Rebuild schedule for today..today+N and upsert only changed Google events.
    Unchanged slots (same content hash) skip the API entirely.
    """
    try:
        connection = GoogleCalendarConnection.objects.get(user=user)
    except GoogleCalendarConnection.DoesNotExist:
        return {"ok": False, "skipped": True, "reason": "not_connected"}

    if not connection.is_connected or not connection.sync_enabled:
        return {"ok": False, "skipped": True, "reason": "disabled"}

    if not google_oauth_configured():
        return {"ok": False, "skipped": True, "reason": "oauth_not_configured"}

    days = days_ahead if days_ahead is not None else int(
        getattr(settings, "GOOGLE_CALENDAR_SYNC_DAYS", 7)
    )
    today = datetime.now(CALENDAR_TZ).date()
    schedule_settings = ScheduleSettings.get_for_user(user)
    tasks = Task.objects.filter(user=user)

    try:
        service = _calendar_service(connection)
        calendar_id = connection.calendar_id or "primary"
        created = updated = deleted = skipped = 0

        for offset in range(days + 1):
            schedule_date = today + timedelta(days=offset)
            items, _ = build_schedule(
                tasks, schedule_settings, schedule_date=schedule_date, user=user
            )
            if not connection.sync_breaks:
                items = [i for i in items if not i.get("is_break")]
            items = [i for i in items if not i.get("is_external")]

            desired = _desired_slots(items, schedule_date)
            existing = {
                m.local_key: m
                for m in CalendarEventMapping.objects.filter(user=user, schedule_date=schedule_date)
            }

            for key, mapping in list(existing.items()):
                if key not in desired:
                    try:
                        _execute_with_retry(
                            service.events().delete(
                                calendarId=calendar_id,
                                eventId=mapping.google_event_id,
                            )
                        )
                    except Exception as exc:  # noqa: BLE001 — event may already be gone
                        logger.info("Delete calendar event %s: %s", mapping.google_event_id, exc)
                    mapping.delete()
                    deleted += 1

            for key, item in desired.items():
                body = _event_body(item)
                digest = _content_hash(body)
                mapping = existing.get(key)
                if mapping and mapping.content_hash == digest:
                    skipped += 1
                    continue

                if mapping:
                    try:
                        _execute_with_retry(
                            service.events().patch(
                                calendarId=calendar_id,
                                eventId=mapping.google_event_id,
                                body=body,
                            )
                        )
                        mapping.content_hash = digest
                        mapping.save(update_fields=["content_hash", "updated_at"])
                        updated += 1
                        continue
                    except Exception as exc:  # noqa: BLE001 — recreate if remote event missing
                        logger.info("Patch failed for %s, recreating: %s", mapping.google_event_id, exc)
                        mapping.delete()

                event = _execute_with_retry(
                    service.events().insert(calendarId=calendar_id, body=body)
                )
                CalendarEventMapping.objects.create(
                    user=user,
                    schedule_date=schedule_date,
                    local_key=key,
                    google_event_id=event["id"],
                    content_hash=digest,
                )
                created += 1

        # Only drop past days. Do not wipe future mappings when auto-syncing
        # a shorter window than "Sync now".
        past = CalendarEventMapping.objects.filter(user=user, schedule_date__lt=today)
        for mapping in past:
            try:
                _execute_with_retry(
                    service.events().delete(
                        calendarId=calendar_id,
                        eventId=mapping.google_event_id,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.info("Delete past calendar event %s: %s", mapping.google_event_id, exc)
            mapping.delete()
            deleted += 1

        connection.last_synced_at = timezone.now()
        connection.last_sync_ok = True
        connection.last_sync_error = ""
        connection.save(update_fields=["last_synced_at", "last_sync_ok", "last_sync_error", "updated_at"])
        return {
            "ok": True,
            "created": created,
            "updated": updated,
            "deleted": deleted,
            "skipped": skipped,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Google Calendar sync failed for user %s", user.pk)
        connection.last_synced_at = timezone.now()
        connection.last_sync_ok = False
        connection.last_sync_error = str(exc)[:2000]
        connection.save(update_fields=["last_synced_at", "last_sync_ok", "last_sync_error", "updated_at"])
        return {"ok": False, "error": str(exc)}


def sync_user_schedule_safe(user) -> None:
    """Optional short-window sync. The web app does not call this after edits."""
    try:
        days = int(getattr(settings, "GOOGLE_CALENDAR_AUTO_SYNC_DAYS", 0))
        sync_user_schedule(user, days_ahead=days)
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected calendar sync error for user %s", getattr(user, "pk", user))


def clear_user_calendar_events(user) -> None:
    """Delete mapped Google events and local mappings (used on disconnect)."""
    try:
        connection = GoogleCalendarConnection.objects.get(user=user)
    except GoogleCalendarConnection.DoesNotExist:
        CalendarEventMapping.objects.filter(user=user).delete()
        return

    if connection.is_connected and google_oauth_configured():
        try:
            service = _calendar_service(connection)
            calendar_id = connection.calendar_id or "primary"
            for mapping in CalendarEventMapping.objects.filter(user=user):
                try:
                    service.events().delete(calendarId=calendar_id, eventId=mapping.google_event_id).execute()
                except Exception as exc:  # noqa: BLE001
                    logger.info("Delete on disconnect %s: %s", mapping.google_event_id, exc)
        except Exception:  # noqa: BLE001
            logger.exception("Could not clear remote events for user %s", user.pk)

    CalendarEventMapping.objects.filter(user=user).delete()
    ImportedCalendarEvent.objects.filter(user=user).delete()


def get_connection_status(user) -> dict:
    configured = google_oauth_configured()
    try:
        connection = GoogleCalendarConnection.objects.get(user=user)
    except GoogleCalendarConnection.DoesNotExist:
        return {
            "configured": configured,
            "connected": False,
            "sync_enabled": False,
            "sync_breaks": True,
            "pull_enabled": True,
            "last_synced_at": None,
            "last_sync_ok": None,
            "last_sync_error": "",
            "last_pulled_at": None,
            "last_pull_ok": None,
            "last_pull_error": "",
            "calendar_id": "primary",
        }
    return {
        "configured": configured,
        "connected": connection.is_connected,
        "sync_enabled": connection.sync_enabled,
        "sync_breaks": connection.sync_breaks,
        "pull_enabled": connection.pull_enabled,
        "last_synced_at": connection.last_synced_at,
        "last_sync_ok": connection.last_sync_ok,
        "last_sync_error": connection.last_sync_error,
        "last_pulled_at": connection.last_pulled_at,
        "last_pull_ok": connection.last_pull_ok,
        "last_pull_error": connection.last_pull_error,
        "calendar_id": connection.calendar_id,
    }
