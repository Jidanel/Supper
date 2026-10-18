# inventaire/views_rapports.py
# VERSION 3 - Mise à jour avec permissions granulaires
# ===================================================================
#
# MODIFICATIONS APPORTÉES:
# - Remplacement de is_admin/is_chef_poste par permissions granulaires
# - Utilisation de has_permission, get_postes_peage_accessibles, check_poste_access
# - Ajout de logs manuels détaillés via log_user_action
# - Les variables de contexte sont identiques à la version précédente
#
# PERMISSIONS UTILISÉES:
# - peut_voir_compte_emploi: Accès au compte d'emploi
# - peut_parametrage_global: Accès au paramétrage global
# ===================================================================

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q
from django.http import HttpResponse
from datetime import date, timedelta, datetime, time
from decimal import Decimal
import logging

from accounts.models import Poste
from inventaire.models import (
    SerieTicket, StockEvent, HistoriqueStock, CouleurTicket,
    GestionStock
)
from inventaire.models_config import ConfigurationGlobale

# Import des permissions granulaires
from common.permissions import (
    has_permission,
    get_postes_peage_accessibles,
    check_poste_access,
    user_has_acces_tous_postes,
    log_acces_refuse,
)

# Import de la fonction de log manuelle
from common.utils import log_user_action

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, Image, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

import os
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('supper')


# ===================================================================
# SÉLECTION DU COMPTE D'EMPLOI
# ===================================================================
# AVANT: request.user.is_admin or request.user.is_chef_poste
# APRÈS: has_permission(request.user, 'peut_voir_compte_emploi')
#
# AVANT postes: is_admin → tous, sinon [poste_affectation]
# APRÈS postes: get_postes_peage_accessibles(request.user)
# ===================================================================

@login_required
def selection_compte_emploi(request):
    """
    Permet de choisir entre aperçu et génération directe PDF

    PERMISSIONS:
    - peut_voir_compte_emploi: Requis pour accéder à cette vue

    ACCÈS AUX POSTES:
    - Utilisateurs avec acces_tous_postes: voient tous les postes de péage
    - Autres: voient uniquement leur poste d'affectation
    """
    user = request.user

    # ========== VÉRIFICATION DES PERMISSIONS ==========
    if not has_permission(user, 'peut_voir_compte_emploi'):
        # Log de l'accès refusé
        log_user_action(
            user=user,
            action="ACCES_REFUSE",
            description="Tentative d'accès à la sélection du compte d'emploi",
            details="Permission peut_voir_compte_emploi manquante",
            niveau="WARNING"
        )
        log_acces_refuse(user, "selection_compte_emploi", "Permission peut_voir_compte_emploi manquante")
        messages.error(request, "Vous n'avez pas la permission d'accéder au compte d'emploi.")
        return redirect('common:dashboard')

    # Log de l'accès à la vue
    logger.info(f"[COMPTE_EMPLOI] Utilisateur {user.username} ({user.get_habilitation_display()}) accède à la sélection du compte d'emploi")

    # ========== DÉTERMINATION DES POSTES ACCESSIBLES ==========
    # Utilise get_postes_peage_accessibles qui gère automatiquement:
    # - Accès tous postes pour habilitations multi-postes
    # - Poste d'affectation uniquement pour les autres
    postes = get_postes_peage_accessibles(user)

    logger.debug(f"[COMPTE_EMPLOI] {user.username}: {postes.count()} poste(s) de péage accessible(s)")

    # Dates par défaut suggérées
    today = date.today()

    # Suggestion : début du mois précédent → fin du mois précédent
    premier_jour_mois_actuel = today.replace(day=1)
    dernier_jour_mois_precedent = premier_jour_mois_actuel - timedelta(days=1)
    premier_jour_mois_precedent = dernier_jour_mois_precedent.replace(day=1)

    date_debut_suggestion = premier_jour_mois_precedent
    date_fin_suggestion = dernier_jour_mois_precedent

    if request.method == 'POST':
        poste_id = request.POST.get('poste_id')
        date_debut_str = request.POST.get('date_debut')
        date_fin_str = request.POST.get('date_fin')
        action = request.POST.get('action', 'apercu')

        # Validations
        if not poste_id:
            messages.error(request, "Veuillez sélectionner un poste")
        elif not date_debut_str or not date_fin_str:
            messages.error(request, "Veuillez sélectionner une date de début et une date de fin")
        else:
            try:
                date_debut = date.fromisoformat(date_debut_str)
                date_fin = date.fromisoformat(date_fin_str)

                if date_debut > date_fin:
                    messages.error(request, "La date de début doit être antérieure à la date de fin")
                elif date_fin > today:
                    messages.error(request, "La date de fin ne peut pas être dans le futur")
                elif (date_fin - date_debut).days > 365:
                    messages.error(request, "La période ne peut pas dépasser 1 an")
                else:
                    # Vérifier que l'utilisateur a accès au poste sélectionné
                    try:
                        poste_selectionne = Poste.objects.get(id=poste_id)
                        if not check_poste_access(user, poste_selectionne):
                            log_user_action(
                                user=user,
                                action="ACCES_REFUSE",
                                description=f"Tentative d'accès au compte d'emploi du poste {poste_selectionne.nom}",
                                details="Poste non autorisé pour cet utilisateur",
                                niveau="WARNING"
                            )
                            messages.error(request, "Vous n'avez pas accès à ce poste.")
                            return redirect('inventaire:selection_compte_emploi')
                    except Poste.DoesNotExist:
                        messages.error(request, "Poste non trouvé")
                        return redirect('inventaire:selection_compte_emploi')

                    # Log de la sélection
                    log_user_action(
                        user=user,
                        action="SELECTION_COMPTE_EMPLOI",
                        description=f"Sélection compte d'emploi - Poste: {poste_selectionne.nom}",
                        details=f"Période: {date_debut_str} au {date_fin_str}, Action: {action}",
                        niveau="INFO"
                    )

                    if action == 'apercu':
                        return redirect('inventaire:apercu_compte_emploi',
                                      poste_id=poste_id,
                                      date_debut=date_debut_str,
                                      date_fin=date_fin_str)
                    else:
                        return redirect('inventaire:generer_compte_emploi',
                                      poste_id=poste_id,
                                      date_debut=date_debut_str,
                                      date_fin=date_fin_str)

            except ValueError:
                messages.error(request, "Format de date invalide")

    # ========== CONTEXTE (identique à la version précédente) ==========
    context = {
        'postes': postes,
        'date_debut_suggestion': date_debut_suggestion,
        'date_fin_suggestion': date_fin_suggestion,
        'date_max': today,
        'title': "Compte d'Emploi des Tickets"
    }

    return render(request, 'inventaire/selection_compte_emploi.html', context)


def calculer_stock_event_sourcing(poste, date_reference):
    """
    VERSION CORRIGÉE - Utilise HistoriqueStock comme source de vérité.

    POURQUOI CE CHANGEMENT:
    Les StockEvent peuvent être incomplets (événements manquants avant
    la mise en place de l'Event Sourcing). HistoriqueStock contient
    l'historique complet de tous les mouvements.

    LOGIQUE:
    Stock = Somme(CREDITS) - Somme(DEBITS) depuis HistoriqueStock

    Args:
        poste: Instance du modèle Poste
        date_reference: date ou datetime - Date pour le calcul du stock

    Returns:
        tuple: (valeur_monetaire: Decimal, nombre_tickets: int)
    """
    try:
        from inventaire.models import HistoriqueStock
    except ImportError:
        from .models import HistoriqueStock

    # =========================================================
    # Convertir la date en datetime pour la requête
    # =========================================================
    if isinstance(date_reference, datetime):
        datetime_target = date_reference
        if timezone.is_naive(datetime_target):
            datetime_target = timezone.make_aware(datetime_target)
    elif isinstance(date_reference, date):
        # Fin de journée pour inclure tous les mouvements du jour
        datetime_target = timezone.make_aware(
            datetime.combine(date_reference, time.max)
        )
    else:
        logger.error(f"[COMPTE_EMPLOI] Type de date invalide: {type(date_reference)}")
        return Decimal('0'), 0

    # =========================================================
    # Calcul via HistoriqueStock (source de vérité)
    # =========================================================
    try:
        historiques = HistoriqueStock.objects.filter(
            poste=poste,
            date_mouvement__lte=datetime_target
        )

        # Somme des crédits
        credits = historiques.filter(type_mouvement='CREDIT').aggregate(
            total=Sum('montant')
        )['total'] or Decimal('0')

        # Somme des débits
        debits = historiques.filter(type_mouvement='DEBIT').aggregate(
            total=Sum('montant')
        )['total'] or Decimal('0')

        # Stock = Crédits - Débits
        valeur = credits - debits
        valeur = max(Decimal('0'), valeur)  # Pas de stock négatif

        # Calculer le nombre de tickets (500 FCFA par ticket)
        tickets = int(valeur / 500)

        # Nombre d'enregistrements pour info
        nb_historiques = historiques.count()

        # Log pour traçabilité
        if isinstance(date_reference, datetime):
            date_str = date_reference.strftime('%d/%m/%Y %H:%M')
        else:
            date_str = date_reference.strftime('%d/%m/%Y')

        logger.info(
            f"[COMPTE_EMPLOI] Stock via HistoriqueStock | "
            f"Poste: {poste.nom} | Date: {date_str} | "
            f"Stock: {valeur:,.0f} FCFA ({tickets} tickets) | "
            f"Crédits: {credits:,.0f} | Débits: {debits:,.0f} | "
            f"{nb_historiques} mouvement(s)"
        )

        return valeur, tickets

    except Exception as e:
        logger.error(
            f"[COMPTE_EMPLOI] Erreur calcul stock | "
            f"Poste: {poste.nom} | Date: {date_reference} | "
            f"Erreur: {str(e)}",
            exc_info=True
        )
        return Decimal('0'), 0


