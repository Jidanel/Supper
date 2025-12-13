# ===================================================================
# Fichier : common/utils.py - VERSION CORRIGÉE
# Fonctions utilitaires SUPPER avec journalisation détaillée
# CORRECTION: Anti-duplication supprimée pour éviter le blocage des logs
# ===================================================================

from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.http import HttpResponseForbidden
from django.utils import timezone
from functools import wraps
from decimal import Decimal
from datetime import datetime, timedelta
import logging
import json
import time

logger = logging.getLogger('supper')


# ===================================================================
# CLASSIFICATION DES HABILITATIONS
# ===================================================================

HABILITATIONS_ADMIN = [
    'admin_principal',
    'coord_psrr',
    'serv_info',
]

HABILITATIONS_SERVICES_CENTRAUX = [
    'serv_emission',
    'chef_ag',
    'serv_controle',
    'serv_ordre',
]

HABILITATIONS_CISOP = [
    'cisop_peage',
    'cisop_pesage',
]

HABILITATIONS_CHEFS_PEAGE = ['chef_peage']
HABILITATIONS_CHEFS_PESAGE = ['chef_station_pesage']
HABILITATIONS_CHEFS = HABILITATIONS_CHEFS_PEAGE + HABILITATIONS_CHEFS_PESAGE

HABILITATIONS_OPERATIONNELS_PESAGE = [
    'regisseur_pesage',
    'chef_equipe_pesage',
]

HABILITATIONS_OPERATIONNELS_PEAGE = [
    'agent_inventaire',
    'caissier',
]

HABILITATIONS_AUTRES = [
    'focal_regional',
    'chef_service',
    'regisseur',
    'comptable_mat',
    'imprimerie',
]

HABILITATIONS_LEGACY = {
    'chef_ordre': 'serv_ordre',
    'chef_controle': 'serv_controle',
    'chef_pesage': 'chef_station_pesage',
}

HABILITATIONS_LABELS = {
    'admin_principal': "Administrateur Principal",
    'coord_psrr': "Coordonnateur PSRR",
    'serv_info': "Agent du Service Informatique",
    'serv_emission': "Agent du Service Émission et Recouvrement",
    'chef_ag': "Chef du Service Affaires Générales",
    'serv_controle': "Agent du Service Contrôle",
    'serv_ordre': "Agent du Service Ordre",
    'cisop_peage': "Agent CISOP Péage",
    'cisop_pesage': "Agent CISOP Pesage",
    'chef_peage': "Chef de Poste Péage",
    'chef_station_pesage': "Chef de Station Pesage",
    'regisseur_pesage': "Régisseur de Station Pesage",
    'chef_equipe_pesage': "Chef d'Équipe Pesage",
    'agent_inventaire': "Agent Inventaire",
    'caissier': "Caissier",
    'focal_regional': "Point Focal Régional",
    'chef_service': "Chef de Service",
    'regisseur': "Régisseur Central",
    'comptable_mat': "Comptable Matières",
    'imprimerie': "Agent de l'Imprimerie Nationale",
}


# ===================================================================
# FONCTIONS DE CLASSIFICATION DES UTILISATEURS
# ===================================================================

def get_habilitation_normalisee(habilitation):
    """Normalise une habilitation en gérant les alias legacy"""
    if not habilitation:
        return 'inconnu'
    return HABILITATIONS_LEGACY.get(habilitation, habilitation)


def get_habilitation_label(habilitation):
    """Retourne le label humain d'une habilitation"""
    habilitation = get_habilitation_normalisee(habilitation)
    return HABILITATIONS_LABELS.get(habilitation, habilitation.replace('_', ' ').title())


def is_admin_user(user):
    """Vérifie si l'utilisateur est un administrateur système"""
    if not user or not hasattr(user, 'is_authenticated'):
        return False
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    habilitation = get_habilitation_normalisee(getattr(user, 'habilitation', None))
    return habilitation in HABILITATIONS_ADMIN


def is_service_central(user):
    """Vérifie si l'utilisateur appartient à un service central"""
    if not user or not hasattr(user, 'habilitation'):
        return False
    habilitation = get_habilitation_normalisee(user.habilitation)
    return habilitation in (HABILITATIONS_ADMIN + HABILITATIONS_SERVICES_CENTRAUX)


def is_cisop(user):
    """Vérifie si l'utilisateur est un agent CISOP"""
    if not user or not hasattr(user, 'habilitation'):
        return False
    habilitation = get_habilitation_normalisee(user.habilitation)
    return habilitation in HABILITATIONS_CISOP


def is_chef_poste(user):
    """Vérifie si l'utilisateur est un chef de poste (péage ou pesage)"""
    if not user or not hasattr(user, 'habilitation'):
        return False
    habilitation = get_habilitation_normalisee(user.habilitation)
    return habilitation in HABILITATIONS_CHEFS


