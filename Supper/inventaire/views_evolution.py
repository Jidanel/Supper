#inventaire/views_evolution.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum
from datetime import date
from decimal import Decimal

from .models import Poste, RecetteJournaliere
from inventaire.services.evolution_service import EvolutionService
from inventaire.models import ObjectifAnnuel
from inventaire.services.forecasting_service import ForecastingService

@login_required
@user_passes_test(lambda u: u.is_admin)
def taux_evolution_view(request):
    """Vue améliorée avec prévisions statistiques"""
    
    type_analyse = request.GET.get('type_analyse', 'mensuel')
    poste_id = request.GET.get('poste', 'tous')
    mois = int(request.GET.get('mois', date.today().month))
    annee = int(request.GET.get('annee', date.today().year))
    
    if poste_id != 'tous':
        postes = Poste.objects.filter(id=poste_id, is_active=True)
    else:
        postes = Poste.objects.filter(is_active=True)
    
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
        estimations_result = ForecastingService.calculer_estimations_periodes(poste)
        
        if estimations_result:
            estimations = estimations_result['estimations_simples']
        else:
            # Fallback sur anciennes estimations si pas assez de données
            estimations = {
                'mensuelle': 0,
                'trimestrielle': 0,
                'semestrielle': 0,
                'annuelle': 0
            }
        
        # Évolutions
        if type_analyse == 'mensuel':
            taux_n1 = EvolutionService.calculer_taux_evolution_mensuel(poste, mois, annee, annee - 1)
            taux_n2 = EvolutionService.calculer_taux_evolution_mensuel(poste, mois, annee, annee - 2)
        else:
            taux_n1 = EvolutionService.calculer_evolution_annuelle_cumulee(poste, mois, annee, annee - 1)
            taux_n2 = EvolutionService.calculer_evolution_annuelle_cumulee(poste, mois, annee, annee - 2)
        
        # Calculs objectifs
        reste_a_realiser = objectif_annee - realise_annee if objectif_annee else None
        taux_realisation = (realise_annee / objectif_annee * 100) if objectif_annee and objectif_annee > 0 else 0
        
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
        'annee_selectionnee': annee,
        'postes': Poste.objects.filter(is_active=True).order_by('nom'),
        'resultats': resultats,
        'totaux': totaux,
    }
    
    return render(request, 'inventaire/taux_evolution_avance.html', context)