# ===================================================================
# FONCTION SIMPLIFIÉE calculer_stock_unifie - À REMPLACER AUSSI
# ===================================================================
# Cette fonction doit aussi utiliser HistoriqueStock comme priorité

def calculer_stock_unifie(poste, date_reference, source_prioritaire='historique'):
    """
    VERSION SIMPLIFIÉE - Utilise HistoriqueStock par défaut.

    Args:
        poste: Instance du modèle Poste
        date_reference: date ou datetime
        source_prioritaire: 'historique' (défaut), 'event_sourcing', ou 'auto'

    Returns:
        dict avec valeur, tickets, source_utilisee, coherent, details
    """
    try:
        from inventaire.models import StockEvent, HistoriqueStock
    except ImportError:
        from .models import StockEvent, HistoriqueStock

    # Convertir la date
    if isinstance(date_reference, datetime):
        datetime_target = date_reference
        if timezone.is_naive(datetime_target):
            datetime_target = timezone.make_aware(datetime_target)
    elif isinstance(date_reference, date):
        datetime_target = timezone.make_aware(
            datetime.combine(date_reference, time.max)
        )
    else:
        return {
            'valeur': Decimal('0'),
            'tickets': 0,
            'source_utilisee': 'erreur',
            'coherent': False,
            'details': {'erreur': f'Type de date invalide: {type(date_reference)}'}
        }

    # =========================================================
    # Calcul via HistoriqueStock (source prioritaire)
    # =========================================================
    historiques = HistoriqueStock.objects.filter(
        poste=poste,
        date_mouvement__lte=datetime_target
    )

    credits = historiques.filter(type_mouvement='CREDIT').aggregate(
        total=Sum('montant')
    )['total'] or Decimal('0')

    debits = historiques.filter(type_mouvement='DEBIT').aggregate(
        total=Sum('montant')
    )['total'] or Decimal('0')

    valeur_hist = max(Decimal('0'), credits - debits)
    tickets_hist = int(valeur_hist / 500)
    nb_historiques = historiques.count()

    # =========================================================
    # Calcul via Event Sourcing (pour comparaison)
    # =========================================================
    events = StockEvent.objects.filter(
        poste=poste,
        event_datetime__lte=datetime_target,
        is_cancelled=False
    )

    totaux_es = events.aggregate(
        total_valeur=Sum('montant_variation'),
        total_tickets=Sum('nombre_tickets_variation')
    )

    valeur_es = max(Decimal('0'), totaux_es['total_valeur'] or Decimal('0'))
    tickets_es = max(0, totaux_es['total_tickets'] or 0)
    nb_events = events.count()

    # =========================================================
    # Analyse de cohérence
    # =========================================================
    ecart = abs(valeur_es - valeur_hist)
    seuil = Decimal('1000')
    coherent = ecart <= seuil

    # =========================================================
    # DÉCISION: Toujours utiliser HistoriqueStock
    # =========================================================
    # Car il contient l'historique complet des mouvements
    valeur_finale = valeur_hist
    tickets_final = tickets_hist
    source_choisie = 'historique'

    # Log si incohérence
    if not coherent:
        logger.warning(
            f"[STOCK_UNIFIE] Incohérence pour {poste.nom} au {date_reference}:\n"
            f"  - Event Sourcing: {valeur_es:,.0f} FCFA ({nb_events} events)\n"
            f"  - HistoriqueStock: {valeur_hist:,.0f} FCFA ({nb_historiques} hist)\n"
            f"  - Écart: {ecart:,.0f} FCFA\n"
            f"  - Source choisie: {source_choisie} (prioritaire)\n"
            f"  - Valeur finale: {valeur_finale:,.0f} FCFA"
        )
    else:
        logger.debug(
            f"[STOCK_UNIFIE] Stock cohérent pour {poste.nom}: "
            f"{valeur_finale:,.0f} FCFA (source: {source_choisie})"
        )

    return {
        'valeur': valeur_finale,
        'tickets': tickets_final,
        'source_utilisee': source_choisie,
        'coherent': coherent,
        'details': {
            'event_sourcing': {
                'valeur': valeur_es,
                'tickets': tickets_es,
                'nb_events': nb_events
            },
            'historique': {
                'valeur': valeur_hist,
                'tickets': tickets_hist,
                'nb_historiques': nb_historiques,
                'credits': credits,
                'debits': debits
            },
            'ecart': ecart
        }
    }




