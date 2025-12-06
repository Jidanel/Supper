# ===================================================================
# inventaire/views_pesage.py - Vues pour le module Pesage SUPPER
# Gestion des permissions par rôle:
# - Admin: accès complet à toutes les stations (doit sélectionner)
# - Chef station pesage: accès complet à SA station uniquement
# - Régisseur pesage: validation/quittancements sur SA station
# - Chef équipe pesage: saisie amendes/pesées sur SA station
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
from django.db.models.functions import TruncDate
from django.views.decorators.http import require_POST, require_GET
from functools import wraps
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import json
import logging

from .models_pesage import (
    AmendeEmise, PeseesJournalieres, QuittancementPesage,
    StatistiquesPesagePeriodique, AmendeEvent
)
from .forms_pesage import (
    AmendeEmiseForm, PeseesJournalieresForm, QuittancementPesageForm,
    RechercheAmendeForm, ValidationPaiementForm, FiltreStatistiquesForm
)
from accounts.models import Poste

logger = logging.getLogger('supper')


# ===================================================================
# CONSTANTES RÔLES PESAGE
# ===================================================================

PESAGE_ROLES = ['chef_equipe_pesage', 'regisseur_pesage', 'chef_station_pesage']
SAISIE_ROLES = ['chef_equipe_pesage', 'chef_station_pesage']  # Peuvent saisir amendes/pesées
VALIDATION_ROLES = ['regisseur_pesage', 'chef_station_pesage']  # Peuvent valider paiements


# ===================================================================
# FONCTIONS UTILITAIRES
# ===================================================================

def is_admin(user):
    """Vérifie si l'utilisateur est administrateur"""
    return user.is_superuser or user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info']


def get_user_station(user):
    """
    Retourne la station de pesage de l'utilisateur.
    
    Returns:
        - None si admin (accès à toutes les stations)
        - Poste si utilisateur affecté à une station pesage
        - False si utilisateur non autorisé
    """
    # Admin = accès à toutes les stations
    if is_admin(user):
        return None
    
    # Vérifier que l'utilisateur a un rôle pesage
    if user.habilitation not in PESAGE_ROLES:
        return False
    
    # Vérifier l'affectation à une station pesage
    if user.poste_affectation and user.poste_affectation.type == 'pesage':
        return user.poste_affectation
    
    return False


def get_stations_accessibles(user):
    """
    Retourne le queryset des stations accessibles pour l'utilisateur.
    """
    if is_admin(user):
        return Poste.objects.filter(type='pesage', is_active=True).order_by('region', 'nom')
    
    station = get_user_station(user)
    if station and station is not False:
        return Poste.objects.filter(id=station.id)
    
    return Poste.objects.none()


def valider_date_saisie(date_cible):
    """
    Valide qu'une date n'est pas dans le futur.
    
    Returns:
        tuple (is_valid: bool, error_message: str or None)
    """
    today = timezone.now().date()
    
    if date_cible > today:
        return False, _("Impossible de saisir des données pour une date future.")
    
    return True, None


def get_station_context(request, user):
    """
    Récupère la station pour le contexte de la vue.
    Gère la sélection pour admin et l'affectation pour les autres.
    
    Returns:
        tuple (station, redirect_response)
        - (station, None) si station trouvée
        - (None, redirect) si admin doit sélectionner une station
    """
    # Utilisateur non-admin: retourner sa station d'affectation
    if not is_admin(user):
        station = get_user_station(user)
        if station is False:
            messages.error(request, _("Vous devez être affecté à une station de pesage."))
            return None, redirect('common:dashboard')
        return station, None
    
    # Admin: chercher la station dans GET, POST ou session
    station_id = (
        request.GET.get('station') or 
        request.POST.get('station') or 
        request.session.get('station_pesage_id')
    )
    
    if station_id:
        try:
            station = Poste.objects.get(pk=station_id, type='pesage', is_active=True)
            # Sauvegarder en session pour les requêtes suivantes
            request.session['station_pesage_id'] = station.id
            return station, None
        except Poste.DoesNotExist:
            # Station invalide, nettoyer la session
            request.session.pop('station_pesage_id', None)
    
    # Pas de station - retourner None (admin peut voir global ou doit sélectionner)
    return None, None


def get_date_debut_journee(date_cible):
    """Retourne le début de la journée pesage (9h)"""
    return timezone.make_aware(datetime.combine(date_cible, time(9, 0, 0)))


def get_date_fin_journee(date_cible):
    """Retourne la fin de la journée pesage (9h jour suivant)"""
    return timezone.make_aware(datetime.combine(date_cible + timedelta(days=1), time(9, 0, 0)))


def get_journee_pesage_actuelle():
    """
    Retourne la date de la journée pesage en cours.
    Avant 9h = journée précédente
    """
    now = timezone.now()
    if now.time() < time(9, 0):
        return now.date() - timedelta(days=1)
    return now.date()


