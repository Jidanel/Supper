# ===================================================================
# common/permissions.py - Module de gestion des permissions SUPPER
# VERSION COMPLÈTE - 73 PERMISSIONS GRANULAIRES
# ===================================================================
"""
Module centralisant toutes les vérifications de permissions pour SUPPER.
Ce module remplace les anciennes vérifications basées sur is_admin par
des vérifications granulaires basées sur les permissions individuelles.

UTILISATION:
    from common.permissions import (
        has_permission,
        get_postes_accessibles,
        peut_saisir_inventaire,
        get_permissions_summary
    )
    
    # Dans une vue
    if has_permission(request.user, 'peut_saisir_inventaire_normal'):
        # L'utilisateur peut saisir un inventaire
        pass
"""

from django.db.models import Q
from functools import wraps
import logging

logger = logging.getLogger('supper.permissions')


# ===================================================================
# CONSTANTES - LISTES DE CLASSIFICATION DES HABILITATIONS
# ===================================================================

# Habilitations qui DOIVENT être affectées à une station de PESAGE
HABILITATIONS_PESAGE = [
    'chef_station_pesage',
    'regisseur_pesage',
    'chef_equipe_pesage',
    'chef_pesage',  # Alias pour compatibilité
]

# Habilitations qui DOIVENT être affectées à un poste de PÉAGE
HABILITATIONS_PEAGE = [
    'chef_peage',
    'agent_inventaire',
]

# Habilitations avec accès à TOUS les postes
HABILITATIONS_MULTI_POSTES = [
    # Administrateurs
    'admin_principal',
    'coord_psrr',
    # Services centraux
    'serv_info',
    'serv_emission',
    'chef_ag',
    'serv_controle',
    'serv_ordre',
    'imprimerie',
    # CISOP
    'cisop_peage',
    'cisop_pesage',
    # Autres
    'focal_regional',
    'chef_service',
    'regisseur',
    'comptable_mat',
    # Anciens noms (alias)
    'chef_ordre',
    'chef_controle',
]

# Habilitations administrateurs (accès complet)
HABILITATIONS_ADMIN = [
    'admin_principal',
    'coord_psrr',
    'serv_info',
]

# Habilitations services centraux (accès étendu)
HABILITATIONS_SERVICES_CENTRAUX = [
    'admin_principal',
    'coord_psrr',
    'serv_info',
    'serv_emission',
    'chef_ag',
    'serv_controle',
    'serv_ordre',
]

# Habilitations CISOP
HABILITATIONS_CISOP = [
    'cisop_peage',
    'cisop_pesage',
]

# Habilitations chefs de poste
HABILITATIONS_CHEFS_POSTE = [
    'chef_peage',
    'chef_station_pesage',
    'chef_pesage',  # Alias
]

# Habilitations opérationnels pesage
HABILITATIONS_OPERATIONNELS_PESAGE = [
    'chef_station_pesage',
    'regisseur_pesage',
    'chef_equipe_pesage',
    'chef_pesage',  # Alias
]

# Habilitations opérationnels péage
HABILITATIONS_OPERATIONNELS_PEAGE = [
    'chef_peage',
    'agent_inventaire',
]

# Toutes les habilitations
TOUTES_HABILITATIONS = (
    HABILITATIONS_PESAGE +
    HABILITATIONS_PEAGE +
    HABILITATIONS_MULTI_POSTES
)


# ===================================================================
# LISTE EXHAUSTIVE DES 73 PERMISSIONS
# ===================================================================

# Permissions d'accès globales (7)
PERMISSIONS_ACCES_GLOBAL = [
    'acces_tous_postes',
    'peut_saisir_peage',
    'peut_saisir_pesage',
    'voir_recettes_potentielles',
    'voir_taux_deperdition',
    'voir_statistiques_globales',
    'peut_saisir_pour_autres_postes',
]

# Anciennes permissions modules (8) - conservées pour compatibilité
PERMISSIONS_MODULES_LEGACY = [
    'peut_gerer_peage',
    'peut_gerer_pesage',
    'peut_gerer_personnel',
    'peut_gerer_budget',
    'peut_gerer_inventaire',
    'peut_gerer_archives',
    'peut_gerer_stocks_psrr',
    'peut_gerer_stock_info',
]

# Permissions Inventaires (10)
PERMISSIONS_INVENTAIRES = [
    'peut_saisir_inventaire_normal',
    'peut_saisir_inventaire_admin',
    'peut_programmer_inventaire',
    'peut_voir_programmation_active',
    'peut_desactiver_programmation',
    'peut_voir_programmation_desactivee',
    'peut_voir_liste_inventaires',
    'peut_voir_liste_inventaires_admin',
    'peut_voir_jours_impertinents',
    'peut_voir_stats_deperdition',
]

# Permissions Recettes Péage (6)
PERMISSIONS_RECETTES_PEAGE = [
    'peut_saisir_recette_peage',
    'peut_voir_liste_recettes_peage',
    'peut_voir_stats_recettes_peage',
    'peut_importer_recettes_peage',
    'peut_voir_evolution_peage',
    'peut_voir_objectifs_peage',
]

# Permissions Quittances Péage (3)
PERMISSIONS_QUITTANCES_PEAGE = [
    'peut_saisir_quittance_peage',
    'peut_voir_liste_quittances_peage',
    'peut_comptabiliser_quittances_peage',
]

# Permissions Pesage (12)
PERMISSIONS_PESAGE = [
    'peut_voir_historique_vehicule_pesage',
    'peut_saisir_amende',
    'peut_saisir_pesee_jour',
    'peut_voir_objectifs_pesage',
    'peut_valider_paiement_amende',
    'peut_lister_amendes',
    'peut_saisir_quittance_pesage',
    'peut_comptabiliser_quittances_pesage',
    'peut_voir_liste_quittancements_pesage',
    'peut_voir_historique_pesees',
    'peut_voir_recettes_pesage',
    'peut_voir_stats_pesage',
]

# Permissions Stock Péage (9)
PERMISSIONS_STOCK_PEAGE = [
    'peut_charger_stock_peage',
    'peut_voir_liste_stocks_peage',
    'peut_voir_stock_date_peage',
    'peut_transferer_stock_peage',
    'peut_voir_tracabilite_tickets',
    'peut_voir_bordereaux_peage',
    'peut_voir_mon_stock_peage',
    'peut_voir_historique_stock_peage',
    'peut_simuler_commandes_peage',
]

# Permissions Gestion (6)
PERMISSIONS_GESTION = [
    'peut_gerer_postes',
    'peut_ajouter_poste',
    'peut_creer_poste_masse',
    'peut_gerer_utilisateurs',
    'peut_creer_utilisateur',
    'peut_voir_journal_audit',
]

# Permissions Rapports (7)
PERMISSIONS_RAPPORTS = [
    'peut_voir_rapports_defaillants_peage',
    'peut_voir_rapports_defaillants_pesage',
    'peut_voir_rapport_inventaires',
    'peut_voir_classement_peage_rendement',
    'peut_voir_classement_station_pesage',
    'peut_voir_classement_peage_deperdition',
    'peut_voir_classement_agents_inventaire',
]

# Permissions Autres (5)
PERMISSIONS_AUTRES = [
    'peut_parametrage_global',
    'peut_voir_compte_emploi',
    'peut_voir_pv_confrontation',
    'peut_authentifier_document',
    'peut_voir_tous_postes',
]

