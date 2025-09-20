from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Sum, Count, Q
from django.http import JsonResponse
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
from django.contrib import messages
from django.shortcuts import render, redirect
from .models import *

@login_required
def statistiques_taux_deperdition(request):
    """Vue principale pour les statistiques de taux de déperdition"""
    
    # Récupération des paramètres
    periode = request.GET.get('periode', 'mensuel')
    annee = request.GET.get('annee', date.today().year)
    poste_id = request.GET.get('poste', 'tous')
    
    # Vérifier les permissions
    if not request.user.is_admin:
        # Les chefs ne voient que le dimanche
        if request.user.is_chef_poste and date.today().weekday() != 6:
            messages.warning(request, "Les statistiques de taux sont disponibles uniquement le dimanche")
            return redirect('inventaire:liste_recettes')
    
    # Préparer les filtres
    filters = Q(taux_deperdition__isnull=False)
    
    # Exclure les jours impertinents
    jours_impertinents = ConfigurationJour.objects.filter(
        statut='impertinent'
    ).values_list('date', flat=True)
    filters &= ~Q(date__in=jours_impertinents)
    
    # Filtre par année
    filters &= Q(date__year=annee)
    
    # Filtre par poste
    if poste_id != 'tous':
        filters &= Q(poste_id=poste_id)
    
    # Calculer les statistiques selon la période
    stats = calculer_stats_par_periode(periode, annee, filters)
    
    # Données pour le graphique
    graph_data = preparer_donnees_graphique(stats, periode)
    
    # Statistiques globales
    stats_globales = RecetteJournaliere.objects.filter(filters).aggregate(
        taux_moyen=Avg('taux_deperdition'),
        total_recettes=Count('id'),
        montant_total=Sum('montant_declare'),
        montant_potentiel_total=Sum('recette_potentielle')
    )
    
    # Calculer l'écart global
    if stats_globales['montant_potentiel_total']:
        ecart_global = (
            (stats_globales['montant_total'] - stats_globales['montant_potentiel_total']) 
            / stats_globales['montant_potentiel_total'] * 100
        )
    else:
        ecart_global = 0
    
    context = {
        'periode': periode,
        'annee': annee,
        'annees_disponibles': range(2020, date.today().year + 1),
        'poste_selectionne': poste_id,
        'postes': Poste.objects.filter(is_active=True),
        'stats': stats,
        'stats_globales': stats_globales,
        'ecart_global': ecart_global,
        'graph_data_json': json.dumps(graph_data, default=str),
        'can_export': request.user.is_admin,
    }
    
    return render(request, 'inventaire/statistiques_taux.html', context)

