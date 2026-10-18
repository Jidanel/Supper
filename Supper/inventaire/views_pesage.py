# ===================================================================
# inventaire/views_pesage.py - Vues pour le module Pesage SUPPER
# VERSION MISE À JOUR - Intégration des permissions granulaires
#
# Gestion des permissions par PERMISSION GRANULAIRE (pas par rôle):
# - peut_saisir_amende: Saisie d'amendes
# - peut_saisir_pesee_jour: Saisie des pesées journalières
# - peut_valider_paiement_amende: Validation des paiements
# - peut_saisir_quittance_pesage: Saisie de quittancements
# - peut_lister_amendes: Consultation des amendes
# - peut_voir_historique_pesees: Historique des pesées
# - peut_voir_recettes_pesage: Recettes pesage
# - peut_voir_stats_pesage: Statistiques pesage
# - peut_comptabiliser_quittances_pesage: Comptabilisation
# - peut_voir_liste_quittancements_pesage: Liste quittancements
#
# Accès aux postes:
# - Habilitations avec acces_tous_postes: peuvent sélectionner n'importe quelle station
# - Habilitations pesage (chef_station, regisseur, chef_equipe): accès à leur station uniquement
# ===================================================================

import calendar
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.core.exceptions import ValidationError
from functools import wraps
from datetime import date, datetime, time, timedelta
from django.db import transaction
from decimal import Decimal
import json
import logging
import os
import pytz

# ===================================================================
# IMPORTS DES MODULES DE PERMISSIONS ET UTILITAIRES CENTRALISÉS
# ===================================================================

from inventaire.utils_pesage import normalize_immatriculation
from common.utils import log_user_action

# Imports depuis le module de permissions centralisé
from common.permissions import (
    # Fonctions de classification utilisateur
    is_admin_user,
    is_service_central,
    is_cisop_pesage,
    is_operationnel_pesage,
    is_chef_station_pesage,
    is_regisseur_pesage,
    is_chef_equipe_pesage,

    # Fonctions d'accès aux postes
    user_has_acces_tous_postes,
    get_postes_accessibles,
    get_postes_pesage_accessibles,
    check_poste_access,
    get_poste_from_request,

    # Fonctions de vérification de permissions
    has_permission,
    has_any_permission,

    # Logging
    log_acces_refuse,

    # Constantes
    HABILITATIONS_OPERATIONNELS_PESAGE,
    PERMISSIONS_PESAGE,
)

# Imports depuis le module de décorateurs centralisé
from common.decorators import (
    permission_required_granular,
    saisie_amende_required,
    saisie_pesee_required,
    validation_paiement_amende_required,
    saisie_quittance_pesage_required,
    liste_amendes_required,
    historique_pesees_required,
    stats_pesage_required,
    comptabiliser_quittances_pesage_required,
    api_permission_required,
    operationnel_pesage_required,
)

from .models_pesage import *
from .forms_pesage import *
from accounts.models import Poste

logger = logging.getLogger('supper')


# ===================================================================
# CONSTANTES POUR LA LOGIQUE MÉTIER 9h-9h (CAMEROUN GMT+1)
# ===================================================================

CAMEROUN_TZ = pytz.timezone('Africa/Douala')
HEURE_DEBUT_JOURNEE = time(9, 0, 0)
HEURE_FIN_JOURNEE = time(8, 59, 59)


# ===================================================================
# FONCTIONS UTILITAIRES D'ACCÈS AUX POSTES (PESAGE)
# ===================================================================

def get_user_station_pesage(user):
    """
    Retourne la station de pesage de l'utilisateur.

    Returns:
        - None si l'utilisateur a accès à tous les postes (admin, services centraux, cisop_pesage)
        - Instance de Poste si utilisateur affecté à une station pesage
        - False si utilisateur non autorisé pour le pesage

    Utilise les permissions granulaires pour déterminer l'accès.
    """
    if not user or not user.is_authenticated:
        return False

    # Vérifier si l'utilisateur a accès à tous les postes (multi-postes)
    if user_has_acces_tous_postes(user):
        logger.debug(f"[PESAGE] Utilisateur {user.username} a accès à toutes les stations (multi-postes)")
        return None

    # Vérifier si l'utilisateur a au moins une permission pesage
    if not has_any_permission(user, PERMISSIONS_PESAGE):
        logger.warning(f"[PESAGE] Accès refusé: {user.username} n'a aucune permission pesage")
        return False

    # Vérifier le poste d'affectation
    poste = getattr(user, 'poste_affectation', None)
    if poste and poste.type == 'pesage' and poste.is_active:
        logger.debug(f"[PESAGE] Utilisateur {user.username} affecté à la station {poste.nom}")
        return poste

    logger.warning(f"[PESAGE] Utilisateur {user.username} sans station de pesage valide")
    return False


def get_stations_pesage_accessibles(user):
    """
    Retourne le queryset des stations de pesage accessibles pour l'utilisateur.
    Utilise la fonction centralisée get_postes_accessibles avec filtre type='pesage'.
    """
    return get_postes_accessibles(user, type_poste='pesage')


def get_station_context(request, user):
    """
    Récupère la station pour le contexte de la vue.

    Logic:
    1. Si l'utilisateur n'a PAS accès à tous les postes → utiliser son poste d'affectation
    2. Si l'utilisateur A accès à tous les postes → permettre la sélection via GET/POST/session

    Returns:
        tuple (station, redirect_response)
        - (station, None) si station trouvée
        - (None, redirect) si redirection nécessaire
        - (None, None) si admin sans station sélectionnée
    """
    # Cas 1: Utilisateur avec accès limité à son poste
    if not user_has_acces_tous_postes(user):
        station = get_user_station_pesage(user)

        if station is False:
            logger.warning(f"[PESAGE] {user.username} tente d'accéder sans permission pesage")
            log_user_action(
                user,
                "Accès pesage refusé",
                f"Tentative d'accès au module pesage sans permission - Habilitation: {user.habilitation}",
                request
            )
            messages.error(request, _("Vous devez être affecté à une station de pesage pour accéder à cette fonctionnalité."))
            return None, redirect('common:dashboard')

        if station is None:
            logger.error(f"[PESAGE] Incohérence: {user.username} n'a pas accès tous postes mais station=None")
            messages.error(request, _("Erreur de configuration. Contactez un administrateur."))
            return None, redirect('common:dashboard')

        logger.debug(f"[PESAGE] Station {station.nom} assignée à {user.username}")
        return station, None

    # Cas 2: Utilisateur avec accès à tous les postes (admin, service central, cisop_pesage)
    station_id = (
        request.GET.get('station') or
        request.POST.get('station') or
        request.session.get('station_pesage_id')
    )

    if station_id:
        try:
            station = Poste.objects.get(pk=station_id, type='pesage', is_active=True)
            request.session['station_pesage_id'] = station.id
            logger.debug(f"[PESAGE] Admin {user.username} a sélectionné la station {station.nom}")
            return station, None
        except Poste.DoesNotExist:
            request.session.pop('station_pesage_id', None)
            logger.warning(f"[PESAGE] Station ID {station_id} invalide pour {user.username}")

    # Admin sans station sélectionnée
    return None, None


def valider_date_saisie(date_cible):
    """Valide qu'une date n'est pas dans le futur."""
    today = timezone.now().date()
    if date_cible > today:
        return False, _("Impossible de saisir des données pour une date future.")
    return True, None


# ===================================================================
# FONCTIONS UTILITAIRES TEMPORELLES (LOGIQUE 9h-9h)
# ===================================================================

def get_datetime_cameroun():
    """Retourne la date/heure actuelle au Cameroun (GMT+1)."""
    return timezone.now().astimezone(CAMEROUN_TZ)


def get_jour_travail_actuel():
    """Détermine le jour de travail actuel selon la logique 9h-9h."""
    maintenant = get_datetime_cameroun()
    if maintenant.time() < HEURE_DEBUT_JOURNEE:
        return (maintenant - timedelta(days=1)).date()
    else:
        return maintenant.date()


def calculer_periode_9h(periode_type, date_debut_custom=None, date_fin_custom=None):
    """Calcule les datetime de début et fin pour une période donnée avec logique 9h-9h."""
    jour_travail = get_jour_travail_actuel()

    if periode_type == 'personnalise' and date_debut_custom and date_fin_custom:
        if isinstance(date_debut_custom, str):
            try:
                date_debut = datetime.strptime(date_debut_custom, '%Y-%m-%d').date()
            except ValueError:
                date_debut = jour_travail.replace(day=1)
        else:
            date_debut = date_debut_custom

        if isinstance(date_fin_custom, str):
            try:
                date_fin = datetime.strptime(date_fin_custom, '%Y-%m-%d').date()
            except ValueError:
                date_fin = jour_travail
        else:
            date_fin = date_fin_custom

        datetime_debut = CAMEROUN_TZ.localize(datetime.combine(date_debut, HEURE_DEBUT_JOURNEE))
        datetime_fin = CAMEROUN_TZ.localize(datetime.combine(date_fin + timedelta(days=1), HEURE_FIN_JOURNEE))
        label = f"Du {date_debut.strftime('%d/%m/%Y')} 9h au {date_fin.strftime('%d/%m/%Y')} 9h"

        return {'datetime_debut': datetime_debut, 'datetime_fin': datetime_fin,
                'date_debut': date_debut, 'date_fin': date_fin, 'label': label}

    if periode_type == 'jour':
        date_debut = jour_travail
        date_fin = jour_travail
        datetime_debut = CAMEROUN_TZ.localize(datetime.combine(jour_travail, HEURE_DEBUT_JOURNEE))
        datetime_fin = CAMEROUN_TZ.localize(datetime.combine(jour_travail + timedelta(days=1), HEURE_FIN_JOURNEE))
        label = f"Aujourd'hui ({jour_travail.strftime('%d/%m/%Y')}) de 9h à demain 9h"

    elif periode_type == 'semaine':
        date_debut = jour_travail - timedelta(days=6)
        date_fin = jour_travail
        datetime_debut = CAMEROUN_TZ.localize(datetime.combine(date_debut, HEURE_DEBUT_JOURNEE))
        datetime_fin = CAMEROUN_TZ.localize(datetime.combine(jour_travail + timedelta(days=1), HEURE_FIN_JOURNEE))
        label = f"7 derniers jours ({date_debut.strftime('%d/%m')} - {date_fin.strftime('%d/%m/%Y')})"

    elif periode_type == 'mois':
        date_debut = jour_travail.replace(day=1)
        date_fin = jour_travail
        datetime_debut = CAMEROUN_TZ.localize(datetime.combine(date_debut, HEURE_DEBUT_JOURNEE))
        datetime_fin = CAMEROUN_TZ.localize(datetime.combine(jour_travail + timedelta(days=1), HEURE_FIN_JOURNEE))
        label = f"Mois en cours ({date_debut.strftime('%d/%m')} - {date_fin.strftime('%d/%m/%Y')})"

    elif periode_type == 'trimestre':
        trimestre = (jour_travail.month - 1) // 3
        mois_debut = trimestre * 3 + 1
        date_debut = jour_travail.replace(month=mois_debut, day=1)
        date_fin = jour_travail
        datetime_debut = CAMEROUN_TZ.localize(datetime.combine(date_debut, HEURE_DEBUT_JOURNEE))
        datetime_fin = CAMEROUN_TZ.localize(datetime.combine(jour_travail + timedelta(days=1), HEURE_FIN_JOURNEE))
        label = f"Trimestre {trimestre + 1} ({date_debut.strftime('%d/%m')} - {date_fin.strftime('%d/%m/%Y')})"

    elif periode_type == 'annee':
        date_debut = jour_travail.replace(month=1, day=1)
        date_fin = jour_travail
        datetime_debut = CAMEROUN_TZ.localize(datetime.combine(date_debut, HEURE_DEBUT_JOURNEE))
        datetime_fin = CAMEROUN_TZ.localize(datetime.combine(jour_travail + timedelta(days=1), HEURE_FIN_JOURNEE))
        label = f"Année {jour_travail.year} ({date_debut.strftime('%d/%m')} - {date_fin.strftime('%d/%m/%Y')})"

    else:
        return calculer_periode_9h('mois')

    return {'datetime_debut': datetime_debut, 'datetime_fin': datetime_fin,
            'date_debut': date_debut, 'date_fin': date_fin, 'label': label}


def get_periode_dates(periode, date_ref=None):
    """Calcule les dates de début et fin pour une période donnée."""
    if date_ref is None:
        date_ref = timezone.now().date()

    if periode == 'jour':
        return date_ref, date_ref
    elif periode == 'semaine':
        date_debut = date_ref - timedelta(days=date_ref.weekday())
        date_fin = date_debut + timedelta(days=6)
        return date_debut, date_fin
    elif periode == 'mois':
        date_debut = date_ref.replace(day=1)
        if date_ref.month == 12:
            date_fin = date_ref.replace(day=31)
        else:
            date_fin = date_ref.replace(month=date_ref.month + 1, day=1) - timedelta(days=1)
        return date_debut, date_fin
    elif periode == 'trimestre':
        trimestre = (date_ref.month - 1) // 3
        date_debut = date_ref.replace(month=trimestre * 3 + 1, day=1)
        if trimestre == 3:
            date_fin = date_ref.replace(month=12, day=31)
        else:
            date_fin = date_ref.replace(month=(trimestre + 1) * 3 + 1, day=1) - timedelta(days=1)
        return date_debut, date_fin
    elif periode == 'annee':
        date_debut = date_ref.replace(month=1, day=1)
        date_fin = date_ref.replace(month=12, day=31)
        return date_debut, date_fin

    return get_periode_dates('mois', date_ref)


# ===================================================================
# DÉCORATEURS SPÉCIFIQUES PESAGE (AVEC GESTION DES POSTES)
# ===================================================================

def pesage_access_required(view_func):
    """
    Vérifie que l'utilisateur a accès au module pesage.
    Utilise la permission granulaire 'peut_lister_amendes' comme permission de base.
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user

        # Vérifier si l'utilisateur a au moins une permission pesage
        if not has_any_permission(user, PERMISSIONS_PESAGE):
            log_user_action(
                user,
                "Accès module pesage refusé",
                f"Aucune permission pesage - Vue: {view_func.__name__}",
                request
            )
            log_acces_refuse(user, view_func.__name__, "Aucune permission pesage")
            messages.error(request, _("Accès non autorisé au module pesage."))
            return redirect('common:dashboard')

        # Vérifier l'accès à une station (sauf si accès tous postes)
        if not user_has_acces_tous_postes(user):
            station = get_user_station_pesage(user)
            if station is False:
                log_user_action(
                    user,
                    "Accès pesage - station manquante",
                    f"Permission pesage OK mais pas de station affectée",
                    request
                )
                messages.error(request, _("Vous devez être affecté à une station de pesage."))
                return redirect('common:dashboard')

        return view_func(request, *args, **kwargs)
    return wrapper


def saisie_pesage_required(view_func):
    """
    Vérifie que l'utilisateur peut saisir des données pesage (amendes ou pesées).
    Permissions: peut_saisir_amende OU peut_saisir_pesee_jour
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not has_any_permission(user, ['peut_saisir_amende', 'peut_saisir_pesee_jour']):
            log_user_action(
                user,
                "Saisie pesage refusée",
                f"Permissions manquantes: peut_saisir_amende, peut_saisir_pesee_jour",
                request
            )
            log_acces_refuse(user, view_func.__name__, "Permission saisie pesage manquante")
            messages.error(request, _("Accès réservé aux chefs d'équipe et chefs de station pesage."))
            return redirect('common:dashboard')

        # Vérifier l'accès à une station
        if not user_has_acces_tous_postes(user):
            station = get_user_station_pesage(user)
            if station is False:
                messages.error(request, _("Vous devez être affecté à une station de pesage."))
                return redirect('common:dashboard')

        return view_func(request, *args, **kwargs)
    return wrapper


def validation_pesage_required(view_func):
    """
    Vérifie que l'utilisateur peut valider des paiements d'amendes.
    Permission: peut_valider_paiement_amende
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not has_permission(user, 'peut_valider_paiement_amende'):
            log_user_action(
                user,
                "Validation paiement refusée",
                f"Permission manquante: peut_valider_paiement_amende",
                request
            )
            log_acces_refuse(user, view_func.__name__, "Permission validation paiement manquante")
            messages.error(request, _("Accès réservé aux régisseurs de station pesage."))
            return redirect('common:dashboard')

        # Vérifier l'accès à une station
        if not user_has_acces_tous_postes(user):
            station = get_user_station_pesage(user)
            if station is False:
                messages.error(request, _("Vous devez être affecté à une station de pesage."))
                return redirect('common:dashboard')

        return view_func(request, *args, **kwargs)
    return wrapper


def quittancement_pesage_required(view_func):
    """
    Vérifie que l'utilisateur peut gérer les quittancements pesage.
    Permission: peut_saisir_quittance_pesage
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not has_permission(user, 'peut_saisir_quittance_pesage'):
            log_user_action(
                user,
                "Quittancement pesage refusé",
                f"Permission manquante: peut_saisir_quittance_pesage",
                request
            )
            log_acces_refuse(user, view_func.__name__, "Permission quittancement pesage manquante")
            messages.error(request, _("Accès réservé aux régisseurs pesage."))
            return redirect('common:dashboard')

        return view_func(request, *args, **kwargs)
    return wrapper


# ===================================================================
# SÉLECTION DE STATION (UTILISATEURS MULTI-POSTES UNIQUEMENT)
# ===================================================================

@login_required
def selectionner_station(request):
    """
    Page intermédiaire pour que les utilisateurs multi-postes sélectionnent une station.
    Accessible uniquement si l'utilisateur a accès à tous les postes.
    """
    user = request.user

    # Vérifier si l'utilisateur a réellement accès à tous les postes
    if not user_has_acces_tous_postes(user):
        log_user_action(
            user,
            "Sélection station - non autorisé",
            f"Utilisateur sans accès tous postes tente de sélectionner une station",
            request
        )
        messages.info(request, _("Vous êtes automatiquement affecté à votre station."))
        return redirect('common:dashboard')

    action = request.GET.get('action', request.POST.get('action', 'liste_amendes'))

    action_urls = {
        'saisir_amende': 'inventaire:saisir_amende',
        'saisir_pesees': 'inventaire:saisir_pesees',
        'importer_amendes': 'inventaire:importer_amendes',
        'saisie_quittancement_pesage': 'inventaire:saisie_quittancement_pesage',
        'liste_amendes': 'inventaire:liste_amendes',
        'amendes_a_valider': 'inventaire:liste_amendes_a_valider',
        'historique_pesees': 'inventaire:historique_pesees',
        'liste_quittancements_pesage': 'inventaire:liste_quittancements_pesage',
        'comptabilisation_quittancements_pesage': 'inventaire:comptabilisation_quittancements_pesage',
        'statistiques_pesage': 'inventaire:statistiques_pesage',
        'recettes_pesage': 'inventaire:recettes_pesage',
    }

    if request.method == 'POST':
        station_id = request.POST.get('station')
        if not station_id:
            messages.error(request, _("Veuillez sélectionner une station."))
        else:
            try:
                station = Poste.objects.get(pk=station_id, type='pesage', is_active=True)
                request.session['station_pesage_id'] = station.id

                log_user_action(
                    user,
                    "Station pesage sélectionnée",
                    f"Station: {station.nom} (ID: {station.id}) - Action: {action}",
                    request
                )

                url_name = action_urls.get(action, 'inventaire:liste_amendes')
                return redirect(f"{reverse(url_name)}?station={station.id}")
            except Poste.DoesNotExist:
                messages.error(request, _("Station invalide."))

    stations = Poste.objects.filter(type='pesage', is_active=True).order_by('region', 'nom')

    context = {
        'stations': stations,
        'action': action,
        'title': _('Sélectionner une station de pesage'),
        'is_admin': is_admin_user(user),
    }

    return render(request, 'pesage/selectionner_station.html', context)