# Liste complète de TOUTES les permissions (73)
TOUTES_PERMISSIONS = (
    PERMISSIONS_ACCES_GLOBAL +
    PERMISSIONS_MODULES_LEGACY +
    PERMISSIONS_INVENTAIRES +
    PERMISSIONS_RECETTES_PEAGE +
    PERMISSIONS_QUITTANCES_PEAGE +
    PERMISSIONS_PESAGE +
    PERMISSIONS_STOCK_PEAGE +
    PERMISSIONS_GESTION +
    PERMISSIONS_RAPPORTS +
    PERMISSIONS_AUTRES
)


# ===================================================================
# SECTION 1: FONCTIONS DE CLASSIFICATION DES UTILISATEURS
# ===================================================================

def is_admin_user(user):
    """
    Vérifie si l'utilisateur a des privilèges administrateur complets.
    Inclut: admin_principal, coord_psrr, serv_info
    """
    if not user or not user.is_authenticated:
        return False
    return (
        user.is_superuser or
        getattr(user, 'habilitation', None) in HABILITATIONS_ADMIN
    )


def is_service_central(user):
    """
    Vérifie si l'utilisateur appartient à un service central.
    Inclut: admin, coord_psrr, serv_info, serv_emission, chef_ag, serv_controle, serv_ordre
    """
    if not user or not user.is_authenticated:
        return False
    return (
        user.is_superuser or
        getattr(user, 'habilitation', None) in HABILITATIONS_SERVICES_CENTRAUX
    )


def is_cisop(user):
    """
    Vérifie si l'utilisateur est un CISOP (péage ou pesage).
    """
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) in HABILITATIONS_CISOP


def is_cisop_peage(user):
    """Vérifie si l'utilisateur est CISOP Péage."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'cisop_peage'


def is_cisop_pesage(user):
    """Vérifie si l'utilisateur est CISOP Pesage."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'cisop_pesage'


def is_chef_poste(user):
    """
    Vérifie si l'utilisateur est un chef de poste (péage ou pesage).
    """
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) in HABILITATIONS_CHEFS_POSTE


def is_chef_poste_peage(user):
    """Vérifie si l'utilisateur est chef de poste péage."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'chef_peage'


def is_chef_station_pesage(user):
    """Vérifie si l'utilisateur est chef de station pesage."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) in ['chef_station_pesage', 'chef_pesage']


def is_agent_inventaire(user):
    """Vérifie si l'utilisateur est agent d'inventaire."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'agent_inventaire'


def is_regisseur_pesage(user):
    """Vérifie si l'utilisateur est régisseur de station pesage."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'regisseur_pesage'


def is_chef_equipe_pesage(user):
    """Vérifie si l'utilisateur est chef d'équipe pesage."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'chef_equipe_pesage'


def is_operationnel_pesage(user):
    """
    Vérifie si l'utilisateur est un opérationnel pesage.
    Inclut: chef_station_pesage, regisseur_pesage, chef_equipe_pesage
    """
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) in HABILITATIONS_OPERATIONNELS_PESAGE


def is_operationnel_peage(user):
    """
    Vérifie si l'utilisateur est un opérationnel péage.
    Inclut: chef_peage, agent_inventaire
    """
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) in HABILITATIONS_OPERATIONNELS_PEAGE


def is_service_emission(user):
    """Vérifie si l'utilisateur est du service émission et recouvrement."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'serv_emission'


def is_service_controle(user):
    """Vérifie si l'utilisateur est du service contrôle et validation."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'serv_controle'


def is_service_ordre(user):
    """Vérifie si l'utilisateur est du service ordre/secrétariat."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) in ['serv_ordre', 'chef_ordre']


def is_chef_affaires_generales(user):
    """Vérifie si l'utilisateur est chef des affaires générales."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'chef_ag'


def is_imprimerie_nationale(user):
    """Vérifie si l'utilisateur est de l'imprimerie nationale."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'imprimerie'


def is_point_focal_regional(user):
    """Vérifie si l'utilisateur est point focal régional."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'focal_regional'


def is_regisseur_central(user):
    """Vérifie si l'utilisateur est régisseur central."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'regisseur'


def is_comptable_matieres(user):
    """Vérifie si l'utilisateur est comptable matières."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'habilitation', None) == 'comptable_mat'


# ===================================================================
# SECTION 2: FONCTIONS D'ACCÈS AUX POSTES
# ===================================================================

def user_has_acces_tous_postes(user):
    """
    Vérifie si l'utilisateur a accès à tous les postes.
    Basé sur: acces_tous_postes, is_superuser, peut_voir_tous_postes ou habilitation multi-postes
    """
    if not user or not user.is_authenticated:
        return False
    
    # Superuser a toujours accès
    if user.is_superuser:
        return True
    
    # Vérifier l'attribut explicite
    if getattr(user, 'acces_tous_postes', False):
        return True
    
    # Vérifier peut_voir_tous_postes
    if getattr(user, 'peut_voir_tous_postes', False):
        return True
    
    # Vérifier par habilitation
    return getattr(user, 'habilitation', None) in HABILITATIONS_MULTI_POSTES


def get_postes_accessibles(user, type_poste=None):
    """
    Retourne le queryset des postes accessibles à l'utilisateur.
    
    Args:
        user: L'utilisateur
        type_poste: Optionnel, filtrer par type ('peage' ou 'pesage')
    
    Returns:
        QuerySet de Poste
    """
    from accounts.models import Poste
    
    if not user or not user.is_authenticated:
        return Poste.objects.none()
    
    # Si accès tous postes
    if user_has_acces_tous_postes(user):
        qs = Poste.objects.filter(is_active=True)
    else:
        # Accès limité au poste d'affectation
        poste = getattr(user, 'poste_affectation', None)
        if poste:
            qs = Poste.objects.filter(id=poste.id, is_active=True)
        else:
            return Poste.objects.none()
    
    # Filtrer par type si spécifié
    if type_poste:
        qs = qs.filter(type=type_poste)
    
    return qs.order_by('type', 'nom')


def get_postes_peage_accessibles(user):
    """Retourne les postes de péage accessibles à l'utilisateur."""
    return get_postes_accessibles(user, type_poste='peage')


def get_postes_pesage_accessibles(user):
    """Retourne les stations de pesage accessibles à l'utilisateur."""
    return get_postes_accessibles(user, type_poste='pesage')


def check_poste_access(user, poste):
    """
    Vérifie si l'utilisateur a accès à un poste spécifique.
    
    Args:
        user: L'utilisateur
        poste: Instance de Poste ou ID du poste
    
    Returns:
        bool: True si accès autorisé
    """
    if not user or not user.is_authenticated:
        return False
    
    # Accès tous postes
    if user_has_acces_tous_postes(user):
        return True
    
    # Récupérer le poste si c'est un ID
    if isinstance(poste, int):
        from accounts.models import Poste
        try:
            poste = Poste.objects.get(id=poste)
        except Poste.DoesNotExist:
            return False
    
    # Vérifier si c'est le poste d'affectation
    poste_affectation = getattr(user, 'poste_affectation', None)
    return poste_affectation and poste_affectation.id == poste.id