def calculer_stats_par_periode(periode, annee, filters):
    """Calcule les statistiques selon la période demandée"""
    from django.db.models import Avg, Count, Sum
    from calendar import monthrange
    
    stats = []
    
    if periode == 'hebdomadaire':
        # Stats par semaine
        date_debut = date(annee, 1, 1)
        date_fin = date(annee, 12, 31)
        current = date_debut
        semaine_num = 1
        
        while current <= date_fin:
            fin_semaine = current + timedelta(days=6)
            
            week_stats = RecetteJournaliere.objects.filter(
                filters,
                date__gte=current,
                date__lte=fin_semaine
            ).aggregate(
                taux_moyen=Avg('taux_deperdition'),
                nombre_jours=Count('id'),
                montant_total=Sum('montant_declare')
            )
            
            if week_stats['nombre_jours'] > 0:
                stats.append({
                    'periode': f'Semaine {semaine_num}',
                    'date_debut': current,
                    'date_fin': fin_semaine,
                    'taux_moyen': float(week_stats['taux_moyen'] or 0),
                    'nombre_jours': week_stats['nombre_jours'],
                    'montant_total': float(week_stats['montant_total'] or 0),
                    'couleur': get_couleur_taux(week_stats['taux_moyen'])
                })
            
            current = fin_semaine + timedelta(days=1)
            semaine_num += 1
    
    elif periode == 'mensuel':
        # Stats par mois
        for mois in range(1, 13):
            month_stats = RecetteJournaliere.objects.filter(
                filters,
                date__month=mois
            ).aggregate(
                taux_moyen=Avg('taux_deperdition'),
                nombre_jours=Count('id'),
                montant_total=Sum('montant_declare')
            )
            
            if month_stats['nombre_jours'] > 0:
                stats.append({
                    'periode': get_month_name(mois),
                    'mois': mois,
                    'taux_moyen': float(month_stats['taux_moyen'] or 0),
                    'nombre_jours': month_stats['nombre_jours'],
                    'montant_total': float(month_stats['montant_total'] or 0),
                    'couleur': get_couleur_taux(month_stats['taux_moyen'])
                })
    
    elif periode == 'trimestriel':
        # Stats par trimestre
        trimestres = [
            (1, 'Q1', [1, 2, 3]),
            (2, 'Q2', [4, 5, 6]),
            (3, 'Q3', [7, 8, 9]),
            (4, 'Q4', [10, 11, 12])
        ]
        
        for num, nom, mois_list in trimestres:
            trim_stats = RecetteJournaliere.objects.filter(
                filters,
                date__month__in=mois_list
            ).aggregate(
                taux_moyen=Avg('taux_deperdition'),
                nombre_jours=Count('id'),
                montant_total=Sum('montant_declare')
            )
            
            if trim_stats['nombre_jours'] > 0:
                stats.append({
                    'periode': nom,
                    'trimestre': num,
                    'taux_moyen': float(trim_stats['taux_moyen'] or 0),
                    'nombre_jours': trim_stats['nombre_jours'],
                    'montant_total': float(trim_stats['montant_total'] or 0),
                    'couleur': get_couleur_taux(trim_stats['taux_moyen'])
                })
    
    elif periode == 'semestriel':
        # Stats par semestre
        semestres = [
            (1, 'S1', [1, 2, 3, 4, 5, 6]),
            (2, 'S2', [7, 8, 9, 10, 11, 12])
        ]
        
        for num, nom, mois_list in semestres:
            sem_stats = RecetteJournaliere.objects.filter(
                filters,
                date__month__in=mois_list
            ).aggregate(
                taux_moyen=Avg('taux_deperdition'),
                nombre_jours=Count('id'),
                montant_total=Sum('montant_declare')
            )
            
            if sem_stats['nombre_jours'] > 0:
                stats.append({
                    'periode': nom,
                    'semestre': num,
                    'taux_moyen': float(sem_stats['taux_moyen'] or 0),
                    'nombre_jours': sem_stats['nombre_jours'],
                    'montant_total': float(sem_stats['montant_total'] or 0),
                    'couleur': get_couleur_taux(sem_stats['taux_moyen'])
                })
    
    elif periode == 'annuel':
        # Stats annuelles (comparaison sur plusieurs années)
        for year in range(annee - 2, annee + 1):
            year_stats = RecetteJournaliere.objects.filter(
                filters,
                date__year=year
            ).aggregate(
                taux_moyen=Avg('taux_deperdition'),
                nombre_jours=Count('id'),
                montant_total=Sum('montant_declare')
            )
            
            if year_stats['nombre_jours'] > 0:
                stats.append({
                    'periode': str(year),
                    'annee': year,
                    'taux_moyen': float(year_stats['taux_moyen'] or 0),
                    'nombre_jours': year_stats['nombre_jours'],
                    'montant_total': float(year_stats['montant_total'] or 0),
                    'couleur': get_couleur_taux(year_stats['taux_moyen'])
                })
    
    return stats

def get_couleur_taux(taux):
    """Retourne la couleur selon le taux"""
    if taux is None:
        return 'secondary'
    taux = float(taux)
    if taux > -5:
        return 'secondary'  # Impertinent
    elif -5 >= taux >= -29.99:
        return 'success'    # Bon
    else:
        return 'danger'     # Mauvais

def get_month_name(month):
    """Retourne le nom du mois en français"""
    mois = {
        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
        5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
        9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
    }
    return mois.get(month, '')

def preparer_donnees_graphique(stats, periode):
    """Prépare les données pour Chart.js"""
    if not stats:
        return {'labels': [], 'data': [], 'colors': []}
    
    labels = [s['periode'] for s in stats]
    data = [s['taux_moyen'] for s in stats]
    
    # Couleurs pour le graphique
    colors = []
    for taux in data:
        if taux > -5:
            colors.append('rgba(108, 117, 125, 0.8)')  # Gris
        elif -5 >= taux >= -29.99:
            colors.append('rgba(40, 167, 69, 0.8)')     # Vert
        else:
            colors.append('rgba(220, 53, 69, 0.8)')     # Rouge
    
    return {
        'labels': labels,
        'data': data,
        'colors': colors,
        'borderColors': [c.replace('0.8', '1') for c in colors]
    }

