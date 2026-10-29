"""
Pull Google Calendar events for all connected users.

Example (PythonAnywhere / cron every minute):
  python manage.py pull_google_calendar
"""
from django.core.management.base import BaseCommand

from tasks import google_calendar as gcal
from tasks.models import GoogleCalendarConnection


class Command(BaseCommand):
    help = "Pull Google Calendar events into the app as busy time."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ignore the pull throttle and always hit the API.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        qs = GoogleCalendarConnection.objects.filter(pull_enabled=True).exclude(token_json="")
        total = qs.count()
        if total == 0:
            self.stdout.write("No connected Google Calendar users.")
            return

        ok = failed = skipped = 0
        for connection in qs.select_related("user"):
            user = connection.user
            result = (
                gcal.pull_user_events(user)
                if force
                else gcal.maybe_pull_user_events(user)
            )
            if result.get("skipped"):
                skipped += 1
                self.stdout.write(f"  user={user.pk} skipped ({result.get('reason')})")
            elif result.get("ok"):
                ok += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  user={user.pk} created={result.get('created', 0)} "
                        f"updated={result.get('updated', 0)} deleted={result.get('deleted', 0)} "
                        f"changed={result.get('changed')}"
                    )
                )
            else:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(f"  user={user.pk} error={result.get('error')}")
                )

        self.stdout.write(
            f"Done. total={total} ok={ok} skipped={skipped} failed={failed}"
        )
