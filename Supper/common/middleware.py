# ===================================================================
# common/middleware.py - VERSION COMPLÈTE ET CORRIGÉE
# REMPLACER ENTIÈREMENT LE FICHIER EXISTANT
# ===================================================================

import logging
import json
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
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.urls import resolve, reverse

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
        
        # CORRECTION: Ne pas bloquer l'accès admin pour les superusers
        if request.path.startswith('/admin/') and request.user.is_authenticated:
            if not (request.user.is_superuser or request.user.is_staff or 
                    getattr(request.user, 'habilitation', '') == 'admin_principal'):
                logger.warning(f"Tentative accès admin bloquée: {request.user.username}")
                return HttpResponseForbidden("Accès administrateur non autorisé")
        
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
        """
        Traitement des réponses sortantes
        MODIFIÉ : Détecte les logs manuels pour éviter duplication
        """
        
        # Calculer la durée de traitement
        if hasattr(request, '_audit_start_time'):
            duration = time.time() - request._audit_start_time
            request._audit_duration = duration
        
        # Ignorer si pas d'utilisateur connecté ou requête à ignorer
        if not hasattr(request, '_audit_info') or self._should_ignore_request(request):
            return response
        
        # ===================================================================
        # NOUVEAU : DÉTECTION DES LOGS MANUELS
        # ===================================================================
        # Si un log manuel a été créé dans la vue (via log_user_action),
        # ne pas créer un log automatique pour éviter la duplication
        if hasattr(request, '_has_manual_log') and request._has_manual_log:
            logger.debug(
                f"Log manuel détecté pour {request.path}, "
                f"skip middleware automatic logging"
            )
            # Le log manuel contient déjà tous les détails nécessaires
            return response
        
        # ===================================================================
        # JOURNALISATION AUTOMATIQUE (si pas de log manuel)
        # ===================================================================
        # Journaliser les actions importantes
        if self._is_important_action(request, response):
            self._log_detailed_action(request, response)
        
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
            '/inventaire/',
            '/recette/',
            '/admin/',
            '/dashboard/',
            '/reports/',
            '/programmation/',
        ]
        
        if any(path in request.path for path in important_paths):
            return True
        
        # Codes de réponse d'erreur
        if response.status_code >= 400:
            return True
        
        return False
    
    def _log_detailed_action(self, request, response):
        """Enregistre l'action avec des détails précis sur qui fait quoi"""
        
        try:
            from accounts.models import JournalAudit
            
            audit_info = request._audit_info
            user = audit_info['user']
            
            # Déterminer l'action précise avec contexte
            action, details = self._build_detailed_action(request, response, user)
            
            # Calculer la durée si disponible
            duration = getattr(request, '_audit_duration', None)
            if duration:
                from datetime import timedelta
                duration_obj = timedelta(seconds=duration)
            else:
                duration_obj = None
            
            # Créer l'entrée de journal détaillée
            JournalAudit.objects.create(
                utilisateur=user,
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
                f"Action détaillée: {action} | {details} | "
                f"Utilisateur: {user.username} ({user.nom_complet}) | "
                f"IP: {audit_info['ip']} | Status: {response.status_code}"
            )
            
        except Exception as e:
            logger.error(f"Erreur lors de la journalisation détaillée: {str(e)}")
    
    def _build_detailed_action(self, request, response, user):
        """
        Construit une description détaillée de l'action effectuée
        
        CORRECTION IMPORTANTE :
        Ordre de vérification modifié pour éviter les faux positifs
        Ex: /inventaire/recettes/ doit être détecté comme RECETTE, pas inventaire
        """
        
        path = request.path.lower()
        method = request.method
        username = f"{user.nom_complet} ({user.username})"
        role = user.get_habilitation_display()
        
        # Essayer de résoudre l'URL pour obtenir les paramètres
        try:
            resolved = resolve(request.path)
            view_kwargs = resolved.kwargs
        except:
            view_kwargs = {}
        
        # ===================================================================
        # ORDRE IMPORTANT : Vérifier d'abord les URLs SPÉCIFIQUES
        # puis les génériques pour éviter les faux positifs
        # ===================================================================
        
        # Actions de connexion/déconnexion
        if 'login' in path:
            if response.status_code == 302:
                return "Connexion réussie", f"{username} ({role}) s'est connecté avec succès"
            else:
                return "Tentative de connexion échouée", f"{username} a tenté de se connecter sans succès"
        
        if 'logout' in path:
            return "Déconnexion", f"{username} s'est déconnecté"
        
        # ===================================================================
        # PRIORITÉ 1 : RECETTES (avant inventaire car URL = /inventaire/recettes/)
        # ===================================================================
        if 'recette' in path:
            poste_id = view_kwargs.get('poste_id') or request.POST.get('poste') or request.GET.get('poste')
            date = request.POST.get('date', '') or request.GET.get('date', '')
            montant = request.POST.get('montant_declare', '')
            
            # Récupérer le nom du poste si disponible
            poste_nom = "Poste non spécifié"
            if poste_id:
                try:
                    from accounts.models import Poste
                    poste = Poste.objects.get(id=poste_id)
                    poste_nom = poste.nom
                except:
                    poste_nom = f"Poste ID {poste_id}"
            
            # Distinction fine des actions sur recettes
            if method == 'POST':
                if 'saisie' in path or 'saisir' in path:
                    return "Saisie recette", f"{username} a saisi la recette du {poste_nom} pour le {date}: {montant} FCFA"
                elif 'modifier' in path or 'edit' in path:
                    return "Modification recette", f"{username} a modifié la recette du {poste_nom} pour le {date}"
                elif 'supprimer' in path or 'delete' in path:
                    return "Suppression recette", f"{username} a supprimé la recette du {poste_nom}"
                else:
                    return "Création recette", f"{username} a créé une recette pour {poste_nom}"
            
            elif method == 'PUT':
                return "Modification recette", f"{username} a modifié la recette du {poste_nom}"
            
            elif method == 'DELETE':
                return "Suppression recette", f"{username} a supprimé la recette du {poste_nom}"
            
            elif method == 'GET':
                # Distinction entre différentes pages recettes
                if 'statistiques' in path or 'stats' in path:
                    periode = request.GET.get('periode', 'non spécifiée')
                    return "Consultation statistiques recettes", f"{username} a consulté les statistiques de recettes pour la période {periode}"
                
                elif 'liste' in path or path.endswith('/recettes/') or path.endswith('/recettes'):
                    # Liste complète des recettes
                    return "Consultation liste recettes", f"{username} a consulté la liste des recettes"
                
                elif view_kwargs.get('pk') or view_kwargs.get('recette_id'):
                    # Détail d'une recette spécifique
                    return "Consultation détail recette", f"{username} a consulté le détail d'une recette du {poste_nom}"
                
                else:
                    return "Consultation recettes", f"{username} a consulté la page des recettes"
        
        # ===================================================================
        # PRIORITÉ 2 : QUITTANCEMENTS (avant inventaire)
        # ===================================================================
        if 'quittancement' in path or 'quittance' in path:
            poste_id = view_kwargs.get('poste_id') or request.POST.get('poste')
            numero = request.POST.get('numero_quittance', '') or request.GET.get('numero', '')
            
            poste_nom = "Poste non spécifié"
            if poste_id:
                try:
                    from accounts.models import Poste
                    poste = Poste.objects.get(id=poste_id)
                    poste_nom = poste.nom
                except:
                    poste_nom = f"Poste ID {poste_id}"
            
            if method == 'POST':
                if 'justification' in path:
                    return "Justification écart quittancement", f"{username} a justifié un écart pour {poste_nom}"
                elif 'image' in path or 'upload' in path:
                    return "Ajout image quittancement", f"{username} a ajouté/modifié l'image du quittancement N°{numero}"
                else:
                    return "Création quittancement", f"{username} a créé un quittancement N°{numero} pour {poste_nom}"
            
            elif method == 'GET':
                if 'comptabilisation' in path:
                    return "Consultation comptabilisation quittancements", f"{username} a consulté la comptabilisation des quittancements"
                elif 'authentification' in path or 'verif' in path:
                    return "Authentification document", f"{username} a vérifié l'authenticité d'un document"
                elif 'detail' in path:
                    return "Consultation détails quittancements", f"{username} a consulté les détails des quittancements"
                else:
                    return "Consultation quittancements", f"{username} a consulté les quittancements"
        
        # ===================================================================
        # PRIORITÉ 3 : PROGRAMMATION (avant inventaire)
        # ===================================================================
        if 'programmation' in path:
            if method == 'POST':
                postes = request.POST.getlist('postes', [])
                mois = request.POST.get('mois', '')
                motif = request.POST.get('motif', '')
                return "Programmation inventaire", f"{username} a programmé un inventaire pour {len(postes)} poste(s) en {mois} - Motif: {motif}"
            else:
                return "Consultation programmations", f"{username} a consulté les programmations d'inventaires"
        
        # ===================================================================
        # PRIORITÉ 4 : INVENTAIRE (après recettes/quittancements/programmation)
        # ===================================================================
        if 'inventaire' in path:
            poste_id = view_kwargs.get('poste_id') or request.POST.get('poste') or request.GET.get('poste')
            date = request.POST.get('date', '') or request.GET.get('date', '')
            
            poste_nom = "Poste non spécifié"
            if poste_id:
                try:
                    from accounts.models import Poste
                    poste = Poste.objects.get(id=poste_id)
                    poste_nom = poste.nom
                except:
                    poste_nom = f"Poste ID {poste_id}"
            
            if method == 'POST':
                if 'saisie' in path or 'saisir' in path:
                    return "Saisie inventaire", f"{username} a saisi l'inventaire du {poste_nom} pour le {date}"
                elif 'modifier' in path or 'edit' in path:
                    return "Modification inventaire", f"{username} a modifié l'inventaire du {poste_nom} pour le {date}"
                elif 'consolider' in path or 'consolidation' in path:
                    mois = request.POST.get('mois', '')
                    annee = request.POST.get('annee', '')
                    return "Consolidation inventaire", f"{username} a consolidé l'inventaire de {poste_nom} pour {mois}/{annee}"
                else:
                    return "Création inventaire", f"{username} a créé un inventaire pour {poste_nom}"
            
            elif method == 'PUT':
                return "Modification inventaire", f"{username} a modifié l'inventaire du {poste_nom}"
            
            elif method == 'DELETE':
                return "Suppression inventaire", f"{username} a supprimé l'inventaire du {poste_nom}"
            
            elif method == 'GET':
                # Distinction entre différentes pages inventaires
                if 'liste' in path or 'index' in path or path.endswith('/inventaires/') or path.endswith('/inventaire/'):
                    return "Consultation liste inventaires", f"{username} a consulté la liste des inventaires"
                
                elif 'mensuel' in path or 'consolidation' in path:
                    return "Consultation inventaires mensuels", f"{username} a consulté les inventaires mensuels consolidés"
                
                elif view_kwargs.get('pk') or view_kwargs.get('inventaire_id'):
                    return "Consultation détail inventaire", f"{username} a consulté le détail d'un inventaire du {poste_nom}"
                
                else:
                    return "Consultation inventaires", f"{username} a consulté la page des inventaires"
        
        # ===================================================================
        # ACTIONS ADMINISTRATIVES
        # ===================================================================
        if 'admin' in path or '/administration/' in path:
            if 'utilisateur' in path or 'user' in path or 'accounts' in path:
                if method == 'POST':
                    return "Gestion utilisateurs", f"{username} a modifié les utilisateurs"
                else:
                    return "Consultation utilisateurs", f"{username} a consulté la liste des utilisateurs"
            
            elif 'poste' in path and '/admin/' in path:
                if method == 'POST':
                    return "Gestion postes", f"{username} a modifié les postes"
                else:
                    return "Consultation postes", f"{username} a consulté la liste des postes"
            
            elif 'journal' in path or 'audit' in path:
                return "Consultation journal d'audit", f"{username} a consulté le journal d'audit"
            
            else:
                return "Administration", f"{username} a accédé au panel d'administration"
        
        # ===================================================================
        # CONFIGURATION JOURS
        # ===================================================================
        if 'configuration' in path or 'config-jour' in path:
            if method == 'POST':
                date_config = request.POST.get('date', '')
                statut = request.POST.get('statut', '')
                return "Configuration jour", f"{username} a configuré le jour {date_config} avec le statut {statut}"
            else:
                return "Consultation configuration jours", f"{username} a consulté la configuration des jours"
        
        # ===================================================================
        # TABLEAU DE BORD
        # ===================================================================
        if 'dashboard' in path:
            if 'admin' in path:
                return "Accès dashboard administrateur", f"{username} a accédé au tableau de bord administrateur"
            elif 'chef' in path:
                return "Accès dashboard chef de poste", f"{username} a accédé au tableau de bord chef de poste"
            elif 'agent' in path:
                return "Accès dashboard agent", f"{username} a accédé au tableau de bord agent"
            else:
                return "Accès tableau de bord", f"{username} ({role}) a accédé à son tableau de bord"
        
        # ===================================================================
        # RAPPORTS
        # ===================================================================
        if 'report' in path or 'rapport' in path:
            type_rapport = request.GET.get('type', 'général')
            periode = request.GET.get('periode', '')
            format_export = request.GET.get('format', 'HTML')
            return "Génération rapport", f"{username} a généré un rapport {type_rapport} pour {periode} (format: {format_export})"
        
        # ===================================================================
        # STOCKS
        # ===================================================================
        if 'stock' in path:
            if 'psrr' in path:
                return "Gestion stocks PSRR", f"{username} a accédé à la gestion des stocks PSRR"
            elif 'informatique' in path or 'info' in path:
                return "Gestion stock informatique", f"{username} a accédé à la gestion du stock informatique"
            else:
                return "Gestion stocks", f"{username} a accédé à la gestion des stocks"
        
        # ===================================================================
        # PÉAGE/PESAGE
        # ===================================================================
        if 'peage' in path:
            return "Gestion péage", f"{username} a accédé à la gestion du péage"
        
        if 'pesage' in path:
            return "Gestion pesage", f"{username} a accédé à la gestion du pesage"
        
        # ===================================================================
        # ACTION GÉNÉRIQUE (fallback)
        # ===================================================================
        return f"{method} {path}", f"{username} ({role}) a effectué une action {method} sur {path}"
    def _get_client_ip(self, request):
        """Récupère l'adresse IP réelle du client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def _build_action_details(self, request, response):
        """Construit les détails de l'action pour le journal"""
        
        details_list = [
            f"URL: {request.path}",
            f"Méthode: {request.method}",
            f"Statut: {response.status_code}",
            f"Timestamp: {timezone.now().isoformat()}"
        ]
        
        # Ajouter les paramètres GET si pertinents
        if request.GET:
            get_params = dict(request.GET)
            # Filtrer les paramètres sensibles
            sensitive_params = ['password', 'token', 'key']
            for param in sensitive_params:
                get_params.pop(param, None)
            
            if get_params:
                details_list.append(f"Paramètres GET: {get_params}")
        
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
                details_list.append(f"Données POST: {post_data}")
        
        # Informations sur les erreurs
        if response.status_code >= 400:
            details_list.append(f"Erreur HTTP {response.status_code}")
            
            if response.status_code == 403:
                details_list.append("Accès interdit - permissions insuffisantes")
            elif response.status_code == 404:
                details_list.append("Ressource non trouvée")
            elif response.status_code == 500:
                details_list.append("Erreur interne du serveur")
        
        # Informations de session
        if hasattr(request, 'session') and request.session.session_key:
            details_list.append(f"Session: {request.session.session_key}")
            details_list.append(f"Session Age: {request.session.get_expiry_age()}")
        
        # Retourner une chaîne formatée lisible
        return " | ".join(details_list)



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
            return redirect('/accounts/login/')
        
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
            
            # Journaliser la tentative d'accès refusée
            try:
                from accounts.models import JournalAudit
                
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
    """Middleware de sécurité"""
    
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
                return redirect('/accounts/login/')
        
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
# FONCTIONS UTILITAIRES POUR LES SIGNAUX
# ===================================================================

def log_model_action(action_type, model_name, object_repr, user=None, details=None):
    """
    Fonction utilitaire pour journaliser les actions sur les modèles
    Utilisable depuis les signaux Django - CORRIGÉE avec vrais champs
    """
    try:
        from accounts.models import JournalAudit
        
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
            return redirect('/accounts/login/')
        
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
            return redirect('/')
        
        return super().dispatch(request, *args, **kwargs)


class AdminRedirectMiddleware(MiddlewareMixin):
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
        
        if any(excluded in path for excluded in excluded_paths):
            return None
        
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