def get_periode_dates(periode, date_ref=None):
    """
    Calcule les dates de début et fin pour une période donnée.
    """
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
# DÉCORATEURS DE PERMISSION
# ===================================================================

def pesage_access_required(view_func):
    """Vérifie que l'utilisateur a accès au module pesage."""
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


def saisie_pesage_required(view_func):
    """Vérifie que l'utilisateur peut saisir des données pesage."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        
        if is_admin(user):
            return view_func(request, *args, **kwargs)
        
        if user.habilitation not in SAISIE_ROLES:
            messages.error(request, _("Accès réservé aux chefs d'équipe et chefs de station pesage."))
            return redirect('common:dashboard')
        
        station = get_user_station(user)
        if station is False:
            messages.error(request, _("Vous devez être affecté à une station de pesage."))
            return redirect('common:dashboard')
        
        return view_func(request, *args, **kwargs)
    return wrapper


def validation_pesage_required(view_func):
    """Vérifie que l'utilisateur peut valider des paiements."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        
        if is_admin(user):
            return view_func(request, *args, **kwargs)
        
        if user.habilitation not in VALIDATION_ROLES:
            messages.error(request, _("Accès réservé aux régisseurs et chefs de station pesage."))
            return redirect('common:dashboard')
        
        station = get_user_station(user)
        if station is False:
            messages.error(request, _("Vous devez être affecté à une station de pesage."))
            return redirect('common:dashboard')
        
        return view_func(request, *args, **kwargs)
    return wrapper


# ===================================================================
# SÉLECTION DE STATION (ADMIN UNIQUEMENT)
# ===================================================================

@login_required
def selectionner_station(request):
    """
    Page intermédiaire pour que les admins sélectionnent une station.
    Redirige vers l'action demandée après sélection.
    """
    user = request.user
    
    # Cette page est réservée aux admins
    if not is_admin(user):
        messages.info(request, _("Vous êtes automatiquement affecté à votre station."))
        return redirect('common:dashboard')
    
    # Action demandée (pour la redirection après sélection)
    action = request.GET.get('action', request.POST.get('action', 'liste_amendes'))
    
    # Mapping des actions vers les URLs
    action_urls = {
        'saisir_amende': 'inventaire:saisir_amende',
        'saisir_pesees': 'inventaire:saisir_pesees',
        'saisir_quittancement': 'inventaire:saisir_quittancement',
        'liste_amendes': 'inventaire:liste_amendes',
        'amendes_a_valider': 'inventaire:liste_amendes_a_valider',
        'historique_pesees': 'inventaire:historique_pesees',
        'liste_quittancements': 'inventaire:liste_quittancements',
        'statistiques': 'inventaire:statistiques_pesage',
        'recettes': 'inventaire:recettes_pesage',
    }
    
    if request.method == 'POST':
        station_id = request.POST.get('station')
        
        if not station_id:
            messages.error(request, _("Veuillez sélectionner une station."))
        else:
            try:
                station = Poste.objects.get(pk=station_id, type='pesage', is_active=True)
                # Sauvegarder en session
                request.session['station_pesage_id'] = station.id
                
                # Rediriger vers l'action demandée
                url_name = action_urls.get(action, 'inventaire:liste_amendes')
                return redirect(f"{reverse(url_name)}?station={station.id}")
                
            except Poste.DoesNotExist:
                messages.error(request, _("Station invalide."))
    
    # Récupérer les stations disponibles
    stations = Poste.objects.filter(type='pesage', is_active=True).order_by('region', 'nom')
    
    context = {
        'stations': stations,
        'action': action,
        'title': _('Sélectionner une station'),
    }
    
    return render(request, 'pesage/selectionner_station.html', context)


# ===================================================================
# GESTION DES AMENDES - SAISIE
# ===================================================================

