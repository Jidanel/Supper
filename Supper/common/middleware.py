# ===================================================================
# Fichier : common/middleware.py - VERSION CORRIGÉE FINALE
# Middleware avec journalisation alignée sur le modèle JournalAudit
# ===================================================================

import logging
import threading
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings
import time

logger = logging.getLogger('supper')

# Thread-local storage pour stocker le contexte utilisateur
_thread_local = threading.local()


class UserContextMiddleware(MiddlewareMixin):
    """
    Middleware pour stocker le contexte utilisateur dans thread-local
    Permet aux signaux d'accéder à l'utilisateur actuel
    """
    
    def process_request(self, request):
        """Stocker l'utilisateur actuel dans le contexte thread-local"""
        _thread_local.user = getattr(request, 'user', None)
        _thread_local.request = request
        _thread_local.start_time = time.time()
    
    def process_response(self, request, response):
        """Nettoyer le contexte à la fin de la requête"""
        # Calculer la durée de traitement
        if hasattr(_thread_local, 'start_time'):
            duration = time.time() - _thread_local.start_time
            _thread_local.duration = duration
        
        return response
    
    def process_exception(self, request, exception):
        """Gérer les exceptions en nettoyant le contexte"""
        if hasattr(_thread_local, 'user'):
            del _thread_local.user
        if hasattr(_thread_local, 'request'):
            del _thread_local.request


def get_current_user():
    """Fonction utilitaire pour récupérer l'utilisateur actuel depuis n'importe où"""
    return getattr(_thread_local, 'user', None)


def get_current_request():
    """Fonction utilitaire pour récupérer la requête actuelle"""
    return getattr(_thread_local, 'request', None)


def get_request_duration():
    """Fonction utilitaire pour récupérer la durée de la requête"""
    return getattr(_thread_local, 'duration', 0)


