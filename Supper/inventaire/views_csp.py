# ===================================================================
# inventaire/views_csp.py - Vues pour le Contrôle Sur Pièce (CSP)
# Application SUPPER - Suivi des Péages et Pesages Routiers
# ===================================================================
#
# DESCRIPTION:
# Ce fichier contient les vues pour la fonctionnalité CSP (Contrôle Sur Pièce)
# qui permet de générer des rapports comparatifs entre les ventes déclarées,
# les montants quittancés et les stocks de tickets pour une période donnée.
#
# PERMISSIONS UTILISÉES:
# - peut_comptabiliser_quittances_peage: Accès au CSP Péage
# - peut_comptabiliser_quittances_pesage: Accès au CSP Pesage
#
# FICHIERS LIÉS:
# - templates/inventaire/csp_peage.html
# - templates/pesage/csp_pesage.html
# - inventaire/urls.py (ajout des routes)
# ===================================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q, Max
from django.http import HttpResponse
from datetime import date, timedelta, datetime
from decimal import Decimal
import logging
import calendar
from inventaire.models import HistoriqueQuittance
from accounts.models import Poste, Region
from inventaire.models import (
    RecetteJournaliere, Quittancement, GestionStock,
    SerieTicket, StockEvent, HistoriqueStock
)

# Import des permissions granulaires
from common.permissions import (
    has_permission,
    get_postes_peage_accessibles,
    get_postes_pesage_accessibles,
    check_poste_access,
    user_has_acces_tous_postes,
    log_acces_refuse,
)

# Import de la fonction de log manuelle
from common.utils import log_user_action

from django.utils import timezone

logger = logging.getLogger('supper')


# ===================================================================
# FONCTIONS UTILITAIRES POUR LE CSP
# ===================================================================

def calculer_stock_debut_periode(poste, date_debut):
    """
    Calcule le stock de tickets au début d'une période via Event Sourcing.
    Retourne le stock à la veille de la date de début.

    Args:
        poste: Instance de Poste
        date_debut: Date de début de la période

    Returns:
        Decimal: Valeur monétaire du stock
    """
    veille_debut = date_debut - timedelta(days=1)

    # Convertir la date en datetime avec fin de journée
    if isinstance(veille_debut, date) and not isinstance(veille_debut, datetime):
        date_reference_dt = timezone.make_aware(
            datetime.combine(veille_debut, datetime.max.time().replace(microsecond=999999))
        )
    else:
        date_reference_dt = veille_debut

    # Via StockEvent
    events = StockEvent.objects.filter(
        poste=poste,
        event_datetime__lte=date_reference_dt,
        is_cancelled=False
    ).aggregate(
        total_valeur=Sum('montant_variation'),
        total_tickets=Sum('nombre_tickets_variation')
    )

    valeur = events['total_valeur'] or Decimal('0')
    tickets = events['total_tickets'] or 0

    return max(Decimal('0'), valeur), max(0, tickets)

def get_date_derniere_quittance_mois(poste, date_debut, date_fin):
        """
        Récupère la date de la dernière quittance pour le dernier mois de la période.

        Logique:
        - CSP du 01 au 20 janvier → chercher dernière quittance de janvier
        - CSP du 01 au 31 janvier → chercher dernière quittance de janvier
        - CSP du 01 janvier au 05 février → chercher dernière quittance de FÉVRIER

        Args:
            poste: Instance de Poste
            date_debut: Date de début de la période CSP
            date_fin: Date de fin de la période CSP

        Returns:
            date ou None: Date de la dernière quittance, ou None si aucune
        """
        # Utiliser le mois de la date de fin
        mois_cible = date_fin.month
        annee_cible = date_fin.year

        # Chercher la dernière quittance (journalière ou décade) pour ce mois
        derniere_quittance = Quittancement.objects.filter(
            poste=poste
        ).filter(
            # Quittancement journalier pour ce mois
            Q(
                type_declaration='journaliere',
                date_recette__year=annee_cible,
                date_recette__month=mois_cible
            ) |
            # Quittancement décade qui touche ce mois
            Q(
                type_declaration='decade',
                date_fin_decade__year=annee_cible,
                date_fin_decade__month=mois_cible
            )
        ).aggregate(
            derniere_date=Max('date_quittancement')
        )

        return derniere_quittance.get('derniere_date')


