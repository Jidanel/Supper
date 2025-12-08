# ===================================================================
# inventaire/views_historique_pesage.py - Vues pour la recherche 
# d'historique et confirmation inter-stations du module Pesage SUPPER
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

logger = logging.getLogger('supper')


# ===================================================================
# CONSTANTES RÔLES PESAGE
# ===================================================================

PESAGE_ROLES = ['chef_equipe_pesage', 'regisseur_pesage', 'chef_station_pesage']
VALIDATION_ROLES = ['regisseur_pesage', 'chef_station_pesage']


# ===================================================================
# FONCTIONS UTILITAIRES
# ===================================================================

def is_admin(user):
    """Vérifie si l'utilisateur est administrateur"""
    return user.is_superuser or user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info']


def get_user_station(user):
    """Retourne la station de pesage de l'utilisateur"""
    if is_admin(user):
        return None
    
    if user.habilitation not in PESAGE_ROLES:
        return False
    
    if user.poste_affectation and user.poste_affectation.type == 'pesage':
        return user.poste_affectation
    
    return False


# ===================================================================
# DÉCORATEUR D'ACCÈS
# ===================================================================

def pesage_access_required(view_func):
    """Vérifie que l'utilisateur a accès au module pesage"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        if is_admin(user):
            return view_func(request, *args, **kwargs)
        if user.habilitation not in PESAGE_ROLES:
            messages.error(request, _("Accès non autorisé au module pesage."))
            return redirect('common:dashboard')
        station = get_user_station(user)
        if station is False:
            messages.error(request, _("Vous devez être affecté à une station de pesage."))
            return redirect('common:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def regisseur_required(view_func):
    """Vérifie que l'utilisateur est régisseur ou admin"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        if is_admin(user):
            return view_func(request, *args, **kwargs)
        if user.habilitation not in VALIDATION_ROLES:
            messages.error(request, _("Accès réservé aux régisseurs."))
            return redirect('common:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ===================================================================
# RECHERCHE D'HISTORIQUE VÉHICULE
# ===================================================================

# inventaire/views_historique_pesage.py

@login_required
def recherche_historique_vehicule(request):
    """
    Page de recherche d'historique véhicule avec résumé statistique.
    Compatible avec l'ancienne version qui fonctionnait.
    """
    from django.core.paginator import Paginator
    from django.db.models import Sum, Count, Q
    from inventaire.models_pesage import AmendeEmise
    from inventaire.utils_pesage import (
        normalize_immatriculation, 
        rechercher_historique_vehicule as rechercher_vehicule,
        get_resume_historique_vehicule
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
        
        # Recherche des amendes (retourne un QuerySet, pas une liste)
        resultats_qs = rechercher_vehicule(
            immatriculation=immatriculation,
            transporteur=transporteur,
            operateur=operateur
        )
        
        # Debug: afficher le nombre de résultats
        logger.info(f"Recherche historique: immat={immatriculation}, transp={transporteur}, op={operateur}")
        logger.info(f"Nombre de résultats: {resultats_qs.count()}")
        
        # Pagination
        paginator = Paginator(resultats_qs, 25)
        page_number = request.GET.get('page')
        resultats = paginator.get_page(page_number)
        
        # Calculer le résumé SI recherche par immatriculation
        if immatriculation:
            resume = get_resume_historique_vehicule(immatriculation)
            logger.info(f"Résumé: {resume}")
    
    context = {
        'resultats': resultats,
        'resume': resume,
        'immatriculation': immatriculation,
        'transporteur': transporteur,
        'operateur': operateur,
        'recherche_effectuee': recherche_effectuee,
    }
    
    return render(request, 'pesage/recherche_historique.html', context)

    
@pesage_access_required
@login_required
def detail_historique_vehicule(request, immatriculation):
    """
    Affiche l'historique complet d'un véhicule par son immatriculation
    """
    from django.core.paginator import Paginator
    from django.db.models import Sum, Count, Q
    from inventaire.utils_pesage import normalize_immatriculation
    from inventaire.models_pesage import AmendeEmise
    from accounts.models import Poste
    
    # Normaliser l'immatriculation
    immat_normalise = normalize_immatriculation(immatriculation)
    
    # Récupérer toutes les amendes pour ce véhicule
    amendes_qs = AmendeEmise.objects.filter(
        immatriculation_normalise=immat_normalise
    ).select_related('station', 'saisi_par', 'valide_par').order_by('-date_heure_emission')
    
    # Appliquer les filtres
    station_filter = request.GET.get('station')
    statut_filter = request.GET.get('statut')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    
    if station_filter:
        amendes_qs = amendes_qs.filter(station_id=station_filter)
    
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
    
    # Résumé statistique global (sans filtres pour avoir les vraies stats)
    amendes_all = AmendeEmise.objects.filter(immatriculation_normalise=immat_normalise)
    
    resume = {
        'total_amendes': amendes_all.count(),
        'total_payees': amendes_all.filter(statut='paye').count(),
        'total_non_payees': amendes_all.exclude(statut='paye').count(),
        'montant_total': amendes_all.aggregate(total=Sum('montant_amende'))['total'] or 0,
        'montant_paye': amendes_all.filter(statut='paye').aggregate(total=Sum('montant_amende'))['total'] or 0,
        'montant_impaye': amendes_all.exclude(statut='paye').aggregate(total=Sum('montant_amende'))['total'] or 0,
        'stations_distinctes': amendes_all.values('station').distinct().count(),
    }
    
    # Stats par station
    stats_par_station = AmendeEmise.objects.filter(
        immatriculation_normalise=immat_normalise
    ).values('station__nom').annotate(
        total=Count('id'),
        payees=Count('id', filter=Q(statut='paye')),
        non_payees=Count('id', filter=~Q(statut='paye'))
    ).order_by('-total')
    
    # Liste des stations pour le filtre
    stations_list = Poste.objects.filter(
        type='pesage',
        is_active=True
    ).order_by('nom')
    
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
    }
    
    return render(request, 'pesage/detail_historique_vehicule.html', context)
# ===================================================================
# VÉRIFICATION AVANT VALIDATION DE PAIEMENT
# ===================================================================

@regisseur_required
def verifier_avant_validation(request, pk):
    """
    Vérifie si un véhicule a des amendes non payées dans d'autres stations
    AVANT de valider un paiement.
    
    URL: /pesage/verifier-avant-validation/<pk>/
    
    Retourne:
        - Si pas d'amende non payée ailleurs: redirige vers validation
        - Si amendes non payées: affiche page de blocage avec options
    """
    user = request.user
    station = get_user_station(user) if not is_admin(user) else None
    
    # Récupérer l'amende
    if is_admin(user):
        amende = get_object_or_404(AmendeEmise, pk=pk)
        station_actuelle = amende.station
    else:
        amende = get_object_or_404(AmendeEmise, pk=pk, station=station)
        station_actuelle = station
    
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
        # Rediriger vers la validation normale
        return redirect('inventaire:valider_paiement_direct', pk=pk)
    
    # Il y a des amendes non payées ailleurs
    # Vérifier s'il existe des demandes de confirmation en attente ou confirmées
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
        # Toutes les confirmations sont obtenues → validation possible
        return redirect('inventaire:valider_paiement_direct', pk=pk)
    
    context = {
        'amende': amende,
        'amendes_impayees': amendes_impayees,
        'demandes_existantes': demandes_existantes,
        'station': station_actuelle,
        'is_admin': is_admin(user),
        'title': _("Validation bloquée - Amendes non payées"),
    }
    
    return render(request, 'pesage/validation_paiement_bloquee.html', context)


@regisseur_required
@require_POST
def valider_paiement_direct(request, pk):
    """
    Valide directement un paiement (après vérification ou avec confirmations).
    
    URL: /pesage/valider-paiement-direct/<pk>/
    """
    user = request.user
    station = get_user_station(user) if not is_admin(user) else None
    
    # Récupérer l'amende
    if is_admin(user):
        amende = get_object_or_404(AmendeEmise, pk=pk)
    else:
        amende = get_object_or_404(AmendeEmise, pk=pk, station=station)
    
    if amende.statut == 'paye':
        messages.warning(request, _("Cette amende a déjà été validée."))
        return redirect('inventaire:liste_amendes')
    
    # Valider le paiement
    amende.statut = 'paye'
    amende.date_paiement = timezone.now()
    amende.valide_par = user
    amende.save()
    
    messages.success(request,
        _("Paiement validé pour l'amende %(numero)s - Montant: %(montant)s FCFA") % {
            'numero': amende.numero_ticket,
            'montant': f"{amende.montant_amende:,.0f}".replace(',', ' ')
        })
    
    logger.info(
        f"Paiement validé par {user.username} - Amende {amende.numero_ticket} "
        f"- {amende.montant_amende} FCFA"
    )
    
    return redirect('inventaire:liste_amendes_a_valider')


# ===================================================================
# GESTION DES DEMANDES DE CONFIRMATION
# ===================================================================

@regisseur_required
def creer_demande_confirmation(request, amende_pk, amende_bloquante_pk):
    """
    Crée une demande de confirmation auprès d'une autre station.
    
    URL: /pesage/creer-demande-confirmation/<amende_pk>/<amende_bloquante_pk>/
    """
    user = request.user
    station = get_user_station(user) if not is_admin(user) else None
    
    # Récupérer l'amende à valider
    if is_admin(user):
        amende_a_valider = get_object_or_404(AmendeEmise, pk=amende_pk)
        station_demandeur = amende_a_valider.station
    else:
        amende_a_valider = get_object_or_404(AmendeEmise, pk=amende_pk, station=station)
        station_demandeur = station
    
    # Récupérer l'amende bloquante
    amende_non_payee = get_object_or_404(AmendeEmise, pk=amende_bloquante_pk, statut='non_paye')
    
    # Vérifier que l'amende bloquante est dans une AUTRE station
    if amende_non_payee.station == station_demandeur:
        messages.error(request, _("L'amende bloquante doit être dans une autre station."))
        return redirect('inventaire:verifier_avant_validation', pk=amende_pk)
    
    # Vérifier si une demande existe déjà
    demande_existante = DemandeConfirmationPaiement.existe_demande_en_attente(
        amende_a_valider, amende_non_payee
    )
    
    if demande_existante:
        messages.warning(request, 
            _("Une demande de confirmation existe déjà (Réf: %(ref)s).") % {
                'ref': demande_existante.reference
            })
        return redirect('inventaire:detail_demande_confirmation', pk=demande_existante.pk)
    
    if request.method == 'POST':
        commentaire = request.POST.get('commentaire', '').strip()
        
        # Créer la demande
        demande = DemandeConfirmationPaiement(
            station_demandeur=station_demandeur,
            regisseur_demandeur=user,
            amende_a_valider=amende_a_valider,
            station_concernee=amende_non_payee.station,
            amende_non_payee=amende_non_payee,
            commentaire_demande=commentaire,
            vehicule_immatriculation=amende_a_valider.immatriculation,
            vehicule_transporteur=amende_a_valider.transporteur,
        )
        demande.save()
        
        messages.success(request,
            _("Demande de confirmation créée (Réf: %(ref)s). "
              "La station %(station)s doit confirmer.") % {
                'ref': demande.reference,
                'station': amende_non_payee.station.nom
            })
        
        logger.info(
            f"Demande confirmation créée par {user.username} - "
            f"Réf: {demande.reference} - Véhicule: {demande.vehicule_immatriculation}"
        )
        
        return redirect('inventaire:mes_demandes_confirmation')
    
    context = {
        'amende_a_valider': amende_a_valider,
        'amende_non_payee': amende_non_payee,
        'station_demandeur': station_demandeur,
        'station': station,
        'is_admin': is_admin(user),
        'title': _("Créer une demande de confirmation"),
    }
    
    return render(request, 'pesage/creer_demande_confirmation.html', context)


@regisseur_required
def mes_demandes_confirmation(request):
    """
    Liste des demandes de confirmation envoyées par ma station.
    
    URL: /pesage/mes-demandes-confirmation/
    """
    user = request.user
    station = get_user_station(user) if not is_admin(user) else None
    
    if is_admin(user):
        # Admin voit toutes les demandes
        demandes = DemandeConfirmationPaiement.objects.all()
    else:
        demandes = DemandeConfirmationPaiement.get_demandes_envoyees_par_station(station)
    
    # Filtrer par statut
    statut_filter = request.GET.get('statut')
    if statut_filter:
        demandes = demandes.filter(statut=statut_filter)
    
    # Pagination
    paginator = Paginator(demandes, 20)
    page = request.GET.get('page')
    demandes_page = paginator.get_page(page)
    
    context = {
        'demandes': demandes_page,
        'statut_filter': statut_filter,
        'statuts': StatutDemandeConfirmation.choices,
        'station': station,
        'is_admin': is_admin(user),
        'title': _("Mes demandes de confirmation"),
    }
    
    return render(request, 'pesage/mes_demandes_confirmation.html', context)


@regisseur_required
def demandes_confirmation_a_traiter(request):
    """
    Liste des demandes de confirmation à traiter (reçues par ma station).
    
    URL: /pesage/demandes-confirmation-a-traiter/
    """
    user = request.user
    station = get_user_station(user) if not is_admin(user) else None
    
    if is_admin(user):
        # Admin: sélection de station requise
        station_id = request.GET.get('station')
        if station_id:
            try:
                station = Poste.objects.get(pk=station_id, type='pesage')
            except Poste.DoesNotExist:
                station = None
        
        if not station:
            stations = Poste.objects.filter(type='pesage', is_active=True).order_by('nom')
            # Compter les demandes en attente par station
            for s in stations:
                s.nb_demandes_attente = DemandeConfirmationPaiement.objects.filter(
                    station_concernee=s,
                    statut=StatutDemandeConfirmation.EN_ATTENTE
                ).count()
            
            context = {
                'stations': stations,
                'is_admin': True,
                'title': _("Sélectionner une station"),
            }
            return render(request, 'pesage/selectionner_station_confirmation.html', context)
    
    # Récupérer les demandes en attente pour cette station
    demandes_attente = DemandeConfirmationPaiement.get_demandes_en_attente_pour_station(station)
    
    # Récupérer aussi les demandes déjà traitées
    demandes_traitees = DemandeConfirmationPaiement.objects.filter(
        station_concernee=station
    ).exclude(
        statut=StatutDemandeConfirmation.EN_ATTENTE
    ).order_by('-date_reponse')[:20]
    
    context = {
        'demandes_attente': demandes_attente,
        'demandes_traitees': demandes_traitees,
        'station': station,
        'is_admin': is_admin(user),
        'title': _("Demandes de confirmation à traiter"),
    }
    
    return render(request, 'pesage/demandes_confirmation_a_traiter.html', context)


@regisseur_required
def detail_demande_confirmation(request, pk):
    """
    Détail d'une demande de confirmation.
    
    URL: /pesage/demande-confirmation/<pk>/
    """
    user = request.user
    station = get_user_station(user) if not is_admin(user) else None
    
    demande = get_object_or_404(
        DemandeConfirmationPaiement.objects.select_related(
            'station_demandeur', 'regisseur_demandeur',
            'station_concernee', 'regisseur_confirmeur',
            'amende_a_valider', 'amende_non_payee',
            'amende_a_valider__station', 'amende_non_payee__station'
        ),
        pk=pk
    )
    
    # Vérifier l'accès
    if not is_admin(user):
        if station not in [demande.station_demandeur, demande.station_concernee]:
            messages.error(request, _("Vous n'avez pas accès à cette demande."))
            return redirect('common:dashboard')
    
    # Déterminer si l'utilisateur peut traiter la demande
    peut_traiter = (
        is_admin(user) or 
        (station == demande.station_concernee and 
         user.habilitation in VALIDATION_ROLES and
         demande.peut_etre_traitee)
    )
    
    # Historique du véhicule
    historique = AmendeEmise.objects.filter(
        immatriculation_normalise__iexact=demande.amende_a_valider.immatriculation_normalise
    ).select_related('station').order_by('-date_heure_emission')[:10]
    
    context = {
        'demande': demande,
        'peut_traiter': peut_traiter,
        'historique': historique,
        'station': station,
        'is_admin': is_admin(user),
        'title': f"Demande {demande.reference}",
    }
    
    return render(request, 'pesage/detail_demande_confirmation.html', context)


@regisseur_required
@require_POST
def traiter_demande_confirmation(request, pk):
    """
    Traite une demande de confirmation (confirmer ou refuser).
    
    URL: /pesage/traiter-demande-confirmation/<pk>/
    """
    user = request.user
    station = get_user_station(user) if not is_admin(user) else None
    
    demande = get_object_or_404(DemandeConfirmationPaiement, pk=pk)
    
    # Vérifier les permissions
    if not is_admin(user) and station != demande.station_concernee:
        messages.error(request, _("Vous ne pouvez pas traiter cette demande."))
        return redirect('inventaire:detail_demande_confirmation', pk=pk)
    
    if not demande.peut_etre_traitee:
        messages.error(request, _("Cette demande ne peut plus être traitée."))
        return redirect('inventaire:detail_demande_confirmation', pk=pk)
    
    action = request.POST.get('action')
    commentaire = request.POST.get('commentaire', '').strip()
    
    if action == 'confirmer':
        if demande.confirmer(user, commentaire):
            messages.success(request,
                _("Demande %(ref)s CONFIRMÉE. Le paiement est maintenant autorisé.") % {
                    'ref': demande.reference
                })
        else:
            messages.error(request, _("Erreur lors de la confirmation."))
    
    elif action == 'refuser':
        if not commentaire:
            messages.error(request, _("Un commentaire est requis pour refuser une demande."))
            return redirect('inventaire:detail_demande_confirmation', pk=pk)
        
        if demande.refuser(user, commentaire):
            messages.success(request,
                _("Demande %(ref)s REFUSÉE. Le paiement reste bloqué.") % {
                    'ref': demande.reference
                })
        else:
            messages.error(request, _("Erreur lors du refus."))
    
    else:
        messages.error(request, _("Action non reconnue."))
    
    return redirect('inventaire:demandes_confirmation_a_traiter')


# ===================================================================
# API ENDPOINTS
# ===================================================================

@pesage_access_required
@require_GET
def api_recherche_historique(request):
    """
    API de recherche rapide d'historique véhicule.
    
    GET params: q (recherche globale), immat, transporteur, operateur
    
    Returns: JSON avec résultats
    """
    q = request.GET.get('q', '').strip()
    immat = request.GET.get('immat', '').strip()
    transporteur = request.GET.get('transporteur', '').strip()
    operateur = request.GET.get('operateur', '').strip()
    
    # Si recherche globale
    if q and not (immat or transporteur or operateur):
        # Rechercher dans tous les champs
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


@regisseur_required
@require_GET
def api_verifier_impaye_autres_stations(request):
    """
    API pour vérifier les amendes impayées dans d'autres stations.
    
    GET params: immatriculation, station_actuelle (ID)
    
    Returns: JSON avec liste des amendes impayées
    """
    immatriculation = request.GET.get('immatriculation', '').strip()
    station_id = request.GET.get('station_actuelle')
    
    if not immatriculation:
        return JsonResponse({'error': 'Immatriculation requise'}, status=400)
    
    try:
        station_actuelle = Poste.objects.get(pk=station_id, type='pesage') if station_id else None
    except Poste.DoesNotExist:
        station_actuelle = None
    
    a_impaye, amendes = verifier_amendes_non_payees_autres_stations(
        immatriculation, station_actuelle
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


@regisseur_required
@require_GET  
def api_count_demandes_attente(request):
    """
    API pour compter les demandes en attente pour une station.
    Utile pour les badges de notification.
    """
    user = request.user
    station = get_user_station(user) if not is_admin(user) else None
    
    if is_admin(user):
        station_id = request.GET.get('station')
        if station_id:
            try:
                station = Poste.objects.get(pk=station_id, type='pesage')
            except Poste.DoesNotExist:
                return JsonResponse({'count': 0})
        else:
            # Compter pour toutes les stations
            count = DemandeConfirmationPaiement.objects.filter(
                statut=StatutDemandeConfirmation.EN_ATTENTE
            ).count()
            return JsonResponse({'count': count})
    
    if not station:
        return JsonResponse({'count': 0})
    
    count = DemandeConfirmationPaiement.objects.filter(
        station_concernee=station,
        statut=StatutDemandeConfirmation.EN_ATTENTE
    ).count()
    
    return JsonResponse({'count': count})