# ===================================================================
# GESTION DES AMENDES - SAISIE
# Permission requise: peut_saisir_amende
# ===================================================================

@saisie_pesage_required
def saisir_amende(request):
    """
    Saisie d'une nouvelle amende.
    Permission: peut_saisir_amende
    """
    user = request.user
    today = timezone.now().date()

    # Vérifier la permission spécifique pour saisir une amende
    if not has_permission(user, 'peut_saisir_amende'):
        log_user_action(
            user,
            "Saisie amende - permission refusée",
            f"Permission peut_saisir_amende manquante",
            request
        )
        messages.error(request, _("Vous n'avez pas la permission de saisir des amendes."))
        return redirect('inventaire:liste_amendes')

    station, redirect_response = get_station_context(request, user)

    # Si utilisateur multi-postes sans station sélectionnée → rediriger vers sélection
    if user_has_acces_tous_postes(user) and station is None:
        return redirect(f"{reverse('inventaire:selectionner_station')}?action=saisir_amende")

    if redirect_response:
        return redirect_response

    if request.method == 'POST':
        form = AmendeEmiseForm(request.POST)

        # Validation de la date
        date_heure_emission_str = request.POST.get('date_heure_emission')
        if date_heure_emission_str:
            try:
                date_heure_emission = datetime.strptime(date_heure_emission_str, '%Y-%m-%d').date()
                is_valid, error_msg = valider_date_saisie(date_heure_emission)
                if not is_valid:
                    messages.error(request, error_msg)
                    return render(request, 'pesage/saisir_amende.html', {
                        'form': form,
                        'station': station,
                        'is_admin': is_admin_user(user),
                        'today': today,
                        'title': _('Saisir une amende'),
                    })
            except ValueError:
                pass

        if form.is_valid():
            amende = form.save(commit=False)
            amende.station = station
            amende.saisi_par = user
            amende.statut = 'non_paye'
            amende.date_heure_emission = timezone.now()
            amende.save()

            messages.success(
                request,
                _("Amende %(numero)s créée avec succès. Montant: %(montant)s FCFA") % {
                    'numero': amende.numero_ticket,
                    'montant': f"{amende.montant_amende:,.0f}".replace(',', ' ')
                }
            )

            # Log détaillé de l'action
            log_user_action(
                user,
                "Saisie amende pesage",
                f"N°Ticket: {amende.numero_ticket} | Montant: {amende.montant_amende} FCFA | "
                f"Immatriculation: {amende.immatriculation} | Station: {station.nom} | "
                f"Surcharge: {amende.est_surcharge} | Hors gabarit: {amende.est_hors_gabarit} | "
                f"Délit de fuite: {amende.est_delit_fuite}",
                request
            )

            if 'saisir_autre' in request.POST:
                return redirect(f"{reverse('inventaire:saisir_amende')}?station={station.pk}")
            return redirect('inventaire:liste_amendes')
    else:
        form = AmendeEmiseForm()

    context = {
        'form': form,
        'station': station,
        'is_admin': is_admin_user(user),
        'today': today,
        'title': _('Saisir une amende'),
        'peut_saisir_amende': has_permission(user, 'peut_saisir_amende'),
    }
    return render(request, 'pesage/saisir_amende.html', context)


# ===================================================================
# LISTE DES AMENDES
# Permission requise: peut_lister_amendes
# ===================================================================

@pesage_access_required
def liste_amendes(request):
    """
    Liste des amendes avec filtres de recherche.
    Permission: peut_lister_amendes
    """
    user = request.user
    stations_accessibles = get_stations_pesage_accessibles(user)

    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response

    # Construction du queryset selon les droits
    if station is None and user_has_acces_tous_postes(user):
        # Utilisateur multi-postes sans station sélectionnée → toutes les amendes
        queryset = AmendeEmise.objects.all()
        station_filter = request.GET.get('station_filter')
        if station_filter:
            queryset = queryset.filter(station_id=station_filter)
            logger.debug(f"[PESAGE] {user.username} filtre les amendes par station ID {station_filter}")
    elif station:
        # Utilisateur avec station spécifique
        queryset = AmendeEmise.objects.filter(station=station)
    else:
        queryset = AmendeEmise.objects.none()

    # Filtres de recherche
    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(
            Q(numero_ticket__icontains=query) |
            Q(immatriculation__icontains=query) |
            Q(transporteur__icontains=query) |
            Q(provenance__icontains=query) |
            Q(destination__icontains=query)
        )

    statut_filter = request.GET.get('statut')
    if statut_filter:
        queryset = queryset.filter(statut=statut_filter)

    infraction_filter = request.GET.get('type_infraction')
    if infraction_filter == 'S':
        queryset = queryset.filter(est_surcharge=True, est_hors_gabarit=False, est_delit_fuite=False)
    elif infraction_filter == 'HG':
        queryset = queryset.filter(est_hors_gabarit=True, est_surcharge=False, est_delit_fuite=False)
    elif infraction_filter == 'DF':
        queryset = queryset.filter(est_delit_fuite=True, est_surcharge=False, est_hors_gabarit=False)
    elif infraction_filter == 'S+HG':
        queryset = queryset.filter(est_surcharge=True, est_hors_gabarit=True, est_delit_fuite=False)
    elif infraction_filter == 'HG+DF':
        queryset = queryset.filter(est_hors_gabarit=True, est_delit_fuite=True, est_surcharge=False)
    elif infraction_filter == 'S+DF':
        queryset = queryset.filter(est_surcharge=True, est_delit_fuite=True, est_hors_gabarit=False)
    elif infraction_filter == 'S+HG+DF':
        queryset = queryset.filter(est_surcharge=True, est_hors_gabarit=True, est_delit_fuite=True)
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    if date_debut:
        queryset = queryset.filter(date_heure_emission__date__gte=date_debut)
    if date_fin:
        queryset = queryset.filter(date_heure_emission__date__lte=date_fin)

    queryset = queryset.select_related('station', 'saisi_par').order_by('-date_heure_emission')

    # Statistiques
    stats = queryset.aggregate(
        total_montant=Sum('montant_amende'),
        total_paye=Sum('montant_amende', filter=Q(statut='paye')),
        total_non_paye=Sum('montant_amende', filter=Q(statut='non_paye')),
        count_total=Count('id'),
        count_paye=Count('id', filter=Q(statut='paye')),
        count_non_paye=Count('id', filter=Q(statut='non_paye')),
    )

    # Pagination
    paginator = Paginator(queryset, 25)
    page = request.GET.get('page')
    amendes = paginator.get_page(page)

    context = {
        'amendes': amendes,
        'station': station,
        'stations_accessibles': stations_accessibles,
        'stats': stats,
        'is_admin': is_admin_user(user),
        'query': query,
        'statut_filter': statut_filter,
        'type_infraction': infraction_filter,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'station_filter': request.GET.get('station_filter', ''),
        'title': _('Liste des amendes'),
        'peut_valider_paiement': has_permission(user, 'peut_valider_paiement_amende'),
        'peut_saisir_amende': has_permission(user, 'peut_saisir_amende'),
    }
    return render(request, 'pesage/liste_amendes.html', context)


@pesage_access_required
def detail_amende(request, pk):
    """
    Détail d'une amende.
    AMÉLIORATION: Détecte si le véhicule a des amendes non payées
    dans d'autres stations et affiche un avertissement.
    """
    user = request.user
    station, _unused = get_station_context(request, user)

    # Récupérer l'amende selon les droits
    if user_has_acces_tous_postes(user):
        amende = get_object_or_404(AmendeEmise, pk=pk)
    else:
        amende = get_object_or_404(AmendeEmise, pk=pk, station=station)

    # Récupérer les événements si disponibles
    events = []
    if hasattr(amende, 'events'):
        events = amende.events.select_related('effectue_par').order_by('-event_datetime')

    # =====================================================================
    # NOUVEAU: Détecter les amendes non payées du véhicule
    # =====================================================================
    from .utils_pesage import normalize_immatriculation

    immat_norm = normalize_immatriculation(amende.immatriculation)

    # Toutes les amendes non payées de ce véhicule (sauf celle-ci)
    amendes_non_payees = AmendeEmise.objects.filter(
        Q(immatriculation_normalise__iexact=immat_norm) |
        Q(immatriculation__iexact=amende.immatriculation) |
        Q(immatriculation__iexact=immat_norm),
        statut='non_paye'
    ).exclude(pk=amende.pk).select_related('station')

    # Séparer par station
    amendes_autres_stations = amendes_non_payees.exclude(station=amende.station)
    amendes_meme_station = amendes_non_payees.filter(station=amende.station)

    # Infos pour l'affichage
    infos_autres_amendes = None
    if amendes_non_payees.exists():
        infos_autres_amendes = {
            'total': amendes_non_payees.count(),
            'autres_stations': {
                'count': amendes_autres_stations.count(),
                'montant': amendes_autres_stations.aggregate(total=Sum('montant_amende'))['total'] or 0,
                'stations': list(amendes_autres_stations.values_list('station__nom', flat=True).distinct()),
            },
            'meme_station': {
                'count': amendes_meme_station.count(),
                'montant': amendes_meme_station.aggregate(total=Sum('montant_amende'))['total'] or 0,
            },
            'montant_total': amendes_non_payees.aggregate(total=Sum('montant_amende'))['total'] or 0,
        }

    # =====================================================================
    # FIN NOUVEAU CODE
    # =====================================================================

    log_user_action(
        user,
        "Consultation détail amende",
        f"Amende {amende.numero_ticket} - Station: {amende.station.nom}",
        request
    )

    context = {
        'amende': amende,
        'events': events,
        'station': station or amende.station,
        'is_admin': is_admin_user(user),
        'title': f"Amende {amende.numero_ticket}",
        'peut_valider_paiement': has_permission(user, 'peut_valider_paiement_amende'),
        # Nouvelles variables
        'infos_autres_amendes': infos_autres_amendes,
        'has_autres_amendes': infos_autres_amendes is not None,
    }
    return render(request, 'pesage/detail_amende.html', context)

# ===================================================================
# VALIDATION DES PAIEMENTS
# Permission requise: peut_valider_paiement_amende
# ===================================================================

@validation_pesage_required
def liste_amendes_a_valider(request):
    """
    Liste des amendes en attente de validation.
    Permission: peut_valider_paiement_amende

    AMÉLIORATION: Détecte pour chaque amende si le véhicule a des amendes
    non payées dans d'autres stations et prépare les infos pour l'affichage.
    """
    user = request.user
    stations_accessibles = get_stations_pesage_accessibles(user)
    peut_valider = has_permission(user, 'peut_valider_paiement_amende')

    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response

    # Construction du queryset
    if station is None and user_has_acces_tous_postes(user):
        queryset = AmendeEmise.objects.filter(statut='non_paye')
        station_filter = request.GET.get('station_filter')
        if station_filter:
            queryset = queryset.filter(station_id=station_filter)
    elif station:
        queryset = AmendeEmise.objects.filter(station=station, statut='non_paye')
    else:
        queryset = AmendeEmise.objects.none()

    queryset = queryset.select_related('station', 'saisi_par').order_by('-date_heure_emission')
    total_a_recouvrer = queryset.aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')

    # =====================================================================
    # NOUVEAU: Détecter les véhicules avec amendes dans autres stations
    # =====================================================================

    # Récupérer toutes les immatriculations de la page actuelle
    paginator = Paginator(queryset, 25)
    page = request.GET.get('page')
    amendes_page = paginator.get_page(page)

    # Collecter les immatriculations uniques de cette page
    immatriculations_page = set()
    for amende in amendes_page:
        immat_norm = normalize_immatriculation(amende.immatriculation)
        immatriculations_page.add(immat_norm)
        immatriculations_page.add(amende.immatriculation)

    # Rechercher TOUTES les amendes non payées pour ces véhicules
    # (incluant celles dans d'autres stations)
    if immatriculations_page:
        amendes_autres_stations = AmendeEmise.objects.filter(
            Q(immatriculation__in=immatriculations_page) |
            Q(immatriculation_normalise__in=immatriculations_page),
            statut='non_paye'
        ).exclude(
            station=station  # Exclure la station actuelle
        ).values(
            'immatriculation',
            'immatriculation_normalise',
            'station__nom',
            'station__id'
        ).annotate(
            nb_amendes=Count('pk'),
            montant_total=Sum('montant_amende')
        )

        # Construire un dictionnaire: immatriculation -> infos autres stations
        # Clé: immatriculation normalisée
        vehicules_avec_autres_amendes = {}

        for item in amendes_autres_stations:
            immat_norm = normalize_immatriculation(item['immatriculation'])

            if immat_norm not in vehicules_avec_autres_amendes:
                vehicules_avec_autres_amendes[immat_norm] = {
                    'stations': [],
                    'total_amendes': 0,
                    'montant_total': Decimal('0'),
                }

            # Ajouter cette station si pas déjà présente
            station_info = {
                'nom': item['station__nom'],
                'id': item['station__id'],
                'nb': item['nb_amendes'],
                'montant': item['montant_total'] or Decimal('0'),
            }

            # Éviter les doublons de station
            stations_existantes = [s['id'] for s in vehicules_avec_autres_amendes[immat_norm]['stations']]
            if item['station__id'] not in stations_existantes:
                vehicules_avec_autres_amendes[immat_norm]['stations'].append(station_info)
                vehicules_avec_autres_amendes[immat_norm]['total_amendes'] += item['nb_amendes']
                vehicules_avec_autres_amendes[immat_norm]['montant_total'] += (item['montant_total'] or Decimal('0'))
    else:
        vehicules_avec_autres_amendes = {}

    # Enrichir chaque amende avec les infos des autres stations
    amendes_enrichies = []
    for amende in amendes_page:
        immat_norm = normalize_immatriculation(amende.immatriculation)

        # Vérifier si ce véhicule a des amendes ailleurs
        infos_autres = vehicules_avec_autres_amendes.get(immat_norm)

        amendes_enrichies.append({
            'amende': amende,
            'has_autres_stations': infos_autres is not None,
            'autres_stations_info': infos_autres,
        })

    # =====================================================================
    # FIN NOUVEAU CODE
    # =====================================================================

    context = {
        'amendes': amendes_page,  # Pour la pagination
        'amendes_enrichies': amendes_enrichies,  # Avec les infos supplémentaires
        'vehicules_avec_autres_amendes': vehicules_avec_autres_amendes,  # Dictionnaire complet
        'station': station,
        'stations_accessibles': stations_accessibles,
        'total_a_recouvrer': total_a_recouvrer,
        'count_total': queryset.count(),
        'is_admin': is_admin_user(user),
        'peut_valider': peut_valider,
        'station_filter': request.GET.get('station_filter', ''),
        'title': _('Amendes à valider'),
    }
    return render(request, 'pesage/liste_amendes_a_valider.html', context)


# ===================================================================
# API pour récupérer les détails des amendes d'un véhicule (AJAX)
# ===================================================================

from django.http import JsonResponse
from django.views.decorators.http import require_GET

@validation_pesage_required
@require_GET
def api_amendes_vehicule_autres_stations(request, immatriculation):
    """
    API JSON qui retourne les amendes non payées d'un véhicule dans d'autres stations.
    Utilisé pour le modal de détails.
    """
    user = request.user
    station, _ = get_station_context(request, user)

    immat_norm = normalize_immatriculation(immatriculation)

    # Rechercher les amendes non payées dans AUTRES stations
    amendes = AmendeEmise.objects.filter(
        Q(immatriculation__iexact=immatriculation) |
        Q(immatriculation__iexact=immat_norm) |
        Q(immatriculation_normalise__iexact=immat_norm),
        statut='non_paye'
    ).exclude(
        station=station
    ).select_related('station').order_by('date_heure_emission')

    # Préparer les données JSON
    data = {
        'immatriculation': immatriculation,
        'count': amendes.count(),
        'montant_total': float(amendes.aggregate(total=Sum('montant_amende'))['total'] or 0),
        'amendes': []
    }

    for amende in amendes:
        data['amendes'].append({
            'id': amende.pk,
            'numero_ticket': amende.numero_ticket,
            'station': amende.station.nom,
            'station_id': amende.station.id,
            'date_emission': amende.date_heure_emission.strftime('%d/%m/%Y %H:%i'),
            'montant': float(amende.montant_amende),
            'transporteur': amende.transporteur or '-',
            'infraction': 'S+HG' if (amende.est_surcharge and amende.est_hors_gabarit) else ('S' if amende.est_surcharge else ('HG' if amende.est_hors_gabarit else '-')),
        })

    return JsonResponse(data)