def calculer_donnees_csp_poste_peage(poste, date_debut, date_fin):
    """
    Calcule toutes les données CSP pour un poste de péage sur une période.

    MISE À JOUR: Ajout des nouvelles colonnes:
    - montant_historique: Montant réel des historiques ACCT
    - ecart_historique: montant_historique - montant_quittance
    - date_derniere_quittance: Date de la dernière quittance du dernier mois

    Args:
        poste: Instance de Poste (péage)
        date_debut: Date de début de la période
        date_fin: Date de fin de la période

    Returns:
        dict: Dictionnaire contenant toutes les données CSP du poste
    """
    nombre_jours_periode = (date_fin - date_debut).days + 1

    # 1. Stock de début de période
    stock_debut_valeur, stock_debut_tickets = calculer_stock_debut_periode(poste, date_debut)

    # 2. Ventes déclarées (RecetteJournaliere)
    recettes = RecetteJournaliere.objects.filter(
        poste=poste,
        date__gte=date_debut,
        date__lte=date_fin
    )

    ventes_declarees = recettes.aggregate(
        total=Sum('montant_declare')
    )['total'] or Decimal('0')

    # Nombre de jours avec ventes déclarées
    jours_declares = recettes.values('date').distinct().count()

    # 3. Montant quittancé
    # 3a. Quittancements journaliers
    quittancements_journaliers = Quittancement.objects.filter(
        poste=poste,
        type_declaration='journaliere',
        date_recette__gte=date_debut,
        date_recette__lte=date_fin
    )

    total_quittance_journalier = quittancements_journaliers.aggregate(
        total=Sum('montant')
    )['total'] or Decimal('0')

    jours_quittances_journaliers = quittancements_journaliers.values('date_recette').distinct().count()

    # 3b. Quittancements de décade chevauchant la période
    quittancements_decades = Quittancement.objects.filter(
        poste=poste,
        type_declaration='decade'
    ).filter(
        Q(date_debut_decade__lte=date_fin) &
        Q(date_fin_decade__gte=date_debut)
    )

    total_quittance_decade = quittancements_decades.aggregate(
        total=Sum('montant')
    )['total'] or Decimal('0')

    # Calculer les jours quittancés par décade (approximation)
    jours_quittances_decades = 0
    for q in quittancements_decades:
        debut_effectif = max(q.date_debut_decade, date_debut)
        fin_effective = min(q.date_fin_decade, date_fin)
        jours_quittances_decades += (fin_effective - debut_effectif).days + 1

    # Total quittancé
    montant_quittance = total_quittance_journalier + total_quittance_decade
    jours_quittances = jours_quittances_journaliers + jours_quittances_decades

    # Éviter les doublons de jours
    jours_quittances = min(jours_quittances, nombre_jours_periode)

    # 4. Écart (déclaré - quittancé)
    ecart = montant_quittance - ventes_declarees

    # 5. Dernières quittances (les 3 dernières de la période)
    dernieres_quittances = Quittancement.objects.filter(
        poste=poste,
        date_quittancement__gte=date_debut,
        date_quittancement__lte=date_fin
    ).order_by('-date_quittancement')[:3]

    montant_dernieres_quittances = dernieres_quittances.aggregate(
        total=Sum('montant')
    )['total'] or Decimal('0')

    # ===================================================================
    # NOUVELLES COLONNES AJOUTÉES
    # ===================================================================

    # 6. Montant historique (ACCT) - via HistoriqueQuittance
    montant_historique = HistoriqueQuittance.get_montant_reel_pour_periode(
        poste, date_debut, date_fin
    )

    # 7. Écart 2 (historique - quittancé)
    ecart_historique = montant_historique - montant_quittance

    # 8. Date dernière quittance du dernier mois de la période
    date_derniere_quittance = get_date_derniere_quittance_mois(poste, date_debut, date_fin)

    # ===================================================================
    # FIN DES NOUVELLES COLONNES
    # ===================================================================

    return {
        'poste': poste,
        'poste_id': poste.id,
        'poste_nom': poste.nom,
        'poste_code': poste.code,
        'region': poste.region.nom if poste.region else 'N/A',
        'region_id': poste.region.id if poste.region else None,
        'stock_debut': stock_debut_valeur,
        'stock_debut_tickets': stock_debut_tickets,
        'ventes_declarees': ventes_declarees,
        'jours_declares': jours_declares,
        'jours_declares_str': f"{jours_declares}/{nombre_jours_periode}",
        'montant_quittance': montant_quittance,
        'jours_quittances': jours_quittances,
        'jours_quittances_str': f"{jours_quittances}/{nombre_jours_periode}",
        'ecart': ecart,
        'montant_dernieres_quittances': montant_dernieres_quittances,
        'dernieres_quittances': list(dernieres_quittances.values(
            'numero_quittance', 'montant', 'date_quittancement'
        )),
        # ===== NOUVELLES CLÉS =====
        'montant_historique': montant_historique,
        'ecart_historique': ecart_historique,
        'date_derniere_quittance': date_derniere_quittance,
    }


