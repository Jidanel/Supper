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
    
    # ===================================================================
    # MIDDLEWARES SUPPER PERSONNALISÉS - ORDRE IMPORTANT
    # ===================================================================
    
    # 1. Contexte utilisateur (doit être après AuthenticationMiddleware)
    'common.middleware.UserContextMiddleware',
    
    # 2. Redirection automatique selon rôles (doit être après UserContextMiddleware)
    'common.middleware.AdminRedirectMiddleware',
    
    # 3. Journalisation des actions (après redirection)
    'common.middleware.AuditMiddleware',
    
    # 4. Sécurité avancée
    'common.middleware.SecurityMiddleware',
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
# URLs de redirection après connexion/déconnexion
LOGIN_URL = '/accounts/login/'
LOGOUT_URL = '/accounts/logout/'

# Redirection par défaut après connexion (sera override par le middleware)
LOGIN_REDIRECT_URL = '/'  # Le middleware gèrera la redirection réelle
# Redirection après déconnexion
LOGOUT_REDIRECT_URL = '/accounts/login/'
# ===================================================================
# CONFIGURATION DES SESSIONS
# ===================================================================
# Site admin par défaut
ADMIN_SITE_HEADER = "Administration SUPPER"
ADMIN_SITE_TITLE = "SUPPER Admin"
ADMIN_INDEX_TITLE = "Tableau de Bord Administrateur"


# Configuration des sessions Django
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 3600 * 8  # 8 heures
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True  # Nécessaire pour la journalisation
SESSION_COOKIE_NAME = 'supper_sessionid'
SESSION_COOKIE_SECURE = not DEBUG  # HTTPS en production
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# Cache par défaut (en mémoire pour développement)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'supper-cache',
        'TIMEOUT': 300,  # 5 minutes
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        }
    }
}

# En production, utiliser Redis :
# CACHES = {
#     'default': {
#         'BACKEND': 'django.core.cache.backends.redis.RedisCache',
#         'LOCATION': 'redis://127.0.0.1:6379/1',
#         'OPTIONS': {
#             'CLIENT_CLASS': 'django_redis.client.DefaultClient',
#         }
#     }
# }


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
            'format': '{levelname} {message}',
            'style': '{',
        },
        'supper_format': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'file_supper': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'supper_app.log',
            'maxBytes': 1024*1024*15,  # 15 MB
            'backupCount': 10,
            'formatter': 'supper_format',
        },
        'file_audit': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'supper_audit.log',
            'maxBytes': 1024*1024*15,  # 15 MB
            'backupCount': 10,
            'formatter': 'supper_format',
        },
        'file_security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'supper_security.log',
            'maxBytes': 1024*1024*5,  # 5 MB
            'backupCount': 5,
            'formatter': 'supper_format',
        },
        'file_redirect': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'supper_redirect.log',
            'maxBytes': 1024*1024*5,  # 5 MB
            'backupCount': 5,
            'formatter': 'supper_format',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'supper': {
            'handlers': ['console', 'file_supper'],
            'level': 'INFO',
            'propagate': False,
        },
        'accounts': {
            'handlers': ['console', 'file_audit'],
            'level': 'INFO',
            'propagate': False,
        },
        'common.middleware': {
            'handlers': ['console', 'file_redirect'],
            'level': 'INFO',
            'propagate': False,
        },
        'security': {
            'handlers': ['file_security'],
            'level': 'WARNING',
            'propagate': False,
        },
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
     messages.ERROR: 'danger',
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

if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    # Configuration SMTP pour production
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'localhost'  # À configurer selon l'environnement
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = ''  # À configurer
    EMAIL_HOST_PASSWORD = ''  # À configurer

DEFAULT_FROM_EMAIL = 'noreply@supper.cm'
ADMIN_EMAIL = 'admin@supper.cm'

# ===================================================================
# CONFIGURATION PAGINATION
# ===================================================================

