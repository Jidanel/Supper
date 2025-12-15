# ===================================================================
# inventaire/views_pv_confrontation.py
# Génération du Procès Verbal de Confrontation pour le Pesage
# VERSION CORRIGÉE - Intégration des permissions granulaires
# ===================================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import logging
import os
import pytz

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, Image, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from django.conf import settings
from accounts.models import Poste, UtilisateurSUPPER
from inventaire.models_pesage import *
from inventaire.models_config import ConfigurationGlobale
from common.utils import log_user_action

# Import des fonctions de permissions granulaires depuis common.permissions
from common.permissions import (
    # Fonctions de vérification de permissions
    has_permission,
    user_has_acces_tous_postes,
    get_postes_pesage_accessibles,
    check_poste_access,
    
    # Fonctions de classification utilisateurs
    is_admin_user,
    is_operationnel_pesage,
    is_regisseur_pesage,
    is_chef_station_pesage,
    
    # Utilitaires de logging
    log_acces_refuse,
)

logger = logging.getLogger('supper')

# Fuseau horaire Cameroun
CAMEROUN_TZ = pytz.timezone('Africa/Douala')
HEURE_DEBUT_JOURNEE = time(9, 0, 0)
HEURE_FIN_JOURNEE = time(8, 59, 59)


# ===================================================================
# FONCTIONS UTILITAIRES - VERSION AVEC PERMISSIONS GRANULAIRES
# ===================================================================

def peut_acceder_pv_confrontation(user):
    """
    Vérifie si l'utilisateur peut accéder au PV de confrontation.
    
    Utilise la permission granulaire 'peut_voir_pv_confrontation'.
    
    Habilitations ayant cette permission selon la matrice:
    - admin_principal, coord_psrr, serv_info (admins)
    - serv_emission, serv_controle, serv_ordre, chef_ag (services centraux)
    - cisop_pesage (CISOP)
    - chef_station_pesage, regisseur_pesage (opérationnels pesage)
    
    Args:
        user: L'utilisateur à vérifier
        
    Returns:
        bool: True si l'utilisateur a la permission d'accès
    """
    if not user or not user.is_authenticated:
        logger.debug(f"[PV_CONFRONTATION] Accès refusé: utilisateur non authentifié")
        return False
    
    # Vérifier la permission granulaire
    has_perm = has_permission(user, 'peut_voir_pv_confrontation')
    
    logger.debug(
        f"[PV_CONFRONTATION] Vérification permission pour {user.username} "
        f"(habilitation={user.habilitation}): {'ACCORDÉE' if has_perm else 'REFUSÉE'}"
    )
    
    return has_perm


def get_user_station_pesage(user):
    """
    Retourne la station de pesage accessible à l'utilisateur.
    
    Logique d'accès selon les permissions granulaires:
    - Utilisateurs avec 'acces_tous_postes' → None (toutes les stations)
    - Utilisateurs HABILITATIONS_PESAGE → leur station d'affectation uniquement
    - Autres cas → False (pas d'accès)
    
    Args:
        user: L'utilisateur
        
    Returns:
        - None si l'utilisateur peut accéder à toutes les stations
        - Poste (station pesage) si accès limité à une station
        - False si l'utilisateur n'a pas accès
    """
    if not user or not user.is_authenticated:
        logger.debug(f"[PV_CONFRONTATION] get_user_station_pesage: utilisateur non authentifié")
        return False
    
    # Vérifier si l'utilisateur a accès à tous les postes
    if user_has_acces_tous_postes(user):
        logger.debug(
            f"[PV_CONFRONTATION] {user.username} a accès à TOUTES les stations de pesage "
            f"(habilitation={user.habilitation}, acces_tous_postes=True)"
        )
        return None  # Accès à toutes les stations
    
    # Pour les opérationnels pesage, vérifier leur station d'affectation
    if is_operationnel_pesage(user):
        poste = getattr(user, 'poste_affectation', None)
        if poste and poste.type == 'pesage' and poste.is_active:
            logger.debug(
                f"[PV_CONFRONTATION] {user.username} a accès à sa station d'affectation: "
                f"{poste.nom} (code={poste.code})"
            )
            return poste
        else:
            logger.warning(
                f"[PV_CONFRONTATION] {user.username} est opérationnel pesage mais "
                f"n'a pas de station de pesage valide affectée"
            )
            return False
    
    logger.debug(
        f"[PV_CONFRONTATION] {user.username} n'a pas accès aux stations de pesage "
        f"(habilitation={user.habilitation})"
    )
    return False


def get_chef_station(station):
    """
    Récupère le chef de station de pesage.
    
    Args:
        station: Instance de Poste (station de pesage)
        
    Returns:
        UtilisateurSUPPER ou None
    """
    chef = UtilisateurSUPPER.objects.filter(
        poste_affectation=station,
        habilitation='chef_station_pesage',
        is_active=True
    ).first()
    
    if chef:
        logger.debug(f"[PV_CONFRONTATION] Chef station {station.nom}: {chef.nom_complet}")
    else:
        logger.debug(f"[PV_CONFRONTATION] Aucun chef station trouvé pour {station.nom}")
    
    return chef


def get_regisseur_station(station):
    """
    Récupère le régisseur de la station de pesage.
    
    Args:
        station: Instance de Poste (station de pesage)
        
    Returns:
        UtilisateurSUPPER ou None
    """
    regisseur = UtilisateurSUPPER.objects.filter(
        poste_affectation=station,
        habilitation='regisseur_pesage',
        is_active=True
    ).first()
    
    if regisseur:
        logger.debug(f"[PV_CONFRONTATION] Régisseur station {station.nom}: {regisseur.nom_complet}")
    else:
        logger.debug(f"[PV_CONFRONTATION] Aucun régisseur trouvé pour {station.nom}")
    
    return regisseur


