# ===================================================================
# Fichier : Supper/views.py - Vues principales et gestion d'erreurs
# VERSION AMÉLIORÉE - Intégration des améliorations du fichier 1 dans le fichier 2
# ===================================================================

from django.shortcuts import redirect, render
from django.views.generic import View, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponse
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
import logging

logger = logging.getLogger('supper')


class HomeView(View):
    """
    Vue d'accueil avec redirection intelligente selon le rôle utilisateur
    AMÉLIORÉE - Combinaison des meilleures pratiques des deux fichiers
    """
    
    def get(self, request):
        """Redirection automatique selon le profil utilisateur connecté"""
        
        if request.user.is_authenticated:
            user = request.user
            
            # Message de bienvenue personnalisé - AMÉLIORÉ avec getattr
            messages.success(
                request, 
                _("Bienvenue %(nom)s ! Redirection vers votre espace de travail...") % {
                    'nom': getattr(user, 'nom_complet', user.username)
                }
            )
            
            # DEBUG: Logs pour diagnostiquer les problèmes de routage
            logger.info(
                f"ROUTAGE DASHBOARD - Utilisateur: {user.username} | "
                f"is_superuser: {user.is_superuser} | "
                f"is_staff: {user.is_staff} | "
                f"habilitation: {getattr(user, 'habilitation', 'standard')}"
            )
            
            # ================================================================
            # LOGIQUE DE ROUTAGE UNIFIÉE - Redirection vers /admin/
            # ================================================================
            
            # PRIORITÉ 1: Super utilisateurs → Admin SUPPER (dashboard principal)
            if user.is_superuser:
                logger.info(f"REDIRECTION SUPER ADMIN: {user.username} → /admin/")
                return redirect('/admin/')
            
            # PRIORITÉ 2: Staff Django → Admin SUPPER
            elif user.is_staff:
                logger.info(f"REDIRECTION STAFF: {user.username} → /admin/")
                return redirect('/admin/')
            
            # PRIORITÉ 3: Habilitations administratives → Admin SUPPER
            elif hasattr(user, 'habilitation') and user.habilitation in [
                'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'
            ]:
                logger.info(f"REDIRECTION ADMIN HABILITATION: {user.username} → /admin/")
                return redirect('/admin/')
            
            # PRIORITÉ 4: Chefs de poste → Admin SUPPER (interfaces en développement)
            elif hasattr(user, 'habilitation') and user.habilitation in ['chef_peage', 'chef_pesage']:
                logger.info(f"REDIRECTION CHEF: {user.username} → /admin/ (temporaire)")
                messages.info(
                    request, 
                    _("Interface chef de poste en cours de développement. Accès au dashboard administrateur.")
                )
                return redirect('/admin/')
            
            # PRIORITÉ 5: Agents inventaire → Admin SUPPER (interfaces en développement)
            elif hasattr(user, 'habilitation') and user.habilitation == 'agent_inventaire':
                logger.info(f"REDIRECTION AGENT: {user.username} → /admin/ (temporaire)")
                messages.info(
                    request, 
                    _("Interface agent inventaire en cours de développement. Accès au dashboard administrateur.")
                )
                return redirect('/admin/')
            
            # PRIORITÉ 6: Autres utilisateurs → Admin SUPPER
            else:
                logger.info(f"REDIRECTION STANDARD: {user.username} → /admin/")
                return redirect('/admin/')
        
        else:
            # Utilisateur non connecté : rediriger vers la page de connexion admin
            logger.info("REDIRECTION LOGIN - Utilisateur non connecté")
            return redirect('/admin/login/')


class StatusView(View):
    """
    Vue de statut pour monitoring externe de l'application
    AMÉLIORÉE - Gestion robuste des erreurs et plus d'informations
    """
    
    def get(self, request):
        """
        Retourne le statut de l'application
        Returns:
            JsonResponse: Statut de l'application avec informations détaillées
        """
        try:
            # Vérification basique de la base de données
            try:
                from accounts.models import UtilisateurSUPPER
                user_count = UtilisateurSUPPER.objects.count()
                db_status = 'connected'
            except Exception:
                # Fallback si les modèles ne sont pas encore disponibles
                user_count = 0
                db_status = 'unavailable'
            
            # Informations de statut étendues
            status_data = {
                'status': 'ok',
                'timestamp': timezone.now().isoformat(),
                'version': '1.0.0',
                'database': db_status,
                'users_count': user_count,
                'environment': 'development' if settings.DEBUG else 'production',
                'app_name': 'SUPPER'
            }
            
            return JsonResponse(status_data)
            
        except Exception as e:
            logger.error(f"Erreur status check: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'timestamp': timezone.now().isoformat(),
                'error': 'System check failed',
                'app_name': 'SUPPER'
            }, status=500)