def is_chef_peage(user):
    """Vérifie si l'utilisateur est un chef de poste péage"""
    if not user or not hasattr(user, 'habilitation'):
        return False
    habilitation = get_habilitation_normalisee(user.habilitation)
    return habilitation in HABILITATIONS_CHEFS_PEAGE


def is_chef_pesage(user):
    """Vérifie si l'utilisateur est un chef de station pesage"""
    if not user or not hasattr(user, 'habilitation'):
        return False
    habilitation = get_habilitation_normalisee(user.habilitation)
    return habilitation in HABILITATIONS_CHEFS_PESAGE


def is_operationnel_pesage(user):
    """Vérifie si l'utilisateur est un opérationnel pesage"""
    if not user or not hasattr(user, 'habilitation'):
        return False
    habilitation = get_habilitation_normalisee(user.habilitation)
    return habilitation in HABILITATIONS_OPERATIONNELS_PESAGE


def is_operationnel_peage(user):
    """Vérifie si l'utilisateur est un opérationnel péage"""
    if not user or not hasattr(user, 'habilitation'):
        return False
    habilitation = get_habilitation_normalisee(user.habilitation)
    return habilitation in HABILITATIONS_OPERATIONNELS_PEAGE


def get_user_category(user):
    """Retourne la catégorie de l'utilisateur"""
    if not user or not hasattr(user, 'habilitation'):
        return "INCONNU"
    
    if user.is_superuser:
        return "SUPERADMIN"
    
    habilitation = get_habilitation_normalisee(user.habilitation)
    
    if habilitation in HABILITATIONS_ADMIN:
        return "ADMINISTRATEUR"
    elif habilitation in HABILITATIONS_SERVICES_CENTRAUX:
        return "SERVICE CENTRAL"
    elif habilitation in HABILITATIONS_CISOP:
        return "CISOP"
    elif habilitation in HABILITATIONS_CHEFS:
        return "CHEF DE POSTE"
    elif habilitation in HABILITATIONS_OPERATIONNELS_PESAGE:
        return "OPÉRATIONNEL PESAGE"
    elif habilitation in HABILITATIONS_OPERATIONNELS_PEAGE:
        return "OPÉRATIONNEL PÉAGE"
    elif habilitation == 'focal_regional':
        return "POINT FOCAL RÉGIONAL"
    else:
        return "AUTRE"


def get_niveau_acces(user):
    """Retourne le niveau d'accès de l'utilisateur"""
    if not user or not hasattr(user, 'habilitation'):
        return "AUCUN"
    
    if user.is_superuser:
        return "COMPLET"
    
    habilitation = get_habilitation_normalisee(user.habilitation)
    
    if habilitation in HABILITATIONS_ADMIN:
        return "COMPLET"
    elif habilitation in HABILITATIONS_SERVICES_CENTRAUX:
        return "ÉTENDU"
    elif habilitation in HABILITATIONS_CISOP:
        return "STANDARD+"
    elif habilitation in HABILITATIONS_CHEFS:
        return "STANDARD"
    elif habilitation in HABILITATIONS_OPERATIONNELS_PESAGE + HABILITATIONS_OPERATIONNELS_PEAGE:
        return "OPÉRATIONNEL"
    else:
        return "LIMITÉ"


# ===================================================================
# FONCTIONS DE DESCRIPTION CONTEXTUELLE DE L'UTILISATEUR
# ===================================================================

