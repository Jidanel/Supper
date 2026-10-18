# ===================================================================
# inventaire/views_stocks.py - VERSION CORRIGÉE
# Gestion des stocks avec permissions granulaires SUPPER
# MISE À JOUR : Intégration complète des 73 permissions
# ===================================================================
"""
Ce fichier contient les vues de gestion des stocks de tickets.

HABILITATIONS ET PERMISSIONS PAR VUE:
-------------------------------------
liste_postes_stocks:
    - Permission: peut_voir_liste_stocks_peage
    - Habilitations: admin_principal, coord_psrr, serv_info, serv_emission,
                     cisop_peage, chef_peage (tous postes)

charger_stock_selection / charger_stock_tickets:
    - Permission: peut_charger_stock_peage
    - Habilitations: admin_principal, coord_psrr, serv_info, serv_emission

confirmation_chargement_stock_tickets:
    - Permission: peut_charger_stock_peage
    - Habilitations: admin_principal, coord_psrr, serv_info, serv_emission

mon_stock:
    - Permission: peut_voir_mon_stock_peage
    - Habilitations: chef_peage (son poste uniquement)

historique_stock:
    - Permission: peut_voir_historique_stock_peage
    - Habilitations: admin + cisop_peage + chef_peage (son poste)

detail_historique_stock:
    - Permission: peut_voir_historique_stock_peage
    - Habilitations: admin + cisop_peage + chef_peage (son poste)
"""

from django.http import HttpResponseForbidden,JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Q
from decimal import Decimal, InvalidOperation
from django.db import models
from datetime import date, timedelta
from django.utils import timezone

from .models import (
    Poste, GestionStock, HistoriqueStock, SerieTicket,
    CouleurTicket, RecetteJournaliere, StockEvent
)
from .forms import *
from accounts.models import UtilisateurSUPPER, NotificationUtilisateur

# ===================================================================
# IMPORTS DES FONCTIONS DE PERMISSIONS DU PROJET
# ===================================================================
from common.permissions import (
    has_permission,
    has_any_permission,
    check_poste_access,
    user_has_acces_tous_postes,
    is_admin_user,
    is_service_central,
    is_cisop_peage,
    is_chef_poste_peage,
    get_postes_accessibles,
    get_postes_peage_accessibles,
    log_acces_refuse,
)

from common.utils import (
    log_user_action,
    log_operation_stock,
    get_user_description,
    get_user_short_description,
    get_user_category,
)

import logging
logger = logging.getLogger('supper')


# ===================================================================
# FONCTIONS UTILITAIRES DE VÉRIFICATION DES PERMISSIONS
# ===================================================================

def peut_voir_stocks(user):
    """
    Vérifie si l'utilisateur peut voir la liste des stocks.

    Permissions: peut_voir_liste_stocks_peage
    Habilitations: admin, serv_emission, cisop_peage, chef_peage
    """
    if not user or not user.is_authenticated:
        return False

    # Superuser a toujours accès
    if user.is_superuser:
        return True

    # Vérifier la permission granulaire
    if has_permission(user, 'peut_voir_liste_stocks_peage'):
        return True

    # Admin et service central ont accès
    if is_admin_user(user) or is_service_central(user):
        return True

    # CISOP péage a accès à tous les stocks péage
    if is_cisop_peage(user):
        return True

    return False


def peut_charger_stock(user):
    """
    Vérifie si l'utilisateur peut charger du stock.

    Permission: peut_charger_stock_peage
    Habilitations: admin_principal, coord_psrr, serv_info, serv_emission
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    # Vérifier la permission granulaire
    if has_permission(user, 'peut_charger_stock_peage'):
        return True

    # Admin a toujours cette permission
    if is_admin_user(user):
        return True

    return False


def peut_voir_mon_stock(user):
    """
    Vérifie si l'utilisateur peut voir son propre stock.

    Permission: peut_voir_mon_stock_peage
    Habilitations: chef_peage (son poste)
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    # Permission granulaire
    if has_permission(user, 'peut_voir_mon_stock_peage'):
        return True

    # Chef de poste péage peut voir son stock
    if is_chef_poste_peage(user) and user.poste_affectation:
        return True

    return False


