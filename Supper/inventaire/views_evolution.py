from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum
from datetime import date
from decimal import Decimal

from .models import Poste, RecetteJournaliere
from inventaire.services.evolution_service import EvolutionService
from inventaire.models import ObjectifAnnuel


@login_required
@user_passes_test(lambda u: u.is_admin)
def taux_evolution_view(request):
    """Vue améliorée pour les taux d'évolution avec estimations et objectifs précis par année sélectionnée."""
    
    # Récupération des paramètres GET avec valeurs par défaut
    type_analyse = request.GET.get('type_analyse', 'mensuel')
    poste_id = request.GET.get('poste', 'tous')
    mois = int(request.GET.get('mois', date.today().month))
    annee = int(request.GET.get('annee', date.today().year))

    # Préparer la liste des postes selon filtre
    if poste_id != 'tous':
        postes = Poste.objects.filter(id=poste_id, is_active=True)
    else:
        postes = Poste.objects.filter(is_active=True)
    
    # Construction du contexte initial
    context = {
        'type_analyse': type_analyse,
        'mois_selectionne': mois,
        'annee_selectionnee': annee,
        'postes': postes.order_by('nom'),
    }
    
    resultats = []
    
    for poste in postes:
        # Estimations de recettes sur différentes périodes
        estimations = {
            'mensuelle': float(EvolutionService.estimer_recettes_periode(poste, 'mensuel')),
            'trimestrielle': float(EvolutionService.estimer_recettes_periode(poste, 'trimestriel')),
            'semestrielle': float(EvolutionService.estimer_recettes_periode(poste, 'semestriel')),
            'annuelle': float(EvolutionService.estimer_recettes_periode(poste, 'annuel')),
        }
        
        # Taux d'évolution mensuelle (comparaison avec année précédente et avant-dernière)
        taux_n1 = EvolutionService.calculer_taux_evolution_mensuel(poste, mois, annee, annee - 1)
        taux_n2 = EvolutionService.calculer_taux_evolution_mensuel(poste, mois, annee, annee - 2)
        
        # Risque annuel de baisse
        risque_annuel = EvolutionService.calculer_risque_baisse_annuel(poste)
        
        # Récupération de l'objectif annuel depuis ObjectifAnnuel pour l'année sélectionnée
        objectif_montant = None
        try:
            objectif_obj = ObjectifAnnuel.objects.get(poste=poste, annee=annee)
            objectif_montant = objectif_obj.montant_objectif
        except ObjectifAnnuel.DoesNotExist:
            objectif_montant = None
        
        # Calcul du total réalisé pour l'année sélectionnée
        realise = RecetteJournaliere.objects.filter(poste=poste, date__year=annee).aggregate(
            total=Sum('montant_declare')
        )['total'] or Decimal('0')
        
        # Calcul du taux de réalisation et reste à réaliser
        taux_realisation = None
        reste_a_realiser = None
        if objectif_montant and objectif_montant > 0:
            taux_realisation = (realise / objectif_montant) * 100
            reste_a_realiser = objectif_montant - realise
        
        # Ajout des données au résultat
        resultats.append({
            'poste': poste,
            'estimations': estimations,
            'evolution': {
                'taux_n1': taux_n1,
                'taux_n2': taux_n2,
                'en_baisse_n1': taux_n1 < 0 if taux_n1 is not None else False,
                'en_baisse_n2': taux_n2 < 0 if taux_n2 is not None else False,
            },
            'risque_annuel': risque_annuel,
            'objectifs': {
                'objectif_annuel': float(objectif_montant) if objectif_montant else None,
                'realise': float(realise),
                'taux_realisation': float(taux_realisation) if taux_realisation else None,
                'reste_a_realiser': float(reste_a_realiser) if reste_a_realiser else None,
                'annee': annee,  # pour clarté dans le contexte
            },
        })
    
    # Calculs globaux pour l'année sélectionnée
    totaux = {
        'objectif_global': ObjectifAnnuel.objects.filter(poste__in=postes, annee=annee).aggregate(
            total=Sum('montant_objectif')
        )['total'] or 0,
        'realise_global': RecetteJournaliere.objects.filter(poste__in=postes, date__year=annee).aggregate(
            total=Sum('montant_declare')
        )['total'] or 0,
    }
    
    totaux['reste_global'] = totaux['objectif_global'] - totaux['realise_global']
    totaux['taux_global'] = (
        (totaux['realise_global'] / totaux['objectif_global'] * 100) if totaux['objectif_global'] > 0 else 0
    )
    
    # Sélection des postes en diminution mensuelle et en risque annuel
    postes_baisse_mensuelle = [r for r in resultats if r['evolution']['en_baisse_n1']]
    postes_baisse_annuelle = [r for r in resultats if r['risque_annuel'] and r['risque_annuel'].get('en_baisse', False)]
    
    context.update({
        'resultats': resultats,
        'totaux': totaux,
        'postes_baisse_mensuelle': postes_baisse_mensuelle,
        'postes_baisse_annuelle': postes_baisse_annuelle,
    })
    
    return render(request, 'inventaire/taux_evolution_avance.html', context)