@saisie_pesage_required
def saisir_amende(request):
    """
    Saisie d'une nouvelle amende.
    - Admin: doit sélectionner une station via page intermédiaire
    - Chef équipe/station: saisie sur sa station uniquement
    """
    user = request.user
    today = timezone.now().date()
    stations_accessibles = get_stations_accessibles(user)
    
    # Récupérer la station selon le contexte
    station, redirect_response = get_station_context(request, user)
    
    # Si admin sans station sélectionnée, rediriger vers sélection
    if is_admin(user) and station is None:
        return redirect(f"{reverse('inventaire:selectionner_station')}?action=saisir_amende")
    
    if redirect_response:
        return redirect_response
    
    if request.method == 'POST':
        form = AmendeEmiseForm(request.POST)
        
        # Récupérer et valider la date d'émission si fournie
        date_emission_str = request.POST.get('date_emission')
        if date_emission_str:
            try:
                date_emission = datetime.strptime(date_emission_str, '%Y-%m-%d').date()
                is_valid, error_msg = valider_date_saisie(date_emission)
                if not is_valid:
                    messages.error(request, error_msg)
                    return render(request, 'pesage/saisir_amende.html', {
                        'form': form,
                        'station': station,
                        'is_admin': is_admin(user),
                        'today': today,
                        'title': _('Saisir une amende'),
                    })
            except ValueError:
                pass  # Utiliser la date actuelle
        
        if form.is_valid():
            amende = form.save(commit=False)
            amende.station = station
            amende.saisi_par = user
            amende.statut = 'non_paye'
            amende.date_emission = timezone.now()
            amende.save()
            
            # Créer l'événement d'émission
            AmendeEvent.objects.create(
                amende=amende,
                type_event='EMISSION',
                utilisateur=user,
                details=f"Émission amende {amende.numero_ticket} - {amende.montant_amende} FCFA"
            )
            
            messages.success(
                request,
                _("Amende %(numero)s créée avec succès. Montant: %(montant)s FCFA") % {
                    'numero': amende.numero_ticket,
                    'montant': f"{amende.montant_amende:,.0f}".replace(',', ' ')
                }
            )
            
            logger.info(
                f"Amende {amende.numero_ticket} créée par {user.username} "
                f"- Station: {station.nom} - Montant: {amende.montant_amende} FCFA"
            )
            
            # Rediriger selon le bouton cliqué
            if 'saisir_autre' in request.POST:
                return redirect(f"{reverse('inventaire:saisir_amende')}?station={station.pk}")
            
            return redirect('inventaire:liste_amendes')
    else:
        form = AmendeEmiseForm()
    
    context = {
        'form': form,
        'station': station,
        'is_admin': is_admin(user),
        'today': today,
        'title': _('Saisir une amende'),
    }
    
    return render(request, 'pesage/saisir_amende.html', context)


# ===================================================================
# GESTION DES AMENDES - LISTE ET DÉTAIL
# ===================================================================

@pesage_access_required
def liste_amendes(request):
    """
    Liste des amendes avec filtres de recherche.
    """
    user = request.user
    stations_accessibles = get_stations_accessibles(user)
    
    # Récupérer la station (peut être None pour admin = vue globale)
    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response
    
    # Base queryset
    if station is None and is_admin(user):
        # Admin sans station = vue globale
        queryset = AmendeEmise.objects.all()
        # Filtre optionnel par station
        station_filter = request.GET.get('station_filter')
        if station_filter:
            queryset = queryset.filter(station_id=station_filter)
    elif station:
        queryset = AmendeEmise.objects.filter(station=station)
    else:
        queryset = AmendeEmise.objects.none()
    
    # Filtres de recherche
    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(
            Q(numero_ticket__icontains=query) |
            Q(immatriculation__icontains=query) |
            Q(nom_transporteur__icontains=query) |
            Q(telephone_transporteur__icontains=query)
        )
    
    statut_filter = request.GET.get('statut')
    if statut_filter:
        queryset = queryset.filter(statut=statut_filter)
    
    type_infraction = request.GET.get('type_infraction')
    if type_infraction:
        queryset = queryset.filter(type_infraction=type_infraction)
    
    # Filtre par dates
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    if date_debut:
        queryset = queryset.filter(date_emission__date__gte=date_debut)
    if date_fin:
        queryset = queryset.filter(date_emission__date__lte=date_fin)
    
    queryset = queryset.select_related('station', 'saisi_par').order_by('-date_emission')
    
    # Statistiques rapides
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
        'is_admin': is_admin(user),
        'query': query,
        'statut_filter': statut_filter,
        'type_infraction': type_infraction,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'station_filter': request.GET.get('station_filter', ''),
        'title': _('Liste des amendes'),
    }
    
    return render(request, 'pesage/liste_amendes.html', context)


@pesage_access_required
def detail_amende(request, pk):
    """Détail d'une amende avec historique des événements."""
    user = request.user
    station, _ = get_station_context(request, user)
    
    # Récupérer l'amende selon les droits
    if is_admin(user):
        amende = get_object_or_404(AmendeEmise, pk=pk)
    else:
        amende = get_object_or_404(AmendeEmise, pk=pk, station=station)
    
    # Historique des événements
    events = amende.events.select_related('utilisateur').order_by('-date_event')
    
    context = {
        'amende': amende,
        'events': events,
        'station': station or amende.station,
        'is_admin': is_admin(user),
        'title': f"Amende {amende.numero_ticket}",
    }
    
    return render(request, 'pesage/detail_amende.html', context)


# ===================================================================
# VALIDATION DES PAIEMENTS
# ===================================================================