def get_datetime_periode_9h(date_debut, date_fin):
    """
    Calcule les datetime de début et fin selon la logique 9h-9h
    Début: date_debut à 9h00
    Fin: date_fin + 1 jour à 8h59:59
    
    Args:
        date_debut: Date de début de la période
        date_fin: Date de fin de la période
        
    Returns:
        tuple: (datetime_debut, datetime_fin)
    """
    datetime_debut = CAMEROUN_TZ.localize(
        datetime.combine(date_debut, HEURE_DEBUT_JOURNEE)
    )
    datetime_fin = CAMEROUN_TZ.localize(
        datetime.combine(date_fin + timedelta(days=1), HEURE_FIN_JOURNEE)
    )
    return datetime_debut, datetime_fin


# ===================================================================
# CALCUL DES DONNÉES DU PV DE CONFRONTATION
# ===================================================================

def nombre_en_lettres_annee(annee):
    """
    Convertit une année en lettres pour le texte officiel
    Ex: 2025 -> 'deux mil vingt-cinq'
        2026 -> 'deux mil vingt-six'
        2030 -> 'deux mil trente'
    """
    unites = ['', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf']
    
    annee = int(annee)
    milliers = annee // 1000
    reste = annee % 1000
    dizaines_reste = reste % 100
    
    resultat = []
    
    # Pour les années 2000+
    if milliers == 2:
        resultat.append('deux mil')
    elif milliers == 1:
        resultat.append('mil')
    
    # Dizaines et unités (pour 20-99)
    if dizaines_reste == 0:
        pass  # Rien à ajouter (ex: 2000)
    elif dizaines_reste < 10:
        resultat.append(unites[dizaines_reste])
    elif dizaines_reste < 20:
        speciaux = ['dix', 'onze', 'douze', 'treize', 'quatorze', 'quinze', 
                    'seize', 'dix-sept', 'dix-huit', 'dix-neuf']
        resultat.append(speciaux[dizaines_reste - 10])
    elif dizaines_reste < 30:
        if dizaines_reste == 20:
            resultat.append('vingt')
        elif dizaines_reste == 21:
            resultat.append('vingt et un')
        else:
            resultat.append(f'vingt-{unites[dizaines_reste - 20]}')
    elif dizaines_reste < 40:
        if dizaines_reste == 30:
            resultat.append('trente')
        elif dizaines_reste == 31:
            resultat.append('trente et un')
        else:
            resultat.append(f'trente-{unites[dizaines_reste - 30]}')
    elif dizaines_reste < 50:
        if dizaines_reste == 40:
            resultat.append('quarante')
        elif dizaines_reste == 41:
            resultat.append('quarante et un')
        else:
            resultat.append(f'quarante-{unites[dizaines_reste - 40]}')
    elif dizaines_reste < 60:
        if dizaines_reste == 50:
            resultat.append('cinquante')
        elif dizaines_reste == 51:
            resultat.append('cinquante et un')
        else:
            resultat.append(f'cinquante-{unites[dizaines_reste - 50]}')
    elif dizaines_reste < 70:
        if dizaines_reste == 60:
            resultat.append('soixante')
        elif dizaines_reste == 61:
            resultat.append('soixante et un')
        else:
            resultat.append(f'soixante-{unites[dizaines_reste - 60]}')
    elif dizaines_reste < 80:
        # 70-79: soixante-dix, soixante et onze, etc.
        if dizaines_reste == 70:
            resultat.append('soixante-dix')
        elif dizaines_reste == 71:
            resultat.append('soixante et onze')
        else:
            speciaux = ['douze', 'treize', 'quatorze', 'quinze', 'seize', 'dix-sept', 'dix-huit', 'dix-neuf']
            resultat.append(f'soixante-{speciaux[dizaines_reste - 72]}')
    elif dizaines_reste < 100:
        # 80-99: quatre-vingt, quatre-vingt-un, etc.
        if dizaines_reste == 80:
            resultat.append('quatre-vingts')
        elif dizaines_reste == 81:
            resultat.append('quatre-vingt-un')
        elif dizaines_reste < 90:
            resultat.append(f'quatre-vingt-{unites[dizaines_reste - 80]}')
        elif dizaines_reste == 90:
            resultat.append('quatre-vingt-dix')
        elif dizaines_reste == 91:
            resultat.append('quatre-vingt-onze')
        else:
            speciaux = ['douze', 'treize', 'quatorze', 'quinze', 'seize', 'dix-sept', 'dix-huit', 'dix-neuf']
            resultat.append(f'quatre-vingt-{speciaux[dizaines_reste - 92]}')
    
    return ' '.join(resultat)


def calculer_donnees_pv_confrontation(station, date_debut, date_fin):
    """
    Calcule toutes les données nécessaires pour le PV de confrontation
    
    Logique 9h-9h: 
    - date_debut à 9h00 → date_fin+1 à 8h59:59
    
    Returns:
        dict avec toutes les données calculées
    """
    logger.info(f"=" * 60)
    logger.info(f"[PV_CONFRONTATION] CALCUL DONNÉES - Station: {station.nom}")
    logger.info(f"[PV_CONFRONTATION] Période: {date_debut} à {date_fin}")
    
    # Datetime avec logique 9h-9h
    datetime_debut, datetime_fin = get_datetime_periode_9h(date_debut, date_fin)
    
    # Datetime pour la période antérieure (avant date_debut à 9h)
    datetime_avant_periode = datetime_debut - timedelta(seconds=1)
    
    # ========== 1. NOMBRE DE PESÉES ==========
    pesees = PeseesJournalieres.objects.filter(
        station=station,
        date__gte=date_debut,
        date__lte=date_fin
    ).aggregate(total=Sum('nombre_pesees'))['total'] or 0
    
    logger.info(f"[PV_CONFRONTATION] Nombre de pesées: {pesees}")
    
    # ========== 2. AMENDES ÉMISES DANS LA PÉRIODE ==========
    # Amendes dont la date d'émission est dans la période 9h-9h
    amendes_emises = AmendeEmise.objects.filter(
        station=station,
        date_heure_emission__gte=datetime_debut,
        date_heure_emission__lte=datetime_fin
    )
    
    # Nombre d'infractions (surcharge + HG = 2 infractions)
    stats_infractions = amendes_emises.aggregate(
        surcharge_seule=Count('id', filter=Q(est_surcharge=True, est_hors_gabarit=False)),
        hg_seul=Count('id', filter=Q(est_surcharge=False, est_hors_gabarit=True)),
        les_deux=Count('id', filter=Q(est_surcharge=True, est_hors_gabarit=True)),
    )
    
    nombre_infractions = (
        stats_infractions['surcharge_seule'] +
        stats_infractions['hg_seul'] +
        (stats_infractions['les_deux'] * 2)  # Compte pour 2
    )
    
    # Montant amendes émises (A)
    montant_emis_A = amendes_emises.aggregate(
        total=Sum('montant_amende')
    )['total'] or Decimal('0')
    
    logger.info(f"[PV_CONFRONTATION] Infractions: {nombre_infractions}, Montant émis (A): {montant_emis_A}")
    
    # ========== 3. MONTANT RECOUVRÉ DU MOIS (B) ==========
    # Amendes émises ET payées dans la période
    amendes_recouv_mois = AmendeEmise.objects.filter(
        station=station,
        statut=StatutAmende.PAYE,
        date_heure_emission__gte=datetime_debut,
        date_heure_emission__lte=datetime_fin,
        date_paiement__gte=datetime_debut,
        date_paiement__lte=datetime_fin
    )
    
    montant_recouvre_mois_B = amendes_recouv_mois.aggregate(
        total=Sum('montant_amende')
    )['total'] or Decimal('0')
    
    logger.info(f"[PV_CONFRONTATION] Montant recouvré du mois (B): {montant_recouvre_mois_B}")
    
    # ========== 4. RAR ANTÉRIEURS RECOUVRÉS (C) ==========
    # Amendes émises AVANT la période mais payées DANS la période
    amendes_rar_anterieurs = AmendeEmise.objects.filter(
        station=station,
        statut=StatutAmende.PAYE,
        date_heure_emission__lt=datetime_debut,  # Émises AVANT
        date_paiement__gte=datetime_debut,       # Payées DANS
        date_paiement__lte=datetime_fin
    )
    
    montant_rar_anterieurs_C = amendes_rar_anterieurs.aggregate(
        total=Sum('montant_amende')
    )['total'] or Decimal('0')
    
    logger.info(f"[PV_CONFRONTATION] RAR antérieurs recouvrés (C): {montant_rar_anterieurs_C}")
    
    # ========== 5. TOTAL (D = B + C) ==========
    total_D = montant_recouvre_mois_B + montant_rar_anterieurs_C
    
    # ========== 6. ÉCART 1 (B - A) ==========
    ecart_1 = montant_recouvre_mois_B - montant_emis_A
    
    # ========== 7. MONTANT REVERSEMENTS AU TRÉSOR (F) ==========
    # Somme des quittancements de la période
    # On prend les quittancements journaliers dont la date_recette est dans la période
    # ET les quittancements par décade qui chevauchent la période
    
    quittancements_journaliers = QuittancementPesage.objects.filter(
        station=station,
        type_declaration='journaliere',
        date_recette__gte=date_debut,
        date_recette__lte=date_fin
    ).aggregate(total=Sum('montant_quittance'))['total'] or Decimal('0')
    
    quittancements_decades = QuittancementPesage.objects.filter(
        station=station,
        type_declaration='decade'
    ).filter(
        Q(date_debut_decade__lte=date_fin) & Q(date_fin_decade__gte=date_debut)
    ).aggregate(total=Sum('montant_quittance'))['total'] or Decimal('0')
    
    montant_reversements_F = quittancements_journaliers + quittancements_decades
    
    logger.info(f"[PV_CONFRONTATION] Reversements au trésor (F): {montant_reversements_F}")
    
    # ========== 8. ÉCART 2 (F - D) ==========
    ecart_2 = montant_reversements_F - total_D
    
    # ========== 9. RESTE À RECOUVRER ==========
    # RAR = Émis dans la période et non encore payé
    reste_a_recouvrer = amendes_emises.filter(
        statut=StatutAmende.NON_PAYE
    ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
    
    # ========== 10. DONNÉES PAR SEMAINE ==========
    donnees_par_semaine = calculer_donnees_par_semaine(
        station, date_debut, date_fin
    )
    
    # Résumé
    donnees = {
        'station': station,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'datetime_debut': datetime_debut,
        'datetime_fin': datetime_fin,
        
        # Ligne principale du tableau
        'nombre_pesees': pesees,
        'nombre_infractions': nombre_infractions,
        'montant_emis_A': montant_emis_A,
        'montant_recouvre_mois_B': montant_recouvre_mois_B,
        'rar_anterieurs_C': montant_rar_anterieurs_C,
        'total_D': total_D,
        'ecart_1': ecart_1,  # B - A
        'montant_reversements_F': montant_reversements_F,
        'ecart_2': ecart_2,  # F - D
        'reste_a_recouvrer': reste_a_recouvrer,
        
        # Détails par semaine
        'donnees_par_semaine': donnees_par_semaine,
        
        # Statistiques détaillées
        'stats_infractions': stats_infractions,
        'annee_texte': nombre_en_lettres_annee(date_fin.year),
    }
    
    logger.info(f"=" * 60)
    logger.info(f"[PV_CONFRONTATION] RÉSUMÉ CALCUL:")
    logger.info(f"  Pesées: {pesees}")
    logger.info(f"  Infractions: {nombre_infractions}")
    logger.info(f"  Émis (A): {montant_emis_A}")
    logger.info(f"  Recouvré mois (B): {montant_recouvre_mois_B}")
    logger.info(f"  RAR antérieurs (C): {montant_rar_anterieurs_C}")
    logger.info(f"  Total (D): {total_D}")
    logger.info(f"  Écart 1 (B-A): {ecart_1}")
    logger.info(f"  Reversements (F): {montant_reversements_F}")
    logger.info(f"  Écart 2 (F-D): {ecart_2}")
    logger.info(f"=" * 60)
    
    return donnees


def calculer_donnees_par_semaine(station, date_debut, date_fin):
    """
    Calcule les données détaillées par semaine personnalisée
    Semaine = 7 jours à partir de date_debut
    """
    semaines = []
    current_start = date_debut
    
    while current_start <= date_fin:
        # Fin de semaine = min(start + 6 jours, date_fin)
        current_end = min(current_start + timedelta(days=6), date_fin)
        
        # Datetime avec logique 9h-9h
        dt_debut, dt_fin = get_datetime_periode_9h(current_start, current_end)
        dt_avant = dt_debut - timedelta(seconds=1)
        
        # Pesées de la semaine
        pesees = PeseesJournalieres.objects.filter(
            station=station,
            date__gte=current_start,
            date__lte=current_end
        ).aggregate(total=Sum('nombre_pesees'))['total'] or 0
        
        # Amendes émises
        amendes_emises = AmendeEmise.objects.filter(
            station=station,
            date_heure_emission__gte=dt_debut,
            date_heure_emission__lte=dt_fin
        )
        
        # Infractions
        stats_inf = amendes_emises.aggregate(
            surcharge_seule=Count('id', filter=Q(est_surcharge=True, est_hors_gabarit=False)),
            hg_seul=Count('id', filter=Q(est_surcharge=False, est_hors_gabarit=True)),
            les_deux=Count('id', filter=Q(est_surcharge=True, est_hors_gabarit=True)),
        )
        infractions = (
            stats_inf['surcharge_seule'] +
            stats_inf['hg_seul'] +
            (stats_inf['les_deux'] * 2)
        )
        
        # Montant émis (A)
        montant_A = amendes_emises.aggregate(
            total=Sum('montant_amende')
        )['total'] or Decimal('0')
        
        # Recouvré du mois (B) - émis ET payé dans la semaine
        montant_B = AmendeEmise.objects.filter(
            station=station,
            statut=StatutAmende.PAYE,
            date_heure_emission__gte=dt_debut,
            date_heure_emission__lte=dt_fin,
            date_paiement__gte=dt_debut,
            date_paiement__lte=dt_fin
        ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
        
        # RAR antérieurs (C)
        montant_C = AmendeEmise.objects.filter(
            station=station,
            statut=StatutAmende.PAYE,
            date_heure_emission__lt=dt_debut,
            date_paiement__gte=dt_debut,
            date_paiement__lte=dt_fin
        ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
        
        # Total D
        total_D = montant_B + montant_C
        
        # Écart 1
        ecart_1 = montant_B - montant_A
        
        # Quittancements (F)
        quitt_jour = QuittancementPesage.objects.filter(
            station=station,
            type_declaration='journaliere',
            date_recette__gte=current_start,
            date_recette__lte=current_end
        ).aggregate(total=Sum('montant_quittance'))['total'] or Decimal('0')
        
        quitt_dec = QuittancementPesage.objects.filter(
            station=station,
            type_declaration='decade'
        ).filter(
            Q(date_debut_decade__lte=current_end) & Q(date_fin_decade__gte=current_start)
        ).aggregate(total=Sum('montant_quittance'))['total'] or Decimal('0')
        
        montant_F = quitt_jour + quitt_dec
        
        # Écart 2
        ecart_2 = montant_F - total_D
        
        semaines.append({
            'date_debut': current_start,
            'date_fin': current_end,
            'label': f"{current_start.strftime('%d/%m')} au {current_end.strftime('%d/%m/%Y')}",
            'nombre_pesees': pesees,
            'nombre_infractions': infractions,
            'montant_A': montant_A,
            'montant_B': montant_B,
            'montant_C': montant_C,
            'total_D': total_D,
            'ecart_1': ecart_1,
            'montant_F': montant_F,
            'ecart_2': ecart_2,
        })
        
        # Semaine suivante
        current_start = current_end + timedelta(days=1)
    
    return semaines


# ===================================================================
# VUES - VERSION AVEC PERMISSIONS GRANULAIRES
# ===================================================================

@login_required
def selection_pv_confrontation(request):
    """
    Vue de sélection pour le PV de confrontation.
    
    Accès basé sur la permission 'peut_voir_pv_confrontation':
    - Utilisateurs avec accès_tous_postes: peuvent choisir n'importe quelle station
    - Utilisateurs opérationnels pesage: station d'affectation uniquement
    
    Variables de contexte (IDENTIQUES au fichier original):
    - stations: QuerySet des stations accessibles (ou None si station_auto)
    - station_auto: Station d'affectation (ou None si accès multiple)
    - date_debut_suggestion: Date de début suggérée (1er jour mois précédent)
    - date_fin_suggestion: Date de fin suggérée (dernier jour mois précédent)
    - date_max: Date maximale sélectionnable (aujourd'hui)
    - is_admin: Boolean indiquant si l'utilisateur a accès à toutes les stations
    - title: Titre de la page
    """
    user = request.user
    
    # === Vérification des permissions granulaires ===
    if not peut_acceder_pv_confrontation(user):
        log_user_action(
            user,
            "Tentative accès PV Confrontation",
            f"Permission 'peut_voir_pv_confrontation' refusée - Habilitation: {user.habilitation}",
            request
        )
        log_acces_refuse(user, "selection_pv_confrontation", "Permission peut_voir_pv_confrontation manquante")
        messages.error(request, "Vous n'avez pas la permission d'accéder au PV de confrontation.")
        return redirect('common:dashboard')
    
    # Log de l'accès à la page de sélection
    logger.info(
        f"[PV_CONFRONTATION] Accès sélection par {user.username} "
        f"(habilitation={user.habilitation})"
    )
    
    # === Déterminer les stations accessibles ===
    # Utilise user_has_acces_tous_postes() au lieu de is_admin()
    acces_global = user_has_acces_tous_postes(user)
    
    if acces_global:
        # Utilisateur avec accès à toutes les stations
        stations = Poste.objects.filter(type='pesage', is_active=True).order_by('region', 'nom')
        station_auto = None
        logger.debug(
            f"[PV_CONFRONTATION] {user.username} a accès à {stations.count()} stations (accès global)"
        )
    else:
        # Utilisateur avec accès limité à sa station d'affectation
        station_auto = get_user_station_pesage(user)
        if station_auto is False:
            log_user_action(
                user,
                "Accès PV Confrontation bloqué",
                "Aucune station de pesage valide affectée à l'utilisateur",
                request
            )
            messages.error(request, "Vous devez être affecté à une station de pesage valide.")
            return redirect('common:dashboard')
        stations = None
        logger.debug(
            f"[PV_CONFRONTATION] {user.username} accès limité à sa station: {station_auto.nom}"
        )
    
    # Dates par défaut: mois précédent
    today = date.today()
    premier_jour_mois = today.replace(day=1)
    dernier_jour_mois_prec = premier_jour_mois - timedelta(days=1)
    premier_jour_mois_prec = dernier_jour_mois_prec.replace(day=1)
    
    if request.method == 'POST':
        # Traitement du formulaire
        if acces_global:
            station_id = request.POST.get('station_id')
            if not station_id:
                messages.error(request, "Veuillez sélectionner une station.")
                return render(request, 'pesage/selection_pv_confrontation.html', {
                    'stations': stations,
                    'date_debut_suggestion': premier_jour_mois_prec,
                    'date_fin_suggestion': dernier_jour_mois_prec,
                    'is_admin': True,  # Variable de contexte maintenue pour compatibilité template
                })
            try:
                station = Poste.objects.get(pk=station_id, type='pesage', is_active=True)
            except Poste.DoesNotExist:
                logger.warning(
                    f"[PV_CONFRONTATION] {user.username} a tenté d'accéder à une station invalide: {station_id}"
                )
                messages.error(request, "Station invalide.")
                return redirect('inventaire:selection_pv_confrontation')
        else:
            station = station_auto
        
        date_debut_str = request.POST.get('date_debut')
        date_fin_str = request.POST.get('date_fin')
        action = request.POST.get('action', 'apercu')
        
        if not date_debut_str or not date_fin_str:
            messages.error(request, "Veuillez sélectionner les dates.")
        else:
            try:
                date_debut = date.fromisoformat(date_debut_str)
                date_fin = date.fromisoformat(date_fin_str)
                
                if date_debut > date_fin:
                    messages.error(request, "La date de début doit être antérieure à la date de fin.")
                elif date_fin > today:
                    messages.error(request, "La date de fin ne peut pas être dans le futur.")
                elif (date_fin - date_debut).days > 365:
                    messages.error(request, "La période ne peut pas dépasser 1 an.")
                else:
                    # Log de l'action de l'utilisateur
                    log_user_action(
                        user,
                        "Sélection PV Confrontation",
                        f"Station: {station.nom}, Période: {date_debut_str} au {date_fin_str}, Action: {action}",
                        request
                    )
                    
                    if action == 'apercu':
                        return redirect('inventaire:apercu_pv_confrontation',
                                        station_id=station.pk,
                                        date_debut=date_debut_str,
                                        date_fin=date_fin_str)
                    else:
                        return redirect('inventaire:generer_pv_confrontation_pdf',
                                        station_id=station.pk,
                                        date_debut=date_debut_str,
                                        date_fin=date_fin_str)
            except ValueError:
                messages.error(request, "Format de date invalide.")
    
    # Variables de contexte IDENTIQUES au fichier original
    context = {
        'stations': stations,
        'station_auto': station_auto,
        'date_debut_suggestion': premier_jour_mois_prec,
        'date_fin_suggestion': dernier_jour_mois_prec,
        'date_max': today,
        'is_admin': acces_global,  # Maintenu pour compatibilité template
        'title': 'PV de Confrontation - Sélection',
    }
    
    return render(request, 'pesage/selection_pv_confrontation.html', context)


@login_required
def apercu_pv_confrontation(request, station_id, date_debut, date_fin):
    """
    Aperçu HTML du PV de confrontation.
    
    Vérifications:
    1. Permission 'peut_voir_pv_confrontation'
    2. Accès à la station spécifique (via check_poste_access)
    
    Variables de contexte (IDENTIQUES au fichier original):
    - station: Instance Poste de la station
    - date_debut: Chaîne de date début (format YYYY-MM-DD)
    - date_fin: Chaîne de date fin (format YYYY-MM-DD)
    - date_debut_obj: Objet date de début
    - date_fin_obj: Objet date de fin
    - donnees: Dictionnaire des données calculées
    - chef_station: Utilisateur chef de station (ou None)
    - regisseur: Utilisateur régisseur (ou None)
    - config: Configuration globale
    - date_du_jour: Date du jour
    - is_admin: Boolean accès global
    - title: Titre de la page
    """
    user = request.user
    station = get_object_or_404(Poste, pk=station_id, type='pesage')
    
    # === Vérification permission granulaire ===
    if not peut_acceder_pv_confrontation(user):
        log_user_action(
            user,
            "Tentative aperçu PV Confrontation",
            f"Permission refusée - Station: {station.nom}",
            request
        )
        log_acces_refuse(user, "apercu_pv_confrontation", "Permission peut_voir_pv_confrontation manquante")
        messages.error(request, "Vous n'avez pas la permission d'accéder au PV de confrontation.")
        return redirect('common:dashboard')
    
    # === Vérification accès à la station spécifique ===
    if not user_has_acces_tous_postes(user):
        # L'utilisateur n'a pas accès global, vérifier l'accès à cette station
        if not check_poste_access(user, station):
            log_user_action(
                user,
                "Accès station refusé - PV Confrontation",
                f"Tentative d'accès à la station {station.nom} (ID={station_id}) non autorisée",
                request
            )
            log_acces_refuse(user, f"apercu_pv_confrontation/{station_id}", "Accès station non autorisé")
            messages.error(request, "Vous n'avez pas accès à cette station.")
            return redirect('inventaire:selection_pv_confrontation')
    
    # Parser les dates
    try:
        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
    except ValueError:
        logger.warning(
            f"[PV_CONFRONTATION] Format de dates invalide: {date_debut} - {date_fin}"
        )
        messages.error(request, "Format de dates invalide.")
        return redirect('inventaire:selection_pv_confrontation')
    
    # Log de l'action
    log_user_action(
        user,
        "Aperçu PV Confrontation",
        f"Station: {station.nom} ({station.code}), Période: {date_debut} au {date_fin}",
        request
    )
    logger.info(
        f"[PV_CONFRONTATION] Aperçu généré par {user.username} pour {station.nom} "
        f"({date_debut} au {date_fin})"
    )
    
    # Récupérer chef et régisseur
    chef_station = get_chef_station(station)
    regisseur = get_regisseur_station(station)
    
    # Calculer les données
    donnees = calculer_donnees_pv_confrontation(station, date_debut_obj, date_fin_obj)
    
    # Récupérer la configuration globale pour l'en-tête
    config = ConfigurationGlobale.get_config()
    
    # Variables de contexte IDENTIQUES au fichier original
    context = {
        'station': station,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'date_debut_obj': date_debut_obj,
        'date_fin_obj': date_fin_obj,
        'donnees': donnees,
        'chef_station': chef_station,
        'regisseur': regisseur,
        'config': config,
        'date_du_jour': date.today(),
        'is_admin': user_has_acces_tous_postes(user),  # Maintenu pour compatibilité template
        'title': f"PV de Confrontation - {station.nom}",
    }
    
    return render(request, 'pesage/apercu_pv_confrontation.html', context)


@login_required
def generer_pv_confrontation_pdf(request, station_id, date_debut, date_fin):
    """
    Génère le PDF du PV de confrontation.
    
    Vérifications:
    1. Permission 'peut_voir_pv_confrontation'
    2. Accès à la station spécifique (via check_poste_access)
    """
    user = request.user
    station = get_object_or_404(Poste, pk=station_id, type='pesage')
    
    # === Vérification permission granulaire ===
    if not peut_acceder_pv_confrontation(user):
        log_user_action(
            user,
            "Tentative génération PDF PV Confrontation",
            f"Permission refusée - Station: {station.nom}",
            request
        )
        log_acces_refuse(user, "generer_pv_confrontation_pdf", "Permission peut_voir_pv_confrontation manquante")
        messages.error(request, "Vous n'avez pas la permission de générer ce document.")
        return redirect('common:dashboard')
    
    # === Vérification accès à la station spécifique ===
    if not user_has_acces_tous_postes(user):
        if not check_poste_access(user, station):
            log_user_action(
                user,
                "Accès station refusé - PDF PV Confrontation",
                f"Tentative génération PDF pour station {station.nom} non autorisée",
                request
            )
            log_acces_refuse(user, f"generer_pv_confrontation_pdf/{station_id}", "Accès station non autorisé")
            messages.error(request, "Vous n'avez pas accès à cette station.")
            return redirect('inventaire:selection_pv_confrontation')
    
    # Parser les dates
    try:
        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
    except ValueError:
        logger.warning(
            f"[PV_CONFRONTATION] Format de dates invalide pour PDF: {date_debut} - {date_fin}"
        )
        messages.error(request, "Format de dates invalide.")
        return redirect('inventaire:selection_pv_confrontation')
    
    # Récupérer les données
    config = ConfigurationGlobale.get_config()
    chef_station = get_chef_station(station)
    regisseur = get_regisseur_station(station)
    donnees = calculer_donnees_pv_confrontation(station, date_debut_obj, date_fin_obj)
    
    # Créer le PDF
    response = HttpResponse(content_type='application/pdf')
    filename = f'pv_confrontation_{station.code}_{date_debut}_au_{date_fin}.pdf'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    
    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(A4),
        rightMargin=1*cm,
        leftMargin=1*cm,
        topMargin=1*cm,
        bottomMargin=1*cm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # ========== EN-TÊTE BILINGUE ==========
    elements.append(creer_entete_pv(config, station))
    elements.append(Spacer(1, 0.5*cm))
    
    # ========== TITRE ==========
    titre_style = ParagraphStyle(
        'TitrePV',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=colors.HexColor('#1a1a1a'),
        alignment=TA_CENTER,
        spaceAfter=15
    )
    
    titre = Paragraph(
        f"<b>PROCÈS VERBAL MENSUEL DE CONFRONTATION</b><br/>"
        f"<font size='11'>Période du {date_debut_obj.strftime('%d/%m/%Y')} au {date_fin_obj.strftime('%d/%m/%Y')}</font>",
        titre_style
    )
    elements.append(titre)
    elements.append(Spacer(1, 0.3*cm))
    
    # ========== TEXTE INTRODUCTIF ==========
    date_jour = date.today().strftime('%d/%m/%Y')
    nom_chef = chef_station.nom_complet if chef_station else "[Chef de Station]"
    nom_regisseur = regisseur.nom_complet if regisseur else "[Régisseur]"
    
    intro_style = ParagraphStyle(
        'IntroStyle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_LEFT,
        spaceAfter=15,
        leading=14
    )
    
    texte_intro = f"""
    L'an deux mil vingt-cinq et le {date_jour},<br/><br/>
    Nous soussignés, <b>{nom_chef}</b>, Chef de Station du Pesage Routier de <b>{station.nom}</b>, 
    et <b>{nom_regisseur}</b>, Régisseur des Recettes à ladite station ;<br/><br/>
    Reconnaissons avoir confronté les Ordres de Paiement émis de la période allant du 
    <b>{date_debut_obj.strftime('%d/%m/%Y')}</b> au <b>{date_fin_obj.strftime('%d/%m/%Y')}</b>, 
    avec les Déclarations des Recettes d'une part, et les Déclarations des Recettes 
    avec les Quittances de Reversement d'autre part.<br/><br/>
    Il se dégage la situation détaillée dans le tableau ci-après :
    """
    
    elements.append(Paragraph(texte_intro, intro_style))
    elements.append(Spacer(1, 0.3*cm))
    
    # ========== TABLEAU RÉCAPITULATIF ==========
    elements.append(creer_tableau_recapitulatif_pv(donnees, styles))
    elements.append(Spacer(1, 0.5*cm))
    
    # ========== TEXTE DE CONCLUSION ==========
    conclusion = Paragraph(
        "En foi de quoi, le présent procès-verbal est établi pour servir et valoir ce que de droit.",
        intro_style
    )
    elements.append(conclusion)
    elements.append(Spacer(1, 1*cm))
    
    # ========== SIGNATURES ==========
    elements.append(creer_signatures_pv(nom_regisseur, nom_chef, styles))
    
    # ========== PAGE 2: DÉTAIL PAR SEMAINE ==========
    elements.append(PageBreak())
    
    # En-tête page 2
    elements.append(creer_entete_pv(config, station))
    elements.append(Spacer(1, 0.3*cm))
    
    titre_detail = Paragraph(
        f"<b>FICHE DE SUIVI DES AMENDES</b><br/>"
        f"<font size='10'>STATION DE PESAGE DE {station.nom.upper()} - "
        f"PÉRIODE DU {date_debut_obj.strftime('%d/%m/%Y')} AU {date_fin_obj.strftime('%d/%m/%Y')}</font>",
        titre_style
    )
    elements.append(titre_detail)
    elements.append(Spacer(1, 0.3*cm))
    
    # Tableau détaillé par semaine
    elements.append(creer_tableau_detail_semaines(donnees, styles))
    elements.append(Spacer(1, 0.5*cm))
    
    # Signatures page 2
    elements.append(creer_signatures_pv(nom_regisseur, nom_chef, styles))
    
    # Générer le PDF
    doc.build(elements)
    
    # Log de l'action (utilisation de log_user_action de common/utils.py)
    log_user_action(
        user,
        "Génération PDF PV Confrontation",
        f"Station: {station.nom} ({station.code}), Période: {date_debut} au {date_fin}, "
        f"Fichier: {filename}",
        request
    )
    logger.info(
        f"[PV_CONFRONTATION] PDF généré par {user.username} - Station: {station.nom}, "
        f"Période: {date_debut} au {date_fin}"
    )
    
    return response


# ===================================================================
# FONCTIONS DE CRÉATION DES ÉLÉMENTS PDF
# ===================================================================

def creer_entete_pv(config, station):
    """Crée l'en-tête bilingue du PV (identique au compte d'emploi)"""
    styles = getSampleStyleSheet()
    
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_CENTER,
        leading=10
    )
    
    col_gauche = [
        Paragraph(f"<b>{config.republique_fr}</b>", header_style),
        Paragraph(config.devise_fr, header_style),
        Paragraph("*****", header_style),
        Paragraph(f"<b>{config.ministere_fr}</b>", header_style),
        Paragraph("*****", header_style),
        Paragraph(f"<b>{config.direction_fr}</b>", header_style),
        Paragraph("**********", header_style),
        Paragraph(f"<b>{config.programme_fr}</b>", header_style),
        Paragraph("*********", header_style),
        Paragraph(f"<b>RÉGIE DE RECETTE DU PESAGE DE {station.nom.upper()}</b>", header_style),
        Paragraph("*********", header_style)
    ]
    
    logo_cell = ""
    if config.logo:
        try:
            logo_path = os.path.join(settings.MEDIA_ROOT, config.logo.name)
            if os.path.exists(logo_path):
                logo_cell = Image(logo_path, width=2.5*cm, height=2.5*cm)
        except:
            pass
    
    col_droite = [
        Paragraph(f"<b>{config.republique_en}</b>", header_style),
        Paragraph(config.devise_en, header_style),
        Paragraph("*****", header_style),
        Paragraph(f"<b>{config.ministere_en}</b>", header_style),
        Paragraph("*****", header_style),
        Paragraph(f"<b>{config.direction_en}</b>", header_style),
        Paragraph("**********", header_style),
        Paragraph(f"<b>{config.programme_en}</b>", header_style),
        Paragraph("*********", header_style),
        Paragraph(f"<b>{station.nom.upper()} WEIGH STATION</b>", header_style),
        Paragraph("*********", header_style)
    ]
    
    if logo_cell:
        header_data = [[col_gauche, logo_cell, col_droite]]
    else:
        header_data = [[col_gauche, "DGI", col_droite]]
    
    header_table = Table(header_data, colWidths=[8*cm, 4*cm, 8*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
    ]))
    
    return header_table


def creer_tableau_recapitulatif_pv(donnees, styles):
    """Crée le tableau récapitulatif principal du PV"""
    
    def fmt(val):
        if val == 0 or val == Decimal('0'):
            return "0"
        return f"{val:,.0f}".replace(',', ' ')
    
    # En-têtes sur 2 lignes
    table_data = [
        # Ligne 1 des en-têtes
        [
            Paragraph("<b>Nombre<br/>des<br/>pesées</b>", styles['Normal']),
            Paragraph("<b>Nombre<br/>d'infractions</b>", styles['Normal']),
            Paragraph("<b>Montant<br/>Ordre des<br/>paiements<br/>(amendes<br/>émises du<br/>mois) (A)</b>", styles['Normal']),
            Paragraph("<b>Montant déclaration des Recettes<br/>(Total des amendes recouvrées)</b>", styles['Normal']),
            "",
            "",
            Paragraph("<b>Écart<br/>(RAR)<br/>(B-A)</b>", styles['Normal']),
            Paragraph("<b>Montant des<br/>reversements<br/>au Trésor<br/>public<br/>(Amendes<br/>reversées) (F)</b>", styles['Normal']),
            Paragraph("<b>Écart<br/>(F-D)</b>", styles['Normal']),
            Paragraph("<b>Observations</b>", styles['Normal']),
        ],
        # Ligne 2 des sous-en-têtes
        [
            "", "", "",
            Paragraph("<b>Montant du<br/>mois (B)</b>", styles['Normal']),
            Paragraph("<b>Montant<br/>des mois<br/>antérieurs<br/>(C)</b>", styles['Normal']),
            Paragraph("<b>Total<br/>D= B+C</b>", styles['Normal']),
            "", "", "", ""
        ],
        # Ligne des données
        [
            fmt(donnees['nombre_pesees']),
            fmt(donnees['nombre_infractions']),
            fmt(donnees['montant_emis_A']),
            fmt(donnees['montant_recouvre_mois_B']),
            fmt(donnees['rar_anterieurs_C']),
            fmt(donnees['total_D']),
            fmt(donnees['ecart_1']),
            fmt(donnees['montant_reversements_F']),
            fmt(donnees['ecart_2']),
            "",  # Observations vides
        ]
    ]
    
    col_widths = [1.8*cm, 1.8*cm, 2.2*cm, 2.2*cm, 2.2*cm, 2.2*cm, 2*cm, 2.5*cm, 2*cm, 2.5*cm]
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Fusion des cellules d'en-tête
        ('SPAN', (3, 0), (5, 0)),  # "Montant déclaration des Recettes"
        ('SPAN', (0, 0), (0, 1)),  # Nombre pesées
        ('SPAN', (1, 0), (1, 1)),  # Nombre infractions
        ('SPAN', (2, 0), (2, 1)),  # Montant A
        ('SPAN', (6, 0), (6, 1)),  # Écart B-A
        ('SPAN', (7, 0), (7, 1)),  # Montant F
        ('SPAN', (8, 0), (8, 1)),  # Écart F-D
        ('SPAN', (9, 0), (9, 1)),  # Observations
        
        # Style en-têtes
        ('BACKGROUND', (0, 0), (-1, 1), colors.HexColor('#4a5568')),
        ('TEXTCOLOR', (0, 0), (-1, 1), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 1), 7),
        
        # Style données
        ('FONTSIZE', (0, 2), (-1, -1), 9),
        ('BACKGROUND', (0, 2), (-1, -1), colors.whitesmoke),
        
        # Alignement
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Bordures
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        
        # Padding
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    
    return table


def creer_tableau_detail_semaines(donnees, styles):
    """Crée le tableau détaillé par semaine (page 2)"""
    
    def fmt(val):
        if val == 0 or val == Decimal('0'):
            return "0"
        return f"{val:,.0f}".replace(',', ' ')
    
    # En-têtes
    table_data = [
        [
            Paragraph("<b>Semaine</b>", styles['Normal']),
            Paragraph("<b>Pesées</b>", styles['Normal']),
            Paragraph("<b>Infr.</b>", styles['Normal']),
            Paragraph("<b>Amendes<br/>émises (A)</b>", styles['Normal']),
            Paragraph("<b>Recouvré<br/>mois (B)</b>", styles['Normal']),
            Paragraph("<b>RAR ant.<br/>(C)</b>", styles['Normal']),
            Paragraph("<b>Total<br/>(D)</b>", styles['Normal']),
            Paragraph("<b>Écart 1<br/>(B-A)</b>", styles['Normal']),
            Paragraph("<b>Reversements<br/>(F)</b>", styles['Normal']),
            Paragraph("<b>Écart 2<br/>(F-D)</b>", styles['Normal']),
            Paragraph("<b>Obs.</b>", styles['Normal']),
        ]
    ]
    
    # Données par semaine
    total_pesees = 0
    total_inf = 0
    total_A = Decimal('0')
    total_B = Decimal('0')
    total_C = Decimal('0')
    total_D = Decimal('0')
    total_F = Decimal('0')
    
    for sem in donnees['donnees_par_semaine']:
        table_data.append([
            sem['label'],
            fmt(sem['nombre_pesees']),
            fmt(sem['nombre_infractions']),
            fmt(sem['montant_A']),
            fmt(sem['montant_B']),
            fmt(sem['montant_C']),
            fmt(sem['total_D']),
            fmt(sem['ecart_1']),
            fmt(sem['montant_F']),
            fmt(sem['ecart_2']),
            "",  # Observations
        ])
        
        total_pesees += sem['nombre_pesees']
        total_inf += sem['nombre_infractions']
        total_A += sem['montant_A']
        total_B += sem['montant_B']
        total_C += sem['montant_C']
        total_D += sem['total_D']
        total_F += sem['montant_F']
    
    # Ligne TOTAL
    table_data.append([
        Paragraph("<b>TOTAL</b>", styles['Normal']),
        Paragraph(f"<b>{fmt(total_pesees)}</b>", styles['Normal']),
        Paragraph(f"<b>{fmt(total_inf)}</b>", styles['Normal']),
        Paragraph(f"<b>{fmt(total_A)}</b>", styles['Normal']),
        Paragraph(f"<b>{fmt(total_B)}</b>", styles['Normal']),
        Paragraph(f"<b>{fmt(total_C)}</b>", styles['Normal']),
        Paragraph(f"<b>{fmt(total_D)}</b>", styles['Normal']),
        Paragraph(f"<b>{fmt(total_B - total_A)}</b>", styles['Normal']),
        Paragraph(f"<b>{fmt(total_F)}</b>", styles['Normal']),
        Paragraph(f"<b>{fmt(total_F - total_D)}</b>", styles['Normal']),
        "",
    ])
    
    col_widths = [3*cm, 1.5*cm, 1.2*cm, 2.2*cm, 2.2*cm, 2*cm, 2*cm, 2*cm, 2.2*cm, 2*cm, 2*cm]
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # En-tête
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c0392b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        
        # Corps
        ('FONTSIZE', (0, 1), (-1, -2), 8),
        ('BACKGROUND', (0, 1), (-1, -2), colors.whitesmoke),
        
        # Ligne Total
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e2e8f0')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        
        # Alignement
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Bordures
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        
        # Padding
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    
    return table


def creer_signatures_pv(nom_regisseur, nom_chef, styles):
    """Crée la zone de signatures"""
    
    sig_style = ParagraphStyle(
        'SignatureStyle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER
    )
    
    signature_data = [
        [
            Paragraph("<b>Le Régisseur des Recettes</b>", sig_style),
            Paragraph("", sig_style),
            Paragraph("<b>Le Chef de Station</b>", sig_style),
        ],
        [
            Paragraph("", sig_style),
            Paragraph("", sig_style),
            Paragraph("", sig_style),
        ],
        [
            Paragraph("", sig_style),
            Paragraph("", sig_style),
            Paragraph("", sig_style),
        ],
        [
            Paragraph(f"<b>{nom_regisseur}</b>", sig_style),
            Paragraph("", sig_style),
            Paragraph(f"<b>{nom_chef}</b>", sig_style),
        ],
    ]
    
    sig_table = Table(signature_data, colWidths=[8*cm, 4*cm, 8*cm])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    
    return sig_table