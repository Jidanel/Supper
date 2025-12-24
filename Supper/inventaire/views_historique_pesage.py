# ===================================================================
# inventaire/views_historique_pesage.py - Vues pour la recherche 
# d'historique et confirmation inter-stations du module Pesage SUPPER
# VERSION MISE À JOUR - Intégration des permissions granulaires
# ===================================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Q
from django.views.decorators.http import require_POST, require_GET
from functools import wraps
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging

from .models_pesage import AmendeEmise
from .models_confirmation import DemandeConfirmationPaiement, StatutDemandeConfirmation
from .utils_pesage import (
    normalize_search_text, normalize_immatriculation,
    rechercher_historique_vehicule, verifier_amendes_non_payees_autres_stations,
    get_resume_historique_vehicule, rechercher_par_criteres_multiples
)
from accounts.models import Poste

# ===================================================================
# IMPORTS DES PERMISSIONS GRANULAIRES DU PROJET
# ===================================================================
from common.permissions import (
    # Fonctions de classification utilisateurs
    is_admin_user,
    is_service_central,
    is_cisop,
    is_cisop_pesage,
    is_operationnel_pesage,
    is_regisseur_pesage,
    is_chef_station_pesage,
    is_chef_equipe_pesage,
    
    # Fonctions d'accès aux postes
    user_has_acces_tous_postes,
    get_postes_accessibles,
    get_postes_pesage_accessibles,
    check_poste_access,
    get_poste_from_request,
    
    # Vérification de permissions granulaires
    has_permission,
    has_any_permission,
    
    # Constantes d'habilitations
    HABILITATIONS_PESAGE,
    HABILITATIONS_OPERATIONNELS_PESAGE,
    HABILITATIONS_MULTI_POSTES,
    HABILITATIONS_ADMIN,
    
    # Logging
    log_acces_refuse,
)

from common.decorators import (
    permission_required_granular,
    operationnel_pesage_required,
    validation_paiement_amende_required,
    historique_vehicule_pesage_required,
    liste_amendes_required,
    api_permission_required,
)

from common.utils import log_user_action

logger = logging.getLogger('supper.pesage')


# ===================================================================
# FONCTIONS UTILITAIRES MISE À JOUR
# ===================================================================

def get_user_station_pesage(user):
    """
    Retourne la station de pesage de l'utilisateur.
    
    RÈGLES:
    - Si admin ou multi-postes: retourne None (accès à toutes les stations)
    - Si opérationnel pesage avec poste d'affectation valide: retourne le poste
    - Sinon: retourne False (pas d'accès)
    
    Args:
        user: L'utilisateur connecté
        
    Returns:
        Poste | None | False
    """
    if not user or not user.is_authenticated:
        return False
    
    # Admin et utilisateurs multi-postes ont accès à toutes les stations
    if user_has_acces_tous_postes(user):
        logger.debug(
            f"[get_user_station_pesage] Utilisateur {user.username} "
            f"(habilitation: {user.habilitation}) a accès à tous les postes"
        )
        return None
    
    # Vérifier que l'habilitation permet l'accès au module pesage
    habilitation = getattr(user, 'habilitation', None)
    if habilitation not in HABILITATIONS_OPERATIONNELS_PESAGE:
        logger.warning(
            f"[get_user_station_pesage] Utilisateur {user.username} "
            f"(habilitation: {habilitation}) n'a pas accès au module pesage"
        )
        return False
    
    # Vérifier que le poste d'affectation est une station de pesage valide
    poste = getattr(user, 'poste_affectation', None)
    if not poste:
        logger.warning(
            f"[get_user_station_pesage] Utilisateur {user.username} "
            f"n'a pas de poste d'affectation"
        )
        return False
    
    if poste.type != 'pesage':
        logger.warning(
            f"[get_user_station_pesage] Utilisateur {user.username} "
            f"affecté à un poste de type '{poste.type}' au lieu de 'pesage'"
        )
        return False
    
    if not poste.is_active:
        logger.warning(
            f"[get_user_station_pesage] Poste {poste.nom} de l'utilisateur "
            f"{user.username} est inactif"
        )
        return False
    
    logger.debug(
        f"[get_user_station_pesage] Utilisateur {user.username} "
        f"affecté à la station {poste.nom}"
    )
    return poste


def peut_valider_paiements(user):
    """
    Vérifie si l'utilisateur peut valider des paiements d'amendes.
    
    HABILITATIONS AUTORISÉES:
    - Admin (admin_principal, coord_psrr, serv_info)
    - Régisseur pesage (regisseur_pesage)
    - Chef de station pesage (chef_station_pesage)
    
    Returns:
        bool: True si autorisé à valider
    """
    if not user or not user.is_authenticated:
        return False
    
    # Vérifier la permission granulaire
    if has_permission(user, 'peut_valider_paiement_amende'):
        return True
    
    # Fallback sur les habilitations admin
    if is_admin_user(user):
        return True
    
    # Vérifier les habilitations spécifiques de validation
    habilitation = getattr(user, 'habilitation', None)
    return habilitation in ['regisseur_pesage']


def filtrer_amendes_par_acces(queryset, user):
    """
    Filtre un queryset d'amendes selon les droits d'accès de l'utilisateur.
    
    RÈGLES:
    - Accès tous postes: toutes les amendes
    - Accès poste unique: amendes de sa station uniquement
    
    Args:
        queryset: QuerySet d'AmendeEmise
        user: Utilisateur connecté
        
    Returns:
        QuerySet filtré
    """
    if user_has_acces_tous_postes(user):
        return queryset
    
    station = get_user_station_pesage(user)
    if station and station is not False:
        return queryset.filter(station=station)
    
    # Aucun accès
    return queryset.none()


# ===================================================================
# DÉCORATEURS PERSONNALISÉS POUR LE MODULE PESAGE
# ===================================================================