def get_poste_from_request(request):
    """
    Extrait le poste depuis les paramètres de la requête.
    Cherche dans GET puis POST les clés: poste, poste_id, station, station_id
    
    Returns:
        Instance de Poste ou None
    """
    from accounts.models import Poste
    
    # Liste des clés possibles
    keys = ['poste', 'poste_id', 'station', 'station_id', 'poste_affectation']
    
    poste_id = None
    for key in keys:
        poste_id = request.GET.get(key) or request.POST.get(key)
        if poste_id:
            break
    
    if poste_id:
        try:
            return Poste.objects.get(id=int(poste_id), is_active=True)
        except (Poste.DoesNotExist, ValueError, TypeError):
            pass
    
    return None


# ===================================================================
# SECTION 3: FONCTION GÉNÉRIQUE DE VÉRIFICATION DE PERMISSION
# ===================================================================

def has_permission(user, permission_name):
    """
    Vérifie si l'utilisateur possède une permission spécifique.
    
    Args:
        user: L'utilisateur
        permission_name: Nom de la permission (str)
    
    Returns:
        bool: True si l'utilisateur a la permission
    
    Usage:
        if has_permission(request.user, 'peut_saisir_inventaire_normal'):
            # Autoriser l'action
    """
    if not user or not user.is_authenticated:
        return False
    
    # Superuser a toutes les permissions
    if user.is_superuser:
        return True
    
    # Vérifier l'attribut de permission
    return getattr(user, permission_name, False)


def has_any_permission(user, permission_names):
    """
    Vérifie si l'utilisateur possède AU MOINS UNE des permissions.
    
    Args:
        user: L'utilisateur
        permission_names: Liste des noms de permissions
    
    Returns:
        bool: True si au moins une permission est accordée
    """
    if not user or not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    return any(getattr(user, perm, False) for perm in permission_names)


def has_all_permissions(user, permission_names):
    """
    Vérifie si l'utilisateur possède TOUTES les permissions.
    
    Args:
        user: L'utilisateur
        permission_names: Liste des noms de permissions
    
    Returns:
        bool: True si toutes les permissions sont accordées
    """
    if not user or not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    return all(getattr(user, perm, False) for perm in permission_names)


# ===================================================================
# SECTION 4: VÉRIFICATIONS PAR MODULE - PERMISSIONS D'ACCÈS GLOBAL
# ===================================================================

def peut_voir_tous_postes(user):
    """Vérifie si l'utilisateur peut voir tous les postes."""
    return has_permission(user, 'peut_voir_tous_postes')


def peut_saisir_peage(user):
    """Vérifie si l'utilisateur peut saisir des données péage."""
    return has_permission(user, 'peut_saisir_peage')


def peut_saisir_pesage(user):
    """Vérifie si l'utilisateur peut saisir des données pesage."""
    return has_permission(user, 'peut_saisir_pesage')


def peut_voir_recettes_potentielles(user):
    """Vérifie si l'utilisateur peut voir les recettes potentielles."""
    return has_permission(user, 'voir_recettes_potentielles')


def peut_voir_taux_deperdition(user):
    """Vérifie si l'utilisateur peut voir le taux de déperdition."""
    return has_permission(user, 'voir_taux_deperdition')


def peut_voir_statistiques_globales(user):
    """Vérifie si l'utilisateur peut voir les statistiques globales."""
    return has_permission(user, 'voir_statistiques_globales')


def peut_saisir_pour_autres_postes(user):
    """Vérifie si l'utilisateur peut saisir pour d'autres postes."""
    return has_permission(user, 'peut_saisir_pour_autres_postes')


# ===================================================================
# SECTION 5: VÉRIFICATIONS PAR MODULE - ANCIENNES PERMISSIONS (LEGACY)
# ===================================================================

def peut_gerer_peage(user):
    """Vérifie si l'utilisateur peut gérer le péage (legacy)."""
    return has_permission(user, 'peut_gerer_peage')


def peut_gerer_pesage(user):
    """Vérifie si l'utilisateur peut gérer le pesage (legacy)."""
    return has_permission(user, 'peut_gerer_pesage')


def peut_gerer_personnel(user):
    """Vérifie si l'utilisateur peut gérer le personnel (legacy)."""
    return has_permission(user, 'peut_gerer_personnel')


def peut_gerer_budget(user):
    """Vérifie si l'utilisateur peut gérer le budget (legacy)."""
    return has_permission(user, 'peut_gerer_budget')


def peut_gerer_inventaire(user):
    """Vérifie si l'utilisateur peut gérer l'inventaire (legacy)."""
    return has_permission(user, 'peut_gerer_inventaire')


def peut_gerer_archives(user):
    """Vérifie si l'utilisateur peut gérer les archives (legacy)."""
    return has_permission(user, 'peut_gerer_archives')


def peut_gerer_stocks_psrr(user):
    """Vérifie si l'utilisateur peut gérer les stocks PSRR (legacy)."""
    return has_permission(user, 'peut_gerer_stocks_psrr')


def peut_gerer_stock_info(user):
    """Vérifie si l'utilisateur peut gérer le stock informatique (legacy)."""
    return has_permission(user, 'peut_gerer_stock_info')


# ===================================================================
# SECTION 6: VÉRIFICATIONS PAR MODULE - INVENTAIRES (10 permissions)
# ===================================================================

def peut_saisir_inventaire_normal(user):
    """
    Vérifie si l'utilisateur peut saisir un inventaire normal.
    Habilitations: agent_inventaire, chef_peage, admin
    """
    return has_permission(user, 'peut_saisir_inventaire_normal')


def peut_saisir_inventaire_admin(user):
    """
    Vérifie si l'utilisateur peut saisir un inventaire administratif.
    Habilitations: admin uniquement
    """
    return has_permission(user, 'peut_saisir_inventaire_admin')


def peut_programmer_inventaire(user):
    """
    Vérifie si l'utilisateur peut programmer un inventaire.
    Habilitations: admin, serv_emission
    """
    return has_permission(user, 'peut_programmer_inventaire')


def peut_voir_programmation_active(user):
    """
    Vérifie si l'utilisateur peut voir la programmation active.
    Habilitations: admin, serv_emission
    """
    return has_permission(user, 'peut_voir_programmation_active')


def peut_desactiver_programmation(user):
    """
    Vérifie si l'utilisateur peut désactiver une programmation.
    Habilitations: admin uniquement
    """
    return has_permission(user, 'peut_desactiver_programmation')


def peut_voir_programmation_desactivee(user):
    """
    Vérifie si l'utilisateur peut voir les programmations désactivées.
    Habilitations: admin, serv_emission
    """
    return has_permission(user, 'peut_voir_programmation_desactivee')


def peut_voir_liste_inventaires(user):
    """
    Vérifie si l'utilisateur peut voir la liste des inventaires.
    Habilitations: chef_peage, agent_inventaire, admin, services
    """
    return has_permission(user, 'peut_voir_liste_inventaires')


def peut_voir_liste_inventaires_admin(user):
    """
    Vérifie si l'utilisateur peut voir la liste des inventaires admin.
    Habilitations: admin, serv_emission
    """
    return has_permission(user, 'peut_voir_liste_inventaires_admin')


def peut_voir_jours_impertinents(user):
    """
    Vérifie si l'utilisateur peut voir les jours impertinents.
    Habilitations: chef_peage, agent_inventaire, admin, serv_emission
    """
    return has_permission(user, 'peut_voir_jours_impertinents')