def calculer_donnees_csp_poste_pesage(station, date_debut, date_fin):
    """
    Calcule toutes les données CSP pour une station de pesage sur une période.

    Colonnes du tableau CSP Pesage (12 colonnes):
    1. Régions
    2. Stations de Pesage
    3. Nbre Pesées
    4. Nbre Infractions
    5. Total amendes émises (A)
    6. Amendes recouvrées (B)
    7. RAR du mois (A - B)
    8. Montant quittancé
    9. ECART1 (Quittancé - B)
    10. Historique ACCT (montant_reel de HistoriquesPesage)
    11. ECART2 (ACCT - Quittancé)
    12. Date dernière quittance

    Args:
        station: Instance de Poste (pesage)
        date_debut: Date de début de la période
        date_fin: Date de fin de la période

    Returns:
        dict: Dictionnaire contenant toutes les données CSP de la station
    """
    from inventaire.models_pesage import QuittancementPesage, AmendeEmise, PeseesJournalieres
    from inventaire.models_historique_pesage import HistoriquesPesage

    nombre_jours_periode = (date_fin - date_debut).days + 1

    # =================================================================
    # 1. NOMBRE DE PESÉES
    # =================================================================
    pesees = PeseesJournalieres.objects.filter(
        station=station,
        date__gte=date_debut,
        date__lte=date_fin
    )

    nbre_pesees = pesees.aggregate(total=Sum('nombre_pesees'))['total'] or 0
    jours_pesees = pesees.values('date').distinct().count()

    # =================================================================
    # 2. NOMBRE D'INFRACTIONS
    # =================================================================
    amendes_emises = AmendeEmise.objects.filter(
        station=station,
        date_heure_emission__date__gte=date_debut,
        date_heure_emission__date__lte=date_fin
    )

    nbre_infractions = amendes_emises.count()

    # =================================================================
    # 3. TOTAL AMENDES ÉMISES (A)
    # =================================================================
    total_amendes_emises = amendes_emises.aggregate(
        total=Sum('montant_amende')
    )['total'] or Decimal('0')

    jours_amendes = amendes_emises.values('date_heure_emission__date').distinct().count()

    # =================================================================
    # 4. AMENDES RECOUVRÉES (B)
    # =================================================================
    amendes_payees = AmendeEmise.objects.filter(
        station=station,
        statut='paye',
        date_paiement__date__gte=date_debut,
        date_paiement__date__lte=date_fin
    )

    amendes_recouvrees = amendes_payees.aggregate(
        total=Sum('montant_amende')
    )['total'] or Decimal('0')

    jours_paiements = amendes_payees.values('date_paiement__date').distinct().count()

    # =================================================================
    # 5. RAR DU MOIS (A - B)
    # =================================================================
    rar_mois = total_amendes_emises - amendes_recouvrees

    # =================================================================
    # 6. MONTANT QUITTANCÉ
    # =================================================================
    # Quittancements journaliers
    quittancements_journaliers = QuittancementPesage.objects.filter(
        station=station,
        type_declaration='journaliere',
        date_recette__gte=date_debut,
        date_recette__lte=date_fin
    )

    total_quittance_journalier = quittancements_journaliers.aggregate(
        total=Sum('montant_quittance')
    )['total'] or Decimal('0')

    jours_quittances_journaliers = quittancements_journaliers.values('date_recette').distinct().count()

    # Quittancements de décade
    quittancements_decades = QuittancementPesage.objects.filter(
        station=station,
        type_declaration='decade'
    ).filter(
        Q(date_debut_decade__lte=date_fin) &
        Q(date_fin_decade__gte=date_debut)
    )

    total_quittance_decade = quittancements_decades.aggregate(
        total=Sum('montant_quittance')
    )['total'] or Decimal('0')

    # Jours quittancés par décade
    jours_quittances_decades = 0
    for q in quittancements_decades:
        if q.date_debut_decade and q.date_fin_decade:
            debut_effectif = max(q.date_debut_decade, date_debut)
            fin_effective = min(q.date_fin_decade, date_fin)
            jours_quittances_decades += (fin_effective - debut_effectif).days + 1

    # Total quittancé
    montant_quittance = total_quittance_journalier + total_quittance_decade
    jours_quittances = min(jours_quittances_journaliers + jours_quittances_decades, nombre_jours_periode)

    # =================================================================
    # 7. ECART 1 (Quittancé - B)
    # =================================================================
    ecart1 = montant_quittance - amendes_recouvrees

    # =================================================================
    # 8. HISTORIQUE ACCT (montant_reel)
    # =================================================================
    # mois_cible = f"{date_fin.year}-{str(date_fin.month).zfill(2)}"
    mois_cible = date_fin.month
    annee_cible = date_fin.year

    historique_acct = Decimal('0')
    historique_obj = None
    has_historique = False

    try:
        historique_obj = HistoriquesPesage.objects.get(
            station=station,
            mois=mois_cible,
            annee=annee_cible
        )
        # CORRECTION: Utiliser montant_reel (part de la station)
        historique_acct = historique_obj.montant_reel
        has_historique = True
    except HistoriquesPesage.DoesNotExist:
        pass

    # =================================================================
    # 9. ECART 2 (ACCT - Quittancé)
    # =================================================================
    ecart2 = historique_acct - montant_quittance

    # =================================================================
    # 10. DATE DERNIÈRE QUITTANCE
    # =================================================================
    mois_cible_num = date_fin.month
    annee_cible = date_fin.year

    derniere_quittance = QuittancementPesage.objects.filter(
        station=station
    ).filter(
        Q(
            type_declaration='journaliere',
            date_recette__year=annee_cible,
            date_recette__month=mois_cible_num
        ) |
        Q(
            type_declaration='decade',
            date_fin_decade__year=annee_cible,
            date_fin_decade__month=mois_cible_num
        )
    ).aggregate(
        derniere_date=Max('date_quittancement')
    )

    date_derniere_quittance = derniere_quittance.get('derniere_date')

    # =================================================================
    # RETOUR DES DONNÉES
    # =================================================================
    return {
        # Identification
        'station': station,
        'station_id': station.id,
        'station_nom': station.nom,
        'station_code': station.code,
        'region': station.region.nom if station.region else 'N/A',
        'region_id': station.region.id if station.region else None,

        # Données CSP
        'nbre_pesees': nbre_pesees,
        'jours_pesees': jours_pesees,
        'jours_pesees_str': f"{jours_pesees}/{nombre_jours_periode}",

        'nbre_infractions': nbre_infractions,

        'total_amendes_emises': total_amendes_emises,
        'jours_amendes': jours_amendes,
        'jours_amendes_str': f"{jours_amendes}/{nombre_jours_periode}",

        'amendes_recouvrees': amendes_recouvrees,
        'jours_paiements': jours_paiements,
        'jours_paiements_str': f"{jours_paiements}/{nombre_jours_periode}",

        'rar_mois': rar_mois,

        'montant_quittance': montant_quittance,
        'jours_quittances': jours_quittances,
        'jours_quittances_str': f"{jours_quittances}/{nombre_jours_periode}",

        'ecart1': ecart1,

        # CORRECTION: historique_acct = montant_reel
        'historique_acct': historique_acct,
        'has_historique': has_historique,
        'historique_numero': f"HP-{historique_obj.annee}-{historique_obj.mois:02d}-{station.code}" if historique_obj else None,

        'ecart2': ecart2,

        'date_derniere_quittance': date_derniere_quittance,

        # Compatibilité
        'amendes_emises': total_amendes_emises,
        'amendes_payees': amendes_recouvrees,
        'ecart': ecart1,
    }


