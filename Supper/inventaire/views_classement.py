# ===================================================================
# inventaire/views_classement.py - Vues de classement SUPPER
# VERSION MISE À JOUR - Intégration des permissions granulaires
# ===================================================================
"""
Vues pour le classement des postes de péage par rendement et performances.
MISE À JOUR: Utilisation des permissions granulaires et filtrage par poste.

RÈGLES D'ACCÈS:
- Classement rendement: peut_voir_classement_peage_rendement
- Classement performances: peut_voir_classement_peage_deperdition  
- Classement agents: peut_voir_classement_agents_inventaire
- Filtrage automatique des postes selon l'habilitation de l'utilisateur
"""

from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Avg, Q
from datetime import date, timedelta
import calendar
from decimal import Decimal
import logging

from accounts.models import Poste, UtilisateurSUPPER
from inventaire.models import RecetteJournaliere
from inventaire.models_performance import PerformanceAgent

# Import des fonctions de permissions et décorateurs
from common.permissions import (
    has_permission,
    get_postes_accessibles,
    get_postes_peage_accessibles,
    check_poste_access,
    user_has_acces_tous_postes,
    is_admin_user,
    is_service_central,
    is_cisop_peage,
)
from common.decorators import (
    permission_required_granular,
    classement_peage_required,
)
from common.utils import log_user_action

logger = logging.getLogger('supper.classement')


# ===================================================================
# FONCTIONS UTILITAIRES
# ===================================================================

def calculer_dates_periode(periode, annee, mois=None, trimestre=None, 
                          semestre=None, semaine=None):
    """
    Calcule les dates de début et fin selon la période sélectionnée.
    
    Args:
        periode: Type de période ('cumul', 'semaine', 'mois', 'trimestre', 'semestre', 'annuel')
        annee: Année de référence
        mois: Numéro du mois (optionnel)
        trimestre: Numéro du trimestre (optionnel)
        semestre: Numéro du semestre (optionnel)
        semaine: Numéro de la semaine (optionnel)
    
    Returns:
        tuple: (date_debut, date_fin)
    """
    today = date.today()
    
    if periode == 'cumul':
        # Cumul à date = depuis le 1er janvier jusqu'à aujourd'hui
        date_debut = date(annee, 1, 1)
        date_fin = today
    
    elif periode == 'semaine':
        if semaine:
            # Semaine spécifique de l'année
            semaine_num = int(semaine)
            date_debut = date(annee, 1, 1) + timedelta(weeks=semaine_num-1)
            date_fin = date_debut + timedelta(days=6)
        else:
            # Semaine en cours
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
    """
    Génère le label de la période pour l'affichage.
    
    Returns:
        str: Label formaté de la période
    """
    mois_noms = {
        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
        5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
        9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
    }
    
    if periode == 'cumul':
        return f"Cumul à date - {annee}"
    
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


# ===================================================================
# VUE: CLASSEMENT DES POSTES PAR RENDEMENT
# ===================================================================

@login_required
@permission_required_granular('peut_voir_classement_peage_rendement')
def classement_postes_rendement(request):
    """
    Vue pour classer les postes par rendement selon différentes périodes.
    UNIQUEMENT basé sur montant_declare (recettes déclarées).
    
    PERMISSIONS REQUISES:
    - peut_voir_classement_peage_rendement
    
    ACCÈS AUX POSTES:
    - Admin/Services centraux/CISOP Péage: Tous les postes de péage
    - Chef de poste/Agent inventaire: Uniquement leur poste d'affectation
    """
    user = request.user
    
    # Log de l'action utilisateur
    log_user_action(
        user=user,
        action="Consultation classement rendement",
        details=f"Accès à la page de classement des postes par rendement",
        request=request
    )
    logger.info(f"[CLASSEMENT_RENDEMENT] Utilisateur {user.username} ({user.habilitation}) accède au classement rendement")
    
    # Récupérer les filtres
    periode = request.GET.get('periode', 'cumul')
    annee = int(request.GET.get('annee', date.today().year))
    mois = request.GET.get('mois')
    trimestre = request.GET.get('trimestre')
    semestre = request.GET.get('semestre')
    semaine = request.GET.get('semaine')
    
    # Déterminer les dates selon la période
    if periode == 'cumul':
        date_debut = date(annee, 1, 1)
        date_fin = date.today()
    else:
        date_debut, date_fin = calculer_dates_periode(
            periode, annee, mois, trimestre, semestre, semaine
        )
    
    # =====================================================
    # FILTRAGE DES POSTES SELON L'HABILITATION
    # =====================================================
    # Les utilisateurs multi-postes voient tous les postes de péage
    # Les utilisateurs mono-poste voient uniquement leur poste
    
    if user_has_acces_tous_postes(user):
        # Admin, services centraux, CISOP péage -> tous les postes de péage
        postes = Poste.objects.filter(is_active=True, type="peage")
        logger.debug(f"[CLASSEMENT_RENDEMENT] {user.username} a accès à tous les postes ({postes.count()} postes)")
    else:
        # Utilisateur mono-poste -> uniquement son poste d'affectation
        postes = get_postes_peage_accessibles(user)
        logger.debug(f"[CLASSEMENT_RENDEMENT] {user.username} accès limité à {postes.count()} poste(s)")
    
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
        top_3 = classement[:3]
        bottom_3 = classement[-3:] if len(classement) > 3 else []
    else:
        total_global = 0
        moyenne_globale = 0
        top_3 = []
        bottom_3 = []
    
    # Log du résultat
    logger.info(f"[CLASSEMENT_RENDEMENT] {user.username} - Période: {periode} - {len(classement)} postes affichés")
    
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
        'title': 'Classement des Postes par Rendement',
        # Indicateur d'accès complet pour le template
        'acces_tous_postes': user_has_acces_tous_postes(user),
    }
    
    return render(request, 'inventaire/classement_rendement.html', context)


# ===================================================================
# VUE: CLASSEMENT DES POSTES PAR PERFORMANCES
# ===================================================================