@validation_pesage_required
@require_POST
def valider_paiement(request, pk):
    """
    Valide le paiement d'une amende.
    Permission: peut_valider_paiement_amende

    COMPORTEMENT:
    1. Vérifier si le véhicule a des amendes NON PAYÉES plus anciennes dans d'AUTRES stations
    2. Si oui → AVERTIR l'utilisateur mais VALIDER quand même le paiement
    3. Les amendes antérieures restent non payées et visibles dans la liste

    LOGIQUE MODIFICATION ADMIN:
    ===========================
    Si l'amende a été modifiée par un admin après une validation initiale:
    - Le champ date_paiement_originale contient la date du premier paiement
    - Lors de la revalidation, on utilise cette date pour comptabiliser la recette
    - Cela garantit que la recette apparaît à la date originale, pas à la date de revalidation

    Exemple:
    - 14/02: Amende émise et payée → date_paiement = 14/02
    - 20/02: Admin modifie → statut='non_paye', date_paiement_originale=14/02
    - 21/02: Revalidation → date_paiement = 14/02 (date originale utilisée)
    - Résultat: Recette comptabilisée au 14/02
    """
    user = request.user

    # Double vérification de la permission
    if not has_permission(user, 'peut_valider_paiement_amende'):
        log_user_action(
            user,
            "Validation paiement - permission refusée",
            f"Tentative de validation sans permission pour amende ID {pk}",
            request
        )
        messages.error(request, _("Vous n'avez pas la permission de valider les paiements."))
        return redirect('inventaire:liste_amendes_a_valider')

    station, _unused = get_station_context(request, user)

    # Récupérer l'amende selon les droits
    if user_has_acces_tous_postes(user):
        amende = get_object_or_404(AmendeEmise, pk=pk)
    else:
        amende = get_object_or_404(AmendeEmise, pk=pk, station=station)

    # Vérification 1: L'amende est-elle déjà payée ?
    if amende.statut == 'paye':
        messages.warning(request, _("Cette amende a déjà été validée."))
        return redirect('inventaire:liste_amendes_a_valider')

    # Vérification 2: Y a-t-il des amendes NON PAYÉES plus anciennes ailleurs ?
    # (Pour avertissement uniquement, pas de blocage)
    immat_norm = normalize_immatriculation(amende.immatriculation)

    amendes_anterieures_non_payees = AmendeEmise.objects.filter(
        Q(immatriculation_normalise__iexact=immat_norm) |
        Q(immatriculation__iexact=amende.immatriculation) |
        Q(immatriculation__iexact=immat_norm),
        statut='non_paye',
        date_heure_emission__lt=amende.date_heure_emission
    ).exclude(
        pk=amende.pk
    ).select_related('station').order_by('date_heure_emission')

    # Préparer l'avertissement si amendes antérieures
    avertissement_amendes = None
    if amendes_anterieures_non_payees.exists():
        # Séparer les amendes de la même station et des autres stations
        amendes_meme_station = amendes_anterieures_non_payees.filter(station=amende.station)
        amendes_autres_stations = amendes_anterieures_non_payees.exclude(station=amende.station)

        avertissement_amendes = {
            'total': amendes_anterieures_non_payees.count(),
            'meme_station': amendes_meme_station.count(),
            'autres_stations': amendes_autres_stations.count(),
            'stations': list(amendes_autres_stations.values_list('station__nom', flat=True).distinct()),
            'montant_total': amendes_anterieures_non_payees.aggregate(total=Sum('montant_amende'))['total'] or 0,
        }

    # VALIDER LE PAIEMENT (même s'il y a des amendes antérieures)
    try:
        amende.statut = 'paye'

        # ===============================================================
        # LOGIQUE CRITIQUE: Date de paiement pour revalidation
        # ===============================================================
        # Si l'amende a été modifiée par un admin après une validation initiale,
        # la date_paiement_originale contient la date du premier paiement.
        # On utilise cette date pour que la recette soit comptabilisée à la
        # date du paiement initial, pas à la date de revalidation.

        est_revalidation = False

        if amende.date_paiement_originale:
            # ============================================
            # CAS: REVALIDATION APRÈS MODIFICATION ADMIN
            # ============================================
            # L'amende avait été payée, puis modifiée par un admin
            # La date_paiement_originale contient la date du premier paiement
            # On utilise cette date pour la comptabilisation de la recette

            est_revalidation = True
            amende.date_paiement = amende.date_paiement_originale

            # Log spécifique pour la revalidation
            log_user_action(
                user,
                "Revalidation paiement amende (après modification admin)",
                f"N°Ticket: {amende.numero_ticket} | Montant: {amende.montant_amende} FCFA | "
                f"Véhicule: {amende.immatriculation} | Station: {amende.station.nom} | "
                f"Date paiement originale utilisée: {amende.date_paiement_originale.strftime('%d/%m/%Y %H:%M')} | "
                f"Ancien statut avant modification: {amende.ancien_statut_avant_modification or 'N/A'} | "
                f"Ancien montant validé: {amende.ancien_montant_valide or 'N/A'} FCFA | "
                f"Modifié par: {amende.modifie_par.get_full_name() if amende.modifie_par else 'N/A'} | "
                f"Date modification: {amende.date_derniere_modification.strftime('%d/%m/%Y %H:%M') if amende.date_derniere_modification else 'N/A'}",
                request
            )

            # Message informatif pour l'utilisateur
            messages.info(request,
                _("ℹ️ Cette amende avait été modifiée par un administrateur. "
                  "La recette de %(montant)s FCFA est comptabilisée à la date originale du %(date)s.") % {
                    'montant': f"{amende.montant_amende:,.0f}".replace(',', ' '),
                    'date': amende.date_paiement_originale.strftime('%d/%m/%Y')
                })

            logger.info(
                f"Revalidation amende {amende.numero_ticket}: "
                f"Date paiement originale {amende.date_paiement_originale} utilisée "
                f"(modification admin le {amende.date_derniere_modification})"
            )
        else:
            # ============================================
            # CAS: PREMIÈRE VALIDATION (NORMALE)
            # ============================================
            # Pas de date_paiement_originale → première validation
            # On utilise la date/heure actuelle

            amende.date_paiement = timezone.now()

        amende.valide_par = user
        amende.save()

        # Message de succès
        messages.success(request,
            _("✅ Paiement validé pour l'amende %(numero)s - Montant: %(montant)s FCFA") % {
                'numero': amende.numero_ticket,
                'montant': f"{amende.montant_amende:,.0f}".replace(',', ' ')
            })

        # Avertissement sur les amendes antérieures (si présentes)
        if avertissement_amendes:
            if avertissement_amendes['autres_stations'] > 0:
                messages.warning(request,
                    _("⚠️ ATTENTION: Ce véhicule (%(immat)s) a encore %(nb)d amende(s) non payée(s) "
                      "dans d'autres stations: %(stations)s. Montant total impayé: %(montant)s FCFA") % {
                        'immat': amende.immatriculation,
                        'nb': avertissement_amendes['autres_stations'],
                        'stations': ', '.join(avertissement_amendes['stations']),
                        'montant': f"{avertissement_amendes['montant_total']:,.0f}".replace(',', ' ')
                    })

            if avertissement_amendes['meme_station'] > 0:
                messages.info(request,
                    _("ℹ️ Ce véhicule a également %(nb)d amende(s) antérieure(s) non payée(s) "
                      "dans cette station.") % {
                        'nb': avertissement_amendes['meme_station']
                    })

        # Journalisation (si pas déjà fait pour revalidation)
        if not est_revalidation:
            details_log = (
                f"N°Ticket: {amende.numero_ticket} | Montant: {amende.montant_amende} FCFA | "
                f"Véhicule: {amende.immatriculation} | Station: {amende.station.nom} | "
                f"Date émission: {amende.date_heure_emission}"
            )

            if avertissement_amendes:
                details_log += (
                    f" | AVERTISSEMENT: {avertissement_amendes['total']} amende(s) antérieure(s) "
                    f"non payée(s) ({avertissement_amendes['autres_stations']} dans autres stations)"
                )

            log_user_action(
                user,
                "Validation paiement amende",
                details_log,
                request
            )

        # Log spécifique si amendes antérieures
        if avertissement_amendes and avertissement_amendes['autres_stations'] > 0:
            logger.info(
                f"Validation avec avertissement: Amende {amende.numero_ticket} validée - "
                f"Véhicule {amende.immatriculation} a {avertissement_amendes['autres_stations']} "
                f"amendes antérieures dans: {avertissement_amendes['stations']}"
            )

    except Exception as e:
        logger.error(f"Erreur validation paiement: {e}", exc_info=True)
        log_user_action(
            user,
            "Erreur validation paiement",
            f"Amende {amende.numero_ticket} - Erreur: {str(e)}",
            request
        )
        messages.error(request, _("Erreur lors de la validation du paiement."))

    return redirect('inventaire:liste_amendes_a_valider')


# ===================================================================
# VUE valider_paiements_masse - AVEC LOGIQUE REVALIDATION
# ===================================================================
# Remplacer également cette vue pour gérer les revalidations en masse

@validation_pesage_required
@require_POST
def valider_paiements_masse(request):
    """
    Valide plusieurs paiements en une fois.
    Permission: peut_valider_paiement_amende

    COMPORTEMENT:
    - Valide toutes les amendes sélectionnées
    - Avertit si des véhicules ont des amendes antérieures non payées
    - Gère les revalidations après modification admin
    """
    user = request.user

    if not has_permission(user, 'peut_valider_paiement_amende'):
        log_user_action(
            user,
            "Validation masse - permission refusée",
            "Tentative de validation en masse sans permission",
            request
        )
        messages.error(request, _("Vous n'avez pas la permission de valider les paiements."))
        return redirect('inventaire:liste_amendes_a_valider')

    station, _unused = get_station_context(request, user)
    amende_ids = request.POST.getlist('amendes')

    if not amende_ids:
        messages.warning(request, _("Aucune amende sélectionnée."))
        return redirect('inventaire:liste_amendes_a_valider')

    count_success = 0
    count_revalidations = 0  # Compteur pour les revalidations
    montant_total = Decimal('0')
    amendes_validees = []
    amendes_revalidees = []  # Liste des revalidations
    vehicules_avec_anterieures = []  # Pour l'avertissement

    for amende_id in amende_ids:
        try:
            if user_has_acces_tous_postes(user):
                amende = AmendeEmise.objects.get(pk=amende_id, statut='non_paye')
            else:
                amende = AmendeEmise.objects.get(pk=amende_id, station=station, statut='non_paye')

            # Vérifier amendes antérieures (pour avertissement)
            immat_norm = normalize_immatriculation(amende.immatriculation)
            amendes_anterieures = AmendeEmise.objects.filter(
                Q(immatriculation_normalise__iexact=immat_norm) |
                Q(immatriculation__iexact=amende.immatriculation),
                statut='non_paye',
                date_heure_emission__lt=amende.date_heure_emission
            ).exclude(station=amende.station).exclude(pk=amende.pk)

            if amendes_anterieures.exists():
                vehicules_avec_anterieures.append({
                    'immat': amende.immatriculation,
                    'nb': amendes_anterieures.count(),
                    'stations': list(amendes_anterieures.values_list('station__nom', flat=True).distinct())
                })

            # Valider le paiement
            amende.statut = 'paye'

            # ===============================================================
            # LOGIQUE CRITIQUE: Date de paiement pour revalidation
            # ===============================================================
            if amende.date_paiement_originale:
                # Revalidation après modification admin
                amende.date_paiement = amende.date_paiement_originale
                count_revalidations += 1
                amendes_revalidees.append({
                    'numero': amende.numero_ticket,
                    'date_originale': amende.date_paiement_originale.strftime('%d/%m/%Y')
                })
            else:
                # Première validation
                amende.date_paiement = timezone.now()

            amende.valide_par = user
            amende.save()

            count_success += 1
            montant_total += amende.montant_amende
            amendes_validees.append(amende.numero_ticket)

        except AmendeEmise.DoesNotExist:
            continue
        except Exception as e:
            logger.warning(f"Erreur validation amende {amende_id}: {e}")
            continue

    if count_success > 0:
        messages.success(request,
            _("✅ %(count)d paiement(s) validé(s) - Total: %(montant)s FCFA") % {
                'count': count_success,
                'montant': f"{montant_total:,.0f}".replace(',', ' ')
            })

        # Message spécifique pour les revalidations
        if count_revalidations > 0:
            messages.info(request,
                _("ℹ️ %(nb)d amende(s) étai(en)t des revalidations après modification admin. "
                  "Les recettes sont comptabilisées aux dates originales.") % {
                    'nb': count_revalidations
                })

        # Avertissement si des véhicules ont des amendes antérieures
        if vehicules_avec_anterieures:
            # Regrouper par véhicule
            vehicules_uniques = {}
            for v in vehicules_avec_anterieures:
                if v['immat'] not in vehicules_uniques:
                    vehicules_uniques[v['immat']] = v

            messages.warning(request,
                _("⚠️ %(nb_vehicules)d véhicule(s) ont des amendes antérieures non payées "
                  "dans d'autres stations. Ces amendes restent à payer.") % {
                    'nb_vehicules': len(vehicules_uniques)
                })

        # Journalisation détaillée
        details_log = (
            f"{count_success} amendes validées | Total: {montant_total} FCFA | "
            f"N°Tickets: {', '.join(amendes_validees[:10])}{'...' if len(amendes_validees) > 10 else ''}"
        )

        if count_revalidations > 0:
            details_log += f" | Revalidations: {count_revalidations}"
            for reval in amendes_revalidees[:5]:
                details_log += f" [{reval['numero']}→{reval['date_originale']}]"
            if len(amendes_revalidees) > 5:
                details_log += "..."

        if vehicules_avec_anterieures:
            details_log += f" | {len(vehicules_avec_anterieures)} véhicules avec amendes antérieures"

        log_user_action(
            user,
            "Validation paiements en masse",
            details_log,
            request
        )

        # Log pour les revalidations
        if count_revalidations > 0:
            logger.info(
                f"Validation masse avec {count_revalidations} revalidation(s): "
                f"{', '.join([r['numero'] for r in amendes_revalidees])}"
            )
    else:
        messages.warning(request, _("Aucun paiement n'a pu être validé."))

    return redirect('inventaire:liste_amendes_a_valider')


# ===================================================================
# VUE OPTIONNELLE: CONSULTATION DES AMENDES ANTÉRIEURES
# Pour permettre au régisseur de voir les détails avant validation
# ===================================================================

@validation_pesage_required
@require_GET
def consulter_amendes_anterieures(request, pk):
    """
    Affiche les détails des amendes antérieures d'un véhicule avant validation.
    Page informative qui permet ensuite de valider.
    """
    user = request.user
    station, _unused = get_station_context(request, user)

    # Récupérer l'amende
    if user_has_acces_tous_postes(user):
        amende = get_object_or_404(AmendeEmise, pk=pk)
    else:
        amende = get_object_or_404(AmendeEmise, pk=pk, station=station)

    # Rechercher les amendes antérieures
    immat_norm = normalize_immatriculation(amende.immatriculation)

    amendes_anterieures = AmendeEmise.objects.filter(
        Q(immatriculation_normalise__iexact=immat_norm) |
        Q(immatriculation__iexact=amende.immatriculation) |
        Q(immatriculation__iexact=immat_norm),
        statut='non_paye',
        date_heure_emission__lt=amende.date_heure_emission
    ).exclude(pk=amende.pk).select_related('station').order_by('date_heure_emission')

    # Séparer par station
    amendes_autres_stations = amendes_anterieures.exclude(station=amende.station)
    amendes_meme_station = amendes_anterieures.filter(station=amende.station)

    # Historique complet du véhicule
    historique = AmendeEmise.objects.filter(
        Q(immatriculation_normalise__iexact=immat_norm) |
        Q(immatriculation__iexact=amende.immatriculation)
    ).select_related('station').order_by('-date_heure_emission')

    # Statistiques
    stats = historique.aggregate(
        total=Count('pk'),
        payees=Count('pk', filter=Q(statut='paye')),
        non_payees=Count('pk', filter=Q(statut='non_paye')),
        montant_total=Sum('montant_amende'),
        montant_paye=Sum('montant_amende', filter=Q(statut='paye')),
        montant_impaye=Sum('montant_amende', filter=Q(statut='non_paye')),
    )

    context = {
        'title': _('Détails avant validation'),
        'amende': amende,
        'station': station,
        'amendes_autres_stations': amendes_autres_stations,
        'amendes_meme_station': amendes_meme_station,
        'historique': historique[:20],  # Limiter à 20 dernières
        'stats': stats,
        'has_anterieures': amendes_anterieures.exists(),
        'montant_total_impaye_autres': amendes_autres_stations.aggregate(
            total=Sum('montant_amende'))['total'] or 0,
    }

    return render(request, 'pesage/consulter_amendes_anterieures.html', context)


# ===================================================================
# VUE DE VALIDATION DIRECTE DEPUIS LA PAGE DE CONSULTATION
# ===================================================================

@validation_pesage_required
@require_POST
def valider_paiement_avec_avertissement(request, pk):
    """
    Valide le paiement après que l'utilisateur a vu l'avertissement.
    Identique à valider_paiement mais avec confirmation explicite.
    """
    # Vérifier que l'utilisateur a coché la case de confirmation
    confirmation = request.POST.get('confirmer_validation', False)

    if not confirmation:
        messages.error(request, _("Veuillez confirmer que vous avez pris connaissance des amendes antérieures."))
        return redirect('inventaire:consulter_amendes_anterieures', pk=pk)

    # Réutiliser la logique de validation standard
    return valider_paiement(request, pk)



# ===================================================================
# PESÉES JOURNALIÈRES
# Permission requise: peut_saisir_pesee_jour
# ===================================================================

@saisie_pesage_required
def saisir_pesees(request):
    """
    Saisie du nombre de pesées journalières.
    Permission: peut_saisir_pesee_jour
    """
    user = request.user
    today = timezone.now().date()

    # Vérifier la permission spécifique
    if not has_permission(user, 'peut_saisir_pesee_jour'):
        log_user_action(
            user,
            "Saisie pesées - permission refusée",
            "Permission peut_saisir_pesee_jour manquante",
            request
        )
        messages.error(request, _("Vous n'avez pas la permission de saisir des pesées."))
        return redirect('inventaire:historique_pesees')

    station, redirect_response = get_station_context(request, user)

    if user_has_acces_tous_postes(user) and station is None:
        return redirect(f"{reverse('inventaire:selectionner_station')}?action=saisir_pesees")

    if redirect_response:
        return redirect_response

    # Gestion de la date
    date_str = request.GET.get('date') or request.POST.get('date')
    if date_str:
        try:
            date_selectionnee = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            date_selectionnee = today
    else:
        date_selectionnee = today

    is_valid, error_msg = valider_date_saisie(date_selectionnee)
    if not is_valid:
        messages.error(request, error_msg)
        date_selectionnee = today

    # Vérifier si déjà saisi
    pesee_existante = PeseesJournalieres.objects.filter(
        station=station,
        date=date_selectionnee
    ).first()
    deja_saisi = pesee_existante is not None

    if request.method == 'POST' and not deja_saisi:
        date_post = request.POST.get('date')
        if date_post:
            try:
                date_post_obj = datetime.strptime(date_post, '%Y-%m-%d').date()
                is_valid, error_msg = valider_date_saisie(date_post_obj)
                if not is_valid:
                    messages.error(request, error_msg)
                    return redirect('inventaire:saisir_pesees')
                date_selectionnee = date_post_obj
            except ValueError:
                pass

        form = PeseesJournalieresForm(request.POST)
        if form.is_valid():
            pesees = form.save(commit=False)
            pesees.station = station
            pesees.date = date_selectionnee
            pesees.saisi_par = user
            pesees.save()

            messages.success(request,
                _("Pesées du %(date)s enregistrées: %(nombre)d pesées") % {
                    'date': pesees.date.strftime('%d/%m/%Y'),
                    'nombre': pesees.nombre_pesees
                })

            log_user_action(
                user,
                "Saisie pesées journalières",
                f"Station: {station.nom} | Date: {pesees.date.strftime('%d/%m/%Y')} | "
                f"Nombre de pesées: {pesees.nombre_pesees}",
                request
            )

            return redirect('inventaire:historique_pesees')
    else:
        form = PeseesJournalieresForm()

    context = {
        'form': form,
        'station': station,
        'today': today,
        'date_selectionnee': date_selectionnee,
        'deja_saisi': deja_saisi,
        'pesee_existante': pesee_existante,
        'is_admin': is_admin_user(user),
        'title': _('Saisir les pesées du jour'),
        'peut_saisir_pesee': has_permission(user, 'peut_saisir_pesee_jour'),
    }
    return render(request, 'pesage/saisir_pesees.html', context)


@pesage_access_required
def historique_pesees(request):
    """
    Historique des pesées journalières.
    Permission: peut_voir_historique_pesees
    """
    user = request.user

    # Vérifier la permission
    if not has_permission(user, 'peut_voir_historique_pesees'):
        log_user_action(
            user,
            "Historique pesées - permission refusée",
            "Permission peut_voir_historique_pesees manquante",
            request
        )
        messages.error(request, _("Vous n'avez pas la permission de voir l'historique des pesées."))
        return redirect('common:dashboard')

    stations_accessibles = get_stations_pesage_accessibles(user)

    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response

    # Construction du queryset
    if station is None and user_has_acces_tous_postes(user):
        queryset = PeseesJournalieres.objects.all()
        station_filter = request.GET.get('station_filter')
        if station_filter:
            queryset = queryset.filter(station_id=station_filter)
    elif station:
        queryset = PeseesJournalieres.objects.filter(station=station)
    else:
        queryset = PeseesJournalieres.objects.none()

    queryset = queryset.select_related('station', 'saisi_par').order_by('-date')
    stats = queryset.aggregate(total_pesees=Sum('nombre_pesees'), count_jours=Count('id'))

    paginator = Paginator(queryset, 30)
    page = request.GET.get('page')
    pesees = paginator.get_page(page)

    context = {
        'pesees': pesees,
        'station': station,
        'stations_accessibles': stations_accessibles,
        'stats': stats,
        'is_admin': is_admin_user(user),
        'station_filter': request.GET.get('station_filter', ''),
        'title': _('Historique des pesées'),
        'peut_saisir_pesee': has_permission(user, 'peut_saisir_pesee_jour'),
    }
    return render(request, 'pesage/historique_pesees.html', context)


