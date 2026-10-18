# ===================================================================
# FICHIER: inventaire/views_historique_quittance.py
# ===================================================================
# Vues pour la gestion des historiques de quittances (ACCT)
# ===================================================================

import os
import uuid
import logging
from decimal import Decimal
from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.core.paginator import Paginator
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models import Q, Sum
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.urls import reverse

from accounts.models import Poste, UtilisateurSUPPER
from inventaire.models import HistoriqueQuittance
from inventaire.forms import HistoriqueQuittanceForm, HistoriqueQuittanceFiltreForm
from common.utils import log_user_action
from common.permissions import (
    has_permission, 
    user_has_acces_tous_postes, 
    is_admin_user,
    get_postes_peage_accessibles
)

logger = logging.getLogger('supper')


# ===================================================================
# CONSTANTES ET FONCTIONS UTILITAIRES
# ===================================================================

# Habilitations autorisées à supprimer des historiques
HABILITATIONS_ADMIN_HISTORIQUE = [
    'admin_principal',
    'coord_psrr', 
    'serv_info',
    'serv_emission',
    'serv_controle'
]


def peut_supprimer_historique(user):
    """
    Vérifie si l'utilisateur peut supprimer des historiques.
    Seuls les administrateurs définis peuvent supprimer.
    """
    if not user or not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    habilitation = getattr(user, 'habilitation', None)
    return habilitation in HABILITATIONS_ADMIN_HISTORIQUE


def peut_saisir_historique(user):
    """
    Vérifie si l'utilisateur peut saisir des historiques.
    Permission: peut_saisir_quittance_peage ou admin
    """
    if not user or not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    # Les admins peuvent toujours saisir
    if is_admin_user(user):
        return True
    
    # Vérifier la permission spécifique
    return has_permission(user, 'peut_saisir_quittance_peage')


def get_poste_utilisateur(user):
    """
    Récupère le poste de péage de l'utilisateur.
    Retourne None si l'utilisateur n'est pas affecté à un poste de péage.
    """
    poste = getattr(user, 'poste_affectation', None)
    if poste and poste.type == 'peage' and poste.is_active:
        return poste
    return None


# ===================================================================
# VUE: SÉLECTION DU POSTE (pour admin multi-postes)
# ===================================================================

@login_required
def selection_poste_historique(request):
    """
    Vue de sélection du poste pour les utilisateurs multi-postes.
    Redirige vers la saisie d'historique avec le poste sélectionné.
    """
    user = request.user
    
    # Vérifier la permission de saisie
    if not peut_saisir_historique(user):
        log_user_action(
            user,
            "ACCES_REFUSE",
            f"Tentative d'accès à la sélection de poste historique | "
            f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )
        messages.error(request, _("Vous n'avez pas la permission de saisir des historiques."))
        return redirect('common:dashboard')
    
    # Récupérer les postes de péage accessibles
    postes = get_postes_peage_accessibles(user)
    
    if request.method == 'POST':
        poste_id = request.POST.get('poste')
        if poste_id:
            return redirect(f"{reverse('inventaire:saisir_historique')}?poste={poste_id}")
        else:
            messages.error(request, _("Veuillez sélectionner un poste."))
    
    context = {
        'postes': postes,
        'title': _("Sélectionner un poste"),
        'action_url': reverse('inventaire:saisir_historique'),
        'is_admin': is_admin_user(user),
    }
    
    return render(request, 'inventaire/selection_poste_historique.html', context)


# ===================================================================
# VUE: SAISIE D'UN HISTORIQUE
# ===================================================================

