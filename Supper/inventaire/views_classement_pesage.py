# ===================================================================
# inventaire/views_classement_pesage.py - Vues de classement pesage SUPPER
# VERSION MISE À JOUR - Intégration des permissions granulaires
# ===================================================================
"""
Vues pour le classement des stations de pesage par rendement.
Basé sur les montants recouvrés (amendes payées/quittancées).

RÈGLES D'ACCÈS:
- Classement pesage: peut_voir_classement_station_pesage
- Filtrage automatique des stations selon l'habilitation de l'utilisateur
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg, Q
from datetime import date, timedelta
import calendar
from decimal import Decimal
import logging

from accounts.models import Poste

# Import des fonctions de permissions et décorateurs
from common.permissions import (
    has_permission,
    get_postes_accessibles,
    get_postes_pesage_accessibles,
    check_poste_access,
    user_has_acces_tous_postes,
    is_admin_user,
    is_service_central,
    is_cisop_pesage,
    is_operationnel_pesage,
)
from common.decorators import (
    permission_required_granular,
    classement_pesage_required,
)
from common.utils import log_user_action

logger = logging.getLogger('supper.classement_pesage')


# ===================================================================
# FONCTIONS UTILITAIRES
# ===================================================================

def calculer_dates_periode_pesage(periode, annee, mois=None, trimestre=None, 
                                   semestre=None, semaine=None):
    """
    Calcule les dates de début et fin selon la période pour le pesage.
    
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
        # Cumul à date (depuis le début de l'année jusqu'à aujourd'hui)
        date_debut = date(annee, 1, 1)
        date_fin = today
    
    elif periode == 'semaine':
        if semaine:
            semaine_num = int(semaine)
            date_debut = date(annee, 1, 1) + timedelta(weeks=semaine_num-1)
            date_fin = date_debut + timedelta(days=6)
        else:
            date_debut = today - timedelta(days=today.weekday())
            date_fin = date_debut + timedelta(days=6)
    
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
    
    return date_debut, date_fin


def get_periode_label_pesage(periode, annee, mois=None, trimestre=None, 
                              semestre=None, semaine=None):
    """
    Génère le label de la période pour l'affichage pesage.
    
    Returns:
        str: Label formaté de la période
    """
    MOIS_NOMS = {
        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
        5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
        9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
    }
    
    if periode == 'cumul':
        return f"Cumul à date - {annee}"
    
    elif periode == 'semaine':
        if semaine:
            return f"Semaine {semaine} - {annee}"
        return "Semaine en cours"
    
    elif periode == 'mois':
        if mois:
            return f"{MOIS_NOMS[int(mois)]} {annee}"
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


def calculer_classement_pesage(date_debut=None, date_fin=None, user=None):
    """
    Calcule le classement des stations de pesage par rendement.
    Basé sur le montant total recouvré (amendes payées).
    
    Args:
        date_debut: Date de début de la période
        date_fin: Date de fin de la période
        user: Utilisateur pour le filtrage des postes accessibles (optionnel)
    
    Returns:
        list: Liste triée des stations avec leurs statistiques
    """
    from inventaire.models_pesage import AmendeEmise, QuittancementPesage
    
    today = date.today()
    
    if date_debut is None:
        date_debut = date(today.year, 1, 1)
    if date_fin is None:
        date_fin = today
    
    # =====================================================
    # FILTRAGE DES STATIONS SELON L'HABILITATION
    # =====================================================
    if user and not user_has_acces_tous_postes(user):
        # Utilisateur mono-poste -> uniquement sa station
        stations = get_postes_pesage_accessibles(user)
    else:
        # Admin, services centraux, CISOP pesage -> toutes les stations
        stations = Poste.objects.filter(type='pesage', is_active=True)
    
    classement = []
    
    for station in stations:
        # Calculer les statistiques pour cette station
        # Basé sur les amendes PAYÉES (date de paiement dans la période)
        stats = AmendeEmise.objects.filter(
            station=station,
            statut='paye',
            date_paiement__date__gte=date_debut,
            date_paiement__date__lte=date_fin
        ).aggregate(
            total_recouvre=Sum('montant_amende'),
            nombre_paiements=Count('id'),
            moyenne_amende=Avg('montant_amende')
        )
        
        # Statistiques des émissions
        stats_emissions = AmendeEmise.objects.filter(
            station=station,
            date_heure_emission__date__gte=date_debut,
            date_heure_emission__date__lte=date_fin
        ).aggregate(
            total_emis=Sum('montant_amende'),
            nombre_emissions=Count('id'),
            hors_gabarit=Count('id', filter=Q(est_hors_gabarit=True))
        )
        
        total_recouvre = stats['total_recouvre'] or Decimal('0')
        nb_paiements = stats['nombre_paiements'] or 0
        moyenne = stats['moyenne_amende'] or Decimal('0')
        
        total_emis = stats_emissions['total_emis'] or Decimal('0')
        nb_emissions = stats_emissions['nombre_emissions'] or 0
        nb_hors_gabarit = stats_emissions['hors_gabarit'] or 0
        
        # Calculer le taux de recouvrement
        taux_recouvrement = 0
        if total_emis > 0:
            taux_recouvrement = (float(total_recouvre) / float(total_emis)) * 100
        
        # Ajouter au classement même si pas de recettes (pour le rang)
        classement.append({
            'station': station,
            'total_recouvre': float(total_recouvre),
            'nombre_paiements': nb_paiements,
            'moyenne_amende': float(moyenne),
            'total_emis': float(total_emis),
            'nombre_emissions': nb_emissions,
            'hors_gabarit': nb_hors_gabarit,
            'taux_recouvrement': round(taux_recouvrement, 1),
            'region': station.get_region_display() if hasattr(station, 'get_region_display') else station.region,
        })
    
    # Trier par total recouvré décroissant
    classement.sort(key=lambda x: x['total_recouvre'], reverse=True)
    
    # Ajouter les rangs
    for i, item in enumerate(classement, 1):
        item['rang'] = i
    
    return classement