def peut_voir_stats_deperdition(user):
    """
    Vérifie si l'utilisateur peut voir les statistiques de déperdition.
    Habilitations: admin, cisop_peage, chef_peage, agent_inventaire
    """
    return has_permission(user, 'peut_voir_stats_deperdition')


# ===================================================================
# SECTION 7: VÉRIFICATIONS PAR MODULE - RECETTES PÉAGE (6 permissions)
# ===================================================================

def peut_saisir_recette_peage(user):
    """
    Vérifie si l'utilisateur peut saisir une recette péage.
    Habilitations: chef_peage, admin
    """
    return has_permission(user, 'peut_saisir_recette_peage')


def peut_voir_liste_recettes_peage(user):
    """
    Vérifie si l'utilisateur peut voir la liste des recettes péage.
    Habilitations: chef_peage, agent_inventaire, admin, services centraux
    """
    return has_permission(user, 'peut_voir_liste_recettes_peage')


def peut_voir_stats_recettes_peage(user):
    """
    Vérifie si l'utilisateur peut voir les statistiques recettes péage.
    Habilitations: chef_peage, agent_inventaire, admin, services centraux
    """
    return has_permission(user, 'peut_voir_stats_recettes_peage')


def peut_importer_recettes_peage(user):
    """
    Vérifie si l'utilisateur peut importer des recettes péage.
    Habilitations: admin, serv_emission
    """
    return has_permission(user, 'peut_importer_recettes_peage')


def peut_voir_evolution_peage(user):
    """
    Vérifie si l'utilisateur peut voir l'évolution péage.
    Habilitations: chef_peage, admin, services centraux, cisop_peage
    """
    return has_permission(user, 'peut_voir_evolution_peage')


def peut_voir_objectifs_peage(user):
    """
    Vérifie si l'utilisateur peut voir les objectifs péage.
    Habilitations: admin, services centraux, cisop_peage, chef_peage
    """
    return has_permission(user, 'peut_voir_objectifs_peage')


# ===================================================================
# SECTION 8: VÉRIFICATIONS PAR MODULE - QUITTANCES PÉAGE (3 permissions)
# ===================================================================

def peut_saisir_quittance_peage(user):
    """
    Vérifie si l'utilisateur peut saisir une quittance péage.
    Habilitations: chef_peage, admin
    """
    return has_permission(user, 'peut_saisir_quittance_peage')


def peut_voir_liste_quittances_peage(user):
    """
    Vérifie si l'utilisateur peut voir la liste des quittances péage.
    Habilitations: chef_peage, agent_inventaire, admin, services centraux
    """
    return has_permission(user, 'peut_voir_liste_quittances_peage')


def peut_comptabiliser_quittances_peage(user):
    """
    Vérifie si l'utilisateur peut comptabiliser les quittances péage.
    Habilitations: serv_emission, serv_controle, serv_ordre, cisop_peage, chef_peage, admin
    """
    return has_permission(user, 'peut_comptabiliser_quittances_peage')


# ===================================================================
# SECTION 9: VÉRIFICATIONS PAR MODULE - PESAGE (12 permissions)
# ===================================================================

def peut_voir_historique_vehicule_pesage(user):
    """
    Vérifie si l'utilisateur peut voir l'historique véhicule pesage.
    Habilitations: chef_station_pesage, regisseur_pesage, chef_equipe_pesage, admin
    """
    return has_permission(user, 'peut_voir_historique_vehicule_pesage')


def peut_saisir_amende(user):
    """
    Vérifie si l'utilisateur peut saisir une amende.
    Habilitations: chef_equipe_pesage, admin
    """
    return has_permission(user, 'peut_saisir_amende')


def peut_saisir_pesee_jour(user):
    """
    Vérifie si l'utilisateur peut saisir une pesée du jour.
    Habilitations: chef_station_pesage, chef_equipe_pesage, admin
    """
    return has_permission(user, 'peut_saisir_pesee_jour')


def peut_voir_objectifs_pesage(user):
    """
    Vérifie si l'utilisateur peut voir les objectifs pesage.
    Habilitations: admin, services centraux, cisop_pesage, opérationnels pesage
    """
    return has_permission(user, 'peut_voir_objectifs_pesage')


def peut_valider_paiement_amende(user):
    """
    Vérifie si l'utilisateur peut valider un paiement d'amende.
    Habilitations: regisseur_pesage, chef_equipe_pesage, chef_station_pesage, admin
    """
    return has_permission(user, 'peut_valider_paiement_amende')


def peut_lister_amendes(user):
    """
    Vérifie si l'utilisateur peut lister les amendes.
    Habilitations: admin, services centraux, cisop_pesage, tous opérationnels pesage
    """
    return has_permission(user, 'peut_lister_amendes')


def peut_saisir_quittance_pesage(user):
    """
    Vérifie si l'utilisateur peut saisir une quittance pesage.
    Habilitations: regisseur_pesage, admin
    """
    return has_permission(user, 'peut_saisir_quittance_pesage')


def peut_comptabiliser_quittances_pesage(user):
    """
    Vérifie si l'utilisateur peut comptabiliser les quittances pesage.
    Habilitations: serv_emission, serv_controle, serv_ordre, cisop_pesage, opérationnels pesage, admin
    """
    return has_permission(user, 'peut_comptabiliser_quittances_pesage')


def peut_voir_liste_quittancements_pesage(user):
    """
    Vérifie si l'utilisateur peut voir la liste des quittancements pesage.
    Habilitations: admin, services centraux, cisop_pesage, opérationnels pesage
    """
    return has_permission(user, 'peut_voir_liste_quittancements_pesage')


def peut_voir_historique_pesees(user):
    """
    Vérifie si l'utilisateur peut voir l'historique des pesées.
    Habilitations: admin, services centraux, cisop_pesage, opérationnels pesage
    """
    return has_permission(user, 'peut_voir_historique_pesees')


def peut_voir_recettes_pesage(user):
    """
    Vérifie si l'utilisateur peut voir les recettes pesage.
    Habilitations: admin, services centraux, cisop_pesage, opérationnels pesage
    """
    return has_permission(user, 'peut_voir_recettes_pesage')


def peut_voir_stats_pesage(user):
    """
    Vérifie si l'utilisateur peut voir les statistiques pesage.
    Habilitations: admin, services centraux, cisop_pesage, opérationnels pesage
    """
    return has_permission(user, 'peut_voir_stats_pesage')


# ===================================================================
# SECTION 10: VÉRIFICATIONS PAR MODULE - STOCK PÉAGE (9 permissions)
# ===================================================================

def peut_charger_stock_peage(user):
    """
    Vérifie si l'utilisateur peut charger du stock péage.
    Habilitations: admin, serv_emission
    """
    return has_permission(user, 'peut_charger_stock_peage')


def peut_voir_liste_stocks_peage(user):
    """
    Vérifie si l'utilisateur peut voir la liste des stocks péage.
    Habilitations: admin, serv_emission, serv_controle, serv_ordre, cisop_peage, chef_peage
    """
    return has_permission(user, 'peut_voir_liste_stocks_peage')


def peut_voir_stock_date_peage(user):
    """
    Vérifie si l'utilisateur peut voir le stock à une date donnée.
    Habilitations: admin, serv_emission, serv_controle, serv_ordre, chef_peage
    """
    return has_permission(user, 'peut_voir_stock_date_peage')


