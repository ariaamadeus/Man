"""
Django settings for Health-Aware Task Manager.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-secret-change-in-production')

DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'

# ALLOWED_HOSTS = [
#     h.strip() for h in
#     os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,192.168.1.8').split(',')
#     if h.strip()
# ]
ALLOWED_HOSTS = ["*"] 

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'tasks.apps.TasksConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'

# MQTT (optional: set in .env to enable schedule event notifications)
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost").strip()
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "man/schedule/current").strip()
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "").strip()
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "").strip()

# Auto-publish current-event notifications while running the web server.
# Enabled by default in DEBUG; disable by setting MQTT_NOTIFIER_AUTOSTART=0.
_default_autostart = "1" if DEBUG else "0"
MQTT_NOTIFIER_AUTOSTART = os.environ.get("MQTT_NOTIFIER_AUTOSTART", _default_autostart).strip() == "1"
MQTT_NOTIFIER_INTERVAL_SECONDS = int(os.environ.get("MQTT_NOTIFIER_INTERVAL_SECONDS", "60").strip() or "60")

# Publish a one-time "initialized/online" message at server startup.
MQTT_PUBLISH_STARTUP_STATUS = os.environ.get("MQTT_PUBLISH_STARTUP_STATUS", "1").strip() == "1"
MQTT_STARTUP_STATUS_TOPIC = os.environ.get("MQTT_STARTUP_STATUS_TOPIC", "").strip()

# Google Calendar (credentials.json preferred; else GOOGLE_CLIENT_* in .env)
def _load_google_oauth_from_credentials_file():
    """Read client_id/secret from Google's credentials.json (web or installed)."""
    import json

    path = BASE_DIR / "credentials.json"
    if not path.is_file():
        return "", "", ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", "", ""
    block = data.get("web") or data.get("installed") or {}
    client_id = (block.get("client_id") or "").strip()
    client_secret = (block.get("client_secret") or "").strip()
    redirects = block.get("redirect_uris") or []
    # Prefer an http redirect that points at this app's callback if listed.
    redirect = ""
    for uri in redirects:
        if isinstance(uri, str) and "callback" in uri:
            redirect = uri.strip()
            break
    return client_id, client_secret, redirect


_gcal_file_id, _gcal_file_secret, _gcal_file_redirect = _load_google_oauth_from_credentials_file()
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip() or _gcal_file_id
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip() or _gcal_file_secret
GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "",
).strip() or _gcal_file_redirect or "http://127.0.0.1:8000/google/callback/"
GOOGLE_CREDENTIALS_FILE = str(BASE_DIR / "credentials.json")
GOOGLE_CALENDAR_SYNC_DAYS = int(os.environ.get("GOOGLE_CALENDAR_SYNC_DAYS", "7").strip() or "7")
GOOGLE_CALENDAR_TIMEZONE = os.environ.get("GOOGLE_CALENDAR_TIMEZONE", "Asia/Jakarta").strip() or "Asia/Jakarta"