@validation_pesage_required
def liste_amendes_a_valider(request):
    """Liste des amendes en attente de validation de paiement."""
    user = request.user
    stations_accessibles = get_stations_accessibles(user)
    
    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response
    
    # Base queryset - amendes non payées
    if station is None and is_admin(user):
        queryset = AmendeEmise.objects.filter(statut='non_paye')
        station_filter = request.GET.get('station_filter')
        if station_filter:
            queryset = queryset.filter(station_id=station_filter)
    elif station:
        queryset = AmendeEmise.objects.filter(station=station, statut='non_paye')
    else:
        queryset = AmendeEmise.objects.none()
    
    queryset = queryset.select_related('station', 'saisi_par').order_by('-date_emission')
    
    # Total à recouvrer
    total_a_recouvrer = queryset.aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
    
    # Pagination
    paginator = Paginator(queryset, 25)
    page = request.GET.get('page')
    amendes = paginator.get_page(page)
    
    context = {
        'amendes': amendes,
        'station': station,
        'stations_accessibles': stations_accessibles,
        'total_a_recouvrer': total_a_recouvrer,
        'count_total': queryset.count(),
        'is_admin': is_admin(user),
        'station_filter': request.GET.get('station_filter', ''),
        'title': _('Amendes à valider'),
    }
    
    return render(request, 'pesage/amendes_a_valider.html', context)


@validation_pesage_required
@require_POST
def valider_paiement(request, pk):
    """Valide le paiement d'une amende unique."""
    user = request.user
    station, _ = get_station_context(request, user)
    
    if is_admin(user):
        amende = get_object_or_404(AmendeEmise, pk=pk)
    else:
        amende = get_object_or_404(AmendeEmise, pk=pk, station=station)
    
    if amende.statut == 'paye':
        messages.warning(request, _("Cette amende a déjà été validée."))
        return redirect('inventaire:liste_amendes_a_valider')
    
    amende.statut = 'paye'
    amende.date_paiement = timezone.now()
    amende.valide_par = user
    amende.save()
    
    AmendeEvent.objects.create(
        amende=amende,
        type_event='PAIEMENT',
        utilisateur=user,
        details=f"Paiement validé - {amende.montant_amende} FCFA"
    )
    
    messages.success(
        request,
        _("Paiement validé pour l'amende %(numero)s - Montant: %(montant)s FCFA") % {
            'numero': amende.numero_ticket,
            'montant': f"{amende.montant_amende:,.0f}".replace(',', ' ')
        }
    )
    
    logger.info(
        f"Paiement validé par {user.username} - Amende {amende.numero_ticket} "
        f"- {amende.montant_amende} FCFA"
    )
    
    return redirect('inventaire:liste_amendes_a_valider')


@validation_pesage_required
@require_POST
def valider_paiements_masse(request):
    """Valide plusieurs paiements en une fois."""
    user = request.user
    station, _ = get_station_context(request, user)
    
    amende_ids = request.POST.getlist('amendes')
    
    if not amende_ids:
        messages.warning(request, _("Aucune amende sélectionnée."))
        return redirect('inventaire:liste_amendes_a_valider')
    
    count_success = 0
    montant_total = Decimal('0')
    
    for amende_id in amende_ids:
        try:
            if is_admin(user):
                amende = AmendeEmise.objects.get(pk=amende_id, statut='non_paye')
            else:
                amende = AmendeEmise.objects.get(pk=amende_id, station=station, statut='non_paye')
            
            amende.statut = 'paye'
            amende.date_paiement = timezone.now()
            amende.valide_par = user
            amende.save()
            
            AmendeEvent.objects.create(
                amende=amende,
                type_event='PAIEMENT',
                utilisateur=user,
                details=f"Paiement validé (masse) - {amende.montant_amende} FCFA"
            )
            
            count_success += 1
            montant_total += amende.montant_amende
            
        except AmendeEmise.DoesNotExist:
            continue
    
    if count_success > 0:
        messages.success(
            request,
            _("%(count)d paiement(s) validé(s) - Total: %(montant)s FCFA") % {
                'count': count_success,
                'montant': f"{montant_total:,.0f}".replace(',', ' ')
            }
        )
        
        logger.info(
            f"Validation en masse par {user.username} - {count_success} amendes "
            f"- Total: {montant_total} FCFA"
        )
    else:
        messages.warning(request, _("Aucun paiement n'a pu être validé."))
    
    return redirect('inventaire:liste_amendes_a_valider')


# ===================================================================
# PESÉES JOURNALIÈRES
# ===================================================================

