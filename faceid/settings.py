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
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cloudinary_storage',   # must come before staticfiles for media
    'cloudinary',
    'accounts',
]

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

# ─── Security (auto-enabled when not DEBUG) ───────────────────────────────────
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ─── Face recognition ─────────────────────────────────────────────────────────
# Verification tolerance: maximum face_distance to accept a login match.
# Lower = stricter. Default library value is 0.6; we use 0.4 for security.
FACE_RECOGNITION_TOLERANCE = float(os.environ.get('FACE_TOLERANCE', '0.4'))

# Enrollment duplicate-check tolerance: how close a new face can be to an
# existing enrolled face before we reject the enrollment as a potential
# duplicate. Must be tighter than verification tolerance.
FACE_ENROLL_DUPLICATE_TOLERANCE = float(os.environ.get('FACE_ENROLL_DUPLICATE_TOLERANCE', '0.35'))

# Number of jitters (re-samples) when extracting an enrollment encoding.
# Higher = more accurate template but slower. 3 is a good balance.
FACE_ENROLL_NUM_JITTERS = int(os.environ.get('FACE_ENROLL_NUM_JITTERS', '3'))

# Number of separate captures to average during enrollment. More samples
# produce a more robust template that handles lighting/angle variation.
FACE_ENROLL_NUM_SAMPLES = int(os.environ.get('FACE_ENROLL_NUM_SAMPLES', '5'))

# Minimum confidence (0-100) required for a verification match. Even if
# the distance is within tolerance, reject if confidence is below this.
FACE_MIN_CONFIDENCE = float(os.environ.get('FACE_MIN_CONFIDENCE', '65'))

# Number of consecutive successful matches to the same user required
# before granting login. Prevents single-frame spoofing with photos.
FACE_VERIFY_CONSECUTIVE_MATCHES = int(os.environ.get('FACE_VERIFY_CONSECUTIVE_MATCHES', '2'))

FACE_PHOTOS_DIR = 'face_photos'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
