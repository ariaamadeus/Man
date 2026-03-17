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
