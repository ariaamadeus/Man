"""
Sync the health-aware schedule to Google Calendar.

Tasks themselves have no fixed times — only build_schedule() produces timed
blocks. After task/settings mutations we rebuild upcoming days and upsert
matching Google Calendar events.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from .models import CalendarEventMapping, GoogleCalendarConnection, ScheduleSettings, Task
from .services import build_schedule

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CALENDAR_TZ = ZoneInfo(getattr(settings, "GOOGLE_CALENDAR_TIMEZONE", "Asia/Jakarta"))


def google_oauth_configured() -> bool:
    return bool(
        getattr(settings, "GOOGLE_CLIENT_ID", "").strip()
        and getattr(settings, "GOOGLE_CLIENT_SECRET", "").strip()
    )


def get_redirect_uri() -> str:
    return getattr(settings, "GOOGLE_REDIRECT_URI", "").strip() or "http://127.0.0.1:8000/google/callback/"


def _flow():
    from google_auth_oauthlib.flow import Flow
    from pathlib import Path

    if not google_oauth_configured():
        raise RuntimeError(
            "Google OAuth is not configured. Place credentials.json in the project root "
            "or set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )

    creds_path = Path(getattr(settings, "GOOGLE_CREDENTIALS_FILE", "") or "")
    redirect_uri = get_redirect_uri()

    if creds_path.is_file():
        # Supports both "web" and "installed" Google client JSON downloads.
        flow = Flow.from_client_secrets_file(str(creds_path), scopes=SCOPES)
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
        flow = Flow.from_client_config(client_config, scopes=SCOPES)

    flow.redirect_uri = redirect_uri
    return flow


def get_authorization_url(state: str) -> str:
    flow = _flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return auth_url


def exchange_code_for_tokens(code: str) -> dict:
    flow = _flow()
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
            expiry = timezone.make_aware(expiry, timezone.utc)

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


def _local_key(item: dict, schedule_date: date) -> str:
    start = item["start_time"].strftime("%H%M")
    end = item["end_time"].strftime("%H%M")
    if item.get("is_break"):
        kind = item.get("break_type") or "break"
        return f"{schedule_date.isoformat()}:break:{kind}:{start}-{end}"
    task_id = item.get("task_id") or "anon"
    return f"{schedule_date.isoformat()}:task:{task_id}:{start}-{end}"


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


def sync_user_schedule(user, days_ahead: Optional[int] = None) -> dict:
    """
    Rebuild schedule for today..today+N and upsert Google Calendar events.
    Returns a small status dict. No-op if not connected / sync disabled.
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
    # Match the UI clock (UTC+7 / Asia/Jakarta).
    today = datetime.now(CALENDAR_TZ).date()
    schedule_settings = ScheduleSettings.get_for_user(user)
    tasks = Task.objects.filter(user=user)

    try:
        service = _calendar_service(connection)
        calendar_id = connection.calendar_id or "primary"
        created = updated = deleted = 0

        for offset in range(days + 1):
            schedule_date = today + timedelta(days=offset)
            items, _ = build_schedule(tasks, schedule_settings, schedule_date=schedule_date)
            if not connection.sync_breaks:
                items = [i for i in items if not i.get("is_break")]

            desired = {}
            for item in items:
                desired[_local_key(item, schedule_date)] = item

            existing = {
                m.local_key: m
                for m in CalendarEventMapping.objects.filter(user=user, schedule_date=schedule_date)
            }

            for key, mapping in list(existing.items()):
                if key not in desired:
                    try:
                        service.events().delete(calendarId=calendar_id, eventId=mapping.google_event_id).execute()
                    except Exception as exc:  # noqa: BLE001 — event may already be gone
                        logger.info("Delete calendar event %s: %s", mapping.google_event_id, exc)
                    mapping.delete()
                    deleted += 1

            for key, item in desired.items():
                body = _event_body(item)
                mapping = existing.get(key)
                if mapping:
                    try:
                        service.events().patch(
                            calendarId=calendar_id,
                            eventId=mapping.google_event_id,
                            body=body,
                        ).execute()
                        mapping.save(update_fields=["updated_at"])
                        updated += 1
                        continue
                    except Exception as exc:  # noqa: BLE001 — recreate if remote event missing
                        logger.info("Patch failed for %s, recreating: %s", mapping.google_event_id, exc)
                        mapping.delete()
                event = service.events().insert(calendarId=calendar_id, body=body).execute()
                CalendarEventMapping.objects.create(
                    user=user,
                    schedule_date=schedule_date,
                    local_key=key,
                    google_event_id=event["id"],
                )
                created += 1

        # Drop mappings for days outside the sync window (e.g. yesterday).
        stale = CalendarEventMapping.objects.filter(user=user).exclude(
            schedule_date__gte=today,
            schedule_date__lte=today + timedelta(days=days),
        )
        for mapping in stale:
            try:
                service.events().delete(calendarId=calendar_id, eventId=mapping.google_event_id).execute()
            except Exception as exc:  # noqa: BLE001
                logger.info("Delete stale calendar event %s: %s", mapping.google_event_id, exc)
            mapping.delete()
            deleted += 1

        connection.last_synced_at = timezone.now()
        connection.last_sync_ok = True
        connection.last_sync_error = ""
        connection.save(update_fields=["last_synced_at", "last_sync_ok", "last_sync_error", "updated_at"])
        return {"ok": True, "created": created, "updated": updated, "deleted": deleted}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Google Calendar sync failed for user %s", user.pk)
        connection.last_synced_at = timezone.now()
        connection.last_sync_ok = False
        connection.last_sync_error = str(exc)[:2000]
        connection.save(update_fields=["last_synced_at", "last_sync_ok", "last_sync_error", "updated_at"])
        return {"ok": False, "error": str(exc)}


def sync_user_schedule_safe(user) -> None:
    """Fire-and-forget wrapper for view hooks — never raises."""
    try:
        sync_user_schedule(user)
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
            "last_synced_at": None,
            "last_sync_ok": None,
            "last_sync_error": "",
            "calendar_id": "primary",
        }
    return {
        "configured": configured,
        "connected": connection.is_connected,
        "sync_enabled": connection.sync_enabled,
        "sync_breaks": connection.sync_breaks,
        "last_synced_at": connection.last_synced_at,
        "last_sync_ok": connection.last_sync_ok,
        "last_sync_error": connection.last_sync_error,
        "calendar_id": connection.calendar_id,
    }