@login_required
def statistiques_recettes(request):
    """Vue pour les statistiques détaillées des recettes"""
    
    # Paramètres de filtrage
    periode = request.GET.get('periode', 'mensuel')
    annee = int(request.GET.get('annee', date.today().year))
    poste_id = request.GET.get('poste', 'tous')
    type_stat = request.GET.get('type_stat', 'montants')  # montants ou comparaison
    
    # Vérification permissions pour chefs de poste
    if request.user.is_chef_poste and not request.user.is_admin:
        if date.today().weekday() != 6:  # Pas dimanche
            type_stat = 'montants'  # Peuvent voir montants mais pas taux
    
    # Préparer les filtres de base
    filters = Q(date__year=annee)
    
    if poste_id != 'tous':
        filters &= Q(poste_id=poste_id)
    
    # Calculer les statistiques
    stats = calculer_stats_recettes(periode, annee, filters, type_stat)
    
    # Comparaison année précédente
    stats_comparaison = None
    if type_stat == 'comparaison':
        filters_precedent = Q(date__year=annee-1)
        if poste_id != 'tous':
            filters_precedent &= Q(poste_id=poste_id)
        stats_comparaison = calculer_stats_recettes(periode, annee-1, filters_precedent, 'montants')
    
    # Top postes
    top_postes = RecetteJournaliere.objects.filter(
        date__year=annee
    ).values('poste__nom', 'poste__code').annotate(
        total=Sum('montant_declare')
    ).order_by('-total')[:10]
    
    context = {
        'periode': periode,
        'annee': annee,
        'annees_disponibles': range(2020, date.today().year + 1),
        'poste_selectionne': poste_id,
        'postes': Poste.objects.filter(is_active=True).order_by('nom'),
        'type_stat': type_stat,
        'stats': stats,
        'stats_comparaison': stats_comparaison,
        'top_postes': top_postes,
        'graph_data_json': json.dumps(preparer_donnees_recettes_graph(stats, stats_comparaison), default=str),
        'peut_voir_taux': request.user.is_admin or (request.user.is_chef_poste and date.today().weekday() == 6)
    }
    
    return render(request, 'inventaire/statistiques_recettes.html', context)