# ===================================================================
# API POUR LES DASHBOARDS - NOUVEAU
# ===================================================================

def api_dashboard_stats(request):
    """
    API pour récupérer les statistiques du dashboard
    Retourne les données en JSON pour AJAX
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        # Import des modèles (si disponibles)
        try:
            from accounts.models import UtilisateurSUPPER, Poste, JournalAudit
            from inventaire.models import InventaireJournalier, RecetteJournaliere
            models_available = True
        except ImportError:
            models_available = False
        
        if not models_available:
            # Données factices pour le développement
            stats = {
                'users_total': 10,
                'users_active': 8,
                'users_online': 3,
                'postes_total': 67,
                'postes_peage': 27,
                'postes_pesage': 40,
                'inventaires_today': 5,
                'inventaires_week': 25,
                'recettes_today': 3,
                'recettes_week': 18,
                'actions_today': 45,
                'db_tables': 15,
            }
        else:
            # Calculer les vraies statistiques
            from datetime import timedelta
            
            today = timezone.now().date()
            week_ago = today - timedelta(days=7)
            
            stats = {
                'users_total': UtilisateurSUPPER.objects.count(),
                'users_active': UtilisateurSUPPER.objects.filter(is_active=True).count(),
                'users_online': UtilisateurSUPPER.objects.filter(
                    last_login__gte=timezone.now() - timedelta(minutes=30)
                ).count(),
                'postes_total': Poste.objects.count(),
                'postes_peage': Poste.objects.filter(type='peage').count(),
                'postes_pesage': Poste.objects.filter(type='pesage').count(),
                'inventaires_today': InventaireJournalier.objects.filter(date=today).count(),
                'inventaires_week': InventaireJournalier.objects.filter(date__gte=week_ago).count(),
                'recettes_today': RecetteJournaliere.objects.filter(date=today).count(),
                'recettes_week': RecetteJournaliere.objects.filter(date__gte=week_ago).count(),
                'actions_today': JournalAudit.objects.filter(timestamp__date=today).count(),
                'db_tables': 15,  # Nombre approximatif de tables
            }
        
        return JsonResponse({
            'success': True,
            'stats': stats,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Erreur API dashboard stats: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Erreur lors de la récupération des statistiques',
            'details': str(e) if request.user.is_superuser else None
        }, status=500)


# ===================================================================
# VUES D'ERREUR PERSONNALISÉES - AMÉLIORÉES
# ===================================================================

class Error403View(TemplateView):
    """
    Vue d'erreur 403 - Accès interdit personnalisée
    AMÉLIORÉE - Plus d'informations contextuelles et suggestions
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
            'support_email': 'admin@supper.cm',
            'dashboard_url': self._get_user_dashboard_url(),
            'show_home_link': True,
            'show_login_link': not self.request.user.is_authenticated,
        })
        
        return context
    
    def _get_user_dashboard_name(self, user):
        """Retourne le nom du dashboard approprié"""
        if (hasattr(user, 'habilitation') and 
            user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info']) or \
           user.is_superuser or user.is_staff:
            return _("tableau de bord administrateur")
        elif hasattr(user, 'habilitation') and user.habilitation in ['chef_peage', 'chef_pesage']:
            return _("tableau de bord chef de poste")
        elif hasattr(user, 'habilitation') and user.habilitation == 'agent_inventaire':
            return _("interface de saisie")
        else:
            return _("tableau de bord")
    
    def _get_user_dashboard_url(self):
        """Retourne l'URL du dashboard approprié - UNIFIÉ vers /admin/"""
        if self.request.user.is_authenticated:
            # Tous les utilisateurs connectés vont vers /admin/ pour le moment
            return '/admin/'
        else:
            return '/admin/login/'


class Error404View(TemplateView):
    """
    Vue d'erreur 404 - Page non trouvée personnalisée
    AMÉLIORÉE - Liens utiles contextuels et recherche
    """
    
    template_name = 'errors/404.html'
    
    def get_context_data(self, **kwargs):
        """Ajoute des informations contextuelles à l'erreur 404"""
        context = super().get_context_data(**kwargs)
        
        # URL demandée pour information
        requested_url = self.request.build_absolute_uri()
        
        # Suggestions de pages utiles
        useful_links = [
            {'name': _('Tableau de bord'), 'url': '/admin/'},
            {'name': _('Accueil'), 'url': '/'},
        ]
        
        # Ajouter des liens spécifiques selon le rôle si connecté
        if self.request.user.is_authenticated:
            user = self.request.user
            
            if hasattr(user, 'peut_gerer_inventaire') and user.peut_gerer_inventaire:
                useful_links.append({
                    'name': _('Gestion inventaires'),
                    'url': '/admin/'
                })
            
            if hasattr(user, 'habilitation') and user.habilitation in ['chef_peage', 'chef_pesage']:
                useful_links.append({
                    'name': _('Gestion recettes'),
                    'url': '/admin/'
                })
            
            if (hasattr(user, 'habilitation') and 
                user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info']) or \
               user.is_superuser:
                useful_links.extend([
                    {'name': _('Panel avancé'), 'url': '/admin/'},
                    {'name': _('Gestion utilisateurs'), 'url': '/admin/'},
                ])
        
        context.update({
            'error_code': '404',
            'error_title': _('Page Non Trouvée'),
            'error_message': _('La page que vous recherchez n\'existe pas ou a été déplacée.'),
            'error_suggestion': _('Vérifiez l\'URL ou utilisez les liens ci-dessous.'),
            'requested_url': requested_url,
            'useful_links': useful_links,
            'show_home_link': True,
            'show_login_link': not self.request.user.is_authenticated,
            'search_enabled': False  # Désactivé pour le moment
        })
        
        return context


class Error500View(TemplateView):
    """
    Vue d'erreur 500 - Erreur serveur personnalisée
    AMÉLIORÉE - ID d'incident et actions recommandées
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
            'error_suggestion': _('Veuillez réessayer dans quelques minutes.'),
            'incident_id': incident_id,
            'recommended_actions': recommended_actions,
            'support_email': 'support@supper.cm',
            'support_phone': '+237 600 000 000',
            'dashboard_url': '/admin/',
            'show_home_link': True,
        })
        
        # Journaliser l'erreur 500 avec l'ID d'incident
        logger.error(f"Erreur 500 - ID incident: {incident_id} - URL: {self.request.build_absolute_uri()}")
        
        return context


# ===================================================================
# GESTIONNAIRES D'ERREURS HTTP GLOBAUX - AMÉLIORÉS
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
    return view(request, exception=exception)


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
    return view(request, exception=exception)


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
# VUES DE MAINTENANCE ET SUPPORT - AMÉLIORÉES
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
# VUES UTILITAIRES - NOUVELLES
# ===================================================================

def health_check(request):
    """Vérification de santé de l'application"""
    try:
        # Vérifier la base de données
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        return JsonResponse({
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'version': '1.0.0',
            'app_name': 'SUPPER'
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e),
            'app_name': 'SUPPER'
        }, status=503)


def robots_txt(request):
    """Fichier robots.txt dynamique"""
    content = """User-agent: *
Disallow: /admin/
Disallow: /django-admin/
Disallow: /api/
Allow: /
"""
    return HttpResponse(content, content_type='text/plain')


# ===================================================================
# FONCTION ACCUEIL SIMPLE - POUR COMPATIBILITÉ
# ===================================================================

def accueil(request):
    """
    Vue d'accueil simple pour compatibilité avec les URLs existantes
    Redirige vers la classe HomeView
    """
    view = HomeView()
    return view.get(request)


# ===================================================================
# LOGGING DE DÉMARRAGE - NOUVEAU
# ===================================================================

logger.info("=" * 60)
logger.info("SUPPER Vues système initialisées:")
logger.info("  - Vue d'accueil avec redirection intelligente vers /admin/")
logger.info("  - Handlers d'erreur: 404, 500, 403 améliorés")
logger.info("  - API dashboard stats pour AJAX")
logger.info("  - Vues de maintenance et utilitaires")
logger.info("  - Health check et robots.txt")
logger.info("  - Fonction accueil pour compatibilité")
logger.info("=" * 60)