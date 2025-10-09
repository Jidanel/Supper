# inventaire/views_classement.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required,user_passes_test
from django.db.models import Sum, Count, Avg, Q
from datetime import date, timedelta
import calendar
from decimal import Decimal
from accounts.models import *
from inventaire.models import *
from inventaire.services.classement_service import *
from inventaire.models_performance import *


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



def is_admin(user):
    """Vérification admin uniquement"""
    return user.is_authenticated and (
        user.is_superuser or
        (hasattr(user, 'is_admin') and user.is_admin())
    )


@login_required
@user_passes_test(is_admin)
def classement_postes_performances(request):
    """
    Vue principale : Classement des postes par performances
    RÉSERVÉ ADMIN UNIQUEMENT
    """
    # Récupérer filtres
    periode = request.GET.get('periode', 'mois')
    annee = int(request.GET.get('annee', date.today().year))
    mois = request.GET.get('mois')
    trimestre = request.GET.get('trimestre')
    semestre = request.GET.get('semestre')
    
    # Déterminer dates selon période
    if periode == 'mois':
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
    
    # Générer classement
    resultats = ClassementService.generer_classement_periode(date_debut, date_fin)
    
    # Préparer données pour template
    classement_postes = []
    
    for item in resultats['postes']:
        poste = item['poste']
        perf = item['performance']
        agents = item['agents']
        
        # Meilleur et pire agent
        meilleur_agent = agents[0] if agents else None
        pire_agent = agents[-1] if len(agents) > 1 else None
        
        classement_postes.append({
            'poste': poste,
            'performance': perf,  # Passer l'objet complet
            'taux_moyen': float(perf.taux_moyen_deperdition or 0),
            'taux_plus_bas': float(perf.taux_plus_bas or 0),
            'taux_plus_eleve': float(perf.taux_plus_eleve or 0),
            'evolution_stock': perf.evolution_stock_jours,
            'taux_evolution_recettes': float(perf.taux_evolution_recettes or 0),
            'nb_jours_impertinents': perf.nombre_jours_impertinents,
            'agents': agents,
            'meilleur_agent': meilleur_agent,
            'pire_agent': pire_agent
        })
    
    # Trier par taux moyen (meilleur = plus proche de 0 entre -5% et -30%)
    classement_postes.sort(key=lambda x: abs(x['taux_moyen'] + 17.5))
    
    # Ajouter rangs
    for i, item in enumerate(classement_postes, 1):
        item['rang'] = i
    
    context = {
        'periode': periode,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'annee': annee,
        'classement_postes': classement_postes,
        'annees_disponibles': range(2020, date.today().year + 2),
        'mois_liste': range(1, 13),
        'trimestres': [1, 2, 3, 4],
        'semestres': [1, 2],
        'title': 'Classement des Postes par Performance'
    }
    
    return render(request, 'inventaire/classement_postes_performances.html', context)


@login_required
@user_passes_test(is_admin)
def classement_agents_performances(request):
    """
    Vue : Classement global des agents d'inventaire
    RÉSERVÉ ADMIN UNIQUEMENT
    """
    # Récupérer filtres
    periode = request.GET.get('periode', 'mois')
    annee = int(request.GET.get('annee', date.today().year))
    mois = request.GET.get('mois')
    trimestre = request.GET.get('trimestre')
    semestre = request.GET.get('semestre')
    
    # Déterminer dates (même logique que ci-dessus)
    if periode == 'mois':
        if mois:
            mois_num = int(mois)
            date_debut = date(annee, mois_num, 1)
            dernier_jour = calendar.monthrange(annee, mois_num)[1]
            date_fin = date(annee, mois_num, dernier_jour)
        else:
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
    
    # Générer classement
    resultats = ClassementService.generer_classement_periode(date_debut, date_fin)
    
    # Préparer classement agents
    classement_agents = []
    
    for item in resultats['agents']:
        agent = item['agent']
        postes_data = item['postes']
        moyenne_globale = item['moyenne_globale']
        
        # Détails par poste
        details_postes = []
        total_jours_impertinents = 0
        
        for poste_item in postes_data:
            perf = poste_item['performance']
            total_jours_impertinents += perf.nombre_jours_impertinents
            
            details_postes.append({
                'poste': poste_item['poste'],
                'note_stock': float(perf.note_stock),
                'note_recettes': float(perf.note_recettes),
                'note_taux': float(perf.note_taux),
                'note_moyenne': float(perf.note_moyenne),
                'jours_impertinents': perf.nombre_jours_impertinents,
                'taux_avant': float(perf.taux_moyen_avant or 0),
                'taux_apres': float(perf.taux_moyen_apres or 0),
                'date_debut': perf.date_debut,
                'date_fin': perf.date_fin
            })
        
        classement_agents.append({
            'agent': agent,
            'moyenne_globale': moyenne_globale,
            'nombre_postes': len(postes_data),
            'details_postes': details_postes,
            'total_jours_impertinents': total_jours_impertinents
        })
    
    # Ajouter rangs
    for i, item in enumerate(classement_agents, 1):
        item['rang'] = i
    
    context = {
        'periode': periode,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'annee': annee,
        'classement_agents': classement_agents,
        'annees_disponibles': range(2020, date.today().year + 2),
        'mois_liste': range(1, 13),
        'trimestres': [1, 2, 3, 4],
        'semestres': [1, 2],
        'title': 'Classement des Agents d\'Inventaire'
    }
    
    return render(request, 'inventaire/classement_agents_performances.html', context)


