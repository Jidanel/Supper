# ===================================================================
# inventaire/views_incident.py - Vues pour la gestion des incidents SUPPER
# VERSION SIMPLIFIÉE - Sans modal, sans AJAX
# À AJOUTER dans le dossier inventaire/
# ===================================================================
"""
Vues pour la gestion des incidents.

Workflow simplifié:
    1. liste_incidents: Liste tous les incidents avec filtres
    2. creer_incident: Permet à tout utilisateur de créer un incident
    3. detail_incident: Affiche les détails d'un incident
    4. traiter_incident: Admin marque comme "Traité"
    5. rejeter_incident: Admin marque comme "Rejeté"
    6. demander_complement: Admin demande un complément d'informations
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import datetime

from .models_incident import Incident, StatutIncident, CategorieIncident, PrioriteIncident
from .forms_incident import IncidentCreationForm, IncidentReponseForm
from common.utils import log_user_action
from common.permissions import is_admin_user

import logging
logger = logging.getLogger('supper')


# ===================================================================
# FONCTIONS UTILITAIRES
# ===================================================================

def _peut_voir_tous_incidents(user):
    """
    Vérifie si l'utilisateur peut voir tous les incidents.
    Seuls les administrateurs ont cette permission.
    """
    return is_admin_user(user)


def _peut_traiter_incident(user):
    """
    Vérifie si l'utilisateur peut traiter les incidents.
    Seuls les administrateurs ont cette permission.
    """
    return is_admin_user(user)


def _get_incidents_filtres(request, queryset):
    """
    Applique les filtres sur le queryset des incidents.
    """
    # Filtre par statut
    statut = request.GET.get('statut', '')
    if statut:
        queryset = queryset.filter(statut=statut)

    # Filtre par catégorie
    categorie = request.GET.get('categorie', '')
    if categorie:
        queryset = queryset.filter(categorie=categorie)

    # Filtre par priorité
    priorite = request.GET.get('priorite', '')
    if priorite:
        queryset = queryset.filter(priorite=priorite)

    # Filtre par utilisateur (nom ou matricule) - admin seulement
    utilisateur = request.GET.get('utilisateur', '')
    if utilisateur:
        queryset = queryset.filter(
            Q(cree_par__nom_complet__icontains=utilisateur) |
            Q(cree_par__username__icontains=utilisateur)
        )

    # Recherche textuelle (sujet, description, référence)
    recherche = request.GET.get('recherche', '')
    if recherche:
        queryset = queryset.filter(
            Q(sujet__icontains=recherche) |
            Q(description__icontains=recherche) |
            Q(reference__icontains=recherche)
        )

    # Filtre par dates
    date_debut = request.GET.get('date_debut', '')
    if date_debut:
        try:
            date_debut_parsed = datetime.strptime(date_debut, '%Y-%m-%d').date()
            queryset = queryset.filter(date_creation__date__gte=date_debut_parsed)
        except ValueError:
            pass

    date_fin = request.GET.get('date_fin', '')
    if date_fin:
        try:
            date_fin_parsed = datetime.strptime(date_fin, '%Y-%m-%d').date()
            queryset = queryset.filter(date_creation__date__lte=date_fin_parsed)
        except ValueError:
            pass

    return queryset


# ===================================================================
# VUE LISTE DES INCIDENTS
# ===================================================================

@login_required
def liste_incidents(request):
    """
    Affiche la liste des incidents avec filtres et pagination.

    - Utilisateurs normaux: voient uniquement leurs propres incidents
    - Administrateurs: voient tous les incidents
    """
    user = request.user
    est_admin = _peut_voir_tous_incidents(user)

    # Base du queryset selon les droits
    if est_admin:
        queryset = Incident.objects.select_related('cree_par', 'traite_par').all()
    else:
        queryset = Incident.objects.select_related('cree_par', 'traite_par').filter(
            cree_par=user
        )

    # Appliquer les filtres
    queryset = _get_incidents_filtres(request, queryset)

    # Tri par défaut: plus récents en premier
    queryset = queryset.order_by('-date_creation')

    # Statistiques pour le dashboard
    if est_admin:
        stats_base = Incident.objects.all()
    else:
        stats_base = Incident.objects.filter(cree_par=user)

    stats = {
        'total': stats_base.count(),
        'en_attente': stats_base.filter(statut=StatutIncident.EN_ATTENTE).count(),
        'traites': stats_base.filter(statut=StatutIncident.TRAITE).count(),
        'rejetes': stats_base.filter(statut=StatutIncident.REJETE).count(),
        'complement_requis': stats_base.filter(statut=StatutIncident.COMPLEMENT_REQUIS).count(),
    }

    # Pagination
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Log de l'action
    log_user_action(
        user,
        "CONSULTATION_LISTE_INCIDENTS",
        f"Consultation de la liste des incidents - Page {page_number} - "
        f"Filtres: statut={request.GET.get('statut', 'tous')}, "
        f"categorie={request.GET.get('categorie', 'toutes')}",
        request
    )

    context = {
        'title': _('Gestion des Incidents'),
        'page_obj': page_obj,
        'incidents': page_obj,
        'stats': stats,
        'est_admin': est_admin,
        'statuts': StatutIncident.choices,
        'categories': CategorieIncident.choices,
        'priorites': PrioriteIncident.choices,
        # Valeurs actuelles des filtres
        'statut_actuel': request.GET.get('statut', ''),
        'categorie_actuelle': request.GET.get('categorie', ''),
        'priorite_actuelle': request.GET.get('priorite', ''),
        'utilisateur_actuel': request.GET.get('utilisateur', ''),
        'recherche_actuelle': request.GET.get('recherche', ''),
        'date_debut_actuelle': request.GET.get('date_debut', ''),
        'date_fin_actuelle': request.GET.get('date_fin', ''),
    }

    return render(request, 'inventaire/incidents/liste_incidents.html', context)


# ===================================================================
# VUE CRÉATION D'INCIDENT
# ===================================================================

@login_required
def creer_incident(request):
    """
    Permet à tout utilisateur authentifié de créer un nouvel incident.
    Le statut est automatiquement mis à "En attente".
    """
    user = request.user

    if request.method == 'POST':
        form = IncidentCreationForm(request.POST)

        if form.is_valid():
            try:
                # Créer l'incident
                incident = form.save(commit=False)
                incident.cree_par = user
                incident.statut = StatutIncident.EN_ATTENTE
                incident.save()

                # Log de l'action
                log_user_action(
                    user,
                    "CREATION_INCIDENT",
                    f"Création de l'incident {incident.reference} - "
                    f"Sujet: {incident.sujet[:50]}... - "
                    f"Catégorie: {incident.get_categorie_display()} - "
                    f"Priorité: {incident.get_priorite_display()}",
                    request,
                    incident_id=incident.id,
                    reference=incident.reference
                )

                messages.success(
                    request,
                    _(f"✅ Incident créé avec succès ! Référence: {incident.reference}")
                )

                return redirect('inventaire:liste_incidents')

            except Exception as e:
                logger.error(f"Erreur création incident: {str(e)}")
                messages.error(
                    request,
                    _("❌ Une erreur est survenue lors de la création de l'incident.")
                )
        else:
            messages.warning(
                request,
                _("⚠️ Veuillez corriger les erreurs dans le formulaire.")
            )
    else:
        form = IncidentCreationForm()

        # Log de la consultation du formulaire
        log_user_action(
            user,
            "ACCES_FORMULAIRE_INCIDENT",
            "Accès au formulaire de création d'incident",
            request
        )

    context = {
        'title': _('Signaler un incident'),
        'form': form,
        'categories': CategorieIncident.choices,
        'priorites': PrioriteIncident.choices,
    }

    return render(request, 'inventaire/creer_incident.html', context)


# ===================================================================
# VUE DÉTAIL D'UN INCIDENT
# ===================================================================

@login_required
def detail_incident(request, pk):
    """
    Affiche les détails d'un incident spécifique.

    - Utilisateurs normaux: peuvent voir uniquement leurs propres incidents
    - Administrateurs: peuvent voir tous les incidents + formulaire de traitement
    """
    user = request.user
    est_admin = _peut_voir_tous_incidents(user)

    # Récupérer l'incident
    if est_admin:
        incident = get_object_or_404(
            Incident.objects.select_related('cree_par', 'traite_par'),
            pk=pk
        )
    else:
        incident = get_object_or_404(
            Incident.objects.select_related('cree_par', 'traite_par'),
            pk=pk,
            cree_par=user
        )

    # Formulaire de réponse pour les admins
    reponse_form = None
    if est_admin and incident.peut_etre_traite:
        reponse_form = IncidentReponseForm()

    # Log de l'action
    log_user_action(
        user,
        "CONSULTATION_DETAIL_INCIDENT",
        f"Consultation de l'incident {incident.reference} - "
        f"Statut: {incident.get_statut_display()}",
        request,
        incident_id=incident.id,
        reference=incident.reference
    )

    context = {
        'title': f'Incident {incident.reference}',
        'incident': incident,
        'est_admin': est_admin,
        'reponse_form': reponse_form,
        'peut_traiter': est_admin and incident.peut_etre_traite,
    }

    return render(request, 'inventaire/incidents/detail_incident.html', context)


# ===================================================================
# ACTIONS ADMIN - TRAITER UN INCIDENT
# ===================================================================

@login_required
def traiter_incident(request, pk):
    """
    Permet à un administrateur de marquer un incident comme TRAITÉ.
    POST uniquement avec une réponse obligatoire.
    """
    user = request.user

    # Vérification des droits
    if not _peut_traiter_incident(user):
        messages.error(request, _("❌ Vous n'avez pas les droits pour traiter les incidents."))
        log_user_action(
            user,
            "ACCES_REFUSE_TRAITEMENT_INCIDENT",
            f"Tentative de traitement d'incident refusée - ID: {pk}",
            request
        )
        return redirect('inventaire:liste_incidents')

    incident = get_object_or_404(Incident, pk=pk)

    # Vérifier que l'incident peut être traité
    if not incident.peut_etre_traite:
        messages.warning(request, _("⚠️ Cet incident a déjà été traité."))
        return redirect('inventaire:detail_incident', pk=pk)

    if request.method == 'POST':
        # Récupérer directement la réponse du POST
        reponse = request.POST.get('reponse', '').strip()

        if len(reponse) < 10:
            messages.warning(request, _("⚠️ Veuillez fournir une réponse d'au moins 10 caractères."))
            return redirect('inventaire:detail_incident', pk=pk)

        ancien_statut = incident.statut

        # Mettre à jour l'incident
        incident.statut = StatutIncident.TRAITE
        incident.traite_par = user
        incident.reponse = reponse
        incident.date_traitement = timezone.now()
        incident.save()

        # Log de l'action
        log_user_action(
            user,
            "TRAITEMENT_INCIDENT",
            f"Incident {incident.reference} marqué comme TRAITÉ - "
            f"Ancien statut: {ancien_statut} - "
            f"Réponse: {reponse[:100]}...",
            request
        )

        messages.success(request, _(f"✅ Incident {incident.reference} marqué comme traité."))
        return redirect('inventaire:detail_incident', pk=pk)

    return redirect('inventaire:detail_incident', pk=pk)


# ===================================================================
# ACTIONS ADMIN - REJETER UN INCIDENT
# ===================================================================

@login_required
def rejeter_incident(request, pk):
    """
    Permet à un administrateur de REJETER un incident.
    POST uniquement avec un motif obligatoire.
    """
    user = request.user

    # Vérification des droits
    if not _peut_traiter_incident(user):
        messages.error(request, _("❌ Vous n'avez pas les droits pour rejeter les incidents."))
        log_user_action(
            user,
            "ACCES_REFUSE_REJET_INCIDENT",
            f"Tentative de rejet d'incident refusée - ID: {pk}",
            request
        )
        return redirect('inventaire:liste_incidents')

    incident = get_object_or_404(Incident, pk=pk)

    # Vérifier que l'incident peut être traité
    if not incident.peut_etre_traite:
        messages.warning(request, _("⚠️ Cet incident a déjà été traité."))
        return redirect('inventaire:detail_incident', pk=pk)

    if request.method == 'POST':
        # Récupérer directement la réponse du POST
        reponse = request.POST.get('reponse', '').strip()

        if len(reponse) < 10:
            messages.warning(request, _("⚠️ Veuillez fournir un motif d'au moins 10 caractères."))
            return redirect('inventaire:detail_incident', pk=pk)

        ancien_statut = incident.statut

        # Mettre à jour l'incident
        incident.statut = StatutIncident.REJETE
        incident.traite_par = user
        incident.reponse = reponse
        incident.date_traitement = timezone.now()
        incident.save()

        # Log de l'action
        log_user_action(
            user,
            "REJET_INCIDENT",
            f"Incident {incident.reference} REJETÉ - "
            f"Ancien statut: {ancien_statut} - "
            f"Motif: {reponse[:100]}...",
            request
        )

        messages.success(request, _(f"⛔ Incident {incident.reference} rejeté."))
        return redirect('inventaire:detail_incident', pk=pk)

    return redirect('inventaire:detail_incident', pk=pk)


# ===================================================================
# ACTIONS ADMIN - DEMANDER COMPLÉMENT D'INFORMATIONS
# ===================================================================

@login_required
def demander_complement(request, pk):
    """
    Permet à un administrateur de demander un COMPLÉMENT D'INFORMATIONS.
    L'utilisateur devra resaisir son incident.
    POST uniquement avec un message obligatoire.
    """
    user = request.user

    # Vérification des droits
    if not _peut_traiter_incident(user):
        messages.error(request, _("❌ Vous n'avez pas les droits pour cette action."))
        log_user_action(
            user,
            "ACCES_REFUSE_COMPLEMENT_INCIDENT",
            f"Tentative de demande de complément refusée - ID: {pk}",
            request
        )
        return redirect('inventaire:liste_incidents')

    incident = get_object_or_404(Incident, pk=pk)

    # Vérifier que l'incident peut être traité
    if not incident.peut_etre_traite:
        messages.warning(request, _("⚠️ Cet incident a déjà été traité."))
        return redirect('inventaire:detail_incident', pk=pk)

    if request.method == 'POST':
        # Récupérer directement la réponse du POST
        reponse = request.POST.get('reponse', '').strip()

        if len(reponse) < 10:
            messages.warning(request, _("⚠️ Veuillez préciser les informations manquantes (10 caractères minimum)."))
            return redirect('inventaire:detail_incident', pk=pk)

        ancien_statut = incident.statut

        # Mettre à jour l'incident
        incident.statut = StatutIncident.COMPLEMENT_REQUIS
        incident.traite_par = user
        incident.reponse = reponse
        incident.save()

        # Log de l'action
        log_user_action(
            user,
            "DEMANDE_COMPLEMENT_INCIDENT",
            f"Incident {incident.reference} - COMPLÉMENT D'INFORMATIONS REQUIS - "
            f"Ancien statut: {ancien_statut} - "
            f"Message: {reponse[:100]}...",
            request
        )

        messages.info(request, _(f"ℹ️ Demande de complément envoyée pour l'incident {incident.reference}."))
        return redirect('inventaire:detail_incident', pk=pk)

    return redirect('inventaire:detail_incident', pk=pk)