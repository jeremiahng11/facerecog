from pathlib import Path
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# ─── Core ─────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-before-deploy')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = ['*']  # Railway provides its own domain; restrict in production if needed

# Trust Railway's reverse proxy for HTTPS detection
CSRF_TRUSTED_ORIGINS = []
RAILWAY_PUBLIC_DOMAIN = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
if RAILWAY_PUBLIC_DOMAIN:
    CSRF_TRUSTED_ORIGINS.append(f'https://{RAILWAY_PUBLIC_DOMAIN}')

# ─── Apps ─────────────────────────────────────────────────────────────────────
# Detect optional packages — project runs without them, gains real-time
# and async capabilities when they're installed + Redis is deployed.
try:
    import channels  # noqa: F401
    import daphne    # noqa: F401
    _CHANNELS_INSTALLED = True
except ImportError:
    _CHANNELS_INSTALLED = False

INSTALLED_APPS = []
if _CHANNELS_INSTALLED:
    # Daphne must come BEFORE django.contrib.staticfiles for ASGI support.
    INSTALLED_APPS.append('daphne')
INSTALLED_APPS += [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cloudinary_storage',   # must come before staticfiles for media
    'cloudinary',
]
if _CHANNELS_INSTALLED:
    INSTALLED_APPS.append('channels')
INSTALLED_APPS.append('accounts')

if _CHANNELS_INSTALLED:
    ASGI_APPLICATION = 'faceid.asgi.application'

# ─── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # static files in production
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'faceid.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
                'accounts.context_processors.branding',
            ],
        },
    },
]

WSGI_APPLICATION = 'faceid.wsgi.application'

# ─── Database — Railway PostgreSQL ────────────────────────────────────────────
# Railway auto-injects DATABASE_URL when you add a Postgres service.
# Falls back to SQLite for local dev if DATABASE_URL is not set.
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ─── Auth ─────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.StaffUser'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

# ─── Localisation ─────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Singapore'
USE_I18N = True
USE_TZ = True

# ─── Static files (WhiteNoise) ────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Only add STATICFILES_DIRS if the /static directory actually exists
_STATIC_SRC = BASE_DIR / 'static'
if _STATIC_SRC.exists():
    STATICFILES_DIRS = [_STATIC_SRC]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ─── Media files ──────────────────────────────────────────────────────────────
# Two supported storage modes:
#   1. Railway Volume (default): mount a volume at MEDIA_ROOT so uploaded
#      photos persist across redeploys. Override MEDIA_ROOT via env var if
#      your volume is mounted somewhere other than /app/media.
#   2. Cloudinary: set CLOUDINARY_URL=cloudinary://API_KEY:API_SECRET@CLOUD_NAME
#      to push uploads to Cloudinary instead of the local filesystem.
MEDIA_URL = '/media/'
MEDIA_ROOT = os.environ.get('MEDIA_ROOT', str(BASE_DIR / 'media'))

CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL', '')
if CLOUDINARY_URL:
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

# ─── Session ─────────────────────────────────────────────────────────────────
SESSION_COOKIE_AGE = int(os.environ.get('SESSION_COOKIE_AGE', '28800'))  # 8 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True   # refresh timeout on each request

# ─── Security (auto-enabled when not DEBUG) ───────────────────────────────────
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ─── Email (for password reset + security notifications) ─────────────────────
# Configure via env vars. Auto-switches to SMTP when EMAIL_HOST_USER is set;
# falls back to console backend (prints to server log) otherwise.
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'noreply@faceid-portal.com')
ADMIN_NOTIFICATION_EMAIL = os.environ.get('ADMIN_NOTIFICATION_EMAIL', '')

# Auto-select backend: use SMTP if credentials are configured, else console.
if os.environ.get('EMAIL_BACKEND'):
    EMAIL_BACKEND = os.environ['EMAIL_BACKEND']
elif EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ─── Face recognition ─────────────────────────────────────────────────────────
# Verification tolerance: maximum face_distance to accept a login match.
# Lower = stricter. Default library value is 0.6; we use 0.4 for security.
FACE_RECOGNITION_TOLERANCE = float(os.environ.get('FACE_TOLERANCE', '0.4'))

# Enrollment duplicate-check tolerance: how close a new face can be to an
# existing enrolled face before we reject the enrollment as a potential
# duplicate. Must be tighter than verification tolerance.
FACE_ENROLL_DUPLICATE_TOLERANCE = float(os.environ.get('FACE_ENROLL_DUPLICATE_TOLERANCE', '0.35'))

# Number of jitters (re-samples) when extracting an enrollment encoding.
# 1 is fast and sufficient when averaging across multiple captures.
FACE_ENROLL_NUM_JITTERS = int(os.environ.get('FACE_ENROLL_NUM_JITTERS', '1'))