def calculer_stats_recettes(periode, annee, filters, type_stat):
    """Calcule les statistiques de recettes par période"""
    stats = []
    
    if periode == 'hebdomadaire':
        # 52 semaines dans l'année
        for semaine in range(1, 53):
            date_debut = date(annee, 1, 1) + timedelta(weeks=semaine-1)
            date_fin = date_debut + timedelta(days=6)
            
            if date_debut.year != annee:
                continue
                
            week_data = RecetteJournaliere.objects.filter(
                filters,
                date__gte=date_debut,
                date__lte=date_fin
            ).aggregate(
                montant_total=Sum('montant_declare'),
                montant_potentiel=Sum('recette_potentielle'),
                nombre_jours=Count('id'),
                taux_moyen=Avg('taux_deperdition')
            )
            
            if week_data['nombre_jours'] > 0:
                ecart = 0
                if week_data['montant_potentiel']:
                    ecart = ((week_data['montant_total'] - week_data['montant_potentiel']) 
                            / week_data['montant_potentiel'] * 100)
                
                stats.append({
                    'periode': f'S{semaine}',
                    'semaine': semaine,
                    'date_debut': date_debut,
                    'date_fin': date_fin,
                    'montant_total': float(week_data['montant_total'] or 0),
                    'montant_potentiel': float(week_data['montant_potentiel'] or 0),
                    'ecart': ecart,
                    'taux_moyen': float(week_data['taux_moyen'] or 0),
                    'nombre_jours': week_data['nombre_jours']
                })
    
    elif periode == 'mensuel':
        mois_noms = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                     'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
        
        for mois in range(1, 13):
            month_data = RecetteJournaliere.objects.filter(
                filters,
                date__month=mois
            ).aggregate(
                montant_total=Sum('montant_declare'),
                montant_potentiel=Sum('recette_potentielle'),
                nombre_jours=Count('id'),
                taux_moyen=Avg('taux_deperdition')
            )
            
            if month_data['nombre_jours'] > 0:
                ecart = 0
                if month_data['montant_potentiel']:
                    ecart = ((month_data['montant_total'] - month_data['montant_potentiel']) 
                            / month_data['montant_potentiel'] * 100)
                
                stats.append({
                    'periode': mois_noms[mois-1],
                    'mois': mois,
                    'montant_total': float(month_data['montant_total'] or 0),
                    'montant_potentiel': float(month_data['montant_potentiel'] or 0),
                    'ecart': ecart,
                    'taux_moyen': float(month_data['taux_moyen'] or 0),
                    'nombre_jours': month_data['nombre_jours'],
                    'moyenne_journaliere': float(month_data['montant_total'] or 0) / month_data['nombre_jours']
                })
    
    elif periode == 'trimestriel':
        trimestres = [
            ('Q1', [1, 2, 3]),
            ('Q2', [4, 5, 6]),
            ('Q3', [7, 8, 9]),
            ('Q4', [10, 11, 12])
        ]
        
        for nom, mois_list in trimestres:
            trim_data = RecetteJournaliere.objects.filter(
                filters,
                date__month__in=mois_list
            ).aggregate(
                montant_total=Sum('montant_declare'),
                montant_potentiel=Sum('recette_potentielle'),
                nombre_jours=Count('id'),
                taux_moyen=Avg('taux_deperdition')
            )
            
            if trim_data['nombre_jours'] > 0:
                ecart = 0
                if trim_data['montant_potentiel']:
                    ecart = ((trim_data['montant_total'] - trim_data['montant_potentiel']) 
                            / trim_data['montant_potentiel'] * 100)
                
                stats.append({
                    'periode': nom,
                    'montant_total': float(trim_data['montant_total'] or 0),
                    'taux_moyen': float(trim_data['taux_moyen'] or 0),
                    'nombre_jours': trim_data['nombre_jours']
                })
    
    elif periode == 'semestriel':
        semestres = [
            ('Semestre 1', [1, 2, 3, 4, 5, 6]),
            ('Semestre 2', [7, 8, 9, 10, 11, 12])
        ]
        
        for nom, mois_list in semestres:
            sem_data = RecetteJournaliere.objects.filter(
                filters,
                date__month__in=mois_list
            ).aggregate(
                montant_total=Sum('montant_declare'),
                nombre_jours=Count('id'),
                taux_moyen=Avg('taux_deperdition')
            )
            
            if sem_data['nombre_jours'] > 0:
                ecart = 0
                if sem_data['montant_potentiel']:
                    ecart = ((sem_data['montant_total'] - sem_data['montant_potentiel']) 
                            / sem_data['montant_potentiel'] * 100)
                
                stats.append({
                    'periode': nom,
                    'montant_total': float(sem_data['montant_total'] or 0),
                    'taux_moyen': float(sem_data['taux_moyen'] or 0),
                    'nombre_jours': sem_data['nombre_jours']
                })
    
    elif periode == 'annuel':
        # Comparaison sur 3 ans
        for year in range(annee - 2, annee + 1):
            year_data = RecetteJournaliere.objects.filter(
                date__year=year
            ).aggregate(
                montant_total=Sum('montant_declare'),
                montant_potentiel=Sum('recette_potentielle'),
                nombre_jours=Count('id'),
                taux_moyen=Avg('taux_deperdition')
            )
            
            if year_data['nombre_jours'] > 0:
                ecart = 0
                if year_data['montant_potentiel']:
                    ecart = ((year_data['montant_total'] - year_data['montant_potentiel']) 
                            / year_data['montant_potentiel'] * 100)
                
                stats.append({
                    'periode': str(year),
                    'annee': year,
                    'montant_total': float(year_data['montant_total'] or 0),
                    'taux_moyen': float(year_data['taux_moyen'] or 0),
                    'nombre_jours': year_data['nombre_jours']
                })
    for stat in stats:
        # Calculer l'évolution pour chaque période
        if 'date_debut' in stat:
            evolution = calculer_evolution_recettes(
                periode='cumul_annuel' if periode == 'annuel' else periode,
                date_reference=stat.get('date_fin', stat.get('date_debut')),
                poste_id=filters.get('poste_id')
            )
            
            stat['evolution_n1'] = evolution['evolution_n1']
            stat['evolution_n2'] = evolution['evolution_n2']
            stat['montant_n1'] = evolution['annee_n1']
            stat['montant_n2'] = evolution['annee_n2']
    
    return stats