def calculer_totaux_csp_pesage(donnees_stations):
    """
    Calcule les totaux pour le tableau CSP Pesage.

    Args:
        donnees_stations: Liste de dicts retournés par calculer_donnees_csp_poste_pesage

    Returns:
        dict: Tous les totaux incluant total_historique
    """
    totaux = {
        'total_pesees': 0,
        'total_infractions': 0,
        'total_amendes_emises': Decimal('0'),
        'total_amendes_recouvrees': Decimal('0'),
        'total_rar': Decimal('0'),
        'total_quittance': Decimal('0'),
        'total_ecart1': Decimal('0'),
        'total_historique': Decimal('0'),
        'total_ecart2': Decimal('0'),
        'stations_avec_historique': 0,
        'stations_sans_historique': 0,
        'nombre_stations': len(donnees_stations),
    }

    for donnees in donnees_stations:
        totaux['total_pesees'] += donnees.get('nbre_pesees', 0)
        totaux['total_infractions'] += donnees.get('nbre_infractions', 0)
        totaux['total_amendes_emises'] += donnees.get('total_amendes_emises', Decimal('0'))
        totaux['total_amendes_recouvrees'] += donnees.get('amendes_recouvrees', Decimal('0'))
        totaux['total_rar'] += donnees.get('rar_mois', Decimal('0'))
        totaux['total_quittance'] += donnees.get('montant_quittance', Decimal('0'))
        totaux['total_ecart1'] += donnees.get('ecart1', Decimal('0'))
        totaux['total_historique'] += donnees.get('historique_acct', Decimal('0'))
        totaux['total_ecart2'] += donnees.get('ecart2', Decimal('0'))

        if donnees.get('has_historique', False):
            totaux['stations_avec_historique'] += 1
        else:
            totaux['stations_sans_historique'] += 1

    return totaux
# ===================================================================
# VUE SÉLECTION CSP PÉAGE
# ===================================================================