def peut_transferer_stock_peage(user):
    """
    Vérifie si l'utilisateur peut transférer du stock péage.
    Habilitations: chef_peage, admin, serv_emission
    """
    return has_permission(user, 'peut_transferer_stock_peage')


def peut_voir_tracabilite_tickets(user):
    """
    Vérifie si l'utilisateur peut voir la traçabilité des tickets.
    Habilitations: admin, services centraux, cisop_peage, chef_peage, agent_inventaire
    """
    return has_permission(user, 'peut_voir_tracabilite_tickets')


def peut_voir_bordereaux_peage(user):
    """
    Vérifie si l'utilisateur peut voir les bordereaux péage.
    Habilitations: admin, services centraux, cisop_peage, chef_peage, agent_inventaire
    """
    return has_permission(user, 'peut_voir_bordereaux_peage')


def peut_voir_mon_stock_peage(user):
    """
    Vérifie si l'utilisateur peut voir son propre stock péage.
    Habilitations: chef_peage, admin, serv_emission
    """
    return has_permission(user, 'peut_voir_mon_stock_peage')


def peut_voir_historique_stock_peage(user):
    """
    Vérifie si l'utilisateur peut voir l'historique du stock péage.
    Habilitations: admin, services centraux, cisop_peage, chef_peage, agent_inventaire
    """
    return has_permission(user, 'peut_voir_historique_stock_peage')


def peut_simuler_commandes_peage(user):
    """
    Vérifie si l'utilisateur peut simuler des commandes péage.
    Habilitations: admin, serv_emission
    """
    return has_permission(user, 'peut_simuler_commandes_peage')


# ===================================================================
# SECTION 11: VÉRIFICATIONS PAR MODULE - GESTION (6 permissions)
# ===================================================================

def peut_gerer_postes(user):
    """
    Vérifie si l'utilisateur peut gérer les postes.
    Habilitations: admin, chef_ag, serv_ordre
    """
    return has_permission(user, 'peut_gerer_postes')


def peut_ajouter_poste(user):
    """
    Vérifie si l'utilisateur peut ajouter un poste.
    Habilitations: admin, chef_ag, serv_ordre
    """
    return has_permission(user, 'peut_ajouter_poste')


def peut_creer_poste_masse(user):
    """
    Vérifie si l'utilisateur peut créer des postes en masse.
    Habilitations: admin, chef_ag, serv_ordre
    """
    return has_permission(user, 'peut_creer_poste_masse')


def peut_gerer_utilisateurs(user):
    """
    Vérifie si l'utilisateur peut gérer les utilisateurs.
    Habilitations: admin, chef_ag, serv_ordre
    """
    return has_permission(user, 'peut_gerer_utilisateurs')


def peut_creer_utilisateur(user):
    """
    Vérifie si l'utilisateur peut créer un utilisateur.
    Habilitations: admin, chef_ag, serv_ordre
    """
    return has_permission(user, 'peut_creer_utilisateur')


def peut_voir_journal_audit(user):
    """
    Vérifie si l'utilisateur peut voir le journal d'audit.
    Habilitations: admin, chef_ag, serv_controle, serv_ordre
    """
    return has_permission(user, 'peut_voir_journal_audit')


# ===================================================================
# SECTION 12: VÉRIFICATIONS PAR MODULE - RAPPORTS (7 permissions)
# ===================================================================

def peut_voir_rapports_defaillants_peage(user):
    """
    Vérifie si l'utilisateur peut voir les rapports des défaillants péage.
    Habilitations: admin, serv_emission, serv_controle
    """
    return has_permission(user, 'peut_voir_rapports_defaillants_peage')


def peut_voir_rapports_defaillants_pesage(user):
    """
    Vérifie si l'utilisateur peut voir les rapports des défaillants pesage.
    Habilitations: admin, serv_controle, cisop_pesage
    """
    return has_permission(user, 'peut_voir_rapports_defaillants_pesage')


def peut_voir_rapport_inventaires(user):
    """
    Vérifie si l'utilisateur peut voir le rapport des inventaires.
    Habilitations: admin, serv_emission, serv_controle, serv_ordre
    """
    return has_permission(user, 'peut_voir_rapport_inventaires')


def peut_voir_classement_peage_rendement(user):
    """
    Vérifie si l'utilisateur peut voir le classement péage par rendement.
    Habilitations: admin, serv_emission, serv_controle, serv_ordre, cisop_peage, chef_peage
    """
    return has_permission(user, 'peut_voir_classement_peage_rendement')


def peut_voir_classement_station_pesage(user):
    """
    Vérifie si l'utilisateur peut voir le classement des stations pesage.
    Habilitations: admin, serv_emission, serv_controle, serv_ordre, cisop_pesage, opérationnels pesage
    """
    return has_permission(user, 'peut_voir_classement_station_pesage')


def peut_voir_classement_peage_deperdition(user):
    """
    Vérifie si l'utilisateur peut voir le classement péage par déperdition.
    Habilitations: admin, serv_emission, serv_controle, serv_ordre, cisop_peage, chef_peage
    """
    return has_permission(user, 'peut_voir_classement_peage_deperdition')


def peut_voir_classement_agents_inventaire(user):
    """
    Vérifie si l'utilisateur peut voir le classement des agents inventaire.
    Habilitations: admin, serv_emission, serv_controle, serv_ordre, chef_peage
    """
    return has_permission(user, 'peut_voir_classement_agents_inventaire')


# ===================================================================
# SECTION 13: VÉRIFICATIONS PAR MODULE - AUTRES (5 permissions)
# ===================================================================

def peut_parametrage_global(user):
    """
    Vérifie si l'utilisateur peut accéder au paramétrage global.
    Habilitations: admin, chef_ag, serv_controle, serv_ordre
    """
    return has_permission(user, 'peut_parametrage_global')


def peut_voir_compte_emploi(user):
    """
    Vérifie si l'utilisateur peut voir le compte d'emploi.
    Habilitations: admin, serv_emission, serv_controle, serv_ordre, cisop_peage, chef_peage
    """
    return has_permission(user, 'peut_voir_compte_emploi')


def peut_voir_pv_confrontation(user):
    """
    Vérifie si l'utilisateur peut voir le PV de confrontation.
    Habilitations: admin, services centraux, cisop_peage, chef_peage, agent_inventaire
    """
    return has_permission(user, 'peut_voir_pv_confrontation')


def peut_authentifier_document(user):
    """
    Vérifie si l'utilisateur peut authentifier un document.
    Habilitations: admin, services centraux, cisop_peage, chef_peage, agent_inventaire
    """
    return has_permission(user, 'peut_authentifier_document')


# ===================================================================
# SECTION 14: RÉSUMÉ COMPLET DES PERMISSIONS (73 permissions)
# ===================================================================

