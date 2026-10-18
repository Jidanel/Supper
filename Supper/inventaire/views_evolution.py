# ===================================================================
# inventaire/views_evolution.py - Vue des taux d'évolution SUPPER
# VERSION CORRIGÉE - Écarts N-1/N-2, projection au 31/12 (annuel)
# et projection fin de mois (mensuel)
# ===================================================================

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from datetime import date
from decimal import Decimal
import calendar
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
    """
    from functools import wraps
    from django.shortcuts import redirect
    from django.contrib import messages

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user

        if is_admin_user(user):
            return view_func(request, *args, **kwargs)

        permissions_requises = [
            'peut_voir_stats_deperdition',
            'peut_voir_evolution_peage',
            'peut_voir_stats_recettes_peage',
            'peut_voir_statistiques_globales',
        ]

        if has_any_permission(user, permissions_requises):
            return view_func(request, *args, **kwargs)

        if is_cisop(user):
            return view_func(request, *args, **kwargs)

        if is_service_central(user):
            return view_func(request, *args, **kwargs)

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
    Vue améliorée avec projections et écarts N-1/N-2.

    Mode mensuel :
      - Projection au dernier jour du mois sélectionné
      - Écart et taux vs même mois N-1
      - Écart et taux vs même mois N-2

    Mode annuel :
      - Projection au 31 décembre
      - Écart et taux vs total annuel N-1
      - Écart et taux vs total annuel N-2
    """
    user = request.user

    log_user_action(
        user=user,
        action="ACCES_TAUX_EVOLUTION",
        details="Consultation page taux d'évolution",
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
        if poste_id != 'tous':
            try:
                postes = Poste.objects.filter(id=poste_id, is_active=True, type='peage')
            except (ValueError, Poste.DoesNotExist):
                postes = Poste.objects.filter(is_active=True, type='peage')
        else:
            postes = Poste.objects.filter(is_active=True, type='peage')

        postes_pour_filtre = Poste.objects.filter(is_active=True).order_by('nom')
    else:
        postes_accessibles = get_postes_accessibles(user)

        if poste_id != 'tous' and postes_accessibles.filter(id=poste_id).exists():
            postes = postes_accessibles.filter(id=poste_id)
        else:
            postes = postes_accessibles

        postes_pour_filtre = postes_accessibles

    log_user_action(
        user=user,
        action="RECHERCHE_TAUX_EVOLUTION",
        details=f"Paramètres: type={type_analyse}, mois={mois}, annee={annee}, "
                f"poste={poste_id}, nb_postes={postes.count()}",
        succes=True
    )

    resultats = []
    postes_baisse_mensuelle = []
    postes_baisse_annuelle = []

    # Noms des mois en français
    MOIS_FR = [
        '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ]

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

        # Estimations forecasting
        try:
            estimations_result = ForecastingService.calculer_estimations_periodes(poste)
            if estimations_result:
                estimations = estimations_result['estimations_simples']
            else:
                estimations = {
                    'mensuelle': 0, 'trimestrielle': 0,
                    'semestrielle': 0, 'annuelle': 0
                }
        except Exception as e:
            logger.warning(f"[taux_evolution] Erreur estimations pour {poste.nom}: {e}")
            estimations = {
                'mensuelle': 0, 'trimestrielle': 0,
                'semestrielle': 0, 'annuelle': 0
            }

        # ===============================================================
        # CALCUL DES ÉVOLUTIONS AVEC ÉCARTS
        # ===============================================================
        try:
            if type_analyse == 'mensuel':
                evo_n1 = EvolutionService.calculer_taux_evolution_mensuel(
                    poste, mois, annee, annee - 1
                )
                evo_n2 = EvolutionService.calculer_taux_evolution_mensuel(
                    poste, mois, annee, annee - 2
                )
            else:
                evo_n1 = EvolutionService.calculer_evolution_annuelle_cumulee(
                    poste, mois, annee, annee - 1
                )
                evo_n2 = EvolutionService.calculer_evolution_annuelle_cumulee(
                    poste, mois, annee, annee - 2
                )
        except Exception as e:
            logger.warning(f"[taux_evolution] Erreur évolution pour {poste.nom}: {e}")
            evo_n1 = {'taux': None, 'ecart': 0, 'montant_n': 0, 'montant_ref': 0}
            evo_n2 = {'taux': None, 'ecart': 0, 'montant_n': 0, 'montant_ref': 0}

        taux_n1 = evo_n1.get('taux')
        taux_n2 = evo_n2.get('taux')
        ecart_n1 = evo_n1.get('ecart', 0)
        ecart_n2 = evo_n2.get('ecart', 0)

        en_baisse_n1 = taux_n1 is not None and taux_n1 < 0
        en_baisse_n2 = taux_n2 is not None and taux_n2 < 0

        # Objectifs
        reste_a_realiser = objectif_annee - realise_annee if objectif_annee else None
        taux_realisation = (
            (realise_annee / objectif_annee * 100)
            if objectif_annee and objectif_annee > 0 else 0
        )

        resultat = {
            'poste': poste,
            'estimations': estimations,
            'evolution': {
                'taux_n1': taux_n1,
                'taux_n2': taux_n2,
                'ecart_n1': ecart_n1,
                'ecart_n2': ecart_n2,
                'en_baisse_n1': en_baisse_n1,
                'en_baisse_n2': en_baisse_n2,
                'montant_n_n1': evo_n1.get('montant_n', evo_n1.get('estimation_31dec', 0)),
                'montant_ref_n1': evo_n1.get('montant_ref', evo_n1.get('total_ref', 0)),
                'montant_n_n2': evo_n2.get('montant_n', evo_n2.get('estimation_31dec', 0)),
                'montant_ref_n2': evo_n2.get('montant_ref', evo_n2.get('total_ref', 0)),
            },
            'objectifs': {
                'objectif_annuel': float(objectif_annee),
                'realise': float(realise_annee),
                'taux_realisation': float(taux_realisation),
                'reste_a_realiser': float(reste_a_realiser) if reste_a_realiser else None,
                'annee': annee,
            }
        }
        resultats.append(resultat)

        # Collecter les postes en baisse pour affichage séparé
        if en_baisse_n1:
            if type_analyse == 'mensuel':
                postes_baisse_mensuelle.append(resultat)
            else:
                postes_baisse_annuelle.append(resultat)

    # Trier par taux de baisse
    postes_baisse_mensuelle.sort(key=lambda x: x['evolution']['taux_n1'] or 0)
    postes_baisse_annuelle.sort(key=lambda x: x['evolution']['taux_n1'] or 0)

    # Totaux globaux
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

    context = {
        'type_analyse': type_analyse,
        'mois_selectionne': mois,
        'mois_nom': MOIS_FR[mois],
        'annee_selectionnee': annee,
        'annee_n1': annee - 1,
        'annee_n2': annee - 2,
        'postes': postes_pour_filtre,
        'resultats': resultats,
        'totaux': totaux,
        'acces_tous_postes': user_has_acces_tous_postes(user),
        'poste_selectionne': poste_id,
        'postes_baisse_mensuelle': postes_baisse_mensuelle,
        'postes_baisse_annuelle': postes_baisse_annuelle,
    }

    return render(request, 'inventaire/taux_evolution_avance.html', context)