class AuditMiddleware(MiddlewareMixin):
    """Middleware de journalisation avancée - INCHANGÉ"""
    
    ACTIONS_TO_LOG = ['POST', 'PUT', 'DELETE', 'PATCH']
    
    SENSITIVE_URLS = [
        '/admin/',
        '/accounts/login/',
        '/accounts/logout/',
        '/dashboard/',
    ]
    
    EXCLUDED_URLS = [
        '/static/',
        '/media/',
        '/favicon.ico',
        '/__debug__/',
        '/api/status/',
    ]
    
    def process_request(self, request):
        if any(excluded in request.path for excluded in self.EXCLUDED_URLS):
            return None
        request._audit_start_time = time.time()
        return None
    
    def process_response(self, request, response):
        if any(excluded in request.path for excluded in self.EXCLUDED_URLS):
            return response
        
        duration = 0
        if hasattr(request, '_audit_start_time'):
            duration = time.time() - request._audit_start_time
        
        should_log = (
            request.method in self.ACTIONS_TO_LOG or
            any(sensitive in request.path for sensitive in self.SENSITIVE_URLS) or
            response.status_code >= 400
        )
        
        if should_log and request.user.is_authenticated:
            self._log_request(request, response, duration)
        
        return response
    
    def _log_request(self, request, response, duration):
        try:
            from accounts.models import JournalAudit
            from datetime import timedelta
            
            action = self._determine_action(request, response)
            details = self._build_details(request, response, duration)
            succes = 200 <= response.status_code < 400
            
            JournalAudit.objects.create(
                utilisateur=request.user,
                action=action,
                details=details,
                adresse_ip=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                url_acces=request.path[:500],
                methode_http=request.method[:10],
                succes=succes,
                duree_execution=timedelta(seconds=duration),
                statut_reponse=response.status_code,
                session_key=getattr(request.session, 'session_key', '')[:40] if hasattr(request, 'session') else ''
            )
            
            log_level = logging.INFO if succes else logging.WARNING
            logger.log(
                log_level,
                f"AUDIT - {request.user.username} - {action} - "
                f"Status: {response.status_code} - Duration: {duration:.3f}s"
            )
            
        except Exception as e:
            logger.error(f"Erreur journalisation audit: {str(e)}")
    
    def _determine_action(self, request, response):
        path = request.path.lower()
        method = request.method
        
        if '/login/' in path:
            return "CONNEXION" if response.status_code < 400 else "TENTATIVE CONNEXION ÉCHOUÉE"
        elif '/logout/' in path:
            return "DÉCONNEXION"
        elif '/admin/' in path:
            if method == 'POST':
                if '/add/' in path:
                    return "CRÉATION ADMIN"
                elif '/change/' in path:
                    return "MODIFICATION ADMIN"
                elif '/delete/' in path:
                    return "SUPPRESSION ADMIN"
                else:
                    return "ACTION ADMIN"
            else:
                return "CONSULTATION ADMIN"
        elif '/dashboard/' in path:
            return "ACCÈS DASHBOARD"
        elif method == 'POST':
            if 'create' in path or 'add' in path:
                return "CRÉATION"
            elif 'edit' in path or 'update' in path or 'change' in path:
                return "MODIFICATION"
            elif 'delete' in path:
                return "SUPPRESSION"
            else:
                return "ACTION POST"
        elif method == 'PUT':
            return "MISE À JOUR"
        elif method == 'DELETE':
            return "SUPPRESSION"
        elif method == 'PATCH':
            return "MODIFICATION PARTIELLE"
        else:
            return f"ACCÈS {method}"
    
    def _build_details(self, request, response, duration):
        details = []
        
        details.append(f"URL: {request.path}")
        details.append(f"Méthode: {request.method}")
        details.append(f"Status: {response.status_code}")
        details.append(f"Durée: {duration:.3f}s")
        
        if hasattr(request.user, 'habilitation'):
            details.append(f"Rôle: {request.user.habilitation}")
        if hasattr(request.user, 'poste_affectation') and request.user.poste_affectation:
            details.append(f"Poste: {request.user.poste_affectation.nom}")
        
        # Interface utilisée
        interface = "Panel Django Admin" if request.path.startswith('/admin/') else "Interface Web"
        details.append(f"Interface: {interface}")
        
        if request.GET:
            get_params = dict(request.GET)
            safe_params = {k: v for k, v in get_params.items() 
                          if k.lower() not in ['password', 'token', 'key']}
            if safe_params:
                details.append(f"Paramètres GET: {safe_params}")
        
        if request.method == 'POST' and request.POST:
            post_data = dict(request.POST)
            safe_post = {k: '[MASQUÉ]' if 'password' in k.lower() or 'token' in k.lower() 
                        else v for k, v in post_data.items()}
            details.append(f"Données POST: {safe_post}")
        
        if hasattr(request, 'session') and request.session.session_key:
            details.append(f"Session: {request.session.session_key[:8]}...")
        
        return " | ".join(details)
    
    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class AdminAccessMiddleware(MiddlewareMixin):
    """
    Middleware pour contrôler l'accès au panel d'administration Django
    CORRIGÉ avec journalisation appropriée
    """
    
    def process_request(self, request):
        """Contrôler l'accès au panel admin Django"""
        
        # Vérifier si c'est une requête vers le panel admin
        if not request.path.startswith('/admin/'):
            return None
        
        # Permettre les assets statiques de l'admin
        if '/admin/static/' in request.path or '/admin/jsi18n/' in request.path:
            return None
        
        # Vérifier l'authentification
        if not request.user.is_authenticated:
            logger.info(f"ACCÈS ADMIN REFUSÉ - Utilisateur non connecté - IP: {self._get_client_ip(request)}")
            return redirect('accounts:login')
        
        # Vérifier les permissions administratives CORRIGÉES
        if not self._has_admin_access(request.user):
            logger.warning(
                f"ACCÈS ADMIN REFUSÉ - {request.user.username} - "
                f"Rôle: {getattr(request.user, 'habilitation', 'N/A')} - "
                f"is_staff: {request.user.is_staff} - "
                f"is_superuser: {request.user.is_superuser}"
            )
            
            messages.error(
                request,
                _("Accès non autorisé au panel d'administration. "
                  "Vous devez avoir des droits administratifs.")
            )
            
            # Journaliser la tentative d'accès refusée avec les VRAIS champs
            try:
                from accounts.models import JournalAudit
                from datetime import timedelta
                
                JournalAudit.objects.create(
                    utilisateur=request.user,
                    action="ACCÈS ADMIN REFUSÉ",
                    details=(f"Tentative d'accès au panel admin sans permissions | "
                           f"URL: {request.path} | "
                           f"Rôle: {getattr(request.user, 'habilitation', 'N/A')} | "
                           f"is_staff: {request.user.is_staff} | "
                           f"is_superuser: {request.user.is_superuser}"),
                    adresse_ip=self._get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                    url_acces=request.path[:500],
                    methode_http=request.method[:10],
                    succes=False,
                    statut_reponse=403,
                    duree_execution=timedelta(seconds=0),
                    session_key=getattr(request.session, 'session_key', '')[:40] if hasattr(request, 'session') else ''
                )
            except Exception as e:
                logger.error(f"Erreur journalisation accès admin refusé: {str(e)}")
            
            # Rediriger vers le dashboard approprié
            return redirect(self._get_user_dashboard_url(request.user))
        
        # Accès autorisé - journaliser
        logger.info(
            f"ACCÈS ADMIN AUTORISÉ - {request.user.username} - "
            f"URL: {request.path}"
        )
        
        return None
    
    def _has_admin_access(self, user):
        """
        Vérifier si l'utilisateur a des droits administratifs
        LOGIQUE CORRIGÉE selon les clarifications
        """
        # Condition 1 : Superutilisateurs (accès complet)
        if user.is_superuser:
            return True
        
        # Condition 2 : Personnel administratif (is_staff)
        if user.is_staff:
            return True
        
        # Condition 3 : Habilitations administratives spécifiques
        if hasattr(user, 'habilitation'):
            admin_roles = [
                'admin_principal',      # Administrateur principal
                'coord_psrr',          # Coordonnateur PSRR
                'serv_info',           # Service informatique
                'serv_emission',       # Service émission et recouvrement
            ]
            
            if user.habilitation in admin_roles:
                return True
        
        # Si aucune condition n'est remplie, pas d'accès
        return False
    
    def _get_user_dashboard_url(self, user):
        """Retourne l'URL du dashboard approprié selon le rôle"""
        if hasattr(user, 'habilitation'):
            # TOUS les rôles administratifs accèdent au dashboard admin
            if self._has_admin_access(user):
                return '/dashboard/admin/'
            elif 'chef' in user.habilitation:
                return '/dashboard/chef/'
            elif user.habilitation == 'agent_inventaire':
                return '/dashboard/agent/'
            else:
                return '/dashboard/'
        
        # Fallback selon les droits Django
        if user.is_staff or user.is_superuser:
            return '/dashboard/admin/'
        
        return '/dashboard/'
    
    def _get_client_ip(self, request):
        """Obtenir l'adresse IP réelle du client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SecurityMiddleware(MiddlewareMixin):
    """Middleware de sécurité - INCHANGÉ"""
    
    SUSPICIOUS_USER_AGENTS = [
        'bot', 'crawler', 'spider', 'scraper', 'scanner',
        'nikto', 'sqlmap', 'nmap', 'masscan'
    ]
    
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_ATTEMPT_WINDOW = 3600
    
    def process_request(self, request):
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        if any(suspicious in user_agent for suspicious in self.SUSPICIOUS_USER_AGENTS):
            logger.warning(
                f"ACTIVITÉ SUSPECTE - User-Agent suspect détecté: {user_agent} - "
                f"IP: {self._get_client_ip(request)} - URL: {request.path}"
            )
        
        if request.path == '/accounts/login/' and request.method == 'POST':
            if self._check_login_attempts(request):
                logger.warning(
                    f"SÉCURITÉ - Trop de tentatives de connexion - "
                    f"IP: {self._get_client_ip(request)}"
                )
                messages.error(
                    request,
                    _("Trop de tentatives de connexion. Veuillez réessayer plus tard.")
                )
                return redirect('accounts:login')
        
        return None
    
    def process_response(self, request, response):
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        if not settings.DEBUG:
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response
    
    def _check_login_attempts(self, request):
        from django.core.cache import cache
        
        ip = self._get_client_ip(request)
        cache_key = f"login_attempts_{ip}"
        
        attempts = cache.get(cache_key, 0)
        
        if attempts >= self.MAX_LOGIN_ATTEMPTS:
            return True
        
        cache.set(cache_key, attempts + 1, self.LOGIN_ATTEMPT_WINDOW)
        return False
    
    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class PerformanceMiddleware(MiddlewareMixin):
    """
    Middleware pour surveiller les performances de l'application
    """
    
    def process_request(self, request):
        """Marquer le début de traitement de la requête"""
        request._start_time = time.time()
    
    def process_response(self, request, response):
        """Calculer et journaliser le temps de traitement"""
        
        if hasattr(request, '_start_time'):
            duration = time.time() - request._start_time
            
            # Journaliser les requêtes lentes (plus de 2 secondes)
            if duration > 2.0:
                logger.warning(
                    f"PERFORMANCE - Requête lente détectée: {duration:.3f}s - "
                    f"URL: {request.path} - "
                    f"Utilisateur: {getattr(request.user, 'username', 'Anonyme')}"
                )
            
            # Ajouter l'en-tête de temps de traitement
            response['X-Response-Time'] = f"{duration:.3f}s"
        
        return response


# ===================================================================
# DÉCORATEURS UTILITAIRES
# ===================================================================

def admin_required(function=None, redirect_url=None):
    """
    Décorateur pour vérifier les permissions administratives
    """
    def check_admin(user):
        if not user.is_authenticated:
            return False
        
        return (
            user.is_superuser or 
            user.is_staff or 
            getattr(user, 'habilitation', None) in [
                'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'
            ]
        )
    
    decorator = user_passes_test(check_admin, login_url=redirect_url)
    
    if function:
        return decorator(function)
    return decorator


def poste_access_required(function=None):
    """
    Décorateur pour vérifier l'accès à un poste spécifique
    """
    def check_poste_access(user):
        # Les admins ont accès à tous les postes
        if user.is_superuser or user.is_staff:
            return True
        
        # Les utilisateurs avec habilitations admin aussi
        if getattr(user, 'habilitation', None) in [
            'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'
        ]:
            return True
        
        # Les autres doivent avoir un poste d'affectation
        return hasattr(user, 'poste_affectation') and user.poste_affectation is not None
    
    decorator = user_passes_test(check_poste_access)
    
    if function:
        return decorator(function)
    return decorator


# ===================================================================
# FONCTIONS UTILITAIRES POUR LES SIGNAUX
# ===================================================================

def log_model_action(action_type, model_name, object_repr, user=None, details=None):
    """
    Fonction utilitaire pour journaliser les actions sur les modèles
    Utilisable depuis les signaux Django - CORRIGÉE avec vrais champs
    """
    try:
        from accounts.models import JournalAudit
        from datetime import timedelta
        
        # Utiliser l'utilisateur du contexte si non fourni
        if user is None:
            user = get_current_user()
        
        # Obtenir la requête actuelle pour plus d'informations
        request = get_current_request()
        
        if user and user.is_authenticated:
            # Construire les détails
            action_details = f"Modèle: {model_name} | Objet: {object_repr}"
            if details:
                action_details += f" | {details}"
            
            # Ajouter des informations de la requête si disponible
            if request:
                action_details += f" | URL: {request.path}"
                action_details += f" | Méthode: {request.method}"
            
            # Calculer la durée
            duration = get_request_duration()
            
            JournalAudit.objects.create(
                utilisateur=user,
                action=action_type,
                details=action_details,
                adresse_ip=get_client_ip_from_request(request) if request else None,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500] if request else '',
                url_acces=request.path[:500] if request else '',
                methode_http=request.method[:10] if request else '',
                succes=True,
                duree_execution=timedelta(seconds=duration),
                statut_reponse=200,  # Action réussie par défaut
                session_key=getattr(request.session, 'session_key', '')[:40] if request and hasattr(request, 'session') else ''
            )
            
            logger.info(f"{action_type} - {user.username} - {model_name}: {object_repr}")
        
    except Exception as e:
        logger.error(f"Erreur journalisation action modèle: {str(e)}")


def get_client_ip_from_request(request):
    """Fonction utilitaire pour obtenir l'IP depuis une requête"""
    if not request:
        return None
    
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# ===================================================================
# MIXINS POUR LES VUES
# ===================================================================