@login_required
def selection_csp_peage(request):
    """
    Vue de sélection de la période pour le CSP Péage.
    Permet de choisir les dates de début et de fin avant de générer le rapport.

    PERMISSIONS:
    - peut_comptabiliser_quittances_peage: Requis pour accéder à cette vue

    ACCÈS AUX POSTES:
    - Utilisateurs avec acces_tous_postes: voient tous les postes de péage
    - Autres: voient uniquement leur poste d'affectation
    """
    user = request.user

    # ========== VÉRIFICATION DES PERMISSIONS ==========
    if not has_permission(user, 'peut_comptabiliser_quittances_peage'):
        log_user_action(
            user=user,
            action="ACCES_REFUSE",
            description="Tentative d'accès à la sélection CSP Péage",
            details=f"Permission peut_comptabiliser_quittances_peage manquante | "
                   f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
                   f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            niveau="WARNING"
        )
        log_acces_refuse(user, "selection_csp_peage", "Permission peut_comptabiliser_quittances_peage manquante")
        messages.error(request, "Vous n'avez pas la permission d'accéder au Contrôle Sur Pièce Péage.")
        return redirect('common:dashboard')

    # Log de l'accès à la vue
    log_user_action(
        user=user,
        action="ACCES_CSP_PEAGE_SELECTION",
        description=f"Accès à la page de sélection CSP Péage",
        details=f"Utilisateur: {user.nom_complet} | "
               f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
               f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
        niveau="INFO"
    )

    logger.info(f"[CSP_PEAGE] Utilisateur {user.username} ({getattr(user, 'habilitation', 'N/A')}) "
                f"accède à la sélection CSP Péage")

    # ========== DÉTERMINATION DES POSTES ACCESSIBLES ==========
    acces_tous_postes = user_has_acces_tous_postes(user)

    if acces_tous_postes:
        postes = Poste.objects.filter(is_active=True, type='peage').select_related('region').order_by('region__nom', 'nom')
    else:
        if user.poste_affectation and user.poste_affectation.type == 'peage':
            postes = Poste.objects.filter(id=user.poste_affectation.id).select_related('region')
        else:
            postes = Poste.objects.none()

    # Dates par défaut suggérées
    today = date.today()

    # Suggestion : début du mois précédent → fin du mois précédent
    premier_jour_mois_actuel = today.replace(day=1)
    dernier_jour_mois_precedent = premier_jour_mois_actuel - timedelta(days=1)
    premier_jour_mois_precedent = dernier_jour_mois_precedent.replace(day=1)

    date_debut_suggestion = premier_jour_mois_precedent
    date_fin_suggestion = dernier_jour_mois_precedent

    if request.method == 'POST':
        date_debut_str = request.POST.get('date_debut')
        date_fin_str = request.POST.get('date_fin')
        poste_id = request.POST.get('poste_id')  # Optionnel pour filtrer un seul poste

        # Validations
        if not date_debut_str or not date_fin_str:
            messages.error(request, "Veuillez sélectionner une date de début et une date de fin.")
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
                    # Log de la sélection
                    log_user_action(
                        user=user,
                        action="SELECTION_PERIODE_CSP_PEAGE",
                        description=f"Sélection période CSP Péage",
                        details=f"Période: {date_debut_str} au {date_fin_str} | "
                               f"Poste filtre: {poste_id or 'Tous'} | "
                               f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
                        niveau="INFO"
                    )

                    # Rediriger vers la génération du rapport
                    url = f"?date_debut={date_debut_str}&date_fin={date_fin_str}"
                    if poste_id:
                        url += f"&poste_id={poste_id}"
                    return redirect(f"{request.path.replace('selection', 'generer')}{url}")

            except ValueError:
                messages.error(request, "Format de date invalide.")

    # ========== CONTEXTE ==========
    context = {
        'postes': postes,
        'date_debut_suggestion': date_debut_suggestion,
        'date_fin_suggestion': date_fin_suggestion,
        'date_max': today,
        'acces_tous_postes': acces_tous_postes,
        'title': "Contrôle Sur Pièce - Péage"
    }

    return render(request, 'inventaire/selection_csp_peage.html', context)


# ===================================================================
# VUE GÉNÉRATION CSP PÉAGE
# ===================================================================

