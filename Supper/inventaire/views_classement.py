# inventaire/views_classement.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg, Q
from datetime import date, timedelta
import calendar
from decimal import Decimal

from accounts.models import Poste
from inventaire.models import RecetteJournaliere

@login_required
def classement_postes_rendement(request):
    """
    Vue pour classer les postes par rendement selon différentes périodes
    UNIQUEMENT basé sur montant_declare (recettes déclarées)
    """
    
    periode = request.GET.get('periode', 'mois')
    annee = int(request.GET.get('annee', date.today().year))
    mois = request.GET.get('mois')
    trimestre = request.GET.get('trimestre')
    semestre = request.GET.get('semestre')
    semaine = request.GET.get('semaine')
    
    # Déterminer les dates selon la période
    date_debut, date_fin = calculer_dates_periode(
        periode, annee, mois, trimestre, semestre, semaine
    )
    
    # Récupérer tous les postes actifs
    postes = Poste.objects.filter(is_active=True)
    
    classement = []
    
    for poste in postes:
        # Calculer les statistiques pour ce poste
        stats = RecetteJournaliere.objects.filter(
            poste=poste,
            date__gte=date_debut,
            date__lte=date_fin
        ).aggregate(
            total_declare=Sum('montant_declare'),
            nombre_jours=Count('id'),
            moyenne_jour=Avg('montant_declare')
        )
        
        total = stats['total_declare'] or Decimal('0')
        nb_jours = stats['nombre_jours'] or 0
        moyenne = stats['moyenne_jour'] or Decimal('0')
        
        # Ajouter au classement seulement si le poste a des recettes
        if total > 0:
            classement.append({
                'poste': poste,
                'total_recettes': float(total),
                'nombre_jours': nb_jours,
                'moyenne_journaliere': float(moyenne),
                'region': poste.region,
                'type_poste': poste.type
            })
    
    # Trier par total décroissant
    classement.sort(key=lambda x: x['total_recettes'], reverse=True)
    
    # Ajouter les rangs
    for i, item in enumerate(classement, 1):
        item['rang'] = i
    
    # Calculer statistiques globales
    if classement:
        total_global = sum(p['total_recettes'] for p in classement)
        moyenne_globale = total_global / len(classement)
        
        # Identifier top 3 et bottom 3
        top_3 = classement[:3]
        bottom_3 = classement[-3:] if len(classement) > 3 else []
    else:
        total_global = 0
        moyenne_globale = 0
        top_3 = []
        bottom_3 = []
    
    context = {
        'classement': classement,
        'periode': periode,
        'periode_label': get_periode_label(
            periode, annee, mois, trimestre, semestre, semaine
        ),
        'date_debut': date_debut,
        'date_fin': date_fin,
        'annee': annee,
        'annees_disponibles': range(2020, date.today().year + 2),
        'mois_liste': range(1, 13),
        'trimestres': [1, 2, 3, 4],
        'semestres': [1, 2],
        'total_global': total_global,
        'moyenne_globale': moyenne_globale,
        'nombre_postes': len(classement),
        'top_3': top_3,
        'bottom_3': bottom_3,
        'title': 'Classement des Postes par Rendement'
    }
    
    return render(request, 'inventaire/classement_rendement.html', context)


def calculer_dates_periode(periode, annee, mois=None, trimestre=None, 
                          semestre=None, semaine=None):
    """Calcule les dates de début et fin selon la période"""
    
    if periode == 'semaine':
        if semaine:
            # Semaine spécifique de l'année
            semaine_num = int(semaine)
            date_debut = date(annee, 1, 1) + timedelta(weeks=semaine_num-1)
            date_fin = date_debut + timedelta(days=6)
        else:
            # Semaine en cours
            today = date.today()
            date_debut = today - timedelta(days=today.weekday())
            date_fin = date_debut + timedelta(days=6)
    
    elif periode == 'mois':
        if mois:
            mois_num = int(mois)
            date_debut = date(annee, mois_num, 1)
            dernier_jour = calendar.monthrange(annee, mois_num)[1]
            date_fin = date(annee, mois_num, dernier_jour)
        else:
            # Mois en cours
            today = date.today()
            date_debut = date(today.year, today.month, 1)
            dernier_jour = calendar.monthrange(today.year, today.month)[1]
            date_fin = date(today.year, today.month, dernier_jour)
    
    elif periode == 'trimestre':
        if trimestre:
            trim_num = int(trimestre)
            mois_debut = (trim_num - 1) * 3 + 1
            date_debut = date(annee, mois_debut, 1)
            mois_fin = mois_debut + 2
            dernier_jour = calendar.monthrange(annee, mois_fin)[1]
            date_fin = date(annee, mois_fin, dernier_jour)
        else:
            # Trimestre en cours
            today = date.today()
            trim_actuel = (today.month - 1) // 3 + 1
            mois_debut = (trim_actuel - 1) * 3 + 1
            date_debut = date(today.year, mois_debut, 1)
            mois_fin = mois_debut + 2
            dernier_jour = calendar.monthrange(today.year, mois_fin)[1]
            date_fin = date(today.year, mois_fin, dernier_jour)
    
    elif periode == 'semestre':
        if semestre:
            sem_num = int(semestre)
            if sem_num == 1:
                date_debut = date(annee, 1, 1)
                date_fin = date(annee, 6, 30)
            else:
                date_debut = date(annee, 7, 1)
                date_fin = date(annee, 12, 31)
        else:
            # Semestre en cours
            today = date.today()
            if today.month <= 6:
                date_debut = date(today.year, 1, 1)
                date_fin = date(today.year, 6, 30)
            else:
                date_debut = date(today.year, 7, 1)
                date_fin = date(today.year, 12, 31)
    
    else:  # annuel
        date_debut = date(annee, 1, 1)
        date_fin = date(annee, 12, 31)
    
    return date_debut, date_fin


def get_periode_label(periode, annee, mois=None, trimestre=None, 
                      semestre=None, semaine=None):
    """Génère le label de la période pour l'affichage"""
    
    mois_noms = {
        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
        5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
        9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
    }
    
    if periode == 'semaine':
        if semaine:
            return f"Semaine {semaine} - {annee}"
        return "Semaine en cours"
    
    elif periode == 'mois':
        if mois:
            return f"{mois_noms[int(mois)]} {annee}"
        return "Mois en cours"
    
    elif periode == 'trimestre':
        if trimestre:
            return f"Trimestre {trimestre} - {annee}"
        return "Trimestre en cours"
    
    elif periode == 'semestre':
        if semestre:
            return f"Semestre {semestre} - {annee}"
        return "Semestre en cours"
    
    else:
        return f"Année {annee}"