@login_required
@permission_required_granular('peut_voir_classement_peage_deperdition')
def classement_postes_performances(request):
    """
    Vue principale: Classement des postes par performances.
    Basé sur le taux de déperdition et autres indicateurs.
    
    PERMISSIONS REQUISES:
    - peut_voir_classement_peage_deperdition
    
    ACCÈS AUX POSTES:
    - Admin/Services centraux/CISOP Péage: Tous les postes
    - Autres: Postes accessibles selon habilitation
    """
    from inventaire.services.classement_service import ClassementService
    
    user = request.user
    
    # Log de l'action utilisateur
    log_user_action(
        user=user,
        action="Consultation classement performances",
        details=f"Accès à la page de classement des postes par performances",
        request=request
    )
    logger.info(f"[CLASSEMENT_PERF] Utilisateur {user.username} ({user.habilitation}) accède au classement performances")
    
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
    
    # =====================================================
    # FILTRAGE DES POSTES SELON L'HABILITATION
    # =====================================================
    
    postes_accessibles = get_postes_peage_accessibles(user)
    postes_accessibles_ids = set(postes_accessibles.values_list('id', flat=True))
    
    # Préparer données pour template
    classement_postes = []
    
    for item in resultats.get('postes', []):
        poste = item['poste']
        
        # Filtrer selon l'accès de l'utilisateur
        if not user_has_acces_tous_postes(user) and poste.id not in postes_accessibles_ids:
            continue
        
        perf = item['performance']
        agents = item['agents']
        
        # Meilleur et pire agent
        meilleur_agent = agents[0] if agents else None
        pire_agent = agents[-1] if len(agents) > 1 else None
        
        classement_postes.append({
            'poste': poste,
            'performance': perf,
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
    
    # Log du résultat
    logger.info(f"[CLASSEMENT_PERF] {user.username} - Période: {periode} - {len(classement_postes)} postes affichés")
    
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
        'title': 'Classement des Postes par Performance',
        'acces_tous_postes': user_has_acces_tous_postes(user),
    }
    
    return render(request, 'inventaire/classement_postes_performances.html', context)


# ===================================================================
# VUE: CLASSEMENT DES AGENTS D'INVENTAIRE
# ===================================================================
# ===================================================================
# inventaire/views_classement.py - VUE CLASSEMENT AGENTS MISE À JOUR
# Utilise le nouveau système de notation avancée
# CHEMIN: Supper/inventaire/views_classement.py
# ===================================================================
"""
Cette vue remplace l'ancienne fonction classement_agents_performances
pour utiliser le nouveau système de notation basé sur la cohérence.

PERMISSIONS REQUISES:
- peut_voir_classement_agents_inventaire

LOGS:
- Consultation du classement avec filtres
- Affichage du nombre d'agents classés
"""


logger = logging.getLogger('supper.classement')


@login_required
@permission_required_granular('peut_voir_classement_agents_inventaire')
def classement_agents_performances(request):
    """
    Vue: Classement global des agents d'inventaire avec le nouveau système de notation.
    
    NOUVEAU SYSTÈME DE NOTATION:
    - Basé sur la cohérence entre 3 critères (recettes, taux, date épuisement)
    - 3/3 critères cohérents: 15-18/20
    - 2/3 critères cohérents: 10-14/20
    - 0-1/3 critères: 6-9/20
    - Malus journées impertinentes: -3 à -4 points
    - Bonus régularité: jusqu'à +2 points
    
    PERMISSIONS REQUISES:
    - peut_voir_classement_agents_inventaire
    """
    user = request.user
    
    # Log de l'action utilisateur
    log_user_action(
        user=user,
        action="Consultation classement agents",
        details=f"Accès à la page de classement des agents d'inventaire | "
                f"Habilitation: {user.habilitation}",
        request=request
    )
    logger.info(
        f"[CLASSEMENT_AGENTS] Utilisateur {user.username} ({user.habilitation}) "
        f"accède au classement agents"
    )
    
    # Récupérer filtres
    periode = request.GET.get('periode', 'mois')
    annee = int(request.GET.get('annee', date.today().year))
    mois = request.GET.get('mois')
    trimestre = request.GET.get('trimestre')
    semestre = request.GET.get('semestre')
    
    # =====================================================
    # CALCUL DES DATES SELON LA PÉRIODE
    # =====================================================
    today = date.today()
    
    if periode == 'mois':
        if mois:
            mois_num = int(mois)
            date_debut = date(annee, mois_num, 1)
            dernier_jour = calendar.monthrange(annee, mois_num)[1]
            date_fin = date(annee, mois_num, dernier_jour)
        else:
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
            if today.month <= 6:
                date_debut = date(today.year, 1, 1)
                date_fin = date(today.year, 6, 30)
            else:
                date_debut = date(today.year, 7, 1)
                date_fin = date(today.year, 12, 31)
    
    else:  # annuel
        date_debut = date(annee, 1, 1)
        date_fin = date(annee, 12, 31)
    
    # Ne pas dépasser aujourd'hui
    if date_fin > today:
        date_fin = today
    
    # =====================================================
    # GÉNÉRATION DU CLASSEMENT AVEC LE NOUVEAU SERVICE
    # =====================================================
    
    try:
        from inventaire.services.classement_service import ClassementService
        
        # Déterminer les postes accessibles selon l'habilitation
        postes_accessibles = get_postes_peage_accessibles(user)
        postes_ids = list(postes_accessibles.values_list('id', flat=True)) if not user_has_acces_tous_postes(user) else None
        
        # Générer le classement
        resultats = ClassementService.generer_classement_periode(
            date_debut, 
            date_fin,
            postes_ids=postes_ids
        )
        
        logger.info(
            f"[CLASSEMENT_AGENTS] Classement généré avec {len(resultats.get('agents', []))} agents"
        )
        
    except ImportError as e:
        logger.error(f"[CLASSEMENT_AGENTS] Service de classement non disponible: {e}")
        messages.warning(
            request, 
            "Le nouveau service de notation n'est pas encore installé. "
            "Utilisation du classement simplifié."
        )
        resultats = _generer_classement_simplifie(user, date_debut, date_fin)
    
    except Exception as e:
        logger.error(f"[CLASSEMENT_AGENTS] Erreur génération classement: {e}")
        messages.error(request, f"Erreur lors de la génération du classement: {str(e)}")
        resultats = {'agents': [], 'statistiques': None}
    
    # =====================================================
    # PRÉPARATION DU CLASSEMENT POUR LE TEMPLATE
    # =====================================================
    
    classement_agents = []
    
    for item in resultats.get('agents', []):
        agent = item['agent']
        postes_data = item.get('postes', [])
        moyenne_globale = item.get('moyenne_globale', 0)
        perf_detaillee = item.get('performance_detaillee')
        
        # Détails par poste
        details_postes = []
        total_jours_impertinents = 0
        
        for poste_item in postes_data:
            poste_info = poste_item.get('poste', {})
            perf = poste_item.get('performance', {})
            
            total_jours_impertinents += perf.get('nombre_jours_impertinents', 0)
            
            details_postes.append({
                'poste': poste_info if isinstance(poste_info, dict) else {'nom': str(poste_info)},
                'note_stock': float(perf.get('note_stock', 0)),
                'note_recettes': float(perf.get('note_recettes', 0)),
                'note_taux': float(perf.get('note_taux', 0)),
                'note_moyenne': float(perf.get('note_moyenne', moyenne_globale)),
                'jours_impertinents': perf.get('nombre_jours_impertinents', 0),
                'taux_avant': float(perf.get('taux_moyen_avant', 0) or 0),
                'taux_apres': float(perf.get('taux_moyen_apres', 0) or 0),
                'date_debut': perf.get('date_debut', date_debut),
                'date_fin': perf.get('date_fin', date_fin)
            })
        
        # Ajouter les informations de cohérence si disponibles
        jours_3_criteres = 0
        jours_2_criteres = 0
        jours_1_critere = 0
        jours_0_critere = 0
        
        if perf_detaillee:
            jours_3_criteres = perf_detaillee.jours_3_criteres
            jours_2_criteres = perf_detaillee.jours_2_criteres
            jours_1_critere = perf_detaillee.jours_1_critere
            jours_0_critere = perf_detaillee.jours_0_critere
            total_jours_impertinents = perf_detaillee.jours_impertinents
        
        classement_agents.append({
            'agent': agent,
            'moyenne_globale': moyenne_globale,
            'nombre_postes': len(postes_data),
            'details_postes': details_postes,
            'total_jours_impertinents': total_jours_impertinents,
            'jours_3_criteres': jours_3_criteres,
            'jours_2_criteres': jours_2_criteres,
            'jours_1_critere': jours_1_critere,
            'jours_0_critere': jours_0_critere,
            'performance_detaillee': perf_detaillee
        })
    
    # Ajouter rangs
    for i, item in enumerate(classement_agents, 1):
        item['rang'] = i
    
    # Log du résultat
    log_user_action(
        user=user,
        action="Classement agents généré",
        details=f"Période: {periode} | Du {date_debut} au {date_fin} | "
                f"{len(classement_agents)} agents affichés",
        request=request
    )
    logger.info(
        f"[CLASSEMENT_AGENTS] {user.username} - Période: {periode} - "
        f"{len(classement_agents)} agents affichés"
    )
    
    # Contexte pour le template
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
        'title': 'Classement des Agents d\'Inventaire',
        'acces_tous_postes': user_has_acces_tous_postes(user),
        'statistiques': resultats.get('statistiques'),
    }
    
    return render(request, 'inventaire/classement_agents_performances.html', context)


