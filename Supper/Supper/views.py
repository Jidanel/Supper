# ===================================================================
# Fichier : Supper/views.py - Vues principales et gestion d'erreurs
# Vues système pour la page d'accueil et gestion des erreurs
# ===================================================================

from django.shortcuts import redirect
from django.views.generic import View, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponse
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.utils import timezone
import logging

logger = logging.getLogger('supper')


class HomeView(View):
    """
    Vue d'accueil avec redirection intelligente selon le rôle utilisateur
    CORRIGÉE - Problème de routage dashboard admin résolu
    """
    
    def get(self, request):
        """Redirection automatique selon le profil utilisateur connecté"""
        
        if request.user.is_authenticated:
            user = request.user
            
            # Message de bienvenue personnalisé
            messages.success(
                request, 
                _("Bienvenue %(nom)s ! Redirection vers votre espace de travail...") % {'nom': user.nom_complet}
            )
            
            # DEBUG: Logs pour diagnostiquer les problèmes de routage
            logger.info(
                f"ROUTAGE DASHBOARD - Utilisateur: {user.username} | "
                f"is_superuser: {user.is_superuser} | "
                f"is_staff: {user.is_staff} | "
                f"habilitation: {user.habilitation}"
            )
            
            # ================================================================
            # LOGIQUE DE ROUTAGE CORRIGÉE
            # ================================================================
            
            # PRIORITÉ 1: Super utilisateurs → Dashboard admin TOUJOURS
            if user.is_superuser:
                logger.info(f"REDIRECTION SUPER ADMIN: {user.username} → dashboard_admin")
                return redirect('common:dashboard_admin')
            
            # PRIORITÉ 2: Staff Django → Dashboard admin
            elif user.is_staff:
                logger.info(f"REDIRECTION STAFF: {user.username} → dashboard_admin")
                return redirect('common:dashboard_admin')
            
            # PRIORITÉ 3: Habilitations administratives → Dashboard admin
            elif user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission']:
                logger.info(f"REDIRECTION ADMIN HABILITATION: {user.username} → dashboard_admin")
                return redirect('common:dashboard_admin')
            
            # PRIORITÉ 4: Chefs de poste → Dashboard chef (DÉSACTIVÉ TEMPORAIREMENT)
            elif user.habilitation in ['chef_peage', 'chef_pesage']:
                logger.info(f"REDIRECTION CHEF DÉSACTIVÉE: {user.username} → dashboard_general")
                messages.warning(
                    request, 
                    _("Interface chef de poste en cours de développement. Accès temporairement au dashboard général.")
                )
                return redirect('common:dashboard_general')
            
            # PRIORITÉ 5: Agents inventaire → Dashboard agent (DÉSACTIVÉ TEMPORAIREMENT)
            elif user.habilitation == 'agent_inventaire':
                logger.info(f"REDIRECTION AGENT DÉSACTIVÉE: {user.username} → dashboard_general")
                messages.warning(
                    request, 
                    _("Interface agent inventaire en cours de développement. Accès temporairement au dashboard général.")
                )
                return redirect('common:dashboard_general')
            
            # PRIORITÉ 6: Autres rôles → Dashboard général
            else:
                logger.info(f"REDIRECTION GÉNÉRAL: {user.username} → dashboard_general (habilitation: {user.habilitation})")
                return redirect('common:dashboard_general')
        
        else:
            # Utilisateur non connecté : rediriger vers la page de connexion
            logger.info("REDIRECTION LOGIN - Utilisateur non connecté")
            return redirect('accounts:login')

class StatusView(View):
    """
    Vue de statut pour monitoring externe de l'application
    Endpoint simple pour vérifier que l'application fonctionne
    """
    
    def get(self, request):
        """
        Retourne le statut de l'application
        Returns:
            JsonResponse: Statut de l'application avec informations basiques
        """
        try:
            # Vérification basique de la base de données
            from accounts.models import UtilisateurSUPPER
            user_count = UtilisateurSUPPER.objects.count()
            
            # Informations de statut
            status_data = {
                'status': 'ok',
                'timestamp': timezone.now().isoformat(),
                'version': '1.0.0',
                'database': 'connected',
                'users_count': user_count,
                'environment': 'development' if settings.DEBUG else 'production'
            }
            
            return JsonResponse(status_data)
            
        except Exception as e:
            logger.error(f"Erreur status check: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'timestamp': timezone.now().isoformat(),
                'error': 'Database connection failed'
            }, status=500)


