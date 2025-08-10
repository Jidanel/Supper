# ===================================================================
# inventaire/views.py - AJOUT DES VUES DE REDIRECTION POUR INVENTAIRES
# À ajouter au fichier inventaire/views.py existant
# ===================================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
import logging

logger = logging.getLogger('supper')

# Import des modèles
from .models import InventaireJournalier, RecetteJournaliere, ConfigurationJour, StatistiquesPeriodiques
from accounts.models import UtilisateurSUPPER, JournalAudit

# ===================================================================
# FONCTIONS UTILITAIRES POUR LES REDIRECTIONS INVENTAIRE
# ===================================================================

def _check_admin_permission(user):
    """Vérifier les permissions administrateur"""
    return (user.is_superuser or 
            user.is_staff or 
            user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'])


def _log_inventaire_admin_access(request, action):
    """Journaliser l'accès aux sections admin inventaire"""
    try:
        JournalAudit.objects.create(
            utilisateur=request.user,
            action=f"Accès admin Django Inventaire - {action}",
            details=f"Redirection depuis SUPPER vers {action}",
            adresse_ip=request.META.get('REMOTE_ADDR'),
            url_acces=request.path,
            methode_http=request.method,
            succes=True
        )
        
        logger.info(f"REDIRECTION ADMIN INVENTAIRE - {request.user.username} -> {action}")
        
    except Exception as e:
        logger.error(f"Erreur journalisation inventaire admin access: {str(e)}")


# ===================================================================
# VUES DE REDIRECTION VERS ADMIN DJANGO - MODULE INVENTAIRE
# ===================================================================

@login_required
def redirect_to_inventaires_admin(request):
    """Redirection vers la gestion des inventaires dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la gestion des inventaires."))
        return redirect('inventaire:inventaire_list')
    
    _log_inventaire_admin_access(request, "Gestion inventaires")
    messages.info(request, _("Redirection vers la gestion des inventaires."))
    
    return redirect('/django-admin/inventaire/inventairejournalier/')


@login_required
def redirect_to_recettes_admin(request):
    """Redirection vers la gestion des recettes dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la gestion des recettes."))
        return redirect('inventaire:inventaire_list')
    
    _log_inventaire_admin_access(request, "Gestion recettes")
    messages.info(request, _("Redirection vers la gestion des recettes."))
    
    return redirect('/django-admin/inventaire/recettejournaliere/')


@login_required
def redirect_to_config_jours_admin(request):
    """Redirection vers la configuration des jours dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la configuration des jours."))
        return redirect('inventaire:config_jour_list')
    
    _log_inventaire_admin_access(request, "Configuration jours")
    messages.info(request, _("Redirection vers la configuration des jours."))
    
    return redirect('/django-admin/inventaire/configurationjour/')


@login_required
def redirect_to_statistiques_admin(request):
    """Redirection vers les statistiques dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé aux statistiques."))
        return redirect('inventaire:inventaire_list')
    
    _log_inventaire_admin_access(request, "Statistiques")
    messages.info(request, _("Redirection vers les statistiques."))
    
    return redirect('/django-admin/inventaire/statistiquesperiodiques/')


# ===================================================================
# REDIRECTIONS SPÉCIFIQUES AVEC PARAMÈTRES
# ===================================================================

@login_required
def redirect_to_edit_inventaire_admin(request, inventaire_id):
    """Redirection vers l'édition d'un inventaire spécifique dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à l'édition des inventaires."))
        return redirect('inventaire:inventaire_list')
    
    # Vérifier que l'inventaire existe
    try:
        inventaire = InventaireJournalier.objects.get(id=inventaire_id)
        _log_inventaire_admin_access(request, f"Édition inventaire {inventaire.poste.nom} du {inventaire.date}")
        messages.info(request, _(f"Redirection vers l'édition de l'inventaire {inventaire.poste.nom} du {inventaire.date}."))
        
        return redirect(f'/django-admin/inventaire/inventairejournalier/{inventaire_id}/change/')
        
    except InventaireJournalier.DoesNotExist:
        messages.error(request, _("Inventaire non trouvé."))
        return redirect('/django-admin/inventaire/inventairejournalier/')


@login_required
def redirect_to_edit_recette_admin(request, recette_id):
    """Redirection vers l'édition d'une recette spécifique dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à l'édition des recettes."))
        return redirect('inventaire:inventaire_list')
    
    # Vérifier que la recette existe
    try:
        recette = RecetteJournaliere.objects.get(id=recette_id)
        _log_inventaire_admin_access(request, f"Édition recette {recette.poste.nom} du {recette.date}")
        messages.info(request, _(f"Redirection vers l'édition de la recette {recette.poste.nom} du {recette.date}."))
        
        return redirect(f'/django-admin/inventaire/recettejournaliere/{recette_id}/change/')
        
    except RecetteJournaliere.DoesNotExist:
        messages.error(request, _("Recette non trouvée."))
        return redirect('/django-admin/inventaire/recettejournaliere/')


# ===================================================================
# REDIRECTIONS POUR CRÉATION
# ===================================================================

@login_required
def redirect_to_add_inventaire_admin(request):
    """Redirection vers l'ajout d'inventaire dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la création d'inventaires."))
        return redirect('inventaire:inventaire_list')
    
    _log_inventaire_admin_access(request, "Ajout inventaire")
    messages.info(request, _("Redirection vers l'ajout d'inventaire."))
    
    return redirect('/django-admin/inventaire/inventairejournalier/add/')


@login_required
def redirect_to_add_recette_admin(request):
    """Redirection vers l'ajout de recette dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la création de recettes."))
        return redirect('inventaire:inventaire_list')
    
    _log_inventaire_admin_access(request, "Ajout recette")
    messages.info(request, _("Redirection vers l'ajout de recette."))
    
    return redirect('/django-admin/inventaire/recettejournaliere/add/')


@login_required
def redirect_to_add_config_jour_admin(request):
    """Redirection vers l'ajout de configuration de jour dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la configuration des jours."))
        return redirect('inventaire:config_jour_list')
    
    _log_inventaire_admin_access(request, "Ajout configuration jour")
    messages.info(request, _("Redirection vers l'ajout de configuration de jour."))
    
    return redirect('/django-admin/inventaire/configurationjour/add/')


# ===================================================================
# API POUR INTÉGRATION AVEC ADMIN DJANGO
# ===================================================================

@login_required
@require_http_methods(["GET"])
def inventaire_stats_api(request):
    """API pour statistiques des inventaires"""
    user = request.user
    
    if not _check_admin_permission(user):
        return JsonResponse({'error': 'Permission refusée'}, status=403)
    
    try:
        from django.utils import timezone
        from datetime import timedelta
        
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        stats = {
            'inventaires_today': InventaireJournalier.objects.filter(date=today).count(),
            'inventaires_week': InventaireJournalier.objects.filter(date__gte=week_ago).count(),
            'inventaires_locked': InventaireJournalier.objects.filter(verrouille=True).count(),
            'inventaires_validated': InventaireJournalier.objects.filter(valide=True).count(),
            'total_inventaires': InventaireJournalier.objects.count(),
        }
        
        return JsonResponse(stats)
        
    except Exception as e:
        logger.error(f"Erreur API inventaire stats: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)


@login_required
@require_http_methods(["GET"])
def recette_stats_api(request):
    """API pour statistiques des recettes"""
    user = request.user
    
    if not _check_admin_permission(user):
        return JsonResponse({'error': 'Permission refusée'}, status=403)
    
    try:
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Sum, Avg
        
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        stats = {
            'recettes_today': RecetteJournaliere.objects.filter(date=today).count(),
            'recettes_week': RecetteJournaliere.objects.filter(date__gte=week_ago).count(),
            'total_recettes': RecetteJournaliere.objects.count(),
            'montant_total_week': RecetteJournaliere.objects.filter(
                date__gte=week_ago
            ).aggregate(Sum('montant_declare'))['montant_declare__sum'] or 0,
            'taux_moyen_week': RecetteJournaliere.objects.filter(
                date__gte=week_ago,
                taux_deperdition__isnull=False
            ).aggregate(Avg('taux_deperdition'))['taux_deperdition__avg'] or 0,
        }
        
        return JsonResponse(stats)
        
    except Exception as e:
        logger.error(f"Erreur API recette stats: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)


@login_required
@require_http_methods(["GET"])
def check_day_status_api(request):
    """API pour vérifier le statut d'un jour"""
    user = request.user
    
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Date requise'}, status=400)
    
    try:
        from datetime import datetime
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        try:
            config = ConfigurationJour.objects.get(date=target_date)
            status = {
                'date': target_date.isoformat(),
                'statut': config.statut,
                'statut_display': config.get_statut_display(),
                'configured': True,
                'cree_par': config.cree_par.nom_complet if config.cree_par else None,
                'commentaire': config.commentaire,
            }
        except ConfigurationJour.DoesNotExist:
            status = {
                'date': target_date.isoformat(),
                'statut': 'ferme',  # Par défaut fermé si pas configuré
                'statut_display': 'Fermé - saisie verrouillée',
                'configured': False,
                'cree_par': None,
                'commentaire': 'Jour non configuré - fermé par défaut',
            }
        
        # Ajouter des informations sur les inventaires/recettes du jour
        inventaires_count = InventaireJournalier.objects.filter(date=target_date).count()
        recettes_count = RecetteJournaliere.objects.filter(date=target_date).count()
        
        status.update({
            'inventaires_count': inventaires_count,
            'recettes_count': recettes_count,
            'has_data': inventaires_count > 0 or recettes_count > 0
        })
        
        return JsonResponse(status)
        
    except ValueError:
        return JsonResponse({'error': 'Format de date invalide'}, status=400)
    except Exception as e:
        logger.error(f"Erreur API check day status: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)


# ===================================================================
# FONCTIONS UTILITAIRES POUR LES TEMPLATES
# ===================================================================

def get_inventaire_admin_context(user):
    """Retourne le contexte d'administration pour les templates inventaire"""
    
    if not _check_admin_permission(user):
        return {}
    
    return {
        'inventaire_admin_nav': {
            'inventaires': {
                'url': '/django-admin/inventaire/inventairejournalier/',
                'title': 'Gérer Inventaires',
                'icon': 'fas fa-clipboard-list',
                'description': 'Gestion complète des inventaires journaliers'
            },
            'recettes': {
                'url': '/django-admin/inventaire/recettejournaliere/',
                'title': 'Gérer Recettes',
                'icon': 'fas fa-euro-sign',
                'description': 'Gestion des recettes journalières'
            },
            'config_jours': {
                'url': '/django-admin/inventaire/configurationjour/',
                'title': 'Configuration Jours',
                'icon': 'fas fa-calendar-alt',
                'description': 'Configuration des jours ouverts/fermés'
            },
            'statistiques': {
                'url': '/django-admin/inventaire/statistiquesperiodiques/',
                'title': 'Statistiques',
                'icon': 'fas fa-chart-bar',
                'description': 'Statistiques périodiques et rapports'
            },
            'add_inventaire': {
                'url': '/django-admin/inventaire/inventairejournalier/add/',
                'title': 'Nouvel Inventaire',
                'icon': 'fas fa-plus-circle',
                'description': 'Créer un nouvel inventaire'
            },
            'add_recette': {
                'url': '/django-admin/inventaire/recettejournaliere/add/',
                'title': 'Nouvelle Recette',
                'icon': 'fas fa-plus-square',
                'description': 'Créer une nouvelle recette'
            }
        }
    }


# ===================================================================
# VUES D'AIDE ET DOCUMENTATION INVENTAIRE
# ===================================================================

@login_required
def inventaire_admin_help_view(request):
    """Vue d'aide pour l'utilisation de l'admin Django - module inventaire"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé."))
        return redirect('inventaire:inventaire_list')
    
    context = {
        'title': 'Aide - Administration Inventaires',
        'user_permissions': {
            'can_manage_inventaires': True,
            'can_manage_recettes': True,
            'can_config_jours': True,
            'can_view_statistics': True,
        },
        'admin_urls': get_inventaire_admin_context(user)['inventaire_admin_nav'],
        'help_sections': [
            {
                'title': 'Gestion des Inventaires',
                'description': 'Créer, modifier et valider les inventaires journaliers',
                'url': '/django-admin/inventaire/inventairejournalier/',
                'features': [
                    'Saisie par période horaire',
                    'Calculs automatiques',
                    'Verrouillage et validation',
                    'Export des données'
                ]
            },
            {
                'title': 'Gestion des Recettes',
                'description': 'Suivi des recettes déclarées et calcul des taux de déperdition',
                'url': '/django-admin/inventaire/recettejournaliere/',
                'features': [
                    'Saisie des montants déclarés',
                    'Calcul automatique des taux',
                    'Alertes visuelles',
                    'Rapports consolidés'
                ]
            },
            {
                'title': 'Configuration des Jours',
                'description': 'Gérer les jours ouverts/fermés pour la saisie',
                'url': '/django-admin/inventaire/configurationjour/',
                'features': [
                    'Ouverture/fermeture jours',
                    'Marquage jours impertinents',
                    'Commentaires et historique',
                    'Contrôle des accès'
                ]
            }
        ]
    }
    
    return render(request, 'inventaire/admin_help.html', context)


# ===================================================================
# GESTION DES ERREURS DE REDIRECTION INVENTAIRE
# ===================================================================

@login_required
def inventaire_redirect_error_handler(request, error_type='permission'):
    """Gestionnaire d'erreurs pour les redirections inventaire"""
    user = request.user
    
    if error_type == 'permission':
        messages.error(request, _(
            "Vous n'avez pas les permissions nécessaires pour accéder à cette section inventaire. "
            "Contactez un administrateur si vous pensez que c'est une erreur."
        ))
        
        # Journaliser la tentative d'accès non autorisée
        try:
            JournalAudit.objects.create(
                utilisateur=user,
                action="ACCÈS REFUSÉ - Redirection admin inventaire",
                details=f"Tentative d'accès non autorisée depuis {request.META.get('HTTP_REFERER', 'URL inconnue')}",
                adresse_ip=request.META.get('REMOTE_ADDR'),
                url_acces=request.path,
                methode_http=request.method,
                succes=False
            )
        except Exception as e:
            logger.error(f"Erreur journalisation tentative accès inventaire: {str(e)}")
    
    elif error_type == 'not_found':
        messages.error(request, _("L'inventaire ou la recette demandée n'a pas été trouvée."))
    
    else:
        messages.error(request, _("Une erreur est survenue lors de la redirection."))
    
    # Rediriger vers la liste des inventaires
    return redirect('inventaire:inventaire_list')


# ===================================================================
# API SUPPLÉMENTAIRE POUR LE DASHBOARD
# ===================================================================

@login_required
@require_http_methods(["POST"])
def quick_action_api(request):
    """API pour les actions rapides depuis le dashboard"""
    user = request.user
    
    if not _check_admin_permission(user):
        return JsonResponse({'error': 'Permission refusée'}, status=403)
    
    action = request.POST.get('action')
    
    try:
        if action == 'open_today':
            # Ouvrir le jour actuel
            from django.utils import timezone
            today = timezone.now().date()
            
            config, created = ConfigurationJour.objects.get_or_create(
                date=today,
                defaults={
                    'statut': 'ouvert',
                    'cree_par': user,
                    'commentaire': f'Ouvert via API par {user.nom_complet}'
                }
            )
            
            if not created and config.statut != 'ouvert':
                config.statut = 'ouvert'
                config.commentaire = f'Réouvert via API par {user.nom_complet}'
                config.save()
            
            _log_inventaire_admin_access(request, f"Ouverture jour {today}")
            
            return JsonResponse({
                'success': True,
                'message': f'Jour {today.strftime("%d/%m/%Y")} ouvert pour la saisie.',
                'date': today.isoformat(),
                'statut': config.statut
            })
        
        elif action == 'mark_impertinent':
            # Marquer un jour comme impertinent
            date_str = request.POST.get('date')
            if not date_str:
                return JsonResponse({'error': 'Date requise'}, status=400)
            
            from datetime import datetime
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            config, created = ConfigurationJour.objects.get_or_create(
                date=target_date,
                defaults={
                    'statut': 'impertinent',
                    'cree_par': user,
                    'commentaire': f'Marqué impertinent via API par {user.nom_complet}'
                }
            )
            
            if not created:
                config.statut = 'impertinent'
                config.commentaire = f'Marqué impertinent via API par {user.nom_complet}'
                config.save()
            
            _log_inventaire_admin_access(request, f"Marquage impertinent {target_date}")
            
            return JsonResponse({
                'success': True,
                'message': f'Jour {target_date.strftime("%d/%m/%Y")} marqué comme impertinent.',
                'date': target_date.isoformat(),
                'statut': config.statut
            })
        
        else:
            return JsonResponse({'error': 'Action non reconnue'}, status=400)
    
    except Exception as e:
        logger.error(f"Erreur API quick action: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)