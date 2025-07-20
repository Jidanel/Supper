# ===================================================================
# SUPPER 2025 - Configuration Django Complète
# Application de Suivi des Péages et Pesages Routiers
# ===================================================================

import os
from pathlib import Path
from django.utils.translation import gettext_lazy as _
from django.contrib.messages import constants as messages

# Import des variables d'environnement
try:
    from decouple import config
except ImportError:
    # Fallback si decouple n'est pas encore installé
    def config(key, default=None, cast=str):
        return os.environ.get(key, default)

# ===================================================================
# CONFIGURATION DE BASE
# ===================================================================

# Répertoire de base du projet
BASE_DIR = Path(__file__).resolve().parent.parent

# Clé secrète Django
SECRET_KEY = config('SECRET_KEY', default='django-insecure-changez-moi-en-production-2025')

# Mode développement
DEBUG = config('DEBUG', default=True, cast=bool)

# Hôtes autorisés
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

# ===================================================================
# APPLICATIONS INSTALLÉES
# ===================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Applications SUPPER
    'accounts.apps.AccountsConfig',      # Gestion des utilisateurs et authentification
    'inventaire.apps.InventaireConfig',  # Module de gestion des inventaires
    'common.apps.CommonConfig',          # Fonctions communes et journalisation
]

# ===================================================================
# MIDDLEWARE
# ===================================================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',      # Support multilingue
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'common.middleware.AdminAccessMiddleware',  # Nouveau middleware pour contrôler l'admin
    'common.middleware.AuditMiddleware',        # Journalisation
]

# ===================================================================
# CONFIGURATION DES URLS ET TEMPLATES
# ===================================================================

ROOT_URLCONF = 'Supper.urls'

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
                'django.template.context_processors.i18n',  # Internationalisation
                'django.template.context_processors.media', # Fichiers média
                'django.template.context_processors.static', # Fichiers statiques
            ],
        },
    },
]

WSGI_APPLICATION = 'Supper.wsgi.application'

# ===================================================================
# CONFIGURATION BASE DE DONNÉES POSTGRESQL
# ===================================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='supper_db'),
        'USER': config('DB_USER', default='supper_user'),
        'PASSWORD': config('DB_PASSWORD', default='SupperDB2025'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 60,
    }
}
# Fallback SQLite pour les tests si PostgreSQL non disponible
if config('USE_SQLITE_FOR_TESTS', default=False, cast=bool):
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_test.sqlite3',
    }

# ===================================================================
# VALIDATION DES MOTS DE PASSE
# ===================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 4,  # Minimum 4 caractères pour les mots de passe
        }
    },
   
]

# ===================================================================
# CONFIGURATION INTERNATIONALE (BILINGUE FR/EN)
# ===================================================================

LANGUAGE_CODE = 'fr'  # Français par défaut
TIME_ZONE = 'Africa/Douala'  # Fuseau horaire du Cameroun

USE_I18N = True      # Activation de l'internationalisation
USE_TZ = True        # Utilisation des fuseaux horaires

# Langues supportées par SUPPER
LANGUAGES = [
    ('fr', _('Français')),
    ('en', _('English')),
]

# Répertoires des fichiers de traduction
LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# ===================================================================
# FICHIERS STATIQUES ET MÉDIA
# ===================================================================

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'  # Pour la collecte en production

# Fichiers média (uploads utilisateurs, photos, documents)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ===================================================================
# MODÈLE UTILISATEUR PERSONNALISÉ
# ===================================================================

AUTH_USER_MODEL = 'accounts.UtilisateurSUPPER'

# URLs de redirection après connexion/déconnexion
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# ===================================================================
# CONFIGURATION DES SESSIONS
# ===================================================================

SESSION_COOKIE_AGE = 3600  # 1 heure d'inactivité
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True  # Nécessaire pour la journalisation
SESSION_COOKIE_NAME = 'supper_sessionid'
SESSION_COOKIE_SECURE = not DEBUG  # HTTPS en production
SESSION_COOKIE_HTTPONLY = True