def pesage_access_required(view_func):
    """
    Décorateur vérifiant l'accès au module pesage.
    
    HABILITATIONS AUTORISÉES:
    - Admin (admin_principal, coord_psrr, serv_info)
    - CISOP pesage (cisop_pesage)
    - Opérationnels pesage (chef_station_pesage, regisseur_pesage, chef_equipe_pesage)
    
    Note: Les utilisateurs avec accès multi-postes peuvent accéder à toutes les stations.
    Les opérationnels pesage ne peuvent accéder qu'à leur station d'affectation.
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        
        # Admin a toujours accès
        if is_admin_user(user):
            logger.info(
                f"[pesage_access] Accès ADMIN accordé à {user.username} "
                f"pour {view_func.__name__}"
            )
            return view_func(request, *args, **kwargs)
        
        # CISOP pesage a accès à toutes les stations
        if is_cisop_pesage(user):
            logger.info(
                f"[pesage_access] Accès CISOP_PESAGE accordé à {user.username} "
                f"pour {view_func.__name__}"
            )
            return view_func(request, *args, **kwargs)
        
        # Vérifier si opérationnel pesage avec station valide
        station = get_user_station_pesage(user)
        if station is False:
            # Journaliser l'accès refusé
            log_user_action(
                user=user,
                action="ACCES_MODULE_PESAGE_REFUSE",
                details=f"Tentative d'accès à {view_func.__name__} refusée - "
                        f"Habilitation: {user.habilitation}, "
                        f"Poste: {getattr(user.poste_affectation, 'nom', 'Aucun')}",
                succes=False
            )
            log_acces_refuse(user, view_func.__name__, "Accès module pesage non autorisé")
            
            messages.error(
                request, 
                _("Accès non autorisé au module pesage. "
                  "Votre habilitation ne vous permet pas d'accéder à ce module.")
            )
            return redirect('common:dashboard')
        
        # Vérifier si opérationnel pesage
        if is_operationnel_pesage(user):
            logger.info(
                f"[pesage_access] Accès OPERATIONNEL_PESAGE accordé à {user.username} "
                f"pour {view_func.__name__} - Station: {station.nom if station else 'Toutes'}"
            )
            return view_func(request, *args, **kwargs)
        
        # Accès refusé par défaut
        log_user_action(
            user=user,
            action="ACCES_MODULE_PESAGE_REFUSE",
            details=f"Tentative d'accès à {view_func.__name__} refusée - "
                    f"Habilitation non reconnue: {user.habilitation}",
            succes=False
        )
        log_acces_refuse(user, view_func.__name__, "Habilitation non autorisée")
        
        messages.error(request, _("Accès non autorisé au module pesage."))
        return redirect('common:dashboard')
    
    return wrapper


def regisseur_pesage_required(view_func):
    """
    Décorateur vérifiant que l'utilisateur peut valider des paiements.
    
    HABILITATIONS AUTORISÉES:
    - Admin (admin_principal, coord_psrr, serv_info)
    - Régisseur pesage (regisseur_pesage)
    - Chef de station pesage (chef_station_pesage)
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        
        if peut_valider_paiements(user):
            station = get_user_station_pesage(user)
            logger.info(
                f"[regisseur_required] Accès accordé à {user.username} "
                f"(habilitation: {user.habilitation}) pour {view_func.__name__} "
                f"- Station: {station.nom if station and station is not False else 'Toutes'}"
            )
            return view_func(request, *args, **kwargs)
        
        # Accès refusé
        log_user_action(
            user=user,
            action="ACCES_VALIDATION_PAIEMENT_REFUSE",
            details=f"Tentative d'accès à {view_func.__name__} refusée - "
                    f"Habilitation: {user.habilitation} ne permet pas la validation",
            succes=False
        )
        log_acces_refuse(user, view_func.__name__, "Validation paiement non autorisée")
        
        messages.error(
            request, 
            _("Accès réservé aux régisseurs  pour la validation des paiements.")
        )
        return redirect('common:dashboard')
    
    return wrapper


# ===================================================================
# RECHERCHE D'HISTORIQUE VÉHICULE
# ===================================================================

@pesage_access_required
def recherche_historique_vehicule(request):
    """
    Page de recherche d'historique véhicule avec résumé statistique.
    
    PERMISSIONS REQUISES:
    - peut_voir_historique_vehicule_pesage OU
    - Être opérationnel pesage (chef_station, regisseur, chef_equipe)
    
    RÈGLES D'ACCÈS:
    - Utilisateurs avec accès tous postes: voient toutes les amendes
    - Opérationnels pesage: voient uniquement les amendes de leur station
    """
    user = request.user
    
    # Log de l'accès à la page
    log_user_action(
        user=user,
        action="ACCES_RECHERCHE_HISTORIQUE_VEHICULE",
        details=f"Accès à la page de recherche d'historique véhicule",
        succes=True
    )
    
    resultats = None
    resume = None
    recherche_effectuee = False
    
    # Récupérer les paramètres de recherche
    immatriculation = request.GET.get('immatriculation', '').strip()
    transporteur = request.GET.get('transporteur', '').strip()
    operateur = request.GET.get('operateur', '').strip()
    
    # Si au moins un critère de recherche
    if immatriculation or transporteur or operateur:
        recherche_effectuee = True
        
        # Recherche des amendes
        resultats_qs = rechercher_historique_vehicule(
            immatriculation=immatriculation,
            transporteur=transporteur,
            operateur=operateur
        )
        
        # Filtrer selon les droits d'accès de l'utilisateur
        resultats_qs = filtrer_amendes_par_acces(resultats_qs, user)
        
        # Log de la recherche
        log_user_action(
            user=user,
            action="RECHERCHE_HISTORIQUE_VEHICULE",
            details=f"Recherche effectuée - Critères: immat='{immatriculation}', "
                    f"transp='{transporteur}', op='{operateur}' - "
                    f"Résultats: {resultats_qs.count()}",
            succes=True
        )
        
        logger.info(
            f"[recherche_historique] Utilisateur {user.username} - "
            f"Recherche: immat={immatriculation}, transp={transporteur}, op={operateur} - "
            f"Résultats: {resultats_qs.count()}"
        )
        
        # Pagination
        paginator = Paginator(resultats_qs, 25)
        page_number = request.GET.get('page')
        resultats = paginator.get_page(page_number)
        
        # Calculer le résumé SI recherche par immatriculation
        if immatriculation:
            resume = get_resume_historique_vehicule(immatriculation)
            logger.debug(f"[recherche_historique] Résumé véhicule: {resume}")
    
    # Déterminer les stations accessibles pour le filtre
    stations_accessibles = get_postes_pesage_accessibles(user)
    
    context = {
        'resultats': resultats,
        'resume': resume,
        'immatriculation': immatriculation,
        'transporteur': transporteur,
        'operateur': operateur,
        'recherche_effectuee': recherche_effectuee,
        'stations_accessibles': stations_accessibles,
        'acces_tous_postes': user_has_acces_tous_postes(user),
    }
    
    return render(request, 'pesage/recherche_historique.html', context)


