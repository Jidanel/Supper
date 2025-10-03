# inventaire/views_stats.py - Version corrigée complète
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Sum, Count, Q
from django.http import JsonResponse
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import calendar
from django.contrib import messages
from .models import *
from inventaire.services.evolution_service import EvolutionService

@login_required
def statistiques_taux_deperdition(request):
    """Vue principale pour les statistiques de taux de déperdition"""
    
    periode = request.GET.get('periode', 'mensuel')
    annee = int(request.GET.get('annee', date.today().year))
    poste_id = request.GET.get('poste', 'tous')
    
    if not request.user.is_admin:
        if request.user.is_chef_poste and date.today().weekday() != 6:
            messages.warning(request, "Les statistiques de taux sont disponibles uniquement le dimanche")
            return redirect('inventaire:liste_recettes')
    
    filters = Q(taux_deperdition__isnull=False)
    
    jours_impertinents = ConfigurationJour.objects.filter(
        statut='impertinent'
    ).values_list('date', flat=True)
    filters &= ~Q(date__in=jours_impertinents)
    filters &= Q(date__year=annee)
    
    if poste_id != 'tous':
        filters &= Q(poste_id=poste_id)
    
    stats = calculer_stats_par_periode(periode, annee, filters)
    graph_data = preparer_donnees_graphique(stats, periode)
    
    stats_globales = RecetteJournaliere.objects.filter(filters).aggregate(
        taux_moyen=Avg('taux_deperdition'),
        total_recettes=Count('id'),
        montant_total=Sum('montant_declare'),
        montant_potentiel_total=Sum('recette_potentielle')
    )
    
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
        'annees_disponibles': range(2020, date.today().year + 2),
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
    filters &= Q(inventaire_associe__isnull=False)
    filters &= Q(taux_deperdition__lte=-5)
    
    jours_impertinents = ConfigurationJour.objects.filter(
        statut='impertinent'
    ).values_list('date', flat=True)
    filters &= ~Q(date__in=jours_impertinents)
    
    stats = []
    
    if periode == 'hebdomadaire':
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
                    'periode': f'Semaine {semaine_num} ({current.strftime("%d/%m")} - {fin_semaine.strftime("%d/%m")})',
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
        mois_noms = {
            1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
            5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
            9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
        }
        
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
                    'periode': f'{mois_noms[mois]} {annee}',
                    'mois': mois,
                    'taux_moyen': float(month_stats['taux_moyen'] or 0),
                    'nombre_jours': month_stats['nombre_jours'],
                    'montant_total': float(month_stats['montant_total'] or 0),
                    'couleur': get_couleur_taux(month_stats['taux_moyen'])
                })
    
    elif periode == 'trimestriel':
        trimestres = [
            (1, 'T1 (Janvier-Mars)', [1, 2, 3]),
            (2, 'T2 (Avril-Juin)', [4, 5, 6]),
            (3, 'T3 (Juillet-Septembre)', [7, 8, 9]),
            (4, 'T4 (Octobre-Décembre)', [10, 11, 12])
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
                    'periode': f'{nom} {annee}',
                    'trimestre': num,
                    'taux_moyen': float(trim_stats['taux_moyen'] or 0),
                    'nombre_jours': trim_stats['nombre_jours'],
                    'montant_total': float(trim_stats['montant_total'] or 0),
                    'couleur': get_couleur_taux(trim_stats['taux_moyen'])
                })
    
    elif periode == 'semestriel':
        semestres = [
            (1, 'S1 (Janvier-Juin)', [1, 2, 3, 4, 5, 6]),
            (2, 'S2 (Juillet-Décembre)', [7, 8, 9, 10, 11, 12])
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
                    'periode': f'{nom} {annee}',
                    'semestre': num,
                    'taux_moyen': float(sem_stats['taux_moyen'] or 0),
                    'nombre_jours': sem_stats['nombre_jours'],
                    'montant_total': float(sem_stats['montant_total'] or 0),
                    'couleur': get_couleur_taux(sem_stats['taux_moyen'])
                })
    
    elif periode == 'annuel':
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
                    'periode': f'Année {year}',
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
        return 'secondary'
    elif -5 >= taux >= -29.99:
        return 'success'
    else:
        return 'danger'

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
    
    colors = []
    for taux in data:
        if taux > -5:
            colors.append('rgba(108, 117, 125, 0.8)')
        elif -5 >= taux >= -29.99:
            colors.append('rgba(40, 167, 69, 0.8)')
        else:
            colors.append('rgba(220, 53, 69, 0.8)')
    
    return {
        'labels': labels,
        'data': data,
        'colors': colors,
        'borderColors': [c.replace('0.8', '1') for c in colors]
    }

