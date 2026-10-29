from .models import ScheduleSettings


def ui_theme(request):
    """Expose the current user's theme preference to every template."""
    theme = 'dark'
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        try:
            theme = ScheduleSettings.get_for_user(user).theme or 'dark'
        except Exception:  # noqa: BLE001 — never break page render for theme
            theme = 'dark'
    if theme not in ('dark', 'light'):
        theme = 'dark'
    return {'ui_theme': theme}