@pesage_access_required
def detail_historique_vehicule(request, immatriculation):
    """
    Affiche l'historique complet d'un véhicule par son immatriculation.
    
    RÈGLES D'ACCÈS:
    - Utilisateurs avec accès tous postes: voient toutes les amendes
    - Opérationnels pesage: voient uniquement les amendes de leur station
    """
    user = request.user
    
    # Normaliser l'immatriculation
    immat_normalise = normalize_immatriculation(immatriculation)
    
    # Récupérer toutes les amendes pour ce véhicule
    amendes_qs = AmendeEmise.objects.filter(
        immatriculation_normalise=immat_normalise
    ).select_related('station', 'saisi_par', 'valide_par').order_by('-date_heure_emission')
    
    # Filtrer selon les droits d'accès
    amendes_qs = filtrer_amendes_par_acces(amendes_qs, user)
    
    # Log de la consultation
    log_user_action(
        user=user,
        action="CONSULTATION_DETAIL_HISTORIQUE_VEHICULE",
        details=f"Consultation historique véhicule {immatriculation.upper()} - "
                f"Amendes trouvées: {amendes_qs.count()}",
        succes=True
    )
    
    # Appliquer les filtres supplémentaires
    station_filter = request.GET.get('station')
    statut_filter = request.GET.get('statut')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    
    if station_filter:
        # Vérifier que l'utilisateur a accès à cette station
        if user_has_acces_tous_postes(user) or check_poste_access(user, int(station_filter)):
            amendes_qs = amendes_qs.filter(station_id=station_filter)
        else:
            logger.warning(
                f"[detail_historique] Utilisateur {user.username} a tenté de filtrer "
                f"sur une station non autorisée: {station_filter}"
            )
    
    if statut_filter == 'paye':
        amendes_qs = amendes_qs.filter(statut='paye')
    elif statut_filter == 'non_paye':
        amendes_qs = amendes_qs.exclude(statut='paye')
    
    if date_debut:
        amendes_qs = amendes_qs.filter(date_heure_emission__date__gte=date_debut)
    
    if date_fin:
        amendes_qs = amendes_qs.filter(date_heure_emission__date__lte=date_fin)
    
    # Calculer le total des montants
    total_montant = amendes_qs.aggregate(total=Sum('montant_amende'))['total'] or 0
    
    # Résumé statistique global (basé sur les amendes accessibles à l'utilisateur)
    amendes_all = AmendeEmise.objects.filter(immatriculation_normalise=immat_normalise)
    amendes_all = filtrer_amendes_par_acces(amendes_all, user)
    
    resume = {
        'total_amendes': amendes_all.count(),
        'total_payees': amendes_all.filter(statut='paye').count(),
        'total_non_payees': amendes_all.exclude(statut='paye').count(),
        'montant_total': amendes_all.aggregate(total=Sum('montant_amende'))['total'] or 0,
        'montant_paye': amendes_all.filter(statut='paye').aggregate(total=Sum('montant_amende'))['total'] or 0,
        'montant_impaye': amendes_all.exclude(statut='paye').aggregate(total=Sum('montant_amende'))['total'] or 0,
        'stations_distinctes': amendes_all.values('station').distinct().count(),
    }
    
    # Stats par station (uniquement les stations accessibles)
    stats_par_station = amendes_all.values('station__nom').annotate(
        total=Count('id'),
        payees=Count('id', filter=Q(statut='paye')),
        non_payees=Count('id', filter=~Q(statut='paye'))
    ).order_by('-total')
    
    # Liste des stations pour le filtre (uniquement celles accessibles)
    stations_list = get_postes_pesage_accessibles(user)
    
    # Pagination
    paginator = Paginator(amendes_qs, 25)
    page_number = request.GET.get('page')
    amendes = paginator.get_page(page_number)
    
    context = {
        'immatriculation': immatriculation.upper(),
        'amendes': amendes,
        'resume': resume,
        'total_montant': total_montant,
        'stats_par_station': stats_par_station,
        'stations_list': stations_list,
        'acces_tous_postes': user_has_acces_tous_postes(user),
    }
    
    return render(request, 'pesage/detail_historique_vehicule.html', context)


# ===================================================================
# VÉRIFICATION AVANT VALIDATION DE PAIEMENT
# ===================================================================