def calculer_donnees_compte_emploi_v2(poste, date_debut, date_fin):
    """
    VERSION 4 - Calcul du compte d'emploi avec traçabilité par recharge.

    PRINCIPE:
    Chaque SerieTicket a un champ historique_source (FK → HistoriqueStock)
    qui indique la recharge qui l'a introduite dans le poste.

    Pour répartir les ventes entre les lignes du compte d'emploi:
    - On récupère les HistoriqueStock CREDIT de la période
    - Pour chaque SerieTicket vendue, on compare son historique_source_id
      avec les IDs des historiques de la période
    - Si l'ID match un approv imprimerie → vente attribuée à cette ligne
    - Si l'ID match un transfert reçu → vente attribuée à cette ligne
    - Sinon (historique antérieur ou NULL) → stock de début

    Stock de début = stock fin de la veille (via calculer_stock_debut_periode du CSP)

    NOTE: Les noms de variables dans le dict retourné sont IDENTIQUES
    à la version précédente pour ne pas casser les templates.

    Args:
        poste: Instance du modèle Poste
        date_debut: date - Date de début de la période
        date_fin: date - Date de fin de la période

    Returns:
        dict: Données complètes du compte d'emploi
    """
    from collections import defaultdict
    from django.db.models import Sum, Q
    from decimal import Decimal
    from datetime import timedelta
    from django.utils import timezone as tz

    from inventaire.models import (
        SerieTicket, StockEvent, HistoriqueStock, CouleurTicket
    )
    from inventaire.views_csp import calculer_stock_debut_periode

    logger.info(f"{'=' * 60}")
    logger.info(f"CALCUL COMPTE D'EMPLOI V4 - {poste.nom}")
    logger.info(f"Période: {date_debut} → {date_fin}")

    # ===================================================================
    # INITIALISATION (mêmes noms de variables que V3)
    # ===================================================================
    donnees = {
        'stock_debut': {
            'stocks': Decimal('0'),
            'ventes': Decimal('0'),
            'stock_final': Decimal('0'),
            'stocks_qte': 0,
            'ventes_qte': 0,
            'source': '',
            'coherent': True
        },
        'approv_imprimerie': {
            'stocks': Decimal('0'),
            'ventes': Decimal('0'),
            'stock_final': Decimal('0'),
            'stocks_qte': 0,
            'ventes_qte': 0,
            'details': [],
        },
        'reapprov_recu': {
            'stocks': Decimal('0'),
            'ventes': Decimal('0'),
            'stock_final': Decimal('0'),
            'stocks_qte': 0,
            'ventes_qte': 0,
            'details': [],
        },
        'reapprov_cede': {
            'stocks': Decimal('0'),
            'ventes': Decimal('0'),
            'stock_final': Decimal('0'),
            'stocks_qte': 0,
            'ventes_qte': 0,
            'details': [],
        },
        'total': {
            'stocks': Decimal('0'),
            'ventes': Decimal('0'),
            'stock_final': Decimal('0'),
        },
        'ventes_par_semaine': {},
        'stock_final_calcule': Decimal('0'),
        'stock_final_qte': 0,
        'diagnostic': {
            'coherent': True,
            'alertes': [],
            'sources_utilisees': {}
        }
    }

    # ===================================================================
    # 1. STOCK DE DÉBUT = stock fin de la veille (via StockEvent/CSP)
    # ===================================================================
    stock_debut_valeur, stock_debut_tickets = calculer_stock_debut_periode(poste, date_debut)

    donnees['stock_debut']['stocks'] = stock_debut_valeur
    donnees['stock_debut']['stocks_qte'] = stock_debut_tickets
    donnees['stock_debut']['source'] = 'event_sourcing_csp'
    donnees['stock_debut']['coherent'] = True
    donnees['diagnostic']['sources_utilisees']['stock_debut'] = 'event_sourcing_csp'

    logger.info(
        f"Stock de début (veille du {date_debut}): "
        f"{stock_debut_valeur:,.0f} FCFA ({stock_debut_tickets} tickets)"
    )

    # ===================================================================
    # 2. APPROVISIONNEMENTS IMPRIMERIE NATIONALE (dans la période)
    #    Inclut imprimerie_nationale ET regularisation car dans le compte
    #    d'emploi les deux sont sur la même ligne "Approv. Imprimerie"
    # ===================================================================
    historiques_imprimerie = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='CREDIT',
        type_stock__in=['imprimerie_nationale', 'imprimerie', 'regularisation'],
        date_mouvement__date__gte=date_debut,
        date_mouvement__date__lte=date_fin
    ).select_related(
        'couleur_principale', 'effectue_par'
    ).order_by('date_mouvement')

    # Collecter les IDs pour la répartition des ventes
    ids_historiques_imprimerie = set()

    for hist in historiques_imprimerie:
        montant = hist.montant or Decimal('0')
        nb_tickets = hist.nombre_tickets or 0

        donnees['approv_imprimerie']['stocks'] += montant
        donnees['approv_imprimerie']['stocks_qte'] += nb_tickets
        ids_historiques_imprimerie.add(hist.id)

        observation = _construire_observation_approvisionnement(hist)
        series = _extraire_series_depuis_serie_ticket(hist)

        donnees['approv_imprimerie']['details'].append({
            'date': hist.date_mouvement,
            'observation': observation,
            'montant': montant,
            'nombre_tickets': nb_tickets,
            'series': series,
            'historique_id': hist.id
        })

    logger.info(
        f"Approv Imprimerie: {donnees['approv_imprimerie']['stocks']:,.0f} FCFA "
        f"({len(ids_historiques_imprimerie)} recharge(s))"
    )

    # ===================================================================
    # 3. TRANSFERTS REÇUS (dans la période)
    # ===================================================================
    historiques_recus = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='CREDIT',
        poste_origine__isnull=False,
        date_mouvement__date__gte=date_debut,
        date_mouvement__date__lte=date_fin
    ).select_related(
        'poste_origine', 'couleur_principale', 'effectue_par'
    ).order_by('date_mouvement')

    ids_historiques_recus = set()

    for hist in historiques_recus:
        montant = hist.montant or Decimal('0')
        nb_tickets = hist.nombre_tickets or 0

        donnees['reapprov_recu']['stocks'] += montant
        donnees['reapprov_recu']['stocks_qte'] += nb_tickets
        ids_historiques_recus.add(hist.id)

        observation = _construire_observation_transfert_recu(hist)
        series = _extraire_series_depuis_serie_ticket(hist)

        donnees['reapprov_recu']['details'].append({
            'date': hist.date_mouvement,
            'observation': observation,
            'montant': montant,
            'nombre_tickets': nb_tickets,
            'poste_origine': hist.poste_origine,
            'numero_bordereau': hist.numero_bordereau,
            'series': series,
            'historique_id': hist.id
        })

    logger.info(
        f"Transferts reçus: {donnees['reapprov_recu']['stocks']:,.0f} FCFA "
        f"({len(ids_historiques_recus)} transfert(s))"
    )

    # ===================================================================
    # 4. TRANSFERTS CÉDÉS (dans la période)
    # ===================================================================
    historiques_cedes = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='DEBIT',
        poste_destination__isnull=False,
        date_mouvement__date__gte=date_debut,
        date_mouvement__date__lte=date_fin
    ).select_related(
        'poste_destination', 'couleur_principale', 'effectue_par'
    ).order_by('date_mouvement')

    for hist in historiques_cedes:
        montant = hist.montant or Decimal('0')
        nb_tickets = hist.nombre_tickets or 0

        donnees['reapprov_cede']['stocks'] -= montant
        donnees['reapprov_cede']['stocks_qte'] -= nb_tickets

        observation = _construire_observation_transfert_cede(hist)
        series = _extraire_series_depuis_serie_ticket(hist)

        donnees['reapprov_cede']['details'].append({
            'date': hist.date_mouvement,
            'observation': observation,
            'montant': -montant,
            'nombre_tickets': -nb_tickets,
            'poste_destination': hist.poste_destination,
            'numero_bordereau': hist.numero_bordereau,
            'series': series,
            'historique_id': hist.id
        })

    logger.info(f"Transferts cédés: {donnees['reapprov_cede']['stocks']:,.0f} FCFA")

    # ===================================================================
    # 5. VENTES - TRAÇABILITÉ PAR RECHARGE D'ORIGINE
    #
    # Pour chaque SerieTicket vendue dans la période, on regarde son
    # historique_source_id pour savoir de quelle recharge elle vient:
    #
    #   - historique_source_id IN ids_historiques_imprimerie
    #     → vente provient d'un approv imprimerie de cette période
    #
    #   - historique_source_id IN ids_historiques_recus
    #     → vente provient d'un transfert reçu de cette période
    #
    #   - historique_source_id absent des deux (NULL ou antérieur)
    #     → le ticket existait avant la période → stock de début
    # ===================================================================
    logger.info(f"{'=' * 40}")
    logger.info(f"RÉCUPÉRATION DES VENTES (SerieTicket + historique_source)")

    series_vendues = SerieTicket.objects.filter(
        poste=poste,
        statut='vendu',
        date_utilisation__gte=date_debut,
        date_utilisation__lte=date_fin
    ).select_related(
        'couleur', 'reference_recette', 'historique_source'
    ).order_by('date_utilisation', 'couleur__libelle_affichage', 'numero_premier')

    total_ventes_valeur = Decimal('0')
    total_ventes_qte = 0
    ventes_par_semaine = {}

    # Compteurs de répartition réelle par origine
    ventes_stock_debut_valeur = Decimal('0')
    ventes_stock_debut_qte = 0
    ventes_approv_imprimerie_valeur = Decimal('0')
    ventes_approv_imprimerie_qte = 0
    ventes_reapprov_recu_valeur = Decimal('0')
    ventes_reapprov_recu_qte = 0

    for serie in series_vendues:
        montant = serie.valeur_monetaire or Decimal('0')
        nb_tickets = serie.nombre_tickets or 0

        total_ventes_valeur += montant
        total_ventes_qte += nb_tickets

        # =========================================================
        # RÉPARTITION: identifier l'origine via historique_source
        # =========================================================
        hist_source_id = serie.historique_source_id

        if hist_source_id and hist_source_id in ids_historiques_imprimerie:
            # Ticket provient d'un approv imprimerie de CETTE période
            ventes_approv_imprimerie_valeur += montant
            ventes_approv_imprimerie_qte += nb_tickets
        elif hist_source_id and hist_source_id in ids_historiques_recus:
            # Ticket provient d'un transfert reçu de CETTE période
            ventes_reapprov_recu_valeur += montant
            ventes_reapprov_recu_qte += nb_tickets
        else:
            # Ticket existait avant la période → stock de début
            # (historique_source est NULL, ou pointe vers un historique
            # antérieur à date_debut)
            ventes_stock_debut_valeur += montant
            ventes_stock_debut_qte += nb_tickets

        # Grouper par semaine pour le détail
        event_date = serie.date_utilisation
        jours_depuis_debut = (event_date - date_debut).days
        numero_semaine = max(0, jours_depuis_debut // 7)

        semaine_debut = date_debut + timedelta(days=numero_semaine * 7)
        semaine_fin_theorique = semaine_debut + timedelta(days=6)
        semaine_fin = min(semaine_fin_theorique, date_fin)

        semaine_key = f"{semaine_debut.strftime('%d/%m')} au {semaine_fin.strftime('%d/%m/%Y')}"

        if semaine_key not in ventes_par_semaine:
            ventes_par_semaine[semaine_key] = {
                'date_debut': semaine_debut,
                'date_fin': semaine_fin,
                'total_valeur': Decimal('0'),
                'total_tickets': 0,
                'series_vendues': [],
            }

        ventes_par_semaine[semaine_key]['total_valeur'] += montant
        ventes_par_semaine[semaine_key]['total_tickets'] += nb_tickets

        # Série avec numéros EXACTS
        ventes_par_semaine[semaine_key]['series_vendues'].append({
            'couleur': serie.couleur,
            'couleur_nom': serie.couleur.libelle_affichage if serie.couleur else 'Inconnu',
            'numero_premier': serie.numero_premier,
            'numero_dernier': serie.numero_dernier,
            'nombre_tickets': nb_tickets,
            'valeur': montant,
            'date_vente': event_date,
            'reference_recette': str(serie.reference_recette) if serie.reference_recette else None,
        })

    logger.info(
        f"  Total ventes: {total_ventes_valeur:,.0f} FCFA ({total_ventes_qte} tickets)"
    )
    logger.info(
        f"  Répartition par historique_source:"
        f"\n    - Stock début (recharges antérieures): "
        f"{ventes_stock_debut_valeur:,.0f} FCFA ({ventes_stock_debut_qte} tickets)"
        f"\n    - Approv Imprimerie (cette période): "
        f"{ventes_approv_imprimerie_valeur:,.0f} FCFA ({ventes_approv_imprimerie_qte} tickets)"
        f"\n    - Réapprov reçu (cette période): "
        f"{ventes_reapprov_recu_valeur:,.0f} FCFA ({ventes_reapprov_recu_qte} tickets)"
    )

    donnees['ventes_par_semaine'] = ventes_par_semaine

    # ===================================================================
    # 6. AFFECTATION DES VENTES PAR LIGNE - DONNÉES RÉELLES
    # ===================================================================
    donnees['stock_debut']['ventes'] = ventes_stock_debut_valeur
    donnees['stock_debut']['ventes_qte'] = ventes_stock_debut_qte

    donnees['approv_imprimerie']['ventes'] = ventes_approv_imprimerie_valeur
    donnees['approv_imprimerie']['ventes_qte'] = ventes_approv_imprimerie_qte

    donnees['reapprov_recu']['ventes'] = ventes_reapprov_recu_valeur
    donnees['reapprov_recu']['ventes_qte'] = ventes_reapprov_recu_qte

    donnees['reapprov_cede']['ventes'] = Decimal('0')
    donnees['reapprov_cede']['ventes_qte'] = 0

    # ===================================================================
    # 7. CALCUL DES STOCKS FINAUX PAR LIGNE
    # ===================================================================
    donnees['stock_debut']['stock_final'] = (
        donnees['stock_debut']['stocks'] - donnees['stock_debut']['ventes']
    )

    donnees['approv_imprimerie']['stock_final'] = (
        donnees['approv_imprimerie']['stocks'] - donnees['approv_imprimerie']['ventes']
    )

    donnees['reapprov_recu']['stock_final'] = (
        donnees['reapprov_recu']['stocks'] - donnees['reapprov_recu']['ventes']
    )

    donnees['reapprov_cede']['stock_final'] = donnees['reapprov_cede']['stocks']

    # ===================================================================
    # 8. CALCUL DES TOTAUX
    # ===================================================================
    donnees['total']['stocks'] = (
        donnees['stock_debut']['stocks'] +
        donnees['approv_imprimerie']['stocks'] +
        donnees['reapprov_recu']['stocks'] +
        donnees['reapprov_cede']['stocks']
    )

    donnees['total']['ventes'] = total_ventes_valeur

    donnees['total']['stock_final'] = (
        donnees['stock_debut']['stock_final'] +
        donnees['approv_imprimerie']['stock_final'] +
        donnees['reapprov_recu']['stock_final'] +
        donnees['reapprov_cede']['stock_final']
    )

    # ===================================================================
    # 9. VÉRIFICATION FINALE - Stock fin via StockEvent
    # ===================================================================
    date_apres_fin = date_fin + timedelta(days=1)
    stock_fin_valeur, stock_fin_tickets = calculer_stock_debut_periode(poste, date_apres_fin)

    donnees['stock_final_calcule'] = stock_fin_valeur
    donnees['stock_final_qte'] = stock_fin_tickets
    donnees['diagnostic']['sources_utilisees']['stock_fin'] = 'event_sourcing_csp'

    ecart_final = abs(donnees['total']['stock_final'] - stock_fin_valeur)
    seuil_coherence = Decimal('5000')

    if ecart_final > seuil_coherence:
        donnees['diagnostic']['coherent'] = False
        donnees['diagnostic']['alertes'].append(
            f"Écart stock final: tableau={donnees['total']['stock_final']:,.0f} FCFA, "
            f"calculé={stock_fin_valeur:,.0f} FCFA, "
            f"écart={ecart_final:,.0f} FCFA"
        )
        logger.warning(
            f"[COMPTE_EMPLOI] ⚠️ Écart détecté:\n"
            f"  - Stock tableau: {donnees['total']['stock_final']:,.0f} FCFA\n"
            f"  - Stock StockEvent: {stock_fin_valeur:,.0f} FCFA\n"
            f"  - Écart: {ecart_final:,.0f} FCFA"
        )

    # ===================================================================
    # RÉSUMÉ FINAL
    # ===================================================================
    logger.info(f"{'=' * 60}")
    logger.info(f"RÉSUMÉ COMPTE D'EMPLOI V4:")
    logger.info(f"  Stock début: {donnees['stock_debut']['stocks']:,.0f} FCFA")
    logger.info(f"    → Ventes (stock ancien): {ventes_stock_debut_valeur:,.0f} FCFA")
    logger.info(f"  Approv IMP: {donnees['approv_imprimerie']['stocks']:,.0f} FCFA")
    logger.info(f"    → Ventes (approv période): {ventes_approv_imprimerie_valeur:,.0f} FCFA")
    logger.info(f"  Reçu: {donnees['reapprov_recu']['stocks']:,.0f} FCFA")
    logger.info(f"    → Ventes (transferts période): {ventes_reapprov_recu_valeur:,.0f} FCFA")
    logger.info(f"  Cédé: {donnees['reapprov_cede']['stocks']:,.0f} FCFA")
    logger.info(f"  Total ventes: {total_ventes_valeur:,.0f} FCFA")
    logger.info(f"  Stock final (tableau): {donnees['total']['stock_final']:,.0f} FCFA")
    logger.info(f"  Stock final (StockEvent): {donnees['stock_final_calcule']:,.0f} FCFA")
    logger.info(f"  Cohérent: {'✓' if donnees['diagnostic']['coherent'] else '✗'}")
    if donnees['diagnostic']['alertes']:
        for alerte in donnees['diagnostic']['alertes']:
            logger.info(f"  ⚠️ {alerte}")
    logger.info(f"{'=' * 60}")

    return donnees

# ===================================================================
# FONCTIONS UTILITAIRES POUR L'EXTRACTION DES SÉRIES
# ===================================================================

def _extraire_series_depuis_serie_ticket(hist):
    """
    Extrait les séries de tickets associées à un HistoriqueStock.

    Ordre de priorité:
    1. Champs structurés de HistoriqueStock (numero_premier_ticket, etc.)
    2. JSONField details_approvisionnement
    3. ManyToMany series_tickets_associees
    4. Fallback: parser le commentaire
    """
    from decimal import Decimal
    from inventaire.models import CouleurTicket

    series = []

    # SOURCE 1: Champs structurés directs sur HistoriqueStock
    if (getattr(hist, 'couleur_principale', None) and
        getattr(hist, 'numero_premier_ticket', None) and
        getattr(hist, 'numero_dernier_ticket', None)):

        nb_tickets = hist.numero_dernier_ticket - hist.numero_premier_ticket + 1
        series.append({
            'couleur': hist.couleur_principale,
            'couleur_nom': hist.couleur_principale.libelle_affichage,
            'numero_premier': hist.numero_premier_ticket,
            'numero_dernier': hist.numero_dernier_ticket,
            'nombre_tickets': nb_tickets,
            'valeur': Decimal(nb_tickets) * Decimal('500')
        })
        return series

    # SOURCE 2: JSONField details_approvisionnement
    if (getattr(hist, 'details_approvisionnement', None) and
        isinstance(hist.details_approvisionnement, dict)):

        series_data = hist.details_approvisionnement.get('series', [])

        for serie_data in series_data:
            couleur = None
            couleur_nom = serie_data.get('couleur_nom', serie_data.get('couleur', 'Inconnu'))

            if 'couleur_id' in serie_data:
                couleur = CouleurTicket.objects.filter(id=serie_data['couleur_id']).first()

            if not couleur and couleur_nom:
                couleur = CouleurTicket.objects.filter(
                    libelle_affichage__icontains=couleur_nom
                ).first()

            num_premier = serie_data.get('numero_premier', serie_data.get('premier'))
            num_dernier = serie_data.get('numero_dernier', serie_data.get('dernier'))

            if num_premier and num_dernier:
                nb_tickets = num_dernier - num_premier + 1
                series.append({
                    'couleur': couleur,
                    'couleur_nom': couleur.libelle_affichage if couleur else couleur_nom,
                    'numero_premier': num_premier,
                    'numero_dernier': num_dernier,
                    'nombre_tickets': nb_tickets,
                    'valeur': Decimal(str(serie_data.get('valeur', serie_data.get('montant', nb_tickets * 500))))
                })

        if series:
            return series

    # SOURCE 3: ManyToMany series_tickets_associees
    if hasattr(hist, 'series_tickets_associees'):
        series_associees = hist.series_tickets_associees.select_related('couleur').all()
        if series_associees.exists():
            for serie in series_associees:
                series.append({
                    'couleur': serie.couleur,
                    'couleur_nom': serie.couleur.libelle_affichage if serie.couleur else 'Inconnu',
                    'numero_premier': serie.numero_premier,
                    'numero_dernier': serie.numero_dernier,
                    'nombre_tickets': serie.nombre_tickets,
                    'valeur': serie.valeur_monetaire
                })
            return series

    # SOURCE 4: Fallback - parser le commentaire
    if getattr(hist, 'commentaire', '') and '#' in (hist.commentaire or ''):
        import re
        patterns = [
            r"(?:Série\s+)?(\w+(?:\s+\w+)?)\s*#(\d+)[–\-](\d+)",
            r"(\w+)\s*#(\d+)[–\-](\d+)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, hist.commentaire)
            if matches:
                for match in matches:
                    couleur_nom = match[0].strip()
                    num_premier = int(match[1])
                    num_dernier = int(match[2])

                    couleur = CouleurTicket.objects.filter(
                        libelle_affichage__icontains=couleur_nom
                    ).first()

                    nb_tickets = num_dernier - num_premier + 1
                    series.append({
                        'couleur': couleur,
                        'couleur_nom': couleur.libelle_affichage if couleur else couleur_nom,
                        'numero_premier': num_premier,
                        'numero_dernier': num_dernier,
                        'nombre_tickets': nb_tickets,
                        'valeur': Decimal(nb_tickets * 500)
                    })

                if series:
                    return series

    return series


def _construire_observation_approvisionnement(hist):
    """Construit le texte d'observation pour un approvisionnement."""
    series = _extraire_series_depuis_serie_ticket(hist)
    if series:
        parts = [
            f"{s['couleur_nom']} #{s['numero_premier']}-{s['numero_dernier']}"
            for s in series
        ]
        return ", ".join(parts)
    return hist.commentaire or f"{hist.nombre_tickets or 0} tickets"


def _construire_observation_transfert_recu(hist):
    """Construit le texte d'observation pour un transfert reçu."""
    series = _extraire_series_depuis_serie_ticket(hist)
    origine = hist.poste_origine.nom if hist.poste_origine else 'Inconnu'
    if series:
        parts = [
            f"{s['couleur_nom']} #{s['numero_premier']}-{s['numero_dernier']}"
            for s in series
        ]
        return f"Reçu de {origine}: " + ", ".join(parts)
    return f"Reçu de {origine}: {hist.commentaire or f'{hist.nombre_tickets or 0} tickets'}"


def _construire_observation_transfert_cede(hist):
    """Construit le texte d'observation pour un transfert cédé."""
    series = _extraire_series_depuis_serie_ticket(hist)
    destination = hist.poste_destination.nom if hist.poste_destination else 'Inconnu'
    if series:
        parts = [
            f"{s['couleur_nom']} #{s['numero_premier']}-{s['numero_dernier']}"
            for s in series
        ]
        return f"Cédé à {destination}: " + ", ".join(parts)
    return f"Cédé à {destination}: {hist.commentaire or f'{hist.nombre_tickets or 0} tickets'}"



# def calculer_donnees_compte_emploi_v2(poste, date_debut, date_fin):
#     """
#     VERSION CORRIGÉE - Calcul des données du compte d'emploi
#     (Fonction utilitaire - aucune modification liée aux permissions)
#     """
#     from collections import defaultdict
#     from django.db.models import Sum
#     from decimal import Decimal
#     from datetime import timedelta

#     try:
#         from inventaire.models import (
#             SerieTicket, StockEvent, HistoriqueStock, CouleurTicket
#         )
#     except ImportError:
#         from .models import SerieTicket, StockEvent, HistoriqueStock, CouleurTicket

#     logger.info(f"=" * 60)
#     logger.info(f"CALCUL COMPTE D'EMPLOI V2 CORRIGÉ - {poste.nom}")
#     logger.info(f"Période: {date_debut} → {date_fin}")

#     # Initialiser la structure de données
#     donnees = {
#         'stock_debut': {
#             'stocks': Decimal('0'),
#             'ventes': Decimal('0'),
#             'stock_final': Decimal('0'),
#             'stocks_qte': 0,
#             'ventes_qte': 0,
#         },
#         'approv_imprimerie': {
#             'stocks': Decimal('0'),
#             'ventes': Decimal('0'),
#             'stock_final': Decimal('0'),
#             'stocks_qte': 0,
#             'ventes_qte': 0,
#             'details': [],
#         },
#         'reapprov_recu': {
#             'stocks': Decimal('0'),
#             'ventes': Decimal('0'),
#             'stock_final': Decimal('0'),
#             'stocks_qte': 0,
#             'ventes_qte': 0,
#             'details': [],
#         },
#         'reapprov_cede': {
#             'stocks': Decimal('0'),
#             'ventes': Decimal('0'),
#             'stock_final': Decimal('0'),
#             'stocks_qte': 0,
#             'ventes_qte': 0,
#             'details': [],
#         },
#         'total': {
#             'stocks': Decimal('0'),
#             'ventes': Decimal('0'),
#             'stock_final': Decimal('0'),
#         },
#         'ventes_par_semaine': {},
#         'stock_final_calcule': Decimal('0'),
#         'stock_final_qte': 0,
#     }

#     # ========== 1. STOCK DE DÉBUT ==========
#     veille_debut = date_debut - timedelta(days=1)
#     stock_debut_valeur, stock_debut_qte = calculer_stock_event_sourcing(poste, veille_debut)

#     donnees['stock_debut']['stocks'] = stock_debut_valeur
#     donnees['stock_debut']['stocks_qte'] = stock_debut_qte

#     logger.info(f"Stock de début (au {veille_debut}): {stock_debut_valeur} FCFA ({stock_debut_qte} tickets)")

#     # ========== 2. APPROVISIONNEMENTS IMPRIMERIE NATIONALE ==========
#     historiques_imprimerie = HistoriqueStock.objects.filter(
#         poste=poste,
#         type_mouvement='CREDIT',
#         type_stock__in=['imprimerie_nationale', 'imprimerie'],
#         date_mouvement__date__gte=date_debut,
#         date_mouvement__date__lte=date_fin
#     ).select_related(
#         'couleur_principale', 'effectue_par'
#     ).prefetch_related(
#         'series_tickets_associees',
#         'series_tickets_associees__couleur'
#     ).order_by('date_mouvement')

#     for hist in historiques_imprimerie:
#         montant = hist.montant or Decimal('0')
#         nb_tickets = hist.nombre_tickets or 0

#         donnees['approv_imprimerie']['stocks'] += montant
#         donnees['approv_imprimerie']['stocks_qte'] += nb_tickets

#         series = extraire_series_depuis_historique(hist)

#         if series:
#             observation_parts = []
#             for s in series:
#                 observation_parts.append(
#                     f"{s['couleur_nom']} #{s['numero_premier']}-{s['numero_dernier']}"
#                 )
#             observation = ", ".join(observation_parts)
#         else:
#             observation = hist.commentaire or f"{nb_tickets} tickets"

#         donnees['approv_imprimerie']['details'].append({
#             'date': hist.date_mouvement,
#             'observation': observation,
#             'montant': montant,
#             'nombre_tickets': nb_tickets,
#             'series': series,
#             'historique_id': hist.id
#         })

#     logger.info(f"Approv Imprimerie: {donnees['approv_imprimerie']['stocks']} FCFA")

#     # ========== 3. TRANSFERTS REÇUS ==========
#     historiques_recus = HistoriqueStock.objects.filter(
#         poste=poste,
#         type_mouvement='CREDIT',
#         poste_origine__isnull=False,
#         date_mouvement__date__gte=date_debut,
#         date_mouvement__date__lte=date_fin
#     ).select_related(
#         'poste_origine', 'couleur_principale', 'effectue_par'
#     ).prefetch_related(
#         'series_tickets_associees',
#         'series_tickets_associees__couleur'
#     ).order_by('date_mouvement')

#     for hist in historiques_recus:
#         montant = hist.montant or Decimal('0')
#         nb_tickets = hist.nombre_tickets or 0

#         donnees['reapprov_recu']['stocks'] += montant
#         donnees['reapprov_recu']['stocks_qte'] += nb_tickets

#         series = extraire_series_depuis_historique(hist)

#         if series:
#             observation_parts = []
#             for s in series:
#                 observation_parts.append(
#                     f"{s['couleur_nom']} #{s['numero_premier']}-{s['numero_dernier']}"
#                 )
#             observation = f"Reçu de {hist.poste_origine.nom}: " + ", ".join(observation_parts)
#         else:
#             observation = f"Reçu de {hist.poste_origine.nom}: {hist.commentaire or f'{nb_tickets} tickets'}"

#         donnees['reapprov_recu']['details'].append({
#             'date': hist.date_mouvement,
#             'observation': observation,
#             'montant': montant,
#             'nombre_tickets': nb_tickets,
#             'poste_origine': hist.poste_origine,
#             'numero_bordereau': hist.numero_bordereau,
#             'series': series,
#             'historique_id': hist.id
#         })

#     logger.info(f"Transferts reçus: {donnees['reapprov_recu']['stocks']} FCFA")

#     # ========== 4. TRANSFERTS CÉDÉS ==========
#     historiques_cedes = HistoriqueStock.objects.filter(
#         poste=poste,
#         type_mouvement='DEBIT',
#         poste_destination__isnull=False,
#         date_mouvement__date__gte=date_debut,
#         date_mouvement__date__lte=date_fin
#     ).select_related(
#         'poste_destination', 'couleur_principale', 'effectue_par'
#     ).prefetch_related(
#         'series_tickets_associees',
#         'series_tickets_associees__couleur'
#     ).order_by('date_mouvement')

#     for hist in historiques_cedes:
#         montant = hist.montant or Decimal('0')
#         nb_tickets = hist.nombre_tickets or 0

#         donnees['reapprov_cede']['stocks'] -= montant
#         donnees['reapprov_cede']['stocks_qte'] -= nb_tickets

#         series = extraire_series_depuis_historique(hist)

#         if series:
#             observation_parts = []
#             for s in series:
#                 observation_parts.append(
#                     f"{s['couleur_nom']} #{s['numero_premier']}-{s['numero_dernier']}"
#                 )
#             observation = f"Cédé à {hist.poste_destination.nom}: " + ", ".join(observation_parts)
#         else:
#             observation = f"Cédé à {hist.poste_destination.nom}: {hist.commentaire or f'{nb_tickets} tickets'}"

#         donnees['reapprov_cede']['details'].append({
#             'date': hist.date_mouvement,
#             'observation': observation,
#             'montant': -montant,
#             'nombre_tickets': -nb_tickets,
#             'poste_destination': hist.poste_destination,
#             'numero_bordereau': hist.numero_bordereau,
#             'series': series,
#             'historique_id': hist.id
#         })

#     logger.info(f"Transferts cédés: {donnees['reapprov_cede']['stocks']} FCFA")

#     # ========== 5. VENTES - Via HistoriqueStock ==========
#     logger.info(f"=" * 40)
#     logger.info(f"RÉCUPÉRATION DES VENTES (via HistoriqueStock)")

#     historiques_ventes = HistoriqueStock.objects.filter(
#         poste=poste,
#         type_mouvement='DEBIT',
#         reference_recette__isnull=False,
#         poste_destination__isnull=True,
#         date_mouvement__date__gte=date_debut,
#         date_mouvement__date__lte=date_fin
#     ).select_related(
#         'reference_recette', 'couleur_principale', 'effectue_par'
#     ).prefetch_related(
#         'series_tickets_associees',
#         'series_tickets_associees__couleur'
#     ).order_by('date_mouvement')

#     logger.info(f"  Nombre d'historiques de vente trouvés: {historiques_ventes.count()}")

#     total_ventes_valeur = Decimal('0')
#     total_ventes_qte = 0
#     ventes_par_semaine = {}

#     for hist in historiques_ventes:
#         montant = hist.montant or Decimal('0')
#         nb_tickets = hist.nombre_tickets or 0

#         total_ventes_valeur += montant
#         total_ventes_qte += nb_tickets

#         if hist.date_mouvement:
#             if hasattr(hist.date_mouvement, 'date'):
#                 event_date = hist.date_mouvement.date()
#             else:
#                 event_date = hist.date_mouvement
#         elif hist.reference_recette:
#             event_date = hist.reference_recette.date
#         else:
#             event_date = date_debut

#         jours_depuis_debut = (event_date - date_debut).days
#         numero_semaine = max(0, jours_depuis_debut // 7)

#         semaine_debut = date_debut + timedelta(days=numero_semaine * 7)
#         semaine_fin_theorique = semaine_debut + timedelta(days=6)
#         semaine_fin = min(semaine_fin_theorique, date_fin)

#         semaine_key = f"{semaine_debut.strftime('%d/%m')} au {semaine_fin.strftime('%d/%m/%Y')}"

#         if semaine_key not in ventes_par_semaine:
#             ventes_par_semaine[semaine_key] = {
#                 'date_debut': semaine_debut,
#                 'date_fin': semaine_fin,
#                 'total_valeur': Decimal('0'),
#                 'total_tickets': 0,
#                 'series_vendues': [],
#                 'historiques': []
#             }

#         ventes_par_semaine[semaine_key]['total_valeur'] += montant
#         ventes_par_semaine[semaine_key]['total_tickets'] += nb_tickets
#         ventes_par_semaine[semaine_key]['historiques'].append(hist)

#         series = extraire_series_depuis_historique(hist)
#         for s in series:
#             s['date_vente'] = event_date
#             s['historique_id'] = hist.id
#             if hist.reference_recette:
#                 s['reference_recette'] = str(hist.reference_recette)
#             ventes_par_semaine[semaine_key]['series_vendues'].append(s)

#     logger.info(f"  Total ventes via HistoriqueStock: {total_ventes_valeur} FCFA ({total_ventes_qte} tickets)")

#     # ========== FALLBACK: StockEvent ==========
#     if total_ventes_valeur == 0:
#         logger.info(f"  → Tentative fallback via StockEvent...")

#         events_ventes = StockEvent.objects.filter(
#             poste=poste,
#             event_type='VENTE',
#             event_datetime__date__gte=date_debut,
#             event_datetime__date__lte=date_fin,
#             is_cancelled=False
#         ).order_by('event_datetime')

#         for event in events_ventes:
#             montant = abs(event.montant_variation)
#             nb_tickets = abs(event.nombre_tickets_variation)

#             total_ventes_valeur += montant
#             total_ventes_qte += nb_tickets

#             event_date = event.event_datetime.date()
#             jours_depuis_debut = (event_date - date_debut).days
#             numero_semaine = max(0, jours_depuis_debut // 7)

#             semaine_debut = date_debut + timedelta(days=numero_semaine * 7)
#             semaine_fin_theorique = semaine_debut + timedelta(days=6)
#             semaine_fin = min(semaine_fin_theorique, date_fin)

#             semaine_key = f"{semaine_debut.strftime('%d/%m')} au {semaine_fin.strftime('%d/%m/%Y')}"

#             if semaine_key not in ventes_par_semaine:
#                 ventes_par_semaine[semaine_key] = {
#                     'date_debut': semaine_debut,
#                     'date_fin': semaine_fin,
#                     'total_valeur': Decimal('0'),
#                     'total_tickets': 0,
#                     'series_vendues': [],
#                     'events': []
#                 }

#             ventes_par_semaine[semaine_key]['total_valeur'] += montant
#             ventes_par_semaine[semaine_key]['total_tickets'] += nb_tickets

#     # ========== Enrichir les semaines sans séries ==========
#     for semaine_key, semaine_data in ventes_par_semaine.items():
#         if not semaine_data['series_vendues']:
#             series_vendues = SerieTicket.objects.filter(
#                 poste=poste,
#                 statut__in=['vendu', 'epuise'],
#                 date_utilisation__gte=semaine_data['date_debut'],
#                 date_utilisation__lte=semaine_data['date_fin']
#             ).select_related('couleur').order_by('date_utilisation', 'couleur__code_normalise', 'numero_premier')

#             for serie in series_vendues:
#                 semaine_data['series_vendues'].append({
#                     'couleur': serie.couleur,
#                     'couleur_nom': serie.couleur.libelle_affichage if serie.couleur else 'Inconnu',
#                     'numero_premier': serie.numero_premier,
#                     'numero_dernier': serie.numero_dernier,
#                     'nombre_tickets': serie.nombre_tickets,
#                     'valeur': serie.valeur_monetaire,
#                     'date_vente': serie.date_utilisation,
#                 })

#         semaine_data['series_vendues'].sort(
#             key=lambda x: (x.get('date_vente') or date_debut, x.get('couleur_nom', ''))
#         )

#     donnees['ventes_par_semaine'] = ventes_par_semaine

#     logger.info(f"Total ventes FINAL: {total_ventes_valeur} FCFA ({total_ventes_qte} tickets)")

#     # ========== 6. RÉPARTITION DES VENTES ==========
#     total_entrees = (
#         donnees['stock_debut']['stocks'] +
#         donnees['approv_imprimerie']['stocks'] +
#         donnees['reapprov_recu']['stocks']
#     )

#     if total_entrees > 0:
#         ratio_stock_debut = donnees['stock_debut']['stocks'] / total_entrees
#         ratio_approv = donnees['approv_imprimerie']['stocks'] / total_entrees
#         ratio_recu = donnees['reapprov_recu']['stocks'] / total_entrees

#         donnees['stock_debut']['ventes'] = total_ventes_valeur * ratio_stock_debut
#         donnees['stock_debut']['ventes_qte'] = int(total_ventes_qte * float(ratio_stock_debut))

#         donnees['approv_imprimerie']['ventes'] = total_ventes_valeur * ratio_approv
#         donnees['approv_imprimerie']['ventes_qte'] = int(total_ventes_qte * float(ratio_approv))

#         donnees['reapprov_recu']['ventes'] = total_ventes_valeur * ratio_recu
#         donnees['reapprov_recu']['ventes_qte'] = int(total_ventes_qte * float(ratio_recu))

#     donnees['reapprov_cede']['ventes'] = Decimal('0')
#     donnees['reapprov_cede']['ventes_qte'] = 0

#     # ========== 7. CALCUL DES STOCKS FINAUX ==========
#     donnees['stock_debut']['stock_final'] = (
#         donnees['stock_debut']['stocks'] - donnees['stock_debut']['ventes']
#     )

#     donnees['approv_imprimerie']['stock_final'] = (
#         donnees['approv_imprimerie']['stocks'] - donnees['approv_imprimerie']['ventes']
#     )

#     donnees['reapprov_recu']['stock_final'] = (
#         donnees['reapprov_recu']['stocks'] - donnees['reapprov_recu']['ventes']
#     )

#     donnees['reapprov_cede']['stock_final'] = donnees['reapprov_cede']['stocks']

#     # ========== 8. CALCUL DES TOTAUX ==========
#     donnees['total']['stocks'] = (
#         donnees['stock_debut']['stocks'] +
#         donnees['approv_imprimerie']['stocks'] +
#         donnees['reapprov_recu']['stocks'] +
#         donnees['reapprov_cede']['stocks']
#     )

#     donnees['total']['ventes'] = total_ventes_valeur

#     donnees['total']['stock_final'] = (
#         donnees['stock_debut']['stock_final'] +
#         donnees['approv_imprimerie']['stock_final'] +
#         donnees['reapprov_recu']['stock_final'] +
#         donnees['reapprov_cede']['stock_final']
#     )

#     # Stock final via Event Sourcing
#     stock_fin_valeur, stock_fin_qte = calculer_stock_event_sourcing(poste, date_fin)
#     donnees['stock_final_calcule'] = stock_fin_valeur
#     donnees['stock_final_qte'] = stock_fin_qte

#     # Vérification cohérence
#     ecart = abs(donnees['total']['stock_final'] - stock_fin_valeur)
#     if ecart > Decimal('1000'):
#         logger.warning(
#             f"Écart détecté: Calcul tableau={donnees['total']['stock_final']}, "
#             f"Event Sourcing={stock_fin_valeur}, Écart={ecart}"
#         )

#     logger.info(f"=" * 60)
#     logger.info(f"RÉSUMÉ COMPTE D'EMPLOI:")
#     logger.info(f"  Stock début: {donnees['stock_debut']['stocks']}")
#     logger.info(f"  Approv IMP: {donnees['approv_imprimerie']['stocks']}")
#     logger.info(f"  Reçu: {donnees['reapprov_recu']['stocks']}")
#     logger.info(f"  Cédé: {donnees['reapprov_cede']['stocks']}")
#     logger.info(f"  Ventes: {donnees['total']['ventes']}")
#     logger.info(f"  Stock final: {donnees['total']['stock_final']}")
#     logger.info(f"=" * 60)

#     return donnees


# ===================================================================
# APERÇU HTML DU COMPTE D'EMPLOI
# ===================================================================
# AVANT: request.user.is_admin puis vérification manuelle poste_affectation
# APRÈS: has_permission('peut_voir_compte_emploi') + check_poste_access()
# ===================================================================

@login_required
def apercu_compte_emploi(request, poste_id, date_debut, date_fin):
    """
    Vue pour afficher un aperçu du compte d'emploi avant génération du PDF

    PERMISSIONS:
    - peut_voir_compte_emploi: Requis pour accéder à cette vue
    - Vérification de l'accès au poste via check_poste_access
    """
    user = request.user
    poste = get_object_or_404(Poste, id=poste_id)

    # ========== VÉRIFICATION DES PERMISSIONS ==========
    # 1. Permission globale
    if not has_permission(user, 'peut_voir_compte_emploi'):
        log_user_action(
            user=user,
            action="ACCES_REFUSE",
            description=f"Tentative d'accès à l'aperçu compte d'emploi - Poste {poste.nom}",
            details="Permission peut_voir_compte_emploi manquante",
            niveau="WARNING"
        )
        log_acces_refuse(user, "apercu_compte_emploi", "Permission peut_voir_compte_emploi manquante")
        messages.error(request, "Vous n'avez pas la permission d'accéder au compte d'emploi.")
        return redirect('common:dashboard')

    # 2. Accès au poste spécifique
    if not check_poste_access(user, poste):
        log_user_action(
            user=user,
            action="ACCES_REFUSE",
            description=f"Tentative d'accès au compte d'emploi du poste {poste.nom}",
            details=f"Poste {poste.nom} non autorisé pour {user.username}",
            niveau="WARNING"
        )
        log_acces_refuse(user, "apercu_compte_emploi", f"Accès au poste {poste.nom} refusé")
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        return redirect('inventaire:selection_compte_emploi')

    # Parser les dates
    try:
        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
    except:
        messages.error(request, "Format de dates invalide")
        return redirect('inventaire:selection_compte_emploi')

    # Log de la consultation
    log_user_action(
        user=user,
        action="CONSULTATION_COMPTE_EMPLOI",
        description=f"Aperçu compte d'emploi - Poste: {poste.nom}",
        details=f"Période: {date_debut} au {date_fin}",
        niveau="INFO"
    )
    logger.info(f"[COMPTE_EMPLOI] {user.username} consulte l'aperçu pour {poste.nom} ({date_debut} - {date_fin})")

    nombre_jours = (date_fin_obj - date_debut_obj).days + 1

    # Calculer les données
    donnees = calculer_donnees_compte_emploi_v2(poste, date_debut_obj, date_fin_obj)

    # Vérifier la cohérence
    coherence_ok = abs(donnees['total']['stock_final'] - donnees['stock_final_calcule']) < 1000

    if not coherence_ok:
        messages.warning(
            request,
            f"⚠️ Écart détecté dans le calcul. "
            f"Stock final tableau: {donnees['total']['stock_final']:,.0f} FCFA, "
            f"Stock final calculé: {donnees['stock_final_calcule']:,.0f} FCFA"
        )

    # ========== CONTEXTE (identique à la version précédente) ==========
    context = {
        'poste': poste,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'date_debut_obj': date_debut_obj,
        'date_fin_obj': date_fin_obj,
        'nombre_jours': nombre_jours,
        'donnees': donnees,
        'coherence_ok': coherence_ok,
        'title': f"Compte d'Emploi - {poste.nom}"
    }

    return render(request, 'inventaire/compte_emploi_v2.html', context)


# ===================================================================
# GÉNÉRATION PDF DU COMPTE D'EMPLOI
# ===================================================================
# (Fonctions utilitaires de génération PDF inchangées)
# ===================================================================

def creer_entete_bilingue(config, poste):
    """Crée l'en-tête bilingue du document"""
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
        Paragraph(f"<b>POSTE DE {poste.nom.upper()}</b>", header_style),
        Paragraph("*********", header_style)
    ]

    logo_cell = ""
    if config.logo:
        try:
            logo_path = os.path.join(settings.MEDIA_ROOT, config.logo.name)
            if os.path.exists(logo_path):
                logo_cell = Image(logo_path, width=3*cm, height=3*cm)
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
        Paragraph(f"<b>POST OF {poste.nom.upper()}</b>", header_style),
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


def creer_tableau_principal(donnees, date_debut, date_fin, styles):
    """Crée le tableau principal du compte d'emploi"""
    periode_str = f"{date_debut.strftime('%d/%m/%Y')} - {date_fin.strftime('%d/%m/%Y')}"

    def fmt_montant(val):
        if val == 0 or val == Decimal('0'):
            return "-"
        return f"{val:,.0f}".replace(',', ' ')

    table_data = [
        [
            Paragraph(f"<b>Période: {periode_str}</b>", styles['Normal']),
            Paragraph("<b>Stocks</b>", styles['Normal']),
            Paragraph("<b>Ventes</b>", styles['Normal']),
            Paragraph("<b>Stock Final</b>", styles['Normal'])
        ],
        [
            "Stock de début",
            fmt_montant(donnees['stock_debut']['stocks']),
            fmt_montant(donnees['stock_debut']['ventes']),
            fmt_montant(donnees['stock_debut']['stock_final'])
        ],
        [
            "Approv. (Imprimerie Nationale)",
            fmt_montant(donnees['approv_imprimerie']['stocks']),
            fmt_montant(donnees['approv_imprimerie']['ventes']),
            fmt_montant(donnees['approv_imprimerie']['stock_final'])
        ],
        [
            "Réapprov. reçu",
            fmt_montant(donnees['reapprov_recu']['stocks']),
            fmt_montant(donnees['reapprov_recu']['ventes']),
            fmt_montant(donnees['reapprov_recu']['stock_final'])
        ],
        [
            "Réapprov. cédé",
            fmt_montant(donnees['reapprov_cede']['stocks']),
            "/",
            fmt_montant(donnees['reapprov_cede']['stock_final'])
        ],
        [
            Paragraph("<b>TOTAL</b>", styles['Normal']),
            Paragraph(f"<b>{fmt_montant(donnees['total']['stocks'])}</b>", styles['Normal']),
            Paragraph(f"<b>{fmt_montant(donnees['total']['ventes'])}</b>", styles['Normal']),
            Paragraph(f"<b>{fmt_montant(donnees['total']['stock_final'])}</b>", styles['Normal'])
        ]
    ]

    col_widths = [6*cm, 4*cm, 4*cm, 4*cm]

    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -2), 9),
        ('BACKGROUND', (0, 1), (-1, -2), colors.whitesmoke),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e2e8f0')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))

    return table