def get_permissions_summary(user):
    """
    Retourne un dictionnaire complet de toutes les 73 permissions de l'utilisateur.
    Utile pour le contexte des templates et pour le débogage.
    
    Returns:
        dict: Dictionnaire avec toutes les permissions regroupées par catégorie
    """
    if not user or not user.is_authenticated:
        return {
            'is_authenticated': False,
            'acces_global': {},
            'modules_legacy': {},
            'inventaires': {},
            'recettes_peage': {},
            'quittances_peage': {},
            'pesage': {},
            'stock_peage': {},
            'gestion': {},
            'rapports': {},
            'autres': {},
            'meta': {},
        }
    
    return {
        'is_authenticated': True,
        
        # Métadonnées utilisateur
        'meta': {
            'is_superuser': user.is_superuser,
            'is_staff': user.is_staff,
            'habilitation': getattr(user, 'habilitation', None),
            'poste_affectation': getattr(user, 'poste_affectation', None),
            'acces_tous_postes': user_has_acces_tous_postes(user),
            'is_admin': is_admin_user(user),
            'is_service_central': is_service_central(user),
            'is_cisop': is_cisop(user),
            'is_chef_poste': is_chef_poste(user),
        },
        
        # Permissions d'accès global (7)
        'acces_global': {
            'acces_tous_postes': getattr(user, 'acces_tous_postes', False) or user.is_superuser,
            'peut_saisir_peage': getattr(user, 'peut_saisir_peage', False) or user.is_superuser,
            'peut_saisir_pesage': getattr(user, 'peut_saisir_pesage', False) or user.is_superuser,
            'voir_recettes_potentielles': getattr(user, 'voir_recettes_potentielles', False) or user.is_superuser,
            'voir_taux_deperdition': getattr(user, 'voir_taux_deperdition', False) or user.is_superuser,
            'voir_statistiques_globales': getattr(user, 'voir_statistiques_globales', False) or user.is_superuser,
            'peut_saisir_pour_autres_postes': getattr(user, 'peut_saisir_pour_autres_postes', False) or user.is_superuser,
        },
        
        # Anciennes permissions modules (8)
        'modules_legacy': {
            'peut_gerer_peage': getattr(user, 'peut_gerer_peage', False) or user.is_superuser,
            'peut_gerer_pesage': getattr(user, 'peut_gerer_pesage', False) or user.is_superuser,
            'peut_gerer_personnel': getattr(user, 'peut_gerer_personnel', False) or user.is_superuser,
            'peut_gerer_budget': getattr(user, 'peut_gerer_budget', False) or user.is_superuser,
            'peut_gerer_inventaire': getattr(user, 'peut_gerer_inventaire', False) or user.is_superuser,
            'peut_gerer_archives': getattr(user, 'peut_gerer_archives', False) or user.is_superuser,
            'peut_gerer_stocks_psrr': getattr(user, 'peut_gerer_stocks_psrr', False) or user.is_superuser,
            'peut_gerer_stock_info': getattr(user, 'peut_gerer_stock_info', False) or user.is_superuser,
        },
        
        # Permissions Inventaires (10)
        'inventaires': {
            'peut_saisir_inventaire_normal': getattr(user, 'peut_saisir_inventaire_normal', False) or user.is_superuser,
            'peut_saisir_inventaire_admin': getattr(user, 'peut_saisir_inventaire_admin', False) or user.is_superuser,
            'peut_programmer_inventaire': getattr(user, 'peut_programmer_inventaire', False) or user.is_superuser,
            'peut_voir_programmation_active': getattr(user, 'peut_voir_programmation_active', False) or user.is_superuser,
            'peut_desactiver_programmation': getattr(user, 'peut_desactiver_programmation', False) or user.is_superuser,
            'peut_voir_programmation_desactivee': getattr(user, 'peut_voir_programmation_desactivee', False) or user.is_superuser,
            'peut_voir_liste_inventaires': getattr(user, 'peut_voir_liste_inventaires', False) or user.is_superuser,
            'peut_voir_liste_inventaires_admin': getattr(user, 'peut_voir_liste_inventaires_admin', False) or user.is_superuser,
            'peut_voir_jours_impertinents': getattr(user, 'peut_voir_jours_impertinents', False) or user.is_superuser,
            'peut_voir_stats_deperdition': getattr(user, 'peut_voir_stats_deperdition', False) or user.is_superuser,
        },
        
        # Permissions Recettes Péage (6)
        'recettes_peage': {
            'peut_saisir_recette_peage': getattr(user, 'peut_saisir_recette_peage', False) or user.is_superuser,
            'peut_voir_liste_recettes_peage': getattr(user, 'peut_voir_liste_recettes_peage', False) or user.is_superuser,
            'peut_voir_stats_recettes_peage': getattr(user, 'peut_voir_stats_recettes_peage', False) or user.is_superuser,
            'peut_importer_recettes_peage': getattr(user, 'peut_importer_recettes_peage', False) or user.is_superuser,
            'peut_voir_evolution_peage': getattr(user, 'peut_voir_evolution_peage', False) or user.is_superuser,
            'peut_voir_objectifs_peage': getattr(user, 'peut_voir_objectifs_peage', False) or user.is_superuser,
        },
        
        # Permissions Quittances Péage (3)
        'quittances_peage': {
            'peut_saisir_quittance_peage': getattr(user, 'peut_saisir_quittance_peage', False) or user.is_superuser,
            'peut_voir_liste_quittances_peage': getattr(user, 'peut_voir_liste_quittances_peage', False) or user.is_superuser,
            'peut_comptabiliser_quittances_peage': getattr(user, 'peut_comptabiliser_quittances_peage', False) or user.is_superuser,
        },
        
        # Permissions Pesage (12)
        'pesage': {
            'peut_voir_historique_vehicule_pesage': getattr(user, 'peut_voir_historique_vehicule_pesage', False) or user.is_superuser,
            'peut_saisir_amende': getattr(user, 'peut_saisir_amende', False) or user.is_superuser,
            'peut_saisir_pesee_jour': getattr(user, 'peut_saisir_pesee_jour', False) or user.is_superuser,
            'peut_voir_objectifs_pesage': getattr(user, 'peut_voir_objectifs_pesage', False) or user.is_superuser,
            'peut_valider_paiement_amende': getattr(user, 'peut_valider_paiement_amende', False) or user.is_superuser,
            'peut_lister_amendes': getattr(user, 'peut_lister_amendes', False) or user.is_superuser,
            'peut_saisir_quittance_pesage': getattr(user, 'peut_saisir_quittance_pesage', False) or user.is_superuser,
            'peut_comptabiliser_quittances_pesage': getattr(user, 'peut_comptabiliser_quittances_pesage', False) or user.is_superuser,
            'peut_voir_liste_quittancements_pesage': getattr(user, 'peut_voir_liste_quittancements_pesage', False) or user.is_superuser,
            'peut_voir_historique_pesees': getattr(user, 'peut_voir_historique_pesees', False) or user.is_superuser,
            'peut_voir_recettes_pesage': getattr(user, 'peut_voir_recettes_pesage', False) or user.is_superuser,
            'peut_voir_stats_pesage': getattr(user, 'peut_voir_stats_pesage', False) or user.is_superuser,
        },
        
        # Permissions Stock Péage (9)
        'stock_peage': {
            'peut_charger_stock_peage': getattr(user, 'peut_charger_stock_peage', False) or user.is_superuser,
            'peut_voir_liste_stocks_peage': getattr(user, 'peut_voir_liste_stocks_peage', False) or user.is_superuser,
            'peut_voir_stock_date_peage': getattr(user, 'peut_voir_stock_date_peage', False) or user.is_superuser,
            'peut_transferer_stock_peage': getattr(user, 'peut_transferer_stock_peage', False) or user.is_superuser,
            'peut_voir_tracabilite_tickets': getattr(user, 'peut_voir_tracabilite_tickets', False) or user.is_superuser,
            'peut_voir_bordereaux_peage': getattr(user, 'peut_voir_bordereaux_peage', False) or user.is_superuser,
            'peut_voir_mon_stock_peage': getattr(user, 'peut_voir_mon_stock_peage', False) or user.is_superuser,
            'peut_voir_historique_stock_peage': getattr(user, 'peut_voir_historique_stock_peage', False) or user.is_superuser,
            'peut_simuler_commandes_peage': getattr(user, 'peut_simuler_commandes_peage', False) or user.is_superuser,
        },
        
        # Permissions Gestion (6)
        'gestion': {
            'peut_gerer_postes': getattr(user, 'peut_gerer_postes', False) or user.is_superuser,
            'peut_ajouter_poste': getattr(user, 'peut_ajouter_poste', False) or user.is_superuser,
            'peut_creer_poste_masse': getattr(user, 'peut_creer_poste_masse', False) or user.is_superuser,
            'peut_gerer_utilisateurs': getattr(user, 'peut_gerer_utilisateurs', False) or user.is_superuser,
            'peut_creer_utilisateur': getattr(user, 'peut_creer_utilisateur', False) or user.is_superuser,
            'peut_voir_journal_audit': getattr(user, 'peut_voir_journal_audit', False) or user.is_superuser,
        },
        
        # Permissions Rapports (7)
        'rapports': {
            'peut_voir_rapports_defaillants_peage': getattr(user, 'peut_voir_rapports_defaillants_peage', False) or user.is_superuser,
            'peut_voir_rapports_defaillants_pesage': getattr(user, 'peut_voir_rapports_defaillants_pesage', False) or user.is_superuser,
            'peut_voir_rapport_inventaires': getattr(user, 'peut_voir_rapport_inventaires', False) or user.is_superuser,
            'peut_voir_classement_peage_rendement': getattr(user, 'peut_voir_classement_peage_rendement', False) or user.is_superuser,
            'peut_voir_classement_station_pesage': getattr(user, 'peut_voir_classement_station_pesage', False) or user.is_superuser,
            'peut_voir_classement_peage_deperdition': getattr(user, 'peut_voir_classement_peage_deperdition', False) or user.is_superuser,
            'peut_voir_classement_agents_inventaire': getattr(user, 'peut_voir_classement_agents_inventaire', False) or user.is_superuser,
        },
        
        # Permissions Autres (5)
        'autres': {
            'peut_parametrage_global': getattr(user, 'peut_parametrage_global', False) or user.is_superuser,
            'peut_voir_compte_emploi': getattr(user, 'peut_voir_compte_emploi', False) or user.is_superuser,
            'peut_voir_pv_confrontation': getattr(user, 'peut_voir_pv_confrontation', False) or user.is_superuser,
            'peut_authentifier_document': getattr(user, 'peut_authentifier_document', False) or user.is_superuser,
            'peut_voir_tous_postes': getattr(user, 'peut_voir_tous_postes', False) or user.is_superuser,
        },
    }