@login_required
def generer_csp_peage(request):
    """
    Vue pour générer le rapport CSP Péage.
    Affiche le tableau avec toutes les données par poste et par région.

    PERMISSIONS:
    - peut_comptabiliser_quittances_peage: Requis pour accéder à cette vue

    Structure du tableau CSP Péage MISE À JOUR:
    | Régions | Postes de Péage | Stock début | Ventes déclarées | Nbre jours |
    | Montant quittancé | Nbre jours | Écart |
    | Montant ACCT | Écart 2 | Date dern. quitt. | Dernières quittances |
    """
    user = request.user

    # ========== VÉRIFICATION DES PERMISSIONS ==========
    if not has_permission(user, 'peut_comptabiliser_quittances_peage'):
        log_user_action(
            user=user,
            action="ACCES_REFUSE",
            description="Tentative de génération CSP Péage",
            details=f"Permission peut_comptabiliser_quittances_peage manquante | "
                   f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
                   f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            niveau="WARNING"
        )
        log_acces_refuse(user, "generer_csp_peage", "Permission peut_comptabiliser_quittances_peage manquante")
        messages.error(request, "Vous n'avez pas la permission d'accéder au Contrôle Sur Pièce Péage.")
        return redirect('common:dashboard')

    # ========== RÉCUPÉRATION DES PARAMÈTRES ==========
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    poste_id = request.GET.get('poste_id')

    if not date_debut_str or not date_fin_str:
        messages.error(request, "Les dates de début et de fin sont obligatoires.")
        return redirect('inventaire:selection_csp_peage')

    try:
        date_debut = date.fromisoformat(date_debut_str)
        date_fin = date.fromisoformat(date_fin_str)
    except ValueError:
        messages.error(request, "Format de date invalide.")
        return redirect('inventaire:selection_csp_peage')

    # ========== DÉTERMINATION DES POSTES ACCESSIBLES ==========
    acces_tous_postes = user_has_acces_tous_postes(user)

    if acces_tous_postes:
        if poste_id:
            postes = Poste.objects.filter(id=poste_id, is_active=True, type='peage').select_related('region')
        else:
            postes = Poste.objects.filter(is_active=True, type='peage').select_related('region').order_by('region__nom', 'nom')
    else:
        if user.poste_affectation and user.poste_affectation.type == 'peage':
            postes = Poste.objects.filter(id=user.poste_affectation.id).select_related('region')
        else:
            postes = Poste.objects.none()
            messages.warning(request, "Vous n'êtes pas affecté à un poste de péage.")

    # Log de l'accès
    log_user_action(
        user=user,
        action="GENERATION_CSP_PEAGE",
        description=f"Génération rapport CSP Péage",
        details=f"Période: {date_debut_str} au {date_fin_str} | "
               f"Nombre de postes: {postes.count()} | "
               f"Poste filtre: {poste_id or 'Tous'} | "
               f"Accès tous postes: {acces_tous_postes} | "
               f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
        niveau="INFO"
    )

    logger.info(f"[CSP_PEAGE] {user.username} génère le rapport CSP Péage "
                f"({date_debut} - {date_fin}) pour {postes.count()} poste(s)")

    # ========== CALCUL DES DONNÉES PAR POSTE ==========
    nombre_jours_periode = (date_fin - date_debut).days + 1
    resultats = []
    resultats_par_region = {}

    # Totaux globaux - MISE À JOUR avec nouvelles colonnes
    totaux = {
        'stock_debut': Decimal('0'),
        'ventes_declarees': Decimal('0'),
        'jours_declares': 0,
        'montant_quittance': Decimal('0'),
        'jours_quittances': 0,
        'ecart': Decimal('0'),
        'montant_dernieres_quittances': Decimal('0'),
        'nombre_postes': 0,
        # ===== NOUVELLES COLONNES =====
        'montant_historique': Decimal('0'),
        'ecart_historique': Decimal('0'),
    }

    for poste in postes:
        donnees = calculer_donnees_csp_poste_peage(poste, date_debut, date_fin)
        resultats.append(donnees)

        # Regroupement par région
        region_nom = donnees['region']
        if region_nom not in resultats_par_region:
            resultats_par_region[region_nom] = {
                'region': region_nom,
                'region_id': donnees['region_id'],
                'postes': [],
                'totaux': {
                    'stock_debut': Decimal('0'),
                    'ventes_declarees': Decimal('0'),
                    'jours_declares': 0,
                    'montant_quittance': Decimal('0'),
                    'jours_quittances': 0,
                    'ecart': Decimal('0'),
                    'montant_dernieres_quittances': Decimal('0'),
                    'nombre_postes': 0,
                    # ===== NOUVELLES COLONNES =====
                    'montant_historique': Decimal('0'),
                    'ecart_historique': Decimal('0'),
                }
            }

        resultats_par_region[region_nom]['postes'].append(donnees)

        # Mise à jour des totaux par région
        r = resultats_par_region[region_nom]['totaux']
        r['stock_debut'] += donnees['stock_debut']
        r['ventes_declarees'] += donnees['ventes_declarees']
        r['jours_declares'] += donnees['jours_declares']
        r['montant_quittance'] += donnees['montant_quittance']
        r['jours_quittances'] += donnees['jours_quittances']
        r['ecart'] += donnees['ecart']
        r['montant_dernieres_quittances'] += donnees['montant_dernieres_quittances']
        r['nombre_postes'] += 1
        # ===== NOUVELLES COLONNES =====
        r['montant_historique'] += donnees['montant_historique']
        r['ecart_historique'] += donnees['ecart_historique']

        # Mise à jour des totaux globaux
        totaux['stock_debut'] += donnees['stock_debut']
        totaux['ventes_declarees'] += donnees['ventes_declarees']
        totaux['jours_declares'] += donnees['jours_declares']
        totaux['montant_quittance'] += donnees['montant_quittance']
        totaux['jours_quittances'] += donnees['jours_quittances']
        totaux['ecart'] += donnees['ecart']
        totaux['montant_dernieres_quittances'] += donnees['montant_dernieres_quittances']
        totaux['nombre_postes'] += 1
        # ===== NOUVELLES COLONNES =====
        totaux['montant_historique'] += donnees['montant_historique']
        totaux['ecart_historique'] += donnees['ecart_historique']

    # Trier les régions par ordre alphabétique
    resultats_par_region = dict(sorted(resultats_par_region.items()))

    # ========== CONTEXTE ==========
    context = {
        'resultats': resultats,
        'resultats_par_region': resultats_par_region,
        'totaux': totaux,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'date_debut_str': date_debut_str,
        'date_fin_str': date_fin_str,
        'nombre_jours_periode': nombre_jours_periode,
        'acces_tous_postes': acces_tous_postes,
        'poste_filtre': poste_id,
        'title': f"CSP Péage - {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"
    }

    return render(request, 'inventaire/csp_peage.html', context)

