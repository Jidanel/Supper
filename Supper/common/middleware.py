# ===================================================================
# common/middleware.py - VERSION SIMPLIFIÉE
# UNIQUEMENT LOGS MANUELS - PAS DE JOURNALISATION AUTOMATIQUE
# ===================================================================

import logging
import time
import threading
from datetime import timedelta
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponseForbidden

logger = logging.getLogger('supper')

# Thread-local storage pour stocker le contexte utilisateur
_thread_local = threading.local()


class UserContextMiddleware(MiddlewareMixin):
    """
    Middleware pour stocker le contexte utilisateur dans thread-local
    Permet aux signaux et fonctions utilitaires d'accéder à l'utilisateur actuel
    """

    def process_request(self, request):
        """Stocker l'utilisateur actuel dans le contexte thread-local"""
        _thread_local.user = getattr(request, 'user', None)
        _thread_local.request = request
        _thread_local.start_time = time.time()

    def process_response(self, request, response):
        """Calculer la durée à la fin de la requête"""
        if hasattr(_thread_local, 'start_time'):
            duration = time.time() - _thread_local.start_time
            _thread_local.duration = duration
        return response

    def process_exception(self, request, exception):
        """Nettoyer le contexte en cas d'exception"""
        if hasattr(_thread_local, 'user'):
            del _thread_local.user
        if hasattr(_thread_local, 'request'):
            del _thread_local.request


def get_current_user():
    """Récupérer l'utilisateur actuel depuis n'importe où"""
    return getattr(_thread_local, 'user', None)


def get_current_request():
    """Récupérer la requête actuelle"""
    return getattr(_thread_local, 'request', None)


def get_request_duration():
    """Récupérer la durée de la requête"""
    return getattr(_thread_local, 'duration', 0)


def get_client_ip_from_request(request):
    """Obtenir l'IP depuis une requête"""
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class AdminAccessMiddleware(MiddlewareMixin):
    """
    Middleware pour contrôler l'accès au panel d'administration Django
    """

    def process_request(self, request):
        """Contrôler l'accès au panel admin Django"""

        if not request.path.startswith('/admin/'):
            return None

        # Permettre les assets statiques de l'admin
        if '/admin/static/' in request.path or '/admin/jsi18n/' in request.path:
            return None

        # Vérifier l'authentification
        if not request.user.is_authenticated:
            return redirect('/accounts/login/')

        # Vérifier les permissions administratives
        if not self._has_admin_access(request.user):
            logger.warning(f"ACCÈS ADMIN REFUSÉ - {request.user.username}")
            messages.error(request, _("Accès non autorisé au panel d'administration."))
            return redirect(self._get_user_dashboard_url(request.user))

        return None

    def _has_admin_access(self, user):
        """Vérifier si l'utilisateur a des droits administratifs"""
        if user.is_superuser or user.is_staff:
            return True

        if hasattr(user, 'habilitation'):
            admin_roles = ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission']
            if user.habilitation in admin_roles:
                return True

        return False

    def _get_user_dashboard_url(self, user):
        """Retourne l'URL du dashboard approprié selon le rôle"""
        if hasattr(user, 'habilitation'):
            if self._has_admin_access(user):
                return '/dashboard/admin/'
            elif 'chef' in user.habilitation:
                return '/dashboard/chef/'
            elif user.habilitation == 'agent_inventaire':
                return '/dashboard/agent/'
        return '/dashboard/'