def _generer_classement_simplifie(user, date_debut, date_fin):
    """
    Génère un classement simplifié basé sur les données réelles des inventaires.
    Utilisé comme fallback si le service ClassementService n'est pas disponible.
    
    Args:
        user: Utilisateur effectuant la requête
        date_debut: Date de début de la période
        date_fin: Date de fin de la période
        
    Returns:
        dict: {'agents': [...], 'statistiques': {...}}
    """
    from inventaire.models import InventaireJournalier, RecetteJournaliere
    from accounts.models import UtilisateurSUPPER, Poste
    
    logger.info(f"[CLASSEMENT_SIMPLIFIE] Génération classement du {date_debut} au {date_fin}")
    
    # Récupérer tous les agents d'inventaire avec leurs statistiques
    agents_stats = InventaireJournalier.objects.filter(
        date__range=[date_debut, date_fin],
        agent_saisie__habilitation='agent_inventaire',
        type_inventaire='normal'
    ).values(
        'agent_saisie',
        'agent_saisie__nom_complet',
        'agent_saisie__username'
    ).annotate(
        nb_inventaires=Count('id'),
        nb_postes=Count('poste', distinct=True),
        total_vehicules=Sum('total_vehicules')
    ).order_by('-nb_inventaires')
    
    agents_list = []
    total_jours_3_criteres = 0
    total_jours_impertinents = 0
    somme_notes = 0
    
    for stats in agents_stats:
        try:
            agent = UtilisateurSUPPER.objects.get(id=stats['agent_saisie'])
            
            # Calculer les métriques détaillées pour cet agent
            perf_agent = _calculer_performance_agent_detaillee(
                agent, date_debut, date_fin
            )
            
            agents_list.append({
                'agent': agent,
                'postes': perf_agent.get('postes', []),
                'moyenne_globale': perf_agent.get('note_moyenne', 0),
                'performance_detaillee': perf_agent
            })
            
            somme_notes += perf_agent.get('note_moyenne', 0)
            total_jours_3_criteres += perf_agent.get('jours_3_criteres', 0)
            total_jours_impertinents += perf_agent.get('jours_impertinents', 0)
            
        except UtilisateurSUPPER.DoesNotExist:
            logger.warning(f"[CLASSEMENT_SIMPLIFIE] Agent introuvable ID: {stats['agent_saisie']}")
            continue
    
    # Trier par note moyenne décroissante
    agents_list.sort(key=lambda x: x['moyenne_globale'], reverse=True)
    
    # Statistiques globales
    statistiques = {
        'jours_3_criteres': total_jours_3_criteres,
        'total_jours_impertinents': total_jours_impertinents,
        'moyenne_globale': somme_notes / len(agents_list) if agents_list else 0,
        'nombre_agents': len(agents_list)
    }
    
    logger.info(f"[CLASSEMENT_SIMPLIFIE] {len(agents_list)} agents classés")
    
    return {'agents': agents_list, 'statistiques': statistiques}



def _calculer_performance_agent_detaillee(agent, date_debut, date_fin):
    """
    Calcule la performance détaillée d'un agent sur une période.
    
    Critères de notation:
    - Cohérence recettes déclarées vs inventaire
    - Taux de déperdition
    - Régularité des saisies
    
    Args:
        agent: Instance UtilisateurSUPPER
        date_debut: Date de début
        date_fin: Date de fin
        
    Returns:
        dict: Performance détaillée avec notes et statistiques
    """
    from inventaire.models import InventaireJournalier, RecetteJournaliere
    from accounts.models import Poste
    
    logger.debug(f"[PERF_AGENT] Calcul performance pour {agent.nom_complet}")
    
    # Récupérer les inventaires de l'agent sur la période
    inventaires = InventaireJournalier.objects.filter(
        agent_saisie=agent,
        date__range=[date_debut, date_fin],
        type_inventaire='normal'
    ).select_related('poste')
    
    if not inventaires.exists():
        return {
            'note_moyenne': 0,
            'jours_travailles': 0,
            'jours_3_criteres': 0,
            'jours_2_criteres': 0,
            'jours_1_critere': 0,
            'jours_0_critere': 0,
            'jours_impertinents': 0,
            'postes': []
        }
    
    # Statistiques de base
    jours_travailles = inventaires.count()
    postes_uniques = inventaires.values_list('poste', flat=True).distinct()
    
    # Compteurs de cohérence
    jours_3_criteres = 0
    jours_2_criteres = 0
    jours_1_critere = 0
    jours_0_critere = 0
    jours_impertinents = 0
    
    # Calcul par inventaire
    notes_journalieres = []
    
    for inv in inventaires:
        # Récupérer la recette associée
        try:
            recette = RecetteJournaliere.objects.get(
                poste=inv.poste,
                date=inv.date
            )
            has_recette = True
            taux_dep = recette.taux_deperdition if recette.taux_deperdition else 0
        except RecetteJournaliere.DoesNotExist:
            has_recette = False
            taux_dep = 0
            recette = None
        
        # Évaluer les 3 critères de cohérence
        criteres_ok = 0
        
        # Critère 1: Inventaire rempli avec données cohérentes
        if inv.total_vehicules and inv.total_vehicules > 0:
            criteres_ok += 1
        
        # Critère 2: Recette déclarée présente
        if has_recette and recette and recette.montant_declare:
            if recette.montant_declare > 0:
                criteres_ok += 1
        
        # Critère 3: Taux de déperdition dans la normale (< -5% est suspect)
        if has_recette and taux_dep is not None:
            if taux_dep <= -5:  # Taux normal (négatif = déperdition)
                criteres_ok += 1
        
        # Compter les critères
        if criteres_ok >= 3:
            jours_3_criteres += 1
            note_jour = 16 + (criteres_ok - 3) * 0.5  # 16-18
        elif criteres_ok == 2:
            jours_2_criteres += 1
            note_jour = 12  # 10-14
        elif criteres_ok == 1:
            jours_1_critere += 1
            note_jour = 8  # 6-9
        else:
            jours_0_critere += 1
            note_jour = 6
        
        # Vérifier jour impertinent (taux > -5%)
        if has_recette and taux_dep is not None and taux_dep > -5:
            jours_impertinents += 1
            note_jour -= 3  # Malus
        
        notes_journalieres.append(note_jour)
    
    # Calculer la note moyenne
    note_moyenne = sum(notes_journalieres) / len(notes_journalieres) if notes_journalieres else 0
    
    # Bonus régularité (présence > 80%)
    jours_possibles = (date_fin - date_debut).days + 1
    taux_presence = (jours_travailles / jours_possibles * 100) if jours_possibles > 0 else 0
    
    if taux_presence >= 80:
        note_moyenne += 2  # Bonus max
    elif taux_presence >= 60:
        note_moyenne += 1
    
    # Plafonner à 20
    note_moyenne = min(20, max(0, note_moyenne))
    
    # Performance par poste
    postes_performance = []
    for poste_id in postes_uniques:
        try:
            poste = Poste.objects.get(id=poste_id)
            inv_poste = inventaires.filter(poste_id=poste_id)
            
            # Calculer stats pour ce poste
            recettes_poste = RecetteJournaliere.objects.filter(
                poste_id=poste_id,
                date__range=[date_debut, date_fin],
                inventaire_associe__agent_saisie=agent
            )
            
            taux_moyen = recettes_poste.aggregate(
                avg=Avg('taux_deperdition')
            )['avg'] or 0
            
            jours_imp_poste = recettes_poste.filter(
                taux_deperdition__gt=-5
            ).count()
            
            postes_performance.append({
                'poste': {'id': poste.id, 'nom': poste.nom, 'code': poste.code},
                'note_stock': min(20, max(0, 15 - abs(taux_moyen or 0) / 5)),
                'note_recettes': min(20, max(0, 14 if recettes_poste.exists() else 8)),
                'note_taux': min(20, max(0, 16 - jours_imp_poste * 2)),
                'note_moyenne': note_moyenne,
                'jours_impertinents': jours_imp_poste,
                'jours_travailles': inv_poste.count(),
                'taux_moyen_avant': taux_moyen,
                'taux_moyen_apres': taux_moyen
            })
        except Poste.DoesNotExist:
            continue
    
    return {
        'note_moyenne': round(note_moyenne, 1),
        'jours_travailles': jours_travailles,
        'jours_3_criteres': jours_3_criteres,
        'jours_2_criteres': jours_2_criteres,
        'jours_1_critere': jours_1_critere,
        'jours_0_critere': jours_0_critere,
        'jours_impertinents': jours_impertinents,
        'taux_presence': round(taux_presence, 1),
        'postes': postes_performance
    }