@regisseur_pesage_required
def verifier_avant_validation(request, pk):
    """
    Vérifie si un véhicule a des amendes non payées dans d'autres stations
    AVANT de valider un paiement.
    
    PERMISSIONS REQUISES:
    - peut_valider_paiement_amende OU
    - Être régisseur/chef de station pesage
    
    RÈGLES MÉTIER:
    - Si pas d'amende non payée ailleurs: redirige vers validation
    - Si amendes non payées: affiche page de blocage avec options
    """
    user = request.user
    station_utilisateur = get_user_station_pesage(user)
    
    # Récupérer l'amende
    if user_has_acces_tous_postes(user):
        amende = get_object_or_404(AmendeEmise, pk=pk)
        station_actuelle = amende.station
    else:
        if station_utilisateur and station_utilisateur is not False:
            amende = get_object_or_404(AmendeEmise, pk=pk, station=station_utilisateur)
            station_actuelle = station_utilisateur
        else:
            log_user_action(
                user=user,
                action="VERIFICATION_VALIDATION_REFUSEE",
                details=f"Tentative de vérification amende {pk} sans station d'affectation valide",
                succes=False
            )
            messages.error(request, _("Vous devez être affecté à une station de pesage."))
            return redirect('common:dashboard')
    
    # Log de la vérification
    log_user_action(
        user=user,
        action="VERIFICATION_AVANT_VALIDATION",
        details=f"Vérification amende {amende.numero_ticket} - "
                f"Véhicule: {amende.immatriculation} - Station: {station_actuelle.nom}",
        succes=True
    )
    
    # Vérifier si déjà payée
    if amende.statut == 'paye':
        messages.warning(request, _("Cette amende a déjà été validée."))
        return redirect('inventaire:liste_amendes')
    
    # Vérifier les amendes non payées dans AUTRES stations
    a_impaye, amendes_impayees = verifier_amendes_non_payees_autres_stations(
        amende.immatriculation, station_actuelle
    )
    
    if not a_impaye:
        # Pas d'amende non payée ailleurs → validation directe possible
        logger.info(
            f"[verifier_validation] Amende {amende.numero_ticket} - "
            f"Pas d'impayé ailleurs - Validation autorisée"
        )
        return redirect('inventaire:valider_paiement_direct', pk=pk)
    
    # Il y a des amendes non payées ailleurs
    demandes_existantes = DemandeConfirmationPaiement.objects.filter(
        amende_a_valider=amende
    ).select_related('station_concernee', 'amende_non_payee')
    
    # Vérifier si toutes les confirmations sont obtenues
    toutes_confirmees = True
    for amende_impayee in amendes_impayees:
        demande = demandes_existantes.filter(amende_non_payee=amende_impayee).first()
        if not demande or demande.statut != StatutDemandeConfirmation.CONFIRME:
            toutes_confirmees = False
            break
    
    if toutes_confirmees:
        logger.info(
            f"[verifier_validation] Amende {amende.numero_ticket} - "
            f"Toutes confirmations obtenues - Validation autorisée"
        )
        return redirect('inventaire:valider_paiement_direct', pk=pk)
    
    # Log du blocage
    log_user_action(
        user=user,
        action="VALIDATION_BLOQUEE_AMENDES_ANTERIEURES",
        details=f"Validation amende {amende.numero_ticket} bloquée - "
                f"Véhicule: {amende.immatriculation} - "
                f"{amendes_impayees.count()} amendes antérieures non payées",
        succes=False
    )
    
    context = {
        'amende': amende,
        'amendes_impayees': amendes_impayees,
        'demandes_existantes': demandes_existantes,
        'station': station_actuelle,
        'is_admin': is_admin_user(user),
        'acces_tous_postes': user_has_acces_tous_postes(user),
        'title': _("Validation bloquée - Amendes non payées"),
    }
    
    return render(request, 'pesage/validation_paiement_bloquee.html', context)


@regisseur_pesage_required
def valider_paiement_direct(request, pk):
    """
    Validation du paiement d'une amende par le régisseur.
    
    RÈGLES MÉTIER:
    1. Seul le régisseur de la station peut valider les amendes de SA station
       (sauf si accès tous postes)
    2. AVANT validation, vérifier si le véhicule a des amendes NON PAYÉES plus anciennes ailleurs
    3. Si amendes plus anciennes non payées → BLOCAGE
    4. L'ordre chronologique doit être respecté (FIFO)
    """
    user = request.user
    amende = get_object_or_404(AmendeEmise, pk=pk)
    
    # ============================================
    # VÉRIFICATION 1: Accès à cette amende
    # ============================================
    if not user_has_acces_tous_postes(user):
        station_utilisateur = get_user_station_pesage(user)
        if station_utilisateur is False or not station_utilisateur:
            log_user_action(
                user=user,
                action="VALIDATION_PAIEMENT_REFUSEE",
                details=f"Tentative validation amende {amende.numero_ticket} - "
                        f"Utilisateur sans station d'affectation valide",
                succes=False
            )
            messages.error(request, _("Vous devez être affecté à une station de pesage."))
            return redirect('inventaire:liste_amendes')
        
        if station_utilisateur != amende.station:
            log_user_action(
                user=user,
                action="VALIDATION_PAIEMENT_REFUSEE",
                details=f"Tentative validation amende {amende.numero_ticket} - "
                        f"Station amende: {amende.station.nom} ≠ Station utilisateur: {station_utilisateur.nom}",
                succes=False
            )
            messages.error(
                request, 
                _("Vous ne pouvez pas valider les amendes de la station %(station)s. "
                  "Vous êtes affecté à %(votre_station)s.") % {
                    'station': amende.station.nom,
                    'votre_station': station_utilisateur.nom
                }
            )
            return redirect('inventaire:liste_amendes')
    
    # ============================================
    # VÉRIFICATION 2: L'amende est-elle déjà payée ?
    # ============================================
    if amende.statut == 'paye':
        messages.warning(request, _("Cette amende a déjà été validée comme payée."))
        return redirect('inventaire:detail_amende', pk=pk)
    
    # ============================================
    # VÉRIFICATION 3: Amendes NON PAYÉES plus anciennes ailleurs ?
    # ============================================
    immat_norm = normalize_immatriculation(amende.immatriculation)
    
    amendes_anterieures_non_payees = AmendeEmise.objects.filter(
        immatriculation_normalise=immat_norm,
        statut='non_paye',
        date_heure_emission__lt=amende.date_heure_emission
    ).exclude(
        station=amende.station
    ).select_related('station').order_by('date_heure_emission')
    
    # ============================================
    # SI AMENDES ANTÉRIEURES NON PAYÉES → BLOCAGE
    # ============================================
    if amendes_anterieures_non_payees.exists():
        request.session['amende_a_valider_pk'] = pk
        request.session['amendes_bloquantes_pks'] = list(
            amendes_anterieures_non_payees.values_list('pk', flat=True)
        )
        
        log_user_action(
            user=user,
            action="VALIDATION_BLOQUEE_FIFO",
            details=f"Validation amende {amende.numero_ticket} bloquée - "
                    f"{amendes_anterieures_non_payees.count()} amendes antérieures non payées "
                    f"(FIFO non respecté)",
            succes=False
        )
        
        return redirect('inventaire:validation_bloquee', pk=pk)
    
    # ============================================
    # SI POST ET PAS DE BLOCAGE → VALIDER LE PAIEMENT
    # ============================================
    if request.method == 'POST':
        # Dernière vérification (race condition)
        amendes_anterieures_check = AmendeEmise.objects.filter(
            immatriculation_normalise=immat_norm,
            statut='non_paye',
            date_heure_emission__lt=amende.date_heure_emission
        ).exclude(station=amende.station).exists()
        
        if amendes_anterieures_check:
            log_user_action(
                user=user,
                action="VALIDATION_ANNULEE_RACE_CONDITION",
                details=f"Validation amende {amende.numero_ticket} annulée - "
                        f"Nouvelles amendes antérieures détectées (race condition)",
                succes=False
            )
            messages.error(
                request,
                _("Impossible de valider : de nouvelles amendes antérieures non payées ont été détectées.")
            )
            return redirect('inventaire:validation_bloquee', pk=pk)
        
        # Valider le paiement
        amende.statut = 'paye'
        amende.date_paiement = timezone.now()
        amende.valide_par = user
        amende.save(update_fields=['statut', 'date_paiement', 'valide_par'])
        
        # Log de la validation réussie
        log_user_action(
            user=user,
            action="VALIDATION_PAIEMENT_AMENDE",
            details=f"Paiement validé - Amende: {amende.numero_ticket} - "
                    f"Véhicule: {amende.immatriculation} - "
                    f"Montant: {amende.montant_amende} FCFA - "
                    f"Station: {amende.station.nom}",
            succes=True
        )
        
        messages.success(
            request, 
            _("✅ Paiement validé pour l'amende %(numero)s - %(montant)s FCFA") % {
                'numero': amende.numero_ticket,
                'montant': amende.montant_amende
            }
        )
        
        logger.info(
            f"[valider_paiement] Paiement validé: Amende {amende.numero_ticket} - "
            f"Véhicule {amende.immatriculation} - Station {amende.station.nom} - "
            f"Régisseur {user.username}"
        )
        
        return redirect('inventaire:liste_amendes_a_valider')
    
    # Si GET, afficher la page de confirmation
    context = {
        'amende': amende,
        'acces_tous_postes': user_has_acces_tous_postes(user),
    }
    return render(request, 'pesage/confirmer_validation_paiement.html', context)