# ===================================================================
# VUE SÉLECTION CSP PESAGE
# ===================================================================

@login_required
def selection_csp_pesage(request):
    """
    Vue de sélection de la période pour le CSP Pesage.
    Permet de choisir les dates de début et de fin avant de générer le rapport.

    PERMISSIONS:
    - peut_comptabiliser_quittances_pesage: Requis pour accéder à cette vue

    ACCÈS AUX STATIONS:
    - Utilisateurs avec acces_tous_postes: voient toutes les stations de pesage
    - Autres: voient uniquement leur station d'affectation
    """
    user = request.user

    # ========== VÉRIFICATION DES PERMISSIONS ==========
    if not has_permission(user, 'peut_comptabiliser_quittances_pesage'):
        log_user_action(
            user=user,
            action="ACCES_REFUSE",
            description="Tentative d'accès à la sélection CSP Pesage",
            details=f"Permission peut_comptabiliser_quittances_pesage manquante | "
                   f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
                   f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
            niveau="WARNING"
        )
        log_acces_refuse(user, "selection_csp_pesage", "Permission peut_comptabiliser_quittances_pesage manquante")
        messages.error(request, "Vous n'avez pas la permission d'accéder au Contrôle Sur Pièce Pesage.")
        return redirect('common:dashboard')

    # Log de l'accès à la vue
    log_user_action(
        user=user,
        action="ACCES_CSP_PESAGE_SELECTION",
        description=f"Accès à la page de sélection CSP Pesage",
        details=f"Utilisateur: {user.nom_complet} | "
               f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
               f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
        niveau="INFO"
    )

    logger.info(f"[CSP_PESAGE] Utilisateur {user.username} ({getattr(user, 'habilitation', 'N/A')}) "
                f"accède à la sélection CSP Pesage")

    # ========== DÉTERMINATION DES STATIONS ACCESSIBLES ==========
    acces_tous_postes = user_has_acces_tous_postes(user)

    if acces_tous_postes:
        stations = Poste.objects.filter(is_active=True, type='pesage').select_related('region').order_by('region__nom', 'nom')
    else:
        if user.poste_affectation and user.poste_affectation.type == 'pesage':
            stations = Poste.objects.filter(id=user.poste_affectation.id).select_related('region')
        else:
            stations = Poste.objects.none()

    # Dates par défaut suggérées
    today = date.today()

    premier_jour_mois_actuel = today.replace(day=1)
    dernier_jour_mois_precedent = premier_jour_mois_actuel - timedelta(days=1)
    premier_jour_mois_precedent = dernier_jour_mois_precedent.replace(day=1)

    date_debut_suggestion = premier_jour_mois_precedent
    date_fin_suggestion = dernier_jour_mois_precedent

    if request.method == 'POST':
        date_debut_str = request.POST.get('date_debut')
        date_fin_str = request.POST.get('date_fin')
        station_id = request.POST.get('station_id')

        if not date_debut_str or not date_fin_str:
            messages.error(request, "Veuillez sélectionner une date de début et une date de fin.")
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
                    log_user_action(
                        user=user,
                        action="SELECTION_PERIODE_CSP_PESAGE",
                        description=f"Sélection période CSP Pesage",
                        details=f"Période: {date_debut_str} au {date_fin_str} | "
                               f"Station filtre: {station_id or 'Toutes'} | "
                               f"IP: {request.META.get('REMOTE_ADDR', 'N/A')}",
                        niveau="INFO"
                    )

                    url = f"?date_debut={date_debut_str}&date_fin={date_fin_str}"
                    if station_id:
                        url += f"&station_id={station_id}"
                    return redirect(f"{request.path.replace('selection', 'generer')}{url}")

            except ValueError:
                messages.error(request, "Format de date invalide.")

    context = {
        'stations': stations,
        'date_debut_suggestion': date_debut_suggestion,
        'date_fin_suggestion': date_fin_suggestion,
        'date_max': today,
        'acces_tous_postes': acces_tous_postes,
        'title': "Contrôle Sur Pièce - Pesage"
    }

    return render(request, 'pesage/selection_csp_pesage.html', context)