def _get_performance_simplifiee(agent, date_debut, date_fin):
    """
    Récupère la performance simplifiée d'un agent.
    Wrapper pour _calculer_performance_agent_detaillee.
    
    Args:
        agent: Instance UtilisateurSUPPER
        date_debut: Date de début
        date_fin: Date de fin
        
    Returns:
        dict: {'note': float, 'rang': int, 'total_agents': int}
    """
    perf = _calculer_performance_agent_detaillee(agent, date_debut, date_fin)
    
    # Calculer le rang parmi tous les agents
    from inventaire.models import InventaireJournalier
    from accounts.models import UtilisateurSUPPER
    
    # Récupérer tous les agents actifs
    agents_avec_inventaires = InventaireJournalier.objects.filter(
        date__range=[date_debut, date_fin],
        agent_saisie__habilitation='agent_inventaire',
        type_inventaire='normal'
    ).values_list('agent_saisie', flat=True).distinct()
    
    total_agents = len(set(agents_avec_inventaires))
    
    # Compter combien d'agents ont une meilleure note
    agents_devant = 0
    for agent_id in set(agents_avec_inventaires):
        if agent_id != agent.id:
            try:
                autre_agent = UtilisateurSUPPER.objects.get(id=agent_id)
                autre_perf = _calculer_performance_agent_detaillee(
                    autre_agent, date_debut, date_fin
                )
                if autre_perf.get('note_moyenne', 0) > perf.get('note_moyenne', 0):
                    agents_devant += 1
            except:
                continue
    
    return {
        'note': perf.get('note_moyenne', 0),
        'rang': agents_devant + 1 if perf.get('jours_travailles', 0) > 0 else None,
        'total_agents': total_agents
    }


# ===================================================================
# FONCTION UTILITAIRE POUR OBTENIR LE RANG D'UN AGENT
# ===================================================================

# def get_rang_agent_periode(agent, date_debut, date_fin):
#     """
#     Obtient le rang d'un agent spécifique sur une période.
    
#     Args:
#         agent: Instance UtilisateurSUPPER
#         date_debut: Date de début
#         date_fin: Date de fin
        
#     Returns:
#         Dict avec rang, total_agents, note
#     """
#     try:
#         from inventaire.services.classement_service import ClassementService
#         return ClassementService.obtenir_rang_agent(agent, date_debut, date_fin)
#     except ImportError:
#         # Fallback simplifié
#         return _get_rang_simplifie(agent, date_debut, date_fin)


def get_rang_agent_periode(agent, date_debut, date_fin):
    """
    Obtient le rang d'un agent spécifique sur une période.
    
    Args:
        agent: Instance UtilisateurSUPPER
        date_debut: Date de début
        date_fin: Date de fin
        
    Returns:
        Dict avec rang, total_agents, note
    """
    return _get_performance_simplifiee(agent, date_debut, date_fin)


def _get_rang_simplifie(agent, date_debut, date_fin):
    """Calcul simplifié du rang si le service complet n'est pas disponible."""
    from inventaire.models import InventaireJournalier
    
    # Compter les inventaires de l'agent
    inventaires_agent = InventaireJournalier.objects.filter(
        agent_saisie=agent,
        date__range=[date_debut, date_fin]
    ).count()
    
    if inventaires_agent == 0:
        return {'rang': None, 'total_agents': 0, 'note': 0}
    
    # Compter tous les agents avec plus d'inventaires
    agents_devant = InventaireJournalier.objects.filter(
        date__range=[date_debut, date_fin],
        agent_saisie__habilitation='agent_inventaire'
    ).values('agent_saisie').annotate(
        nb=Count('id')
    ).filter(nb__gt=inventaires_agent).count()
    
    total_agents = InventaireJournalier.objects.filter(
        date__range=[date_debut, date_fin],
        agent_saisie__habilitation='agent_inventaire'
    ).values('agent_saisie').distinct().count()
    
    # Note approximative
    jours_possibles = (date_fin - date_debut).days + 1
    taux = (inventaires_agent / jours_possibles * 100) if jours_possibles > 0 else 0
    note = min(20, 8 + taux / 10)
    
    return {
        'rang': agents_devant + 1,
        'total_agents': total_agents,
        'note': note,
        'jours_travailles': inventaires_agent,
        'taux_presence': taux
    }


# ===================================================================
# VUE: DÉTAIL PERFORMANCE D'UN POSTE
# ===================================================================

@login_required
@permission_required_granular(['peut_voir_classement_peage_deperdition', 'peut_voir_stats_deperdition'])
def detail_performance_poste(request, poste_id):
    """
    Vue détaillée de la performance d'un poste.
    
    PERMISSIONS REQUISES:
    - peut_voir_classement_peage_deperdition OU peut_voir_stats_deperdition
    
    ACCÈS AU POSTE:
    - Vérifié via check_poste_access
    """
    from inventaire.services.classement_service import ClassementService
    
    user = request.user
    poste = get_object_or_404(Poste, id=poste_id)
    
    # =====================================================
    # VÉRIFICATION D'ACCÈS AU POSTE
    # =====================================================
    if not check_poste_access(user, poste):
        log_user_action(
            user=user,
            action="Accès refusé - Détail performance poste",
            details=f"Tentative d'accès au poste {poste.nom} (ID: {poste_id}) - Accès non autorisé",
            request=request,
            succes=False
        )
        logger.warning(f"[DETAIL_POSTE] Accès refusé pour {user.username} au poste {poste.nom}")
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        return redirect('inventaire:classement_rendement')
    
    # Log de l'action
    log_user_action(
        user=user,
        action="Consultation détail performance poste",
        details=f"Consultation de la performance du poste {poste.nom} (ID: {poste_id})",
        request=request
    )
    logger.info(f"[DETAIL_POSTE] {user.username} consulte la performance du poste {poste.nom}")
    
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


# ===================================================================
# VUE: DÉTAIL PERFORMANCE D'UN AGENT
# ===================================================================
# ===================================================================
# VUE: DÉTAIL PERFORMANCE AGENT - MISE À JOUR
# ===================================================================
# CHEMIN: Supper/inventaire/views_detail_performance.py
# ===================================================================
"""
Vue détaillée de la performance d'un agent d'inventaire.
Intègre le nouveau système de notation basé sur la cohérence des 3 critères:
- Recettes déclarées
- Taux de déperdition
- Date d'épuisement du stock

PERMISSIONS REQUISES:
- peut_voir_classement_agents_inventaire

LOGS:
- Consultation du profil agent
- Accès refusé si non autorisé
"""