# ===================================================================
# VUES D'ERREUR PERSONNALISÉES
# ===================================================================

class Error403View(TemplateView):
    """
    Vue d'erreur 403 - Accès interdit personnalisée
    Affichage convivial avec suggestions d'actions
    """
    
    template_name = 'errors/403.html'
    
    def get_context_data(self, **kwargs):
        """Ajoute des informations contextuelles à l'erreur 403"""
        context = super().get_context_data(**kwargs)
        
        # Suggestions d'actions selon l'utilisateur
        suggestions = []
        
        if self.request.user.is_authenticated:
            user = self.request.user
            suggestions.extend([
                _("Vérifiez que vous avez les permissions nécessaires"),
                _("Contactez votre administrateur si vous pensez que c'est une erreur"),
                f"Retour à votre {self._get_user_dashboard_name(user)}"
            ])
        else:
            suggestions.extend([
                _("Connectez-vous avec votre compte SUPPER"),
                _("Vérifiez que l'URL est correcte"),
                _("Contactez l'administrateur système si le problème persiste")
            ])
        
        context.update({
            'error_code': '403',
            'error_title': _('Accès Interdit'),
            'error_message': _('Vous n\'avez pas les permissions nécessaires pour accéder à cette page.'),
            'suggestions': suggestions,
            'support_email': 'admin@supper.cm',  # À configurer selon l'environnement
            'dashboard_url': self._get_user_dashboard_url()
        })
        
        return context
    
    def _get_user_dashboard_name(self, user):
        """Retourne le nom du dashboard approprié"""
        if user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info'] or user.is_superuser or user.is_staff:
            return _("tableau de bord administrateur")
        elif user.habilitation in ['chef_peage', 'chef_pesage']:
            return _("tableau de bord chef de poste")
        elif user.habilitation == 'agent_inventaire':
            return _("interface de saisie")
        else:
            return _("tableau de bord")
    
    def _get_user_dashboard_url(self):
        """Retourne l'URL du dashboard approprié"""
        if self.request.user.is_authenticated:
            user = self.request.user
            if user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info'] or user.is_superuser or user.is_staff:
                return '/dashboard/admin/'
            elif user.habilitation in ['chef_peage', 'chef_pesage']:
                return '/dashboard/chef/'
            elif user.habilitation == 'agent_inventaire':
                return '/dashboard/agent/'
            else:
                return '/dashboard/'
        else:
            return '/accounts/login/'


class Error404View(TemplateView):
    """
    Vue d'erreur 404 - Page non trouvée personnalisée
    Design cohérent avec l'application SUPPER
    """
    
    template_name = 'errors/404.html'
    
    def get_context_data(self, **kwargs):
        """Ajoute des informations contextuelles à l'erreur 404"""
        context = super().get_context_data(**kwargs)
        
        # URL demandée pour information
        requested_url = self.request.build_absolute_uri()
        
        # Suggestions de pages utiles
        useful_links = [
            {'name': _('Tableau de bord'), 'url': '/dashboard/'},
            {'name': _('Mon profil'), 'url': '/accounts/profile/'},
            {'name': _('Aide'), 'url': '/dashboard/aide/'},
        ]
        
        # Ajouter des liens spécifiques selon le rôle si connecté
        if self.request.user.is_authenticated:
            user = self.request.user
            
            if user.peut_gerer_inventaire:
                useful_links.append({
                    'name': _('Saisie inventaire'),
                    'url': '/inventaire/saisie/'
                })
            
            if user.habilitation in ['chef_peage', 'chef_pesage']:
                useful_links.append({
                    'name': _('Saisie recette'),
                    'url': '/inventaire/recettes/saisie/'
                })
            
            if user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info'] or user.is_superuser:
                useful_links.extend([
                    {'name': _('Gestion utilisateurs'), 'url': '/accounts/users/'},
                    {'name': _('Journal d\'audit'), 'url': '/dashboard/audit/'},
                ])
        
        context.update({
            'error_code': '404',
            'error_title': _('Page Non Trouvée'),
            'error_message': _('La page que vous recherchez n\'existe pas ou a été déplacée.'),
            'requested_url': requested_url,
            'useful_links': useful_links,
            'search_enabled': True  # Activer la recherche si implémentée
        })
        
        return context