# ===================================================================
# VUE GÉNÉRATION CSP PESAGE
# ===================================================================
@login_required
def generer_csp_pesage(request):
    """
    Vue pour générer le rapport CSP Pesage.

    STRUCTURE DU TABLEAU (12 colonnes):
    | Régions | Stations | Nbre Pesées | Nbre Infractions | Amendes émises (A) |
    | Amendes recouvrées (B) | RAR (A-B) | Montant quittancé | ECART1 |
    | Historique ACCT | ECART2 | Date dern. quittance |
    """
    user = request.user

    # Vérification des permissions
    if not has_permission(user, 'peut_comptabiliser_quittances_pesage'):
        log_user_action(
            user=user,
            action="ACCES_REFUSE",
            description="Tentative de génération CSP Pesage",
            details="Permission peut_comptabiliser_quittances_pesage manquante",
            niveau="warning"
        )
        log_acces_refuse(user, "generer_csp_pesage", "Permission manquante")
        messages.error(request, "Vous n'avez pas la permission d'accéder au Contrôle Sur Pièce Pesage.")
        return redirect('common:dashboard')

    # Récupération des paramètres
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    station_id = request.GET.get('station_id')

    if not date_debut_str or not date_fin_str:
        messages.error(request, "Les dates de début et de fin sont obligatoires.")
        return redirect('inventaire:selection_csp_pesage')

    try:
        date_debut = date.fromisoformat(date_debut_str)
        date_fin = date.fromisoformat(date_fin_str)
    except ValueError:
        messages.error(request, "Format de date invalide.")
        return redirect('inventaire:selection_csp_pesage')

    # Détermination des stations accessibles
    acces_tous_postes = user_has_acces_tous_postes(user)

    if acces_tous_postes:
        if station_id:
            stations = Poste.objects.filter(id=station_id, is_active=True, type='pesage').select_related('region')
        else:
            stations = Poste.objects.filter(is_active=True, type='pesage').select_related('region').order_by('region__nom', 'nom')
    else:
        if user.poste_affectation and user.poste_affectation.type == 'pesage':
            stations = Poste.objects.filter(id=user.poste_affectation.id).select_related('region')
        else:
            stations = Poste.objects.none()
            messages.warning(request, "Vous n'êtes pas affecté à une station de pesage.")

    # Log de l'accès
    log_user_action(
        user=user,
        action="GENERATION_CSP_PESAGE",
        description="Génération rapport CSP Pesage",
        details=f"Période: {date_debut_str} au {date_fin_str} | Stations: {stations.count()}",
        niveau="info"
    )

    # Calcul des données par station
    nombre_jours_periode = (date_fin - date_debut).days + 1
    resultats = []
    resultats_par_region = {}

    for station in stations:
        donnees = calculer_donnees_csp_poste_pesage(station, date_debut, date_fin)
        resultats.append(donnees)

        # Regroupement par région
        region_nom = donnees['region']
        if region_nom not in resultats_par_region:
            resultats_par_region[region_nom] = {
                'region': region_nom,
                'region_id': donnees['region_id'],
                'stations': [],
                'totaux': {
                    'nbre_pesees': 0,
                    'nbre_infractions': 0,
                    'total_amendes_emises': Decimal('0'),
                    'amendes_recouvrees': Decimal('0'),
                    'rar_mois': Decimal('0'),
                    'montant_quittance': Decimal('0'),
                    'ecart1': Decimal('0'),
                    'historique_acct': Decimal('0'),
                    'ecart2': Decimal('0'),
                    'nombre_stations': 0,
                    'stations_avec_historique': 0,
                }
            }

        resultats_par_region[region_nom]['stations'].append(donnees)

        # Mise à jour des totaux par région
        r = resultats_par_region[region_nom]['totaux']
        r['nbre_pesees'] += donnees['nbre_pesees']
        r['nbre_infractions'] += donnees['nbre_infractions']
        r['total_amendes_emises'] += donnees['total_amendes_emises']
        r['amendes_recouvrees'] += donnees['amendes_recouvrees']
        r['rar_mois'] += donnees['rar_mois']
        r['montant_quittance'] += donnees['montant_quittance']
        r['ecart1'] += donnees['ecart1']
        r['historique_acct'] += donnees['historique_acct']
        r['ecart2'] += donnees['ecart2']
        r['nombre_stations'] += 1
        if donnees['has_historique']:
            r['stations_avec_historique'] += 1

    # Calcul des totaux globaux
    totaux = calculer_totaux_csp_pesage(resultats)

    # Trier les régions par ordre alphabétique
    resultats_par_region = dict(sorted(resultats_par_region.items()))

    # Nom du mois pour le titre
    mois_noms = {
        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
        5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
        9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
    }
    mois_nom = mois_noms.get(date_fin.month, str(date_fin.month))

    context = {
        'resultats': resultats,
        'resultats_par_region': resultats_par_region,
        'totaux': totaux,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'date_debut_str': date_debut_str,
        'date_fin_str': date_fin_str,
        'nombre_jours_periode': nombre_jours_periode,
        'mois_nom': mois_nom,
        'annee': date_fin.year,
        'acces_tous_postes': acces_tous_postes,
        'station_filtre': station_id,
        'title': f"CSP Pesage - {mois_nom} {date_fin.year}"
    }

    return render(request, 'pesage/csp_pesage.html', context)