PAGINATION_CONFIG = {
    'LOGS_PER_PAGE': 50,
    'USERS_PER_PAGE': 25,
    'INVENTAIRES_PER_PAGE': 30,
    'RECETTES_PER_PAGE': 30,
}

# Pagination par défaut
PAGINATE_BY = 25
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
# Protection CSRF
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_USE_SESSIONS = False  # Utiliser les cookies pour CSRF

# En-têtes de sécurité (gérés aussi par le middleware)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

# En production uniquement
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000  # 1 an
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
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

#Compression des réponses
USE_GZIP = True

# ===================================================================
# CONFIGURATION DÉVELOPPEMENT VS PRODUCTION
# ===================================================================

if DEBUG:
    # Paramètres de développement
    INTERNAL_IPS = ['127.0.0.1', 'localhost']
    
    # Debug toolbar si installé
    try:
        import debug_toolbar
        INSTALLED_APPS += ['debug_toolbar']
        MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
    except ImportError:
        pass

else:
    # Paramètres de production
    ALLOWED_HOSTS = ['*']  # À restreindre en production
    
    # Désactiver les informations sensibles
    ADMINS = [('Admin SUPPER', ADMIN_EMAIL)]
    MANAGERS = ADMINS
    
    # Logging plus verbeux en production
    LOGGING['handlers']['file_supper']['level'] = 'WARNING'

# ===================================================================
# VARIABLES SPÉCIFIQUES SUPPER
# ===================================================================

# Configuration métier SUPPER
SUPPER_CONFIG = {
    'VERSION': '1.0.0',
    'ORGANIZATION': 'Programme de Sécurisation des Recettes Routières',
    'COUNTRY': 'Cameroun',
    'DEFAULT_TIMEZONE': 'Africa/Douala',
    'SUPPORTED_LANGUAGES': ['fr', 'en'],
    'MAX_UPLOAD_SIZE': 10 * 1024 * 1024,  # 10 MB
    'SESSION_TIMEOUT_MINUTES': 480,  # 8 heures
    'BACKUP_RETENTION_DAYS': 30,
    'LOG_RETENTION_DAYS': 90,
}

# Paramètres de calcul métier
CALCUL_CONFIG = {
    'TAUX_VEHICULES_LOURDS': 0.75,  # 75% de véhicules lourds
    'TARIF_MOYEN_FCFA': 500,        # 500 FCFA par véhicule
    'HEURES_FONCTIONNEMENT': 24,    # 24h/24
    'SEUILS_DEPERDITION': {
        'BON': -10,      # > -10%
        'ATTENTION': -30, # -10% à -30%
        'CRITIQUE': -30   # < -30%
    }
}

# ===================================================================
# IMPORTS CONDITIONNELS POUR ENVIRONNEMENTS
# ===================================================================

# Importer les paramètres locaux s'ils existent
import importlib.util

local_settings_path = Path(__file__).parent / 'local_settings.py'
if local_settings_path.exists():
    spec = importlib.util.spec_from_file_location("local_settings", str(local_settings_path))
    local_settings = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(local_settings)
    for setting in dir(local_settings):
        if setting.isupper():
            globals()[setting] = getattr(local_settings, setting)
    print("✅ Paramètres locaux chargés")
else:
    print("ℹ️ Aucun paramètre local trouvé")

# Importer les paramètres de production s'ils existent
if not DEBUG:
    production_settings_path = Path(__file__).parent / 'production_settings.py'
    if production_settings_path.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("production_settings", str(production_settings_path))
        production_settings = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(production_settings)
        for setting in dir(production_settings):
            if setting.isupper():
                globals()[setting] = getattr(production_settings, setting)
        print("✅ Paramètres de production chargés")
    else:
        print("⚠️ Aucun paramètre de production trouvé")

print(f"🚀 SUPPER v{SUPPER_CONFIG['VERSION']} - Mode {'Développement' if DEBUG else 'Production'}")