import logging
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Avg, Count, Q, F

from accounts.models import UtilisateurSUPPER, Poste
from inventaire.models import (
    InventaireJournalier, 
    RecetteJournaliere, 
    PerformanceAgent,
    ConfigurationJour,
    StatutJour
)
from common.decorators import permission_required_granular
from common.permissions import (
    user_has_acces_tous_postes,
    get_postes_peage_accessibles,
    check_poste_access
)
from common.utils import log_user_action

logger = logging.getLogger('supper.classement')


@login_required
@permission_required_granular('peut_voir_classement_agents_inventaire')
def detail_performance_agent(request, agent_id):
    """
    Vue détaillée de la performance d'un agent avec le nouveau système de notation.
    
    NOUVEAU SYSTÈME DE NOTATION:
    - Basé sur la cohérence entre 3 critères (recettes, taux, date épuisement)
    - 3/3 critères cohérents: 15-18/20
    - 2/3 critères cohérents: 10-14/20
    - 0-1/3 critères: 6-9/20
    - Malus journées impertinentes: -3 à -4 points
    - Bonus régularité: jusqu'à +2 points
    
    PERMISSIONS REQUISES:
    - peut_voir_classement_agents_inventaire
    
    ACCÈS:
    - Admin/Services centraux: Tous les agents
    - Chef de poste: Agents de son poste uniquement
    - Agent: Son propre profil uniquement
    """
    user = request.user
    agent = get_object_or_404(UtilisateurSUPPER, id=agent_id)
    
    # =====================================================
    # VÉRIFICATION D'ACCÈS À L'AGENT
    # =====================================================
    
    if agent.id != user.id and not user_has_acces_tous_postes(user):
        # Vérifier si l'utilisateur a accès au poste de l'agent
        if agent.poste_affectation and not check_poste_access(user, agent.poste_affectation):
            log_user_action(
                user=user,
                action="Accès refusé - Détail performance agent",
                details=f"Tentative d'accès au profil de l'agent {agent.nom_complet} (ID: {agent_id}) - "
                        f"Accès non autorisé | Habilitation: {user.habilitation}",
                request=request,
                succes=False
            )
            logger.warning(
                f"[DETAIL_AGENT] Accès refusé pour {user.username} ({user.habilitation}) "
                f"à l'agent {agent.nom_complet}"
            )
            messages.error(request, "Vous n'avez pas accès à ce profil.")
            return redirect('inventaire:classement_agents_performances')
    
    # Log de l'action
    log_user_action(
        user=user,
        action="Consultation détail performance agent",
        details=f"Agent: {agent.nom_complet} (ID: {agent_id}) | "
                f"Consulté par: {user.nom_complet} ({user.habilitation})",
        request=request
    )
    logger.info(
        f"[DETAIL_AGENT] {user.username} ({user.habilitation}) "
        f"consulte la performance de l'agent {agent.nom_complet}"
    )
    
    # =====================================================
    # RÉCUPÉRATION DES FILTRES DE PÉRIODE
    # =====================================================
    
    periode = request.GET.get('periode', 'mois')
    annee = int(request.GET.get('annee', date.today().year))
    mois = request.GET.get('mois')
    trimestre = request.GET.get('trimestre')
    semestre = request.GET.get('semestre')
    
    # Paramètres de date personnalisés (depuis le classement)
    date_debut_param = request.GET.get('date_debut')
    date_fin_param = request.GET.get('date_fin')
    
    today = date.today()
    
    # Utiliser les dates personnalisées si fournies
    if date_debut_param and date_fin_param:
        try:
            from datetime import datetime
            date_debut = datetime.strptime(date_debut_param, '%Y-%m-%d').date()
            date_fin = datetime.strptime(date_fin_param, '%Y-%m-%d').date()
        except ValueError:
            date_debut = date(today.year, today.month, 1)
            date_fin = today
    
    elif periode == 'mois':
        if mois:
            mois_num = int(mois)
            date_debut = date(annee, mois_num, 1)
            dernier_jour = calendar.monthrange(annee, mois_num)[1]
            date_fin = date(annee, mois_num, dernier_jour)
        else:
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
            if today.month <= 6:
                date_debut = date(today.year, 1, 1)
                date_fin = date(today.year, 6, 30)
            else:
                date_debut = date(today.year, 7, 1)
                date_fin = date(today.year, 12, 31)
    
    else:  # annuel
        date_debut = date(annee, 1, 1)
        date_fin = date(annee, 12, 31)
    
    # Ne pas dépasser aujourd'hui
    if date_fin > today:
        date_fin = today
    
    # =====================================================
    # RÉCUPÉRATION DES PERFORMANCES AVEC NOUVEAU SYSTÈME
    # =====================================================
    
    try:
        from inventaire.services.classement_service import ClassementService
        
        # Obtenir la performance détaillée de l'agent
        performance_detaillee = ClassementService.obtenir_rang_agent(
            agent, date_debut, date_fin
        )
        
        # Récupérer les performances par poste
        postes_data = _get_performances_par_poste_detaillees(
            agent, date_debut, date_fin, user
        )
        
        # Statistiques de cohérence
        coherence_stats = _calculer_stats_coherence(agent, date_debut, date_fin)
        
        logger.info(
            f"[DETAIL_AGENT] Performance récupérée pour {agent.nom_complet}: "
            f"Note={performance_detaillee.get('note', 0):.2f}/20"
        )
        
    except ImportError as e:
        logger.warning(f"[DETAIL_AGENT] Service de notation non disponible: {e}")
        performance_detaillee = _get_performance_simplifiee(agent, date_debut, date_fin)
        postes_data = _get_performances_par_poste_simplifiees(agent, date_debut, date_fin, user)
        coherence_stats = None
    
    except Exception as e:
        logger.error(f"[DETAIL_AGENT] Erreur récupération performance: {e}")
        messages.warning(request, f"Certaines données n'ont pas pu être chargées: {str(e)}")
        performance_detaillee = {'note': 0, 'rang': None, 'total_agents': 0}
        postes_data = []
        coherence_stats = None
    
    # =====================================================
    # VÉRIFICATION DES DONNÉES
    # =====================================================
    
    if not postes_data and performance_detaillee.get('note', 0) == 0:
        context = {
            'agent': agent,
            'date_debut': date_debut,
            'date_fin': date_fin,
            'periode': periode,
            'annee': annee,
            'error': "Aucune donnée de performance disponible pour cet agent sur la période sélectionnée.",
            'title': f'Performance {agent.nom_complet}'
        }
        return render(request, 'inventaire/detail_performance_agent.html', context)
    
    # =====================================================
    # CALCUL DES STATISTIQUES GLOBALES
    # =====================================================
    
    # Moyenne globale
    if postes_data:
        total_notes = [float(p.get('note_moyenne', 0)) for p in postes_data]
        moyenne_globale = sum(total_notes) / len(total_notes) if total_notes else 0
        meilleure_note = max(total_notes) if total_notes else 0
        pire_note = min(total_notes) if total_notes else 0
    else:
        moyenne_globale = performance_detaillee.get('note', 0)
        meilleure_note = moyenne_globale
        pire_note = moyenne_globale
    
    # Totaux de cohérence
    if coherence_stats:
        total_jours_3_criteres = coherence_stats.get('jours_3_criteres', 0)
        total_jours_2_criteres = coherence_stats.get('jours_2_criteres', 0)
        total_jours_1_critere = coherence_stats.get('jours_1_critere', 0)
        total_jours_0_critere = coherence_stats.get('jours_0_critere', 0)
        total_jours_impertinents = coherence_stats.get('jours_impertinents', 0)
        total_jours_travailles = coherence_stats.get('jours_travailles', 0)
        taux_presence = coherence_stats.get('taux_presence', 0)
    else:
        # Calculer depuis les postes_data
        total_jours_3_criteres = sum(p.get('jours_3_criteres', 0) for p in postes_data)
        total_jours_2_criteres = sum(p.get('jours_2_criteres', 0) for p in postes_data)
        total_jours_1_critere = sum(p.get('jours_1_critere', 0) for p in postes_data)
        total_jours_0_critere = sum(p.get('jours_0_critere', 0) for p in postes_data)
        total_jours_impertinents = sum(p.get('jours_impertinents', 0) for p in postes_data)
        total_jours_travailles = sum(p.get('jours_travailles', 0) for p in postes_data)
        
        jours_possibles = (date_fin - date_debut).days + 1
        taux_presence = (total_jours_travailles / jours_possibles * 100) if jours_possibles > 0 else 0
    
    # Pourcentages de cohérence
    total_jours_coherence = (
        total_jours_3_criteres + total_jours_2_criteres + 
        total_jours_1_critere + total_jours_0_critere
    )
    
    if total_jours_coherence > 0:
        pct_3_criteres = total_jours_3_criteres / total_jours_coherence * 100
        pct_2_criteres = total_jours_2_criteres / total_jours_coherence * 100
        pct_faible = (total_jours_1_critere + total_jours_0_critere) / total_jours_coherence * 100
    else:
        pct_3_criteres = pct_2_criteres = pct_faible = 0
    
    # =====================================================
    # ÉVOLUTION ET TENDANCE
    # =====================================================
    
    evolution_data = _calculer_evolution_agent(agent, date_debut, date_fin)
    
    # =====================================================
    # RECOMMANDATIONS PERSONNALISÉES
    # =====================================================
    
    recommandations = _generer_recommandations(
        moyenne_globale=moyenne_globale,
        pct_3_criteres=pct_3_criteres,
        total_jours_impertinents=total_jours_impertinents,
        postes_data=postes_data
    )
    
    # =====================================================
    # LOG FINAL ET CONTEXTE
    # =====================================================
    
    log_user_action(
        user=user,
        action="Détail performance agent consulté",
        details=f"Agent: {agent.nom_complet} | Période: {date_debut} - {date_fin} | "
                f"Note: {moyenne_globale:.2f}/20 | Rang: {performance_detaillee.get('rang', '-')}/{performance_detaillee.get('total_agents', '-')}",
        request=request
    )
    
    context = {
        # Agent
        'agent': agent,
        'title': f'Performance {agent.nom_complet}',
        
        # Période
        'date_debut': date_debut,
        'date_fin': date_fin,
        'periode': periode,
        'annee': annee,
        
        # Notes et classement
        'moyenne_globale': moyenne_globale,
        'meilleure_note': meilleure_note,
        'pire_note': pire_note,
        'rang': performance_detaillee.get('rang'),
        'total_agents': performance_detaillee.get('total_agents', 0),
        
        # Cohérence
        'total_jours_3_criteres': total_jours_3_criteres,
        'total_jours_2_criteres': total_jours_2_criteres,
        'total_jours_1_critere': total_jours_1_critere,
        'total_jours_0_critere': total_jours_0_critere,
        'pct_3_criteres': pct_3_criteres,
        'pct_2_criteres': pct_2_criteres,
        'pct_faible': pct_faible,
        
        # Présence et impertinents
        'total_jours_travailles': total_jours_travailles,
        'total_jours_impertinents': total_jours_impertinents,
        'taux_presence': taux_presence,
        
        # Postes
        'postes': postes_data,
        'nombre_postes': len(postes_data),
        
        # Évolution
        'evolution_data': evolution_data,
        
        # Recommandations
        'recommandations': recommandations,
        
        # Filtres disponibles
        'annees_disponibles': range(2020, date.today().year + 2),
        'mois_liste': range(1, 13),
        'trimestres': [1, 2, 3, 4],
        'semestres': [1, 2],
    }
    
    return render(request, 'inventaire/detail_performance_agent.html', context)