@login_required
def saisir_historique(request):
    """
    Vue de saisie d'un nouvel historique de quittance.
    
    Flux:
    1. Utilisateur remplit le formulaire
    2. Données validées et stockées en session
    3. Redirection vers la page de confirmation
    
    Permissions:
    - Chef de poste: peut saisir pour son poste uniquement
    - Admin: peut saisir pour n'importe quel poste
    """
    user = request.user
    today = timezone.now().date()
    
    # Vérifier la permission de saisie
    if not peut_saisir_historique(user):
        log_user_action(
            user,
            "ACCES_REFUSE",
            f"Tentative de saisie d'historique | "
            f"Permission peut_saisir_quittance_peage manquante | "
            f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )
        messages.error(request, _("Vous n'avez pas la permission de saisir des historiques."))
        return redirect('common:dashboard')
    
    # Déterminer les postes accessibles
    acces_tous_postes = user_has_acces_tous_postes(user)
    postes_accessibles = get_postes_peage_accessibles(user)
    
    # Déterminer le poste à utiliser
    poste_preselectionne = None
    
    if acces_tous_postes:
        # Admin: vérifier si un poste est spécifié dans l'URL
        poste_id = request.GET.get('poste') or request.POST.get('poste')
        if poste_id:
            try:
                poste_preselectionne = Poste.objects.get(
                    id=int(poste_id), 
                    type='peage', 
                    is_active=True
                )
            except (Poste.DoesNotExist, ValueError):
                messages.error(request, _("Poste invalide."))
                return redirect('inventaire:selection_poste_historique')
        else:
            # Pas de poste spécifié, rediriger vers la sélection
            return redirect('inventaire:selection_poste_historique')
    else:
        # Chef de poste: utiliser son poste d'affectation
        poste_preselectionne = get_poste_utilisateur(user)
        if not poste_preselectionne:
            messages.error(request, _("Vous n'êtes pas affecté à un poste de péage."))
            return redirect('common:dashboard')
    
    if request.method == 'POST':
        form = HistoriqueQuittanceForm(
            request.POST,
            request.FILES,
            user=user,
            postes_queryset=postes_accessibles,
            poste_preselectionne=poste_preselectionne
        )
        
        # Si le champ poste est désactivé, forcer la valeur
        if not acces_tous_postes and poste_preselectionne:
            form.data = form.data.copy()
            form.data['poste'] = str(poste_preselectionne.id)
        
        if form.is_valid():
            # Stocker les données en session pour la confirmation
            request.session['historique_temp'] = {
                'poste_id': form.cleaned_data['poste'],
                'poste_nom': form.cleaned_data['poste_instance'].nom,
                'poste_code': form.cleaned_data['poste_instance'].code,
                'mois': form.cleaned_data['mois'],
                'montant_global': str(form.cleaned_data['montant_global']),
                'montant_reel': str(form.cleaned_data['montant_reel']),
                'observations': form.cleaned_data.get('observations', ''),
            }
            
            # Gérer l'image uploadée
            if 'image_historique' in request.FILES:
                image = request.FILES['image_historique']
                # Sauvegarder temporairement l'image
                temp_filename = f"temp_historique_{uuid.uuid4().hex}_{image.name}"
                temp_path = default_storage.save(f'temp/{temp_filename}', ContentFile(image.read()))
                request.session['historique_image_temp'] = temp_path
            else:
                request.session['historique_image_temp'] = None
            
            logger.info(
                f"[HISTORIQUE] {user.username} a préparé un historique pour confirmation | "
                f"Poste: {form.cleaned_data['poste_instance'].nom} | "
                f"Mois: {form.cleaned_data['mois']}"
            )
            
            return redirect('inventaire:confirmer_historique')
    else:
        form = HistoriqueQuittanceForm(
            user=user,
            postes_queryset=postes_accessibles,
            poste_preselectionne=poste_preselectionne
        )
    
    context = {
        'form': form,
        'poste': poste_preselectionne,
        'is_admin': is_admin_user(user),
        'acces_tous_postes': acces_tous_postes,
        'today': today,
        'title': _("Saisir un historique de quittance"),
    }
    
    return render(request, 'inventaire/saisir_historique.html', context)


# ===================================================================
# VUE: CONFIRMATION D'UN HISTORIQUE
# ===================================================================