# @regisseur_pesage_required
# def validation_bloquee(request, pk):
#     """
#     Page affichée quand la validation est bloquée à cause d'amendes antérieures non payées.
#     """
#     user = request.user
#     amende_a_valider = get_object_or_404(AmendeEmise, pk=pk)
#     immat_norm = normalize_immatriculation(amende_a_valider.immatriculation)
    
#     # Log de l'accès à la page de blocage
#     log_user_action(
#         user=user,
#         action="CONSULTATION_PAGE_VALIDATION_BLOQUEE",
#         details=f"Consultation page blocage - Amende: {amende_a_valider.numero_ticket} - "
#                 f"Véhicule: {amende_a_valider.immatriculation}",
#         succes=True
#     )
    
#     # Récupérer les amendes bloquantes
#     amendes_bloquantes = AmendeEmise.objects.filter(
#         Q(immatriculation_normalise__iexact=immat_norm) |
#         Q(immatriculation__iexact=amende_a_valider.immatriculation) |
#         Q(immatriculation__iexact=immat_norm),
#         statut='non_paye',
#         date_heure_emission__lt=amende_a_valider.date_heure_emission
#     ).exclude(
#         station=amende_a_valider.station
#     ).exclude(
#         pk=amende_a_valider.pk
#     ).select_related('station', 'saisi_par').order_by('date_heure_emission')
    
#     # Historique complet du véhicule (filtré selon accès utilisateur)
#     historique_complet = AmendeEmise.objects.filter(
#         Q(immatriculation_normalise__iexact=immat_norm) |
#         Q(immatriculation__iexact=amende_a_valider.immatriculation) |
#         Q(immatriculation__iexact=immat_norm)
#     ).select_related('station', 'saisi_par', 'valide_par').order_by('-date_heure_emission')
    
#     # Filtrer selon accès si non admin
#     if not user_has_acces_tous_postes(user):
#         # L'utilisateur voit quand même les amendes bloquantes (pour comprendre le blocage)
#         # mais l'historique complet est filtré
#         pass  # On garde l'historique complet pour la compréhension du blocage
    
#     # Statistiques du véhicule
#     stats = historique_complet.aggregate(
#         total=Count('id'),
#         payees=Count('id', filter=Q(statut='paye')),
#         non_payees=Count('id', filter=Q(statut='non_paye')),
#         montant_total=Sum('montant_amende'),
#         montant_impaye=Sum('montant_amende', filter=Q(statut='non_paye')),
#     )
    
#     # Vérifier les demandes de confirmation déjà envoyées
#     demandes_existantes = DemandeConfirmationPaiement.objects.filter(
#         amende_a_valider=amende_a_valider,
#         statut__in=['en_attente', 'confirme']
#     ).select_related(
#         'amende_non_payee',
#         'amende_non_payee__station',
#         'station_concernee'
#     )
    
#     # Créer un dict pour savoir quelles amendes ont déjà une demande
#     amendes_avec_demande = {d.amende_non_payee_id: d for d in demandes_existantes}
    
#     context = {
#         'amende_a_valider': amende_a_valider,
#         'amendes_bloquantes': amendes_bloquantes,
#         'historique_complet': historique_complet,
#         'stats': stats,
#         'amendes_avec_demande': amendes_avec_demande,
#         'acces_tous_postes': user_has_acces_tous_postes(user),
#     }
    
#     return render(request, 'pesage/validation_bloquee.html', context)


# # ===================================================================
# # GESTION DES DEMANDES DE CONFIRMATION
# # ===================================================================