@saisie_pesage_required
def saisir_pesees(request):
    """
    Saisie du nombre de pesées journalières.
    Une seule saisie par jour et par station, non modifiable.
    BLOQUE LES DATES FUTURES.
    """
    user = request.user
    today = timezone.now().date()
    stations_accessibles = get_stations_accessibles(user)
    
    # Récupérer la station
    station, redirect_response = get_station_context(request, user)
    
    # Si admin sans station, rediriger vers sélection
    if is_admin(user) and station is None:
        return redirect(f"{reverse('inventaire:selectionner_station')}?action=saisir_pesees")
    
    if redirect_response:
        return redirect_response
    
    # Date sélectionnée (par défaut aujourd'hui)
    date_str = request.GET.get('date') or request.POST.get('date')
    if date_str:
        try:
            date_selectionnee = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            date_selectionnee = today
    else:
        date_selectionnee = today
    
    # VALIDATION: Bloquer les dates futures
    is_valid, error_msg = valider_date_saisie(date_selectionnee)
    if not is_valid:
        messages.error(request, error_msg)
        date_selectionnee = today
    
    # Vérifier si déjà saisi
    pesee_existante = PeseesJournalieres.objects.filter(
        station=station, date=date_selectionnee
    ).first()
    deja_saisi = pesee_existante is not None
    
    if request.method == 'POST' and not deja_saisi:
        # Re-valider la date dans le POST
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
            
            messages.success(
                request,
                _("Pesées du %(date)s enregistrées: %(nombre)d pesées") % {
                    'date': pesees.date.strftime('%d/%m/%Y'),
                    'nombre': pesees.nombre_pesees
                }
            )
            
            logger.info(
                f"Pesées saisies par {user.username} - Station: {station.nom} "
                f"- Date: {pesees.date} - Nombre: {pesees.nombre_pesees}"
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
        'is_admin': is_admin(user),
        'title': _('Saisir les pesées du jour'),
    }
    
    return render(request, 'pesage/saisir_pesees.html', context)


@pesage_access_required
def historique_pesees(request):
    """Historique des pesées journalières."""
    user = request.user
    stations_accessibles = get_stations_accessibles(user)
    
    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response
    
    # Base queryset
    if station is None and is_admin(user):
        queryset = PeseesJournalieres.objects.all()
        station_filter = request.GET.get('station_filter')
        if station_filter:
            queryset = queryset.filter(station_id=station_filter)
    elif station:
        queryset = PeseesJournalieres.objects.filter(station=station)
    else:
        queryset = PeseesJournalieres.objects.none()
    
    queryset = queryset.select_related('station', 'saisi_par').order_by('-date')
    
    # Statistiques
    stats = queryset.aggregate(
        total_pesees=Sum('nombre_pesees'),
        count_jours=Count('id')
    )
    
    # Pagination
    paginator = Paginator(queryset, 30)
    page = request.GET.get('page')
    pesees = paginator.get_page(page)
    
    context = {
        'pesees': pesees,
        'station': station,
        'stations_accessibles': stations_accessibles,
        'stats': stats,
        'is_admin': is_admin(user),
        'station_filter': request.GET.get('station_filter', ''),
        'title': _('Historique des pesées'),
    }
    
    return render(request, 'pesage/historique_pesees.html', context)


# ===================================================================
# QUITTANCEMENTS
# ===================================================================