# ===================================================================
# QUITTANCEMENTS - SAISIE
# Permission requise: peut_saisir_quittance_pesage
# ===================================================================

@quittancement_pesage_required
def saisie_quittancement_pesage(request):
    """
    Vue pour saisir un quittancement pesage (version en 3 étapes)
    Permission: peut_saisir_quittance_pesage
    """
    user = request.user

    # Nettoyer la session au début si nouvelle saisie
    if request.method == 'GET' and 'etape' not in request.GET:
        for key in ['exercice_pesage_temp', 'mois_pesage_temp', 'type_declaration_pesage_temp',
                   'form_data_pesage_temp', 'image_pesage_temp_path', 'station_pesage_id']:
            request.session.pop(key, None)

    # GESTION DE LA STATION
    if user_has_acces_tous_postes(user):
        station_id = (
            request.GET.get('station') or
            request.POST.get('station') or
            request.session.get('station_pesage_id')
        )

        if not station_id:
            return redirect(f"{reverse('inventaire:selectionner_station')}?action=saisie_quittancement_pesage")

        try:
            station = Poste.objects.get(pk=station_id, type='pesage', is_active=True)
            request.session['station_pesage_id'] = station.id
        except Poste.DoesNotExist:
            request.session.pop('station_pesage_id', None)
            messages.error(request, "❌ Station invalide, veuillez en sélectionner une autre")
            return redirect(f"{reverse('inventaire:selectionner_station')}?action=saisie_quittancement_pesage")
    else:
        poste = getattr(user, 'poste_affectation', None)
        if poste and poste.type == 'pesage':
            station = poste
        else:
            log_user_action(
                user,
                "Quittancement pesage - station manquante",
                "Utilisateur sans station de pesage tente de saisir un quittancement",
                request
            )
            messages.error(request, "❌ Vous devez être affecté à une station de pesage")
            return redirect('common:dashboard')

    etape = int(request.POST.get('etape', request.GET.get('etape', 1)))

    # ÉTAPE 1 : Paramètres globaux
    if etape == 1:
        if request.method == 'POST':
            exercice = request.POST.get('exercice')
            mois = request.POST.get('mois')
            type_declaration = request.POST.get('type_declaration')

            errors = []
            if not exercice: errors.append("Veuillez sélectionner un exercice")
            if not mois: errors.append("Veuillez sélectionner un mois")
            if not type_declaration: errors.append("Veuillez sélectionner un type de déclaration")

            if errors:
                for error in errors:
                    messages.error(request, f"⚠️ {error}")
                return redirect(f"{reverse('inventaire:saisie_quittancement_pesage')}?station={station.id}")

            request.session['exercice_pesage_temp'] = exercice
            request.session['mois_pesage_temp'] = mois
            request.session['type_declaration_pesage_temp'] = type_declaration

            log_user_action(
                user,
                "Quittancement pesage - étape 1",
                f"Station: {station.nom} | Exercice: {exercice} | Mois: {mois} | Type: {type_declaration}",
                request
            )

            return redirect(f"{reverse('inventaire:saisie_quittancement_pesage')}?etape=2&station={station.id}")

        annee_courante = datetime.now().year
        annees = list(range(annee_courante - 5, annee_courante + 2))

        context = {
            'etape': 1,
            'station': station,
            'annees': annees,
            'annee_courante': annee_courante,
            'types_declaration': [('journaliere', 'Journalière (par jour)'), ('decade', 'Par décade')],
            'is_admin': is_admin_user(user),
        }
        return render(request, 'pesage/saisie_quittancement_pesage.html', context)

    # ÉTAPE 2 : Saisie du quittancement + IMAGE
    elif etape == 2:
        exercice = request.session.get('exercice_pesage_temp')
        mois = request.session.get('mois_pesage_temp')
        type_declaration = request.session.get('type_declaration_pesage_temp')

        if not all([exercice, mois, type_declaration]):
            messages.error(request, "❌ Session expirée, veuillez recommencer")
            return redirect(f"{reverse('inventaire:saisie_quittancement_pesage')}?station={station.id}")

        if request.method == 'POST':
            form_data = {
                'station_id': station.id,
                'numero_quittance': request.POST.get('numero_quittance'),
                'date_quittancement': request.POST.get('date_quittancement'),
                'montant': request.POST.get('montant'),
                'observations': request.POST.get('observations', ''),
            }

            if type_declaration == 'journaliere':
                form_data['date_recette'] = request.POST.get('date_recette')
            else:
                form_data['date_debut_decade'] = request.POST.get('date_debut_decade')
                form_data['date_fin_decade'] = request.POST.get('date_fin_decade')

            # Gérer l'image uploadée
            has_image = False
            image_name = None
            if 'image_quittance' in request.FILES:
                from django.core.files.storage import default_storage
                image_file = request.FILES['image_quittance']
                temp_name = f"temp_pesage_{user.id}_{timezone.now().timestamp()}_{image_file.name}"
                temp_path = os.path.join('temp_quittances_pesage', temp_name)
                saved_path = default_storage.save(temp_path, image_file)
                request.session['image_pesage_temp_path'] = saved_path
                has_image = True
                image_name = image_file.name

            form_data['has_image'] = has_image
            form_data['image_name'] = image_name

            # VALIDATION COMPLÈTE
            errors = []

            # Validation numéro de quittance
            if not form_data['numero_quittance']:
                errors.append("Le numéro de quittance est obligatoire")
            else:
                numero = form_data['numero_quittance'].strip().upper()

                if QuittancementPesage.objects.filter(numero_quittance__iexact=numero).exists():
                    errors.append(f"Le numéro de quittance '{numero}' existe déjà dans les quittancements pesage")

                try:
                    from inventaire.models import Quittancement
                    if Quittancement.objects.filter(numero_quittance__iexact=numero).exists():
                        errors.append(f"Le numéro de quittance '{numero}' existe déjà dans les quittancements péage")
                except ImportError:
                    pass

            if not form_data['date_quittancement']:
                errors.append("La date de quittancement est obligatoire")
            if not form_data['montant']:
                errors.append("Le montant est obligatoire")
            if not has_image:
                errors.append("L'image de la quittance est obligatoire")

            if type_declaration == 'journaliere':
                if not form_data.get('date_recette'):
                    errors.append("La date de recette est obligatoire")
            else:
                if not form_data.get('date_debut_decade'):
                    errors.append("La date de début de décade est obligatoire")
                if not form_data.get('date_fin_decade'):
                    errors.append("La date de fin de décade est obligatoire")
                elif form_data.get('date_debut_decade') and form_data.get('date_fin_decade'):
                    if form_data['date_debut_decade'] > form_data['date_fin_decade']:
                        errors.append("La date de début doit être antérieure à la date de fin")

            # Validation des dates déjà quittancées
            if not errors:
                try:
                    from inventaire.utils_quittancement import valider_dates_quittancement_pesage

                    if type_declaration == 'journaliere':
                        is_valid, error_msg, _ = valider_dates_quittancement_pesage(
                            station=station,
                            exercice=int(exercice),
                            mois=mois,
                            type_declaration='journaliere',
                            date_recette=form_data.get('date_recette')
                        )
                    else:
                        is_valid, error_msg, _ = valider_dates_quittancement_pesage(
                            station=station,
                            exercice=int(exercice),
                            mois=mois,
                            type_declaration='decade',
                            date_debut=form_data.get('date_debut_decade'),
                            date_fin=form_data.get('date_fin_decade')
                        )

                    if not is_valid:
                        errors.append(error_msg)

                except Exception as e:
                    logger.error(f"Erreur validation dates pesage: {e}")

            if errors:
                for error in errors:
                    messages.error(request, f"❌ {error}")

                if has_image and request.session.get('image_pesage_temp_path'):
                    from django.core.files.storage import default_storage
                    temp_path = request.session.get('image_pesage_temp_path')
                    if default_storage.exists(temp_path):
                        default_storage.delete(temp_path)
                    request.session.pop('image_pesage_temp_path', None)

                context = {
                    'etape': 2,
                    'station': station,
                    'exercice': exercice,
                    'mois': mois,
                    'type_declaration': type_declaration,
                    'form_data': form_data,
                    'is_admin': is_admin_user(user),
                }
                return render(request, 'pesage/saisie_quittancement_pesage.html', context)

            request.session['form_data_pesage_temp'] = form_data
            return redirect(f"{reverse('inventaire:saisie_quittancement_pesage')}?etape=3&station={station.id}")

        context = {
            'etape': 2,
            'station': station,
            'exercice': exercice,
            'mois': mois,
            'type_declaration': type_declaration,
            'is_admin': is_admin_user(user),
        }
        return render(request, 'pesage/saisie_quittancement_pesage.html', context)

    # ÉTAPE 3 : Confirmation et enregistrement
    elif etape == 3:
        exercice = request.session.get('exercice_pesage_temp')
        mois = request.session.get('mois_pesage_temp')
        type_declaration = request.session.get('type_declaration_pesage_temp')
        form_data = request.session.get('form_data_pesage_temp')
        image_temp_path = request.session.get('image_pesage_temp_path')

        if not all([exercice, mois, type_declaration, form_data]):
            messages.error(request, "❌ Session expirée")
            return redirect(f"{reverse('inventaire:saisie_quittancement_pesage')}?station={station.id}")

        if request.method == 'POST':
            action = request.POST.get('action')

            if action == 'confirmer':
                try:
                    quittancement = QuittancementPesage(
                        numero_quittance=form_data['numero_quittance'],
                        station=station,
                        exercice=int(exercice),
                        mois=mois,
                        type_declaration=type_declaration,
                        date_quittancement=form_data['date_quittancement'],
                        montant_quittance=Decimal(form_data['montant']),
                        observations=form_data.get('observations', ''),
                        saisi_par=user,
                    )

                    if type_declaration == 'journaliere':
                        quittancement.date_recette = form_data['date_recette']
                    else:
                        quittancement.date_debut_decade = form_data['date_debut_decade']
                        quittancement.date_fin_decade = form_data['date_fin_decade']

                    if image_temp_path:
                        from django.core.files.storage import default_storage
                        from django.core.files import File
                        if default_storage.exists(image_temp_path):
                            temp_file = default_storage.open(image_temp_path, 'rb')
                            original_name = os.path.basename(image_temp_path).split('_', 4)[-1]
                            final_name = f"quittances_pesage/{quittancement.exercice}/{quittancement.mois}/{original_name}"
                            quittancement.image_quittance.save(final_name, File(temp_file), save=False)
                            temp_file.close()
                            default_storage.delete(image_temp_path)

                    quittancement.save()

                    log_user_action(
                        user,
                        "Création quittancement pesage",
                        f"N°{quittancement.numero_quittance} | Station: {station.nom} | "
                        f"Montant: {quittancement.montant_quittance} FCFA | "
                        f"Exercice: {exercice} | Mois: {mois} | Type: {type_declaration}",
                        request
                    )

                    # Nettoyer la session
                    for key in ['exercice_pesage_temp', 'mois_pesage_temp', 'type_declaration_pesage_temp',
                               'form_data_pesage_temp', 'image_pesage_temp_path']:
                        request.session.pop(key, None)

                    messages.success(request, f"✅ Quittancement {quittancement.numero_quittance} enregistré avec succès")
                    return redirect('inventaire:liste_quittancements_pesage')

                except ValidationError as e:
                    messages.error(request, f"❌ Erreur de validation : {e}")
                except Exception as e:
                    messages.error(request, f"❌ Erreur : {str(e)}")
                    logger.error(f"Erreur création quittancement pesage : {str(e)}", exc_info=True)

            elif action == 'retour':
                return redirect(f"{reverse('inventaire:saisie_quittancement_pesage')}?etape=2&station={station.id}")

            else:
                # Annulation
                if image_temp_path:
                    from django.core.files.storage import default_storage
                    if default_storage.exists(image_temp_path):
                        default_storage.delete(image_temp_path)

                for key in ['exercice_pesage_temp', 'mois_pesage_temp', 'type_declaration_pesage_temp',
                           'form_data_pesage_temp', 'image_pesage_temp_path']:
                    request.session.pop(key, None)

                messages.info(request, "Saisie annulée")
                return redirect('inventaire:liste_quittancements_pesage')

        # Affichage de la confirmation
        if type_declaration == 'journaliere':
            periode = f"Jour : {form_data['date_recette']}"
        else:
            periode = f"Décade : du {form_data['date_debut_decade']} au {form_data['date_fin_decade']}"

        context = {
            'etape': 3,
            'station': station,
            'exercice': exercice,
            'mois': mois,
            'type_declaration': type_declaration,
            'form_data': form_data,
            'periode': periode,
            'has_image': form_data.get('has_image', False),
            'image_name': form_data.get('image_name'),
            'is_admin': is_admin_user(user),
        }
        return render(request, 'pesage/saisie_quittancement_pesage.html', context)


# ===================================================================
# LISTE DES QUITTANCEMENTS
# Permission: peut_voir_liste_quittancements_pesage
# ===================================================================

