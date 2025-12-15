# ===================================================================
# common/decorators.py - Décorateurs de permissions SUPPER
# VERSION COMPLÈTE - Basé sur les 73 permissions granulaires
# ===================================================================
"""
Décorateurs pour contrôler l'accès aux vues basé sur les permissions granulaires.

UTILISATION:
    from common.decorators import (
        permission_required_granular,
        inventaire_admin_required,
        pesage_required,
        gestion_postes_required
    )
    
    @inventaire_admin_required
    def ma_vue_inventaire_admin(request):
        ...
    
    @permission_required_granular('peut_saisir_amende')
    def saisir_amende(request):
        ...
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
import logging

from .permissions import (
    # Fonctions génériques
    has_permission,
    has_any_permission,
    has_all_permissions,
    check_poste_access,
    user_has_acces_tous_postes,
    get_poste_from_request,
    log_acces_refuse,
    
    # Classification utilisateurs
    is_admin_user,
    is_service_central,
    is_cisop,
    is_cisop_peage,
    is_cisop_pesage,
    is_chef_poste,
    is_chef_poste_peage,
    is_chef_station_pesage,
    is_agent_inventaire,
    is_regisseur_pesage,
    is_chef_equipe_pesage,
    is_operationnel_pesage,
    is_operationnel_peage,
    is_service_emission,
    is_service_controle,
    is_service_ordre,
    is_chef_affaires_generales,
    is_imprimerie_nationale,
    
    # Listes de permissions par module
    PERMISSIONS_INVENTAIRES,
    PERMISSIONS_RECETTES_PEAGE,
    PERMISSIONS_QUITTANCES_PEAGE,
    PERMISSIONS_PESAGE,
    PERMISSIONS_STOCK_PEAGE,
    PERMISSIONS_GESTION,
    PERMISSIONS_RAPPORTS,
)

logger = logging.getLogger('supper.decorators')


# ===================================================================
# SECTION 1: DÉCORATEUR GÉNÉRIQUE DE PERMISSION
# ===================================================================

def permission_required_granular(permission_name, redirect_url='accounts:login', 
                                  raise_exception=False, message=None):
    """
    Décorateur générique pour vérifier une permission spécifique.
    
    Args:
        permission_name: Nom de la permission à vérifier (str ou list)
        redirect_url: URL de redirection si permission refusée
        raise_exception: Si True, lève PermissionDenied au lieu de rediriger
        message: Message personnalisé à afficher
    
    Usage:
        @permission_required_granular('peut_saisir_inventaire_admin')
        def ma_vue(request):
            ...
        
        @permission_required_granular(['peut_saisir_amende', 'peut_lister_amendes'])
        def vue_amendes(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            
            # Vérification de la permission
            if isinstance(permission_name, (list, tuple)):
                has_perm = has_any_permission(user, permission_name)
                perm_display = " ou ".join(permission_name)
            else:
                has_perm = has_permission(user, permission_name)
                perm_display = permission_name
            
            if has_perm:
                return view_func(request, *args, **kwargs)
            
            # Permission refusée
            log_acces_refuse(user, view_func.__name__, f"Permission manquante: {perm_display}")
            
            if raise_exception:
                raise PermissionDenied(message or f"Permission requise: {perm_display}")
            
            # Message d'erreur
            msg = message or f"Vous n'avez pas la permission d'accéder à cette fonctionnalité."
            messages.error(request, msg)
            
            return redirect(redirect_url)
        
        return _wrapped_view
    return decorator


def all_permissions_required(permission_names, redirect_url='accounts:login',
                             raise_exception=False, message=None):
    """
    Décorateur pour vérifier que TOUTES les permissions sont accordées.
    
    Usage:
        @all_permissions_required(['peut_gerer_utilisateurs', 'peut_voir_journal_audit'])
        def vue_admin_complete(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            
            if has_all_permissions(user, permission_names):
                return view_func(request, *args, **kwargs)
            
            # Permission refusée
            missing = [p for p in permission_names if not has_permission(user, p)]
            log_acces_refuse(user, view_func.__name__, f"Permissions manquantes: {missing}")
            
            if raise_exception:
                raise PermissionDenied(message or f"Permissions requises: {', '.join(permission_names)}")
            
            messages.error(request, message or "Vous n'avez pas toutes les permissions requises.")
            return redirect(redirect_url)
        
        return _wrapped_view
    return decorator


# ===================================================================
# SECTION 2: DÉCORATEURS PAR CLASSIFICATION UTILISATEUR
# ===================================================================

def admin_required(redirect_url='common:dashboard', message=None):
    """
    Décorateur pour les vues réservées aux administrateurs.
    Inclut: admin_principal, coord_psrr, serv_info
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if is_admin_user(request.user):
                return view_func(request, *args, **kwargs)
            
            log_acces_refuse(request.user, view_func.__name__, "Administrateur requis")
            messages.error(request, message or "Accès réservé aux administrateurs.")
            return redirect(redirect_url)
        
        return _wrapped_view
    return decorator


def service_central_required(redirect_url='common:dashboard', message=None):
    """
    Décorateur pour les vues réservées aux services centraux.
    Inclut: admin, coord_psrr, serv_info, serv_emission, chef_ag, serv_controle, serv_ordre
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if is_service_central(request.user):
                return view_func(request, *args, **kwargs)
            
            log_acces_refuse(request.user, view_func.__name__, "Service central requis")
            messages.error(request, message or "Accès réservé aux services centraux.")
            return redirect(redirect_url)
        
        return _wrapped_view
    return decorator


def cisop_required(redirect_url='common:dashboard', message=None):
    """Décorateur pour les vues réservées aux CISOP (péage ou pesage)."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if is_cisop(request.user) or is_admin_user(request.user):
                return view_func(request, *args, **kwargs)
            
            log_acces_refuse(request.user, view_func.__name__, "CISOP requis")
            messages.error(request, message or "Accès réservé aux CISOP.")
            return redirect(redirect_url)
        
        return _wrapped_view
    return decorator


def chef_poste_required(redirect_url='common:dashboard', message=None):
    """Décorateur pour les vues réservées aux chefs de poste."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if is_chef_poste(request.user) or is_admin_user(request.user):
                return view_func(request, *args, **kwargs)
            
            log_acces_refuse(request.user, view_func.__name__, "Chef de poste requis")
            messages.error(request, message or "Accès réservé aux chefs de poste.")
            return redirect(redirect_url)
        
        return _wrapped_view
    return decorator


def operationnel_pesage_required(redirect_url='common:dashboard', message=None):
    """
    Décorateur pour les vues réservées aux opérationnels pesage.
    Inclut: chef_station_pesage, regisseur_pesage, chef_equipe_pesage
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if is_operationnel_pesage(request.user) or is_admin_user(request.user):
                return view_func(request, *args, **kwargs)
            
            log_acces_refuse(request.user, view_func.__name__, "Opérationnel pesage requis")
            messages.error(request, message or "Accès réservé au personnel pesage.")
            return redirect(redirect_url)
        
        return _wrapped_view
    return decorator


def operationnel_peage_required(redirect_url='common:dashboard', message=None):
    """
    Décorateur pour les vues réservées aux opérationnels péage.
    Inclut: chef_peage, agent_inventaire
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if is_operationnel_peage(request.user) or is_admin_user(request.user):
                return view_func(request, *args, **kwargs)
            
            log_acces_refuse(request.user, view_func.__name__, "Opérationnel péage requis")
            messages.error(request, message or "Accès réservé au personnel péage.")
            return redirect(redirect_url)
        
        return _wrapped_view
    return decorator


# ===================================================================
# SECTION 3: DÉCORATEURS MODULE INVENTAIRES
# ===================================================================

def inventaire_saisie_required(redirect_url='common:dashboard'):
    """
    Décorateur pour la saisie d'inventaire normal.
    Permission: peut_saisir_inventaire_normal
    """
    return permission_required_granular(
        'peut_saisir_inventaire_normal',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de saisir des inventaires."
    )


def inventaire_admin_required(redirect_url='common:dashboard'):
    """
    Décorateur pour la saisie d'inventaire administratif.
    Permission: peut_saisir_inventaire_admin
    """
    return permission_required_granular(
        'peut_saisir_inventaire_admin',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de saisir des inventaires administratifs."
    )


def programmation_inventaire_required(redirect_url='common:dashboard'):
    """
    Décorateur pour la programmation d'inventaires.
    Permission: peut_programmer_inventaire
    """
    return permission_required_granular(
        'peut_programmer_inventaire',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de programmer des inventaires."
    )


def liste_inventaires_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir la liste des inventaires.
    Permission: peut_voir_liste_inventaires OU peut_voir_liste_inventaires_admin
    """
    return permission_required_granular(
        ['peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin'],
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir les inventaires."
    )


def liste_inventaires_admin_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir la liste des inventaires admin.
    Permission: peut_voir_liste_inventaires_admin
    """
    return permission_required_granular(
        'peut_voir_liste_inventaires_admin',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir les inventaires administratifs."
    )


def stats_deperdition_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir les statistiques de déperdition.
    Permission: peut_voir_stats_deperdition
    """
    return permission_required_granular(
        'peut_voir_stats_deperdition',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir les statistiques de déperdition."
    )


# ===================================================================
# SECTION 4: DÉCORATEURS MODULE RECETTES PÉAGE
# ===================================================================

def saisie_recette_peage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour la saisie de recettes péage.
    Permission: peut_saisir_recette_peage
    """
    return permission_required_granular(
        'peut_saisir_recette_peage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de saisir des recettes péage."
    )


def liste_recettes_peage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir la liste des recettes péage.
    Permission: peut_voir_liste_recettes_peage
    """
    return permission_required_granular(
        'peut_voir_liste_recettes_peage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir les recettes péage."
    )


def import_recettes_peage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour importer des recettes péage.
    Permission: peut_importer_recettes_peage
    """
    return permission_required_granular(
        'peut_importer_recettes_peage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission d'importer des recettes."
    )


# ===================================================================
# SECTION 5: DÉCORATEURS MODULE QUITTANCES PÉAGE
# ===================================================================

def saisie_quittance_peage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour la saisie de quittances péage.
    Permission: peut_saisir_quittance_peage
    """
    return permission_required_granular(
        'peut_saisir_quittance_peage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de saisir des quittances péage."
    )


def comptabiliser_quittances_peage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour comptabiliser les quittances péage.
    Permission: peut_comptabiliser_quittances_peage
    """
    return permission_required_granular(
        'peut_comptabiliser_quittances_peage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de comptabiliser les quittances péage."
    )


# ===================================================================
# SECTION 6: DÉCORATEURS MODULE PESAGE
# ===================================================================

def saisie_amende_required(redirect_url='common:dashboard'):
    """
    Décorateur pour la saisie d'amendes.
    Permission: peut_saisir_amende
    """
    return permission_required_granular(
        'peut_saisir_amende',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de saisir des amendes."
    )


def saisie_pesee_required(redirect_url='common:dashboard'):
    """
    Décorateur pour la saisie de pesées.
    Permission: peut_saisir_pesee_jour
    """
    return permission_required_granular(
        'peut_saisir_pesee_jour',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de saisir des pesées."
    )


def validation_paiement_amende_required(redirect_url='common:dashboard'):
    """
    Décorateur pour valider les paiements d'amendes.
    Permission: peut_valider_paiement_amende
    """
    return permission_required_granular(
        'peut_valider_paiement_amende',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de valider les paiements d'amendes."
    )


def liste_amendes_required(redirect_url='common:dashboard'):
    """
    Décorateur pour lister les amendes.
    Permission: peut_lister_amendes
    """
    return permission_required_granular(
        'peut_lister_amendes',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir les amendes."
    )


def saisie_quittance_pesage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour la saisie de quittances pesage.
    Permission: peut_saisir_quittance_pesage
    """
    return permission_required_granular(
        'peut_saisir_quittance_pesage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de saisir des quittances pesage."
    )


def comptabiliser_quittances_pesage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour comptabiliser les quittances pesage.
    Permission: peut_comptabiliser_quittances_pesage
    """
    return permission_required_granular(
        'peut_comptabiliser_quittances_pesage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de comptabiliser les quittances pesage."
    )


def historique_pesees_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir l'historique des pesées.
    Permission: peut_voir_historique_pesees
    """
    return permission_required_granular(
        'peut_voir_historique_pesees',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir l'historique des pesées."
    )


def stats_pesage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir les statistiques pesage.
    Permission: peut_voir_stats_pesage
    """
    return permission_required_granular(
        'peut_voir_stats_pesage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir les statistiques pesage."
    )


def historique_vehicule_pesage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir l'historique véhicule pesage.
    Permission: peut_voir_historique_vehicule_pesage
    """
    return permission_required_granular(
        'peut_voir_historique_vehicule_pesage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir l'historique des véhicules."
    )


# ===================================================================
# SECTION 7: DÉCORATEURS MODULE STOCK PÉAGE
# ===================================================================

def charger_stock_peage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour charger du stock péage.
    Permission: peut_charger_stock_peage
    """
    return permission_required_granular(
        'peut_charger_stock_peage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de charger du stock."
    )


def transferer_stock_peage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour transférer du stock péage.
    Permission: peut_transferer_stock_peage
    """
    return permission_required_granular(
        'peut_transferer_stock_peage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de transférer du stock."
    )


def tracabilite_tickets_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir la traçabilité des tickets.
    Permission: peut_voir_tracabilite_tickets
    """
    return permission_required_granular(
        'peut_voir_tracabilite_tickets',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir la traçabilité des tickets."
    )


def bordereaux_peage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir les bordereaux péage.
    Permission: peut_voir_bordereaux_peage
    """
    return permission_required_granular(
        'peut_voir_bordereaux_peage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir les bordereaux."
    )


def simuler_commandes_required(redirect_url='common:dashboard'):
    """
    Décorateur pour simuler des commandes.
    Permission: peut_simuler_commandes_peage
    """
    return permission_required_granular(
        'peut_simuler_commandes_peage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de simuler des commandes."
    )


# ===================================================================
# SECTION 8: DÉCORATEURS MODULE GESTION
# ===================================================================

def gestion_postes_required(redirect_url='common:dashboard'):
    """
    Décorateur pour gérer les postes.
    Permission: peut_gerer_postes
    """
    return permission_required_granular(
        'peut_gerer_postes',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de gérer les postes."
    )


def ajout_poste_required(redirect_url='common:dashboard'):
    """
    Décorateur pour ajouter un poste.
    Permission: peut_ajouter_poste
    """
    return permission_required_granular(
        'peut_ajouter_poste',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission d'ajouter des postes."
    )


def gestion_utilisateurs_required(redirect_url='common:dashboard'):
    """
    Décorateur pour gérer les utilisateurs.
    Permission: peut_gerer_utilisateurs
    """
    return permission_required_granular(
        'peut_gerer_utilisateurs',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de gérer les utilisateurs."
    )


def creation_utilisateur_required(redirect_url='common:dashboard'):
    """
    Décorateur pour créer un utilisateur.
    Permission: peut_creer_utilisateur
    """
    return permission_required_granular(
        'peut_creer_utilisateur',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de créer des utilisateurs."
    )


def journal_audit_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir le journal d'audit.
    Permission: peut_voir_journal_audit
    """
    return permission_required_granular(
        'peut_voir_journal_audit',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir le journal d'audit."
    )


def parametrage_global_required(redirect_url='common:dashboard'):
    """
    Décorateur pour le paramétrage global.
    Permission: peut_parametrage_global
    """
    return permission_required_granular(
        'peut_parametrage_global',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission d'accéder au paramétrage global."
    )


# ===================================================================
# SECTION 9: DÉCORATEURS MODULE RAPPORTS
# ===================================================================

def rapports_defaillants_peage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir les rapports défaillants péage.
    Permission: peut_voir_rapports_defaillants_peage
    """
    return permission_required_granular(
        'peut_voir_rapports_defaillants_peage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir ces rapports."
    )


def rapports_defaillants_pesage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir les rapports défaillants pesage.
    Permission: peut_voir_rapports_defaillants_pesage
    """
    return permission_required_granular(
        'peut_voir_rapports_defaillants_pesage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir ces rapports."
    )


def rapport_inventaires_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir le rapport des inventaires.
    Permission: peut_voir_rapport_inventaires
    """
    return permission_required_granular(
        'peut_voir_rapport_inventaires',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir ce rapport."
    )


def classement_peage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir les classements péage.
    Permission: peut_voir_classement_peage_rendement OU peut_voir_classement_peage_deperdition
    """
    return permission_required_granular(
        ['peut_voir_classement_peage_rendement', 'peut_voir_classement_peage_deperdition'],
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir les classements péage."
    )


def classement_pesage_required(redirect_url='common:dashboard'):
    """
    Décorateur pour voir le classement des stations pesage.
    Permission: peut_voir_classement_station_pesage
    """
    return permission_required_granular(
        'peut_voir_classement_station_pesage',
        redirect_url=redirect_url,
        message="Vous n'avez pas la permission de voir le classement pesage."
    )


# ===================================================================
# SECTION 10: DÉCORATEURS AVEC VÉRIFICATION DE POSTE
# ===================================================================

def poste_access_required(redirect_url='common:dashboard', message=None):
    """
    Décorateur qui vérifie que l'utilisateur a accès au poste demandé.
    Le poste est extrait de la requête (GET/POST) ou des kwargs de l'URL.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            
            # Tenter d'extraire le poste
            poste = get_poste_from_request(request)
            
            # Si pas trouvé dans la requête, chercher dans les kwargs
            if not poste and 'poste_id' in kwargs:
                from accounts.models import Poste
                try:
                    poste = Poste.objects.get(id=kwargs['poste_id'])
                except Poste.DoesNotExist:
                    messages.error(request, "Poste non trouvé.")
                    return redirect(redirect_url)
            
            # Si toujours pas de poste, utiliser le poste d'affectation
            if not poste:
                poste = user.poste_affectation
            
            # Vérifier l'accès
            if poste and check_poste_access(user, poste):
                return view_func(request, *args, **kwargs)
            
            # Accès refusé
            log_acces_refuse(user, view_func.__name__, f"Accès au poste refusé")
            messages.error(request, message or "Vous n'avez pas accès à ce poste.")
            return redirect(redirect_url)
        
        return _wrapped_view
    return decorator


def own_poste_only(redirect_url='common:dashboard', message=None):
    """
    Décorateur qui limite l'accès au poste d'affectation de l'utilisateur uniquement.
    Utile pour les agents qui ne doivent travailler que sur leur poste.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            
            # Admin et multi-postes peuvent passer
            if user_has_acces_tous_postes(user):
                return view_func(request, *args, **kwargs)
            
            # Vérifier que l'utilisateur a un poste d'affectation
            if not user.poste_affectation:
                messages.error(request, "Vous n'avez pas de poste d'affectation.")
                return redirect(redirect_url)
            
            # Extraire le poste demandé
            poste_demande = get_poste_from_request(request)
            if not poste_demande and 'poste_id' in kwargs:
                from accounts.models import Poste
                try:
                    poste_demande = Poste.objects.get(id=kwargs['poste_id'])
                except Poste.DoesNotExist:
                    pass
            
            # Si un poste est demandé, vérifier que c'est le bon
            if poste_demande and poste_demande.id != user.poste_affectation.id:
                log_acces_refuse(user, view_func.__name__, "Tentative d'accès à un autre poste")
                messages.error(request, message or "Vous ne pouvez accéder qu'à votre poste d'affectation.")
                return redirect(redirect_url)
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    return decorator


# ===================================================================
# SECTION 11: DÉCORATEURS POUR API/AJAX
# ===================================================================

def api_permission_required(permission_name):
    """
    Décorateur pour les vues API/AJAX.
    Retourne une réponse JSON en cas d'erreur.
    
    Usage:
        @api_permission_required('peut_voir_tracabilite_tickets')
        def api_recherche_ticket(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Vérifier l'authentification
            if not request.user.is_authenticated:
                return JsonResponse({
                    'success': False,
                    'error': 'Authentification requise',
                    'code': 'not_authenticated'
                }, status=401)
            
            # Vérifier la permission
            if isinstance(permission_name, (list, tuple)):
                has_perm = has_any_permission(request.user, permission_name)
            else:
                has_perm = has_permission(request.user, permission_name)
            
            if has_perm:
                return view_func(request, *args, **kwargs)
            
            # Permission refusée
            log_acces_refuse(request.user, view_func.__name__, f"API permission: {permission_name}")
            
            return JsonResponse({
                'success': False,
                'error': 'Permission refusée',
                'code': 'permission_denied'
            }, status=403)
        
        return _wrapped_view
    return decorator


def api_poste_access_required():
    """
    Décorateur API qui vérifie l'accès au poste.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({
                    'success': False,
                    'error': 'Authentification requise'
                }, status=401)
            
            # Extraire et vérifier le poste
            poste = get_poste_from_request(request)
            if poste and not check_poste_access(request.user, poste):
                return JsonResponse({
                    'success': False,
                    'error': 'Accès au poste refusé'
                }, status=403)
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    return decorator


# ===================================================================
# SECTION 12: DÉCORATEURS COMBINÉS COURANTS
# ===================================================================

def inventaire_complet_required(redirect_url='common:dashboard'):
    """
    Décorateur combiné pour les fonctionnalités complètes d'inventaire.
    Requiert: peut_saisir_inventaire_admin ET peut_programmer_inventaire
    """
    return all_permissions_required(
        ['peut_saisir_inventaire_admin', 'peut_programmer_inventaire'],
        redirect_url=redirect_url,
        message="Vous n'avez pas toutes les permissions d'inventaire requises."
    )


def gestion_complete_required(redirect_url='common:dashboard'):
    """
    Décorateur combiné pour la gestion complète (postes + utilisateurs).
    Requiert: peut_gerer_postes ET peut_gerer_utilisateurs
    """
    return all_permissions_required(
        ['peut_gerer_postes', 'peut_gerer_utilisateurs'],
        redirect_url=redirect_url,
        message="Vous n'avez pas toutes les permissions de gestion requises."
    )


def pesage_complet_required(redirect_url='common:dashboard'):
    """
    Décorateur combiné pour toutes les opérations pesage.
    Requiert au moins une permission pesage.
    """
    return permission_required_granular(
        PERMISSIONS_PESAGE,
        redirect_url=redirect_url,
        message="Vous n'avez pas de permissions pour le module pesage."
    )


def stock_complet_required(redirect_url='common:dashboard'):
    """
    Décorateur combiné pour toutes les opérations stock.
    Requiert au moins une permission stock.
    """
    return permission_required_granular(
        PERMISSIONS_STOCK_PEAGE,
        redirect_url=redirect_url,
        message="Vous n'avez pas de permissions pour le module stock."
    )


# ===================================================================
# EXPORTS
# ===================================================================

__all__ = [
    # Génériques
    'permission_required_granular',
    'all_permissions_required',
    
    # Classification utilisateurs
    'admin_required',
    'service_central_required',
    'cisop_required',
    'chef_poste_required',
    'operationnel_pesage_required',
    'operationnel_peage_required',
    
    # Inventaires
    'inventaire_saisie_required',
    'inventaire_admin_required',
    'programmation_inventaire_required',
    'liste_inventaires_required',
    'liste_inventaires_admin_required',
    'stats_deperdition_required',
    
    # Recettes péage
    'saisie_recette_peage_required',
    'liste_recettes_peage_required',
    'import_recettes_peage_required',
    
    # Quittances péage
    'saisie_quittance_peage_required',
    'comptabiliser_quittances_peage_required',
    
    # Pesage
    'saisie_amende_required',
    'saisie_pesee_required',
    'validation_paiement_amende_required',
    'liste_amendes_required',
    'saisie_quittance_pesage_required',
    'comptabiliser_quittances_pesage_required',
    'historique_pesees_required',
    'stats_pesage_required',
    'historique_vehicule_pesage_required',
    
    # Stock péage
    'charger_stock_peage_required',
    'transferer_stock_peage_required',
    'tracabilite_tickets_required',
    'bordereaux_peage_required',
    'simuler_commandes_required',
    
    # Gestion
    'gestion_postes_required',
    'ajout_poste_required',
    'gestion_utilisateurs_required',
    'creation_utilisateur_required',
    'journal_audit_required',
    'parametrage_global_required',
    
    # Rapports
    'rapports_defaillants_peage_required',
    'rapports_defaillants_pesage_required',
    'rapport_inventaires_required',
    'classement_peage_required',
    'classement_pesage_required',
    
    # Vérification poste
    'poste_access_required',
    'own_poste_only',
    
    # API
    'api_permission_required',
    'api_poste_access_required',
    
    # Combinés
    'inventaire_complet_required',
    'gestion_complete_required',
    'pesage_complet_required',
    'stock_complet_required',
]