@validation_pesage_required
def saisir_quittancement_pesage(request):
    """
    Saisie d'un quittancement par le régisseur.
    BLOQUE LES DATES FUTURES.
    """
    user = request.user
    today = timezone.now().date()
    stations_accessibles = get_stations_accessibles(user)
    
    station, redirect_response = get_station_context(request, user)
    
    if is_admin(user) and station is None:
        return redirect(f"{reverse('inventaire:selectionner_station')}?action=saisir_quittancement")
    
    if redirect_response:
        return redirect_response
    
    if request.method == 'POST':
        form = QuittancementPesageForm(request.POST, request.FILES)
        
        # Valider que date_fin n'est pas dans le futur
        date_fin_str = request.POST.get('date_fin')
        if date_fin_str:
            try:
                date_fin_obj = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                is_valid, error_msg = valider_date_saisie(date_fin_obj)
                if not is_valid:
                    messages.error(request, _("La date de fin ne peut pas être dans le futur."))
                    return render(request, 'pesage/saisir_quittancement.html', {
                        'form': form,
                        'station': station,
                        'is_admin': is_admin(user),
                        'today': today,
                        'title': _('Saisir un quittancement'),
                    })
            except ValueError:
                pass
        
        if form.is_valid():
            quittancement = form.save(commit=False)
            quittancement.station = station
            quittancement.saisi_par = user
            
            # Calculer le montant attendu
            montant_attendu = AmendeEmise.objects.filter(
                station=station,
                statut='paye',
                date_paiement__date__gte=quittancement.date_debut,
                date_paiement__date__lte=quittancement.date_fin
            ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
            
            quittancement.montant_attendu = montant_attendu
            quittancement.ecart = quittancement.montant_quittance - montant_attendu
            quittancement.save()
            
            messages.success(
                request,
                _("Quittancement enregistré. Montant: %(montant)s FCFA") % {
                    'montant': f"{quittancement.montant_quittance:,.0f}".replace(',', ' ')
                }
            )
            
            if quittancement.ecart != 0:
                if quittancement.ecart > 0:
                    messages.info(request, _("Écart positif de %(ecart)s FCFA") % {
                        'ecart': f"{quittancement.ecart:,.0f}".replace(',', ' ')
                    })
                else:
                    messages.warning(request, _("Écart négatif de %(ecart)s FCFA") % {
                        'ecart': f"{abs(quittancement.ecart):,.0f}".replace(',', ' ')
                    })
            
            logger.info(
                f"Quittancement saisi par {user.username} - Station: {station.nom} "
                f"- Période: {quittancement.date_debut} au {quittancement.date_fin} "
                f"- Montant: {quittancement.montant_quittance} FCFA"
            )
            
            return redirect('inventaire:liste_quittancements')
    else:
        form = QuittancementPesageForm()
    
    context = {
        'form': form,
        'station': station,
        'is_admin': is_admin(user),
        'today': today,
        'title': _('Saisir un quittancement'),
    }
    
    return render(request, 'pesage/saisir_quittancement.html', context)


@pesage_access_required
def liste_quittancements_pesage(request):
    """Liste des quittancements."""
    user = request.user
    stations_accessibles = get_stations_accessibles(user)
    
    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response
    
    if station is None and is_admin(user):
        queryset = QuittancementPesage.objects.all()
        station_filter = request.GET.get('station_filter')
        if station_filter:
            queryset = queryset.filter(station_id=station_filter)
    elif station:
        queryset = QuittancementPesage.objects.filter(station=station)
    else:
        queryset = QuittancementPesage.objects.none()
    
    queryset = queryset.select_related('station', 'saisi_par').order_by('-date_debut')
    
    stats = queryset.aggregate(
        total_quittance=Sum('montant_quittance'),
        total_attendu=Sum('montant_attendu'),
        total_ecart=Sum('ecart')
    )
    
    paginator = Paginator(queryset, 20)
    page = request.GET.get('page')
    quittancements = paginator.get_page(page)
    
    context = {
        'quittancements': quittancements,
        'station': station,
        'stations_accessibles': stations_accessibles,
        'stats': stats,
        'is_admin': is_admin(user),
        'station_filter': request.GET.get('station_filter', ''),
        'title': _('Liste des quittancements'),
    }
    
    return render(request, 'pesage/liste_quittancements.html', context)


# ===================================================================
# STATISTIQUES
# ===================================================================

@pesage_access_required
def statistiques_pesage(request):
    """Statistiques détaillées du pesage."""
    user = request.user
    stations_accessibles = get_stations_accessibles(user)
    today = timezone.now().date()
    
    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response
    
    # Paramètres de filtre
    periode = request.GET.get('periode', 'mois')
    date_debut, date_fin = get_periode_dates(periode, today)
    
    # Calculer les statistiques
    stats = {
        'emissions': 0,
        'hors_gabarit': 0,
        'montant_emis': Decimal('0'),
        'montant_recouvre': Decimal('0'),
        'reste_a_recouvrer': Decimal('0'),
        'nombre_pesees': 0,
        'taux_recouvrement': 0,
    }
    
    # Base queryset
    if station:
        amendes = AmendeEmise.objects.filter(
            station=station,
            date_emission__date__gte=date_debut,
            date_emission__date__lte=date_fin
        )
    elif is_admin(user):
        amendes = AmendeEmise.objects.filter(
            date_emission__date__gte=date_debut,
            date_emission__date__lte=date_fin
        )
    else:
        amendes = AmendeEmise.objects.none()
    
    if amendes.exists():
        agg = amendes.aggregate(
            count=Count('id'),
            hg_count=Count('id', filter=Q(type_infraction__in=['HG', 'S+HG'])),
            montant_emis=Sum('montant_amende'),
            montant_recouvre=Sum('montant_amende', filter=Q(statut='paye'))
        )
        
        stats['emissions'] = agg['count'] or 0
        stats['hors_gabarit'] = agg['hg_count'] or 0
        stats['montant_emis'] = agg['montant_emis'] or Decimal('0')
        stats['montant_recouvre'] = agg['montant_recouvre'] or Decimal('0')
        stats['reste_a_recouvrer'] = stats['montant_emis'] - stats['montant_recouvre']
        
        if stats['montant_emis'] > 0:
            stats['taux_recouvrement'] = round(
                (float(stats['montant_recouvre']) / float(stats['montant_emis'])) * 100, 2
            )
    
    # Pesées de la période
    if station:
        pesees_qs = PeseesJournalieres.objects.filter(
            station=station, date__gte=date_debut, date__lte=date_fin
        )
    elif is_admin(user):
        pesees_qs = PeseesJournalieres.objects.filter(
            date__gte=date_debut, date__lte=date_fin
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
        'is_admin': is_admin(user),
        'title': _('Statistiques Pesage'),
    }
    
    return render(request, 'pesage/statistiques.html', context)


# ===================================================================
# RECETTES PESAGE
# ===================================================================

@pesage_access_required
def recettes_pesage(request):
    """
    Suivi des recettes pesage avec recherche avancée.
    Recherche par nom, immatriculation, numéro de ticket.
    Filtres par période.
    """
    user = request.user
    stations_accessibles = get_stations_accessibles(user)
    today = timezone.now().date()
    
    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response
    
    # Paramètres de recherche
    query = request.GET.get('q', '').strip()
    periode = request.GET.get('periode', 'mois')
    type_infraction = request.GET.get('type_infraction', '')
    date_debut_param = request.GET.get('date_debut')
    date_fin_param = request.GET.get('date_fin')
    
    # Calculer les dates de période
    if date_debut_param and date_fin_param:
        try:
            date_debut = datetime.strptime(date_debut_param, '%Y-%m-%d').date()
            date_fin = datetime.strptime(date_fin_param, '%Y-%m-%d').date()
        except ValueError:
            date_debut, date_fin = get_periode_dates(periode, today)
    else:
        date_debut, date_fin = get_periode_dates(periode, today)
    
    # Base queryset - amendes payées uniquement
    if station is None and is_admin(user):
        queryset = AmendeEmise.objects.filter(statut='paye')
        station_filter = request.GET.get('station_filter')
        if station_filter:
            queryset = queryset.filter(station_id=station_filter)
    elif station:
        queryset = AmendeEmise.objects.filter(station=station, statut='paye')
    else:
        queryset = AmendeEmise.objects.none()
    
    # Filtrer par période
    queryset = queryset.filter(
        date_paiement__date__gte=date_debut,
        date_paiement__date__lte=date_fin
    )
    
    # Recherche textuelle
    if query:
        queryset = queryset.filter(
            Q(numero_ticket__icontains=query) |
            Q(immatriculation__icontains=query) |
            Q(nom_transporteur__icontains=query) |
            Q(telephone_transporteur__icontains=query)
        )
    
    # Filtre type infraction
    if type_infraction:
        queryset = queryset.filter(type_infraction=type_infraction)
    
    # Statistiques globales
    stats = queryset.aggregate(
        total_recouvre=Sum('montant_amende'),
        count_paiements=Count('id'),
        count_amendes=Count('id', distinct=True)
    )
    
    # Calculer moyenne journalière
    jours = (date_fin - date_debut).days + 1
    moyenne_journaliere = (stats['total_recouvre'] or 0) / jours if jours > 0 else 0
    stats['moyenne_journaliere'] = moyenne_journaliere
    
    # Agrégation par jour pour l'affichage
    recettes_par_jour = queryset.annotate(
        date=TruncDate('date_paiement')
    ).values('date').annotate(
        total=Sum('montant_amende'),
        count_paiements=Count('id')
    ).order_by('-date')
    
    # Pagination
    paginator = Paginator(list(recettes_par_jour), 15)
    page = request.GET.get('page')
    recettes = paginator.get_page(page)
    
    context = {
        'recettes': recettes,
        'station': station,
        'stations_accessibles': stations_accessibles,
        'stats': stats,
        'is_admin': is_admin(user),
        'query': query,
        'periode': periode,
        'type_infraction': type_infraction,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'station_filter': request.GET.get('station_filter', ''),
        'title': _('Recettes Pesage'),
    }
    
    return render(request, 'pesage/recettes_pesage.html', context)


@pesage_access_required
def imprimer_recette_jour(request, date_str):
    """
    Page d'impression pour les recettes d'un jour.
    """
    user = request.user
    station, redirect_response = get_station_context(request, user)
    if redirect_response:
        return redirect_response
    
    try:
        date_cible = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, _("Format de date invalide."))
        return redirect('inventaire:recettes_pesage')
    
    # Récupérer les paiements du jour
    if station is None and is_admin(user):
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
        date_paiement__date=date_cible
    ).select_related('station', 'valide_par').order_by('date_paiement')
    
    # Calculs
    total = paiements.aggregate(total=Sum('montant_amende'))['total'] or 0
    
    # Stats par type d'infraction
    stats_types = paiements.values('type_infraction').annotate(
        count=Count('id'),
        montant=Sum('montant_amende')
    ).order_by('type_infraction')
    
    context = {
        'paiements': paiements,
        'date': date_cible,
        'station': station_obj,
        'total': total,
        'count': paiements.count(),
        'stats_types': stats_types,
        'is_admin': is_admin(user),
        'title': f"Recettes du {date_cible.strftime('%d/%m/%Y')}",
    }
    
    return render(request, 'pesage/imprimer_recette_jour.html', context)