@login_required
def confirmer_historique(request):
    """
    Vue de confirmation avant création de l'historique.
    
    Affiche un résumé des données saisies et permet:
    - Confirmer: crée l'historique
    - Modifier: retourne au formulaire
    - Annuler: annule et supprime les données temporaires
    """
    user = request.user
    
    # Vérifier la permission
    if not peut_saisir_historique(user):
        messages.error(request, _("Vous n'avez pas la permission de saisir des historiques."))
        return redirect('common:dashboard')
    
    # Récupérer les données de session
    historique_data = request.session.get('historique_temp')
    image_temp_path = request.session.get('historique_image_temp')
    
    if not historique_data:
        messages.warning(request, _("Aucune donnée d'historique en attente. Veuillez recommencer."))
        return redirect('inventaire:saisir_historique')
    
    # Récupérer le poste
    try:
        poste = Poste.objects.get(id=int(historique_data['poste_id']))
    except (Poste.DoesNotExist, ValueError, KeyError):
        messages.error(request, _("Poste invalide."))
        _nettoyer_session_historique(request)
        return redirect('inventaire:saisir_historique')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirmer':
            # Créer l'historique
            try:
                historique = HistoriqueQuittance(
                    poste=poste,
                    mois=historique_data['mois'],
                    montant_global=Decimal(historique_data['montant_global']),
                    montant_reel=Decimal(historique_data['montant_reel']),
                    observations=historique_data.get('observations', ''),
                    saisi_par=user
                )
                
                # Déplacer l'image temporaire vers l'emplacement final
                if image_temp_path and default_storage.exists(image_temp_path):
                    # Lire le fichier temporaire
                    with default_storage.open(image_temp_path, 'rb') as temp_file:
                        content = temp_file.read()
                    
                    # Créer le nom de fichier final
                    ext = os.path.splitext(image_temp_path)[1]
                    final_filename = f"historique_{poste.code}_{historique_data['mois']}{ext}"
                    
                    # Sauvegarder dans le dossier final
                    historique.image_historique.save(final_filename, ContentFile(content), save=False)
                    
                    # Supprimer le fichier temporaire
                    default_storage.delete(image_temp_path)
                
                historique.save()
                
                # Log de l'action
                log_user_action(
                    user,
                    "CREATION_HISTORIQUE_QUITTANCE",
                    f"Création d'un historique de quittance | "
                    f"Numéro: {historique.numero_historique} | "
                    f"Poste: {poste.nom} ({poste.code}) | "
                    f"Mois: {historique.get_mois_display()} | "
                    f"Montant global: {historique.montant_global:,.0f} FCFA | "
                    f"Montant réel: {historique.montant_reel:,.0f} FCFA | "
                    f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
                    request
                )
                
                logger.info(
                    f"[HISTORIQUE] {user.username} a créé l'historique {historique.numero_historique} | "
                    f"Poste: {poste.nom} | Mois: {historique.mois}"
                )
                
                # Nettoyer la session
                _nettoyer_session_historique(request)
                
                messages.success(
                    request,
                    _("Historique %(numero)s créé avec succès pour %(poste)s - %(mois)s.") % {
                        'numero': historique.numero_historique,
                        'poste': poste.nom,
                        'mois': historique.get_mois_display()
                    }
                )
                
                return redirect('inventaire:liste_historiques')
                
            except Exception as e:
                logger.error(f"[HISTORIQUE] Erreur création historique: {str(e)}")
                messages.error(request, _("Erreur lors de la création de l'historique: %(error)s") % {'error': str(e)})
                return redirect('inventaire:saisir_historique')
        
        elif action == 'modifier':
            # Retourner au formulaire (garder les données en session)
            poste_id = historique_data.get('poste_id')
            return redirect(f"{reverse('inventaire:saisir_historique')}?poste={poste_id}")
        
        elif action == 'annuler':
            # Supprimer l'image temporaire si elle existe
            if image_temp_path and default_storage.exists(image_temp_path):
                default_storage.delete(image_temp_path)
            
            _nettoyer_session_historique(request)
            messages.info(request, _("Saisie annulée."))
            return redirect('inventaire:liste_historiques')
    
    # Formater les montants pour l'affichage
    montant_global_display = f"{Decimal(historique_data['montant_global']):,.0f}".replace(',', ' ')
    montant_reel_display = f"{Decimal(historique_data['montant_reel']):,.0f}".replace(',', ' ')
    
    # Déterminer le nom du mois
    mois_str = historique_data['mois']
    mois_noms = {
        '01': 'Janvier', '02': 'Février', '03': 'Mars',
        '04': 'Avril', '05': 'Mai', '06': 'Juin',
        '07': 'Juillet', '08': 'Août', '09': 'Septembre',
        '10': 'Octobre', '11': 'Novembre', '12': 'Décembre'
    }
    annee = mois_str[:4]
    mois_num = mois_str[5:7]
    mois_display = f"{mois_noms.get(mois_num, mois_num)} {annee}"
    
    context = {
        'poste': poste,
        'mois': mois_str,
        'mois_display': mois_display,
        'montant_global': historique_data['montant_global'],
        'montant_global_display': montant_global_display,
        'montant_reel': historique_data['montant_reel'],
        'montant_reel_display': montant_reel_display,
        'observations': historique_data.get('observations', ''),
        'has_image': bool(image_temp_path),
        'is_admin': is_admin_user(user),
        'title': _("Confirmer l'historique de quittance"),
    }
    
    return render(request, 'inventaire/confirmer_historique.html', context)


def _nettoyer_session_historique(request):
    """Nettoie les données d'historique de la session."""
    if 'historique_temp' in request.session:
        del request.session['historique_temp']
    if 'historique_image_temp' in request.session:
        del request.session['historique_image_temp']