class AuditMixin:
    """
    Mixin pour ajouter automatiquement la journalisation aux vues
    """
    
    def dispatch(self, request, *args, **kwargs):
        """Journaliser l'accès à la vue"""
        view_name = self.__class__.__name__
        action = f"ACCÈS VUE - {view_name}"
        
        if request.user.is_authenticated:
            log_model_action(
                action_type=action,
                model_name="Vue",
                object_repr=view_name,
                user=request.user,
                details=f"Paramètres URL: {kwargs}"
            )
        
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin:
    """
    Mixin pour exiger des permissions administratives
    """
    
    def dispatch(self, request, *args, **kwargs):
        """Vérifier les permissions avant d'accéder à la vue"""
        if not request.user.is_authenticated:
            messages.error(request, _("Vous devez être connecté pour accéder à cette page."))
            return redirect('accounts:login')
        
        # Vérifier les permissions admin
        has_admin_access = (
            request.user.is_superuser or 
            request.user.is_staff or 
            getattr(request.user, 'habilitation', None) in [
                'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'
            ]
        )
        
        if not has_admin_access:
            messages.error(request, _("Accès non autorisé à cette section administrative."))
            return redirect('common:dashboard_general')
        
        return super().dispatch(request, *args, **kwargs)

class AdminRedirectMiddleware:
    """
    Middleware pour gérer la redirection automatique post-connexion
    et bloquer l'accès croisé entre interfaces
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Traitement avant la vue
        response = self.process_request(request)
        if response:
            return response
        
        response = self.get_response(request)
        return response
    
    def process_request(self, request):
        """Gérer les redirections selon les rôles"""
        
        # Vérifier la redirection post-connexion
        if request.user.is_authenticated and 'redirect_after_login' in request.session:
            redirect_url = request.session.pop('redirect_after_login')
            return redirect(redirect_url)
        
        # Bloquer l'accès croisé entre interfaces
        if request.user.is_authenticated:
            return self.check_interface_access(request)
        
        return None
    
    def is_admin_user(self, user):
        """Détermine si un utilisateur est un administrateur"""
        if user.is_superuser or user.is_staff:
            return True
        
        admin_roles = [
            'admin_principal',
            'coord_psrr', 
            'serv_info',
            'serv_emission'
        ]
        
        return getattr(user, 'habilitation', None) in admin_roles
    def check_interface_access(self, request):
        """Vérifier et rediriger si mauvaise interface"""
        
        path = request.path
        user = request.user
        is_admin = self.is_admin_user(user)
        
        # Exclure certaines URLs de la vérification
        excluded_paths = [
            '/static/', '/media/', '/favicon.ico', '/__debug__/',
            '/admin/static/', '/admin/jsi18n/', '/accounts/logout/'
        ]
        
         # RÈGLE 1: Admins ne peuvent PAS accéder à l'interface web normale
        if is_admin and path.startswith('/dashboard/') and not path.startswith('/admin/'):
            logger.warning(
                f"ACCÈS BLOQUÉ - Admin {user.username} tente d'accéder à l'interface web: {path}"
            )
            messages.info(
                request,
                _("Redirection vers votre panel d'administration...")
            )
            return redirect('/admin/')
        
        # RÈGLE 2: Utilisateurs normaux ne peuvent PAS accéder au panel Django
        if not is_admin and path.startswith('/admin/'):
            logger.warning(
                f"ACCÈS BLOQUÉ - Utilisateur {user.username} tente d'accéder au panel admin: {path}"
            )
            messages.info(
                request,
                _("Redirection vers votre interface utilisateur...")
            )
            return redirect('/dashboard/')
        
        # RÈGLE 3: Redirection de la racine selon le rôle
        if path == '/' or path == '/dashboard/':
            if is_admin:
                return redirect('/admin/')
            else:
                # Rediriger vers l'interface appropriée selon le rôle
                if user.habilitation in ['chef_peage', 'chef_pesage']:
                    return redirect('/dashboard/chef/')
                elif user.habilitation == 'agent_inventaire':
                    return redirect('/dashboard/agent/')
                else:
                    return redirect('/dashboard/general/')
        
        return None
    
    