# @regisseur_pesage_required
# def creer_demande_confirmation(request, amende_pk, amende_bloquante_pk):
#     """
#     Crée une demande de confirmation auprès d'une autre station.
#     """
#     user = request.user
#     station_utilisateur = get_user_station_pesage(user)
    
#     # Récupérer l'amende à valider
#     if user_has_acces_tous_postes(user):
#         amende_a_valider = get_object_or_404(AmendeEmise, pk=amende_pk)
#         station_demandeur = amende_a_valider.station
#     else:
#         if station_utilisateur and station_utilisateur is not False:
#             amende_a_valider = get_object_or_404(AmendeEmise, pk=amende_pk, station=station_utilisateur)
#             station_demandeur = station_utilisateur
#         else:
#             messages.error(request, _("Vous devez être affecté à une station de pesage."))
#             return redirect('common:dashboard')
    
#     # Récupérer l'amende bloquante
#     amende_non_payee = get_object_or_404(AmendeEmise, pk=amende_bloquante_pk, statut='non_paye')
    
#     # Vérifier que l'amende bloquante est dans une AUTRE station
#     if amende_non_payee.station == station_demandeur:
#         messages.error(request, _("L'amende bloquante doit être dans une autre station."))
#         return redirect('inventaire:verifier_avant_validation', pk=amende_pk)
    
#     # Vérifier si une demande existe déjà
#     demande_existante = DemandeConfirmationPaiement.existe_demande_en_attente(
#         amende_a_valider, amende_non_payee
#     )
    
#     if demande_existante:
#         messages.warning(request, 
#             _("Une demande de confirmation existe déjà (Réf: %(ref)s).") % {
#                 'ref': demande_existante.reference
#             })
#         return redirect('inventaire:detail_demande_confirmation', pk=demande_existante.pk)
    
#     if request.method == 'POST':
#         commentaire = request.POST.get('commentaire', '').strip()
        
#         # Créer la demande
#         demande = DemandeConfirmationPaiement(
#             station_demandeur=station_demandeur,
#             regisseur_demandeur=user,
#             amende_a_valider=amende_a_valider,
#             station_concernee=amende_non_payee.station,
#             amende_non_payee=amende_non_payee,
#             commentaire_demande=commentaire,
#             vehicule_immatriculation=amende_a_valider.immatriculation,
#             vehicule_transporteur=amende_a_valider.transporteur,
#         )
#         demande.save()
        
#         # Log de la création
#         log_user_action(
#             user=user,
#             action="CREATION_DEMANDE_CONFIRMATION",
#             details=f"Demande créée - Réf: {demande.reference} - "
#                     f"Amende à valider: {amende_a_valider.numero_ticket} - "
#                     f"Amende bloquante: {amende_non_payee.numero_ticket} - "
#                     f"Station concernée: {amende_non_payee.station.nom}",
#             succes=True
#         )
        
#         messages.success(request,
#             _("Demande de confirmation créée (Réf: %(ref)s). "
#               "La station %(station)s doit confirmer.") % {
#                 'ref': demande.reference,
#                 'station': amende_non_payee.station.nom
#             })
        
#         logger.info(
#             f"[creer_demande] Demande confirmation créée par {user.username} - "
#             f"Réf: {demande.reference} - Véhicule: {demande.vehicule_immatriculation}"
#         )
        
#         return redirect('inventaire:mes_demandes_confirmation')
    
#     context = {
#         'amende_a_valider': amende_a_valider,
#         'amende_non_payee': amende_non_payee,
#         'station_demandeur': station_demandeur,
#         'station': station_utilisateur,
#         'is_admin': is_admin_user(user),
#         'acces_tous_postes': user_has_acces_tous_postes(user),
#         'title': _("Créer une demande de confirmation"),
#     }
    
#     return render(request, 'pesage/creer_demande_confirmation.html', context)


# @regisseur_pesage_required
# def mes_demandes_confirmation(request):
#     """
#     Liste des demandes de confirmation envoyées par ma station.
#     """
#     user = request.user
#     station = get_user_station_pesage(user)
    
#     log_user_action(
#         user=user,
#         action="CONSULTATION_MES_DEMANDES_CONFIRMATION",
#         details=f"Consultation liste des demandes envoyées",
#         succes=True
#     )
    
#     if user_has_acces_tous_postes(user):
#         demandes = DemandeConfirmationPaiement.objects.all()
#     else:
#         if station and station is not False:
#             demandes = DemandeConfirmationPaiement.get_demandes_envoyees_par_station(station)
#         else:
#             demandes = DemandeConfirmationPaiement.objects.none()
    
#     # Filtrer par statut
#     statut_filter = request.GET.get('statut')
#     if statut_filter:
#         demandes = demandes.filter(statut=statut_filter)
    
#     # Pagination
#     paginator = Paginator(demandes, 20)
#     page = request.GET.get('page')
#     demandes_page = paginator.get_page(page)
    
#     context = {
#         'demandes': demandes_page,
#         'statut_filter': statut_filter,
#         'statuts': StatutDemandeConfirmation.choices,
#         'station': station if station and station is not False else None,
#         'is_admin': is_admin_user(user),
#         'acces_tous_postes': user_has_acces_tous_postes(user),
#         'title': _("Mes demandes de confirmation"),
#     }
    
#     return render(request, 'pesage/mes_demandes_confirmation.html', context)


# @regisseur_pesage_required
# def demandes_confirmation_a_traiter(request):
#     """
#     Liste des demandes de confirmation à traiter (reçues par ma station).
#     """
#     user = request.user
#     station = get_user_station_pesage(user)
    
#     log_user_action(
#         user=user,
#         action="CONSULTATION_DEMANDES_A_TRAITER",
#         details=f"Consultation liste des demandes à traiter",
#         succes=True
#     )
    
#     if user_has_acces_tous_postes(user):
#         # Admin: sélection de station requise
#         station_id = request.GET.get('station')
#         if station_id:
#             try:
#                 station = Poste.objects.get(pk=station_id, type='pesage')
#             except Poste.DoesNotExist:
#                 station = None
        