@login_required
@user_passes_test(is_admin)
def detail_performance_poste(request, poste_id):
    """
    Vue détaillée de la performance d'un poste
    """
    from django.shortcuts import get_object_or_404
    
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Récupérer filtres
    periode = request.GET.get('periode', 'mois')
    annee = int(request.GET.get('annee', date.today().year))
    mois = request.GET.get('mois')
    
    # Déterminer dates
    if periode == 'mois' and mois:
        mois_num = int(mois)
        date_debut = date(annee, mois_num, 1)
        dernier_jour = calendar.monthrange(annee, mois_num)[1]
        date_fin = date(annee, mois_num, dernier_jour)
    else:
        today = date.today()
        date_debut = date(today.year, today.month, 1)
        dernier_jour = calendar.monthrange(today.year, today.month)[1]
        date_fin = date(today.year, today.month, dernier_jour)
    
    # Calculer performance
    perf = ClassementService.calculer_performance_poste(poste, date_debut, date_fin)
    
    if not perf:
        context = {
            'poste': poste,
            'error': 'Aucune donnée pour cette période'
        }
        return render(request, 'inventaire/detail_performance_poste.html', context)
    
    # Récupérer performances agents
    performances_agents = PerformanceAgent.objects.filter(
        poste=poste,
        date_debut__gte=date_debut,
        date_fin__lte=date_fin
    ).select_related('agent').order_by('-note_moyenne')
    
    agents_data = []
    for perf_agent in performances_agents:
        agents_data.append({
            'agent': perf_agent.agent,
            'note_stock': float(perf_agent.note_stock),
            'note_recettes': float(perf_agent.note_recettes),
            'note_taux': float(perf_agent.note_taux),
            'note_moyenne': float(perf_agent.note_moyenne),
            'taux_avant': float(perf_agent.taux_moyen_avant or 0),
            'taux_apres': float(perf_agent.taux_moyen_apres or 0),
            'jours_impertinents': perf_agent.nombre_jours_impertinents
        })
    
    context = {
        'poste': poste,
        'performance': perf,
        'agents': agents_data,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'title': f'Performance {poste.nom}'
    }
    
    return render(request, 'inventaire/detail_performance_poste.html', context)


@login_required
@user_passes_test(is_admin)
def detail_performance_agent(request, agent_id):
    """
    Vue détaillée de la performance d'un agent
    """
    from django.shortcuts import get_object_or_404
    
    agent = get_object_or_404(UtilisateurSUPPER, id=agent_id)
    
    # Récupérer filtres
    periode = request.GET.get('periode', 'mois')
    annee = int(request.GET.get('annee', date.today().year))
    mois = request.GET.get('mois')
    
    # Déterminer dates
    if periode == 'mois' and mois:
        mois_num = int(mois)
        date_debut = date(annee, mois_num, 1)
        dernier_jour = calendar.monthrange(annee, mois_num)[1]
        date_fin = date(annee, mois_num, dernier_jour)
    else:
        today = date.today()
        date_debut = date(today.year, today.month, 1)
        dernier_jour = calendar.monthrange(today.year, today.month)[1]
        date_fin = date(today.year, today.month, dernier_jour)
    
    # Récupérer toutes les performances de l'agent
    performances = PerformanceAgent.objects.filter(
        agent=agent,
        date_debut__gte=date_debut,
        date_fin__lte=date_fin
    ).select_related('poste').order_by('-note_moyenne')
    
    if not performances.exists():
        context = {
            'agent': agent,
            'error': 'Aucune donnée pour cette période'
        }
        return render(request, 'inventaire/detail_performance_agent.html', context)
    
    # Préparer données
    postes_data = []
    total_notes = []
    
    for perf in performances:
        total_notes.append(float(perf.note_moyenne))
        
        postes_data.append({
            'poste': perf.poste,
            'date_debut': perf.date_debut,
            'date_fin': perf.date_fin,
            'note_stock': float(perf.note_stock),
            'note_recettes': float(perf.note_recettes),
            'note_taux': float(perf.note_taux),
            'note_moyenne': float(perf.note_moyenne),
            'taux_avant': float(perf.taux_moyen_avant or 0),
            'taux_apres': float(perf.taux_moyen_apres or 0),
            'evolution_stock': (perf.date_stock_avant - perf.date_stock_apres).days if perf.date_stock_avant and perf.date_stock_apres else 0,
            'jours_impertinents': perf.nombre_jours_impertinents
        })
    
    moyenne_globale = sum(total_notes) / len(total_notes) if total_notes else 0
    
    context = {
        'agent': agent,
        'moyenne_globale': moyenne_globale,
        'nombre_postes': len(postes_data),
        'postes': postes_data,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'title': f'Performance {agent.nom_complet}'
    }
    
    return render(request, 'inventaire/detail_performance_agent.html', context)