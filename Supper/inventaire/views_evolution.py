# ===================================================================
# inventaire/views_evolution.py - Vue des taux d'évolution SUPPER
# VERSION MISE À JOUR - Intégration des permissions granulaires
# ===================================================================

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from datetime import date
from decimal import Decimal
import logging

from .models import Poste, RecetteJournaliere
from inventaire.services.evolution_service import EvolutionService
from inventaire.models import ObjectifAnnuel
from inventaire.services.forecasting_service import ForecastingService

# ===================================================================
# IMPORTS DES PERMISSIONS GRANULAIRES DU PROJET
# ===================================================================
from common.permissions import (
    is_admin_user,
    is_service_central,
    is_cisop,
    user_has_acces_tous_postes,
    get_postes_accessibles,
    get_postes_peage_accessibles,
    check_poste_access,
    has_permission,
    has_any_permission,
    log_acces_refuse,
)

from common.decorators import (
    permission_required_granular,
    admin_required,
    stats_deperdition_required,
)

from common.utils import log_user_action

logger = logging.getLogger('supper.evolution')


# ===================================================================
# DÉCORATEUR POUR L'ACCÈS AUX STATISTIQUES D'ÉVOLUTION
# ===================================================================

def evolution_stats_required(view_func):
    """
    Décorateur vérifiant l'accès aux statistiques d'évolution.
    
    PERMISSIONS REQUISES (au moins une):
    - peut_voir_stats_deperdition
    - peut_voir_evolution_peage
    - peut_voir_stats_recettes_peage
    - Être admin (admin_principal, coord_psrr, serv_info)
    - Être CISOP péage
    """
    from functools import wraps
    from django.shortcuts import redirect
    from django.contrib import messages
    
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        
        # Admin a toujours accès
        if is_admin_user(user):
            logger.info(
                f"[evolution_stats] Accès ADMIN accordé à {user.username} "
                f"pour {view_func.__name__}"
            )
            return view_func(request, *args, **kwargs)
        
        # Vérifier les permissions granulaires
        permissions_requises = [
            'peut_voir_stats_deperdition',
            'peut_voir_evolution_peage',
            'peut_voir_stats_recettes_peage',
            'peut_voir_statistiques_globales',
        ]
        
        if has_any_permission(user, permissions_requises):
            logger.info(
                f"[evolution_stats] Accès accordé à {user.username} "
                f"(habilitation: {user.habilitation}) pour {view_func.__name__}"
            )
            return view_func(request, *args, **kwargs)
        
        # CISOP a accès
        if is_cisop(user):
            logger.info(
                f"[evolution_stats] Accès CISOP accordé à {user.username} "
                f"pour {view_func.__name__}"
            )
            return view_func(request, *args, **kwargs)
        
        # Service central a accès
        if is_service_central(user):
            logger.info(
                f"[evolution_stats] Accès SERVICE_CENTRAL accordé à {user.username} "
                f"pour {view_func.__name__}"
            )
            return view_func(request, *args, **kwargs)
        
        # Accès refusé
        log_user_action(
            user=user,
            action="ACCES_STATS_EVOLUTION_REFUSE",
            details=f"Tentative d'accès à {view_func.__name__} refusée - "
                    f"Habilitation: {user.habilitation}",
            succes=False
        )
        log_acces_refuse(user, view_func.__name__, "Accès statistiques évolution non autorisé")
        
        messages.error(
            request, 
            "Vous n'avez pas la permission d'accéder aux statistiques d'évolution."
        )
        return redirect('common:dashboard')
    
    return wrapper


# ===================================================================
# VUE PRINCIPALE DES TAUX D'ÉVOLUTION
# ===================================================================