#         if not station:
#             stations = Poste.objects.filter(type='pesage', is_active=True).order_by('nom')
#             # Compter les demandes en attente par station
#             for s in stations:
#                 s.nb_demandes_attente = DemandeConfirmationPaiement.objects.filter(
#                     station_concernee=s,
#                     statut=StatutDemandeConfirmation.EN_ATTENTE
#                 ).count()
            
#             context = {
#                 'stations': stations,
#                 'is_admin': True,
#                 'acces_tous_postes': True,
#                 'title': _("Sélectionner une station"),
#             }
#             return render(request, 'pesage/selectionner_station_confirmation.html', context)
    
#     if not station or station is False:
#         messages.error(request, _("Vous devez être affecté à une station de pesage."))
#         return redirect('common:dashboard')
    
#     # Récupérer les demandes en attente pour cette station
#     demandes_attente = DemandeConfirmationPaiement.get_demandes_en_attente_pour_station(station)
    
#     # Récupérer aussi les demandes déjà traitées
#     demandes_traitees = DemandeConfirmationPaiement.objects.filter(
#         station_concernee=station
#     ).exclude(
#         statut=StatutDemandeConfirmation.EN_ATTENTE
#     ).order_by('-date_reponse')[:20]
    
#     context = {
#         'demandes_attente': demandes_attente,
#         'demandes_traitees': demandes_traitees,
#         'station': station,
#         'is_admin': is_admin_user(user),
#         'acces_tous_postes': user_has_acces_tous_postes(user),
#         'title': _("Demandes de confirmation à traiter"),
#     }
    
#     return render(request, 'pesage/demandes_confirmation_a_traiter.html', context)


# @regisseur_pesage_required
# def detail_demande_confirmation(request, pk):
#     """
#     Détail d'une demande de confirmation.
#     """
#     user = request.user
#     station = get_user_station_pesage(user)
    
#     demande = get_object_or_404(
#         DemandeConfirmationPaiement.objects.select_related(
#             'station_demandeur', 'regisseur_demandeur',
#             'station_concernee', 'regisseur_confirmeur',
#             'amende_a_valider', 'amende_non_payee',
#             'amende_a_valider__station', 'amende_non_payee__station'
#         ),
#         pk=pk
#     )
    
#     # Vérifier l'accès
#     if not user_has_acces_tous_postes(user):
#         if station and station is not False:
#             if station not in [demande.station_demandeur, demande.station_concernee]:
#                 log_user_action(
#                     user=user,
#                     action="ACCES_DEMANDE_CONFIRMATION_REFUSE",
#                     details=f"Tentative d'accès demande {demande.reference} - "
#                             f"Station utilisateur: {station.nom} non autorisée",
#                     succes=False
#                 )
#                 messages.error(request, _("Vous n'avez pas accès à cette demande."))
#                 return redirect('common:dashboard')
#         else:
#             messages.error(request, _("Vous devez être affecté à une station de pesage."))
#             return redirect('common:dashboard')
    
#     # Log de la consultation
#     log_user_action(
#         user=user,
#         action="CONSULTATION_DETAIL_DEMANDE_CONFIRMATION",
#         details=f"Consultation demande {demande.reference}",
#         succes=True
#     )
    
#     # Déterminer si l'utilisateur peut traiter la demande
#     peut_traiter = False
#     if user_has_acces_tous_postes(user):
#         peut_traiter = demande.peut_etre_traitee
#     elif station and station is not False:
#         peut_traiter = (
#             station == demande.station_concernee and 
#             peut_valider_paiements(user) and
#             demande.peut_etre_traitee
#         )
    
#     # Historique du véhicule
#     historique = AmendeEmise.objects.filter(
#         immatriculation_normalise__iexact=demande.amende_a_valider.immatriculation_normalise
#     ).select_related('station').order_by('-date_heure_emission')[:10]
    
#     context = {
#         'demande': demande,
#         'peut_traiter': peut_traiter,
#         'historique': historique,
#         'station': station if station and station is not False else None,
#         'is_admin': is_admin_user(user),
#         'acces_tous_postes': user_has_acces_tous_postes(user),
#         'title': f"Demande {demande.reference}",
#     }
    
#     return render(request, 'pesage/detail_demande_confirmation.html', context)


# @regisseur_pesage_required
# @require_POST
# def traiter_demande_confirmation(request, pk):
#     """
#     Traite une demande de confirmation (confirmer ou refuser).
#     """
#     user = request.user
#     station = get_user_station_pesage(user)
    
#     demande = get_object_or_404(DemandeConfirmationPaiement, pk=pk)
    
#     # Vérifier les permissions
#     if not user_has_acces_tous_postes(user):
#         if station is False or not station:
#             messages.error(request, _("Vous devez être affecté à une station de pesage."))
#             return redirect('common:dashboard')
#         if station != demande.station_concernee:
#             log_user_action(
#                 user=user,
#                 action="TRAITEMENT_DEMANDE_REFUSE",
#                 details=f"Tentative traitement demande {demande.reference} - "
#                         f"Station utilisateur: {station.nom} ≠ Station concernée: {demande.station_concernee.nom}",
#                 succes=False
#             )
#             messages.error(request, _("Vous ne pouvez pas traiter cette demande."))
#             return redirect('inventaire:detail_demande_confirmation', pk=pk)
    
#     if not demande.peut_etre_traitee:
#         messages.error(request, _("Cette demande ne peut plus être traitée."))
#         return redirect('inventaire:detail_demande_confirmation', pk=pk)
    
#     action = request.POST.get('action')
#     commentaire = request.POST.get('commentaire', '').strip()
    
#     if action == 'confirmer':
#         if demande.confirmer(user, commentaire):
#             log_user_action(
#                 user=user,
#                 action="CONFIRMATION_DEMANDE",
#                 details=f"Demande {demande.reference} CONFIRMÉE - "
#                         f"Amende: {demande.amende_non_payee.numero_ticket}",
#                 succes=True
#             )
#             messages.success(request,
#                 _("Demande %(ref)s CONFIRMÉE. Le paiement est maintenant autorisé.") % {
#                     'ref': demande.reference
#                 })
#         else:
#             messages.error(request, _("Erreur lors de la confirmation."))
    