def get_user_description(user, include_poste=True):
    """
    Génère une description complète et contextuelle de l'utilisateur
    """
    if not user:
        return "Utilisateur inconnu"
    
    nom = getattr(user, 'nom_complet', user.username)
    habilitation = get_habilitation_normalisee(getattr(user, 'habilitation', 'inconnu'))
    role_label = get_habilitation_label(habilitation)
    
    if habilitation in HABILITATIONS_ADMIN + HABILITATIONS_SERVICES_CENTRAUX:
        if habilitation == 'coord_psrr':
            return f"{nom}, {role_label}"
        else:
            return f"{nom}, {role_label} (Administration Centrale)"
    
    elif habilitation in HABILITATIONS_CISOP:
        return f"{nom}, {role_label}"
    
    elif habilitation in HABILITATIONS_CHEFS_PEAGE:
        if include_poste and hasattr(user, 'poste_affectation') and user.poste_affectation:
            poste = user.poste_affectation
            return f"{nom}, Chef de Poste du {poste.nom}"
        return f"{nom}, Chef de Poste Péage"
    
    elif habilitation in HABILITATIONS_CHEFS_PESAGE:
        if include_poste and hasattr(user, 'poste_affectation') and user.poste_affectation:
            poste = user.poste_affectation
            return f"{nom}, Chef de la Station de Pesage de {poste.nom}"
        return f"{nom}, Chef de Station Pesage"
    
    elif habilitation in HABILITATIONS_OPERATIONNELS_PESAGE:
        if include_poste and hasattr(user, 'poste_affectation') and user.poste_affectation:
            poste = user.poste_affectation
            return f"{nom}, {role_label} à la Station de Pesage de {poste.nom}"
        return f"{nom}, {role_label}"
    
    elif habilitation == 'agent_inventaire':
        if include_poste and hasattr(user, 'poste_affectation') and user.poste_affectation:
            poste = user.poste_affectation
            type_str = "Péage" if getattr(poste, 'type', '') == 'peage' else "Station de Pesage"
            return f"{nom}, Agent Inventaire au {type_str} de {poste.nom}"
        return f"{nom}, Agent Inventaire"
    
    elif habilitation == 'caissier':
        if include_poste and hasattr(user, 'poste_affectation') and user.poste_affectation:
            poste = user.poste_affectation
            return f"{nom}, Caissier au {poste.nom}"
        return f"{nom}, Caissier"
    
    elif habilitation == 'focal_regional':
        if include_poste and hasattr(user, 'poste_affectation') and user.poste_affectation:
            poste = user.poste_affectation
            return f"{nom}, Point Focal Régional ({getattr(poste, 'region', '')})"
        return f"{nom}, Point Focal Régional"
    
    else:
        if include_poste and hasattr(user, 'poste_affectation') and user.poste_affectation:
            return f"{nom}, {role_label} ({user.poste_affectation.nom})"
        return f"{nom}, {role_label}"


def get_user_short_description(user):
    """Version courte de la description utilisateur"""
    if not user:
        return "Inconnu"
    
    nom = getattr(user, 'nom_complet', user.username)
    parts = nom.split()
    if len(parts) >= 2:
        short_name = f"{parts[0][0]}. {parts[-1]}"
    else:
        short_name = nom[:15]
    
    habilitation = get_habilitation_normalisee(getattr(user, 'habilitation', 'inconnu'))
    
    role_abbr = {
        'admin_principal': "Admin",
        'coord_psrr': "Coord. PSRR",
        'serv_info': "S. Info",
        'serv_emission': "S. Émission",
        'chef_ag': "Chef AG",
        'serv_controle': "S. Contrôle",
        'serv_ordre': "S. Ordre",
        'cisop_peage': "CISOP Péage",
        'cisop_pesage': "CISOP Pesage",
        'chef_peage': "Chef Péage",
        'chef_station_pesage': "Chef Pesage",
        'regisseur_pesage': "Rég. Pesage",
        'chef_equipe_pesage': "Chef Éq. Pesage",
        'agent_inventaire': "Agent Inv.",
        'caissier': "Caissier",
        'focal_regional': "PF Régional",
    }.get(habilitation, habilitation[:10])
    
    if hasattr(user, 'poste_affectation') and user.poste_affectation:
        poste_short = user.poste_affectation.nom[:15]
        return f"{short_name} ({role_abbr} {poste_short})"
    
    return f"{short_name} ({role_abbr})"


# ===================================================================
# FONCTION PRINCIPALE DE JOURNALISATION - VERSION CORRIGÉE
# ===================================================================