# =====================================================
# FONCTIONS UTILITAIRES
# =====================================================

# def _get_performances_par_poste_detaillees(agent, date_debut, date_fin, user):
#     """
#     Récupère les performances détaillées par poste avec le nouveau système.
#     """
#     try:
#         from .services import notation_agent_service
#         notation_service = notation_agent_service.get_notation_service()
        
#         # Récupérer les postes où l'agent a travaillé
#         postes_ids = InventaireJournalier.objects.filter(
#             agent_saisie=agent,
#             date__range=[date_debut, date_fin]
#         ).values_list('poste_id', flat=True).distinct()
        
#         postes = Poste.objects.filter(id__in=postes_ids)
        
#         # Filtrer selon l'accès de l'utilisateur
#         if not user_has_acces_tous_postes(user):
#             postes_accessibles = get_postes_peage_accessibles(user)
#             postes = postes.filter(id__in=postes_accessibles)
        
#         postes_data = []
        
#         for poste in postes:
#             # Calculer la performance pour ce poste
#             perf = notation_service.calculer_performance_agent_periode(
#                 agent, date_debut, date_fin, poste=poste
#             )
            
#             if perf:
#                 postes_data.append({
#                     'poste': poste,
#                     'date_debut': perf.date_debut,
#                     'date_fin': perf.date_fin,
#                     'note_moyenne': perf.note_finale,
#                     'note_stock': perf.note_finale * 0.3,  # Approximation si non disponible
#                     'note_recettes': perf.note_finale * 0.35,
#                     'note_taux': perf.note_finale * 0.35,
#                     'jours_3_criteres': perf.jours_3_criteres,
#                     'jours_2_criteres': perf.jours_2_criteres,
#                     'jours_1_critere': perf.jours_1_critere,
#                     'jours_0_critere': perf.jours_0_critere,
#                     'jours_impertinents': perf.jours_impertinents,
#                     'jours_travailles': perf.jours_travailles,
#                     'taux_avant': perf.taux_moyen_avant,
#                     'taux_apres': perf.taux_moyen_apres,
#                     'evolution_taux': _calculer_evolution_taux(perf.taux_moyen_avant, perf.taux_moyen_apres),
#                 })
        
#         # Trier par note décroissante
#         postes_data.sort(key=lambda x: x['note_moyenne'], reverse=True)
        
#         return postes_data
        
#     except Exception as e:
#         logger.error(f"[DETAIL_AGENT] Erreur récupération performances par poste: {e}")
#         return _get_performances_par_poste_simplifiees(agent, date_debut, date_fin, user)

def _get_performances_par_poste_detaillees(agent, date_debut, date_fin, user):
    """
    Récupère les performances détaillées par poste pour un agent.
    
    Args:
        agent: Agent dont on veut les performances
        date_debut: Date de début
        date_fin: Date de fin
        user: Utilisateur effectuant la requête (pour filtrage)
        
    Returns:
        list: Liste des performances par poste
    """
    perf = _calculer_performance_agent_detaillee(agent, date_debut, date_fin)
    return perf.get('postes', [])