@login_required
@evolution_stats_required
def taux_evolution_view(request):
    """
    Vue améliorée avec prévisions statistiques.
    
    PERMISSIONS REQUISES:
    - Être admin OU
    - peut_voir_stats_deperdition OU
    - peut_voir_evolution_peage OU
    - Être service central / CISOP
    
    RÈGLES D'ACCÈS AUX POSTES:
    - Utilisateurs avec accès tous postes: voient tous les postes
    - Autres utilisateurs: voient uniquement leur poste d'affectation
    """
    user = request.user
    
    # Log de l'accès à la page
    log_user_action(
        user=user,
        action="ACCES_TAUX_EVOLUTION",
        details=f"Consultation page taux d'évolution",
        succes=True
    )
    
    type_analyse = request.GET.get('type_analyse', 'mensuel')
    poste_id = request.GET.get('poste', 'tous')
    mois = int(request.GET.get('mois', date.today().month))
    annee = int(request.GET.get('annee', date.today().year))
    
    # ===================================================================
    # DÉTERMINER LES POSTES ACCESSIBLES
    # ===================================================================
    
    if user_has_acces_tous_postes(user):
        # Utilisateur avec accès global
        if poste_id != 'tous':
            try:
                postes = Poste.objects.filter(id=poste_id, is_active=True)
            except (ValueError, Poste.DoesNotExist):
                postes = Poste.objects.filter(is_active=True)
        else:
            postes = Poste.objects.filter(is_active=True)
        
        postes_pour_filtre = Poste.objects.filter(is_active=True).order_by('nom')
        logger.debug(
            f"[taux_evolution] Utilisateur {user.username} a accès à tous les postes - "
            f"Filtre: {poste_id}"
        )
    else:
        # Utilisateur avec accès limité à son poste
        postes_accessibles = get_postes_accessibles(user)
        
        if poste_id != 'tous' and postes_accessibles.filter(id=poste_id).exists():
            postes = postes_accessibles.filter(id=poste_id)
        else:
            postes = postes_accessibles
        
        postes_pour_filtre = postes_accessibles
        logger.debug(
            f"[taux_evolution] Utilisateur {user.username} a accès limité - "
            f"Postes: {list(postes_accessibles.values_list('nom', flat=True))}"
        )
    
    # Log des paramètres de recherche
    log_user_action(
        user=user,
        action="RECHERCHE_TAUX_EVOLUTION",
        details=f"Paramètres: type={type_analyse}, mois={mois}, annee={annee}, "
                f"poste={poste_id}, nb_postes={postes.count()}",
        succes=True
    )
    
    resultats = []
    
    for poste in postes:
        # Objectif annuel
        try:
            objectif_obj = ObjectifAnnuel.objects.get(poste=poste, annee=annee)
            objectif_annee = objectif_obj.montant_objectif
        except ObjectifAnnuel.DoesNotExist:
            objectif_annee = Decimal('0')
        
        # Réalisé de l'année
        realise_annee = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        # Utiliser les nouvelles estimations
        try:
            estimations_result = ForecastingService.calculer_estimations_periodes(poste)
            
            if estimations_result:
                estimations = estimations_result['estimations_simples']
            else:
                estimations = {
                    'mensuelle': 0,
                    'trimestrielle': 0,
                    'semestrielle': 0,
                    'annuelle': 0
                }
        except Exception as e:
            logger.warning(
                f"[taux_evolution] Erreur calcul estimations pour {poste.nom}: {e}"
            )
            estimations = {
                'mensuelle': 0,
                'trimestrielle': 0,
                'semestrielle': 0,
                'annuelle': 0
            }
        
        # Évolutions
        try:
            if type_analyse == 'mensuel':
                taux_n1 = EvolutionService.calculer_taux_evolution_mensuel(
                    poste, mois, annee, annee - 1
                )
                taux_n2 = EvolutionService.calculer_taux_evolution_mensuel(
                    poste, mois, annee, annee - 2
                )
            else:
                taux_n1 = EvolutionService.calculer_evolution_annuelle_cumulee(
                    poste, mois, annee, annee - 1
                )
                taux_n2 = EvolutionService.calculer_evolution_annuelle_cumulee(
                    poste, mois, annee, annee - 2
                )
        except Exception as e:
            logger.warning(
                f"[taux_evolution] Erreur calcul évolution pour {poste.nom}: {e}"
            )
            taux_n1 = None
            taux_n2 = None
        
        # Calculs objectifs
        reste_a_realiser = objectif_annee - realise_annee if objectif_annee else None
        taux_realisation = (
            (realise_annee / objectif_annee * 100) 
            if objectif_annee and objectif_annee > 0 else 0
        )
        
        resultats.append({
            'poste': poste,
            'estimations': estimations,
            'evolution': {
                'taux_n1': taux_n1,
                'taux_n2': taux_n2,
                'en_baisse_n1': taux_n1 < 0 if taux_n1 is not None else False,
                'en_baisse_n2': taux_n2 < 0 if taux_n2 is not None else False,
            },
            'objectifs': {
                'objectif_annuel': float(objectif_annee),
                'realise': float(realise_annee),
                'taux_realisation': float(taux_realisation),
                'reste_a_realiser': float(reste_a_realiser) if reste_a_realiser else None,
                'annee': annee,
            }
        })
    
    # Totaux globaux (uniquement pour les postes accessibles)
    totaux = {
        'objectif_global': ObjectifAnnuel.objects.filter(
            poste__in=postes,
            annee=annee
        ).aggregate(total=Sum('montant_objectif'))['total'] or 0,
        
        'realise_global': RecetteJournaliere.objects.filter(
            poste__in=postes,
            date__year=annee
        ).aggregate(total=Sum('montant_declare'))['total'] or 0,
    }
    
    totaux['reste_global'] = totaux['objectif_global'] - totaux['realise_global']
    totaux['taux_global'] = (
        (totaux['realise_global'] / totaux['objectif_global'] * 100) 
        if totaux['objectif_global'] > 0 else 0
    )
    
    logger.info(
        f"[taux_evolution] Résultats générés pour {user.username} - "
        f"{len(resultats)} postes, type={type_analyse}, période={mois}/{annee}"
    )
    
    context = {
        'type_analyse': type_analyse,
        'mois_selectionne': mois,
        'annee_selectionnee': annee,
        'postes': postes_pour_filtre,
        'resultats': resultats,
        'totaux': totaux,
        'acces_tous_postes': user_has_acces_tous_postes(user),
        'poste_selectionne': poste_id,
    }
    
    return render(request, 'inventaire/taux_evolution_avance.html', context)