#     elif action == 'refuser':
#         if not commentaire:
#             messages.error(request, _("Un commentaire est requis pour refuser une demande."))
#             return redirect('inventaire:detail_demande_confirmation', pk=pk)
        
#         if demande.refuser(user, commentaire):
#             log_user_action(
#                 user=user,
#                 action="REFUS_DEMANDE",
#                 details=f"Demande {demande.reference} REFUSÉE - "
#                         f"Raison: {commentaire}",
#                 succes=True
#             )
#             messages.success(request,
#                 _("Demande %(ref)s REFUSÉE. Le paiement reste bloqué.") % {
#                     'ref': demande.reference
#                 })
#         else:
#             messages.error(request, _("Erreur lors du refus."))
    
#     else:
#         messages.error(request, _("Action non reconnue."))
    
#     return redirect('inventaire:demandes_confirmation_a_traiter')


# ===================================================================
# API ENDPOINTS
# ===================================================================

@pesage_access_required
@require_GET
def api_recherche_historique(request):
    """
    API de recherche rapide d'historique véhicule.
    """
    user = request.user
    q = request.GET.get('q', '').strip()
    immat = request.GET.get('immat', '').strip()
    transporteur = request.GET.get('transporteur', '').strip()
    operateur = request.GET.get('operateur', '').strip()
    
    # Si recherche globale
    if q and not (immat or transporteur or operateur):
        immat_norm = normalize_immatriculation(q)
        text_norm = normalize_search_text(q)
        
        resultats = AmendeEmise.objects.filter(
            Q(immatriculation_normalise__icontains=immat_norm) |
            Q(transporteur_normalise__icontains=text_norm) |
            Q(operateur_normalise__icontains=text_norm)
        ).select_related('station').order_by('-date_heure_emission')[:20]
    else:
        criteres = {
            'immatriculation': immat,
            'transporteur': transporteur,
            'operateur': operateur,
        }
        resultats = rechercher_par_criteres_multiples(criteres)[:20]
    
    # Filtrer selon les droits d'accès
    resultats = filtrer_amendes_par_acces(resultats, user)
    
    # Log de la recherche API
    log_user_action(
        user=user,
        action="API_RECHERCHE_HISTORIQUE",
        details=f"Recherche API - q='{q}', immat='{immat}' - Résultats: {len(resultats)}",
        succes=True
    )
    
    data = {
        'count': len(resultats),
        'resultats': [{
            'id': a.pk,
            'numero_ticket': a.numero_ticket,
            'immatriculation': a.immatriculation,
            'transporteur': a.transporteur,
            'operateur': a.operateur,
            'station': a.station.nom,
            'montant': float(a.montant_amende),
            'statut': a.get_statut_display(),
            'statut_code': a.statut,
            'date': a.date_heure_emission.strftime('%d/%m/%Y %H:%M'),
            'url': reverse('inventaire:detail_amende', args=[a.pk]),
        } for a in resultats]
    }
    
    return JsonResponse(data)


@regisseur_pesage_required
@require_GET
def api_verifier_impaye_autres_stations(request):
    """
    API pour vérifier les amendes impayées dans d'autres stations.
    """
    user = request.user
    immatriculation = request.GET.get('immatriculation', '').strip()
    station_id = request.GET.get('station_actuelle')
    
    if not immatriculation:
        return JsonResponse({'error': 'Immatriculation requise'}, status=400)
    
    try:
        station_actuelle = Poste.objects.get(pk=station_id, type='pesage') if station_id else None
    except Poste.DoesNotExist:
        station_actuelle = None
    
    # Vérifier l'accès à la station si spécifiée
    if station_actuelle and not user_has_acces_tous_postes(user):
        if not check_poste_access(user, station_actuelle):
            return JsonResponse({'error': 'Accès non autorisé à cette station'}, status=403)
    
    a_impaye, amendes = verifier_amendes_non_payees_autres_stations(
        immatriculation, station_actuelle
    )
    
    log_user_action(
        user=user,
        action="API_VERIFICATION_IMPAYE",
        details=f"Vérification impayés - Véhicule: {immatriculation} - "
                f"Résultat: {'OUI' if a_impaye else 'NON'} ({amendes.count()} amendes)",
        succes=True
    )
    
    data = {
        'a_impaye': a_impaye,
        'count': amendes.count() if a_impaye else 0,
        'amendes': [{
            'id': a.pk,
            'numero_ticket': a.numero_ticket,
            'station': a.station.nom,
            'station_id': a.station.id,
            'montant': float(a.montant_amende),
            'date': a.date_heure_emission.strftime('%d/%m/%Y %H:%M'),
            'transporteur': a.transporteur,
        } for a in amendes] if a_impaye else []
    }
    
    return JsonResponse(data)


# @regisseur_pesage_required
# @require_GET  
# def api_count_demandes_attente(request):
#     """
#     API pour compter les demandes en attente pour une station.
#     Utile pour les badges de notification.
#     """
#     user = request.user
#     station = get_user_station_pesage(user)
    
#     if user_has_acces_tous_postes(user):
#         station_id = request.GET.get('station')
#         if station_id:
#             try:
#                 station = Poste.objects.get(pk=station_id, type='pesage')
#             except Poste.DoesNotExist:
#                 return JsonResponse({'count': 0})
#         else:
#             # Compter pour toutes les stations
#             count = DemandeConfirmationPaiement.objects.filter(
#                 statut=StatutDemandeConfirmation.EN_ATTENTE
#             ).count()
#             return JsonResponse({'count': count})
    
#     if not station or station is False:
#         return JsonResponse({'count': 0})
    
#     count = DemandeConfirmationPaiement.objects.filter(
#         station_concernee=station,
#         statut=StatutDemandeConfirmation.EN_ATTENTE
#     ).count()
    
#     return JsonResponse({'count': count})