def creer_section_details_approvisionnement(donnees, styles, titre="DÉTAILS DES APPROVISIONNEMENTS - IMPRIMERIE NATIONALE"):
    """Crée la section des détails d'approvisionnement"""
    elements = []

    titre_style = ParagraphStyle(
        'TitreSection',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=colors.HexColor('#2d3748'),
        spaceAfter=10,
        spaceBefore=15
    )
    elements.append(Paragraph(titre, titre_style))

    details = donnees['approv_imprimerie']['details']

    if not details:
        elements.append(Paragraph("<i>Aucun approvisionnement sur cette période</i>", styles['Normal']))
        return elements

    table_data = [
        ['Date', 'Observation (Couleur, Séries)', 'Montant (FCFA)']
    ]

    for detail in details:
        date_str = detail['date'].strftime('%d/%m/%Y') if detail['date'] else '-'
        observation = detail['observation'][:80] + "..." if len(detail['observation']) > 80 else detail['observation']
        montant = f"{detail['montant']:,.0f}".replace(',', ' ')

        table_data.append([date_str, observation, montant])

    table = Table(table_data, colWidths=[2.5*cm, 11*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3182ce')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    elements.append(table)
    return elements


def creer_section_transferts_recus(donnees, styles):
    """Crée la section des transferts reçus"""
    elements = []

    titre_style = ParagraphStyle(
        'TitreSection',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=colors.HexColor('#38a169'),
        spaceAfter=10,
        spaceBefore=15
    )
    elements.append(Paragraph("DÉTAILS DES TRANSFERTS REÇUS", titre_style))

    details = donnees['reapprov_recu']['details']

    if not details:
        elements.append(Paragraph("<i>Aucun transfert reçu sur cette période</i>", styles['Normal']))
        return elements

    table_data = [
        ['Date', 'Observation (Origine, Séries)', 'Montant (FCFA)']
    ]

    for detail in details:
        date_str = detail['date'].strftime('%d/%m/%Y') if detail['date'] else '-'
        observation = detail['observation'][:80] + "..." if len(detail['observation']) > 80 else detail['observation']
        montant = f"{detail['montant']:,.0f}".replace(',', ' ')

        table_data.append([date_str, observation, montant])

    table = Table(table_data, colWidths=[2.5*cm, 11*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#38a169')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    elements.append(table)
    return elements


def creer_section_transferts_cedes(donnees, styles):
    """Crée la section des transferts cédés"""
    elements = []

    titre_style = ParagraphStyle(
        'TitreSection',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=colors.HexColor('#e53e3e'),
        spaceAfter=10,
        spaceBefore=15
    )
    elements.append(Paragraph("DÉTAILS DES TRANSFERTS CÉDÉS", titre_style))

    details = donnees['reapprov_cede']['details']

    if not details:
        elements.append(Paragraph("<i>Aucun transfert cédé sur cette période</i>", styles['Normal']))
        return elements

    table_data = [
        ['Date', 'Observation (Destination, Séries)', 'Montant (FCFA)']
    ]

    for detail in details:
        date_str = detail['date'].strftime('%d/%m/%Y') if detail['date'] else '-'
        observation = detail['observation'][:80] + "..." if len(detail['observation']) > 80 else detail['observation']
        montant = f"{abs(detail['montant']):,.0f}".replace(',', ' ')

        table_data.append([date_str, observation, f"-{montant}"])

    table = Table(table_data, colWidths=[2.5*cm, 11*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e53e3e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#e53e3e')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    elements.append(table)
    return elements


def creer_section_ventes_par_semaine(donnees, styles):
    """Crée la section des ventes par semaine personnalisée"""
    elements = []

    titre_style = ParagraphStyle(
        'TitreSection',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=colors.HexColor('#dd6b20'),
        spaceAfter=10,
        spaceBefore=15
    )
    elements.append(Paragraph("DÉTAILS DES VENTES PAR SEMAINE", titre_style))

    ventes_par_semaine = donnees['ventes_par_semaine']

    if not ventes_par_semaine:
        elements.append(Paragraph("<i>Aucune vente sur cette période</i>", styles['Normal']))
        return elements

    semaines_triees = sorted(
        ventes_par_semaine.items(),
        key=lambda x: x[1]['date_debut']
    )

    for semaine_key, semaine_data in semaines_triees:
        semaine_header = Paragraph(
            f"<b>SEMAINE DU {semaine_key}</b>",
            ParagraphStyle(
                'SemaineHeader',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.whitesmoke,
                alignment=TA_CENTER
            )
        )

        table_data = [[semaine_header, '', '']]

        series_par_couleur = {}
        for serie in semaine_data['series_vendues']:
            couleur_nom = serie.get('couleur_nom', 'Inconnu')
            if couleur_nom not in series_par_couleur:
                series_par_couleur[couleur_nom] = {
                    'series': [],
                    'total_tickets': 0,
                    'total_valeur': Decimal('0')
                }
            series_par_couleur[couleur_nom]['series'].append(serie)
            series_par_couleur[couleur_nom]['total_tickets'] += serie.get('nombre_tickets', 0)
            series_par_couleur[couleur_nom]['total_valeur'] += serie.get('valeur', Decimal('0'))

        for couleur_nom, couleur_data in series_par_couleur.items():
            series_str_list = []
            for s in couleur_data['series'][:5]:
                series_str_list.append(f"#{s['numero_premier']}-{s['numero_dernier']}")

            if len(couleur_data['series']) > 5:
                series_str_list.append(f"... (+{len(couleur_data['series']) - 5})")

            series_str = ", ".join(series_str_list)

            table_data.append([
                f"{couleur_nom}",
                f"{series_str}",
                f"{couleur_data['total_valeur']:,.0f} FCFA".replace(',', ' ')
            ])

        table_data.append([
            Paragraph("<b>Total semaine</b>", styles['Normal']),
            f"{semaine_data['total_tickets']} tickets",
            f"{semaine_data['total_valeur']:,.0f} FCFA".replace(',', ' ')
        ])

        table = Table(table_data, colWidths=[4*cm, 8*cm, 3.5*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dd6b20')),
            ('SPAN', (0, 0), (-1, 0)),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#fef3e2')),
            ('FONTSIZE', (0, 1), (-1, -2), 7),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fed7aa')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 8),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dd6b20')),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 0.3*cm))

    return elements


def creer_pied_page(poste, config, user):
    """Crée le pied de page avec signature et horodatage"""
    styles = getSampleStyleSheet()

    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_CENTER
    )

    date_impression = datetime.now().strftime("%d/%m/%Y à %H:%M")

    footer_data = [
        [Paragraph(f"le {date_impression}", footer_style)],
        [Spacer(1, 0.3*cm)],
        [Paragraph("<b>LE CHEF DE POSTE</b>", footer_style)],
        [Spacer(1, 1*cm)],
        [Paragraph("_________________________", footer_style)],
        [Spacer(1, 0.3*cm)],
        [Paragraph(
            f"<i>Document généré par SUPPER - Utilisateur: {user.nom_complet}</i>",
            ParagraphStyle('FooterItalic', parent=footer_style, fontSize=7, textColor=colors.grey)
        )]
    ]

    footer_table = Table(footer_data, colWidths=[20*cm])

    return footer_table


# ===================================================================
# GÉNÉRATION PDF DU COMPTE D'EMPLOI
# ===================================================================
# AVANT: request.user.is_admin puis vérification manuelle poste_affectation
# APRÈS: has_permission('peut_voir_compte_emploi') + check_poste_access()
# ===================================================================

@login_required
def generer_compte_emploi_pdf(request, poste_id, date_debut, date_fin):
    """
    Génère le PDF du compte d'emploi avec le nouveau format

    PERMISSIONS:
    - peut_voir_compte_emploi: Requis pour accéder à cette vue
    - Vérification de l'accès au poste via check_poste_access
    """
    user = request.user
    poste = get_object_or_404(Poste, id=poste_id)

    # ========== VÉRIFICATION DES PERMISSIONS ==========
    # 1. Permission globale
    if not has_permission(user, 'peut_voir_compte_emploi'):
        log_user_action(
            user=user,
            action="ACCES_REFUSE",
            description=f"Tentative de génération PDF compte d'emploi - Poste {poste.nom}",
            details="Permission peut_voir_compte_emploi manquante",
            niveau="WARNING"
        )
        log_acces_refuse(user, "generer_compte_emploi_pdf", "Permission peut_voir_compte_emploi manquante")
        messages.error(request, "Vous n'avez pas la permission de générer ce document.")
        return redirect('common:dashboard')

    # 2. Accès au poste spécifique
    if not check_poste_access(user, poste):
        log_user_action(
            user=user,
            action="ACCES_REFUSE",
            description=f"Tentative de génération PDF pour le poste {poste.nom}",
            details=f"Poste {poste.nom} non autorisé pour {user.username}",
            niveau="WARNING"
        )
        log_acces_refuse(user, "generer_compte_emploi_pdf", f"Accès au poste {poste.nom} refusé")
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        return redirect('inventaire:selection_compte_emploi')

    # Parser les dates
    try:
        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
    except:
        messages.error(request, "Format de dates invalide")
        return redirect('inventaire:selection_compte_emploi')

    # Log de la génération
    log_user_action(
        user=user,
        action="GENERATION_PDF_COMPTE_EMPLOI",
        description=f"Génération PDF compte d'emploi - Poste: {poste.nom}",
        details=f"Période: {date_debut} au {date_fin}",
        niveau="INFO"
    )
    logger.info(f"[COMPTE_EMPLOI] {user.username} génère le PDF pour {poste.nom} ({date_debut} - {date_fin})")

    # Récupérer config
    config = ConfigurationGlobale.get_config()

    # Calcul des données
    donnees = calculer_donnees_compte_emploi_v2(poste, date_debut_obj, date_fin_obj)

    # Générer PDF
    response = HttpResponse(content_type='application/pdf')
    filename = f'compte_emploi_{poste.code}_{date_debut}_au_{date_fin}.pdf'
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

    # En-tête bilingue
    elements.append(creer_entete_bilingue(config, poste))
    elements.append(Spacer(1, 0.5*cm))

    # Titre
    titre_style = ParagraphStyle(
        'TitreCompte',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=colors.HexColor('#1a1a1a'),
        alignment=TA_CENTER,
        spaceAfter=20
    )

    titre = Paragraph(
        f"COMPTE D'EMPLOI DES TICKETS<br/>"
        f"Période du {date_debut_obj.strftime('%d/%m/%Y')} au {date_fin_obj.strftime('%d/%m/%Y')}",
        titre_style
    )
    elements.append(titre)
    elements.append(Spacer(1, 0.5*cm))

    # Tableau principal
    elements.append(creer_tableau_principal(donnees, date_debut_obj, date_fin_obj, styles))
    elements.append(Spacer(1, 0.5*cm))

    # Section Approvisionnements Imprimerie
    elements.extend(creer_section_details_approvisionnement(donnees, styles))

    # Section Transferts reçus
    elements.extend(creer_section_transferts_recus(donnees, styles))

    # Section Transferts cédés
    elements.extend(creer_section_transferts_cedes(donnees, styles))

    # Saut de page
    elements.append(PageBreak())

    # Section Ventes par semaine
    elements.extend(creer_section_ventes_par_semaine(donnees, styles))

    # Note de vérification
    elements.append(Spacer(1, 0.5*cm))

    note_style = ParagraphStyle(
        'Note',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor('#4b5563'),
        alignment=TA_CENTER
    )

    ecart = abs(donnees['total']['stock_final'] - donnees['stock_final_calcule'])

    if ecart < Decimal('1000'):
        note_text = "✓ Cohérence vérifiée : Stock final tableau = Stock calculé par Event Sourcing"
        note_color = '#10b981'
    else:
        note_text = f"⚠ Écart détecté : {ecart:,.0f} FCFA".replace(',', ' ')
        note_color = '#ef4444'

    elements.append(Paragraph(f"<font color='{note_color}'>{note_text}</font>", note_style))

    # Pied de page
    elements.append(Spacer(1, 0.5*cm))
    elements.append(creer_pied_page(poste, config, user))

    # Générer le PDF
    doc.build(elements)

    return response


# ===================================================================
# PARAMÉTRAGE GLOBAL
# ===================================================================
# AVANT: @user_passes_test(lambda u: u.is_admin)
# APRÈS: Vérification via has_permission('peut_parametrage_global')
# ===================================================================

@login_required
def parametrage_global(request):
    """
    Vue de paramétrage global pour tous les postes

    PERMISSIONS:
    - peut_parametrage_global: Requis pour accéder à cette vue
    """
    user = request.user

    # ========== VÉRIFICATION DES PERMISSIONS ==========
    if not has_permission(user, 'peut_parametrage_global'):
        log_user_action(
            user=user,
            action="ACCES_REFUSE",
            description="Tentative d'accès au paramétrage global",
            details="Permission peut_parametrage_global manquante",
            niveau="WARNING"
        )
        log_acces_refuse(user, "parametrage_global", "Permission peut_parametrage_global manquante")
        messages.error(request, "Vous n'avez pas la permission d'accéder au paramétrage global.")
        return redirect('common:dashboard')

    # Log de l'accès
    logger.info(f"[PARAMETRAGE] {user.username} ({user.get_habilitation_display()}) accède au paramétrage global")

    config = ConfigurationGlobale.get_config()

    if request.method == 'POST':
        config.republique_fr = request.POST.get('republique_fr', config.republique_fr)
        config.devise_fr = request.POST.get('devise_fr', config.devise_fr)
        config.ministere_fr = request.POST.get('ministere_fr', config.ministere_fr)
        config.direction_fr = request.POST.get('direction_fr', config.direction_fr)
        config.programme_fr = request.POST.get('programme_fr', config.programme_fr)

        config.republique_en = request.POST.get('republique_en', config.republique_en)
        config.devise_en = request.POST.get('devise_en', config.devise_en)
        config.ministere_en = request.POST.get('ministere_en', config.ministere_en)
        config.direction_en = request.POST.get('direction_en', config.direction_en)
        config.programme_en = request.POST.get('programme_en', config.programme_en)

        if 'logo' in request.FILES:
            config.logo = request.FILES['logo']

        config.save()

        # Log de la modification
        log_user_action(
            user=user,
            action="MODIFICATION_PARAMETRAGE_GLOBAL",
            description="Mise à jour de la configuration globale",
            details="Paramètres bilingues FR/EN modifiés",
            niveau="INFO"
        )
        logger.info(f"[PARAMETRAGE] {user.username} a modifié la configuration globale")

        messages.success(request, "Configuration globale mise à jour avec succès")
        return redirect('inventaire:parametrage_global')

    # ========== CONTEXTE (identique à la version précédente) ==========
    context = {
        'config': config,
        'title': 'Paramétrage Global des Documents'
    }

    return render(request, 'inventaire/parametrage_global.html', context)