@login_required
def liste_quittancements_pesage(request):
    """
    Liste des quittancements pesage avec filtres.
    Permission: peut_voir_liste_quittancements_pesage
    """
    user = request.user

    # Vérifier la permission
    if not has_permission(user, 'peut_voir_liste_quittancements_pesage'):
        log_user_action(
            user,
            "Liste quittancements - permission refusée",
            "Permission peut_voir_liste_quittancements_pesage manquante",
            request
        )
        messages.error(request, _("Accès non autorisé."))
        return redirect('inventaire:liste_amendes')

    # Construction du queryset selon les droits
    if user_has_acces_tous_postes(user):
        quittancements = QuittancementPesage.objects.all()
        stations = Poste.objects.filter(type='pesage', is_active=True).order_by('nom')
    else:
        poste = getattr(user, 'poste_affectation', None)
        if poste and poste.type == 'pesage':
            quittancements = QuittancementPesage.objects.filter(station=poste)
            stations = None
        else:
            quittancements = QuittancementPesage.objects.none()
            stations = None

    # Filtres
    station_id = request.GET.get('station')
    exercice = request.GET.get('exercice')
    type_declaration = request.GET.get('type_declaration')
    mois = request.GET.get('mois')

    if station_id:
        quittancements = quittancements.filter(station_id=station_id)
    if exercice:
        quittancements = quittancements.filter(exercice=exercice)
    if type_declaration:
        quittancements = quittancements.filter(type_declaration=type_declaration)
    if mois:
        quittancements = quittancements.filter(mois=mois)

    quittancements = quittancements.select_related('station', 'saisi_par').order_by('-date_quittancement', '-id')

    paginator = Paginator(quittancements, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    total_montant = quittancements.aggregate(Sum('montant_quittance'))['montant_quittance__sum'] or Decimal('0')

    current_year = datetime.now().year
    years_range = list(range(current_year, current_year - 5, -1))

    context = {
        'page_obj': page_obj,
        'quittancements': page_obj,
        'total_montant': total_montant,
        'nombre_quittancements': quittancements.count(),
        'stations': stations,
        'exercice_courant': current_year,
        'years_range': years_range,
        'types_declaration': [('journaliere', 'Journalière'), ('decade', 'Par décade')],
        'is_admin': is_admin_user(user),
        'title': _('Liste des quittancements'),
        'peut_saisir_quittance': has_permission(user, 'peut_saisir_quittance_pesage'),
    }
    return render(request, 'pesage/liste_quittancements_pesage.html', context)


# ===================================================================
# COMPTABILISATION DES QUITTANCEMENTS
# Permission: peut_comptabiliser_quittances_pesage
# ===================================================================

@login_required
def comptabilisation_quittancements_pesage(request):
    """
    Comptabilisation des quittancements PESAGE.

    CORRECTIONS APPLIQUÉES:
    - Permission peut_comptabiliser_quittances_pesage requise
    - Utilise user_has_acces_tous_postes() au lieu de vérifications manuelles
      pour permettre aux profils cisop_pesage, serv_controle, etc.
      de voir toutes les stations

    Profils ayant accès à toutes les stations (via HABILITATIONS_MULTI_POSTES):
    - admin_principal, coord_psrr, serv_info (administrateurs)
    - serv_emission, chef_ag, serv_controle, serv_ordre (services centraux)
    - cisop_peage, cisop_pesage (CISOP)
    - imprimerie, focal_regional, comptable_mat
    """
    from common.permissions import user_has_acces_tous_postes, has_permission, is_admin_user
    from common.utils import log_user_action

    import calendar
    from datetime import timedelta, date
    from decimal import Decimal
    from django.db.models import Q, Sum

    user = request.user

    # =========================================
    # VÉRIFICATION PERMISSION GRANULAIRE
    # =========================================
    if not has_permission(user, 'peut_comptabiliser_quittances_pesage'):
        log_user_action(
            user,
            "ACCÈS REFUSÉ - Comptabilisation quittancements pesage",
            f"Permission manquante: peut_comptabiliser_quittances_pesage | "
            f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )
        messages.error(request, _("Accès non autorisé."))
        return redirect('inventaire:liste_quittancements_pesage')

    # =========================================
    # DÉTERMINATION DU TYPE D'ACCÈS
    # CORRECTION: Utilise user_has_acces_tous_postes()
    # =========================================
    acces_tous_postes = user_has_acces_tous_postes(user)

    # Log d'accès avec détails
    type_acces = "Toutes stations" if acces_tous_postes else f"Station affectée: {getattr(user.poste_affectation, 'nom', 'Aucune')}"
    log_user_action(
        user,
        "Accès comptabilisation quittancements pesage",
        f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
        f"Type accès: {type_acces} | "
        f"Accès toutes stations: {acces_tous_postes} | "
        f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
        request
    )

    # =========================================
    # RÉCUPÉRATION DES PARAMÈTRES
    # =========================================
    annee_courante = timezone.now().year
    mois_courant = timezone.now().month

    periode = request.GET.get('periode', 'mois')
    station_id = request.GET.get('station')
    annee = int(request.GET.get('annee', annee_courante))
    mois = request.GET.get('mois')

    # =========================================
    # CALCUL DES DATES SELON LA PÉRIODE
    # =========================================
    mois_int = mois_courant  # Valeur par défaut

    if periode == 'mois':
        if mois:
            try:
                annee_mois = mois.split('-')
                mois_int = int(annee_mois[1])
                annee = int(annee_mois[0])
            except (ValueError, IndexError):
                mois_int = mois_courant
        else:
            mois_int = mois_courant
        date_debut = date(annee, mois_int, 1)
        dernier_jour = calendar.monthrange(annee, mois_int)[1]
        date_fin = date(annee, mois_int, dernier_jour)
    elif periode == 'trimestre':
        trimestre = int(request.GET.get('trimestre', ((mois_courant - 1) // 3) + 1))
        mois_debut = (trimestre - 1) * 3 + 1
        mois_fin = trimestre * 3
        date_debut = date(annee, mois_debut, 1)
        dernier_jour = calendar.monthrange(annee, mois_fin)[1]
        date_fin = date(annee, mois_fin, dernier_jour)
    elif periode == 'semestre':
        semestre = int(request.GET.get('semestre', 1 if mois_courant <= 6 else 2))
        if semestre == 1:
            date_debut = date(annee, 1, 1)
            date_fin = date(annee, 6, 30)
        else:
            date_debut = date(annee, 7, 1)
            date_fin = date(annee, 12, 31)
    else:  # année
        date_debut = date(annee, 1, 1)
        date_fin = date(annee, 12, 31)

    # =========================================
    # SÉLECTION DES STATIONS SELON PERMISSIONS
    # CORRECTION PRINCIPALE: user_has_acces_tous_postes()
    # =========================================
    if acces_tous_postes:
        # Utilisateur avec accès à toutes les stations
        # (admin, serv_controle, cisop_pesage, serv_emission, etc.)
        if station_id:
            stations = Poste.objects.filter(id=station_id, type='pesage', is_active=True)
        else:
            stations = Poste.objects.filter(type='pesage', is_active=True)

        log_user_action(
            user,
            "Comptabilisation pesage - Accès multi-stations",
            f"Nombre de stations accessibles: {stations.count()} | "
            f"Filtre station_id: {station_id or 'Aucun (toutes)'}",
            request
        )
    else:
        # Utilisateur avec accès limité à sa station d'affectation
        if user.poste_affectation and user.poste_affectation.type == 'pesage':
            stations = Poste.objects.filter(id=user.poste_affectation.id)
            log_user_action(
                user,
                "Comptabilisation pesage - Accès station unique",
                f"Station: {user.poste_affectation.nom} (ID: {user.poste_affectation.id})",
                request
            )
        else:
            stations = Poste.objects.none()
            log_user_action(
                user,
                "Comptabilisation pesage - Aucune station",
                "L'utilisateur n'a pas de station de pesage affectée",
                request
            )

    # Liste des stations pour le filtre dropdown
    if acces_tous_postes:
        stations_filtre = Poste.objects.filter(type='pesage', is_active=True).order_by('nom')
    else:
        stations_filtre = None

    # =========================================
    # CALCUL DES RÉSULTATS PAR STATION
    # =========================================
    resultats = []
    total_attendu_global = Decimal('0')
    total_quittance_global = Decimal('0')

    for station in stations:
        # Amendes payées dans la période
        amendes_payees = AmendeEmise.objects.filter(
            station=station,
            statut='paye',
            date_paiement__date__gte=date_debut,
            date_paiement__date__lte=date_fin
        )
        total_attendu = amendes_payees.aggregate(Sum('montant_amende'))['montant_amende__sum'] or Decimal('0')

        # Quittancements journaliers
        quittancements_journaliers = QuittancementPesage.objects.filter(
            station=station,
            type_declaration='journaliere',
            date_recette__range=[date_debut, date_fin]
        ).aggregate(Sum('montant_quittance'))['montant_quittance__sum'] or Decimal('0')

        # Quittancements de décade
        quittancements_decades = QuittancementPesage.objects.filter(
            station=station,
            type_declaration='decade'
        ).filter(
            Q(date_debut_decade__lte=date_fin) & Q(date_fin_decade__gte=date_debut)
        ).aggregate(Sum('montant_quittance'))['montant_quittance__sum'] or Decimal('0')

        total_quittance = quittancements_journaliers + quittancements_decades
        ecart = total_quittance - total_attendu
        ecart_pourcentage = (ecart / total_attendu * 100) if total_attendu > 0 else Decimal('0')

        # Déterminer le statut
        if abs(ecart) < 1:
            statut, statut_label, statut_class = 'conforme', 'Conforme', 'success'
        else:
            justification_existe = JustificationEcartPesage.objects.filter(
                station=station,
                date_debut=date_debut,
                date_fin=date_fin
            ).exists()
            if justification_existe:
                statut, statut_label, statut_class = 'justifie', 'Justifié', 'info'
            else:
                statut, statut_label, statut_class = 'ecart', 'Non justifié', 'danger'

        resultats.append({
            'station': station,
            'station_id': station.id,
            'station_nom': station.nom,
            'total_quittance': total_quittance,
            'total_attendu': total_attendu,
            'ecart': ecart,
            'ecart_pourcentage': ecart_pourcentage,
            'statut': statut,
            'statut_label': statut_label,
            'statut_class': statut_class
        })
        total_attendu_global += total_attendu
        total_quittance_global += total_quittance

    # =========================================
    # CALCUL DES STATISTIQUES GLOBALES
    # =========================================
    ecart_global = total_quittance_global - total_attendu_global
    statistiques = {
        'total_attendu': total_attendu_global,
        'total_quittance': total_quittance_global,
        'ecart_total': ecart_global,
        'ecart_pourcentage': (ecart_global / total_attendu_global * 100) if total_attendu_global > 0 else Decimal('0'),
        'nombre_stations': len(resultats),
        'nombre_conformes': len([r for r in resultats if r['statut'] == 'conforme']),
        'nombre_justifies': len([r for r in resultats if r['statut'] == 'justifie']),
        'nombre_ecarts': len([r for r in resultats if r['statut'] == 'ecart']),
    }

    annees_disponibles = list(range(annee_courante - 5, annee_courante + 1))

    # =========================================
    # LOG FINAL DE CONSULTATION
    # =========================================
    log_user_action(
        user,
        "Consultation comptabilisation quittancements pesage",
        f"Période: {periode} | Dates: {date_debut} au {date_fin} | "
        f"Stations analysées: {len(resultats)} | "
        f"Conformes: {statistiques['nombre_conformes']} | "
        f"Écarts: {statistiques['nombre_ecarts']} | "
        f"Total attendu: {total_attendu_global} FCFA | "
        f"Total quittancé: {total_quittance_global} FCFA | "
        f"Écart global: {ecart_global} FCFA",
        request
    )

    # =========================================
    # CONTEXTE POUR LE TEMPLATE
    # CORRECTION: is_admin utilise user_has_acces_tous_postes()
    # =========================================
    context = {
        'resultats': resultats,
        'statistiques': statistiques,
        'periode': periode,
        'annee': annee,
        'annees_disponibles': annees_disponibles,
        'mois': f"{annee}-{mois_int:02d}" if periode == 'mois' else None,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'stations': stations_filtre,  # Pour le dropdown
        'station_selectionne': int(station_id) if station_id else None,
        # CORRECTION: Variables d'accès cohérentes
        'is_admin': acces_tous_postes,
        'acces_tous_postes': acces_tous_postes,
        'title': _('Comptabilisation Quittancements Pesage'),
    }

    return render(request, 'pesage/comptabilisation_quittancements_pesage.html', context)
# ===================================================================
# JUSTIFICATION ÉCART PESAGE
#
# AVANT: @quittancement_pesage_required (regisseur + admin)
# APRÈS: Permission 'peut_comptabiliser_quittances_pesage'
# ===================================================================

@login_required
def justifier_ecart_pesage(request, station_id, date_debut, date_fin):
    """
    Justifier un écart entre quittancements et amendes payées.

    PERMISSION: peut_comptabiliser_quittances_pesage
    """
    user = request.user

    # Vérifier la permission granulaire
    if not has_permission(user, 'peut_comptabiliser_quittances_pesage'):
        logger.warning(
            f"Accès refusé justifier_ecart_pesage | User: {user.username} | "
            f"Permission peut_comptabiliser_quittances_pesage: {getattr(user, 'peut_comptabiliser_quittances_pesage', False)}"
        )
        messages.error(request, _("Vous n'avez pas la permission de justifier les écarts."))
        return redirect('common:dashboard')

    station = get_object_or_404(Poste, id=station_id, type='pesage')

    # Parser les dates
    try:
        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
    except ValueError as e:
        messages.error(request, f"Format de date invalide : {str(e)}")
        return redirect('inventaire:comptabilisation_quittancements_pesage')

    # Calculer les totaux
    total_quittance = QuittancementPesage.objects.filter(
        station=station
    ).filter(
        Q(type_declaration='journaliere', date_recette__range=[date_debut_obj, date_fin_obj]) |
        Q(type_declaration='decade', date_debut_decade__lte=date_fin_obj, date_fin_decade__gte=date_debut_obj)
    ).aggregate(Sum('montant_quittance'))['montant_quittance__sum'] or Decimal('0')

    total_attendu = AmendeEmise.objects.filter(
        station=station,
        statut='paye',
        date_paiement__date__gte=date_debut_obj,
        date_paiement__date__lte=date_fin_obj
    ).aggregate(Sum('montant_amende'))['montant_amende__sum'] or Decimal('0')

    ecart = total_quittance - total_attendu
    ecart_pourcentage = (ecart / total_attendu * 100) if total_attendu > 0 else 0

    # Vérifier si une justification existe déjà
    justification_existante = JustificationEcartPesage.objects.filter(
        station=station,
        date_debut=date_debut_obj,
        date_fin=date_fin_obj
    ).select_related('justifie_par').first()

    if request.method == 'POST':
        justification_texte = request.POST.get('justification', '').strip()

        if len(justification_texte) < 20:
            messages.error(request, "❌ La justification doit contenir au moins 20 caractères.")
        else:
            try:
                if justification_existante:
                    # Mise à jour
                    justification_existante.justification = justification_texte
                    justification_existante.justifie_par = user
                    justification_existante.date_justification = timezone.now()
                    justification_existante.montant_quittance = total_quittance
                    justification_existante.montant_attendu = total_attendu
                    justification_existante.ecart = ecart
                    justification_existante.save()
                else:
                    # Création
                    JustificationEcartPesage.objects.create(
                        station=station,
                        date_debut=date_debut_obj,
                        date_fin=date_fin_obj,
                        montant_quittance=total_quittance,
                        montant_attendu=total_attendu,
                        ecart=ecart,
                        justification=justification_texte,
                        justifie_par=user
                    )

                log_user_action(
                    user,
                    "Justification écart quittancement pesage",
                    f"Station: {station.nom} | Période: {date_debut_obj} - {date_fin_obj} | "
                    f"Écart: {ecart} FCFA",
                    request
                )

                logger.info(
                    f"Justification écart pesage | User: {user.username} | "
                    f"Station: {station.nom} | Période: {date_debut_obj} - {date_fin_obj} | "
                    f"Écart: {ecart} FCFA"
                )

                messages.success(request, "✅ Justification enregistrée avec succès.")
                return redirect('inventaire:comptabilisation_quittancements_pesage')
            except Exception as e:
                logger.error(f"Erreur justification écart pesage: {e}", exc_info=True)
                messages.error(request, f"❌ Erreur lors de l'enregistrement : {str(e)}")

    context = {
        'station': station,
        'date_debut': date_debut_obj,
        'date_fin': date_fin_obj,
        'total_quittance': total_quittance,
        'total_attendu': total_attendu,
        'ecart': ecart,
        'ecart_pourcentage': ecart_pourcentage,
        'justification_existante': justification_existante,
        'is_admin': is_admin_user(user),
        'title': _('Justifier Écart'),
    }
    return render(request, 'pesage/justifier_ecart_pesage.html', context)

@login_required
@require_GET
def confirmer_suppression_quittancement_pesage(request, pk):
    """
    Vue de confirmation de suppression d'un quittancement pesage.
    Affiche une page de confirmation avec les détails du quittancement.

    Permission requise: is_admin_user (admin_principal, coord_psrr, serv_info)

    Args:
        request: HttpRequest
        pk: ID du quittancement pesage à supprimer

    Returns:
        Rendu du template de confirmation ou redirection si non autorisé
    """
    user = request.user

    # =========================================
    # VÉRIFICATION PERMISSION ADMINISTRATEUR
    # =========================================
    if not is_admin_user(user):
        log_user_action(
            user,
            "ACCÈS REFUSÉ - Suppression quittancement pesage",
            f"Tentative de suppression du quittancement pesage ID={pk} | "
            f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
            f"Permission requise: is_admin_user | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )
        messages.error(request, _("Seuls les administrateurs peuvent supprimer des quittancements."))
        return redirect('inventaire:liste_quittancements_pesage')

    # =========================================
    # RÉCUPÉRATION DU QUITTANCEMENT PESAGE
    # =========================================
    quittancement = get_object_or_404(
        QuittancementPesage.objects.select_related('station', 'saisi_par'),
        pk=pk
    )

    # =========================================
    # PRÉPARATION DES DONNÉES D'AFFICHAGE
    # =========================================

    # Déterminer la période concernée
    if quittancement.type_declaration == 'journaliere':
        periode_str = f"Jour du {quittancement.date_recette.strftime('%d/%m/%Y')}" if quittancement.date_recette else "Date non définie"
        jours_liberes = [quittancement.date_recette] if quittancement.date_recette else []
    else:  # decade
        if quittancement.date_debut_decade and quittancement.date_fin_decade:
            periode_str = f"Décade du {quittancement.date_debut_decade.strftime('%d/%m/%Y')} au {quittancement.date_fin_decade.strftime('%d/%m/%Y')}"
            # Calculer tous les jours de la décade
            jours_liberes = []
            current = quittancement.date_debut_decade
            while current <= quittancement.date_fin_decade:
                jours_liberes.append(current)
                current += timedelta(days=1)
        else:
            periode_str = "Période non définie"
            jours_liberes = []

    # Log de l'accès à la page de confirmation
    log_user_action(
        user,
        "Accès page suppression quittancement pesage",
        f"Quittancement pesage ID={pk} | N°{quittancement.numero_quittance} | "
        f"Station: {quittancement.station.nom} | "
        f"Montant: {quittancement.montant_quittance} FCFA | "
        f"Période: {periode_str} | "
        f"Jours à libérer: {len(jours_liberes)} | "
        f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
        request
    )

    context = {
        'quittancement': quittancement,
        'station': quittancement.station,
        'periode_str': periode_str,
        'jours_liberes': jours_liberes,
        'nombre_jours': len(jours_liberes),
        'title': f"Confirmer la suppression - {quittancement.numero_quittance}",
    }

    return render(request, 'pesage/confirmer_suppression_quittancement_pesage.html', context)


@login_required
@require_POST
def supprimer_quittancement_pesage(request, pk):
    """
    Vue d'exécution de la suppression d'un quittancement pesage.
    Supprime le quittancement et libère les jours associés pour permettre
    une nouvelle saisie.

    Permission requise: is_admin_user (admin_principal, coord_psrr, serv_info)

    LOGIQUE DE LIBÉRATION DES JOURS:
    - Pour type_declaration='journaliere': libère date_recette
    - Pour type_declaration='decade': libère tous les jours entre date_debut_decade et date_fin_decade

    La suppression du quittancement suffit à libérer les jours car la validation
    des dates dans saisie_quittancement_pesage vérifie l'existence de quittancements
    pour ces dates/périodes.

    Args:
        request: HttpRequest (POST)
        pk: ID du quittancement pesage à supprimer

    Returns:
        Redirection vers la liste des quittancements pesage avec message de succès/erreur
    """
    user = request.user

    # =========================================
    # VÉRIFICATION PERMISSION ADMINISTRATEUR
    # =========================================
    if not is_admin_user(user):
        log_user_action(
            user,
            "ACCÈS REFUSÉ - Exécution suppression quittancement pesage",
            f"Tentative POST de suppression du quittancement pesage ID={pk} | "
            f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
            f"Permission requise: is_admin_user | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )
        messages.error(request, _("Seuls les administrateurs peuvent supprimer des quittancements."))
        return redirect('inventaire:liste_quittancements_pesage')

    # =========================================
    # RÉCUPÉRATION DU QUITTANCEMENT PESAGE
    # =========================================
    quittancement = get_object_or_404(
        QuittancementPesage.objects.select_related('station', 'saisi_par'),
        pk=pk
    )

    # =========================================
    # CAPTURE DES INFORMATIONS AVANT SUPPRESSION
    # =========================================
    numero_quittance = quittancement.numero_quittance
    station_nom = quittancement.station.nom
    station_id = quittancement.station.id
    montant = quittancement.montant_quittance
    montant_attendu = quittancement.montant_attendu
    ecart = quittancement.ecart
    exercice = quittancement.exercice
    mois = quittancement.mois
    type_declaration = quittancement.type_declaration
    saisi_par_nom = quittancement.saisi_par.nom_complet if quittancement.saisi_par else "N/A"
    date_saisie = quittancement.date_saisie

    # Déterminer les jours libérés
    if type_declaration == 'journaliere':
        date_recette = quittancement.date_recette
        periode_str = f"Jour: {date_recette.strftime('%d/%m/%Y')}" if date_recette else "N/A"
        jours_liberes_str = date_recette.strftime('%d/%m/%Y') if date_recette else "Aucun"
        nombre_jours = 1 if date_recette else 0
    else:  # decade
        date_debut = quittancement.date_debut_decade
        date_fin = quittancement.date_fin_decade
        if date_debut and date_fin:
            periode_str = f"Décade: {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"
            nombre_jours = (date_fin - date_debut).days + 1
            jours_liberes_str = f"{date_debut.strftime('%d/%m/%Y')} à {date_fin.strftime('%d/%m/%Y')} ({nombre_jours} jours)"
        else:
            periode_str = "Décade: dates non définies"
            jours_liberes_str = "Aucun"
            nombre_jours = 0

    # =========================================
    # SUPPRESSION DE L'IMAGE SI EXISTANTE
    # =========================================
    image_supprimee = False
    if quittancement.image_quittance:
        try:
            # Supprimer le fichier physique
            if quittancement.image_quittance.name:
                from django.core.files.storage import default_storage
                if default_storage.exists(quittancement.image_quittance.name):
                    default_storage.delete(quittancement.image_quittance.name)
                    image_supprimee = True
        except Exception as e:
            logger.warning(f"Erreur suppression image quittancement pesage {pk}: {e}")

    # =========================================
    # SUPPRESSION DU QUITTANCEMENT
    # =========================================
    try:
        quittancement.delete()

        # Log détaillé de la suppression réussie
        log_user_action(
            user,
            "SUPPRESSION QUITTANCEMENT PESAGE",
            f"N°{numero_quittance} SUPPRIMÉ | "
            f"Station: {station_nom} (ID={station_id}) | "
            f"Montant quittancé: {montant} FCFA | "
            f"Montant attendu: {montant_attendu or 'N/A'} FCFA | "
            f"Écart: {ecart or 'N/A'} FCFA | "
            f"Exercice: {exercice} | Mois: {mois} | "
            f"Type: {type_declaration} | "
            f"Période libérée: {periode_str} | "
            f"Jours libérés: {jours_liberes_str} | "
            f"Saisi initialement par: {saisi_par_nom} le {date_saisie.strftime('%d/%m/%Y %H:%M') if date_saisie else 'N/A'} | "
            f"Image supprimée: {'Oui' if image_supprimee else 'Non'} | "
            f"Supprimé par: {user.nom_complet if hasattr(user, 'nom_complet') else user.username} | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )

        messages.success(
            request,
            f"✅ Quittancement pesage N°{numero_quittance} supprimé avec succès. "
            f"{nombre_jours} jour(s) libéré(s) pour la station {station_nom}."
        )

    except Exception as e:
        log_user_action(
            user,
            "ERREUR - Suppression quittancement pesage",
            f"Échec suppression N°{numero_quittance} | "
            f"Station: {station_nom} | "
            f"Erreur: {str(e)} | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )
        logger.error(f"Erreur suppression quittancement pesage {pk}: {e}", exc_info=True)
        messages.error(request, f"❌ Erreur lors de la suppression: {str(e)}")

    return redirect('inventaire:liste_quittancements_pesage')

# ===================================================================
# DÉTAILS QUITTANCEMENTS PÉRIODE
#
# AVANT: regisseur, chef_station + admin
# APRÈS: Permission 'peut_voir_liste_quittancements_pesage'
# ===================================================================

@login_required
def detail_quittancements_periode_pesage(request, station_id, date_debut, date_fin):
    """
    Affiche les détails des quittancements et amendes payées pour une période.

    PERMISSION: peut_voir_liste_quittancements_pesage
    """
    user = request.user

    # Vérifier la permission granulaire
    if not has_permission(user, 'peut_voir_liste_quittancements_pesage'):
        logger.warning(
            f"Accès refusé detail_quittancements_periode_pesage | User: {user.username} | "
            f"Permission peut_voir_liste_quittancements_pesage: {getattr(user, 'peut_voir_liste_quittancements_pesage', False)}"
        )
        messages.error(request, _("Accès non autorisé."))
        return redirect('inventaire:liste_amendes')

    station = get_object_or_404(Poste, id=station_id, type='pesage')

    # Parser les dates
    try:
        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, "Format de date invalide")
        return redirect('inventaire:comptabilisation_quittancements_pesage')

    # Récupérer les quittancements de la période
    quittancements = QuittancementPesage.objects.filter(station=station).filter(
        Q(type_declaration='journaliere', date_recette__range=[date_debut_obj, date_fin_obj]) |
        Q(type_declaration='decade', date_debut_decade__lte=date_fin_obj, date_fin_decade__gte=date_debut_obj)
    ).select_related('saisi_par').order_by('date_quittancement')

    # Récupérer les amendes payées de la période
    amendes_payees = AmendeEmise.objects.filter(
        station=station,
        statut='paye',
        date_paiement__date__gte=date_debut_obj,
        date_paiement__date__lte=date_fin_obj
    ).select_related('saisi_par', 'valide_par').order_by('date_paiement')

    # Totaux
    total_quittance = quittancements.aggregate(Sum('montant_quittance'))['montant_quittance__sum'] or Decimal('0')
    total_amendes = amendes_payees.aggregate(Sum('montant_amende'))['montant_amende__sum'] or Decimal('0')
    ecart = total_quittance - total_amendes

    # Vérifier si une justification existe
    justification = JustificationEcartPesage.objects.filter(
        station=station,
        date_debut=date_debut_obj,
        date_fin=date_fin_obj
    ).first()

    logger.info(
        f"Détail quittancements période | User: {user.username} | "
        f"Station: {station.nom} | Période: {date_debut_obj} - {date_fin_obj}"
    )

    context = {
        'station': station,
        'date_debut': date_debut_obj,
        'date_fin': date_fin_obj,
        'quittancements': quittancements,
        'amendes_payees': amendes_payees,
        'total_quittance': total_quittance,
        'total_amendes': total_amendes,
        'ecart': ecart,
        'justification': justification,
        'is_admin': is_admin_user(user),
        'title': _(f'Détail Quittancements - {station.nom}'),
    }
    return render(request, 'pesage/detail_quittancements_periode_pesage.html', context)


# ===================================================================
# EXPORT EXCEL QUITTANCEMENTS
#
# AVANT: @quittancement_pesage_required (regisseur + admin)
# APRÈS: Permission 'peut_comptabiliser_quittances_pesage'
# ===================================================================

@login_required
def export_quittancements_pesage(request):
    """
    Export Excel des quittancements pesage.

    PERMISSION: peut_comptabiliser_quittances_pesage
    """
    user = request.user

    # Vérifier la permission granulaire
    if not has_permission(user, 'peut_comptabiliser_quittances_pesage'):
        logger.warning(
            f"Accès refusé export_quittancements_pesage | User: {user.username} | "
            f"Permission peut_comptabiliser_quittances_pesage: {getattr(user, 'peut_comptabiliser_quittances_pesage', False)}"
        )
        messages.error(request, _("Vous n'avez pas la permission d'exporter les quittancements."))
        return redirect('inventaire:liste_quittancements_pesage')

    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    except ImportError:
        messages.error(request, _("Module openpyxl non installé."))
        return redirect('inventaire:liste_quittancements_pesage')

    # Filtres
    station_id = request.GET.get('station')
    exercice = request.GET.get('exercice')
    mois = request.GET.get('mois')

    # Construire le queryset
    quittancements = QuittancementPesage.objects.all()
    if station_id:
        quittancements = quittancements.filter(station_id=station_id)
    if exercice:
        quittancements = quittancements.filter(exercice=exercice)
    if mois:
        quittancements = quittancements.filter(mois=mois)

    quittancements = quittancements.select_related('station', 'saisi_par').order_by('-date_quittancement')

    # Créer le workbook Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Quittancements Pesage"

    # Styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="C0392B", end_color="C0392B", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    # En-têtes
    headers = ['N° Quittance', 'Station', 'Exercice', 'Mois', 'Type', 'Date Quittancement',
               'Période', 'Montant Quittancé', 'Saisi par']

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border

    # Données
    for row, q in enumerate(quittancements, 2):
        if q.type_declaration == 'journaliere':
            periode = q.date_recette.strftime('%d/%m/%Y') if q.date_recette else ''
        else:
            if q.date_debut_decade and q.date_fin_decade:
                periode = f"{q.date_debut_decade.strftime('%d/%m/%Y')} - {q.date_fin_decade.strftime('%d/%m/%Y')}"
            else:
                periode = ''

        ws.cell(row=row, column=1, value=q.numero_quittance).border = thin_border
        ws.cell(row=row, column=2, value=q.station.nom).border = thin_border
        ws.cell(row=row, column=3, value=q.exercice).border = thin_border
        ws.cell(row=row, column=4, value=q.mois).border = thin_border
        ws.cell(row=row, column=5, value=q.get_type_declaration_display()).border = thin_border
        ws.cell(row=row, column=6, value=q.date_quittancement.strftime('%d/%m/%Y')).border = thin_border
        ws.cell(row=row, column=7, value=periode).border = thin_border
        ws.cell(row=row, column=8, value=float(q.montant_quittance)).border = thin_border
        ws.cell(row=row, column=9, value=q.saisi_par.nom_complet if q.saisi_par else '').border = thin_border

    # Ajuster les largeurs de colonnes
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 18

    # Préparer la réponse HTTP
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=quittancements_pesage_{timezone.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    wb.save(response)

    log_user_action(
        user,
        "Export Excel quittancements pesage",
        f"Nombre: {quittancements.count()}",
        request
    )

    logger.info(
        f"Export quittancements pesage | User: {user.username} | "
        f"Nombre: {quittancements.count()}"
    )

    return response


# ===================================================================
# STATISTIQUES PESAGE
# Permission: peut_voir_stats_pesage
# ===================================================================

@login_required
def statistiques_pesage(request):
    """
    Statistiques détaillées du pesage.
    Permission: peut_voir_stats_pesage
    """
    user = request.user

    # Vérifier la permission
    if not has_permission(user, 'peut_voir_stats_pesage'):
        log_user_action(
            user,
            "Statistiques pesage - permission refusée",
            "Permission peut_voir_stats_pesage manquante",
            request
        )
        messages.error(request, _("Vous n'avez pas la permission de voir les statistiques."))
        return redirect('common:dashboard')

    stations_accessibles = get_stations_pesage_accessibles(user)
    today = timezone.now().date()

    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response

    periode = request.GET.get('periode', 'mois')
    date_debut, date_fin = get_periode_dates(periode, today)

    stats = {
        'emissions': 0,
        'hors_gabarit': 0,
        'surcharges': 0,
        'delit_fuite': 0,
        'montant_emis': Decimal('0'),
        'montant_recouvre': Decimal('0'),
        'reste_a_recouvrer': Decimal('0'),
        'nombre_pesees': 0,
        'taux_recouvrement': 0,
    }

    # Construction du queryset
    if station:
        amendes = AmendeEmise.objects.filter(
            station=station,
            date_heure_emission__date__gte=date_debut,
            date_heure_emission__date__lte=date_fin
        )
    elif user_has_acces_tous_postes(user):
        amendes = AmendeEmise.objects.filter(
            date_heure_emission__date__gte=date_debut,
            date_heure_emission__date__lte=date_fin
        )
    else:
        amendes = AmendeEmise.objects.none()

    if amendes.exists():
        agg = amendes.aggregate(
            count=Count('id'),
            hg_count=Count('id', filter=Q(est_hors_gabarit=True)),
            surcharge_count=Count('id', filter=Q(est_surcharge=True)),
            df_count=Count('id', filter=Q(est_delit_fuite=True)),
            montant_emis=Sum('montant_amende'),
            montant_recouvre=Sum('montant_amende', filter=Q(statut='paye'))
        )
        stats['emissions'] = agg['count'] or 0
        stats['hors_gabarit'] = agg['hg_count'] or 0
        stats['surcharges'] = agg['surcharge_count'] or 0
        stats['delit_fuite'] = agg['df_count'] or 0
        stats['montant_emis'] = agg['montant_emis'] or Decimal('0')
        stats['montant_recouvre'] = agg['montant_recouvre'] or Decimal('0')
        stats['reste_a_recouvrer'] = stats['montant_emis'] - stats['montant_recouvre']
        if stats['montant_emis'] > 0:
            stats['taux_recouvrement'] = round(
                (float(stats['montant_recouvre']) / float(stats['montant_emis'])) * 100, 2)
    # Pesées
    if station:
        pesees_qs = PeseesJournalieres.objects.filter(
            station=station,
            date__gte=date_debut,
            date__lte=date_fin
        )
    elif user_has_acces_tous_postes(user):
        pesees_qs = PeseesJournalieres.objects.filter(
            date__gte=date_debut,
            date__lte=date_fin
        )
    else:
        pesees_qs = PeseesJournalieres.objects.none()

    stats['nombre_pesees'] = pesees_qs.aggregate(total=Sum('nombre_pesees'))['total'] or 0

    context = {
        'stats': stats,
        'station': station,
        'stations_accessibles': stations_accessibles,
        'periode': periode,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'is_admin': is_admin_user(user),
        'title': _('Statistiques Pesage'),
    }
    return render(request, 'pesage/statistiques_pesage.html', context)


# ===================================================================
# RECETTES PESAGE
# Permission: peut_voir_recettes_pesage
# ===================================================================

@login_required
def recettes_pesage(request):
    """
    Suivi des recettes pesage (amendes payées).
    Permission: peut_voir_recettes_pesage
    """
    user = request.user

    # Vérifier la permission
    if not has_permission(user, 'peut_voir_recettes_pesage'):
        log_user_action(
            user,
            "Recettes pesage - permission refusée",
            "Permission peut_voir_recettes_pesage manquante",
            request
        )
        messages.error(request, _("Accès non autorisé."))
        return redirect('inventaire:liste_amendes')

    stations_accessibles = get_stations_pesage_accessibles(user)
    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response

    periode = request.GET.get('periode', 'mois')
    date_debut_param = request.GET.get('date_debut', '')
    date_fin_param = request.GET.get('date_fin', '')
    station_filter = request.GET.get('station_filter', '')

    periodes_predefinies = ['jour', 'semaine', 'mois', 'trimestre', 'annee']

    if periode in periodes_predefinies:
        periode_info = calculer_periode_9h(periode)
    elif periode == 'personnalise' and date_debut_param and date_fin_param:
        periode_info = calculer_periode_9h('personnalise', date_debut_param, date_fin_param)
    else:
        periode = 'mois'
        periode_info = calculer_periode_9h('mois')

    datetime_debut = periode_info['datetime_debut']
    datetime_fin = periode_info['datetime_fin']
    date_debut = periode_info['date_debut']
    date_fin = periode_info['date_fin']

    # Construction du queryset
    if station is None and user_has_acces_tous_postes(user):
        queryset = AmendeEmise.objects.filter(statut='paye')
        if station_filter:
            queryset = queryset.filter(station_id=station_filter)
    elif station:
        queryset = AmendeEmise.objects.filter(station=station, statut='paye')
        station_filter = ''
    else:
        queryset = AmendeEmise.objects.none()
        station_filter = ''

    queryset = queryset.filter(
        date_paiement__gte=datetime_debut,
        date_paiement__lt=datetime_fin
    )

    stats = queryset.aggregate(
        total_recouvre=Sum('montant_amende'),
        count_paiements=Count('id')
    )

    recettes_par_jour = queryset.annotate(
        date_jour=TruncDate('date_paiement')
    ).values('date_jour').annotate(
        total=Sum('montant_amende'),
        count_paiements=Count('id')
    ).order_by('-date_jour')

    paginator = Paginator(list(recettes_par_jour), 15)
    page = request.GET.get('page')
    recettes = paginator.get_page(page)

    context = {
        'recettes': recettes,
        'station': station,
        'stations_accessibles': stations_accessibles,
        'stats': stats,
        'is_admin': is_admin_user(user),
        'periode': periode,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'station_filter': station_filter,
        'title': _('Recettes Pesage'),
    }
    return render(request, 'pesage/recettes_pesage.html', context)


# ===================================================================
# IMPRIMER RECETTE JOUR
#
# AVANT: @pesage_access_required (PESAGE_ROLES + admin)
# APRÈS: Permission 'peut_voir_recettes_pesage'
# ===================================================================

@login_required
def imprimer_recette_jour(request, date_str):
    """
    Page d'impression pour les recettes d'un jour.

    PERMISSION: peut_voir_recettes_pesage
    """
    user = request.user

    # Vérifier la permission granulaire
    if not has_permission(user, 'peut_voir_recettes_pesage'):
        logger.warning(
            f"Accès refusé imprimer_recette_jour | User: {user.username} | "
            f"Permission peut_voir_recettes_pesage: {getattr(user, 'peut_voir_recettes_pesage', False)}"
        )
        messages.error(request, _("Accès non autorisé."))
        return redirect('common:dashboard')

    # Récupérer le contexte de station
    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response

    # Parser la date
    try:
        date_cible = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, _("Format de date invalide."))
        return redirect('inventaire:recettes_pesage')

    # Calculer datetime 9h-9h pour ce jour
    datetime_debut = CAMEROUN_TZ.localize(datetime.combine(date_cible, HEURE_DEBUT_JOURNEE))
    datetime_fin = CAMEROUN_TZ.localize(datetime.combine(date_cible + timedelta(days=1), HEURE_FIN_JOURNEE))

    # Récupérer les paiements du jour
    if station is None and user_has_acces_tous_postes(user):
        queryset = AmendeEmise.objects.filter(statut='paye')
        station_filter = request.GET.get('station')
        if station_filter:
            queryset = queryset.filter(station_id=station_filter)
            try:
                station_obj = Poste.objects.get(pk=station_filter)
            except Poste.DoesNotExist:
                station_obj = None
        else:
            station_obj = None
    elif station:
        queryset = AmendeEmise.objects.filter(station=station, statut='paye')
        station_obj = station
    else:
        queryset = AmendeEmise.objects.none()
        station_obj = None

    paiements = queryset.filter(
        date_paiement__gte=datetime_debut,
        date_paiement__lte=datetime_fin
    ).select_related('station', 'valide_par', 'saisi_par').order_by('date_paiement')

    total = paiements.aggregate(total=Sum('montant_amende'))['total'] or 0

     # Statistiques par type d'infraction
    stats_types = []

    # Définir toutes les combinaisons possibles
    combinaisons = [
        {
            'label': 'Surcharge (S)',
            'filtre': {'est_surcharge': True, 'est_hors_gabarit': False, 'est_delit_fuite': False},
        },
        {
            'label': 'Hors Gabarit (HG)',
            'filtre': {'est_hors_gabarit': True, 'est_surcharge': False, 'est_delit_fuite': False},
        },
        {
            'label': 'Délit de Fuite (DF)',
            'filtre': {'est_delit_fuite': True, 'est_surcharge': False, 'est_hors_gabarit': False},
        },
        {
            'label': 'Surcharge + Hors Gabarit (S+HG)',
            'filtre': {'est_surcharge': True, 'est_hors_gabarit': True, 'est_delit_fuite': False},
        },
        {
            'label': 'Hors Gabarit + Délit de Fuite (HG+DF)',
            'filtre': {'est_hors_gabarit': True, 'est_delit_fuite': True, 'est_surcharge': False},
        },
        {
            'label': 'Surcharge + Délit de Fuite (S+DF)',
            'filtre': {'est_surcharge': True, 'est_delit_fuite': True, 'est_hors_gabarit': False},
        },
        {
            'label': 'Surcharge + HG + Délit de Fuite (S+HG+DF)',
            'filtre': {'est_surcharge': True, 'est_hors_gabarit': True, 'est_delit_fuite': True},
        },
    ]

    for combo in combinaisons:
        qs = paiements.filter(**combo['filtre'])
        if qs.exists():
            stats_types.append({
                'type': combo['label'],
                'count': qs.count(),
                'montant': qs.aggregate(m=Sum('montant_amende'))['m'] or 0
            })

    logger.info(
        f"Impression recette jour | User: {user.username} | "
        f"Date: {date_cible} | Station: {station_obj.nom if station_obj else 'Toutes'} | "
        f"Paiements: {paiements.count()} | Total: {total} FCFA"
    )

    context = {
        'paiements': paiements,
        'date': date_cible,
        'datetime_debut': datetime_debut,
        'datetime_fin': datetime_fin,
        'station': station_obj,
        'total': total,
        'count': paiements.count(),
        'stats_types': stats_types,
        'is_admin': is_admin_user(user),
        'title': f"Recettes du {date_cible.strftime('%d/%m/%Y')} (9h-9h)",
    }

    return render(request, 'pesage/imprimer_recette_jour.html', context)


# ===================================================================
# API ENDPOINTS (JSON)
# Utilisent les décorateurs API pour retourner des réponses JSON
# ===================================================================

@login_required
@require_GET
def api_check_pesees(request):
    """
    API pour vérifier si les pesées ont déjà été saisies.
    GET params: date (YYYY-MM-DD), station (ID)
    """
    date_str = request.GET.get('date')
    station_id = request.GET.get('station')

    if not date_str or not station_id:
        return JsonResponse({'error': 'Paramètres date et station requis'}, status=400)

    try:
        date_cible = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Format de date invalide'}, status=400)

    try:
        station = Poste.objects.get(pk=station_id, type='pesage')
    except Poste.DoesNotExist:
        return JsonResponse({'error': 'Station non trouvée'}, status=404)

    # Vérifier l'accès à la station
    if not check_poste_access(request.user, station):
        return JsonResponse({'error': 'Accès non autorisé à cette station'}, status=403)

    pesee = PeseesJournalieres.objects.filter(station=station, date=date_cible).first()

    if pesee:
        return JsonResponse({
            'deja_saisi': True,
            'nombre_pesees': pesee.nombre_pesees,
            'date': date_cible.strftime('%d/%m/%Y'),
            'saisi_par': pesee.saisi_par.nom_complet if pesee.saisi_par else None
        })

    return JsonResponse({
        'deja_saisi': False,
        'date': date_cible.strftime('%d/%m/%Y')
    })


@login_required
@require_GET
def api_montant_attendu(request):
    """
    API pour calculer le montant attendu pour un quittancement.
    GET params: station, date_debut, date_fin (YYYY-MM-DD)
    """
    station_id = request.GET.get('station')
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')

    if not all([station_id, date_debut_str, date_fin_str]):
        return JsonResponse({'error': 'Paramètres requis'}, status=400)

    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Format date invalide'}, status=400)

    try:
        station = Poste.objects.get(pk=station_id, type='pesage')
    except Poste.DoesNotExist:
        return JsonResponse({'error': 'Station non trouvée'}, status=404)

    # Vérifier l'accès
    if not check_poste_access(request.user, station):
        return JsonResponse({'error': 'Accès non autorisé'}, status=403)

    paiements = AmendeEmise.objects.filter(
        station=station,
        statut='paye',
        date_paiement__date__gte=date_debut,
        date_paiement__date__lte=date_fin
    )

    agg = paiements.aggregate(total=Sum('montant_amende'), count=Count('id'))

    return JsonResponse({
        'montant': float(agg['total'] or 0),
        'count': agg['count'] or 0,
        'station': station.nom
    })


@login_required
@require_GET
def api_paiements_jour(request):
    """
    API pour récupérer les paiements d'un jour.

    PERMISSION: peut_voir_recettes_pesage
    """
    user = request.user

    # Vérifier la permission granulaire
    if not has_permission(user, 'peut_voir_recettes_pesage'):
        logger.warning(
            f"Accès refusé api_paiements_jour | User: {user.username} | "
            f"Permission peut_voir_recettes_pesage: {getattr(user, 'peut_voir_recettes_pesage', False)}"
        )
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    station, _redirect = get_station_context(request, user)

    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Date requise'}, status=400)

    try:
        date_cible = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Format date invalide'}, status=400)

    if station is None and user_has_acces_tous_postes(user):
        queryset = AmendeEmise.objects.filter(statut='paye')
        station_filter = request.GET.get('station')
        if station_filter:
            queryset = queryset.filter(station_id=station_filter)
    elif station:
        queryset = AmendeEmise.objects.filter(station=station, statut='paye')
    else:
        queryset = AmendeEmise.objects.none()

    paiements = queryset.filter(date_paiement__date=date_cible).select_related('valide_par')

    data = {
        'date': date_cible.strftime('%d/%m/%Y'),
        'paiements': [{
            'id': p.pk,
            'numero_ticket': p.numero_ticket,
            'immatriculation': p.immatriculation,
            'transporteur': p.transporteur or '-',
            'montant': float(p.montant_amende),
            'heure': p.date_paiement.strftime('%H:%M') if p.date_paiement else '-',
        } for p in paiements],
        'total': float(paiements.aggregate(Sum('montant_amende'))['montant_amende__sum'] or 0),
        'count': paiements.count(),
    }

    return JsonResponse(data)


@login_required
@require_GET
def api_recherche_amende(request):
    """
    API de recherche rapide d'amende.

    PERMISSION: peut_lister_amendes
    """
    user = request.user

    # Vérifier la permission granulaire
    if not has_permission(user, 'peut_lister_amendes'):
        logger.warning(
            f"Accès refusé api_recherche_amende | User: {user.username} | "
            f"Permission peut_lister_amendes: {getattr(user, 'peut_lister_amendes', False)}"
        )
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    station, _redirect = get_station_context(request, user)

    query = request.GET.get('q', '').strip()

    if len(query) < 2:
        return JsonResponse({'results': []})

    if station is None and user_has_acces_tous_postes(user):
        amendes = AmendeEmise.objects.all()
    elif station:
        amendes = AmendeEmise.objects.filter(station=station)
    else:
        amendes = AmendeEmise.objects.none()

    amendes = amendes.filter(
        Q(numero_ticket__icontains=query) |
        Q(immatriculation__icontains=query) |
        Q(transporteur__icontains=query)
    ).select_related('station')[:10]

    results = [{
        'id': a.pk,
        'numero_ticket': a.numero_ticket,
        'immatriculation': a.immatriculation,
        'montant': float(a.montant_amende),
        'statut': a.get_statut_display(),
        'station': a.station.nom,
    } for a in amendes]

    return JsonResponse({'results': results})


# ===================================================================
# API STATS JOUR
#
# AVANT: @pesage_access_required (PESAGE_ROLES + admin)
# APRÈS: Permission 'peut_voir_stats_pesage'
# ===================================================================

@login_required
@require_GET
def api_stats_jour(request):
    """
    API pour récupérer les statistiques d'un jour spécifique.

    PERMISSION: peut_voir_stats_pesage
    """
    user = request.user

    # Vérifier la permission granulaire
    if not has_permission(user, 'peut_voir_stats_pesage'):
        logger.warning(
            f"Accès refusé api_stats_jour | User: {user.username} | "
            f"Permission peut_voir_stats_pesage: {getattr(user, 'peut_voir_stats_pesage', False)}"
        )
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    # Récupérer le contexte de station
    station, _ = get_station_context(request, user)

    # Paramètres
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Date requise'}, status=400)

    try:
        date_cible = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Format date invalide'}, status=400)

    # Construire le queryset selon l'accès
    if station is None and user_has_acces_tous_postes(user):
        amendes = AmendeEmise.objects.filter(date_heure_emission__date=date_cible)
        station_filter = request.GET.get('station')
        if station_filter:
            amendes = amendes.filter(station_id=station_filter)
    elif station:
        amendes = AmendeEmise.objects.filter(station=station, date_heure_emission__date=date_cible)
    else:
        amendes = AmendeEmise.objects.none()

    # Calculer les statistiques
    stats = amendes.aggregate(
        count=Count('id'),
        hg_count=Count('id', filter=Q(est_hors_gabarit=True)),
        surcharge_count=Count('id', filter=Q(est_surcharge=True)),
        montant_emis=Sum('montant_amende'),
        montant_recouvre=Sum('montant_amende', filter=Q(statut='paye')),
        count_paye=Count('id', filter=Q(statut='paye')),
        count_non_paye=Count('id', filter=Q(statut='non_paye')),
    )

    montant_emis = stats['montant_emis'] or Decimal('0')
    montant_recouvre = stats['montant_recouvre'] or Decimal('0')
    reste = montant_emis - montant_recouvre
    taux_recouvrement = 0
    if montant_emis > 0:
        taux_recouvrement = round((float(montant_recouvre) / float(montant_emis)) * 100, 2)

    logger.info(
        f"API stats jour | User: {user.username} | "
        f"Date: {date_cible} | Station: {station.nom if station else 'Toutes'} | "
        f"Emissions: {stats['count'] or 0}"
    )

    return JsonResponse({
        'date': date_cible.strftime('%d/%m/%Y'),
        'emissions': stats['count'] or 0,
        'hors_gabarit': stats['hg_count'] or 0,
        'surcharge': stats['surcharge_count'] or 0,
        'montant_emis': float(montant_emis),
        'montant_recouvre': float(montant_recouvre),
        'reste_a_recouvrer': float(reste),
        'taux_recouvrement': taux_recouvrement,
        'count_paye': stats['count_paye'] or 0,
        'count_non_paye': stats['count_non_paye'] or 0,
    })


# ===================================================================
# API STATS PÉRIODE
#
# AVANT: Authentifié uniquement
# APRÈS: Permission 'peut_voir_stats_pesage'
# ===================================================================

@login_required
@require_GET
def api_stats_periode(request):
    """
    API pour récupérer les statistiques d'une période.

    PERMISSION: peut_voir_stats_pesage
    """
    user = request.user

    # Vérifier la permission granulaire
    if not has_permission(user, 'peut_voir_stats_pesage'):
        logger.warning(
            f"Accès refusé api_stats_periode | User: {user.username} | "
            f"Permission peut_voir_stats_pesage: {getattr(user, 'peut_voir_stats_pesage', False)}"
        )
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    # Paramètres
    station_id = request.GET.get('station')
    periode = request.GET.get('periode', 'mois')
    date_str = request.GET.get('date')

    # Déterminer la date de référence
    if date_str:
        try:
            date_ref = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            date_ref = timezone.now().date()
    else:
        date_ref = timezone.now().date()

    # Calculer les dates de la période
    date_debut, date_fin = get_periode_dates(periode, date_ref)

    # Construire le queryset
    amendes = AmendeEmise.objects.filter(
        date_heure_emission__date__gte=date_debut,
        date_heure_emission__date__lte=date_fin
    )

    station = None
    if station_id:
        try:
            station = Poste.objects.get(pk=station_id, type='pesage')
            amendes = amendes.filter(station=station)
        except Poste.DoesNotExist:
            return JsonResponse({'error': 'Station non trouvée'}, status=404)

    # Calculer les statistiques
    stats = amendes.aggregate(
        emissions=Count('id'),
        hors_gabarit=Count('id', filter=Q(est_hors_gabarit=True)),
        surcharge=Count('id', filter=Q(est_surcharge=True)),
        montant_emis=Sum('montant_amende'),
        montant_recouvre=Sum('montant_amende', filter=Q(statut='paye')),
        count_paye=Count('id', filter=Q(statut='paye')),
        count_non_paye=Count('id', filter=Q(statut='non_paye'))
    )

    # Pesées de la période
    pesees_qs = PeseesJournalieres.objects.filter(
        date__gte=date_debut, date__lte=date_fin
    )
    if station_id:
        pesees_qs = pesees_qs.filter(station_id=station_id)

    nombre_pesees = pesees_qs.aggregate(total=Sum('nombre_pesees'))['total'] or 0

    # Calculs finaux
    montant_emis = stats['montant_emis'] or Decimal('0')
    montant_recouvre = stats['montant_recouvre'] or Decimal('0')
    reste = montant_emis - montant_recouvre
    taux_recouvrement = 0
    if montant_emis > 0:
        taux_recouvrement = round((float(montant_recouvre) / float(montant_emis)) * 100, 2)

    logger.info(
        f"API stats période | User: {user.username} | "
        f"Période: {periode} ({date_debut} - {date_fin}) | "
        f"Station: {station.nom if station else 'Toutes'}"
    )

    return JsonResponse({
        'periode': periode,
        'date_debut': date_debut.strftime('%d/%m/%Y'),
        'date_fin': date_fin.strftime('%d/%m/%Y'),
        'emissions': stats['emissions'] or 0,
        'hors_gabarit': stats['hors_gabarit'] or 0,
        'surcharge': stats['surcharge'] or 0,
        'montant_emis': float(montant_emis),
        'montant_recouvre': float(montant_recouvre),
        'reste_a_recouvrer': float(reste),
        'taux_recouvrement': taux_recouvrement,
        'count_paye': stats['count_paye'] or 0,
        'count_non_paye': stats['count_non_paye'] or 0,
        'nombre_pesees': nombre_pesees,
        'station': station.nom if station else None,
    })


@login_required
@require_http_methods(["GET", "POST"])
def modifier_amende(request, pk):
    """
    Modification d'une amende par un administrateur.

    LOGIQUE MÉTIER CRITIQUE:
    ========================
    1. Si l'amende est déjà payée (statut='paye'):
       - Le statut est remis à 'non_paye'
       - Le montant est "retiré" des recettes (via le changement de statut)
       - La date_paiement_originale est conservée
       - Le régisseur devra revalider le paiement
       - Lors de la revalidation, la recette sera comptabilisée à la date_paiement_originale

    2. La traçabilité est complète:
       - date_derniere_modification
       - modifie_par
       - ancien_statut_avant_modification
       - ancien_montant_valide

    Permission: Administrateurs uniquement (is_admin_user)
    """
    user = request.user

    # ===================================================================
    # VÉRIFICATION ADMIN STRICTE
    # ===================================================================
    if not is_admin_user(user):
        log_user_action(
            user,
            "MODIFICATION AMENDE - ACCÈS REFUSÉ",
            f"Tentative de modification amende ID {pk} sans droits administrateur | "
            f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )
        messages.error(request, _("❌ Accès réservé aux administrateurs."))
        return redirect('inventaire:liste_amendes')

    # ===================================================================
    # RÉCUPÉRATION DE L'AMENDE
    # ===================================================================
    amende = get_object_or_404(AmendeEmise, pk=pk)
    station = amende.station

    # Sauvegarder les valeurs originales AVANT modification
    ancien_statut = amende.statut
    ancien_montant = amende.montant_amende
    ancienne_immatriculation = amende.immatriculation
    ancien_transporteur = amende.transporteur
    etait_payee = (ancien_statut == 'paye')

    # Log de l'accès à la page de modification
    log_user_action(
        user,
        "MODIFICATION AMENDE - ACCÈS PAGE",
        f"Amende N°{amende.numero_ticket} | Station: {station.nom} | "
        f"Statut actuel: {ancien_statut} | Montant: {ancien_montant} FCFA | "
        f"Était payée: {'OUI' if etait_payee else 'NON'}",
        request
    )

    # ===================================================================
    # TRAITEMENT DU FORMULAIRE POST
    # ===================================================================
    if request.method == 'POST':
        form = AmendeEmiseForm(request.POST, instance=amende)

        if form.is_valid():
            try:
                with transaction.atomic():
                    amende_modifiee = form.save(commit=False)

                    # ===============================================
                    # LOGIQUE MÉTIER CRITIQUE: AMENDE DÉJÀ PAYÉE
                    # ===============================================
                    if etait_payee:
                        # 1. Sauvegarder l'ancien statut et montant
                        amende_modifiee.ancien_statut_avant_modification = ancien_statut
                        amende_modifiee.ancien_montant_valide = ancien_montant

                        # 2. Conserver la date de paiement originale
                        if amende.date_paiement and not amende.date_paiement_originale:
                            amende_modifiee.date_paiement_originale = amende.date_paiement
                        elif amende.date_paiement_originale:
                            # Garder la date originale si elle existe déjà
                            pass
                        else:
                            amende_modifiee.date_paiement_originale = amende.date_paiement

                        # 3. Remettre le statut à non_paye
                        amende_modifiee.statut = 'non_paye'

                        # 4. NE PAS effacer date_paiement (pour conserver l'historique)
                        # La recette sera comptabilisée à cette date lors de la revalidation

                        # 5. NE PAS effacer valide_par (pour l'historique)

                    # ===============================================
                    # TRAÇABILITÉ DE LA MODIFICATION
                    # ===============================================
                    amende_modifiee.date_derniere_modification = timezone.now()
                    amende_modifiee.modifie_par = user

                    # Sauvegarder
                    amende_modifiee.save()

                    # ===============================================
                    # LOGGING DÉTAILLÉ
                    # ===============================================
                    modifications = []

                    if amende_modifiee.montant_amende != ancien_montant:
                        modifications.append(f"Montant: {ancien_montant} → {amende_modifiee.montant_amende} FCFA")

                    if amende_modifiee.immatriculation != ancienne_immatriculation:
                        modifications.append(f"Immat: {ancienne_immatriculation} → {amende_modifiee.immatriculation}")

                    if amende_modifiee.transporteur != ancien_transporteur:
                        modifications.append(f"Transporteur: {ancien_transporteur} → {amende_modifiee.transporteur}")

                    if etait_payee:
                        modifications.append(f"⚠️ STATUT RÉINITIALISÉ: {ancien_statut} → non_paye")
                        modifications.append(f"💰 MONTANT RETIRÉ DES RECETTES: {ancien_montant} FCFA")
                        modifications.append(f"📅 Date paiement originale conservée: {amende_modifiee.date_paiement_originale}")

                    details_log = (
                        f"Amende N°{amende.numero_ticket} modifiée | "
                        f"Station: {station.nom} | "
                        f"Modifications: {' | '.join(modifications) if modifications else 'Aucune modification majeure'}"
                    )

                    log_user_action(
                        user,
                        "MODIFICATION AMENDE - SUCCÈS",
                        details_log,
                        request
                    )

                    # ===============================================
                    # CRÉER UN ÉVÉNEMENT DE MODIFICATION (Event Sourcing)
                    # ===============================================
                    try:
                        AmendeEvent.objects.create(
                            amende=amende_modifiee,
                            event_type='MODIFICATION',
                            event_datetime=timezone.now(),
                            montant=amende_modifiee.montant_amende,
                            effectue_par=user,
                            metadata={
                                'action': 'modification_admin',
                                'ancien_statut': ancien_statut,
                                'nouveau_statut': amende_modifiee.statut,
                                'ancien_montant': str(ancien_montant),
                                'nouveau_montant': str(amende_modifiee.montant_amende),
                                'modifications': modifications,
                                'etait_payee': etait_payee,
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Erreur création AmendeEvent: {e}")

                    # ===============================================
                    # MESSAGES DE SUCCÈS
                    # ===============================================
                    if etait_payee:
                        messages.warning(request, _(
                            "⚠️ ATTENTION: L'amende %(numero)s a été modifiée. "
                            "Le statut a été remis à 'Non payé' et le montant de %(montant)s FCFA "
                            "a été retiré des recettes. Le régisseur devra revalider le paiement. "
                            "La recette sera alors comptabilisée à la date du %(date)s."
                        ) % {
                            'numero': amende.numero_ticket,
                            'montant': f"{ancien_montant:,.0f}".replace(',', ' '),
                            'date': amende_modifiee.date_paiement_originale.strftime('%d/%m/%Y') if amende_modifiee.date_paiement_originale else 'N/A'
                        })
                    else:
                        messages.success(request, _(
                            "✅ Amende %(numero)s modifiée avec succès."
                        ) % {'numero': amende.numero_ticket})

                    return redirect('inventaire:detail_amende', pk=amende.pk)

            except Exception as e:
                logger.error(f"Erreur modification amende {pk}: {e}", exc_info=True)
                log_user_action(
                    user,
                    "MODIFICATION AMENDE - ERREUR",
                    f"Amende N°{amende.numero_ticket} | Erreur: {str(e)}",
                    request
                )
                messages.error(request, _("❌ Erreur lors de la modification: %(error)s") % {'error': str(e)})
        else:
            # Erreurs de validation du formulaire
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"❌ {field}: {error}")
    else:
        form = AmendeEmiseForm(instance=amende)

    # ===================================================================
    # CONTEXTE DU TEMPLATE
    # ===================================================================
    context = {
        'form': form,
        'amende': amende,
        'station': station,
        'is_admin': True,
        'title': f"Modifier amende {amende.numero_ticket}",
        'etait_payee': etait_payee,
        'ancien_statut': ancien_statut,
        'ancien_montant': ancien_montant,
    }

    return render(request, 'pesage/modifier_amende.html', context)


# ===================================================================
# VUE: MODIFICATION DES PESÉES JOURNALIÈRES (ADMIN UNIQUEMENT)
# ===================================================================

@login_required
@require_http_methods(["GET", "POST"])
def modifier_pesees(request, pk):
    """
    Modification du nombre de pesées journalières par un administrateur.

    LOGIQUE MÉTIER:
    ===============
    - Modification simple avec traçabilité complète
    - Sauvegarde de l'ancienne valeur
    - Logging détaillé de l'action

    Permission: Administrateurs uniquement (is_admin_user)

    CORRECTION v2.1:
    ================
    - Ajout validation défensive sur pesee.date (peut être None)
    - Formatage sécurisé des dates pour éviter AttributeError
    """
    user = request.user

    # ===================================================================
    # VÉRIFICATION ADMIN STRICTE
    # ===================================================================
    if not is_admin_user(user):
        log_user_action(
            user,
            "MODIFICATION PESÉES - ACCÈS REFUSÉ",
            f"Tentative de modification pesées ID {pk} sans droits administrateur | "
            f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )
        messages.error(request, _("❌ Accès réservé aux administrateurs."))
        return redirect('inventaire:historique_pesees')

    # ===================================================================
    # RÉCUPÉRATION DE LA PESÉE
    # ===================================================================
    pesee = get_object_or_404(PeseesJournalieres, pk=pk)
    station = pesee.station

    # Sauvegarder les valeurs originales
    ancien_nombre = pesee.nombre_pesees
    date_pesee = pesee.date

    # ===================================================================
    # VALIDATION DÉFENSIVE : VÉRIFIER QUE LA DATE N'EST PAS NULL
    # ===================================================================
    if date_pesee is None:
        # Log de l'anomalie détectée
        log_user_action(
            user,
            "MODIFICATION PESÉES - ANOMALIE DONNÉES",
            f"Pesées ID {pk} avec date NULL détectée | "
            f"Station: {station.nom if station else 'N/A'} | "
            f"Nombre pesées: {ancien_nombre} | "
            f"Action: Modification refusée - données corrompues | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )

        logger.error(
            f"[PESAGE] Anomalie: PeseesJournalieres pk={pk} a date=NULL. "
            f"Station: {station.nom if station else 'N/A'}. "
            f"Utilisateur: {user.username}"
        )

        messages.error(
            request,
            _(
                "❌ Erreur de données : L'enregistrement des pesées (ID: %(pk)s) "
                "n'a pas de date valide. Veuillez contacter un administrateur système "
                "pour corriger cette anomalie dans la base de données."
            ) % {'pk': pk}
        )
        return redirect('inventaire:historique_pesees')

    # ===================================================================
    # FORMATAGE SÉCURISÉ DE LA DATE POUR LES LOGS ET AFFICHAGE
    # ===================================================================
    date_pesee_formatee = date_pesee.strftime('%d/%m/%Y')

    # Log de l'accès
    log_user_action(
        user,
        "MODIFICATION PESÉES - ACCÈS PAGE",
        f"Pesées du {date_pesee_formatee} | Station: {station.nom} | "
        f"Nombre actuel: {ancien_nombre}",
        request
    )

    # ===================================================================
    # TRAITEMENT DU FORMULAIRE POST
    # ===================================================================
    if request.method == 'POST':
        form = PeseesJournalieresForm(request.POST, instance=pesee)

        if form.is_valid():
            try:
                with transaction.atomic():
                    pesee_modifiee = form.save(commit=False)

                    # Sauvegarder l'ancienne valeur
                    pesee_modifiee.ancien_nombre_pesees = ancien_nombre

                    # Traçabilité
                    pesee_modifiee.date_derniere_modification = timezone.now()
                    pesee_modifiee.modifie_par = user

                    pesee_modifiee.save()

                    # Logging détaillé
                    nouveau_nombre = pesee_modifiee.nombre_pesees
                    difference = nouveau_nombre - ancien_nombre

                    log_user_action(
                        user,
                        "MODIFICATION PESÉES - SUCCÈS",
                        f"Pesées du {date_pesee_formatee} modifiées | "
                        f"Station: {station.nom} | "
                        f"Ancien nombre: {ancien_nombre} → Nouveau: {nouveau_nombre} | "
                        f"Différence: {'+' if difference > 0 else ''}{difference}",
                        request
                    )

                    messages.success(request, _(
                        "✅ Pesées du %(date)s modifiées avec succès: %(ancien)d → %(nouveau)d"
                    ) % {
                        'date': date_pesee_formatee,
                        'ancien': ancien_nombre,
                        'nouveau': nouveau_nombre
                    })

                    return redirect('inventaire:historique_pesees')

            except Exception as e:
                logger.error(f"Erreur modification pesées {pk}: {e}", exc_info=True)
                log_user_action(
                    user,
                    "MODIFICATION PESÉES - ERREUR",
                    f"Pesées du {date_pesee_formatee} | Station: {station.nom} | Erreur: {str(e)}",
                    request
                )
                messages.error(request, _("❌ Erreur lors de la modification: %(error)s") % {'error': str(e)})
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"❌ {field}: {error}")
    else:
        form = PeseesJournalieresForm(instance=pesee)

    # ===================================================================
    # CONTEXTE DU TEMPLATE
    # ===================================================================
    context = {
        'form': form,
        'pesee': pesee,
        'station': station,
        'is_admin': True,
        'title': f"Modifier pesées du {date_pesee_formatee}",
        'ancien_nombre': ancien_nombre,
    }

    return render(request, 'pesage/modifier_pesees.html', context)

@login_required
@require_http_methods(["GET"])
def confirmer_suppression_pesees(request, pk):
    """
    Affiche la page de confirmation avant suppression d'un enregistrement de pesées.

    LOGIQUE MÉTIER:
    ===============
    - Affiche les détails de la pesée à supprimer
    - Demande confirmation explicite de l'utilisateur
    - Permet d'annuler et revenir à l'historique

    Permission: Administrateurs uniquement (is_admin_user)

    Méthode: GET uniquement (affichage)

    Returns:
        Template de confirmation avec les détails de la pesée
    """
    user = request.user

    # ===================================================================
    # VÉRIFICATION ADMIN STRICTE
    # ===================================================================
    if not is_admin_user(user):
        log_user_action(
            user,
            "SUPPRESSION PESÉES - ACCÈS CONFIRMATION REFUSÉ",
            f"Tentative d'accès à la confirmation de suppression pesées ID {pk} sans droits administrateur | "
            f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )
        messages.error(request, _("❌ Accès réservé aux administrateurs."))
        return redirect('inventaire:historique_pesees')

    # ===================================================================
    # RÉCUPÉRATION DE LA PESÉE
    # ===================================================================
    pesee = get_object_or_404(PeseesJournalieres, pk=pk)
    station = pesee.station

    # ===================================================================
    # LOG DE L'ACCÈS À LA PAGE DE CONFIRMATION
    # ===================================================================
    # Gestion défensive de la date (peut être None)
    if pesee.date:
        date_pesee_str = pesee.date.strftime('%d/%m/%Y')
    else:
        date_pesee_str = "Date non définie"

    log_user_action(
        user,
        "SUPPRESSION PESÉES - ACCÈS CONFIRMATION",
        f"Accès page de confirmation suppression | "
        f"Pesées ID {pk} | Station: {station.nom if station else 'N/A'} | "
        f"Date: {date_pesee_str} | Nombre: {pesee.nombre_pesees} | "
        f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
        request
    )

    # ===================================================================
    # CONTEXTE DU TEMPLATE
    # ===================================================================
    context = {
        'pesee': pesee,
        'station': station,
        'title': f"Confirmer la suppression - Pesées du {date_pesee_str}",
        'date_pesee_str': date_pesee_str,
    }

    return render(request, 'pesage/confirmer_suppression_pesees.html', context)


# ===================================================================
# VUE: SUPPRESSION DES PESÉES JOURNALIÈRES (POST - EXÉCUTE LA SUPPRESSION)
# ===================================================================

@login_required
@require_POST
def supprimer_pesees(request, pk):
    """
    Suppression effective d'un enregistrement de pesées journalières.

    LOGIQUE MÉTIER:
    ===============
    - Exécute la suppression après confirmation
    - Traçabilité complète avant suppression
    - Logging détaillé de l'action
    - Validation défensive sur les données

    Permission: Administrateurs uniquement (is_admin_user)

    Méthode: POST uniquement (sécurité CSRF)

    Returns:
        Redirect vers historique_pesees avec message de confirmation
    """
    user = request.user

    # ===================================================================
    # VÉRIFICATION ADMIN STRICTE
    # ===================================================================
    if not is_admin_user(user):
        log_user_action(
            user,
            "SUPPRESSION PESÉES - ACCÈS REFUSÉ",
            f"Tentative de suppression pesées ID {pk} sans droits administrateur | "
            f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )
        messages.error(request, _("❌ Accès réservé aux administrateurs."))
        return redirect('inventaire:historique_pesees')

    # ===================================================================
    # RÉCUPÉRATION DE LA PESÉE
    # ===================================================================
    pesee = get_object_or_404(PeseesJournalieres, pk=pk)

    # ===================================================================
    # SAUVEGARDE DES INFORMATIONS AVANT SUPPRESSION (pour les logs)
    # ===================================================================
    pesee_id = pesee.pk
    station_nom = pesee.station.nom if pesee.station else "Station inconnue"
    station_id = pesee.station.id if pesee.station else None
    nombre_pesees = pesee.nombre_pesees
    saisi_par_nom = pesee.saisi_par.nom_complet if pesee.saisi_par else "Utilisateur inconnu"
    saisi_par_id = pesee.saisi_par.id if pesee.saisi_par else None
    date_saisie = pesee.date_saisie
    observations = pesee.observations or "Aucune"

    # Gestion défensive de la date (peut être None selon l'erreur initiale)
    if pesee.date:
        date_pesee_str = pesee.date.strftime('%d/%m/%Y')
        date_pesee_jour = pesee.date.strftime('%A %d %B %Y')
    else:
        date_pesee_str = "Date non définie"
        date_pesee_jour = "Date non définie"
        logger.warning(
            f"[PESAGE] Suppression pesée ID {pk} avec date=NULL. "
            f"Station: {station_nom}. Utilisateur: {user.username}"
        )

    # ===================================================================
    # LOG DÉTAILLÉ AVANT SUPPRESSION
    # ===================================================================
    log_user_action(
        user,
        "SUPPRESSION PESÉES - EXÉCUTION",
        f"Suppression pesées ID {pesee_id} | "
        f"Station: {station_nom} (ID: {station_id}) | "
        f"Date: {date_pesee_str} | "
        f"Nombre pesées supprimées: {nombre_pesees} | "
        f"Initialement saisi par: {saisi_par_nom} (ID: {saisi_par_id}) | "
        f"Date saisie originale: {date_saisie.strftime('%d/%m/%Y %H:%M') if date_saisie else 'N/A'} | "
        f"Observations: {observations[:100]}... | "
        f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
        request
    )

    # ===================================================================
    # SUPPRESSION
    # ===================================================================
    try:
        pesee.delete()

        # Log de succès
        logger.info(
            f"[PESAGE] Pesées supprimées avec succès | "
            f"ID: {pesee_id} | Station: {station_nom} | "
            f"Date: {date_pesee_str} | Nombre: {nombre_pesees} | "
            f"Par: {user.username}"
        )

        messages.success(
            request,
            _(
                "✅ Pesées du %(date)s supprimées avec succès. "
                "%(nombre)d pesée(s) retirée(s) pour la station %(station)s."
            ) % {
                'date': date_pesee_str,
                'nombre': nombre_pesees,
                'station': station_nom
            }
        )

    except Exception as e:
        # Log d'erreur
        logger.error(
            f"[PESAGE] Erreur suppression pesées ID {pesee_id}: {e}",
            exc_info=True
        )

        log_user_action(
            user,
            "SUPPRESSION PESÉES - ERREUR",
            f"Échec suppression pesées ID {pesee_id} | "
            f"Station: {station_nom} | Date: {date_pesee_str} | "
            f"Erreur: {str(e)} | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )

        messages.error(
            request,
            _("❌ Erreur lors de la suppression: %(error)s") % {'error': str(e)}
        )

    return redirect('inventaire:historique_pesees')

@login_required
def importer_amendes(request):
    """
    Import en masse des amendes depuis un fichier Excel.

    Permission: peut_saisir_amende

    Format attendu du fichier Excel:
    A: *Numéro ticket
    B: *Immatriculation
    C: *Nom du transporteur
    D: Opérateur/chauffeur (0 si non renseigné)
    E: *Ville de provenance
    F: *Ville de destination
    G: *Produit transporté
    H: *Nature de l'infraction (S, HG, DF, S+HG, HG+DF, S+DF, S+HG+DF)
    I: *Montant
    J: Observations
    """
    user = request.user

    # Vérifier la permission spécifique
    if not has_permission(user, 'peut_saisir_amende'):
        log_user_action(
            user,
            "Import amendes - permission refusée",
            f"Permission peut_saisir_amende manquante",
            request
        )
        messages.error(request, _("Vous n'avez pas la permission d'importer des amendes."))
        return redirect('inventaire:liste_amendes')

    # Déterminer la station
    station, redirect_response = get_station_context(request, user)

    # Si utilisateur multi-postes sans station sélectionnée → rediriger vers sélection
    if user_has_acces_tous_postes(user) and station is None:
        return redirect(f"{reverse('inventaire:selectionner_station')}?action=importer_amendes")

    if redirect_response:
        return redirect_response

    resultats = None
    erreurs_import = []
    amendes_importees = 0

    if request.method == 'POST':
        from .forms_pesage import ImportAmendesForm
        form = ImportAmendesForm(request.POST, request.FILES)

        if form.is_valid():
            fichier = request.FILES['fichier_excel']

            # Vérifier l'extension
            if not fichier.name.endswith(('.xlsx', '.xls')):
                messages.error(request, _("Le fichier doit être au format Excel (.xlsx ou .xls)."))
                return render(request, 'pesage/importer_amendes.html', {
                    'form': form,
                    'station': station,
                    'is_admin': is_admin_user(user),
                    'title': _('Importer des amendes'),
                })

            try:
                import openpyxl

                wb = openpyxl.load_workbook(fichier, read_only=True)
                ws = wb.active

                rows = list(ws.iter_rows(min_row=2, values_only=True))  # Skip header row

                if not rows:
                    messages.warning(request, _("Le fichier est vide ou ne contient que l'en-tête."))
                    return render(request, 'pesage/importer_amendes.html', {
                        'form': ImportAmendesForm(),
                        'station': station,
                        'is_admin': is_admin_user(user),
                        'title': _('Importer des amendes'),
                    })

                resultats = []

                for idx, row in enumerate(rows, start=2):
                    ligne_info = {'ligne': idx, 'statut': 'ok', 'erreur': '', 'data': {}}

                    # Extraire les valeurs (10 colonnes A-J)
                    try:
                        numero_ticket = str(row[0]).strip() if row[0] else ''
                        immatriculation = str(row[1]).strip() if row[1] else ''
                        transporteur = str(row[2]).strip() if row[2] else ''
                        operateur = str(row[3]).strip() if row[3] else '0'
                        provenance = str(row[4]).strip() if row[4] else ''
                        destination = str(row[5]).strip() if row[5] else ''
                        produit = str(row[6]).strip() if row[6] else ''
                        nature_infraction = str(row[7]).strip().upper() if row[7] else ''
                        montant_raw = row[8]
                        observations = str(row[9]).strip() if len(row) > 9 and row[9] else ''
                    except (IndexError, TypeError) as e:
                        ligne_info['statut'] = 'erreur'
                        ligne_info['erreur'] = f"Format de ligne invalide: {str(e)}"
                        erreurs_import.append(ligne_info)
                        resultats.append(ligne_info)
                        continue

                    ligne_info['data'] = {
                        'numero_ticket': numero_ticket,
                        'immatriculation': immatriculation,
                        'transporteur': transporteur,
                        'nature': nature_infraction,
                    }

                    # Validation des champs obligatoires
                    champs_manquants = []
                    if not numero_ticket:
                        champs_manquants.append('Numéro ticket')
                    if not immatriculation:
                        champs_manquants.append('Immatriculation')
                    if not transporteur:
                        champs_manquants.append('Transporteur')
                    if not provenance:
                        champs_manquants.append('Provenance')
                    if not destination:
                        champs_manquants.append('Destination')
                    if not produit:
                        champs_manquants.append('Produit')
                    if not nature_infraction:
                        champs_manquants.append('Nature infraction')
                    if montant_raw is None or montant_raw == '':
                        champs_manquants.append('Montant')

                    if champs_manquants:
                        ligne_info['statut'] = 'erreur'
                        ligne_info['erreur'] = f"Champs obligatoires manquants: {', '.join(champs_manquants)}"
                        erreurs_import.append(ligne_info)
                        resultats.append(ligne_info)
                        continue

                    # Valider le montant
                    try:
                        montant = Decimal(str(montant_raw).replace(' ', '').replace(',', '.'))
                        if montant < 0:
                            raise ValueError("Montant négatif")
                    except (ValueError, Exception):
                        ligne_info['statut'] = 'erreur'
                        ligne_info['erreur'] = f"Montant invalide: {montant_raw}"
                        erreurs_import.append(ligne_info)
                        resultats.append(ligne_info)
                        continue

                    # Parser la nature de l'infraction
                    # Normaliser: remplacer les espaces et mettre en majuscules
                    nature_clean = nature_infraction.replace(' ', '').upper()

                    est_surcharge = False
                    est_hors_gabarit = False
                    est_delit_fuite = False

                    natures_valides = {
                        'S': (True, False, False),
                        'HG': (False, True, False),
                        'DF': (False, False, True),
                        'S+HG': (True, True, False),
                        'HG+S': (True, True, False),
                        'HG+DF': (False, True, True),
                        'DF+HG': (False, True, True),
                        'S+DF': (True, False, True),
                        'DF+S': (True, False, True),
                        'S+HG+DF': (True, True, True),
                        'S+DF+HG': (True, True, True),
                        'HG+S+DF': (True, True, True),
                        'HG+DF+S': (True, True, True),
                        'DF+S+HG': (True, True, True),
                        'DF+HG+S': (True, True, True),
                    }

                    if nature_clean in natures_valides:
                        est_surcharge, est_hors_gabarit, est_delit_fuite = natures_valides[nature_clean]
                    else:
                        ligne_info['statut'] = 'erreur'
                        ligne_info['erreur'] = f"Nature d'infraction invalide: '{nature_infraction}'. Valeurs acceptées: S, HG, DF, S+HG, HG+DF, S+DF, S+HG+DF"
                        erreurs_import.append(ligne_info)
                        resultats.append(ligne_info)
                        continue

                    # Vérifier unicité du numéro de ticket
                    numero_ticket_upper = numero_ticket.upper().strip()
                    if AmendeEmise.objects.filter(numero_ticket=numero_ticket_upper).exists():
                        ligne_info['statut'] = 'erreur'
                        ligne_info['erreur'] = f"Numéro de ticket '{numero_ticket_upper}' déjà existant"
                        erreurs_import.append(ligne_info)
                        resultats.append(ligne_info)
                        continue

                    # Gérer l'opérateur par défaut
                    if not operateur or operateur.strip() == '' or operateur.strip() == 'None':
                        operateur = '0'

                    # Créer l'amende
                    try:
                        amende = AmendeEmise(
                            numero_ticket=numero_ticket_upper,
                            station=station,
                            immatriculation=immatriculation.upper(),
                            transporteur=transporteur,
                            operateur=operateur,
                            provenance=provenance,
                            destination=destination,
                            produit_transporte=produit,
                            est_surcharge=est_surcharge,
                            est_hors_gabarit=est_hors_gabarit,
                            est_delit_fuite=est_delit_fuite,
                            montant_amende=montant,
                            statut='non_paye',
                            saisi_par=user,
                            date_heure_emission=timezone.now(),
                            observations=observations,
                        )
                        amende.save()
                        amendes_importees += 1
                        ligne_info['statut'] = 'ok'
                    except Exception as e:
                        ligne_info['statut'] = 'erreur'
                        ligne_info['erreur'] = f"Erreur création: {str(e)}"
                        erreurs_import.append(ligne_info)

                    resultats.append(ligne_info)

                wb.close()

                # Log de l'import
                log_user_action(
                    user,
                    "Import amendes Excel",
                    f"Station: {station.nom} | Fichier: {fichier.name} | "
                    f"Lignes traitées: {len(rows)} | "
                    f"Importées: {amendes_importees} | "
                    f"Erreurs: {len(erreurs_import)}",
                    request
                )

                if amendes_importees > 0:
                    messages.success(
                        request,
                        _("✅ %(nb)d amende(s) importée(s) avec succès sur %(total)d ligne(s).") % {
                            'nb': amendes_importees,
                            'total': len(rows),
                        }
                    )

                if erreurs_import:
                    messages.warning(
                        request,
                        _("⚠️ %(nb)d ligne(s) en erreur. Consultez le détail ci-dessous.") % {
                            'nb': len(erreurs_import),
                        }
                    )

            except Exception as e:
                logger.error(f"Erreur import amendes Excel: {e}", exc_info=True)
                messages.error(request, _("❌ Erreur lors de la lecture du fichier: %(error)s") % {'error': str(e)})

    else:
        from .forms_pesage import ImportAmendesForm
        form = ImportAmendesForm()

    context = {
        'form': form if not resultats else ImportAmendesForm(),
        'station': station,
        'is_admin': is_admin_user(user),
        'title': _('Importer des amendes'),
        'resultats': resultats,
        'amendes_importees': amendes_importees,
        'erreurs_import': erreurs_import,
        'peut_saisir_amende': has_permission(user, 'peut_saisir_amende'),
    }
    return render(request, 'pesage/importer_amendes.html', context)