# ===================================================================
# VUE: LISTE DES HISTORIQUES
# ===================================================================
@login_required
def liste_historiques(request):
    """
    Liste des historiques de quittances avec filtres.
    
    Filtres disponibles:
    - Par poste (admin uniquement)
    - Par mois
    - Par année
    
    Permissions:
    - Admin: voit tous les historiques
    - Chef de poste: voit uniquement les historiques de son poste
    """
    user = request.user
    
    # Vérifier la permission de base
    if not user.is_authenticated:
        return redirect('accounts:login')
    
    # Déterminer les postes accessibles
    acces_tous_postes = user_has_acces_tous_postes(user)
    postes_accessibles = get_postes_peage_accessibles(user)
    
    # Construire le queryset de base
    if acces_tous_postes:
        queryset = HistoriqueQuittance.objects.all()
    else:
        poste_user = get_poste_utilisateur(user)
        if poste_user:
            queryset = HistoriqueQuittance.objects.filter(poste=poste_user)
        else:
            queryset = HistoriqueQuittance.objects.none()
    
    # Récupérer les filtres actuels
    current_filters = {
        'poste': request.GET.get('poste', ''),
        'annee': request.GET.get('annee', ''),
        'mois': request.GET.get('mois', ''),
    }
    
    # Filtre par poste (admin uniquement)
    poste_filter = current_filters['poste']
    if poste_filter and acces_tous_postes:
        queryset = queryset.filter(poste_id=poste_filter)
    
    # Filtre par année
    annee_filter = current_filters['annee']
    if annee_filter:
        try:
            queryset = queryset.filter(annee=int(annee_filter))
        except ValueError:
            pass
    
    # Filtre par mois (numéro du mois: 01, 02, etc.)
    mois_filter = current_filters['mois']
    if mois_filter:
        queryset = queryset.filter(mois__endswith=f"-{mois_filter}")
    
    # Recherche textuelle
    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(
            Q(numero_historique__icontains=query) |
            Q(poste__nom__icontains=query) |
            Q(poste__code__icontains=query) |
            Q(observations__icontains=query)
        )
    
    # Optimiser et ordonner
    queryset = queryset.select_related('poste', 'saisi_par').order_by('-annee', '-mois', 'poste__nom')
    
    # Calculer les statistiques AVANT la pagination
    stats_aggregates = queryset.aggregate(
        total_montant_global=Sum('montant_global'),
        total_montant_reel=Sum('montant_reel'),
    )
    
    stats = {
        'total_historiques': queryset.count(),
        'total_montant_global': stats_aggregates['total_montant_global'] or Decimal('0'),
        'total_montant_reel': stats_aggregates['total_montant_reel'] or Decimal('0'),
        'postes_couverts': queryset.values('poste').distinct().count(),
    }
    
    # Générer les listes pour les filtres
    # Années disponibles (de l'année actuelle à 5 ans en arrière)
    current_year = date.today().year
    annees_disponibles = list(range(current_year, current_year - 6, -1))
    
    # Mois disponibles
    mois_disponibles = [
        ('01', 'Janvier'),
        ('02', 'Février'),
        ('03', 'Mars'),
        ('04', 'Avril'),
        ('05', 'Mai'),
        ('06', 'Juin'),
        ('07', 'Juillet'),
        ('08', 'Août'),
        ('09', 'Septembre'),
        ('10', 'Octobre'),
        ('11', 'Novembre'),
        ('12', 'Décembre'),
    ]
    
    # Pagination
    paginator = Paginator(queryset, 20)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)
    
    # Log de l'accès
    log_user_action(
        user,
        "CONSULTATION_LISTE_HISTORIQUES",
        f"Consultation de la liste des historiques | "
        f"Filtres: poste={poste_filter or 'Tous'}, mois={mois_filter or 'Tous'}, année={annee_filter or 'Toutes'} | "
        f"Résultats: {stats['total_historiques']} historique(s) | "
        f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
        request
    )
    
    context = {
        # Données principales
        'historiques': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        
        # Statistiques
        'stats': stats,
        
        # Filtres - VARIABLES CORRIGÉES
        'postes': postes_accessibles,  # <-- AJOUTÉ (queryset de postes)
        'annees_disponibles': annees_disponibles,  # <-- AJOUTÉ
        'mois_disponibles': mois_disponibles,  # <-- AJOUTÉ
        'current_filters': current_filters,  # <-- AJOUTÉ
        
        # Permissions - NOMS CORRIGÉS
        'acces_tous_postes': acces_tous_postes,
        'can_add': peut_saisir_historique(user),  # <-- RENOMMÉ (était 'peut_saisir')
        'can_delete': peut_supprimer_historique(user),  # <-- RENOMMÉ (était 'peut_supprimer')
        'is_admin': is_admin_user(user),
        
        # Recherche
        'query': query,
        
        # Métadonnées
        'title': _("Liste des historiques de quittances"),
    }
    
    return render(request, 'inventaire/liste_historiques.html', context)