# ===================================================================
# API ENDPOINTS (JSON)
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
    
    pesee = PeseesJournalieres.objects.filter(station=station, date=date_cible).first()
    
    if pesee:
        return JsonResponse({
            'deja_saisi': True,
            'nombre_pesees': pesee.nombre_pesees,
            'date': date_cible.strftime('%d/%m/%Y'),
            'saisi_par': pesee.saisi_par.nom_complet if pesee.saisi_par else None
        })
    
    return JsonResponse({'deja_saisi': False, 'date': date_cible.strftime('%d/%m/%Y')})


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


@pesage_access_required
@require_GET
def api_paiements_jour(request):
    """API pour récupérer les paiements d'un jour."""
    user = request.user
    station, _ = get_station_context(request, user)
    
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Date requise'}, status=400)
    
    try:
        date_cible = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Format date invalide'}, status=400)
    
    if station is None and is_admin(user):
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
            'transporteur': p.nom_transporteur or '-',
            'montant': float(p.montant_amende),
            'heure': p.date_paiement.strftime('%H:%M') if p.date_paiement else '-',
        } for p in paiements],
        'total': float(paiements.aggregate(Sum('montant_amende'))['montant_amende__sum'] or 0),
        'count': paiements.count(),
    }
    
    return JsonResponse(data)