def log_user_action(user, action, details="", request=None, **extra_data):
    """
    Fonction PRINCIPALE pour journaliser une action utilisateur.
    
    VERSION CORRIGÉE: Anti-duplication SUPPRIMÉE pour éviter le blocage des logs.
    Chaque appel crée maintenant une entrée dans le journal.
    
    Args:
        user: Utilisateur effectuant l'action
        action: Nom de l'action (ex: "SAISIE_RECETTE", "Modification utilisateur")
        details: Détails de l'action (texte libre)
        request: Objet request Django (optionnel mais recommandé)
        **extra_data: Données supplémentaires structurées
    
    Returns:
        JournalAudit: L'entrée de journal créée, ou None en cas d'erreur
    """
    try:
        from accounts.models import JournalAudit
        
        # NOTE: Section ANTI-DUPLICATION SUPPRIMÉE volontairement
        # car elle bloquait tous les logs en production.
        # Chaque appel à log_user_action crée maintenant une entrée.
        
        # ===================================================================
        # EXTRACTION DES INFORMATIONS DE REQUÊTE
        # ===================================================================
        ip = None
        session_key = ''
        user_agent = ""
        url = ""
        method = ""
        duration = None
        
        if request:
            # IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')
            
            # Session
            session_key = getattr(request.session, 'session_key', '') or ''
            
            # User agent
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
            
            # URL et méthode
            url = request.path[:500] if request.path else ''
            method = request.method[:10] if request.method else ''
            
            # Durée
            if hasattr(request, '_audit_start_time'):
                duration_seconds = time.time() - request._audit_start_time
                duration = timedelta(seconds=duration_seconds)
        
        # ===================================================================
        # CONSTRUCTION DU MESSAGE DÉTAILLÉ
        # ===================================================================
        user_desc = get_user_description(user, include_poste=True)
        
        formatted_message = _format_action_message(
            user=user,
            user_desc=user_desc,
            action=action,
            details=details,
            extra_data=extra_data
        )
        
        # ===================================================================
        # CRÉATION DE L'ENTRÉE DE JOURNAL
        # ===================================================================
        log_entry = JournalAudit.objects.create(
            utilisateur=user,
            action=action,
            details=formatted_message,
            adresse_ip=ip,
            user_agent=user_agent,
            session_key=session_key,
            url_acces=url,
            methode_http=method,
            succes=True,
            statut_reponse=200,
            duree_execution=duration
        )
        
        # Log dans le fichier système
        category = get_user_category(user)
        icon = _get_category_icon(category)
        logger.info(f"{icon} {action} | {get_user_short_description(user)} | {details[:100] if details else 'OK'}")
        
        return log_entry
        
    except Exception as e:
        logger.error(f"Erreur journalisation: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def _format_action_message(user, user_desc, action, details, extra_data):
    """Formate le message d'action de manière contextuelle et détaillée"""
    
    action_upper = action.upper()
    
    # SAISIE DE RECETTE
    if 'RECETTE' in action_upper:
        montant = extra_data.get('montant')
        poste = extra_data.get('poste')
        date_action = extra_data.get('date_action') or extra_data.get('date')
        
        msg = f"{user_desc} a enregistré une recette"
        
        if montant:
            msg += f" de {format_montant_fcfa(montant)}"
        if poste:
            poste_nom = poste.nom if hasattr(poste, 'nom') else str(poste)
            msg += f" pour le poste {poste_nom}"
        if date_action:
            msg += f" pour la journée du {_format_date(date_action)}"
        if details:
            msg += f". {details}"
        
        return msg
    
    # SAISIE D'INVENTAIRE
    elif 'INVENTAIRE' in action_upper:
        poste = extra_data.get('poste')
        date_action = extra_data.get('date_action') or extra_data.get('date')
        nb_vehicules = extra_data.get('nb_vehicules') or extra_data.get('total_vehicules')
        periode = extra_data.get('periode')
        nb_periodes = extra_data.get('nb_periodes')
        
        msg = f"{user_desc} a saisi"
        
        if periode:
            msg += f" l'inventaire de la période {periode}"
        else:
            msg += " l'inventaire journalier"
        
        if poste:
            poste_nom = poste.nom if hasattr(poste, 'nom') else str(poste)
            msg += f" du poste {poste_nom}"
        if date_action:
            msg += f" du {_format_date(date_action)}"
        if nb_vehicules:
            msg += f" avec {nb_vehicules} véhicule(s) compté(s)"
        if nb_periodes:
            msg += f" ({nb_periodes} période(s) saisie(s))"
        if details:
            msg += f". {details}"
        
        return msg
    
    # GESTION UTILISATEUR
    elif 'UTILISATEUR' in action_upper or 'USER' in action_upper or 'MODIFICATION' in action_upper:
        utilisateur_cible = extra_data.get('utilisateur_cible') or extra_data.get('user_cible')
        operation = extra_data.get('operation', 'modification')
        
        msg = f"{user_desc} a effectué une {operation}"
        
        if utilisateur_cible:
            if hasattr(utilisateur_cible, 'nom_complet'):
                msg += f" sur le compte de {utilisateur_cible.nom_complet} ({utilisateur_cible.username})"
            else:
                msg += f" sur le compte {utilisateur_cible}"
        
        if details:
            msg += f". {details}"
        
        return msg
    
    # CONNEXION / DÉCONNEXION
    elif 'CONNEXION' in action_upper or 'LOGIN' in action_upper:
        msg = f"{user_desc} s'est connecté(e) au système"
        if details:
            msg += f". {details}"
        return msg
    
    elif 'DÉCONNEXION' in action_upper or 'LOGOUT' in action_upper:
        msg = f"{user_desc} s'est déconnecté(e) du système"
        if details:
            msg += f". {details}"
        return msg
    
    # CAS GÉNÉRIQUE
    else:
        msg = f"{user_desc}"
        
        if details:
            msg += f" | {details}"
        
        if extra_data:
            extras = []
            for key, value in extra_data.items():
                if value is not None:
                    formatted_key = key.replace('_', ' ').title()
                    if isinstance(value, (int, float, Decimal)) and 'montant' in key.lower():
                        value = format_montant_fcfa(value)
                    elif hasattr(value, 'nom'):
                        value = value.nom
                    elif hasattr(value, 'strftime'):
                        value = _format_date(value)
                    extras.append(f"{formatted_key}: {value}")
            
            if extras:
                msg += f" | {' | '.join(extras)}"
        
        return msg


def _get_category_icon(category):
    """Retourne l'icône emoji correspondant à la catégorie"""
    icons = {
        "SUPERADMIN": "🔐",
        "ADMINISTRATEUR": "🔐",
        "SERVICE CENTRAL": "📋",
        "CISOP": "🔍",
        "CHEF DE POSTE": "👔",
        "OPÉRATIONNEL PESAGE": "⚖️",
        "OPÉRATIONNEL PÉAGE": "🚗",
        "POINT FOCAL RÉGIONAL": "🗺️",
        "AUTRE": "👤",
        "INCONNU": "❓",
    }
    return icons.get(category, "📌")


def _format_date(date_value):
    """Formate une date en français"""
    if date_value is None:
        return "date inconnue"
    
    if isinstance(date_value, str):
        try:
            date_value = datetime.strptime(date_value, '%Y-%m-%d').date()
        except ValueError:
            return date_value
    
    if hasattr(date_value, 'strftime'):
        return date_value.strftime('%d/%m/%Y')
    
    return str(date_value)


# ===================================================================
# FONCTIONS DE JOURNALISATION SPÉCIALISÉES
# ===================================================================

def log_saisie_recette(user, poste, montant, date_recette, request=None, **extra):
    """Journalise une saisie de recette"""
    log_user_action(
        user,
        "SAISIE_RECETTE",
        f"Recette de {format_montant_fcfa(montant)}",
        request,
        montant=montant,
        poste=poste,
        date_action=date_recette,
        **extra
    )


def log_saisie_inventaire(user, poste, date_inventaire, nb_vehicules=None, 
                          periode=None, nb_periodes=None, request=None, **extra):
    """Journalise une saisie d'inventaire"""
    log_user_action(
        user,
        "SAISIE_INVENTAIRE",
        f"Inventaire {periode if periode else 'journalier'}",
        request,
        poste=poste,
        date_action=date_inventaire,
        nb_vehicules=nb_vehicules,
        periode=periode,
        nb_periodes=nb_periodes,
        **extra
    )


def log_saisie_amende(user, station, montant, vehicule, date_amende, request=None, **extra):
    """Journalise une saisie d'amende pesage"""
    log_user_action(
        user,
        "SAISIE_AMENDE",
        f"Amende de {format_montant_fcfa(montant)} pour {vehicule}",
        request,
        montant=montant,
        station=station,
        vehicule=vehicule,
        date_action=date_amende,
        **extra
    )


def log_operation_stock(user, poste, type_operation, quantite, serie=None, request=None, **extra):
    """Journalise une opération de stock"""
    log_user_action(
        user,
        f"STOCK_{type_operation.upper()}",
        f"{type_operation.title()} de {quantite} tickets",
        request,
        poste=poste,
        type_operation=type_operation,
        quantite=quantite,
        serie=serie,
        **extra
    )


def log_validation(user, element, poste=None, date_element=None, request=None, **extra):
    """Journalise une validation"""
    log_user_action(
        user,
        "VALIDATION",
        f"Validation de {element}",
        request,
        element=element,
        poste=poste,
        date_action=date_element,
        **extra
    )


def log_verrouillage(user, element, poste=None, date_element=None, request=None, **extra):
    """Journalise un verrouillage"""
    log_user_action(
        user,
        "VERROUILLAGE",
        f"Verrouillage de {element}",
        request,
        element=element,
        poste=poste,
        date_action=date_element,
        **extra
    )


def log_export(user, type_export, format_export="PDF", periode=None, request=None, **extra):
    """Journalise un export ou génération de rapport"""
    log_user_action(
        user,
        "EXPORT_RAPPORT",
        f"Génération {type_export} ({format_export})",
        request,
        type_export=type_export,
        format=format_export,
        periode=periode,
        **extra
    )


def log_acces_refuse(user, ressource, raison="Permission insuffisante", request=None):
    """Journalise un accès refusé"""
    try:
        from accounts.models import JournalAudit
        
        ip = None
        url = ""
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')
            url = request.path
        
        user_desc = get_user_description(user)
        
        JournalAudit.objects.create(
            utilisateur=user,
            action="ACCÈS_REFUSÉ",
            details=f"{user_desc} - Accès refusé à {ressource}: {raison}",
            adresse_ip=ip,
            url_acces=url,
            succes=False,
            statut_reponse=403
        )
        
        logger.warning(f"⛔ ACCÈS REFUSÉ | {get_user_short_description(user)} | {ressource} | {raison}")
        
    except Exception as e:
        logger.error(f"Erreur journalisation accès refusé: {str(e)}")


def log_erreur_action(user, action, erreur, request=None, **extra):
    """Journalise une erreur lors d'une action"""
    try:
        from accounts.models import JournalAudit
        
        user_desc = get_user_description(user)
        
        ip = None
        url = ""
        if request:
            ip = request.META.get('REMOTE_ADDR')
            url = request.path
        
        JournalAudit.objects.create(
            utilisateur=user,
            action=f"ERREUR_{action}",
            details=f"{user_desc} a rencontré une erreur: {erreur}",
            adresse_ip=ip,
            url_acces=url,
            succes=False,
            statut_reponse=500
        )
        
        logger.error(f"❌ ERREUR | {get_user_short_description(user)} | {action} | {erreur}")
        
    except Exception as e:
        logger.error(f"Erreur journalisation erreur: {str(e)}")


# ===================================================================
# DÉCORATEURS DE JOURNALISATION
# ===================================================================

def log_action(action_name, include_params=False):
    """Décorateur pour journaliser automatiquement des actions"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if hasattr(request, 'user') and request.user.is_authenticated:
                extra_details = f"Paramètres: {args}" if include_params and args else ""
                
                try:
                    response = view_func(request, *args, **kwargs)
                    
                    log_user_action(
                        request.user,
                        action_name,
                        f"Action réussie. {extra_details}",
                        request
                    )
                    
                    return response
                    
                except Exception as e:
                    log_erreur_action(request.user, action_name, str(e), request)
                    raise
            else:
                return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def log_action_detailed(action_name, get_details_func=None):
    """Décorateur avancé pour journalisation avec extraction de détails"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if hasattr(request, 'user') and request.user.is_authenticated:
                try:
                    response = view_func(request, *args, **kwargs)
                    
                    extra_data = {}
                    if get_details_func:
                        try:
                            extra_data = get_details_func(request, response, *args, **kwargs) or {}
                        except Exception:
                            pass
                    
                    log_user_action(
                        request.user,
                        action_name,
                        "Action réussie",
                        request,
                        **extra_data
                    )
                    
                    return response
                    
                except Exception as e:
                    log_erreur_action(request.user, action_name, str(e), request)
                    raise
            else:
                return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


# ===================================================================
# DÉCORATEURS DE PERMISSIONS
# ===================================================================

def require_permission(permission_field):
    """Décorateur pour vérifier les permissions granulaires SUPPER"""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not hasattr(request.user, permission_field):
                log_acces_refuse(
                    request.user,
                    request.path,
                    f"Permission {permission_field} non définie",
                    request
                )
                return HttpResponseForbidden("Permission insuffisante")
            
            if not getattr(request.user, permission_field):
                log_acces_refuse(
                    request.user,
                    request.path,
                    f"Permission {permission_field} désactivée",
                    request
                )
                return HttpResponseForbidden("Permission insuffisante")
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def require_any_permission(*permission_fields):
    """Décorateur pour vérifier qu'au moins une permission est accordée"""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            for perm in permission_fields:
                if hasattr(request.user, perm) and getattr(request.user, perm):
                    return view_func(request, *args, **kwargs)
            
            log_acces_refuse(
                request.user,
                request.path,
                f"Aucune des permissions requises: {', '.join(permission_fields)}",
                request
            )
            return HttpResponseForbidden("Permission insuffisante")
        
        return wrapper
    return decorator


def require_all_permissions(*permission_fields):
    """Décorateur pour vérifier que toutes les permissions sont accordées"""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            missing = []
            for perm in permission_fields:
                if not hasattr(request.user, perm) or not getattr(request.user, perm):
                    missing.append(perm)
            
            if missing:
                log_acces_refuse(
                    request.user,
                    request.path,
                    f"Permissions manquantes: {', '.join(missing)}",
                    request
                )
                return HttpResponseForbidden("Permission insuffisante")
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def require_habilitation(*habilitations):
    """Décorateur pour vérifier l'habilitation de l'utilisateur"""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            user_hab = get_habilitation_normalisee(getattr(request.user, 'habilitation', None))
            normalized_habs = [get_habilitation_normalisee(h) for h in habilitations]
            
            if user_hab not in normalized_habs:
                log_acces_refuse(
                    request.user,
                    request.path,
                    f"Habilitation {user_hab} non autorisée (requises: {', '.join(habilitations)})",
                    request
                )
                return HttpResponseForbidden("Habilitation insuffisante")
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def require_poste_access(view_func):
    """Décorateur pour vérifier l'accès au poste demandé"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        poste_id = kwargs.get('poste_id') or kwargs.get('pk') or request.GET.get('poste_id')
        
        if poste_id:
            try:
                from accounts.models import Poste
                poste = Poste.objects.get(id=poste_id)
                
                if not request.user.peut_acceder_poste(poste):
                    log_acces_refuse(
                        request.user,
                        f"Poste {poste.nom}",
                        "Accès au poste non autorisé",
                        request
                    )
                    return HttpResponseForbidden("Accès au poste non autorisé")
                
            except Poste.DoesNotExist:
                return HttpResponseForbidden("Poste inexistant")
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


# ===================================================================
# MIXIN POUR VUES BASÉES SUR LES CLASSES
# ===================================================================

class AuditMixin:
    """Mixin pour les vues basées sur les classes avec journalisation"""
    audit_action = None
    required_permission = None
    required_habilitation = None
    audit_log_get = True  # Par défaut, journalise aussi les GET
    
    def dispatch(self, request, *args, **kwargs):
        # Vérifier l'habilitation si spécifiée
        if self.required_habilitation and request.user.is_authenticated:
            user_hab = get_habilitation_normalisee(getattr(request.user, 'habilitation', None))
            
            habs = self.required_habilitation
            if isinstance(habs, str):
                habs = [habs]
            
            normalized_habs = [get_habilitation_normalisee(h) for h in habs]
            
            if user_hab not in normalized_habs:
                log_acces_refuse(
                    request.user,
                    f"Vue {self.__class__.__name__}",
                    f"Habilitation {user_hab} non autorisée",
                    request
                )
                return HttpResponseForbidden("Habilitation insuffisante")
        
        # Vérifier les permissions si spécifiées
        if self.required_permission and request.user.is_authenticated:
            if not hasattr(request.user, self.required_permission) or \
               not getattr(request.user, self.required_permission):
                log_acces_refuse(
                    request.user,
                    f"Vue {self.__class__.__name__}",
                    f"Permission {self.required_permission} manquante",
                    request
                )
                return HttpResponseForbidden("Permission insuffisante")
        
        # Journaliser l'accès si action spécifiée
        if self.audit_action and request.user.is_authenticated:
            # Ne journaliser GET que si audit_log_get est True
            if request.method != 'GET' or self.audit_log_get:
                log_user_action(
                    request.user,
                    f"ACCES_{self.audit_action}",
                    f"Accès à la vue {self.__class__.__name__}",
                    request
                )
        
        return super().dispatch(request, *args, **kwargs)


# ===================================================================
# DÉCORATEURS PRÉ-CONFIGURÉS
# ===================================================================

admin_required = user_passes_test(is_admin_user)
chef_poste_required = user_passes_test(is_chef_poste)
chef_peage_required = user_passes_test(is_chef_peage)
chef_pesage_required = user_passes_test(is_chef_pesage)
service_central_required = user_passes_test(is_service_central)
cisop_required = user_passes_test(is_cisop)


# ===================================================================
# FONCTIONS UTILITAIRES GÉNÉRALES
# ===================================================================

def get_user_postes_accessibles(user):
    """Retourne la liste des postes accessibles pour un utilisateur"""
    if user.is_authenticated:
        return user.get_postes_accessibles()
    else:
        from accounts.models import Poste
        return Poste.objects.none()


def can_user_access_poste(user, poste):
    """Vérifie si un utilisateur peut accéder à un poste donné"""
    if user.is_authenticated:
        return user.peut_acceder_poste(poste)
    return False


def format_montant_fcfa(montant):
    """Formate un montant en FCFA avec séparateurs de milliers"""
    if montant is None:
        return "0 FCFA"
    
    try:
        montant_int = int(montant)
        return f"{montant_int:,} FCFA".replace(',', ' ')
    except (ValueError, TypeError):
        return "0 FCFA"


def calculer_couleur_alerte(taux_deperdition):
    """Détermine la couleur d'alerte selon le taux de déperdition"""
    if taux_deperdition is None:
        return 'secondary'
    
    from django.conf import settings
    config = getattr(settings, 'SUPPER_CONFIG', {})
    seuil_orange = config.get('SEUIL_ALERTE_ORANGE', -10)
    seuil_rouge = config.get('SEUIL_ALERTE_ROUGE', -30)
    
    if taux_deperdition > seuil_orange:
        return 'success'
    elif taux_deperdition >= seuil_rouge:
        return 'warning'
    else:
        return 'danger'


def get_classe_badge_alerte(taux_deperdition):
    """Retourne la classe CSS Bootstrap pour le badge d'alerte"""
    couleur = calculer_couleur_alerte(taux_deperdition)
    return f"badge bg-{couleur}"


def get_periodes_inventaire():
    """Retourne la liste des périodes horaires pour l'inventaire"""
    from django.conf import settings
    config = getattr(settings, 'SUPPER_CONFIG', {})
    return config.get('PERIODES_INVENTAIRE', [
        '08h-09h', '09h-10h', '10h-11h', '11h-12h',
        '12h-13h', '13h-14h', '14h-15h', '15h-16h',
        '16h-17h', '17h-18h'
    ])


def valider_numero_telephone(numero):
    """Valide un numéro de téléphone camerounais"""
    import re
    pattern = r'^\+?237?[0-9]{8,9}$'
    return re.match(pattern, str(numero)) is not None


def generer_code_poste(nom_poste, region, type_poste='peage'):
    """Génère automatiquement un code de poste basé sur le nom et la région"""
    from accounts.models import Poste
    
    nom_code = ''.join(c for c in nom_poste.upper() if c.isalpha())[:3]
    region_code = ''.join(c for c in region.upper() if c.isalpha())[:2]
    type_prefix = "P" if type_poste == 'peage' else "S"
    
    existing_codes = Poste.objects.filter(
        code__startswith=f"{type_prefix}-{nom_code}-{region_code}"
    ).count()
    
    numero = str(existing_codes + 1).zfill(2)
    
    return f"{type_prefix}-{nom_code}-{region_code}-{numero}"


def exporter_donnees_csv(queryset, champs, nom_fichier="export"):
    """Exporte un queryset en CSV"""
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{nom_fichier}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    response.write('\ufeff')
    
    writer = csv.writer(response, delimiter=';')
    writer.writerow([field.verbose_name for field in champs])
    
    for obj in queryset:
        row = []
        for field in champs:
            value = getattr(obj, field.name, '')
            if hasattr(value, 'strftime'):
                value = value.strftime('%d/%m/%Y %H:%M') if hasattr(value, 'hour') else value.strftime('%d/%m/%Y')
            elif callable(value):
                value = value()
            row.append(str(value) if value is not None else '')
        writer.writerow(row)
    
    return response


def nettoyer_donnees_anciennes(model_class, champ_date, jours_retention):
    """Supprime les données anciennes selon une politique de rétention"""
    date_limite = timezone.now() - timedelta(days=jours_retention)
    
    filter_kwargs = {f"{champ_date}__lt": date_limite}
    objets_a_supprimer = model_class.objects.filter(**filter_kwargs)
    
    count = objets_a_supprimer.count()
    if count > 0:
        objets_a_supprimer.delete()
        logger.info(f"Nettoyage {model_class.__name__}: {count} objets supprimés")
    
    return count


def get_statistiques_utilisateur(user, jours=30):
    """Retourne des statistiques d'activité pour un utilisateur"""
    from accounts.models import JournalAudit
    
    date_debut = timezone.now() - timedelta(days=jours)
    
    actions = JournalAudit.objects.filter(
        utilisateur=user,
        timestamp__gte=date_debut
    )
    
    stats = {
        'total_actions': actions.count(),
        'actions_reussies': actions.filter(succes=True).count(),
        'actions_echouees': actions.filter(succes=False).count(),
        'derniere_action': actions.order_by('-timestamp').first(),
        'actions_par_type': {},
    }
    
    for action in actions.values('action').distinct():
        action_name = action['action']
        stats['actions_par_type'][action_name] = actions.filter(action=action_name).count()
    
    return stats


def get_resume_permissions(user):
    """Retourne un résumé lisible des permissions d'un utilisateur"""
    if not user:
        return []
    
    permissions = []
    
    if getattr(user, 'acces_tous_postes', False):
        permissions.append("Accès tous postes")
    
    categories = {
        'Inventaires': [
            ('peut_saisir_inventaire_normal', 'Saisie inventaire'),
            ('peut_programmer_inventaire', 'Programmation inventaire'),
            ('peut_voir_stats_deperdition', 'Stats déperdition'),
        ],
        'Recettes Péage': [
            ('peut_saisir_recette_peage', 'Saisie recette'),
            ('peut_voir_liste_recettes_peage', 'Consultation recettes'),
            ('peut_importer_recettes_peage', 'Import recettes'),
        ],
        'Pesage': [
            ('peut_saisir_amende', 'Saisie amende'),
            ('peut_valider_paiement_amende', 'Validation paiement'),
            ('peut_voir_stats_pesage', 'Stats pesage'),
        ],
        'Stock': [
            ('peut_charger_stock_peage', 'Chargement stock'),
            ('peut_transferer_stock_peage', 'Transfert stock'),
            ('peut_voir_tracabilite_tickets', 'Traçabilité'),
        ],
        'Gestion': [
            ('peut_gerer_utilisateurs', 'Gestion utilisateurs'),
            ('peut_gerer_postes', 'Gestion postes'),
            ('peut_voir_journal_audit', 'Journal audit'),
        ],
    }
    
    for categorie, perms in categories.items():
        perms_actives = []
        for field, label in perms:
            if getattr(user, field, False):
                perms_actives.append(label)
        
        if perms_actives:
            permissions.append({
                'categorie': categorie,
                'permissions': perms_actives
            })
    
    return permissions