def get_rang_station_pesage(station, annee=None, user=None):
    """
    Retourne le rang d'une station dans le classement cumul à date.
    
    Args:
        station: Instance de Poste (station de pesage)
        annee: Année pour le calcul (par défaut: année en cours)
        user: Utilisateur pour le filtrage (optionnel)
    
    Returns:
        dict: {'rang': int, 'total_stations': int, 'total_recouvre': Decimal}
    """
    if annee is None:
        annee = date.today().year
    
    today = date.today()
    date_debut = date(annee, 1, 1)
    date_fin = today
    
    classement = calculer_classement_pesage(date_debut, date_fin, user)
    
    for item in classement:
        if item['station'].id == station.id:
            return {
                'rang': item['rang'],
                'total_stations': len(classement),
                'total_recouvre': item['total_recouvre'],
                'taux_recouvrement': item['taux_recouvrement']
            }
    
    return {
        'rang': None,
        'total_stations': len(classement),
        'total_recouvre': 0,
        'taux_recouvrement': 0
    }


# ===================================================================
# VUE PRINCIPALE: CLASSEMENT DES STATIONS DE PESAGE
# ===================================================================

@login_required
@permission_required_granular('peut_voir_classement_station_pesage')
def classement_stations_pesage_rendement(request):
    """
    Vue pour classer les stations de pesage par rendement.
    Basé sur les montants recouvrés (amendes payées).
    
    PERMISSIONS REQUISES:
    - peut_voir_classement_station_pesage
    
    ACCÈS AUX STATIONS:
    - Admin/Services centraux/CISOP Pesage: Toutes les stations
    - Opérationnels pesage (chef station, régisseur, chef équipe): Leur station uniquement
    """
    user = request.user
    
    # Log de l'action utilisateur
    log_user_action(
        user=user,
        action="Consultation classement pesage rendement",
        details=f"Accès à la page de classement des stations de pesage par rendement",
        request=request
    )
    logger.info(f"[CLASSEMENT_PESAGE] Utilisateur {user.username} ({user.habilitation}) accède au classement pesage")
    
    # Récupérer les filtres
    periode = request.GET.get('periode', 'cumul')
    annee = int(request.GET.get('annee', date.today().year))
    mois = request.GET.get('mois')
    trimestre = request.GET.get('trimestre')
    semestre = request.GET.get('semestre')
    semaine = request.GET.get('semaine')
    
    # Déterminer les dates selon la période
    date_debut, date_fin = calculer_dates_periode_pesage(
        periode, annee, mois, trimestre, semestre, semaine
    )
    
    # Calculer le classement (avec filtrage automatique selon l'utilisateur)
    classement = calculer_classement_pesage(date_debut, date_fin, user)
    
    # Calculer statistiques globales
    if classement:
        total_global = sum(p['total_recouvre'] for p in classement)
        total_emis_global = sum(p['total_emis'] for p in classement)
        moyenne_globale = total_global / len(classement) if classement else 0
        taux_global = (total_global / total_emis_global * 100) if total_emis_global > 0 else 0
        
        # Identifier top 3 et bottom 3
        top_3 = classement[:3]
        bottom_3 = classement[-3:] if len(classement) > 3 else []
    else:
        total_global = 0
        total_emis_global = 0
        moyenne_globale = 0
        taux_global = 0
        top_3 = []
        bottom_3 = []
    
    # Log du résultat
    logger.info(f"[CLASSEMENT_PESAGE] {user.username} - Période: {periode} - {len(classement)} stations affichées")
    
    # Noms des mois pour le filtre
    MOIS_NOMS = {
        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
        5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
        9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
    }
    
    context = {
        'classement': classement,
        'periode': periode,
        'periode_label': get_periode_label_pesage(
            periode, annee, mois, trimestre, semestre, semaine
        ),
        'date_debut': date_debut,
        'date_fin': date_fin,
        'annee': annee,
        'mois_selectionne': mois,
        'trimestre_selectionne': trimestre,
        'semestre_selectionne': semestre,
        'annees_disponibles': range(2020, date.today().year + 2),
        'mois_liste': [(i, MOIS_NOMS[i]) for i in range(1, 13)],
        'trimestres': [
            (1, '1er trimestre (Jan-Mars)'),
            (2, '2ème trimestre (Avr-Juin)'),
            (3, '3ème trimestre (Juil-Sept)'),
            (4, '4ème trimestre (Oct-Déc)')
        ],
        'semestres': [
            (1, '1er semestre (Jan-Juin)'),
            (2, '2ème semestre (Juil-Déc)')
        ],
        'total_global': total_global,
        'total_emis_global': total_emis_global,
        'taux_global': round(taux_global, 1),
        'moyenne_globale': moyenne_globale,
        'nombre_stations': len(classement),
        'top_3': top_3,
        'bottom_3': bottom_3,
        'title': 'Classement des Stations de Pesage par Rendement',
        # Indicateur d'accès complet pour le template
        'acces_tous_postes': user_has_acces_tous_postes(user),
    }
    
    return render(request, 'pesage/classement_stations_rendement.html', context)