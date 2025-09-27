from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Q
from datetime import date, datetime, timedelta
import json
from .models import *

@login_required
@user_passes_test(lambda u: u.is_admin)
def taux_evolution_view(request):
    """Vue améliorée pour les taux d'évolution avec estimations"""
    from inventaire.services.evolution_service import EvolutionService
    
    # Paramètres de filtrage
    type_analyse = request.GET.get('type_analyse', 'mensuel')
    poste_id = request.GET.get('poste', 'tous')
    mois = int(request.GET.get('mois', date.today().month))
    annee = int(request.GET.get('annee', date.today().year))
    
    context = {
        'type_analyse': type_analyse,
        'mois_selectionne': mois,
        'annee_selectionnee': annee,
        'postes': Poste.objects.filter(is_active=True).order_by('nom')
    }
    
    # Filtrer les postes si nécessaire
    if poste_id != 'tous':
        postes = Poste.objects.filter(id=poste_id)
    else:
        postes = Poste.objects.filter(is_active=True)
    
    # Calculer les données selon le type d'analyse
    resultats = []
    
    for poste in postes:
        # Calcul des estimations
        estimation_mensuelle = EvolutionService.estimer_recettes_periode(poste, 'mensuel')
        estimation_trimestrielle = EvolutionService.estimer_recettes_periode(poste, 'trimestriel')
        estimation_semestrielle = EvolutionService.estimer_recettes_periode(poste, 'semestriel')
        estimation_annuelle = EvolutionService.estimer_recettes_periode(poste, 'annuel')
        
        # Calcul des taux d'évolution
        taux_n1 = EvolutionService.calculer_taux_evolution_mensuel(
            poste, mois, annee, annee - 1
        )
        taux_n2 = EvolutionService.calculer_taux_evolution_mensuel(
            poste, mois, annee, annee - 2
        )
        
        # Calcul du risque de baisse annuel
        risque_annuel = EvolutionService.calculer_risque_baisse_annuel(poste)
        
        # Objectifs et réalisation
        realise = poste.get_realisation_annee(annee)
        taux_realisation = poste.get_taux_realisation(annee)
        reste_a_realiser = None
        if poste.objectif_annuel:
            reste_a_realiser = poste.objectif_annuel - realise
        
        resultats.append({
            'poste': poste,
            'estimations': {
                'mensuelle': float(estimation_mensuelle),
                'trimestrielle': float(estimation_trimestrielle),
                'semestrielle': float(estimation_semestrielle),
                'annuelle': float(estimation_annuelle)
            },
            'evolution': {
                'taux_n1': taux_n1,
                'taux_n2': taux_n2,
                'en_baisse_n1': taux_n1 < 0 if taux_n1 else False,
                'en_baisse_n2': taux_n2 < 0 if taux_n2 else False
            },
            'risque_annuel': risque_annuel,
            'objectifs': {
                'objectif_annuel': float(poste.objectif_annuel) if poste.objectif_annuel else None,
                'realise': float(realise),
                'taux_realisation': float(taux_realisation) if taux_realisation else None,
                'reste_a_realiser': float(reste_a_realiser) if reste_a_realiser else None
            }
        })
    
    # Calculs globaux
    totaux = {
        'objectif_global': sum(r['objectifs']['objectif_annuel'] or 0 for r in resultats),
        'realise_global': sum(r['objectifs']['realise'] for r in resultats),
        'reste_global': 0
    }
    totaux['reste_global'] = totaux['objectif_global'] - totaux['realise_global']
    if totaux['objectif_global'] > 0:
        totaux['taux_global'] = (totaux['realise_global'] / totaux['objectif_global'] * 100)
    else:
        totaux['taux_global'] = 0
    
    # Identifier les postes en baisse
    postes_baisse_mensuelle = [r for r in resultats if r['evolution']['en_baisse_n1']]
    postes_baisse_annuelle = [r for r in resultats if r['risque_annuel'] and r['risque_annuel']['en_baisse']]
    
    context.update({
        'resultats': resultats,
        'totaux': totaux,
        'postes_baisse_mensuelle': postes_baisse_mensuelle,
        'postes_baisse_annuelle': postes_baisse_annuelle
    })
    
    return render(request, 'inventaire/taux_evolution_avance.html', context)