# def _get_performances_par_poste_simplifiees(agent, date_debut, date_fin, user):
#     """
#     Version simplifiée si le service de notation n'est pas disponible.
#     """
#     # Récupérer les performances existantes depuis la base
#     performances = PerformanceAgent.objects.filter(
#         agent=agent,
#         date_debut__gte=date_debut,
#         date_fin__lte=date_fin
#     ).select_related('poste').order_by('-note_moyenne')
    
#     # Filtrer selon l'accès de l'utilisateur
#     if not user_has_acces_tous_postes(user):
#         postes_accessibles = get_postes_peage_accessibles(user)
#         postes_accessibles_ids = set(postes_accessibles.values_list('id', flat=True))
#         performances = [p for p in performances if p.poste_id in postes_accessibles_ids]
    
#     postes_data = []
    
#     for perf in performances:
#         postes_data.append({
#             'poste': perf.poste,
#             'date_debut': perf.date_debut,
#             'date_fin': perf.date_fin,
#             'note_moyenne': float(perf.note_moyenne),
#             'note_stock': float(perf.note_stock) if hasattr(perf, 'note_stock') else 0,
#             'note_recettes': float(perf.note_recettes) if hasattr(perf, 'note_recettes') else 0,
#             'note_taux': float(perf.note_taux) if hasattr(perf, 'note_taux') else 0,
#             'jours_3_criteres': 0,
#             'jours_2_criteres': 0,
#             'jours_1_critere': 0,
#             'jours_0_critere': 0,
#             'jours_impertinents': perf.nombre_jours_impertinents if hasattr(perf, 'nombre_jours_impertinents') else 0,
#             'jours_travailles': 0,
#             'taux_avant': float(perf.taux_moyen_avant or 0) if hasattr(perf, 'taux_moyen_avant') else 0,
#             'taux_apres': float(perf.taux_moyen_apres or 0) if hasattr(perf, 'taux_moyen_apres') else 0,
#             'evolution_taux': _calculer_evolution_taux(
#                 getattr(perf, 'taux_moyen_avant', None),
#                 getattr(perf, 'taux_moyen_apres', None)
#             ),
#         })
    
#     return postes_data

def _get_performances_par_poste_simplifiees(agent, date_debut, date_fin, user):
    """
    Alias pour _get_performances_par_poste_detaillees (compatibilité).
    """
    return _get_performances_par_poste_detaillees(agent, date_debut, date_fin, user)



def _get_performance_simplifiee(agent, date_debut, date_fin):
    """
    Calcul simplifié de la performance si le service complet n'est pas disponible.
    """
    inventaires = InventaireJournalier.objects.filter(
        agent_saisie=agent,
        date__range=[date_debut, date_fin]
    ).count()
    
    if inventaires == 0:
        return {'note': 0, 'rang': None, 'total_agents': 0}
    
    jours_possibles = (date_fin - date_debut).days + 1
    taux_presence = (inventaires / jours_possibles * 100) if jours_possibles > 0 else 0
    
    # Note basée sur le taux de présence
    if taux_presence >= 80:
        note = 16 + (taux_presence - 80) / 20 * 2
    elif taux_presence >= 60:
        note = 12 + (taux_presence - 60) / 20 * 4
    elif taux_presence >= 40:
        note = 10 + (taux_presence - 40) / 20 * 2
    else:
        note = 6 + taux_presence / 40 * 4
    
    return {
        'note': min(20, note),
        'rang': None,
        'total_agents': 0,
        'jours_travailles': inventaires,
        'taux_presence': taux_presence
    }


# def _calculer_stats_coherence(agent, date_debut, date_fin):
#     """
#     Calcule les statistiques de cohérence de l'agent.
#     """
#     try:
#         from .services import notation_service
#         notation_service = notation_service.get_notation_service()
        
#         perf = notation_service.calculer_performance_agent_periode(
#             agent, date_debut, date_fin
#         )
        
#         if perf:
#             return {
#                 'jours_3_criteres': perf.jours_3_criteres,
#                 'jours_2_criteres': perf.jours_2_criteres,
#                 'jours_1_critere': perf.jours_1_critere,
#                 'jours_0_critere': perf.jours_0_critere,
#                 'jours_impertinents': perf.jours_impertinents,
#                 'jours_travailles': perf.jours_travailles,
#                 'taux_presence': perf.taux_presence
#             }
        
#         return None
        
#     except Exception:
#         return None


def _calculer_stats_coherence(agent, date_debut, date_fin):
    """
    Calcule les statistiques de cohérence pour un agent.
    
    Args:
        agent: Instance UtilisateurSUPPER
        date_debut: Date de début
        date_fin: Date de fin
        
    Returns:
        dict: Statistiques de cohérence
    """
    perf = _calculer_performance_agent_detaillee(agent, date_debut, date_fin)
    
    return {
        'jours_3_criteres': perf.get('jours_3_criteres', 0),
        'jours_2_criteres': perf.get('jours_2_criteres', 0),
        'jours_1_critere': perf.get('jours_1_critere', 0),
        'jours_0_critere': perf.get('jours_0_critere', 0),
        'jours_impertinents': perf.get('jours_impertinents', 0),
        'jours_travailles': perf.get('jours_travailles', 0),
        'taux_presence': perf.get('taux_presence', 0)
    }


def _calculer_evolution_taux(taux_avant, taux_apres):
    """
    Calcule l'évolution du taux et retourne un dict avec les infos.
    """
    if taux_avant is None or taux_apres is None:
        return {
            'valeur': None,
            'direction': 'stable',
            'classe': 'text-muted'
        }
    
    evolution = float(taux_apres) - float(taux_avant)
    
    if evolution > 5:
        direction = 'amelioration'
        classe = 'text-success'
        icone = 'fa-arrow-up'
    elif evolution < -5:
        direction = 'degradation'
        classe = 'text-danger'
        icone = 'fa-arrow-down'
    else:
        direction = 'stable'
        classe = 'text-muted'
        icone = 'fa-equals'
    
    return {
        'valeur': evolution,
        'direction': direction,
        'classe': classe,
        'icone': icone
    }


# def _calculer_evolution_agent(agent, date_debut, date_fin):
#     """
#     Calcule l'évolution de la performance de l'agent dans le temps.
#     Retourne des données pour un graphique.
#     """
#     # Diviser la période en semaines
#     evolution = []
#     current = date_debut
    
#     while current <= date_fin:
#         week_end = min(current + timedelta(days=6), date_fin)
        
#         # Compter les inventaires de la semaine
#         inventaires = InventaireJournalier.objects.filter(
#             agent_saisie=agent,
#             date__range=[current, week_end]
#         ).count()
        
#         # Compter les jours impertinents
#         impertinents = ConfigurationJour.objects.filter(
#             date__range=[current, week_end],
#             statut=StatutJour.IMPERTINENT
#         ).count()
        
#         evolution.append({
#             'semaine': current.strftime('%d/%m'),
#             'date_debut': current,
#             'date_fin': week_end,
#             'inventaires': inventaires,
#             'impertinents': impertinents
#         })
        
#         current = week_end + timedelta(days=1)
    
#     return evolution