@login_required
def statistiques_recettes(request):
    """Vue améliorée pour les statistiques détaillées des recettes avec identification des périodes"""
    
    periode = request.GET.get('periode', 'mensuel')
    annee = int(request.GET.get('annee', date.today().year))
    poste_id = request.GET.get('poste', 'tous')
    type_stat = request.GET.get('type_stat', 'montants')
    
    if request.user.is_chef_poste and not request.user.is_admin:
        if date.today().weekday() != 6:
            type_stat = 'montants'
    
    filters = Q(date__year=annee)
    if poste_id != 'tous':
        filters &= Q(poste_id=poste_id)
    
    stats = calculer_stats_recettes(periode, annee, filters, type_stat)
    
    stats_comparaison = None
    if type_stat == 'comparaison':
        filters_precedent = Q(date__year=annee-1)
        if poste_id != 'tous':
            filters_precedent &= Q(poste_id=poste_id)
        stats_comparaison = calculer_stats_recettes(periode, annee-1, filters_precedent, 'montants')
    
    top_postes = RecetteJournaliere.objects.filter(
        date__year=annee
    ).values('poste__nom', 'poste__code').annotate(
        total=Sum('montant_declare')
    ).order_by('-total')[:10]
    
    context = {
        'periode': periode,
        'annee': annee,
        'annees_disponibles': range(2020, date.today().year + 2),
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
    """Calcule les statistiques de recettes par période avec identification claire"""
    stats = []
    
    mois_noms = {
        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
        5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
        9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
    }
    
    if periode == 'hebdomadaire':
        date_debut = date(annee, 1, 1)
        date_fin = date(annee, 12, 31)
        current = date_debut
        semaine_num = 1
        
        while current <= date_fin:
            fin_semaine = current + timedelta(days=6)
            if fin_semaine > date_fin:
                fin_semaine = date_fin
                
            week_data = RecetteJournaliere.objects.filter(
                filters,
                date__gte=current,
                date__lte=fin_semaine
            ).aggregate(
                montant_total=Sum('montant_declare'),
                montant_potentiel=Sum('recette_potentielle'),
                nombre_jours=Count('id'),
                taux_moyen=Avg('taux_deperdition')
            )
            
            if week_data['nombre_jours'] > 0:
                moyenne_jour = float(week_data['montant_total'] or 0) / week_data['nombre_jours']
                
                stats.append({
                    'periode': f'Semaine {semaine_num} ({current.strftime("%d/%m")} - {fin_semaine.strftime("%d/%m")})',
                    'semaine': semaine_num,
                    'date_debut': current,
                    'date_fin': fin_semaine,
                    'montant_total': float(week_data['montant_total'] or 0),
                    'montant_potentiel': float(week_data['montant_potentiel'] or 0),
                    'taux_moyen': float(week_data['taux_moyen'] or 0),
                    'nombre_jours': week_data['nombre_jours'],
                    'moyenne_journaliere': moyenne_jour
                })
            
            current = fin_semaine + timedelta(days=1)
            semaine_num += 1
    
    elif periode == 'mensuel':
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
                moyenne_jour = float(month_data['montant_total'] or 0) / month_data['nombre_jours']
                
                stats.append({
                    'periode': f'{mois_noms[mois]} {annee}',
                    'mois': mois,
                    'mois_num': mois,
                    'montant_total': float(month_data['montant_total'] or 0),
                    'montant_potentiel': float(month_data['montant_potentiel'] or 0),
                    'taux_moyen': float(month_data['taux_moyen'] or 0),
                    'nombre_jours': month_data['nombre_jours'],
                    'moyenne_journaliere': moyenne_jour,
                    'date_debut': date(annee, mois, 1),
                    'date_fin': date(annee, mois, calendar.monthrange(annee, mois)[1])
                })
    
    elif periode == 'trimestriel':
        trimestres = [
            ('T1', 'Janvier-Mars', [1, 2, 3]),
            ('T2', 'Avril-Juin', [4, 5, 6]),
            ('T3', 'Juillet-Septembre', [7, 8, 9]),
            ('T4', 'Octobre-Décembre', [10, 11, 12])
        ]
        
        for code, nom_periode, mois_list in trimestres:
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
                moyenne_jour = float(trim_data['montant_total'] or 0) / trim_data['nombre_jours']
                
                stats.append({
                    'periode': f'{code} {annee}',
                    'trimestre': f'{nom_periode} {annee}',
                    'montant_total': float(trim_data['montant_total'] or 0),
                    'montant_potentiel': float(trim_data['montant_potentiel'] or 0),
                    'taux_moyen': float(trim_data['taux_moyen'] or 0),
                    'nombre_jours': trim_data['nombre_jours'],
                    'moyenne_journaliere': moyenne_jour
                })
    
    elif periode == 'semestriel':
        semestres = [
            ('S1', 'Janvier-Juin', [1, 2, 3, 4, 5, 6]),
            ('S2', 'Juillet-Décembre', [7, 8, 9, 10, 11, 12])
        ]
        
        for code, nom_periode, mois_list in semestres:
            sem_data = RecetteJournaliere.objects.filter(
                filters,
                date__month__in=mois_list
            ).aggregate(
                montant_total=Sum('montant_declare'),
                montant_potentiel=Sum('recette_potentielle'),
                nombre_jours=Count('id'),
                taux_moyen=Avg('taux_deperdition')
            )
            
            if sem_data['nombre_jours'] > 0:
                moyenne_jour = float(sem_data['montant_total'] or 0) / sem_data['nombre_jours']
                
                stats.append({
                    'periode': f'{code} {annee}',
                    'semestre': f'{nom_periode} {annee}',
                    'montant_total': float(sem_data['montant_total'] or 0),
                    'montant_potentiel': float(sem_data['montant_potentiel'] or 0),
                    'taux_moyen': float(sem_data['taux_moyen'] or 0),
                    'nombre_jours': sem_data['nombre_jours'],
                    'moyenne_journaliere': moyenne_jour
                })
    
    elif periode == 'annuel':
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
                moyenne_jour = float(year_data['montant_total'] or 0) / year_data['nombre_jours']
                
                stats.append({
                    'periode': f'Année {year}',
                    'annee': year,
                    'montant_total': float(year_data['montant_total'] or 0),
                    'montant_potentiel': float(year_data['montant_potentiel'] or 0),
                    'taux_moyen': float(year_data['taux_moyen'] or 0),
                    'nombre_jours': year_data['nombre_jours'],
                    'moyenne_journaliere': moyenne_jour
                })
    
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

def calculer_evolution_recettes(periode, date_reference, poste_id=None):
    """Calcule l'évolution des recettes par rapport aux années précédentes"""
    evolution = {
        'annee_n': 0,
        'annee_n1': 0,
        'annee_n2': 0,
        'evolution_n1': None,
        'evolution_n2': None
    }
    
    base_filter = Q()
    if poste_id and poste_id != 'tous':
        base_filter &= Q(poste_id=poste_id)
    
    if periode == 'jour':
        for year_offset in [0, 1, 2]:
            try:
                date_calc = date_reference.replace(year=date_reference.year - year_offset)
            except ValueError:
                continue
                
            result = RecetteJournaliere.objects.filter(
                base_filter,
                date=date_calc
            ).aggregate(total=Sum('montant_declare'))
            
            total = float(result['total'] or 0)
            
            if year_offset == 0:
                evolution['annee_n'] = total
            elif year_offset == 1:
                evolution['annee_n1'] = total
            elif year_offset == 2:
                evolution['annee_n2'] = total
    
    elif periode == 'cumul_annuel':
        for year_offset in [0, 1, 2]:
            year = date_reference.year - year_offset
            date_debut = date(year, 1, 1)
            try:
                date_fin = date_reference.replace(year=year)
            except ValueError:
                date_fin = date(year, date_reference.month, 
                              calendar.monthrange(year, date_reference.month)[1])
            
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
    
    if evolution['annee_n1'] > 0:
        evolution['evolution_n1'] = ((evolution['annee_n'] - evolution['annee_n1']) / evolution['annee_n1']) * 100
    
    if evolution['annee_n2'] > 0:
        evolution['evolution_n2'] = ((evolution['annee_n'] - evolution['annee_n2']) / evolution['annee_n2']) * 100
    
    return evolution