def get_permissions_flat(user):
    """
    Retourne un dictionnaire plat de toutes les 73 permissions.
    Utile pour le contexte simplifié des templates.
    
    Returns:
        dict: Dictionnaire {permission_name: bool}
    """
    if not user or not user.is_authenticated:
        return {perm: False for perm in TOUTES_PERMISSIONS}
    
    return {
        perm: getattr(user, perm, False) or user.is_superuser
        for perm in TOUTES_PERMISSIONS
    }


def get_permissions_count(user):
    """
    Retourne le nombre de permissions actives pour l'utilisateur.
    
    Returns:
        dict: {'total': int, 'actives': int, 'pourcentage': float}
    """
    if not user or not user.is_authenticated:
        return {'total': len(TOUTES_PERMISSIONS), 'actives': 0, 'pourcentage': 0.0}
    
    if user.is_superuser:
        return {'total': len(TOUTES_PERMISSIONS), 'actives': len(TOUTES_PERMISSIONS), 'pourcentage': 100.0}
    
    actives = sum(1 for perm in TOUTES_PERMISSIONS if getattr(user, perm, False))
    total = len(TOUTES_PERMISSIONS)
    
    return {
        'total': total,
        'actives': actives,
        'pourcentage': round((actives / total) * 100, 1) if total > 0 else 0.0
    }


# ===================================================================
# SECTION 15: CONTEXT PROCESSOR POUR TEMPLATES
# ===================================================================