# Number of separate captures to average during enrollment. 3 captures
# is enough for liveness variance + template averaging while keeping
# enrollment fast (~2 seconds vs ~5 with 5 samples).
FACE_ENROLL_NUM_SAMPLES = int(os.environ.get('FACE_ENROLL_NUM_SAMPLES', '3'))

# Minimum confidence (0-100) required for a verification match. Even if
# the distance is within tolerance, reject if confidence is below this.
FACE_MIN_CONFIDENCE = float(os.environ.get('FACE_MIN_CONFIDENCE', '65'))

# Number of consecutive successful matches to the same user required
# before granting login. 2 is sufficient for liveness variance check
# while keeping kiosk queues fast.  Override via env var if needed.
FACE_VERIFY_CONSECUTIVE_MATCHES = int(os.environ.get('FACE_VERIFY_CONSECUTIVE_MATCHES', '2'))

FACE_PHOTOS_DIR = 'face_photos'

# IP lockout: after this many failed scan sessions (not individual frames)
# from the same IP within FACE_LOCKOUT_DURATION_MINUTES, block the IP.
FACE_LOCKOUT_THRESHOLD = int(os.environ.get('FACE_LOCKOUT_THRESHOLD', '10'))
FACE_LOCKOUT_DURATION_MINUTES = int(os.environ.get('FACE_LOCKOUT_DURATION_MINUTES', '5'))

# ─── Branding (customise via env vars) ────────────────────────────────────────
BRAND_NAME = os.environ.get('BRAND_NAME', 'FaceID Portal')
BRAND_COMPANY = os.environ.get('BRAND_COMPANY', '')
BRAND_ACCENT_COLOR = os.environ.get('BRAND_ACCENT_COLOR', '#1e56b8')

# ─── Kiosk ────────────────────────────────────────────────────────────────────
# Idle timeout: seconds of inactivity before the kiosk auto-resets to scan.
KIOSK_IDLE_TIMEOUT = int(os.environ.get('KIOSK_IDLE_TIMEOUT', '15'))
# After printing, auto-logout and reset after this many seconds.
KIOSK_POST_PRINT_TIMEOUT = int(os.environ.get('KIOSK_POST_PRINT_TIMEOUT', '10'))

# ─── Cafeteria ─────────────────────────────────────────────────────────────
# HMAC key for signing QR collection tokens. Derived from SECRET_KEY if not set.
QR_SECRET_KEY = os.environ.get('QR_SECRET_KEY', '')
# Kiosk idle timeout (seconds) before returning to idle screen.
STAFF_IDLE_TIMEOUT_SECONDS = int(os.environ.get('STAFF_IDLE_TIMEOUT_SECONDS', '30'))
# Default monthly staff credit allowance (SGD).
DEFAULT_MONTHLY_CREDIT = float(os.environ.get('DEFAULT_MONTHLY_CREDIT', '50.00'))
# Working days per month used for proration calculation.
CREDIT_WORKING_DAYS = int(os.environ.get('CREDIT_WORKING_DAYS', '30'))
# Day of month to reset credits (used by future Celery Beat task).
CREDIT_RESET_DAY = int(os.environ.get('CREDIT_RESET_DAY', '1'))

# ─── Redis-backed Channels + Celery (auto-active when REDIS_URL is set) ─────
REDIS_URL = os.environ.get('REDIS_URL', '')

if _CHANNELS_INSTALLED and REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [REDIS_URL]},
        },
    }
elif _CHANNELS_INSTALLED:
    # In-memory channel layer — works for a single-process dev server but
    # NOT for multi-worker production. Deploy Redis on Railway to upgrade.
    CHANNEL_LAYERS = {
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    }

# Celery — auto-active when REDIS_URL is set. Tasks degrade to no-ops without.
CELERY_BROKER_URL = REDIS_URL or 'memory://'
CELERY_RESULT_BACKEND = REDIS_URL or 'cache+memory://'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# ─── Stripe ────────────────────────────────────────────────────────────────
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

# ─── PayNow ────────────────────────────────────────────────────────────────
PAYNOW_UEN = os.environ.get('PAYNOW_UEN', '')
PAYNOW_MERCHANT_NAME = os.environ.get('PAYNOW_MERCHANT_NAME', 'Cafeteria')

# ─── Cron endpoint secret (for GitHub Actions scheduled tasks) ──────────────
CRON_SECRET = os.environ.get('CRON_SECRET', '')

# ─── Vending machine API ────────────────────────────────────────────────────
# Shared API key that vending machines include as Bearer token.
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
VENDING_API_KEY = os.environ.get('VENDING_API_KEY', '')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