@pesage_access_required
@require_GET
def api_stats_jour(request):
    """API pour récupérer les stats d'un jour."""
    user = request.user
    station, _ = get_station_context(request, user)
    
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Date requise'}, status=400)
    
    try:
        date_cible = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Format date invalide'}, status=400)
    
    if station is None and is_admin(user):
        amendes = AmendeEmise.objects.filter(date_emission__date=date_cible)
        station_filter = request.GET.get('station')
        if station_filter:
            amendes = amendes.filter(station_id=station_filter)
    elif station:
        amendes = AmendeEmise.objects.filter(station=station, date_emission__date=date_cible)
    else:
        amendes = AmendeEmise.objects.none()
    
    stats = amendes.aggregate(
        count=Count('id'),
        hg_count=Count('id', filter=Q(type_infraction__in=['HG', 'S+HG'])),
        montant_emis=Sum('montant_amende'),
        montant_recouvre=Sum('montant_amende', filter=Q(statut='paye'))
    )
    
    return JsonResponse({
        'emissions': stats['count'] or 0,
        'hors_gabarit': stats['hg_count'] or 0,
        'montant_emis': float(stats['montant_emis'] or 0),
        'montant_recouvre': float(stats['montant_recouvre'] or 0),
    })


@pesage_access_required
@require_GET
def api_recherche_amende(request):
    """API de recherche rapide d'amende."""
    user = request.user
    station, _ = get_station_context(request, user)
    
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    if station is None and is_admin(user):
        amendes = AmendeEmise.objects.all()
    elif station:
        amendes = AmendeEmise.objects.filter(station=station)
    else:
        amendes = AmendeEmise.objects.none()
    
    amendes = amendes.filter(
        Q(numero_ticket__icontains=query) |
        Q(immatriculation__icontains=query) |
        Q(nom_transporteur__icontains=query)
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


@login_required
@require_GET
def api_stats_periode(request):
    """
    API pour récupérer les statistiques d'une période.
    GET params: station (optionnel), periode (jour|semaine|mois|trimestre|annee), date
    """
    station_id = request.GET.get('station')
    periode = request.GET.get('periode', 'mois')
    date_str = request.GET.get('date')
    
    if date_str:
        try:
            date_ref = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            date_ref = timezone.now().date()
    else:
        date_ref = timezone.now().date()
    
    date_debut, date_fin = get_periode_dates(periode, date_ref)
    
    # Base queryset
    amendes = AmendeEmise.objects.filter(
        date_emission__date__gte=date_debut,
        date_emission__date__lte=date_fin
    )
    
    if station_id:
        try:
            station = Poste.objects.get(pk=station_id, type='pesage')
            amendes = amendes.filter(station=station)
        except Poste.DoesNotExist:
            return JsonResponse({'error': 'Station non trouvée'}, status=404)
    
    stats = amendes.aggregate(
        emissions=Count('id'),
        hors_gabarit=Count('id', filter=Q(type_infraction__in=['HG', 'S+HG'])),
        montant_emis=Sum('montant_amende'),
        montant_recouvre=Sum('montant_amende', filter=Q(statut='paye')),
        count_paye=Count('id', filter=Q(statut='paye')),
        count_non_paye=Count('id', filter=Q(statut='non_paye'))
    )
    
    # Pesées
    pesees_qs = PeseesJournalieres.objects.filter(
        date__gte=date_debut, date__lte=date_fin
    )
    if station_id:
        pesees_qs = pesees_qs.filter(station_id=station_id)
    
    nombre_pesees = pesees_qs.aggregate(total=Sum('nombre_pesees'))['total'] or 0
    
    montant_emis = stats['montant_emis'] or 0
    montant_recouvre = stats['montant_recouvre'] or 0
    taux_recouvrement = 0
    if montant_emis > 0:
        taux_recouvrement = (float(montant_recouvre) / float(montant_emis)) * 100
    
    return JsonResponse({
        'periode': periode,
        'date_debut': date_debut.strftime('%d/%m/%Y'),
        'date_fin': date_fin.strftime('%d/%m/%Y'),
        'emissions': stats['emissions'] or 0,
        'hors_gabarit': stats['hors_gabarit'] or 0,
        'montant_emis': float(montant_emis),
        'montant_recouvre': float(montant_recouvre),
        'reste_a_recouvrer': float(montant_emis - montant_recouvre),
        'taux_recouvrement': round(taux_recouvrement, 2),
        'count_paye': stats['count_paye'] or 0,
        'count_non_paye': stats['count_non_paye'] or 0,
        'nombre_pesees': nombre_pesees
    })