# ===================================================================
# CONFIGURATION DE LA JOURNALISATION COMPLÈTE
# ===================================================================

# Créer le dossier logs s'il n'existe pas
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
        'audit': {
            'format': '{asctime} | {name} | {levelname} | {message}',
            'style': '{',
        },
    },
    'handlers': {
        # Fichier principal de l'application
        'file_app': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'supper_app.log',
            'maxBytes': 5*1024*1024,  # 5 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        # Fichier spécifique pour l'audit utilisateur
        'file_audit': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'supper_audit.log',
            'maxBytes': 10*1024*1024,  # 10 MB
            'backupCount': 10,
            'formatter': 'audit',
            'encoding': 'utf-8',
        },
        # Fichier pour les erreurs
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'supper_errors.log',
            'maxBytes': 5*1024*1024,  # 5 MB
            'backupCount': 3,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        # Console pour le développement
        'console': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        # Logger principal de SUPPER
        'supper': {
            'handlers': ['file_app', 'file_audit', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Logger Django
        'django': {
            'handlers': ['file_error', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Logger base de données (limité pour éviter trop de logs)
        'django.db.backends': {
            'handlers': ['file_app'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Logger requêtes HTTP
        'django.request': {
            'handlers': ['file_error', 'console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}

# ===================================================================
# CONFIGURATION DES MESSAGES
# ===================================================================

MESSAGE_TAGS = {
    messages.DEBUG: 'debug',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'error',
}

# ===================================================================
# CONFIGURATION SPÉCIFIQUE À SUPPER
# ===================================================================

# Paramètres métier pour le calcul des taux de déperdition
SUPPER_CONFIG = {
    'TARIF_VEHICULE_LEGER': 500,          # Tarif en FCFA
    'POURCENTAGE_VEHICULES_LEGERS': 75,   # 75% de véhicules légers
    'SEUIL_ALERTE_ROUGE': -30,            # Taux de déperdition critique (%)
    'SEUIL_ALERTE_ORANGE': -10,           # Taux de déperdition attention (%)
    'HEURES_OUVERTURE_POSTE': 24,         # Heures d'ouverture par jour
    'RETENTION_LOGS_JOURS': 180,          # Conservation des logs (6 mois)
    'PERIODES_INVENTAIRE': [              # Créneaux horaires pour inventaire
        '08h-09h', '09h-10h', '10h-11h', '11h-12h',
        '12h-13h', '13h-14h', '14h-15h', '15h-16h',
        '16h-17h', '17h-18h'
    ],
}

# ===================================================================
# CONFIGURATION EMAIL
# ===================================================================

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@supper.cm')

# ===================================================================
# CONFIGURATION CACHE
# ===================================================================

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'supper-cache',
        'TIMEOUT': 300,  # 5 minutes
    }
}

# Configuration Redis pour la production (décommentez si nécessaire)
"""
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}
"""

# ===================================================================
# CONFIGURATION PAGINATION
# ===================================================================

PAGINATION_CONFIG = {
    'LOGS_PER_PAGE': 50,
    'USERS_PER_PAGE': 25,
    'INVENTAIRES_PER_PAGE': 30,
    'RECETTES_PER_PAGE': 30,
}

# ===================================================================
# CONFIGURATION DE SÉCURITÉ
# ===================================================================

# Sécurité en production
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True

# Protection CSRF
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# ===================================================================
# PARAMÈTRES DE DÉVELOPPEMENT
# ===================================================================

if DEBUG:
    # Autoriser tous les hôtes en développement
    ALLOWED_HOSTS = ['*']
    

    # Debug Toolbar si installé - COMMENTÉ TEMPORAIREMENT
    # try:
    #     import debug_toolbar
    #     INSTALLED_APPS.append('debug_toolbar')
    #     MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
    #     
    #     DEBUG_TOOLBAR_CONFIG = {
    #         'SHOW_TOOLBAR_CALLBACK': lambda request: True,
    #     }
    #     
    # except ImportError:
    #     pass
# ===================================================================
# TYPE DE CHAMP PRIMAIRE PAR DÉFAUT
# ===================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'