def _calculer_evolution_agent(agent, date_debut, date_fin):
    """
    Calcule l'évolution des performances d'un agent sur la période.
    
    Args:
        agent: Instance UtilisateurSUPPER
        date_debut: Date de début
        date_fin: Date de fin
        
    Returns:
        dict: Données d'évolution pour graphiques
    """
    from inventaire.models import InventaireJournalier, RecetteJournaliere
    
    # Récupérer les données jour par jour
    inventaires = InventaireJournalier.objects.filter(
        agent_saisie=agent,
        date__range=[date_debut, date_fin],
        type_inventaire='normal'
    ).order_by('date')
    
    evolution = {
        'dates': [],
        'notes': [],
        'vehicules': [],
        'taux': []
    }
    
    for inv in inventaires:
        evolution['dates'].append(inv.date.strftime('%d/%m'))
        evolution['vehicules'].append(inv.total_vehicules or 0)
        
        # Récupérer le taux de déperdition si disponible
        try:
            recette = RecetteJournaliere.objects.get(
                poste=inv.poste,
                date=inv.date
            )
            taux = float(recette.taux_deperdition) if recette.taux_deperdition else 0
        except RecetteJournaliere.DoesNotExist:
            taux = 0
        
        evolution['taux'].append(taux)
        
        # Note du jour (simplifiée)
        note = 12  # Base
        if inv.total_vehicules and inv.total_vehicules > 0:
            note += 2
        if taux <= -5:
            note += 2
        elif taux > -5:
            note -= 3  # Malus impertinent
        
        evolution['notes'].append(min(20, max(0, note)))
    
    return evolution


# def _generer_recommandations(moyenne_globale, pct_3_criteres, total_jours_impertinents, postes_data):
#     """
#     Génère des recommandations personnalisées basées sur la performance.
#     """
#     recommandations = []
    
#     # Recommandation principale basée sur la note
#     if moyenne_globale >= 16:
#         recommandations.append({
#             'type': 'success',
#             'icone': 'fa-trophy',
#             'titre': 'Excellent !',
#             'message': "Performance exceptionnelle. Cet agent peut servir de référence pour la formation des pairs."
#         })
#     elif moyenne_globale >= 14:
#         recommandations.append({
#             'type': 'info',
#             'icone': 'fa-thumbs-up',
#             'titre': 'Très bien',
#             'message': "Bonne performance générale. Maintenir ce niveau d'excellence."
#         })
#     elif moyenne_globale >= 12:
#         recommandations.append({
#             'type': 'primary',
#             'icone': 'fa-chart-line',
#             'titre': 'Performance correcte',
#             'message': "Résultats satisfaisants avec une marge de progression identifiable."
#         })
#     elif moyenne_globale >= 10:
#         recommandations.append({
#             'type': 'warning',
#             'icone': 'fa-exclamation-triangle',
#             'titre': 'À améliorer',
#             'message': "Performance en dessous des attentes. Une formation complémentaire est recommandée."
#         })
#     else:
#         recommandations.append({
#             'type': 'danger',
#             'icone': 'fa-times-circle',
#             'titre': 'Action requise',
#             'message': "Performance insuffisante nécessitant une intervention immédiate et un suivi rapproché."
#         })
    
#     # Recommandation sur la cohérence
#     if pct_3_criteres < 50:
#         recommandations.append({
#             'type': 'warning',
#             'icone': 'fa-balance-scale',
#             'titre': 'Cohérence à améliorer',
#             'message': f"Seulement {pct_3_criteres:.0f}% des jours avec cohérence totale (3/3 critères). "
#                        "Travailler sur l'alignement des données saisies."
#         })
    
#     # Recommandation sur les jours impertinents
#     if total_jours_impertinents > 5:
#         recommandations.append({
#             'type': 'danger',
#             'icone': 'fa-calendar-times',
#             'titre': 'Jours impertinents élevés',
#             'message': f"{total_jours_impertinents} jours impertinents détectés. "
#                        "Réviser les pratiques de saisie et la qualité des données."
#         })
#     elif total_jours_impertinents > 2:
#         recommandations.append({
#             'type': 'warning',
#             'icone': 'fa-calendar-times',
#             'titre': 'Attention aux jours impertinents',
#             'message': f"{total_jours_impertinents} jour(s) impertinent(s). "
#                        "Surveiller la cohérence des saisies."
#         })
    
#     # Recommandations spécifiques par poste
#     for poste in postes_data:
#         if poste.get('note_moyenne', 0) < 10:
#             recommandations.append({
#                 'type': 'warning',
#                 'icone': 'fa-building',
#                 'titre': f"Poste {poste['poste'].nom}",
#                 'message': f"Note faible ({poste['note_moyenne']:.1f}/20) sur ce poste. "
#                            "Analyser les causes spécifiques et proposer un accompagnement."
#             })
    
#     return recommandations

def _generer_recommandations(moyenne_globale, pct_3_criteres, total_jours_impertinents, postes_data):
    """
    Génère des recommandations personnalisées basées sur les performances.
    
    Args:
        moyenne_globale: Note moyenne de l'agent
        pct_3_criteres: Pourcentage de jours avec 3/3 critères
        total_jours_impertinents: Nombre de jours impertinents
        postes_data: Liste des performances par poste
        
    Returns:
        list: Liste de recommandations
    """
    recommandations = []
    
    # Recommandation basée sur la note globale
    if moyenne_globale >= 15:
        recommandations.append({
            'type': 'success',
            'message': 'Excellente performance ! Continuez ainsi et partagez vos bonnes pratiques avec les autres agents.'
        })
    elif moyenne_globale >= 12:
        recommandations.append({
            'type': 'success',
            'message': 'Bonne performance générale. Quelques améliorations sur la cohérence des critères pourraient vous faire progresser vers l\'excellence.'
        })
    elif moyenne_globale >= 10:
        recommandations.append({
            'type': 'warning',
            'message': 'Performance correcte mais améliorable. Concentrez-vous sur l\'alignement des trois critères de notation (recettes, taux, stock).'
        })
    else:
        recommandations.append({
            'type': 'danger',
            'message': 'Performance insuffisante nécessitant une intervention immédiate et un suivi rapproché.'
        })
    
    # Recommandation sur les jours impertinents
    if total_jours_impertinents > 5:
        recommandations.append({
            'type': 'warning',
            'message': f'Attention: {total_jours_impertinents} jours impertinents détectés. Vérifiez la cohérence entre vos saisies d\'inventaire et les recettes déclarées par le chef de poste.'
        })
    elif total_jours_impertinents > 0:
        recommandations.append({
            'type': 'warning',
            'message': f'{total_jours_impertinents} jour(s) impertinent(s). Analysez les écarts entre inventaire et recettes pour ces journées.'
        })
    
    # Recommandation sur la cohérence 3/3
    if pct_3_criteres < 50:
        recommandations.append({
            'type': 'warning',
            'message': f'Seulement {pct_3_criteres:.0f}% des jours avec cohérence totale (3/3 critères). Travailler sur l\'alignement des données saisies.'
        })
    elif pct_3_criteres >= 80:
        recommandations.append({
            'type': 'success',
            'message': f'Excellent taux de cohérence ({pct_3_criteres:.0f}% des jours avec 3/3 critères).'
        })
    
    # Recommandation sur les postes (si données disponibles)
    if postes_data:
        postes_faibles = [p for p in postes_data if p.get('note_moyenne', 0) < 10]
        if postes_faibles:
            noms_postes = [p.get('poste', {}).get('nom', 'Inconnu') if isinstance(p.get('poste'), dict) else str(p.get('poste', 'Inconnu')) for p in postes_faibles[:3]]
            recommandations.append({
                'type': 'warning',
                'message': f'Performances faibles sur certains postes: {", ".join(noms_postes)}. Un accompagnement spécifique pourrait être utile.'
            })
    
    return recommandations

# ===================================================================
# EXPORTS
# ===================================================================

__all__ = [
    '_generer_classement_simplifie',
    '_calculer_performance_agent_detaillee',
    '_get_performance_simplifiee',
    '_get_performances_par_poste_detaillees',
    '_get_performances_par_poste_simplifiees',
    '_calculer_stats_coherence',
    '_calculer_evolution_agent',
    '_generer_recommandations',
    'get_rang_agent_periode',
]