class Error500View(TemplateView):
    """
    Vue d'erreur 500 - Erreur serveur personnalisée
    Gestion gracieuse des erreurs système
    """
    
    template_name = 'errors/500.html'
    
    def get_context_data(self, **kwargs):
        """Ajoute des informations pour l'erreur 500"""
        context = super().get_context_data(**kwargs)
        
        # Générer un ID d'incident pour le support
        incident_id = f"SUP-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        
        # Actions recommandées
        recommended_actions = [
            _("Actualisez la page (F5 ou Ctrl+R)"),
            _("Revenez à la page précédente"),
            _("Attendez quelques minutes et réessayez"),
            _("Contactez le support technique si le problème persiste")
        ]
        
        context.update({
            'error_code': '500',
            'error_title': _('Erreur Système'),
            'error_message': _('Une erreur inattendue s\'est produite. Nos équipes techniques ont été notifiées.'),
            'incident_id': incident_id,
            'recommended_actions': recommended_actions,
            'support_email': 'support@supper.cm',
            'support_phone': '+237 600 000 000',  # À configurer
            'dashboard_url': '/dashboard/'
        })
        
        # Journaliser l'erreur 500 avec l'ID d'incident
        logger.error(f"Erreur 500 - ID incident: {incident_id} - URL: {self.request.build_absolute_uri()}")
        
        return context


# ===================================================================
# GESTIONNAIRES D'ERREURS HTTP GLOBAUX
# ===================================================================

def handler403(request, exception):
    """
    Gestionnaire global pour les erreurs 403
    Args:
        request: Requête HTTP
        exception: Exception levée
    Returns:
        HttpResponse: Page d'erreur 403 personnalisée
    """
    logger.warning(f"Erreur 403: {request.build_absolute_uri()} - User: {request.user}")
    
    view = Error403View.as_view()
    return view(request)


def handler404(request, exception):
    """
    Gestionnaire global pour les erreurs 404
    Args:
        request: Requête HTTP
        exception: Exception levée
    Returns:
        HttpResponse: Page d'erreur 404 personnalisée
    """
    logger.warning(f"Erreur 404: {request.build_absolute_uri()}")
    
    view = Error404View.as_view()
    return view(request)


def handler500(request):
    """
    Gestionnaire global pour les erreurs 500
    Args:
        request: Requête HTTP
    Returns:
        HttpResponse: Page d'erreur 500 personnalisée
    """
    logger.error(f"Erreur 500: {request.build_absolute_uri()}")
    
    view = Error500View.as_view()
    return view(request)


# ===================================================================
# VUES DE MAINTENANCE ET SUPPORT
# ===================================================================

class MaintenanceView(TemplateView):
    """
    Vue de maintenance pour les interruptions planifiées
    À utiliser lors de mises à jour importantes
    """
    
    template_name = 'maintenance.html'
    
    def get_context_data(self, **kwargs):
        """Informations de maintenance"""
        context = super().get_context_data(**kwargs)
        
        context.update({
            'maintenance_title': _('Maintenance en Cours'),
            'maintenance_message': _('SUPPER est temporairement indisponible pour maintenance. Merci de votre patience.'),
            'estimated_duration': _('Durée estimée : 30 minutes'),
            'contact_info': {
                'email': 'admin@supper.cm',
                'phone': '+237 600 000 000'
            }
        })
        
        return context


# ===================================================================
# IMPORTS NÉCESSAIRES
# ===================================================================

from django.conf import settings