class SecurityMiddleware(MiddlewareMixin):
    """Middleware de sécurité : en-têtes + limitation des ÉCHECS de connexion"""

    # Mots suspects dans le User-Agent (simple journalisation)
    SUSPICIOUS_USER_AGENTS = ['bot', 'crawler', 'spider', 'scraper', 'scanner', 'nikto', 'sqlmap']
    # Nombre d'ÉCHECS autorisés avant blocage (par IP + matricule)
    MAX_LOGIN_ATTEMPTS = 10
    # Durée du blocage / de la fenêtre de comptage, en secondes (15 min)
    LOGIN_ATTEMPT_WINDOW = 900

    def _cle_login(self, request):
        """Construit la clé de cache : IP + matricule saisi"""
        ip = get_client_ip_from_request(request)  # IP du client
        # Le champ peut s'appeler 'username' ou 'matricule' selon le formulaire
        matricule = (request.POST.get('username') or request.POST.get('matricule') or '').strip().lower()
        return f"login_echecs_{ip}_{matricule}"  # clé unique par IP + matricule

    def process_request(self, request):
        # Journaliser les User-Agents suspects (sans bloquer)
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        if any(suspicious in user_agent for suspicious in self.SUSPICIOUS_USER_AGENTS):
            logger.warning(f"ACTIVITÉ SUSPECTE - User-Agent: {user_agent}")

        # Vérifier uniquement les envois du formulaire de connexion
        if request.path == '/accounts/login/' and request.method == 'POST':
            from django.core.cache import cache
            request._login_cle = self._cle_login(request)  # mémoriser la clé pour process_response
            # Trop d'échecs déjà enregistrés pour ce couple IP + matricule ?
            if cache.get(request._login_cle, 0) >= self.MAX_LOGIN_ATTEMPTS:
                request._login_bloque = True  # marquer : ne pas recompter ce blocage
                messages.error(request, _("Trop de tentatives de connexion. Réessayez plus tard."))
                return redirect('/accounts/login/')
        return None

    def process_response(self, request, response):
        # Compter les échecs / réinitialiser sur succès (uniquement POST login non bloqué)
        if (request.path == '/accounts/login/' and request.method == 'POST'
                and hasattr(request, '_login_cle') and not getattr(request, '_login_bloque', False)):
            from django.core.cache import cache
            if response.status_code == 302:
                # Redirection = connexion réussie → on efface le compteur
                cache.delete(request._login_cle)
            else:
                # Page réaffichée (200) = identifiants refusés → +1 échec
                cache.set(request._login_cle, cache.get(request._login_cle, 0) + 1,
                          self.LOGIN_ATTEMPT_WINDOW)

        # En-têtes de sécurité (inchangés)
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        return response

class PerformanceMiddleware(MiddlewareMixin):
    """Middleware pour surveiller les performances"""

    def process_request(self, request):
        request._start_time = time.time()

    def process_response(self, request, response):
        if hasattr(request, '_start_time'):
            duration = time.time() - request._start_time
            if duration > 2.0:
                logger.warning(f"PERFORMANCE - Requête lente: {duration:.3f}s - URL: {request.path}")
            response['X-Response-Time'] = f"{duration:.3f}s"
        return response


# ===================================================================
# DÉCORATEURS UTILITAIRES
# ===================================================================

def admin_required(function=None, redirect_url=None):
    """Décorateur pour vérifier les permissions administratives"""
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
    """Décorateur pour vérifier l'accès à un poste"""
    def check_poste_access(user):
        if user.is_superuser or user.is_staff:
            return True
        if getattr(user, 'habilitation', None) in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission']:
            return True
        return hasattr(user, 'poste_affectation') and user.poste_affectation is not None

    decorator = user_passes_test(check_poste_access)
    if function:
        return decorator(function)
    return decorator


# ===================================================================
# MIXINS POUR LES VUES
# ===================================================================

class AdminRequiredMixin:
    """Mixin pour exiger des permissions administratives"""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, _("Vous devez être connecté."))
            return redirect('/accounts/login/')

        has_admin = (
            request.user.is_superuser or
            request.user.is_staff or
            getattr(request.user, 'habilitation', None) in [
                'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'
            ]
        )

        if not has_admin:
            messages.error(request, _("Accès non autorisé."))
            return redirect('/')

        return super().dispatch(request, *args, **kwargs)