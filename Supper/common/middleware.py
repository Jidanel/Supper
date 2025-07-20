# ===================================================================
# common/middleware.py - Middleware de journalisation SUPPER
# ===================================================================

import logging
import json
import time
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


# Configuration du logger spécifique à SUPPER
logger = logging.getLogger('supper')


class AuditMiddleware(MiddlewareMixin):
    """
    Middleware personnalisé pour la journalisation automatique
    des actions utilisateur dans l'application SUPPER
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_request(self, request):
        """Traitement des requêtes entrantes"""
        
        # Marquer le début du traitement
        request._audit_start_time = time.time()
        
        # Ignorer les requêtes pour les fichiers statiques et certaines URLs
        if self._should_ignore_request(request):
            return None
        
        # Enregistrer les informations de session pour les utilisateurs connectés
        if hasattr(request, 'user') and not isinstance(request.user, AnonymousUser):
            session_key = request.session.session_key or 'unknown'
            request._audit_info = {
                'user': request.user,
                'ip': self._get_client_ip(request),
                'session': session_key,
                'path': request.path,
                'method': request.method,
                'user_agent': request.META.get('HTTP_USER_AGENT', 'Unknown')[:500]
            }
        
        return None
    
    def process_response(self, request, response):
        """Traitement des réponses sortantes"""
        
        # Calculer la durée de traitement
        if hasattr(request, '_audit_start_time'):
            duration = time.time() - request._audit_start_time
            request._audit_duration = duration
        
        # Ignorer si pas d'utilisateur connecté ou requête à ignorer
        if not hasattr(request, '_audit_info') or self._should_ignore_request(request):
            return response
        
        # Journaliser les actions importantes
        if self._is_important_action(request, response):
            self._log_action(request, response)
        
        return response
    
    def _should_ignore_request(self, request):
        """Détermine si la requête doit être ignorée pour la journalisation"""
        ignore_paths = [
            '/static/',
            '/media/',
            '/favicon.ico',
            '/admin/jsi18n/',
            '__debug__',
            '/api/heartbeat/',
            '/health/',
        ]
        
        # Ignorer les requêtes AJAX de mise à jour automatique fréquentes
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and request.method == 'GET':
            ajax_ignore_paths = ['/api/notifications/', '/api/status/']
            if any(ignore_path in request.path for ignore_path in ajax_ignore_paths):
                return True
        
        return any(ignore_path in request.path for ignore_path in ignore_paths)
    
    def _is_important_action(self, request, response):
        """Détermine si l'action mérite d'être journalisée"""
        
        # Toutes les méthodes de modification
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            return True
        
        # Pages importantes même en GET
        important_paths = [
            '/accounts/login/',
            '/accounts/logout/',
            '/inventaire/saisie/',
            '/recette/saisie/',
            '/admin/',
            '/dashboard/',
            '/reports/',
        ]
        
        if any(path in request.path for path in important_paths):
            return True
        
        # Codes de réponse d'erreur
        if response.status_code >= 400:
            return True
        
        return False
    
    def _log_action(self, request, response):
        """Enregistre l'action dans le journal d'audit"""
        
        try:
            from accounts.models import JournalAudit
            
            audit_info = request._audit_info
            action = self._determine_action(request, response)
            details = self._build_action_details(request, response)
            
            # Calculer la durée si disponible
            duration = getattr(request, '_audit_duration', None)
            if duration:
                from datetime import timedelta
                duration_obj = timedelta(seconds=duration)
            else:
                duration_obj = None
            
            # Créer l'entrée de journal
            JournalAudit.objects.create(
                utilisateur=audit_info['user'],
                action=action,
                details=details,
                adresse_ip=audit_info['ip'],
                user_agent=audit_info['user_agent'],
                session_key=audit_info['session'],
                url_acces=audit_info['path'],
                methode_http=audit_info['method'],
                statut_reponse=response.status_code,
                succes=response.status_code < 400,
                duree_execution=duration_obj
            )
            
            # Log dans le fichier système aussi
            logger.info(
                f"Action: {action} | Utilisateur: {audit_info['user'].username} | "
                f"IP: {audit_info['ip']} | Path: {audit_info['path']} | "
                f"Status: {response.status_code} | "
                f"Durée: {duration:.3f}s" if duration else "Durée: N/A"
            )
            
        except Exception as e:
            # Ne pas interrompre l'application si le logging échoue
            logger.error(f"Erreur lors de la journalisation: {str(e)}")
    
    def _determine_action(self, request, response):
        """Détermine le type d'action effectuée"""
        
        path = request.path.lower()
        method = request.method
        
        # Actions de connexion/déconnexion
        if 'login' in path:
            if response.status_code == 302:  # Redirection = succès
                return "Connexion réussie"
            else:
                return "Tentative de connexion échouée"
        
        if 'logout' in path:
            return "Déconnexion"
        
        # Actions sur l'inventaire
        if 'inventaire' in path:
            if method == 'POST':
                return "Saisie inventaire"
            elif method == 'PUT':
                return "Modification inventaire"
            elif method == 'DELETE':
                return "Suppression inventaire"
            else:
                return "Consultation inventaire"
        
        # Actions sur les recettes
        if 'recette' in path:
            if method == 'POST':
                return "Saisie recette"
            elif method == 'PUT':
                return "Modification recette"
            else:
                return "Consultation recette"
        
        # Actions administratives
        if 'admin' in path or 'user' in path:
            if method == 'POST':
                return "Action administrative"
            else:
                return "Consultation administration"
        
        # Tableau de bord
        if 'dashboard' in path:
            return "Accès tableau de bord"
        
        # Rapports
        if 'report' in path:
            return "Génération rapport"
        
        # Action générique
        return f"{method} {path}"
    
    def _build_action_details(self, request, response):
        """Construit les détails de l'action pour le journal"""
        
        details = {
            'url': request.path,
            'method': request.method,
            'status_code': response.status_code,
            'timestamp': timezone.now().isoformat(),
        }
        
        # Ajouter les paramètres GET si pertinents
        if request.GET:
            get_params = dict(request.GET)
            # Filtrer les paramètres sensibles
            sensitive_params = ['password', 'token', 'key']
            for param in sensitive_params:
                get_params.pop(param, None)
            
            if get_params:
                details['parametres_get'] = get_params
        
        # Ajouter les données POST si pertinentes (sans mots de passe)
        if request.method == 'POST' and hasattr(request, 'POST'):
            post_data = dict(request.POST)
            # Supprimer les champs sensibles
            sensitive_fields = [
                'password', 'password1', 'password2', 'csrfmiddlewaretoken',
                'old_password', 'new_password1', 'new_password2'
            ]
            for field in sensitive_fields:
                post_data.pop(field, None)
            
            if post_data:
                details['donnees_post'] = post_data
        
        # Informations sur les erreurs
        if response.status_code >= 400:
            details['erreur'] = f"Code d'erreur HTTP {response.status_code}"
            
            if response.status_code == 403:
                details['erreur_details'] = "Accès interdit - permissions insuffisantes"
            elif response.status_code == 404:
                details['erreur_details'] = "Ressource non trouvée"
            elif response.status_code == 500:
                details['erreur_details'] = "Erreur interne du serveur"
        
        # Informations de session
        if hasattr(request, 'session'):
            details['session_info'] = {
                'session_key': request.session.session_key,
                'session_age': request.session.get_expiry_age(),
            }
        
        return json.dumps(details, ensure_ascii=False, default=str)
    
    def _get_client_ip(self, request):
        """Récupère l'adresse IP réelle du client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip



class AdminAccessMiddleware(MiddlewareMixin):
    """
    Middleware pour contrôler l'accès au panel d'administration Django
    Seuls les administrateurs principaux peuvent y accéder
    """
    
    def process_request(self, request):
        # Vérifier si la requête concerne le panel admin Django
        if request.path.startswith('/admin/'):
            # Permettre l'accès aux fichiers statiques de l'admin
            if request.path.startswith('/admin/jsi18n/') or \
               request.path.startswith('/admin/static/'):
                return None
            
            # Vérifier que l'utilisateur est connecté
            if not request.user.is_authenticated:
                return None  # Laisser Django gérer la redirection de connexion
            
            # Vérifier que l'utilisateur est admin principal
            if not self._is_admin_principal(request.user):
                messages.error(
                    request, 
                    "Accès interdit. Seuls les administrateurs principaux "
                    "peuvent accéder au panel d'administration Django. "
                    "Utilisez l'interface SUPPER dédiée à votre rôle."
                )
                
                # Log de la tentative d'accès
                from common.utils import log_user_action
                log_user_action(
                    request.user,
                    "ACCÈS REFUSÉ - Panel Admin Django",
                    f"Tentative d'accès au panel admin par {request.user.habilitation}",
                    request
                )
                
                # Rediriger vers le dashboard SUPPER approprié
                return redirect(self._get_user_dashboard_url(request.user))
        
        return None
    
    def _is_admin_principal(self, user):
        """Vérifie si l'utilisateur est un administrateur principal"""
        return (
            user.is_superuser and 
            hasattr(user, 'habilitation') and 
            user.habilitation == 'admin_principal'
        )
    
    def _get_user_dashboard_url(self, user):
        """Retourne l'URL du dashboard approprié selon le rôle"""
        if hasattr(user, 'habilitation'):
            if user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info']:
                return '/dashboard/admin/'
            elif 'chef' in user.habilitation:
                return '/dashboard/chef/'
            elif user.habilitation == 'agent_inventaire':
                return '/dashboard/agent/'
            else:
                return '/dashboard/'
        
        return '/dashboard/'


