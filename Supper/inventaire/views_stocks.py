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

from django.http import HttpResponseForbidden
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
from .forms import ChargementStockTicketsForm
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
    # Utilisateurs avec accès tous postes voient tout
    # Sinon, uniquement leur poste (si chef de poste)
    
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
        # Recherche insensible à la casse sur le nom OU le code
        postes = postes.filter(
            models.Q(nom__icontains=search_query) |
            models.Q(code__icontains=search_query)
        )
    
    # ===================================================================
    # CALCUL DES DONNÉES DE STOCK
    # ===================================================================
    stocks_data = []
    
    for poste in postes:
        # Récupérer ou créer le stock
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
            
            # Déterminer le niveau d'alerte
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
    # STATISTIQUES GLOBALES (calculées sur TOUS les postes, pas filtrés)
    # ===================================================================
    # Pour les stats, on récupère tous les postes accessibles (sans filtre de recherche)
    if user_has_acces_tous_postes(user):
        all_postes = Poste.objects.filter(is_active=True, type='peage')
    elif user.poste_affectation:
        all_postes = Poste.objects.filter(id=user.poste_affectation.id, is_active=True)
    else:
        all_postes = Poste.objects.none()
    
    # Calculer les stats globales
    all_stocks = GestionStock.objects.filter(poste__in=all_postes)
    total_stock = all_stocks.aggregate(total=Sum('valeur_monetaire'))['total'] or Decimal('0')
    total_tickets = all_stocks.aggregate(total=Sum('nombre_tickets'))['total'] or 0
    
    # Compter les stocks critiques et faibles (basé sur les données calculées)
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
    # PAGINATION
    # ===================================================================
    paginator = Paginator(stocks_data, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Log de l'action
    log_user_action(
        user,
        "CONSULTATION_LISTE_STOCKS",
        f"Consultation de {len(stocks_data)} poste(s) - "
        f"{'Recherche: ' + search_query + ' - ' if search_query else ''}"
        f"Stock total: {total_stock:,.0f} FCFA - "
        f"Stocks critiques: {stocks_critiques}",
        request,
        nb_postes=len(stocks_data),
        total_stock=str(total_stock),
        stocks_critiques=stocks_critiques,
        stocks_faibles=stocks_faibles,
        search_query=search_query if search_query else None
    )
    
    # ===================================================================
    # CONTEXTE
    # ===================================================================
    context = {
        'page_obj': page_obj,
        'total_stock': total_stock,
        'total_tickets': total_tickets,
        'stocks_critiques': stocks_critiques,
        'stocks_faibles': stocks_faibles,
        'search_query': search_query,  # NOUVEAU: terme de recherche pour le template
        'title': 'Gestion des Stocks - Vue d\'ensemble'
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


# ===================================================================
# VUE: CHARGEMENT STOCK AVEC TICKETS
# ===================================================================

@login_required
def charger_stock_tickets(request, poste_id):
    """
    Vue MISE À JOUR pour charger le stock avec gestion des tickets par séries.
    
    AVANT:
        - @user_passes_test(is_admin) uniquement
        - Pas de logs détaillés
    
    APRÈS:
        - Permission: peut_charger_stock_peage
        - Vérification d'accès au poste
        - Logs détaillés
        - Variables contexte IDENTIQUES
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
        f"📥 CHARGEMENT STOCK TICKETS | {get_user_short_description(user)} | "
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
    
    # ===================================================================
    # TRAITEMENT DU FORMULAIRE
    # ===================================================================
    if request.method == 'POST':
        form = ChargementStockTicketsForm(request.POST)
        
        if form.is_valid():
            couleur_saisie = form.cleaned_data['couleur_saisie']
            numero_premier = form.cleaned_data['numero_premier']
            numero_dernier = form.cleaned_data['numero_dernier']
            type_stock = form.cleaned_data['type_stock']
            commentaire = form.cleaned_data.get('commentaire', '')
            
            # Obtenir ou créer la couleur normalisée
            couleur_obj = CouleurTicket.obtenir_ou_creer(couleur_saisie)
            
            # Calculer montant
            nombre_tickets = numero_dernier - numero_premier + 1
            montant = Decimal(nombre_tickets) * Decimal('500')
            
            # Stocker en session pour confirmation
            request.session['chargement_stock_tickets'] = {
                'poste_id': poste_id,
                'couleur_id': couleur_obj.id,
                'couleur_libelle': couleur_obj.libelle_affichage,
                'numero_premier': numero_premier,
                'numero_dernier': numero_dernier,
                'nombre_tickets': nombre_tickets,
                'montant': str(montant),
                'type_stock': type_stock,
                'commentaire': commentaire
            }
            
            logger.info(
                f"📋 PRÉPARATION CHARGEMENT | {get_user_short_description(user)} | "
                f"Poste: {poste.nom} | Série: {couleur_obj.libelle_affichage} "
                f"#{numero_premier}-{numero_dernier} | Redirection vers confirmation"
            )
            
            return redirect('inventaire:confirmation_chargement_stock_tickets')
    else:
        form = ChargementStockTicketsForm()
    
    # Historique récent
    historique_recent = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='CREDIT'
    ).select_related('effectue_par').order_by('-date_mouvement')[:5]
    
    # Grouper les séries par couleur
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
    
    # ===================================================================
    # CONTEXTE - VARIABLES IDENTIQUES À L'ANCIENNE VERSION
    # ===================================================================
    context = {
        'poste': poste,
        'stock': stock,
        'form': form,
        'series_par_couleur': series_par_couleur,
        'historique_recent': historique_recent,
        'title': f'Charger stock - {poste.nom}'
    }
    
    return render(request, 'inventaire/charger_stock_tickets.html', context)


# ===================================================================
# VUE: CONFIRMATION CHARGEMENT STOCK TICKETS
# ===================================================================

@login_required
def confirmation_chargement_stock_tickets(request):
    """
    Confirmation du chargement avec vérification d'unicité annuelle.
    
    AVANT:
        - @user_passes_test(is_admin) uniquement
        - Pas de logs détaillés
    
    APRÈS:
        - Permission: peut_charger_stock_peage
        - Logs détaillés de chaque étape
        - Variables contexte IDENTIQUES
    """
    user = request.user
    
    # ===================================================================
    # VÉRIFICATION DES PERMISSIONS
    # ===================================================================
    if not peut_charger_stock(user):
        log_acces_refuse(
            user,
            "confirmation_chargement_stock_tickets",
            "Permission peut_charger_stock_peage manquante"
        )
        messages.error(request, "Vous n'avez pas la permission de charger du stock.")
        logger.warning(
            f"🚫 ACCÈS REFUSÉ | {get_user_short_description(user)} | "
            f"Vue: confirmation_chargement_stock_tickets"
        )
        return redirect('inventaire:liste_postes_stocks')
    
    # Récupérer les données de session
    chargement_data = request.session.get('chargement_stock_tickets')
    
    if not chargement_data:
        messages.error(request, "Aucune donnée de chargement en attente")
        logger.warning(
            f"⚠️ SESSION VIDE | {get_user_short_description(user)} | "
            f"Pas de données de chargement en session"
        )
        return redirect('inventaire:liste_postes_stocks')
    
    poste = get_object_or_404(Poste, id=chargement_data['poste_id'])
    couleur = get_object_or_404(CouleurTicket, id=chargement_data['couleur_id'])
    
    # Vérifier l'accès au poste
    if not verifier_acces_poste_stock(user, poste):
        del request.session['chargement_stock_tickets']
        log_acces_refuse(
            user,
            f"confirmation_chargement_stock_tickets (poste: {poste.nom})",
            "Accès au poste non autorisé"
        )
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        return redirect('inventaire:liste_postes_stocks')
    
    logger.info(
        f"✅ CONFIRMATION CHARGEMENT | {get_user_short_description(user)} | "
        f"Poste: {poste.nom} | Série: {couleur.libelle_affichage}"
    )
    
    # ===================================================================
    # TRAITEMENT POST
    # ===================================================================
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirmer':
            try:
                numero_premier = chargement_data['numero_premier']
                numero_dernier = chargement_data['numero_dernier']
                type_stock = chargement_data['type_stock']
                commentaire = chargement_data['commentaire']
                
                # Vérification d'unicité annuelle
                annee_actuelle = date.today().year
                erreurs_unicite = []
                
                for num_ticket in range(numero_premier, numero_dernier + 1):
                    est_unique, msg, historique = SerieTicket.verifier_unicite_annuelle(
                        num_ticket, couleur, annee_actuelle
                    )
                    
                    if not est_unique:
                        erreurs_unicite.append({
                            'numero': num_ticket,
                            'message': msg,
                            'historique': historique
                        })
                
                if erreurs_unicite:
                    messages.error(
                        request,
                        f"❌ CHARGEMENT IMPOSSIBLE : {len(erreurs_unicite)} ticket(s) "
                        f"de cette série existent déjà en {annee_actuelle}"
                    )
                    
                    logger.warning(
                        f"⚠️ UNICITÉ ANNUELLE | {get_user_short_description(user)} | "
                        f"Poste: {poste.nom} | {len(erreurs_unicite)} conflit(s) détecté(s)"
                    )
                    
                    for erreur in erreurs_unicite[:5]:
                        hist = erreur['historique']
                        messages.warning(
                            request,
                            f"Ticket {couleur.libelle_affichage} #{erreur['numero']} : "
                            f"Reçu le {hist['date_reception'].strftime('%d/%m/%Y')} "
                            f"au poste {hist['poste_reception']} "
                            f"({hist['type_entree']}) - Statut: {hist['statut']}"
                        )
                    
                    if len(erreurs_unicite) > 5:
                        messages.info(
                            request,
                            f"... et {len(erreurs_unicite) - 5} autre(s) ticket(s) en conflit"
                        )
                    
                    del request.session['chargement_stock_tickets']
                    return redirect('inventaire:charger_stock_tickets', poste_id=poste.id)
                
                # Exécuter le chargement
                success, message, serie, historique = executer_chargement_stock_avec_series(
                    poste=poste,
                    couleur=couleur,
                    numero_premier=numero_premier,
                    numero_dernier=numero_dernier,
                    type_stock=type_stock,
                    user=user,
                    commentaire=commentaire
                )
                
                if success:
                    del request.session['chargement_stock_tickets']
                    
                    montant = Decimal(chargement_data['montant'])
                    nombre_tickets = chargement_data['nombre_tickets']
                    
                    messages.success(
                        request,
                        f"✅ Stock crédité avec succès : Série {couleur.libelle_affichage} "
                        f"#{numero_premier}-{numero_dernier} "
                        f"({nombre_tickets} tickets = {montant:,.0f} FCFA)"
                    )
                    
                    # Log final du chargement
                    log_operation_stock(
                        user,
                        poste,
                        "CHARGEMENT_CONFIRME",
                        nombre_tickets,
                        serie=f"{couleur.libelle_affichage} #{numero_premier}-{numero_dernier}",
                        request=request,
                        type_stock=type_stock,
                        montant=str(montant),
                        historique_id=historique.id if historique else None
                    )
                    
                    logger.info(
                        f"✅ CHARGEMENT CONFIRMÉ | {get_user_short_description(user)} | "
                        f"Poste: {poste.nom} | Série: {couleur.libelle_affichage} "
                        f"#{numero_premier}-{numero_dernier} | "
                        f"{nombre_tickets} tickets = {montant:,.0f} FCFA"
                    )
                    
                    return redirect('inventaire:liste_postes_stocks')
                else:
                    raise Exception(message)
                    
            except Exception as e:
                logger.error(
                    f"❌ ERREUR CHARGEMENT | {get_user_short_description(user)} | "
                    f"Poste: {poste.nom} | Erreur: {str(e)}",
                    exc_info=True
                )
                messages.error(request, f"❌ Erreur lors du chargement : {str(e)}")
                return redirect('inventaire:charger_stock_tickets', poste_id=poste.id)
        
        elif action == 'annuler':
            del request.session['chargement_stock_tickets']
            messages.info(request, "Chargement annulé")
            logger.info(
                f"↩️ CHARGEMENT ANNULÉ | {get_user_short_description(user)} | "
                f"Poste: {poste.nom}"
            )
            return redirect('inventaire:charger_stock_tickets', poste_id=poste.id)
    
    # ===================================================================
    # PRÉPARATION AFFICHAGE
    # ===================================================================
    montant = Decimal(chargement_data['montant'])
    
    # Vérifier les conflits potentiels
    annee_actuelle = date.today().year
    tickets_existants = []
    for num in range(chargement_data['numero_premier'], 
                     min(chargement_data['numero_premier'] + 10, chargement_data['numero_dernier'] + 1)):
        est_unique, msg, hist = SerieTicket.verifier_unicite_annuelle(
            num, couleur, annee_actuelle
        )
        if not est_unique:
            tickets_existants.append({'numero': num, 'historique': hist})
    
    # ===================================================================
    # CONTEXTE - VARIABLES IDENTIQUES À L'ANCIENNE VERSION
    # ===================================================================
    context = {
        'poste': poste,
        'couleur': couleur,
        'numero_premier': chargement_data['numero_premier'],
        'numero_dernier': chargement_data['numero_dernier'],
        'nombre_tickets': chargement_data['nombre_tickets'],
        'montant': montant,
        'type_stock': chargement_data['type_stock'],
        'type_stock_label': (
            'Régularisation' if chargement_data['type_stock'] == 'regularisation'
            else 'Imprimerie Nationale'
        ),
        'commentaire': chargement_data['commentaire'],
        'tickets_existants': tickets_existants,
        'annee_actuelle': annee_actuelle,
        'title': 'Confirmation du chargement de stock'
    }
    
    return render(request, 'inventaire/confirmation_chargement_stock_tickets.html', context)


# ===================================================================
# FONCTION UTILITAIRE: EXÉCUTION DU CHARGEMENT
# ===================================================================

def executer_chargement_stock_avec_series(poste, couleur, numero_premier, numero_dernier, 
                                          type_stock, user, commentaire=None):
    """
    VERSION CORRIGÉE : Avec remplissage des champs structurés de HistoriqueStock.
    
    Cette fonction est identique à l'originale mais conservée ici pour cohérence.
    
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
            
            # 5. Associer la série
            historique.series_tickets_associees.add(serie)
            
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
                    expediteur=user,
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
        return False, f"❌ Erreur : {str(e)}", None, None


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