def permissions_context_processor(request):
    """
    Context processor pour injecter les permissions dans tous les templates.
    
    Ajouter dans settings.py:
    TEMPLATES = [{
        'OPTIONS': {
            'context_processors': [
                ...
                'common.permissions.permissions_context_processor',
            ],
        },
    }]
    
    Utilisation dans les templates:
        {% if user_permissions.inventaires.peut_saisir_inventaire_normal %}
            <a href="...">Saisir inventaire</a>
        {% endif %}
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {'user_permissions': get_permissions_summary(None)}
    
    return {
        'user_permissions': get_permissions_summary(request.user),
        'user_permissions_flat': get_permissions_flat(request.user),
        'user_permissions_count': get_permissions_count(request.user),
    }


# ===================================================================
# SECTION 16: UTILITAIRES DE LOGGING
# ===================================================================

def log_permission_check(user, permission_name, result, context=None):
    """
    Journalise une vérification de permission.
    Utile pour le débogage et l'audit.
    """
    user_info = f"{user.username}" if user and user.is_authenticated else "anonymous"
    status = "ACCORDÉE" if result else "REFUSÉE"
    context_info = f" - {context}" if context else ""
    
    logger.debug(f"Permission {permission_name}: {status} pour {user_info}{context_info}")


def log_acces_refuse(user, action, raison=None):
    """
    Journalise un accès refusé dans le journal d'audit.
    
    Args:
        user: L'utilisateur
        action: L'action tentée
        raison: Raison du refus (optionnel)
    """
    from accounts.models import JournalAudit
    
    if not user or not user.is_authenticated:
        return
    
    details = f"Tentative d'accès refusée: {action}"
    if raison:
        details += f" - Raison: {raison}"
    
    try:
        JournalAudit.objects.create(
            utilisateur=user,
            action="ACCES_REFUSE",
            details=details,
            succes=False
        )
        logger.warning(f"Accès refusé: {user.username} - {action}")
    except Exception as e:
        logger.error(f"Erreur lors de la journalisation de l'accès refusé: {e}")


# ===================================================================
# SECTION 17: FONCTIONS UTILITAIRES DIVERSES
# ===================================================================

def get_habilitation_display(habilitation):
    """
    Retourne le nom lisible d'une habilitation.
    """
    from accounts.models import Habilitation
    try:
        return dict(Habilitation.choices).get(habilitation, habilitation)
    except:
        return habilitation


def normaliser_habilitation(habilitation):
    """
    Normalise les alias d'habilitation vers leur forme canonique.
    """
    alias_map = {
        'chef_ordre': 'serv_ordre',
        'chef_controle': 'serv_controle',
        'chef_pesage': 'chef_station_pesage',
    }
    return alias_map.get(habilitation, habilitation)


def habilitation_requiert_poste(habilitation):
    """
    Retourne True si l'habilitation nécessite obligatoirement un poste.
    """
    habilitation_norm = normaliser_habilitation(habilitation)
    return habilitation_norm in HABILITATIONS_PESAGE or habilitation_norm in HABILITATIONS_PEAGE


def get_type_poste_requis(habilitation):
    """
    Retourne le type de poste requis pour une habilitation.
    Retourne 'pesage', 'peage', ou None si pas de contrainte.
    """
    habilitation_norm = normaliser_habilitation(habilitation)
    
    if habilitation_norm in HABILITATIONS_PESAGE:
        return 'pesage'
    elif habilitation_norm in HABILITATIONS_PEAGE:
        return 'peage'
    return None


def validate_user_poste_access(user, poste, raise_exception=False):
    """
    Valide que l'utilisateur a accès au poste spécifié.
    
    Args:
        user: L'utilisateur
        poste: Le poste à vérifier
        raise_exception: Si True, lève une exception si accès refusé
    
    Returns:
        bool: True si accès autorisé
    
    Raises:
        PermissionDenied: Si raise_exception=True et accès refusé
    """
    from django.core.exceptions import PermissionDenied
    
    has_access = check_poste_access(user, poste)
    
    if not has_access and raise_exception:
        log_acces_refuse(user, f"accès au poste {poste}", "Poste non autorisé")
        raise PermissionDenied("Vous n'avez pas accès à ce poste.")
    
    return has_access


# ===================================================================
# EXPORTS PUBLICS
# ===================================================================

__all__ = [
    # Constantes
    'HABILITATIONS_PESAGE',
    'HABILITATIONS_PEAGE',
    'HABILITATIONS_MULTI_POSTES',
    'HABILITATIONS_ADMIN',
    'HABILITATIONS_SERVICES_CENTRAUX',
    'HABILITATIONS_CISOP',
    'HABILITATIONS_CHEFS_POSTE',
    'HABILITATIONS_OPERATIONNELS_PESAGE',
    'HABILITATIONS_OPERATIONNELS_PEAGE',
    'TOUTES_HABILITATIONS',
    'TOUTES_PERMISSIONS',
    'PERMISSIONS_ACCES_GLOBAL',
    'PERMISSIONS_MODULES_LEGACY',
    'PERMISSIONS_INVENTAIRES',
    'PERMISSIONS_RECETTES_PEAGE',
    'PERMISSIONS_QUITTANCES_PEAGE',
    'PERMISSIONS_PESAGE',
    'PERMISSIONS_STOCK_PEAGE',
    'PERMISSIONS_GESTION',
    'PERMISSIONS_RAPPORTS',
    'PERMISSIONS_AUTRES',
    
    # Classification utilisateurs
    'is_admin_user',
    'is_service_central',
    'is_cisop',
    'is_cisop_peage',
    'is_cisop_pesage',
    'is_chef_poste',
    'is_chef_poste_peage',
    'is_chef_station_pesage',
    'is_agent_inventaire',
    'is_regisseur_pesage',
    'is_chef_equipe_pesage',
    'is_operationnel_pesage',
    'is_operationnel_peage',
    'is_service_emission',
    'is_service_controle',
    'is_service_ordre',
    'is_chef_affaires_generales',
    'is_imprimerie_nationale',
    'is_point_focal_regional',
    'is_regisseur_central',
    'is_comptable_matieres',
    
    # Accès postes
    'user_has_acces_tous_postes',
    'get_postes_accessibles',
    'get_postes_peage_accessibles',
    'get_postes_pesage_accessibles',
    'check_poste_access',
    'get_poste_from_request',
    'validate_user_poste_access',
    
    # Vérification générique
    'has_permission',
    'has_any_permission',
    'has_all_permissions',
    
    # Permissions accès global (7)
    'peut_voir_tous_postes',
    'peut_saisir_peage',
    'peut_saisir_pesage',
    'peut_voir_recettes_potentielles',
    'peut_voir_taux_deperdition',
    'peut_voir_statistiques_globales',
    'peut_saisir_pour_autres_postes',
    
    # Permissions legacy (8)
    'peut_gerer_peage',
    'peut_gerer_pesage',
    'peut_gerer_personnel',
    'peut_gerer_budget',
    'peut_gerer_inventaire',
    'peut_gerer_archives',
    'peut_gerer_stocks_psrr',
    'peut_gerer_stock_info',
    
    # Permissions inventaires (10)
    'peut_saisir_inventaire_normal',
    'peut_saisir_inventaire_admin',
    'peut_programmer_inventaire',
    'peut_voir_programmation_active',
    'peut_desactiver_programmation',
    'peut_voir_programmation_desactivee',
    'peut_voir_liste_inventaires',
    'peut_voir_liste_inventaires_admin',
    'peut_voir_jours_impertinents',
    'peut_voir_stats_deperdition',
    
    # Permissions recettes péage (6)
    'peut_saisir_recette_peage',
    'peut_voir_liste_recettes_peage',
    'peut_voir_stats_recettes_peage',
    'peut_importer_recettes_peage',
    'peut_voir_evolution_peage',
    'peut_voir_objectifs_peage',
    
    # Permissions quittances péage (3)
    'peut_saisir_quittance_peage',
    'peut_voir_liste_quittances_peage',
    'peut_comptabiliser_quittances_peage',
    
    # Permissions pesage (12)
    'peut_voir_historique_vehicule_pesage',
    'peut_saisir_amende',
    'peut_saisir_pesee_jour',
    'peut_voir_objectifs_pesage',
    'peut_valider_paiement_amende',
    'peut_lister_amendes',
    'peut_saisir_quittance_pesage',
    'peut_comptabiliser_quittances_pesage',
    'peut_voir_liste_quittancements_pesage',
    'peut_voir_historique_pesees',
    'peut_voir_recettes_pesage',
    'peut_voir_stats_pesage',
    
    # Permissions stock péage (9)
    'peut_charger_stock_peage',
    'peut_voir_liste_stocks_peage',
    'peut_voir_stock_date_peage',
    'peut_transferer_stock_peage',
    'peut_voir_tracabilite_tickets',
    'peut_voir_bordereaux_peage',
    'peut_voir_mon_stock_peage',
    'peut_voir_historique_stock_peage',
    'peut_simuler_commandes_peage',
    
    # Permissions gestion (6)
    'peut_gerer_postes',
    'peut_ajouter_poste',
    'peut_creer_poste_masse',
    'peut_gerer_utilisateurs',
    'peut_creer_utilisateur',
    'peut_voir_journal_audit',
    
    # Permissions rapports (7)
    'peut_voir_rapports_defaillants_peage',
    'peut_voir_rapports_defaillants_pesage',
    'peut_voir_rapport_inventaires',
    'peut_voir_classement_peage_rendement',
    'peut_voir_classement_station_pesage',
    'peut_voir_classement_peage_deperdition',
    'peut_voir_classement_agents_inventaire',
    
    # Permissions autres (5)
    'peut_parametrage_global',
    'peut_voir_compte_emploi',
    'peut_voir_pv_confrontation',
    'peut_authentifier_document',
    
    # Résumés et utilitaires
    'get_permissions_summary',
    'get_permissions_flat',
    'get_permissions_count',
    'permissions_context_processor',
    'log_permission_check',
    'log_acces_refuse',
    'get_habilitation_display',
    'normaliser_habilitation',
    'habilitation_requiert_poste',
    'get_type_poste_requis',
]