# ===================================================================
# VUE: DÉTAIL D'UN HISTORIQUE
# ===================================================================

@login_required
def detail_historique(request, pk):
    """
    Affiche le détail d'un historique de quittance.
    """
    user = request.user
    
    historique = get_object_or_404(HistoriqueQuittance, pk=pk)
    
    # Vérifier l'accès
    acces_tous_postes = user_has_acces_tous_postes(user)
    if not acces_tous_postes:
        poste_user = get_poste_utilisateur(user)
        if not poste_user or historique.poste_id != poste_user.id:
            log_user_action(
                user,
                "ACCES_REFUSE",
                f"Tentative d'accès au détail historique {historique.numero_historique} | "
                f"Poste historique: {historique.poste.nom} | "
                f"Poste utilisateur: {poste_user.nom if poste_user else 'Aucun'} | "
                f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
                request
            )
            messages.error(request, _("Vous n'avez pas accès à cet historique."))
            return redirect('inventaire:liste_historiques')
    
    # Log de la consultation
    log_user_action(
        user,
        "CONSULTATION_DETAIL_HISTORIQUE",
        f"Consultation du détail de l'historique {historique.numero_historique} | "
        f"Poste: {historique.poste.nom} | "
        f"Mois: {historique.get_mois_display()} | "
        f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
        request
    )
    
    context = {
        'historique': historique,
        'is_admin': is_admin_user(user),
        'peut_supprimer': peut_supprimer_historique(user),
        'title': f"Historique {historique.numero_historique}",
    }
    
    return render(request, 'inventaire/detail_historique.html', context)


# ===================================================================
# VUE: SUPPRESSION D'UN HISTORIQUE
# ===================================================================

@login_required
def supprimer_historique(request, pk):
    """
    Supprime un historique de quittance.
    
    RÉSERVÉ AUX ADMINISTRATEURS:
    - admin_principal
    - coord_psrr
    - serv_info
    - serv_emission
    - serv_controle
    
    La suppression libère le mois pour un nouvel enregistrement.
    """
    user = request.user
    
    historique = get_object_or_404(HistoriqueQuittance, pk=pk)
    
    # Vérifier la permission de suppression
    if not peut_supprimer_historique(user):
        log_user_action(
            user,
            "ACCES_REFUSE",
            f"Tentative de suppression de l'historique {historique.numero_historique} | "
            f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
            f"Permission refusée (non administrateur) | "
            f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            request
        )
        messages.error(request, _("Seuls les administrateurs peuvent supprimer des historiques."))
        return redirect('inventaire:liste_historiques')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirmer':
            # Sauvegarder les infos pour le log avant suppression
            numero = historique.numero_historique
            poste_nom = historique.poste.nom
            poste_code = historique.poste.code
            mois_display = historique.get_mois_display()
            montant_reel = historique.montant_reel
            
            # Supprimer l'image si elle existe
            if historique.image_historique:
                historique.image_historique.delete(save=False)
            
            # Supprimer l'historique
            historique.delete()
            
            # Log de la suppression
            log_user_action(
                user,
                "SUPPRESSION_HISTORIQUE_QUITTANCE",
                f"Suppression de l'historique de quittance | "
                f"Numéro: {numero} | "
                f"Poste: {poste_nom} ({poste_code}) | "
                f"Mois: {mois_display} | "
                f"Montant réel supprimé: {montant_reel:,.0f} FCFA | "
                f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
                request
            )
            
            logger.info(
                f"[HISTORIQUE] {user.username} a supprimé l'historique {numero} | "
                f"Poste: {poste_nom} | Mois libéré: {mois_display}"
            )
            
            messages.success(
                request,
                _("Historique %(numero)s supprimé. Le mois %(mois)s est maintenant disponible pour %(poste)s.") % {
                    'numero': numero,
                    'mois': mois_display,
                    'poste': poste_nom
                }
            )
            
            return redirect('inventaire:liste_historiques')
        
        else:
            # Annuler
            return redirect('inventaire:liste_historiques')
    
    context = {
        'historique': historique,
        'is_admin': is_admin_user(user),
        'title': _("Confirmer la suppression"),
    }
    
    return render(request, 'inventaire/supprimer_historique_confirm.html', context)