def peut_voir_historique_stock(user):
    """
    Vérifie si l'utilisateur peut voir l'historique du stock.

    Permission: peut_voir_historique_stock_peage
    Habilitations: admin, cisop_peage, chef_peage (son poste)
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    # Permission granulaire
    if has_permission(user, 'peut_voir_historique_stock_peage'):
        return True

    # Admin et services centraux
    if is_admin_user(user) or is_service_central(user):
        return True

    # CISOP péage
    if is_cisop_peage(user):
        return True

    return False


def verifier_acces_poste_stock(user, poste):
    """
    Vérifie si l'utilisateur a accès au stock d'un poste spécifique.

    Args:
        user: L'utilisateur
        poste: Le poste cible

    Returns:
        bool: True si accès autorisé
    """
    if not user or not user.is_authenticated:
        return False

    # Superuser ou accès tous postes
    if user.is_superuser or user_has_acces_tous_postes(user):
        return True

    # Vérifier si c'est le poste d'affectation
    poste_affectation = getattr(user, 'poste_affectation', None)
    if poste_affectation and poste_affectation.id == poste.id:
        return True

    # Utiliser check_poste_access du module permissions
    return check_poste_access(user, poste)


# ===================================================================
# VUE: LISTE DES POSTES ET LEURS STOCKS
# ===================================================================

@login_required
def liste_postes_stocks(request):
    """
    Vue pour afficher tous les stocks des postes avec calcul de date d'épuisement.

    VERSION MISE À JOUR - Ajout des statistiques globales :
        - Total chargé Imprimerie Nationale (montant + tickets)
        - Total vendu (montant + tickets)
        - Total restant (montant + tickets)

    FONCTIONNALITÉS:
        - Recherche côté serveur sur tous les postes (nom et code)
        - Pagination avec conservation du paramètre de recherche
        - Calcul de date d'épuisement basé sur ventes moyennes
        - Niveaux d'alerte (danger, warning, info, success)

    PARAMÈTRES GET:
        - q: terme de recherche (optionnel)
        - page: numéro de page (optionnel)
    """
    user = request.user

    # ===================================================================
    # VÉRIFICATION DES PERMISSIONS
    # ===================================================================
    if not peut_voir_stocks(user):
        log_acces_refuse(
            user,
            "liste_postes_stocks",
            "Permission peut_voir_liste_stocks_peage manquante"
        )
        messages.error(request, "Vous n'avez pas la permission de consulter les stocks.")
        logger.warning(
            f"🚫 ACCÈS REFUSÉ | {get_user_short_description(user)} | "
            f"Vue: liste_postes_stocks | Permission: peut_voir_liste_stocks_peage"
        )
        return redirect('common:dashboard')

    # ===================================================================
    # RÉCUPÉRATION DU PARAMÈTRE DE RECHERCHE
    # ===================================================================
    search_query = request.GET.get('q', '').strip()

    # Log de l'accès
    if search_query:
        logger.info(
            f"📦 RECHERCHE STOCKS | {get_user_short_description(user)} | "
            f"Terme: '{search_query}'"
        )
    else:
        logger.info(
            f"📦 CONSULTATION STOCKS | {get_user_short_description(user)} | "
            f"Accès à la liste des stocks"
        )

    # ===================================================================
    # RÉCUPÉRATION DES POSTES SELON LES PERMISSIONS
    # ===================================================================
    if user_has_acces_tous_postes(user):
        postes = Poste.objects.filter(is_active=True, type='peage')
    elif user.poste_affectation:
        postes = Poste.objects.filter(id=user.poste_affectation.id, is_active=True)
    else:
        postes = Poste.objects.none()

    # ===================================================================
    # FILTRAGE PAR RECHERCHE (si un terme est fourni)
    # ===================================================================
    if search_query:
        postes = postes.filter(
            models.Q(nom__icontains=search_query) |
            models.Q(code__icontains=search_query)
        )

    # ===================================================================
    # CALCUL DES DONNÉES DE STOCK PAR POSTE
    # ===================================================================
    stocks_data = []

    for poste in postes:
        stock, created = GestionStock.objects.get_or_create(
            poste=poste,
            defaults={'valeur_monetaire': Decimal('0')}
        )

        # Calculer la vente moyenne journalière sur les 30 derniers jours
        date_fin = date.today()
        date_debut = date_fin - timedelta(days=30)

        ventes_mois = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[date_debut, date_fin]
        ).aggregate(
            total=Sum('montant_declare'),
            nombre_jours=models.Count('id')
        )

        vente_moyenne_journaliere = Decimal('0')
        if ventes_mois['total'] and ventes_mois['nombre_jours'] > 0:
            vente_moyenne_journaliere = ventes_mois['total'] / ventes_mois['nombre_jours']

        # Calculer la date d'épuisement
        date_epuisement = None
        jours_restants = None
        alerte_stock = 'success'

        if vente_moyenne_journaliere > 0:
            jours_restants = int(stock.valeur_monetaire / vente_moyenne_journaliere)
            date_epuisement = date_fin + timedelta(days=jours_restants - 7)

            if jours_restants <= 14:
                alerte_stock = 'danger'
            elif jours_restants > 14 and jours_restants <= 21:
                alerte_stock = 'warning'
            elif jours_restants > 21 and jours_restants <= 30:
                alerte_stock = 'info'

        stocks_data.append({
            'poste': poste,
            'stock': stock,
            'valeur_monetaire': stock.valeur_monetaire,
            'nombre_tickets': stock.nombre_tickets,
            'vente_moyenne': vente_moyenne_journaliere,
            'jours_restants': jours_restants,
            'date_epuisement': date_epuisement,
            'alerte': alerte_stock,
            'derniere_mise_a_jour': stock.derniere_mise_a_jour
        })

    # Trier par valeur monétaire (stocks les plus bas en premier)
    stocks_data.sort(key=lambda x: x['valeur_monetaire'])

    # ===================================================================
    # STATISTIQUES GLOBALES EXISTANTES (sans filtre de recherche)
    # ===================================================================
    if user_has_acces_tous_postes(user):
        all_postes = Poste.objects.filter(is_active=True, type='peage')
    elif user.poste_affectation:
        all_postes = Poste.objects.filter(id=user.poste_affectation.id, is_active=True)
    else:
        all_postes = Poste.objects.none()

    all_stocks = GestionStock.objects.filter(poste__in=all_postes)
    total_stock = all_stocks.aggregate(total=Sum('valeur_monetaire'))['total'] or Decimal('0')
    total_tickets = all_stocks.aggregate(total=Sum('nombre_tickets'))['total'] or 0

    # Calcul des stocks critiques et faibles
    all_stocks_data = []
    for poste in all_postes:
        stock, _ = GestionStock.objects.get_or_create(
            poste=poste,
            defaults={'valeur_monetaire': Decimal('0')}
        )

        date_fin = date.today()
        date_debut = date_fin - timedelta(days=30)

        ventes_mois = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[date_debut, date_fin]
        ).aggregate(
            total=Sum('montant_declare'),
            nombre_jours=models.Count('id')
        )

        vente_moyenne = Decimal('0')
        if ventes_mois['total'] and ventes_mois['nombre_jours'] > 0:
            vente_moyenne = ventes_mois['total'] / ventes_mois['nombre_jours']

        jours_restants = None
        if vente_moyenne > 0:
            jours_restants = int(stock.valeur_monetaire / vente_moyenne)

        all_stocks_data.append({'jours_restants': jours_restants})

    stocks_critiques = len([s for s in all_stocks_data if s['jours_restants'] is not None and s['jours_restants'] <= 14])
    stocks_faibles = len([s for s in all_stocks_data if s['jours_restants'] is not None and 14 < s['jours_restants'] <= 21])

    # ===================================================================
    # NOUVELLES STATISTIQUES GLOBALES - IMPRIMERIE NATIONALE ET VENTES
    # ===================================================================

    # 1. TOTAL CHARGÉ PAR L'IMPRIMERIE NATIONALE
    # Historique type_mouvement='CREDIT' ET type_stock='imprimerie_nationale'
    stats_imprimerie = HistoriqueStock.objects.filter(
        poste__in=all_postes,
        type_mouvement='CREDIT',
        type_stock='imprimerie_nationale'
    ).aggregate(
        total_montant=Sum('montant'),
        total_tickets=Sum('nombre_tickets')
    )

    total_imprimerie_montant = stats_imprimerie['total_montant'] or Decimal('0')
    total_imprimerie_tickets = stats_imprimerie['total_tickets'] or 0

    logger.debug(
        f"📊 STATS IMPRIMERIE | Montant: {total_imprimerie_montant:,.0f} FCFA | "
        f"Tickets: {total_imprimerie_tickets:,}"
    )

    # 2. TOTAL VENDU (DÉBIT avec reference_recette = ventes)
    # Note: Les ventes sont enregistrées comme DEBIT avec reference_recette non null
    stats_ventes = HistoriqueStock.objects.filter(
        poste__in=all_postes,
        type_mouvement='DEBIT',
        reference_recette__isnull=False
    ).aggregate(
        total_montant=Sum('montant'),
        total_tickets=Sum('nombre_tickets')
    )

    total_vendu_montant = stats_ventes['total_montant'] or Decimal('0')
    total_vendu_tickets = stats_ventes['total_tickets'] or 0

    logger.debug(
        f"📊 STATS VENTES | Montant: {total_vendu_montant:,.0f} FCFA | "
        f"Tickets: {total_vendu_tickets:,}"
    )

    # 3. TOTAL RESTANT (déjà calculé ci-dessus: total_stock et total_tickets)
    # Utilise les données de GestionStock
    total_restant_montant = total_stock
    total_restant_tickets = total_tickets

    logger.debug(
        f"📊 STATS RESTANT | Montant: {total_restant_montant:,.0f} FCFA | "
        f"Tickets: {total_restant_tickets:,}"
    )

    # ===================================================================
    # PAGINATION
    # ===================================================================
    paginator = Paginator(stocks_data, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # ===================================================================
    # LOG DE L'ACTION UTILISATEUR (détaillé)
    # ===================================================================
    log_user_action(
        user,
        "CONSULTATION_LISTE_STOCKS",
        f"Consultation de {len(stocks_data)} poste(s) - "
        f"{'Recherche: ' + search_query + ' - ' if search_query else ''}"
        f"Stock total: {total_stock:,.0f} FCFA - "
        f"Stocks critiques: {stocks_critiques} - "
        f"Imprimerie chargé: {total_imprimerie_montant:,.0f} FCFA ({total_imprimerie_tickets:,} tickets) - "
        f"Vendu: {total_vendu_montant:,.0f} FCFA ({total_vendu_tickets:,} tickets) - "
        f"Restant: {total_restant_montant:,.0f} FCFA ({total_restant_tickets:,} tickets)",
        request,
        nb_postes=len(stocks_data),
        total_stock=str(total_stock),
        stocks_critiques=stocks_critiques,
        stocks_faibles=stocks_faibles,
        search_query=search_query if search_query else None,
        total_imprimerie_montant=str(total_imprimerie_montant),
        total_imprimerie_tickets=total_imprimerie_tickets,
        total_vendu_montant=str(total_vendu_montant),
        total_vendu_tickets=total_vendu_tickets,
        total_restant_montant=str(total_restant_montant),
        total_restant_tickets=total_restant_tickets
    )

    # ===================================================================
    # CONTEXTE - AVEC LES NOUVELLES VARIABLES
    # ===================================================================
    context = {
        # Données existantes (inchangées)
        'page_obj': page_obj,
        'total_stock': total_stock,
        'total_tickets': total_tickets,
        'stocks_critiques': stocks_critiques,
        'stocks_faibles': stocks_faibles,
        'search_query': search_query,
        'title': 'Gestion des Stocks - Vue d\'ensemble',

        # NOUVELLES STATISTIQUES
        # Imprimerie Nationale
        'total_imprimerie_montant': total_imprimerie_montant,
        'total_imprimerie_tickets': total_imprimerie_tickets,

        # Ventes (déstockage)
        'total_vendu_montant': total_vendu_montant,
        'total_vendu_tickets': total_vendu_tickets,

        # Stock restant (redondant avec total_stock mais explicite)
        'total_restant_montant': total_restant_montant,
        'total_restant_tickets': total_restant_tickets,
    }

    return render(request, 'inventaire/liste_stocks.html', context)
# ===================================================================
# VUE: SÉLECTION DE POSTE POUR CHARGEMENT
# ===================================================================

@login_required
def charger_stock_selection(request, poste_id):
    """
    Vue pour charger le stock d'un poste spécifique.

    AVANT:
        - Vérification simple avec peut_acceder_poste
        - Pas de permission granulaire

    APRÈS:
        - Permission: peut_charger_stock_peage
        - Vérification d'accès au poste avec check_poste_access
        - Logs détaillés
        - Variables contexte IDENTIQUES
    """
    user = request.user
    poste = get_object_or_404(Poste, id=poste_id, is_active=True)

    # ===================================================================
    # VÉRIFICATION DES PERMISSIONS
    # ===================================================================
    if not peut_charger_stock(user):
        log_acces_refuse(
            user,
            f"charger_stock_selection (poste: {poste.nom})",
            "Permission peut_charger_stock_peage manquante"
        )
        messages.error(request, "Vous n'avez pas la permission de charger du stock.")
        logger.warning(
            f"🚫 ACCÈS REFUSÉ | {get_user_short_description(user)} | "
            f"Vue: charger_stock_selection | Poste: {poste.nom} | "
            f"Permission: peut_charger_stock_peage"
        )
        return redirect('inventaire:liste_postes_stocks')

    # Vérifier l'accès au poste spécifique
    if not verifier_acces_poste_stock(user, poste):
        log_acces_refuse(
            user,
            f"charger_stock_selection (poste: {poste.nom})",
            "Accès au poste non autorisé"
        )
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        logger.warning(
            f"🚫 ACCÈS REFUSÉ | {get_user_short_description(user)} | "
            f"Vue: charger_stock_selection | Poste: {poste.nom} | "
            f"Raison: Accès au poste non autorisé"
        )
        return redirect('inventaire:liste_postes_stocks')

    # Log de l'accès
    logger.info(
        f"📥 CHARGEMENT STOCK | {get_user_short_description(user)} | "
        f"Accès au formulaire de chargement pour {poste.nom}"
    )

    # ===================================================================
    # TRAITEMENT DU FORMULAIRE
    # ===================================================================
    if request.method == 'POST':
        form = ChargementStockTicketsForm(request.POST)
        if form.is_valid():
            try:
                couleur = form.cleaned_data['couleur']
                numero_premier = form.cleaned_data['numero_premier']
                numero_dernier = form.cleaned_data['numero_dernier']
                type_stock = form.cleaned_data.get('type_stock', 'imprimerie_nationale')
                observations = form.cleaned_data.get('observations', '')

                # Validation
                if numero_dernier <= numero_premier:
                    messages.error(request, "Le numéro du dernier ticket doit être supérieur au premier.")
                    logger.warning(
                        f"⚠️ VALIDATION ÉCHOUÉE | {get_user_short_description(user)} | "
                        f"Chargement stock {poste.nom} | Numéros invalides: {numero_premier}-{numero_dernier}"
                    )
                    return render(request, 'inventaire/charger_stock_selection.html', {
                        'form': form,
                        'poste': poste,
                        'title': f'Charger le stock - {poste.nom}'
                    })

                # Vérifier les conflits avec les séries existantes
                series_existantes = SerieTicket.objects.filter(
                    couleur=couleur,
                    poste=poste,
                    statut='stock'
                )

                for serie in series_existantes:
                    if not (numero_dernier < serie.numero_premier or
                            numero_premier > serie.numero_dernier):
                        messages.error(
                            request,
                            f"Conflit avec la série existante {serie.couleur.libelle_affichage} "
                            f"#{serie.numero_premier}-{serie.numero_dernier}"
                        )
                        logger.warning(
                            f"⚠️ CONFLIT SÉRIE | {get_user_short_description(user)} | "
                            f"Chargement stock {poste.nom} | "
                            f"Conflit avec série {serie.couleur.libelle_affichage} "
                            f"#{serie.numero_premier}-{serie.numero_dernier}"
                        )
                        return render(request, 'inventaire/charger_stock_selection.html', {
                            'form': form,
                            'poste': poste,
                            'title': f'Charger le stock - {poste.nom}'
                        })

                # Exécuter le chargement
                success, message, serie, historique = executer_chargement_stock_avec_series(
                    poste=poste,
                    couleur=couleur,
                    numero_premier=numero_premier,
                    numero_dernier=numero_dernier,
                    type_stock=type_stock,
                    user=user,
                    commentaire=observations
                )

                if success:
                    messages.success(request, message)

                    # Log détaillé du chargement réussi
                    nombre_tickets = numero_dernier - numero_premier + 1
                    montant = Decimal(nombre_tickets) * Decimal('500')

                    log_operation_stock(
                        user,
                        poste,
                        "CHARGEMENT",
                        nombre_tickets,
                        serie=f"{couleur.libelle_affichage} #{numero_premier}-{numero_dernier}",
                        request=request,
                        type_stock=type_stock,
                        montant=str(montant)
                    )

                    logger.info(
                        f"✅ CHARGEMENT RÉUSSI | {get_user_short_description(user)} | "
                        f"Poste: {poste.nom} | Série: {couleur.libelle_affichage} "
                        f"#{numero_premier}-{numero_dernier} | "
                        f"{nombre_tickets} tickets = {montant:,.0f} FCFA"
                    )

                    return redirect('inventaire:detail_stock', poste_id=poste.id)
                else:
                    messages.error(request, message)
                    logger.error(
                        f"❌ CHARGEMENT ÉCHOUÉ | {get_user_short_description(user)} | "
                        f"Poste: {poste.nom} | Erreur: {message}"
                    )

            except Exception as e:
                logger.error(
                    f"❌ ERREUR INATTENDUE | {get_user_short_description(user)} | "
                    f"charger_stock_selection | Poste: {poste.nom} | Erreur: {str(e)}",
                    exc_info=True
                )
                messages.error(request, f"Erreur inattendue: {str(e)}")
    else:
        form = ChargementStockTicketsForm()

    # Récupérer les séries actuelles en stock
    series_actuelles = SerieTicket.objects.filter(
        poste=poste,
        statut='stock'
    ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')

    # Récupérer le stock total
    try:
        stock_total = GestionStock.objects.get(poste=poste)
    except GestionStock.DoesNotExist:
        stock_total = None

    # ===================================================================
    # CONTEXTE - VARIABLES IDENTIQUES À L'ANCIENNE VERSION
    # ===================================================================
    context = {
        'form': form,
        'poste': poste,
        'series_actuelles': series_actuelles,
        'stock_total': stock_total,
        'title': f'Charger le stock - {poste.nom}'
    }

    return render(request, 'inventaire/charger_stock_selection.html', context)




def executer_chargement_stock_multiple(poste, series_data, type_stock, user, commentaire=""):
    """
    Exécute le chargement de PLUSIEURS séries de tickets en une seule transaction.

    CORRECTION V4: Après création de l'historique, lie chaque série via
    historique_source pour traçabilité dans le compte d'emploi.

    Args:
        poste: Instance du Poste destinataire
        series_data: Liste de dictionnaires avec les données de chaque série:
            [{'couleur': CouleurTicket, 'numero_premier': int, 'numero_dernier': int}, ...]
        type_stock: 'imprimerie_nationale' ou 'regularisation'
        user: Utilisateur effectuant le chargement
        commentaire: Commentaire optionnel

    Returns:
        tuple (bool, str, list, HistoriqueStock):
            (succès, message, liste_séries_créées, historique)
    """
    timestamp = timezone.now()
    series_creees = []
    montant_total = Decimal('0')
    nombre_tickets_total = 0

    logger.info(
        f"📦 DÉBUT CHARGEMENT MULTIPLE | {get_user_short_description(user)} | "
        f"Poste: {poste.nom} | {len(series_data)} série(s) à charger | "
        f"Type: {type_stock}"
    )

    try:
        with transaction.atomic():
            # 1. Récupérer le stock actuel
            stock, created = GestionStock.objects.get_or_create(
                poste=poste,
                defaults={'valeur_monetaire': Decimal('0')}
            )
            stock_avant = stock.valeur_monetaire

            logger.info(f"  📊 Stock avant: {stock_avant:,.0f} FCFA")

            # 2. Traiter chaque série
            details_series = []

            for idx, serie_data in enumerate(series_data):
                couleur = serie_data['couleur']
                numero_premier = serie_data['numero_premier']
                numero_dernier = serie_data['numero_dernier']

                # Calculs
                nombre_tickets = numero_dernier - numero_premier + 1
                montant = Decimal(nombre_tickets) * Decimal('500')

                logger.info(
                    f"  📝 Série {idx+1}: {couleur.libelle_affichage} "
                    f"#{numero_premier}-{numero_dernier} "
                    f"({nombre_tickets} tickets = {montant:,.0f} FCFA)"
                )

                # Créer la série de tickets
                serie = SerieTicket.objects.create(
                    poste=poste,
                    couleur=couleur,
                    numero_premier=numero_premier,
                    numero_dernier=numero_dernier,
                    nombre_tickets=nombre_tickets,
                    valeur_monetaire=montant,
                    statut='stock',
                    type_entree=type_stock,
                    responsable_reception=user,
                    commentaire=commentaire
                )

                series_creees.append(serie)
                montant_total += montant
                nombre_tickets_total += nombre_tickets

                # Préparer les détails pour l'historique
                details_series.append({
                    'couleur_id': couleur.id,
                    'couleur_nom': couleur.libelle_affichage,
                    'numero_premier': numero_premier,
                    'numero_dernier': numero_dernier,
                    'nombre_tickets': nombre_tickets,
                    'montant': str(montant)
                })

            # 3. Mettre à jour le stock global
            stock.valeur_monetaire += montant_total
            stock.save()
            stock_apres = stock.valeur_monetaire

            logger.info(
                f"  📊 Stock après: {stock_apres:,.0f} FCFA "
                f"(+{montant_total:,.0f} FCFA)"
            )

            # 4. Créer l'historique avec les détails de toutes les séries
            historique = HistoriqueStock.objects.create(
                poste=poste,
                type_mouvement='CREDIT',
                type_stock=type_stock,
                montant=montant_total,
                nombre_tickets=nombre_tickets_total,
                stock_avant=stock_avant,
                stock_apres=stock_apres,
                effectue_par=user,
                commentaire=f"Chargement multiple: {len(series_data)} série(s) - {commentaire}",
                details_approvisionnement={'series': details_series}
            )

            # Associer les séries à l'historique (ManyToMany existant)
            historique.series_tickets_associees.add(*series_creees)

            # === NOUVEAU V4: Lier chaque série à son historique source ===
            for serie in series_creees:
                serie.historique_source = historique
                serie.save(update_fields=['historique_source'])

            # 5. Créer l'événement de stock
            StockEvent.objects.create(
                poste=poste,
                event_type='CHARGEMENT',
                event_datetime=timestamp,
                montant_variation=montant_total,
                nombre_tickets_variation=nombre_tickets_total,
                stock_resultant=stock_apres,
                tickets_resultants=int(stock_apres / 500),
                effectue_par=user,
                reference_id=str(historique.id),
                reference_type='HistoriqueStock',
                metadata={
                    'type_stock': type_stock,
                    'nb_series': len(series_data),
                    'series': details_series
                },
                commentaire=f"Chargement multiple de {len(series_data)} série(s)"
            )

            logger.info(
                f"✅ CHARGEMENT MULTIPLE RÉUSSI | {get_user_short_description(user)} | "
                f"Poste: {poste.nom} | {len(series_creees)} série(s) | "
                f"{nombre_tickets_total} tickets | {montant_total:,.0f} FCFA"
            )

            return (
                True,
                f"✅ {len(series_creees)} série(s) chargée(s) avec succès "
                f"({nombre_tickets_total} tickets = {montant_total:,.0f} FCFA)",
                series_creees,
                historique
            )

    except Exception as e:
        logger.error(
            f"❌ ERREUR CHARGEMENT MULTIPLE | {get_user_short_description(user)} | "
            f"Poste: {poste.nom} | Erreur: {str(e)}",
            exc_info=True
        )
        return False, f"Erreur lors du chargement: {str(e)}", [], None


# ===================================================================
# VUE: CHARGEMENT STOCK MULTIPLE (NOUVELLE VERSION)
# ===================================================================

@login_required
def charger_stock_tickets(request, poste_id):
    """
    Vue MISE À JOUR pour charger le stock avec PLUSIEURS séries à la fois.

    Fonctionne comme la saisie de recette avec tickets:
    - Un formulaire de base (type de stock, commentaire)
    - Un formset pour les séries (couleur, premier, dernier)
    - Ajout/suppression dynamique de séries via JavaScript

    Permissions: peut_charger_stock_peage + accès au poste
    """
    user = request.user
    poste = get_object_or_404(Poste, id=poste_id)

    # ===================================================================
    # VÉRIFICATION DES PERMISSIONS
    # ===================================================================
    if not peut_charger_stock(user):
        log_acces_refuse(
            user,
            f"charger_stock_tickets (poste: {poste.nom})",
            "Permission peut_charger_stock_peage manquante"
        )
        messages.error(request, "Vous n'avez pas la permission de charger du stock.")
        logger.warning(
            f"🚫 ACCÈS REFUSÉ | {get_user_short_description(user)} | "
            f"Vue: charger_stock_tickets | Poste: {poste.nom}"
        )
        return redirect('inventaire:liste_postes_stocks')

    # Vérifier l'accès au poste
    if not verifier_acces_poste_stock(user, poste):
        log_acces_refuse(
            user,
            f"charger_stock_tickets (poste: {poste.nom})",
            "Accès au poste non autorisé"
        )
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        return redirect('inventaire:liste_postes_stocks')

    logger.info(
        f"📥 CHARGEMENT STOCK MULTIPLE | {get_user_short_description(user)} | "
        f"Accès au formulaire pour {poste.nom}"
    )

    # ===================================================================
    # RÉCUPÉRATION DES DONNÉES
    # ===================================================================
    stock, created = GestionStock.objects.get_or_create(
        poste=poste,
        defaults={'valeur_monetaire': Decimal('0')}
    )

    series_en_stock = SerieTicket.objects.filter(
        poste=poste,
        statut='stock'
    ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')

    # Grouper les séries par couleur pour l'affichage
    series_par_couleur = {}
    for serie in series_en_stock:
        couleur_code = serie.couleur.code_normalise
        if couleur_code not in series_par_couleur:
            series_par_couleur[couleur_code] = {
                'couleur': serie.couleur,
                'series': [],
                'total_tickets': 0,
                'valeur_totale': Decimal('0')
            }

        series_par_couleur[couleur_code]['series'].append(serie)
        series_par_couleur[couleur_code]['total_tickets'] += serie.nombre_tickets
        series_par_couleur[couleur_code]['valeur_totale'] += serie.valeur_monetaire

    # Récupérer les couleurs existantes pour l'autocomplétion
    couleurs_existantes = CouleurTicket.objects.all().order_by('code_normalise')

    # ===================================================================
    # TRAITEMENT DU FORMULAIRE
    # ===================================================================
    if request.method == 'POST':
        form = ChargementStockMultipleBaseForm(request.POST)
        formset = DetailSerieChargementFormSet(request.POST, prefix='series')

        if form.is_valid() and formset.is_valid():
            type_stock = form.cleaned_data['type_stock']
            commentaire = form.cleaned_data.get('commentaire', '')

            # Validation des séries
            series_valides = []
            erreurs_validation = []
            annee_actuelle = date.today().year

            for i, form_serie in enumerate(formset):
                if form_serie.cleaned_data and not form_serie.cleaned_data.get('DELETE', False):
                    couleur_saisie = form_serie.cleaned_data['couleur_saisie']
                    numero_premier = form_serie.cleaned_data['numero_premier']
                    numero_dernier = form_serie.cleaned_data['numero_dernier']

                    # Obtenir ou créer la couleur normalisée
                    couleur_obj = CouleurTicket.obtenir_ou_creer(couleur_saisie)

                    # Vérification d'unicité annuelle
                    est_unique, msg, details = SerieTicket.verifier_unicite_annuelle_chargement(
                        couleur_obj, numero_premier, numero_dernier, annee_actuelle
                    )

                    if not est_unique:
                        erreurs_validation.append(f"❌ Série {i+1}: {msg}")
                        continue

                    # Ajouter aux séries valides
                    nombre_tickets = numero_dernier - numero_premier + 1
                    montant = Decimal(nombre_tickets) * Decimal('500')

                    series_valides.append({
                        'couleur': couleur_obj,
                        'couleur_libelle': couleur_obj.libelle_affichage,
                        'numero_premier': numero_premier,
                        'numero_dernier': numero_dernier,
                        'nombre_tickets': nombre_tickets,
                        'montant': montant
                    })

            # Vérifier qu'il y a au moins une série valide
            if not series_valides:
                if not erreurs_validation:
                    erreurs_validation.append("Vous devez saisir au moins une série de tickets.")

            # Si erreurs, réafficher le formulaire
            if erreurs_validation:
                for erreur in erreurs_validation:
                    messages.error(request, erreur)

                # Log des erreurs
                logger.warning(
                    f"⚠️ VALIDATION ÉCHOUÉE | {get_user_short_description(user)} | "
                    f"Poste: {poste.nom} | {len(erreurs_validation)} erreur(s)"
                )
            else:
                # Stocker en session pour confirmation
                montant_total = sum(s['montant'] for s in series_valides)
                nombre_tickets_total = sum(s['nombre_tickets'] for s in series_valides)

                request.session['chargement_stock_multiple'] = {
                    'poste_id': poste_id,
                    'type_stock': type_stock,
                    'commentaire': commentaire,
                    'series': [
                        {
                            'couleur_id': s['couleur'].id,
                            'couleur_libelle': s['couleur_libelle'],
                            'numero_premier': s['numero_premier'],
                            'numero_dernier': s['numero_dernier'],
                            'nombre_tickets': s['nombre_tickets'],
                            'montant': str(s['montant'])
                        }
                        for s in series_valides
                    ],
                    'montant_total': str(montant_total),
                    'nombre_tickets_total': nombre_tickets_total
                }

                logger.info(
                    f"📋 PRÉPARATION CHARGEMENT MULTIPLE | {get_user_short_description(user)} | "
                    f"Poste: {poste.nom} | {len(series_valides)} série(s) | "
                    f"{nombre_tickets_total} tickets | {montant_total:,.0f} FCFA"
                )

                return redirect('inventaire:confirmation_chargement_stock_tickets')
    else:
        form = ChargementStockMultipleBaseForm()
        formset = DetailSerieChargementFormSet(prefix='series')

    # Historique récent
    historique_recent = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='CREDIT'
    ).select_related('effectue_par').order_by('-date_mouvement')[:5]

    # ===================================================================
    # CONTEXTE
    # ===================================================================
    context = {
        'poste': poste,
        'stock': stock,
        'form': form,
        'formset': formset,
        'series_par_couleur': series_par_couleur,
        'couleurs_existantes': couleurs_existantes,
        'historique_recent': historique_recent,
        'title': f'Charger stock - {poste.nom}'
    }

    return render(request, 'inventaire/charger_stock_tickets.html', context)



# ===================================================================
# VUE: CONFIRMATION CHARGEMENT STOCK TICKETS
# ===================================================================

# ===================================================================
# VUE: CONFIRMATION CHARGEMENT STOCK MULTIPLE
# ===================================================================

@login_required
def confirmation_chargement_stock_tickets(request):
    """
    Page de confirmation pour le chargement MULTIPLE de séries.

    Affiche un récapitulatif de toutes les séries à charger
    et permet de valider ou annuler l'opération.
    """
    user = request.user

    # Vérification des permissions
    if not peut_charger_stock(user):
        log_acces_refuse(
            user,
            "confirmation_chargement_stock_tickets",
            "Permission peut_charger_stock_peage manquante"
        )
        messages.error(request, "Vous n'avez pas la permission de charger du stock.")
        return redirect('inventaire:liste_postes_stocks')

    # Récupérer les données de session
    chargement_data = request.session.get('chargement_stock_multiple')

    if not chargement_data:
        messages.error(request, "Aucune donnée de chargement en attente.")
        logger.warning(
            f"⚠️ SESSION VIDE | {get_user_short_description(user)} | "
            f"Pas de données de chargement en session"
        )
        return redirect('inventaire:liste_postes_stocks')

    poste = get_object_or_404(Poste, id=chargement_data['poste_id'])

    # Vérifier l'accès au poste
    if not verifier_acces_poste_stock(user, poste):
        del request.session['chargement_stock_multiple']
        log_acces_refuse(
            user,
            f"confirmation_chargement_stock_tickets (poste: {poste.nom})",
            "Accès au poste non autorisé"
        )
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        return redirect('inventaire:liste_postes_stocks')

    logger.info(
        f"✅ CONFIRMATION CHARGEMENT MULTIPLE | {get_user_short_description(user)} | "
        f"Poste: {poste.nom} | {len(chargement_data['series'])} série(s)"
    )

    # ===================================================================
    # TRAITEMENT POST
    # ===================================================================
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'confirmer':
            try:
                # Préparer les données des séries
                series_data = []
                for serie_info in chargement_data['series']:
                    couleur = CouleurTicket.objects.get(id=serie_info['couleur_id'])
                    series_data.append({
                        'couleur': couleur,
                        'numero_premier': serie_info['numero_premier'],
                        'numero_dernier': serie_info['numero_dernier']
                    })

                # Exécuter le chargement
                success, message, series_creees, historique = executer_chargement_stock_multiple(
                    poste=poste,
                    series_data=series_data,
                    type_stock=chargement_data['type_stock'],
                    user=user,
                    commentaire=chargement_data.get('commentaire', '')
                )

                if success:
                    # Nettoyer la session
                    del request.session['chargement_stock_multiple']

                    # Log de l'action
                    log_user_action(
                        user,
                        "CHARGEMENT_STOCK_MULTIPLE",
                        f"Chargement de {len(series_creees)} série(s) pour {poste.nom} - "
                        f"{chargement_data['nombre_tickets_total']} tickets = "
                        f"{chargement_data['montant_total']} FCFA",
                        request,
                        poste=poste.nom,
                        nb_series=len(series_creees),
                        montant_total=chargement_data['montant_total'],
                        type_stock=chargement_data['type_stock']
                    )

                    messages.success(request, message)
                    return redirect('inventaire:liste_postes_stocks')
                else:
                    messages.error(request, message)
                    return redirect('inventaire:charger_stock_tickets', poste_id=poste.id)

            except Exception as e:
                logger.error(
                    f"❌ ERREUR CHARGEMENT | {get_user_short_description(user)} | "
                    f"Poste: {poste.nom} | Erreur: {str(e)}",
                    exc_info=True
                )
                messages.error(request, f"Erreur lors du chargement: {str(e)}")
                return redirect('inventaire:charger_stock_tickets', poste_id=poste.id)

        elif action == 'annuler':
            del request.session['chargement_stock_multiple']
            messages.info(request, "Chargement annulé.")
            logger.info(
                f"↩️ CHARGEMENT ANNULÉ | {get_user_short_description(user)} | "
                f"Poste: {poste.nom}"
            )
            return redirect('inventaire:charger_stock_tickets', poste_id=poste.id)

    # ===================================================================
    # PRÉPARATION AFFICHAGE
    # ===================================================================

    # Enrichir les données des séries pour l'affichage
    series_enrichies = []
    for serie_info in chargement_data['series']:
        couleur = CouleurTicket.objects.get(id=serie_info['couleur_id'])
        series_enrichies.append({
            'couleur': couleur,
            'numero_premier': serie_info['numero_premier'],
            'numero_dernier': serie_info['numero_dernier'],
            'nombre_tickets': serie_info['nombre_tickets'],
            'montant': Decimal(serie_info['montant'])
        })

    montant_total = Decimal(chargement_data['montant_total'])

    # Récupérer le stock actuel
    stock, _ = GestionStock.objects.get_or_create(
        poste=poste,
        defaults={'valeur_monetaire': Decimal('0')}
    )

    context = {
        'poste': poste,
        'series': series_enrichies,
        'montant_total': montant_total,
        'nombre_tickets_total': chargement_data['nombre_tickets_total'],
        'type_stock': chargement_data['type_stock'],
        'type_stock_label': (
            'Imprimerie Nationale' if chargement_data['type_stock'] == 'imprimerie_nationale'
            else 'Régularisation'
        ),
        'commentaire': chargement_data.get('commentaire', ''),
        'stock_actuel': stock.valeur_monetaire,
        'stock_apres': stock.valeur_monetaire + montant_total,
        'title': 'Confirmation du chargement de stock'
    }

    return render(request, 'inventaire/confirmation_chargement_stock_tickets.html', context)


# ===================================================================
# VUE: MODIFICATION DES SÉRIES EN STOCK (Admin uniquement)
# ===================================================================

# ===================================================================
# inventaire/views_stocks.py - CORRECTIONS POUR LE PROBLÈME DE DIVERGENCE
# Chemin: inventaire/views_stocks.py
#
# PROBLÈME: Stock Event Sourcing différent du stock réel
# CAUSE: Les séries reçues par transfert ne sont pas visibles dans
#        modifier_series_stock mais sont comptées dans GestionStock
#
# SOLUTIONS DANS CE FICHIER:
# 1. Vue modifier_series_stock corrigée - affiche TOUTES les séries
# 2. Vue diagnostic_stock - compare les 3 sources de données
# 3. Vue reconcilier_stock - permet de corriger les divergences
# ===================================================================

# ===================================================================
# CORRECTION 1: MODIFIER_SERIES_STOCK - AFFICHE TOUTES LES SÉRIES
# ===================================================================

@login_required
def modifier_series_stock(request, poste_id):
    """
    Vue CORRIGÉE pour modifier les séries de tickets EN STOCK d'un poste.

    CORRECTION MAJEURE:
    - Affiche TOUTES les séries en stock (y compris transferts reçus)
    - Les séries transférées sont marquées comme "non modifiables directement"
    - Affiche le récapitulatif montrant la correspondance avec GestionStock

    RÉSERVÉ AUX ADMINISTRATEURS.
    """
    user = request.user

    # ===================================================================
    # VÉRIFICATION: Admin uniquement
    # ===================================================================
    if not is_admin_user(user):
        log_acces_refuse(
            user,
            f"modifier_series_stock (poste_id: {poste_id})",
            "Administrateur requis"
        )
        messages.error(request, "Accès réservé aux administrateurs.")
        logger.warning(
            f"🚫 ACCÈS REFUSÉ | {get_user_short_description(user)} | "
            f"Vue: modifier_series_stock | Raison: Non admin"
        )
        return redirect('inventaire:liste_postes_stocks')

    poste = get_object_or_404(Poste, id=poste_id)

    logger.info(
        f"🔧 MODIFICATION SÉRIES | {get_user_short_description(user)} | "
        f"Accès au formulaire pour {poste.nom}"
    )

    # ===================================================================
    # RÉCUPÉRATION DE TOUTES LES SÉRIES EN STOCK
    # ===================================================================

    # 1. Séries MODIFIABLES (imprimerie_nationale, regularisation)
    series_modifiables = SerieTicket.objects.filter(
        poste=poste,
        statut='stock',
        type_entree__in=['imprimerie_nationale', 'regularisation']
    ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')

    # 2. Séries TRANSFÉRÉES (non modifiables directement)
    series_transferees = SerieTicket.objects.filter(
        poste=poste,
        statut='stock',
        type_entree='transfert_recu'
    ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')

    # 3. TOUTES les séries en stock (pour le total)
    toutes_series_stock = SerieTicket.objects.filter(
        poste=poste,
        statut='stock'
    ).select_related('couleur')

    # ===================================================================
    # CALCUL DES TOTAUX PAR SOURCE
    # ===================================================================

    # Total des séries modifiables
    total_modifiables = series_modifiables.aggregate(
        total_valeur=Sum('valeur_monetaire'),
        total_tickets=Sum('nombre_tickets')
    )
    valeur_modifiables = total_modifiables['total_valeur'] or Decimal('0')
    tickets_modifiables = total_modifiables['total_tickets'] or 0

    # Total des séries transférées
    total_transferees = series_transferees.aggregate(
        total_valeur=Sum('valeur_monetaire'),
        total_tickets=Sum('nombre_tickets')
    )
    valeur_transferees = total_transferees['total_valeur'] or Decimal('0')
    tickets_transferees = total_transferees['total_tickets'] or 0

    # Total de toutes les séries
    total_series = toutes_series_stock.aggregate(
        total_valeur=Sum('valeur_monetaire'),
        total_tickets=Sum('nombre_tickets')
    )
    valeur_series_total = total_series['total_valeur'] or Decimal('0')
    tickets_series_total = total_series['total_tickets'] or 0

    # Stock dans GestionStock
    stock, _ = GestionStock.objects.get_or_create(
        poste=poste,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    valeur_gestion_stock = stock.valeur_monetaire

    # Stock via Event Sourcing
    valeur_event_sourcing, tickets_event_sourcing = StockEvent.get_stock_at_date(
        poste, date.today()
    )

    # ===================================================================
    # DÉTECTION DES DIVERGENCES
    # ===================================================================
    divergences = []

    # Divergence SerieTicket vs GestionStock
    ecart_series_gestion = valeur_series_total - valeur_gestion_stock
    if abs(ecart_series_gestion) > Decimal('1'):
        divergences.append({
            'type': 'series_vs_gestion',
            'message': f"Écart entre séries en stock ({valeur_series_total:,.0f} FCFA) "
                      f"et GestionStock ({valeur_gestion_stock:,.0f} FCFA): "
                      f"{ecart_series_gestion:+,.0f} FCFA",
            'ecart': ecart_series_gestion,
            'gravite': 'warning' if abs(ecart_series_gestion) < 50000 else 'danger'
        })

    # Divergence GestionStock vs Event Sourcing
    ecart_gestion_events = valeur_gestion_stock - valeur_event_sourcing
    if abs(ecart_gestion_events) > Decimal('1'):
        divergences.append({
            'type': 'gestion_vs_events',
            'message': f"Écart entre GestionStock ({valeur_gestion_stock:,.0f} FCFA) "
                      f"et Event Sourcing ({valeur_event_sourcing:,.0f} FCFA): "
                      f"{ecart_gestion_events:+,.0f} FCFA",
            'ecart': ecart_gestion_events,
            'gravite': 'warning' if abs(ecart_gestion_events) < 50000 else 'danger'
        })

    # ===================================================================
    # LOG DE L'ACTION - DIAGNOSTIC
    # ===================================================================
    log_user_action(
        user,
        "DIAGNOSTIC_SERIES_STOCK",
        f"Diagnostic des séries stock pour {poste.nom} - "
        f"Modifiables: {valeur_modifiables:,.0f} FCFA ({tickets_modifiables} tickets) - "
        f"Transférées: {valeur_transferees:,.0f} FCFA ({tickets_transferees} tickets) - "
        f"Total séries: {valeur_series_total:,.0f} FCFA - "
        f"GestionStock: {valeur_gestion_stock:,.0f} FCFA - "
        f"Event Sourcing: {valeur_event_sourcing:,.0f} FCFA - "
        f"Divergences: {len(divergences)}",
        request,
        poste=poste.nom,
        valeur_modifiables=str(valeur_modifiables),
        valeur_transferees=str(valeur_transferees),
        valeur_gestion_stock=str(valeur_gestion_stock),
        valeur_event_sourcing=str(valeur_event_sourcing),
        nb_divergences=len(divergences)
    )

    # ===================================================================
    # TRAITEMENT POST (INCHANGÉ)
    # ===================================================================
    couleurs_existantes = CouleurTicket.objects.all().order_by('code_normalise')

    if request.method == 'POST':
        modifications = []
        suppressions = []
        erreurs = []

        for serie in series_modifiables:
            prefix = f"serie_{serie.id}"

            supprimer = request.POST.get(f"{prefix}_supprimer") == 'on'

            if supprimer:
                suppressions.append(serie)
                continue

            nouvelle_couleur = request.POST.get(f"{prefix}_couleur", '').strip()
            nouveau_premier = request.POST.get(f"{prefix}_premier", '')
            nouveau_dernier = request.POST.get(f"{prefix}_dernier", '')

            try:
                nouveau_premier = int(nouveau_premier) if nouveau_premier else serie.numero_premier
                nouveau_dernier = int(nouveau_dernier) if nouveau_dernier else serie.numero_dernier
            except ValueError:
                erreurs.append(f"Série #{serie.id}: Numéros invalides")
                continue

            couleur_obj = CouleurTicket.obtenir_ou_creer(nouvelle_couleur) if nouvelle_couleur else serie.couleur

            a_change = (
                couleur_obj.id != serie.couleur.id or
                nouveau_premier != serie.numero_premier or
                nouveau_dernier != serie.numero_dernier
            )

            if a_change:
                if nouveau_premier > nouveau_dernier:
                    erreurs.append(
                        f"Série {serie.couleur.libelle_affichage} #{serie.numero_premier}-{serie.numero_dernier}: "
                        f"Le premier numéro doit être <= au dernier"
                    )
                    continue

                modifications.append({
                    'serie': serie,
                    'ancienne_couleur': serie.couleur.libelle_affichage,
                    'nouvelle_couleur': couleur_obj,
                    'ancien_premier': serie.numero_premier,
                    'nouveau_premier': nouveau_premier,
                    'ancien_dernier': serie.numero_dernier,
                    'nouveau_dernier': nouveau_dernier
                })

        if erreurs:
            for erreur in erreurs:
                messages.error(request, erreur)
        else:
            try:
                with transaction.atomic():
                    for serie in suppressions:
                        stock_obj, _ = GestionStock.objects.get_or_create(
                            poste=poste,
                            defaults={'valeur_monetaire': Decimal('0')}
                        )
                        stock_avant = stock_obj.valeur_monetaire
                        stock_obj.valeur_monetaire -= serie.valeur_monetaire
                        stock_obj.save()

                        HistoriqueStock.objects.create(
                            poste=poste,
                            type_mouvement='DEBIT',
                            type_stock='regularisation',
                            montant=serie.valeur_monetaire,
                            nombre_tickets=serie.nombre_tickets,
                            stock_avant=stock_avant,
                            stock_apres=stock_obj.valeur_monetaire,
                            effectue_par=user,
                            commentaire=f"Suppression administrative: {serie.couleur.libelle_affichage} "
                                       f"#{serie.numero_premier}-{serie.numero_dernier}"
                        )

                        # CORRECTION: Créer aussi un StockEvent
                        StockEvent.objects.create(
                            poste=poste,
                            event_type='AJUSTEMENT',
                            event_datetime=timezone.now(),
                            montant_variation=-serie.valeur_monetaire,
                            nombre_tickets_variation=-serie.nombre_tickets,
                            stock_resultant=stock_obj.valeur_monetaire,
                            tickets_resultants=int(stock_obj.valeur_monetaire / 500),
                            effectue_par=user,
                            commentaire=f"Suppression administrative série {serie.couleur.libelle_affichage}"
                        )

                        logger.info(
                            f"🗑️ SUPPRESSION SÉRIE | {get_user_short_description(user)} | "
                            f"Poste: {poste.nom} | {serie.couleur.libelle_affichage} "
                            f"#{serie.numero_premier}-{serie.numero_dernier}"
                        )

                        serie.delete()

                    for mod in modifications:
                        serie = mod['serie']
                        ancienne_valeur = serie.valeur_monetaire

                        serie.couleur = mod['nouvelle_couleur']
                        serie.numero_premier = mod['nouveau_premier']
                        serie.numero_dernier = mod['nouveau_dernier']
                        serie.nombre_tickets = mod['nouveau_dernier'] - mod['nouveau_premier'] + 1
                        serie.valeur_monetaire = Decimal(serie.nombre_tickets) * Decimal('500')
                        serie.save()

                        nouvelle_valeur = serie.valeur_monetaire

                        if ancienne_valeur != nouvelle_valeur:
                            stock_obj, _ = GestionStock.objects.get_or_create(
                                poste=poste,
                                defaults={'valeur_monetaire': Decimal('0')}
                            )
                            difference = nouvelle_valeur - ancienne_valeur
                            stock_obj.valeur_monetaire += difference
                            stock_obj.save()

                            # CORRECTION: Créer aussi un StockEvent pour la modification
                            StockEvent.objects.create(
                                poste=poste,
                                event_type='AJUSTEMENT',
                                event_datetime=timezone.now(),
                                montant_variation=difference,
                                nombre_tickets_variation=int(difference / 500),
                                stock_resultant=stock_obj.valeur_monetaire,
                                tickets_resultants=int(stock_obj.valeur_monetaire / 500),
                                effectue_par=user,
                                commentaire=f"Modification série {mod['ancienne_couleur']} -> {mod['nouvelle_couleur'].libelle_affichage}"
                            )

                        logger.info(
                            f"✏️ MODIFICATION SÉRIE | {get_user_short_description(user)} | "
                            f"Poste: {poste.nom} | {mod['ancienne_couleur']} "
                            f"#{mod['ancien_premier']}-{mod['ancien_dernier']} -> "
                            f"{mod['nouvelle_couleur'].libelle_affichage} "
                            f"#{mod['nouveau_premier']}-{mod['nouveau_dernier']}"
                        )

                    log_user_action(
                        user,
                        "MODIFICATION_SERIES_STOCK",
                        f"Modification de séries au poste {poste.nom}: "
                        f"{len(modifications)} modifiée(s), {len(suppressions)} supprimée(s)",
                        request,
                        poste=poste.nom,
                        nb_modifications=len(modifications),
                        nb_suppressions=len(suppressions)
                    )

                    if modifications or suppressions:
                        messages.success(
                            request,
                            f"✅ Opération réussie: {len(modifications)} série(s) modifiée(s), "
                            f"{len(suppressions)} série(s) supprimée(s)"
                        )
                    else:
                        messages.info(request, "Aucune modification effectuée.")

                    return redirect('inventaire:modifier_series_stock', poste_id=poste_id)

            except Exception as e:
                logger.error(
                    f"❌ ERREUR MODIFICATION SÉRIES | {get_user_short_description(user)} | "
                    f"Poste: {poste.nom} | Erreur: {str(e)}",
                    exc_info=True
                )
                messages.error(request, f"Erreur lors de la modification: {str(e)}")

    # ===================================================================
    # CONTEXTE - AVEC TOUTES LES INFORMATIONS
    # ===================================================================
    context = {
        'poste': poste,
        'stock': stock,

        # Séries par catégorie
        'series_modifiables': series_modifiables,
        'series_transferees': series_transferees,

        # Totaux
        'valeur_modifiables': valeur_modifiables,
        'tickets_modifiables': tickets_modifiables,
        'valeur_transferees': valeur_transferees,
        'tickets_transferees': tickets_transferees,
        'valeur_series_total': valeur_series_total,
        'tickets_series_total': tickets_series_total,

        # Comparaison des sources
        'valeur_gestion_stock': valeur_gestion_stock,
        'valeur_event_sourcing': valeur_event_sourcing,
        'tickets_event_sourcing': tickets_event_sourcing,

        # Divergences détectées
        'divergences': divergences,
        'a_divergences': len(divergences) > 0,

        # Autres
        'couleurs_existantes': couleurs_existantes,
        'title': f'Modifier les séries - {poste.nom}'
    }

    return render(request, 'inventaire/modifier_series_stock.html', context)


# ===================================================================
# CORRECTION 2: DIAGNOSTIC COMPLET DU STOCK D'UN POSTE
# ===================================================================

@login_required
def diagnostic_stock(request, poste_id):
    """
    Page de diagnostic complet du stock pour un poste.
    Compare les 3 sources de données et identifie les écarts.
    """
    from accounts.models import Poste
    from .models import GestionStock, SerieTicket, StockEvent
    from django.db.models import Sum
    from decimal import Decimal

    poste = get_object_or_404(Poste, id=poste_id)

    # Vérification des permissions
    if not request.user.is_admin and not is_admin_user(request.user):
        if not user_has_acces_tous_postes(request.user):
            postes_accessibles = get_postes_peage_accessibles(request.user)
            if poste not in postes_accessibles:
                messages.error(request, "Vous n'avez pas accès à ce poste.")
                return redirect('inventaire:liste_postes_stocks')

    # 1. Données de GestionStock
    stock, _ = GestionStock.objects.get_or_create(
        poste=poste,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    valeur_gestion = stock.valeur_monetaire or Decimal('0')
    tickets_gestion = int(valeur_gestion / 500) if valeur_gestion else 0

    # 2. Données des SerieTicket
    series_stock = SerieTicket.objects.filter(poste=poste, statut='stock')

    # Séries par type d'entrée
    series_imprimerie = series_stock.filter(type_entree='imprimerie_nationale')
    series_regularisation = series_stock.filter(type_entree='regularisation')
    series_transfert = series_stock.filter(type_entree='transfert_recu')

    # Totaux SerieTicket
    agg_series = series_stock.aggregate(
        total_valeur=Sum('valeur_monetaire'),
        total_tickets=Sum('nombre_tickets')
    )
    valeur_series = Decimal(str(agg_series['total_valeur'] or 0))
    tickets_series = agg_series['total_tickets'] or 0

    # 3. Données Event Sourcing
    try:
        result = StockEvent.get_stock_at_date(poste)
        if result and isinstance(result, tuple) and len(result) == 2:
            valeur_event = Decimal(str(result[0] or 0))
            tickets_event = result[1] or 0
        else:
            valeur_event = Decimal('0')
            tickets_event = 0
    except Exception as e:
        import logging
        logger = logging.getLogger('supper')
        logger.warning(f"Erreur EventSourcing pour {poste.nom}: {e}")
        valeur_event = Decimal('0')
        tickets_event = 0

    # 4. Calcul des écarts - SEULEMENT si différence significative (> 1 FCFA)
    ecarts = []
    seuil_tolerance = Decimal('1')  # Tolérance d'arrondi

    # Écart GestionStock vs SerieTicket
    ecart_gestion_series = valeur_gestion - valeur_series
    if abs(ecart_gestion_series) > seuil_tolerance:
        ecarts.append({
            'source1': 'GestionStock',
            'source2': 'SerieTicket',
            'ecart': ecart_gestion_series,
            'ecart_abs': abs(ecart_gestion_series),
            'gravite': 'danger' if abs(ecart_gestion_series) > 100000 else 'warning',
            'message': f"Écart de {abs(ecart_gestion_series):,.0f} FCFA entre GestionStock et SerieTicket"
        })

    # Écart GestionStock vs EventSourcing
    ecart_gestion_event = valeur_gestion - valeur_event
    if abs(ecart_gestion_event) > seuil_tolerance:
        ecarts.append({
            'source1': 'GestionStock',
            'source2': 'EventSourcing',
            'ecart': ecart_gestion_event,
            'ecart_abs': abs(ecart_gestion_event),
            'gravite': 'danger' if abs(ecart_gestion_event) > 100000 else 'warning',
            'message': f"Écart de {abs(ecart_gestion_event):,.0f} FCFA entre GestionStock et EventSourcing"
        })

    # Écart SerieTicket vs EventSourcing
    ecart_series_event = valeur_series - valeur_event
    if abs(ecart_series_event) > seuil_tolerance:
        ecarts.append({
            'source1': 'SerieTicket',
            'source2': 'EventSourcing',
            'ecart': ecart_series_event,
            'ecart_abs': abs(ecart_series_event),
            'gravite': 'info',
            'message': f"Écart de {abs(ecart_series_event):,.0f} FCFA entre SerieTicket et EventSourcing"
        })

    # Journalisation
    try:
        log_user_action(
            request.user,
            "Diagnostic stock",
            f"Diagnostic du stock pour {poste.nom} - "
            f"GestionStock: {valeur_gestion:,.0f} FCFA, "
            f"SerieTicket: {valeur_series:,.0f} FCFA, "
            f"EventSourcing: {valeur_event:,.0f} FCFA - "
            f"{len(ecarts)} écart(s) détecté(s)",
            request
        )
    except Exception:
        pass  # Ne pas bloquer si la journalisation échoue

    # Déterminer si cohérent
    a_ecarts = len(ecarts) > 0
    nb_ecarts = len(ecarts)

    context = {
        'poste': poste,
        'stock': stock,

        # GestionStock
        'valeur_gestion': valeur_gestion,
        'tickets_gestion': tickets_gestion,

        # SerieTicket
        'valeur_series': valeur_series,
        'tickets_series': tickets_series,
        'series_imprimerie': series_imprimerie,
        'series_regularisation': series_regularisation,
        'series_transfert': series_transfert,
        'nb_series_imprimerie': series_imprimerie.count(),
        'nb_series_regularisation': series_regularisation.count(),
        'nb_series_transfert': series_transfert.count(),

        # EventSourcing
        'valeur_event': valeur_event,
        'tickets_event': tickets_event,

        # Écarts
        'ecarts': ecarts,
        'a_ecarts': a_ecarts,
        'nb_ecarts': nb_ecarts,
    }

    return render(request, 'inventaire/diagnostic_stock.html', context)

# ===================================================================
# CORRECTION 3: RÉCONCILIATION DU STOCK
# ===================================================================

@login_required
def reconcilier_stock(request, poste_id):
    """
    Vue pour corriger les divergences de stock en synchronisant les 3 sources.

    Actions possibles:
    1. Synchroniser GestionStock avec le total des SerieTicket
    2. Reconstruire les StockEvent depuis HistoriqueStock
    3. Créer un ajustement manuel
    """
    user = request.user

    if not is_admin_user(user):
        log_acces_refuse(user, "reconcilier_stock", "Administrateur requis")
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('inventaire:liste_postes_stocks')

    poste = get_object_or_404(Poste, id=poste_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        try:
            with transaction.atomic():
                if action == 'sync_gestion_series':
                    # Synchroniser GestionStock avec SerieTicket
                    total_series = SerieTicket.objects.filter(
                        poste=poste,
                        statut='stock'
                    ).aggregate(
                        total_valeur=Sum('valeur_monetaire'),
                        total_tickets=Sum('nombre_tickets')
                    )

                    nouvelle_valeur = total_series['total_valeur'] or Decimal('0')
                    nouveaux_tickets = total_series['total_tickets'] or 0

                    stock, _ = GestionStock.objects.get_or_create(
                        poste=poste,
                        defaults={'valeur_monetaire': Decimal('0')}
                    )
                    ancienne_valeur = stock.valeur_monetaire

                    stock.valeur_monetaire = nouvelle_valeur
                    stock.nombre_tickets = nouveaux_tickets
                    stock.save()

                    # Créer un historique de l'ajustement
                    difference = nouvelle_valeur - ancienne_valeur
                    if difference != 0:
                        HistoriqueStock.objects.create(
                            poste=poste,
                            type_mouvement='CREDIT' if difference > 0 else 'DEBIT',
                            type_stock='regularisation',
                            montant=abs(difference),
                            nombre_tickets=int(abs(difference) / 500),
                            stock_avant=ancienne_valeur,
                            stock_apres=nouvelle_valeur,
                            effectue_par=user,
                            commentaire=f"Synchronisation administrative GestionStock avec SerieTicket"
                        )

                        # Créer le StockEvent correspondant
                        StockEvent.objects.create(
                            poste=poste,
                            event_type='AJUSTEMENT',
                            event_datetime=timezone.now(),
                            montant_variation=difference,
                            nombre_tickets_variation=int(difference / 500),
                            stock_resultant=nouvelle_valeur,
                            tickets_resultants=nouveaux_tickets,
                            effectue_par=user,
                            commentaire=f"Synchronisation GestionStock: {ancienne_valeur:,.0f} -> {nouvelle_valeur:,.0f} FCFA"
                        )

                    log_user_action(
                        user,
                        "RECONCILIATION_STOCK_SYNC_SERIES",
                        f"Synchronisation GestionStock avec SerieTicket pour {poste.nom} - "
                        f"Ancienne valeur: {ancienne_valeur:,.0f} FCFA - "
                        f"Nouvelle valeur: {nouvelle_valeur:,.0f} FCFA - "
                        f"Différence: {difference:+,.0f} FCFA",
                        request,
                        poste=poste.nom,
                        ancienne_valeur=str(ancienne_valeur),
                        nouvelle_valeur=str(nouvelle_valeur),
                        difference=str(difference)
                    )

                    messages.success(
                        request,
                        f"✅ GestionStock synchronisé: {nouvelle_valeur:,.0f} FCFA "
                        f"(différence: {difference:+,.0f} FCFA)"
                    )

                elif action == 'reconstruire_events':
                    # Reconstruire les événements depuis HistoriqueStock
                    stock_final, tickets_final = StockEvent.recalculate_stock_from_historique(poste)

                    log_user_action(
                        user,
                        "RECONCILIATION_STOCK_REBUILD_EVENTS",
                        f"Reconstruction des StockEvent pour {poste.nom} - "
                        f"Stock final: {stock_final:,.0f} FCFA ({tickets_final} tickets)",
                        request,
                        poste=poste.nom,
                        stock_final=str(stock_final),
                        tickets_final=tickets_final
                    )

                    messages.success(
                        request,
                        f"✅ Événements reconstruits. Stock calculé: {stock_final:,.0f} FCFA"
                    )

                elif action == 'sync_complet':
                    # Synchronisation complète: SerieTicket -> GestionStock -> Events

                    # 1. Calculer le total des séries
                    total_series = SerieTicket.objects.filter(
                        poste=poste,
                        statut='stock'
                    ).aggregate(
                        total_valeur=Sum('valeur_monetaire'),
                        total_tickets=Sum('nombre_tickets')
                    )
                    valeur_reference = total_series['total_valeur'] or Decimal('0')
                    tickets_reference = total_series['total_tickets'] or 0

                    # 2. Mettre à jour GestionStock
                    stock, _ = GestionStock.objects.get_or_create(
                        poste=poste,
                        defaults={'valeur_monetaire': Decimal('0')}
                    )
                    ancienne_valeur = stock.valeur_monetaire
                    stock.valeur_monetaire = valeur_reference
                    stock.nombre_tickets = tickets_reference
                    stock.save()

                    # 3. Reconstruire les événements
                    stock_events_final, tickets_events_final = StockEvent.recalculate_stock_from_historique(poste)

                    # 4. Ajuster si nécessaire
                    ecart_final = valeur_reference - stock_events_final
                    if abs(ecart_final) > Decimal('1'):
                        StockEvent.objects.create(
                            poste=poste,
                            event_type='AJUSTEMENT',
                            event_datetime=timezone.now(),
                            montant_variation=ecart_final,
                            nombre_tickets_variation=int(ecart_final / 500),
                            stock_resultant=valeur_reference,
                            tickets_resultants=tickets_reference,
                            effectue_par=user,
                            commentaire=f"Ajustement final synchronisation complète"
                        )

                    log_user_action(
                        user,
                        "RECONCILIATION_STOCK_COMPLET",
                        f"Synchronisation complète du stock pour {poste.nom} - "
                        f"Valeur finale: {valeur_reference:,.0f} FCFA ({tickets_reference} tickets)",
                        request,
                        poste=poste.nom,
                        valeur_finale=str(valeur_reference),
                        tickets_final=tickets_reference
                    )

                    messages.success(
                        request,
                        f"✅ Synchronisation complète effectuée. Stock: {valeur_reference:,.0f} FCFA"
                    )

                return redirect('inventaire:diagnostic_stock', poste_id=poste_id)

        except Exception as e:
            logger.error(
                f"❌ ERREUR RÉCONCILIATION | {get_user_short_description(user)} | "
                f"Poste: {poste.nom} | Action: {action} | Erreur: {str(e)}",
                exc_info=True
            )
            messages.error(request, f"Erreur lors de la réconciliation: {str(e)}")

    return redirect('inventaire:diagnostic_stock', poste_id=poste_id)


# ===================================================================
# API: VÉRIFICATION RAPIDE DU STOCK (JSON)
# ===================================================================

@login_required
def api_verification_stock(request, poste_id):
    """
    API JSON pour vérifier rapidement l'état du stock d'un poste.
    Retourne les 3 valeurs et les écarts éventuels.
    """
    user = request.user
    poste = get_object_or_404(Poste, id=poste_id)

    # Vérifier l'accès
    if not is_admin_user(user) and not check_poste_access(user, poste):
        return JsonResponse({'error': 'Accès non autorisé'}, status=403)

    # Calculer les 3 sources
    stock, _ = GestionStock.objects.get_or_create(
        poste=poste,
        defaults={'valeur_monetaire': Decimal('0')}
    )

    total_series = SerieTicket.objects.filter(
        poste=poste,
        statut='stock'
    ).aggregate(
        total_valeur=Sum('valeur_monetaire'),
        total_tickets=Sum('nombre_tickets')
    )

    valeur_events, tickets_events = StockEvent.get_stock_at_date(poste, date.today())

    # Construire la réponse
    valeur_gestion = float(stock.valeur_monetaire)
    valeur_series = float(total_series['total_valeur'] or 0)
    valeur_es = float(valeur_events)

    ecarts = []
    if abs(valeur_gestion - valeur_series) > 1:
        ecarts.append(f"GestionStock vs Séries: {valeur_gestion - valeur_series:+,.0f}")
    if abs(valeur_gestion - valeur_es) > 1:
        ecarts.append(f"GestionStock vs Events: {valeur_gestion - valeur_es:+,.0f}")

    return JsonResponse({
        'poste': {
            'id': poste.id,
            'nom': poste.nom
        },
        'stock': {
            'gestion_stock': valeur_gestion,
            'series_tickets': valeur_series,
            'event_sourcing': valeur_es
        },
        'coherent': len(ecarts) == 0,
        'ecarts': ecarts
    })


# ===================================================================
# FONCTION UTILITAIRE: EXÉCUTION DU CHARGEMENT
# ===================================================================

def executer_chargement_stock_avec_series(poste, couleur, numero_premier, numero_dernier,
                                          type_stock, user, commentaire=None):
    """
    VERSION CORRIGÉE V4 : Avec remplissage de historique_source.

    Args:
        poste: Instance du modèle Poste
        couleur: Instance du modèle CouleurTicket
        numero_premier: Numéro du premier ticket
        numero_dernier: Numéro du dernier ticket
        type_stock: Type de stock ('imprimerie_nationale' ou 'regularisation')
        user: Utilisateur effectuant l'opération
        commentaire: Commentaire optionnel

    Returns:
        tuple: (success, message, serie, historique)
    """
    try:
        with transaction.atomic():
            now = timezone.now()
            nombre_tickets = numero_dernier - numero_premier + 1
            montant = Decimal(nombre_tickets) * Decimal('500')

            # 1. Créer la série de tickets
            serie = SerieTicket.objects.create(
                poste=poste,
                couleur=couleur,
                numero_premier=numero_premier,
                numero_dernier=numero_dernier,
                statut='stock',
                type_entree=type_stock,
                commentaire=commentaire or f"Chargement {type_stock}",
                date_reception=now,
                responsable_reception=user
            )

            # 2. Mettre à jour le stock global
            stock, created = GestionStock.objects.get_or_create(
                poste=poste,
                defaults={'valeur_monetaire': Decimal('0'), 'nombre_tickets': 0}
            )

            stock_avant = stock.valeur_monetaire
            stock.valeur_monetaire += montant
            stock.nombre_tickets += nombre_tickets
            stock.save()

            # 3. Préparer les labels
            type_stock_label = (
                "Régularisation" if type_stock == 'regularisation'
                else "Imprimerie Nationale"
            )

            type_stock_historique = 'imprimerie_nationale' if type_stock in ['imprimerie', 'imprimerie_nationale'] else type_stock

            commentaire_historique = (
                f"{type_stock_label} - Série {couleur.libelle_affichage} "
                f"#{numero_premier}-{numero_dernier}"
            )
            if commentaire:
                commentaire_historique += f"\n{commentaire}"

            # Préparer le JSONField
            details_approvisionnement = {
                'type': type_stock_label,
                'type_code': type_stock_historique,
                'series': [{
                    'couleur_id': couleur.id,
                    'couleur_nom': couleur.libelle_affichage,
                    'couleur_code': couleur.code_normalise,
                    'numero_premier': numero_premier,
                    'numero_dernier': numero_dernier,
                    'nombre_tickets': nombre_tickets,
                    'valeur': str(montant),
                    'serie_id': serie.id
                }],
                'total_tickets': nombre_tickets,
                'total_valeur': str(montant),
                'date_operation': now.isoformat()
            }

            # 4. Créer l'historique
            historique = HistoriqueStock.objects.create(
                poste=poste,
                type_mouvement='CREDIT',
                type_stock=type_stock_historique,
                montant=montant,
                nombre_tickets=nombre_tickets,
                stock_avant=stock_avant,
                stock_apres=stock.valeur_monetaire,
                effectue_par=user,
                commentaire=commentaire_historique,
                date_mouvement=now,
                numero_premier_ticket=numero_premier,
                numero_dernier_ticket=numero_dernier,
                couleur_principale=couleur,
                details_approvisionnement=details_approvisionnement
            )

            # 5. Associer la série (ManyToMany existant)
            historique.series_tickets_associees.add(serie)

            # === NOUVEAU V4: Lier la série à son historique source ===
            serie.historique_source = historique
            serie.save(update_fields=['historique_source'])

            # 6. Créer l'événement Event Sourcing
            event_type = 'REGULARISATION' if type_stock == 'regularisation' else 'CHARGEMENT'

            metadata = {
                'type_stock': type_stock,
                'type_stock_label': type_stock_label,
                'serie': {
                    'id': serie.id,
                    'couleur': couleur.libelle_affichage,
                    'couleur_id': couleur.id,
                    'couleur_code': couleur.code_normalise,
                    'numero_premier': numero_premier,
                    'numero_dernier': numero_dernier,
                    'nombre_tickets': nombre_tickets,
                    'valeur': str(montant)
                },
                'historique_id': historique.id,
                'operation': 'chargement_stock_avec_series'
            }

            StockEvent.objects.create(
                poste=poste,
                event_type=event_type,
                event_datetime=now,
                montant_variation=montant,
                nombre_tickets_variation=nombre_tickets,
                stock_resultant=stock.valeur_monetaire,
                tickets_resultants=stock.nombre_tickets,
                effectue_par=user,
                reference_id=str(historique.id),
                reference_type='HistoriqueStock',
                metadata=metadata,
                commentaire=commentaire or f"Chargement série {couleur.libelle_affichage}"
            )

            # 7. Notifications aux chefs de poste
            chefs = UtilisateurSUPPER.objects.filter(
                poste_affectation=poste,
                habilitation__in=['chef_peage', 'chef_pesage'],
                is_active=True
            )

            for chef in chefs:
                NotificationUtilisateur.objects.create(
                    destinataire=chef,
                    titre=f"Nouveau stock de tickets - {type_stock_label}",
                    message=(
                        f"Stock {type_stock_label} crédité : "
                        f"Série {couleur.libelle_affichage} "
                        f"#{numero_premier}-{numero_dernier} "
                        f"({nombre_tickets:,} tickets = {montant:,.0f} FCFA) "
                        f"pour {poste.nom}"
                    ),
                    type_notification='info'
                )

            # 8. Log
            logger.info(
                f"✅ Chargement stock réussi : {couleur.libelle_affichage} "
                f"#{numero_premier}-{numero_dernier} pour {poste.nom}"
            )

            return True, (
                f"✅ Chargement réussi : {nombre_tickets:,} tickets "
                f"({montant:,.0f} FCFA)"
            ), serie, historique

    except Exception as e:
        logger.error(
            f"Erreur lors du chargement stock : {str(e)}",
            exc_info=True
        )
        return False, f"❌ Erreur lors du chargement : {str(e)}", None, None


# ===================================================================
# VUE: MON STOCK (CHEF DE POSTE)
# ===================================================================

@login_required
def mon_stock(request):
    """
    Vue pour qu'un chef de poste consulte son stock.

    AVANT:
        - @login_required seul
        - Vérifie juste poste_affectation

    APRÈS:
        - Permission: peut_voir_mon_stock_peage OU chef_peage
        - Logs détaillés
        - Variables contexte IDENTIQUES
    """
    user = request.user

    # ===================================================================
    # VÉRIFICATION DES PERMISSIONS
    # ===================================================================
    if not peut_voir_mon_stock(user):
        log_acces_refuse(
            user,
            "mon_stock",
            "Permission peut_voir_mon_stock_peage manquante"
        )
        messages.error(request, "Vous n'avez pas la permission de consulter ce stock.")
        logger.warning(
            f"🚫 ACCÈS REFUSÉ | {get_user_short_description(user)} | "
            f"Vue: mon_stock"
        )
        return redirect('common:dashboard')

    if not user.poste_affectation:
        messages.error(request, "Vous n'êtes affecté à aucun poste")
        logger.warning(
            f"⚠️ PAS DE POSTE | {get_user_short_description(user)} | "
            f"Tentative d'accès à mon_stock sans poste d'affectation"
        )
        return redirect('common:dashboard')

    poste = user.poste_affectation

    logger.info(
        f"📊 MON STOCK | {get_user_short_description(user)} | "
        f"Consultation du stock de {poste.nom}"
    )

    # ===================================================================
    # RÉCUPÉRATION DES DONNÉES
    # ===================================================================
    stock, created = GestionStock.objects.get_or_create(
        poste=poste,
        defaults={'valeur_monetaire': Decimal('0')}
    )

    # Statistiques du mois
    date_fin = date.today()
    date_debut = date_fin - timedelta(days=30)

    ventes_mois = RecetteJournaliere.objects.filter(
        poste=poste,
        date__range=[date_debut, date_fin]
    ).aggregate(
        total=Sum('montant_declare'),
        nombre=models.Count('id')
    )

    vente_moyenne_journaliere = Decimal('0')
    if ventes_mois['total'] and ventes_mois['nombre'] > 0:
        vente_moyenne_journaliere = ventes_mois['total'] / ventes_mois['nombre']

    # Calcul date d'épuisement
    date_epuisement = None
    if vente_moyenne_journaliere > 0:
        jours_restants = int(stock.valeur_monetaire / vente_moyenne_journaliere)
        date_epuisement = date_fin + timedelta(days=jours_restants - 7)

    # Historique récent
    historique = HistoriqueStock.objects.filter(
        poste=poste
    ).order_by('-date_mouvement')[:10]

    # Log de l'action
    log_user_action(
        user,
        "CONSULTATION_MON_STOCK",
        f"Consultation du stock du poste {poste.nom} - "
        f"Valeur: {stock.valeur_monetaire:,.0f} FCFA",
        request,
        poste=poste.nom,
        valeur_stock=str(stock.valeur_monetaire),
        nombre_tickets=stock.nombre_tickets
    )

    # ===================================================================
    # CONTEXTE - VARIABLES IDENTIQUES À L'ANCIENNE VERSION
    # ===================================================================
    context = {
        'poste': poste,
        'stock': stock,
        'ventes_mois': ventes_mois,
        'date_epuisement': date_epuisement,
        'historique': historique,
        'title': f'Mon stock - {poste.nom}',
    }

    return render(request, 'inventaire/mon_stock.html', context)


# ===================================================================
# VUE: HISTORIQUE STOCK D'UN POSTE
# ===================================================================

@login_required
def historique_stock(request, poste_id):
    """
    Vue complète de l'historique d'un poste.

    AVANT:
        - Vérifie is_admin OU peut_acceder_poste
        - Pas de logs détaillés

    APRÈS:
        - Permission: peut_voir_historique_stock_peage
        - Vérification d'accès au poste avec check_poste_access
        - Logs détaillés
        - Variables contexte IDENTIQUES
    """
    user = request.user
    poste = get_object_or_404(Poste, id=poste_id)

    # ===================================================================
    # VÉRIFICATION DES PERMISSIONS
    # ===================================================================
    if not peut_voir_historique_stock(user):
        log_acces_refuse(
            user,
            f"historique_stock (poste: {poste.nom})",
            "Permission peut_voir_historique_stock_peage manquante"
        )
        messages.error(request, "Vous n'avez pas la permission de voir l'historique.")
        logger.warning(
            f"🚫 ACCÈS REFUSÉ | {get_user_short_description(user)} | "
            f"Vue: historique_stock | Poste: {poste.nom}"
        )
        return redirect('inventaire:inventaire_list')

    # Vérifier l'accès au poste (sauf admin qui peut tout voir)
    if not is_admin_user(user) and not user_has_acces_tous_postes(user):
        if not verifier_acces_poste_stock(user, poste):
            log_acces_refuse(
                user,
                f"historique_stock (poste: {poste.nom})",
                "Accès au poste non autorisé"
            )
            messages.error(request, "Accès non autorisé")
            logger.warning(
                f"🚫 ACCÈS REFUSÉ | {get_user_short_description(user)} | "
                f"Vue: historique_stock | Poste: {poste.nom} | Raison: Pas d'accès au poste"
            )
            return redirect('inventaire:inventaire_list')

    logger.info(
        f"📜 HISTORIQUE STOCK | {get_user_short_description(user)} | "
        f"Consultation historique de {poste.nom}"
    )

    # ===================================================================
    # FILTRAGE DES DONNÉES
    # ===================================================================
    type_mouvement = request.GET.get('type', 'tous')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')

    historiques = HistoriqueStock.objects.filter(poste=poste)

    if type_mouvement != 'tous':
        historiques = historiques.filter(type_mouvement=type_mouvement)

    if date_debut:
        historiques = historiques.filter(date_mouvement__gte=date_debut)

    if date_fin:
        historiques = historiques.filter(date_mouvement__lte=date_fin)

    historiques = historiques.select_related('effectue_par', 'reference_recette')

    # Séparation approvisionnements/déstockages
    approvisionnements = historiques.filter(type_mouvement='CREDIT')
    destockages = historiques.filter(type_mouvement='DEBIT')

    # Pagination
    paginator = Paginator(historiques.order_by('-date_mouvement'), 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Stock actuel
    stock = GestionStock.objects.filter(poste=poste).first()

    # Liste des postes pour le filtre admin
    postes_liste = None
    if is_admin_user(user) or user_has_acces_tous_postes(user):
        postes_liste = Poste.objects.filter(is_active=True).order_by('nom')

    # Log de l'action
    log_user_action(
        user,
        "CONSULTATION_HISTORIQUE_STOCK",
        f"Consultation historique de {poste.nom} - "
        f"{historiques.count()} mouvement(s)",
        request,
        poste=poste.nom,
        nb_mouvements=historiques.count(),
        filtres={'type': type_mouvement, 'date_debut': date_debut, 'date_fin': date_fin}
    )

    # ===================================================================
    # CONTEXTE - VARIABLES IDENTIQUES À L'ANCIENNE VERSION
    # ===================================================================
    context = {
        'poste': poste,
        'page_obj': page_obj,
        'stock': stock,
        'total_approvisionnements': approvisionnements.aggregate(Sum('montant'))['montant__sum'] or 0,
        'total_destockages': destockages.aggregate(Sum('montant'))['montant__sum'] or 0,
        'nombre_approvisionnements': approvisionnements.count(),
        'nombre_destockages': destockages.count(),
        'filters': {
            'type': type_mouvement,
            'date_debut': date_debut,
            'date_fin': date_fin
        },
        'title': f'Historique stock - {poste.nom}',
        'postes_liste': postes_liste,
        'is_admin': is_admin_user(user)
    }

    return render(request, 'inventaire/historique_stock.html', context)


# ===================================================================
# VUE: DÉTAIL D'UN HISTORIQUE DE STOCK
# ===================================================================

@login_required
def detail_historique_stock(request, historique_id):
    """
    Vue pour afficher les détails complets d'une opération de stock.

    AVANT:
        - Vérification basique peut_acceder_poste
        - Pas de logs détaillés

    APRÈS:
        - Permission: peut_voir_historique_stock_peage
        - Vérification d'accès au poste
        - Logs détaillés
        - Variables contexte IDENTIQUES
    """
    import re
    from collections import defaultdict

    user = request.user

    # ===================================================================
    # RÉCUPÉRATION DE L'HISTORIQUE
    # ===================================================================
    historique = get_object_or_404(
        HistoriqueStock.objects.select_related(
            'poste',
            'effectue_par',
            'reference_recette',
            'poste_origine',
            'poste_destination',
            'couleur_principale'
        ).prefetch_related(
            'series_tickets_associees',
            'series_tickets_associees__couleur'
        ),
        id=historique_id
    )

    poste = historique.poste

    # ===================================================================
    # VÉRIFICATION DES PERMISSIONS
    # ===================================================================
    if not peut_voir_historique_stock(user):
        log_acces_refuse(
            user,
            f"detail_historique_stock (historique: {historique_id})",
            "Permission peut_voir_historique_stock_peage manquante"
        )
        messages.error(request, "Vous n'avez pas la permission de voir ce détail.")
        logger.warning(
            f"🚫 ACCÈS REFUSÉ | {get_user_short_description(user)} | "
            f"Vue: detail_historique_stock | Historique: {historique_id}"
        )
        return HttpResponseForbidden("Vous n'avez pas la permission d'accéder à cette page")

    # Vérifier l'accès au poste
    if not is_admin_user(user) and not user_has_acces_tous_postes(user):
        if not verifier_acces_poste_stock(user, poste):
            log_acces_refuse(
                user,
                f"detail_historique_stock (poste: {poste.nom})",
                "Accès au poste non autorisé"
            )
            logger.warning(
                f"🚫 ACCÈS REFUSÉ | {get_user_short_description(user)} | "
                f"Vue: detail_historique_stock | Poste: {poste.nom}"
            )
            return HttpResponseForbidden("Vous n'avez pas accès à ce poste")

    logger.info(
        f"🔍 DÉTAIL HISTORIQUE | {get_user_short_description(user)} | "
        f"Historique ID: {historique_id} | Poste: {poste.nom} | "
        f"Type: {historique.type_mouvement}"
    )

    # ===================================================================
    # FONCTION: CALCUL DU STOCK VIA HISTORIQUES
    # ===================================================================
    def calculer_stock_via_historiques(poste_cible, date_reference):
        historiques_avant = HistoriqueStock.objects.filter(
            poste=poste_cible,
            date_mouvement__lt=date_reference
        )

        totaux_credit = historiques_avant.filter(
            type_mouvement='CREDIT'
        ).aggregate(
            total_montant=Sum('montant'),
            total_tickets=Sum('nombre_tickets')
        )

        totaux_debit = historiques_avant.filter(
            type_mouvement='DEBIT'
        ).aggregate(
            total_montant=Sum('montant'),
            total_tickets=Sum('nombre_tickets')
        )

        montant_credit = totaux_credit['total_montant'] or Decimal('0')
        montant_debit = totaux_debit['total_montant'] or Decimal('0')
        tickets_credit = totaux_credit['total_tickets'] or 0
        tickets_debit = totaux_debit['total_tickets'] or 0

        stock_valeur = max(Decimal('0'), montant_credit - montant_debit)
        stock_tickets = max(0, tickets_credit - tickets_debit)

        return stock_valeur, stock_tickets

    # ===================================================================
    # FONCTION: EXTRACTION DES SÉRIES
    # ===================================================================
    def extraire_series_depuis_historique(hist):
        series = []

        # Source 1: Champs structurés directs
        if (hasattr(hist, 'couleur_principale') and hist.couleur_principale and
            hasattr(hist, 'numero_premier_ticket') and hist.numero_premier_ticket and
            hasattr(hist, 'numero_dernier_ticket') and hist.numero_dernier_ticket):

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

        # Source 2: JSONField details_approvisionnement
        if (hasattr(hist, 'details_approvisionnement') and
            hist.details_approvisionnement and
            isinstance(hist.details_approvisionnement, dict)):

            series_data = hist.details_approvisionnement.get('series', [])

            for serie_data in series_data:
                couleur = None
                couleur_nom = serie_data.get('couleur_nom', 'Inconnu')

                if 'couleur_id' in serie_data:
                    couleur = CouleurTicket.objects.filter(id=serie_data['couleur_id']).first()

                if not couleur and couleur_nom:
                    couleur = CouleurTicket.objects.filter(
                        libelle_affichage__icontains=couleur_nom
                    ).first()

                num_premier = serie_data.get('numero_premier')
                num_dernier = serie_data.get('numero_dernier')

                if num_premier and num_dernier:
                    nb_tickets = num_dernier - num_premier + 1
                    series.append({
                        'couleur': couleur,
                        'couleur_nom': couleur.libelle_affichage if couleur else couleur_nom,
                        'numero_premier': num_premier,
                        'numero_dernier': num_dernier,
                        'nombre_tickets': nb_tickets,
                        'valeur': Decimal(str(serie_data.get('valeur', nb_tickets * 500)))
                    })

            if series:
                return series

        # Source 3: Parser le commentaire
        if hasattr(hist, 'commentaire') and hist.commentaire and '#' in hist.commentaire:
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

                        if not couleur:
                            couleur = CouleurTicket.objects.filter(
                                code_normalise__icontains=couleur_nom.lower().replace(' ', '_')
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

        # Source 4: ManyToMany
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

        return series

    # ===================================================================
    # CALCUL DES STOCKS AVANT/APRÈS
    # ===================================================================
    stock_avant_valeur, stock_avant_qte = calculer_stock_via_historiques(
        poste_cible=poste,
        date_reference=historique.date_mouvement
    )

    if historique.type_mouvement == 'CREDIT':
        stock_apres_valeur = stock_avant_valeur + historique.montant
        stock_apres_qte = stock_avant_qte + historique.nombre_tickets
    else:
        stock_apres_valeur = max(Decimal('0'), stock_avant_valeur - historique.montant)
        stock_apres_qte = max(0, stock_avant_qte - historique.nombre_tickets)

    # ===================================================================
    # TRAITEMENT PAR TYPE D'OPÉRATION
    # ===================================================================
    details_approvisionnement = None
    details_vente = None
    info_transfert = None
    series_avant_groupees = defaultdict(list)
    series_apres_groupees = defaultdict(list)

    # CAS 1: TRANSFERT SORTANT
    if historique.type_mouvement == 'DEBIT' and historique.poste_destination:
        info_transfert = {
            'poste_origine': poste,
            'poste_destination': historique.poste_destination,
            'numero_bordereau': historique.numero_bordereau,
            'type': 'sortant',
            'series': []
        }

        series_extraites = extraire_series_depuis_historique(historique)

        for serie in series_extraites:
            couleur_nom = serie.get('couleur_nom', 'Inconnu')
            info_transfert['series'].append({
                'couleur': serie.get('couleur'),
                'numero_premier': serie.get('numero_premier'),
                'numero_dernier': serie.get('numero_dernier'),
                'nombre_tickets': serie.get('nombre_tickets'),
                'valeur_monetaire': serie.get('valeur')
            })
            series_avant_groupees[couleur_nom].append({
                'numero_premier': serie.get('numero_premier'),
                'numero_dernier': serie.get('numero_dernier'),
                'nombre_tickets': serie.get('nombre_tickets'),
                'valeur': serie.get('valeur'),
                'action': 'transférée'
            })

    # CAS 2: TRANSFERT ENTRANT
    elif historique.type_mouvement == 'CREDIT' and historique.poste_origine:
        info_transfert = {
            'poste_origine': historique.poste_origine,
            'poste_destination': poste,
            'numero_bordereau': historique.numero_bordereau,
            'type': 'entrant',
            'series': []
        }

        series_extraites = extraire_series_depuis_historique(historique)

        for serie in series_extraites:
            couleur_nom = serie.get('couleur_nom', 'Inconnu')
            info_transfert['series'].append({
                'couleur': serie.get('couleur'),
                'numero_premier': serie.get('numero_premier'),
                'numero_dernier': serie.get('numero_dernier'),
                'nombre_tickets': serie.get('nombre_tickets'),
                'valeur_monetaire': serie.get('valeur')
            })
            series_apres_groupees[couleur_nom].append({
                'numero_premier': serie.get('numero_premier'),
                'numero_dernier': serie.get('numero_dernier'),
                'nombre_tickets': serie.get('nombre_tickets'),
                'valeur': serie.get('valeur'),
                'action': 'créditée'
            })

    # CAS 3: VENTE
    elif historique.type_mouvement == 'DEBIT' and historique.reference_recette:
        details_vente = historique.reference_recette.details_ventes_tickets.select_related(
            'couleur'
        ).all()

        for detail in details_vente:
            couleur_nom = detail.couleur.libelle_affichage if detail.couleur else 'Inconnu'
            series_avant_groupees[couleur_nom].append({
                'numero_premier': detail.numero_premier,
                'numero_dernier': detail.numero_dernier,
                'nombre_tickets': detail.nombre_tickets,
                'valeur': detail.montant,
                'action': 'vendue'
            })

    # CAS 4: APPROVISIONNEMENT
    elif historique.type_mouvement == 'CREDIT':
        type_label = "Régularisation" if historique.type_stock == 'regularisation' else "Imprimerie Nationale"

        details_approvisionnement = {
            'type': type_label,
            'montant': historique.montant,
            'nombre_tickets': historique.nombre_tickets,
            'series': []
        }

        series_extraites = extraire_series_depuis_historique(historique)

        for serie in series_extraites:
            couleur_nom = serie.get('couleur_nom', 'Inconnu')
            details_approvisionnement['series'].append(serie)
            series_apres_groupees[couleur_nom].append({
                'numero_premier': serie.get('numero_premier'),
                'numero_dernier': serie.get('numero_dernier'),
                'nombre_tickets': serie.get('nombre_tickets'),
                'valeur': serie.get('valeur'),
                'action': 'ajoutée'
            })

    # CAS 5: AUTRE DEBIT
    elif historique.type_mouvement == 'DEBIT':
        series_extraites = extraire_series_depuis_historique(historique)

        for serie in series_extraites:
            couleur_nom = serie.get('couleur_nom', 'Inconnu')
            series_avant_groupees[couleur_nom].append({
                'numero_premier': serie.get('numero_premier'),
                'numero_dernier': serie.get('numero_dernier'),
                'nombre_tickets': serie.get('nombre_tickets'),
                'valeur': serie.get('valeur'),
                'action': 'débitée'
            })

    # Conversion en dict standard
    series_avant_groupees = dict(series_avant_groupees)
    series_apres_groupees = dict(series_apres_groupees)

    # Log de l'action
    log_user_action(
        user,
        "CONSULTATION_DETAIL_HISTORIQUE",
        f"Détail historique {historique_id} - Poste: {poste.nom} - "
        f"Type: {historique.type_mouvement} - Montant: {historique.montant:,.0f} FCFA",
        request,
        historique_id=historique_id,
        poste=poste.nom,
        type_mouvement=historique.type_mouvement,
        montant=str(historique.montant)
    )

    # ===================================================================
    # CONTEXTE - VARIABLES IDENTIQUES À L'ANCIENNE VERSION
    # ===================================================================
    context = {
        'historique': historique,
        'poste': poste,
        'stock_avant_valeur': stock_avant_valeur,
        'stock_avant_qte': stock_avant_qte,
        'stock_apres_valeur': stock_apres_valeur,
        'stock_apres_qte': stock_apres_qte,
        'series_avant_groupees': series_avant_groupees,
        'series_apres_groupees': series_apres_groupees,
        'details_vente': details_vente,
        'info_transfert': info_transfert,
        'details_approvisionnement': details_approvisionnement,
        'title': f'Détail opération - {poste.nom}',
    }

    return render(request, 'inventaire/detail_historique_stock.html', context)


# ===================================================================
# FONCTION: VÉRIFICATION ET CORRECTION DES ASSOCIATIONS
# ===================================================================

def verifier_et_corriger_associations(poste_id=None):
    """
    Vérifie et corrige les associations manquantes entre historiques et séries.

    Cette fonction est conservée identique à l'originale.
    """
    import re

    query = Q(type_mouvement='CREDIT')
    if poste_id:
        query &= Q(poste_id=poste_id)

    historiques = HistoriqueStock.objects.filter(query).prefetch_related('series_tickets_associees')

    corrections = 0

    for historique in historiques:
        if not historique.series_tickets_associees.exists() and historique.commentaire:
            pattern = r"Série\s+(\w+)\s+#(\d+)-(\d+)"
            match = re.search(pattern, historique.commentaire)

            if match:
                couleur_nom = match.group(1)
                num_premier = int(match.group(2))
                num_dernier = int(match.group(3))

                serie = SerieTicket.objects.filter(
                    poste=historique.poste,
                    numero_premier=num_premier,
                    numero_dernier=num_dernier,
                    date_reception=historique.date_mouvement.date()
                ).first()

                if serie:
                    historique.series_tickets_associees.add(serie)
                    corrections += 1
                    logger.info(
                        f"Association corrigée : Historique {historique.id} "
                        f"-> Série {serie.id} ({couleur_nom} #{num_premier}-{num_dernier})"
                    )

    logger.info(f"Vérification terminée : {corrections} associations corrigées")
    return corrections