def preparer_donnees_recettes_graph(stats, stats_comparaison=None):
    """Prépare les données pour le graphique de recettes"""
    if not stats:
        return {'labels': [], 'datasets': []}
    
    labels = [s['periode'] for s in stats]
    
    datasets = [{
        'label': 'Montants déclarés',
        'data': [s['montant_total'] for s in stats],
        'backgroundColor': 'rgba(54, 162, 235, 0.5)',
        'borderColor': 'rgba(54, 162, 235, 1)',
        'borderWidth': 2
    }]
    
    # Ajouter montants potentiels si disponibles
    # if any(s.get('montant_potentiel') for s in stats):
    #     datasets.append({
    #         'label': 'Montants potentiels',
    #         'data': [s['montant_potentiel'] for s in stats],
    #         'backgroundColor': 'rgba(255, 159, 64, 0.5)',
    #         'borderColor': 'rgba(255, 159, 64, 1)',
    #         'borderWidth': 2
    #     })
    
    # Ajouter comparaison année précédente si disponible
    if stats_comparaison:
        datasets.append({
            'label': 'Année précédente',
            'data': [s['montant_total'] for s in stats_comparaison],
            'backgroundColor': 'rgba(201, 203, 207, 0.5)',
            'borderColor': 'rgba(201, 203, 207, 1)',
            'borderWidth': 1,
            'type': 'line'
        })
    
    return {
        'labels': labels,
        'datasets': datasets
    }

# Dans inventaire/views.py - Nouvelle fonction pour calculer l'évolution
def calculer_evolution_recettes(periode, date_reference, poste_id=None):
    """
    Calcule l'évolution des recettes par rapport aux années précédentes
    """
    from django.db.models import Sum
    from datetime import timedelta
    
    evolution = {
        'annee_n': 0,
        'annee_n1': 0,
        'annee_n2': 0,
        'evolution_n1': None,
        'evolution_n2': None
    }
    
    # Filtres de base
    base_filter = Q()
    if poste_id and poste_id != 'tous':
        base_filter &= Q(poste_id=poste_id)
    
    # Calcul selon la période
    if periode == 'jour':
        dates = {
            'n': date_reference,
            'n1': date_reference.replace(year=date_reference.year - 1),
            'n2': date_reference.replace(year=date_reference.year - 2)
        }
        
        for key, date_calc in dates.items():
            result = RecetteJournaliere.objects.filter(
                base_filter,
                date=date_calc
            ).aggregate(total=Sum('montant_declare'))
            
            if key == 'n':
                evolution['annee_n'] = float(result['total'] or 0)
            elif key == 'n1':
                evolution['annee_n1'] = float(result['total'] or 0)
            elif key == 'n2':
                evolution['annee_n2'] = float(result['total'] or 0)
    
    elif periode == 'cumul_annuel':
        # Du 1er janvier à la date de référence
        for year_offset in [0, 1, 2]:
            year = date_reference.year - year_offset
            date_debut = date(year, 1, 1)
            date_fin = date_reference.replace(year=year)
            
            result = RecetteJournaliere.objects.filter(
                base_filter,
                date__gte=date_debut,
                date__lte=date_fin
            ).aggregate(total=Sum('montant_declare'))
            
            total = float(result['total'] or 0)
            
            if year_offset == 0:
                evolution['annee_n'] = total
            elif year_offset == 1:
                evolution['annee_n1'] = total
            elif year_offset == 2:
                evolution['annee_n2'] = total
    
    elif periode == 'mois':
        # Même mois des années précédentes
        for year_offset in [0, 1, 2]:
            year = date_reference.year - year_offset
            result = RecetteJournaliere.objects.filter(
                base_filter,
                date__year=year,
                date__month=date_reference.month
            ).aggregate(total=Sum('montant_declare'))
            
            total = float(result['total'] or 0)
            
            if year_offset == 0:
                evolution['annee_n'] = total
            elif year_offset == 1:
                evolution['annee_n1'] = total
            elif year_offset == 2:
                evolution['annee_n2'] = total
    
    # Calcul des taux d'évolution
    if evolution['annee_n1'] > 0:
        evolution['evolution_n1'] = ((evolution['annee_n'] - evolution['annee_n1']) / evolution['annee_n1']) * 100
    
    if evolution['annee_n2'] > 0:
        evolution['evolution_n2'] = ((evolution['annee_n'] - evolution['annee_n2']) / evolution['annee_n2']) * 100
    
    return evolution

