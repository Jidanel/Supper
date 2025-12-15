# ===================================================================
# inventaire/views_transferts.py - VERSION MISE À JOUR
# Vues pour le transfert de stock entre postes (en montants)
# MISE À JOUR: Intégration des permissions granulaires
# ===================================================================

from django.http import HttpResponse, HttpResponseForbidden, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Avg, Count, Q
from django.core.paginator import Paginator
from decimal import Decimal
from datetime import datetime
from django.utils import timezone

from accounts.models import Poste, NotificationUtilisateur, UtilisateurSUPPER
from inventaire.models import *
from common.utils import log_user_action
import logging

logger = logging.getLogger('supper')


# ===================================================================
# FONCTIONS UTILITAIRES DE VÉRIFICATION DES PERMISSIONS
# ===================================================================

def has_permission(user, permission_name):
    """
    Vérifie si l'utilisateur possède une permission spécifique.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return getattr(user, permission_name, False)


def has_any_permission(user, permission_names):
    """
    Vérifie si l'utilisateur possède AU MOINS UNE des permissions.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return any(getattr(user, perm, False) for perm in permission_names)


def user_has_acces_tous_postes(user):
    """
    Vérifie si l'utilisateur a accès à tous les postes.
    """
    HABILITATIONS_MULTI_POSTES = [
        'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission',
        'chef_ag', 'serv_controle', 'serv_ordre', 'imprimerie',
        'cisop_peage', 'cisop_pesage', 'focal_regional', 'chef_service',
        'regisseur', 'comptable_mat', 'chef_ordre', 'chef_controle',
    ]
    
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if getattr(user, 'acces_tous_postes', False):
        return True
    if getattr(user, 'peut_voir_tous_postes', False):
        return True
    return getattr(user, 'habilitation', None) in HABILITATIONS_MULTI_POSTES


def check_poste_access(user, poste):
    """
    Vérifie si l'utilisateur a accès à un poste spécifique.
    """
    if not user or not user.is_authenticated:
        return False
    if user_has_acces_tous_postes(user):
        return True
    if isinstance(poste, int):
        try:
            poste = Poste.objects.get(id=poste)
        except Poste.DoesNotExist:
            return False
    poste_affectation = getattr(user, 'poste_affectation', None)
    return poste_affectation and poste_affectation.id == poste.id


def peut_transferer_stock(user):
    """
    Vérifie si l'utilisateur peut transférer du stock péage.
    Habilitations: admin_principal, coord_psrr, serv_info, serv_emission, chef_peage
    """
    return has_permission(user, 'peut_transferer_stock_peage')


def peut_voir_bordereaux(user):
    """
    Vérifie si l'utilisateur peut voir les bordereaux péage.
    Habilitations: admin, services centraux, cisop_peage, chef_peage*, agent_inventaire*
    """
    return has_permission(user, 'peut_voir_bordereaux_peage')


def log_acces_refuse(user, ressource, raison, request=None):
    """
    Journalise un accès refusé.
    """
    logger.warning(
        f"ACCÈS REFUSÉ - Utilisateur: {user.username if user else 'Anonyme'} | "
        f"Ressource: {ressource} | Raison: {raison}"
    )
    if user and user.is_authenticated:
        try:
            log_user_action(
                user,
                "ACCES_REFUSE",
                f"Accès refusé à {ressource}: {raison}",
                request
            )
        except Exception as e:
            logger.error(f"Erreur lors de la journalisation de l'accès refusé: {e}")


# ===================================================================
# VUES DE TRANSFERT DE STOCK (MONTANTS)
# ===================================================================

@login_required
def selection_transfert_stock(request):
    """
    Sélection des postes pour le transfert de stock (en montants)
    
    PERMISSIONS REQUISES: peut_transferer_stock_peage
    
    HABILITATIONS AUTORISÉES:
    - admin_principal, coord_psrr, serv_info (admins)
    - serv_emission (service émission)
    - chef_peage (chef de poste péage)
    
    AVANT: @user_passes_test(is_admin) - Admin uniquement
    APRÈS: Permission peut_transferer_stock_peage
    
    VARIABLES CONTEXTE: postes, title
    """
    user = request.user
    
    # Vérification des permissions
    if not peut_transferer_stock(user):
        log_acces_refuse(
            user,
            "Selection transfert stock",
            f"Permission peut_transferer_stock_peage manquante (habilitation: {user.habilitation})",
            request
        )
        messages.error(request, "Vous n'avez pas la permission de transférer du stock.")
        return redirect('common:dashboard')
    
    logger.info(
        f"TRANSFERT_STOCK - Accès sélection par {user.username} "
        f"(habilitation: {user.habilitation})"
    )
    
    # Récupérer les postes accessibles
    if user_has_acces_tous_postes(user):
        postes = Poste.objects.filter(is_active=True).order_by('nom')
    else:
        if user.poste_affectation:
            postes = Poste.objects.filter(id=user.poste_affectation.id, is_active=True)
        else:
            postes = Poste.objects.none()
    
    # Récupérer les stocks actuels
    postes_data = []
    for poste in postes:
        stock = GestionStock.objects.filter(poste=poste).first()
        postes_data.append({
            'poste': poste,
            'stock_actuel': stock.valeur_monetaire if stock else Decimal('0'),
            'tickets_actuels': stock.nombre_tickets if stock else 0
        })
    
    if request.method == 'POST':
        poste_origine_id = request.POST.get('poste_origine_id')
        poste_destination_id = request.POST.get('poste_destination_id')
        
        if not poste_origine_id or not poste_destination_id:
            messages.error(request, "Veuillez sélectionner les deux postes")
            return redirect('inventaire:selection_transfert_stock')
        
        if poste_origine_id == poste_destination_id:
            messages.error(request, "Les postes d'origine et de destination doivent être différents")
            return redirect('inventaire:selection_transfert_stock')
        
        # Vérifier l'accès au poste d'origine
        try:
            poste_origine = Poste.objects.get(id=poste_origine_id)
            if not user_has_acces_tous_postes(user) and not check_poste_access(user, poste_origine):
                log_acces_refuse(
                    user,
                    f"Transfert depuis {poste_origine.nom}",
                    "Accès au poste d'origine non autorisé",
                    request
                )
                messages.error(request, "Vous n'avez pas accès au poste d'origine sélectionné.")
                return redirect('inventaire:selection_transfert_stock')
        except Poste.DoesNotExist:
            messages.error(request, "Poste d'origine introuvable")
            return redirect('inventaire:selection_transfert_stock')
        
        log_user_action(
            user,
            "TRANSFERT_STOCK_SELECTION",
            f"Sélection transfert stock: poste {poste_origine_id} → {poste_destination_id}",
            request
        )
        
        return redirect('inventaire:formulaire_transfert_stock', 
                       origine_id=poste_origine_id,
                       destination_id=poste_destination_id)
    
    context = {
        'postes': postes_data,
        'title': 'Transférer du Stock Entre Postes'
    }
    
    return render(request, 'inventaire/selection_transfert_stock.html', context)


@login_required
def formulaire_transfert_stock(request, origine_id, destination_id):
    """
    Formulaire de saisie du montant à transférer
    
    PERMISSIONS REQUISES: peut_transferer_stock_peage
    
    AVANT: @user_passes_test(is_admin) - Admin uniquement
    APRÈS: Permission peut_transferer_stock_peage
    
    VARIABLES CONTEXTE: poste_origine, poste_destination, stock_origine, stock_destination, title
    """
    user = request.user
    
    # Vérification des permissions
    if not peut_transferer_stock(user):
        log_acces_refuse(
            user,
            "Formulaire transfert stock",
            f"Permission peut_transferer_stock_peage manquante (habilitation: {user.habilitation})",
            request
        )
        messages.error(request, "Vous n'avez pas la permission de transférer du stock.")
        return redirect('common:dashboard')
    
    poste_origine = get_object_or_404(Poste, id=origine_id)
    poste_destination = get_object_or_404(Poste, id=destination_id)
    
    # Vérifier l'accès au poste d'origine
    if not user_has_acces_tous_postes(user) and not check_poste_access(user, poste_origine):
        log_acces_refuse(
            user,
            f"Formulaire transfert depuis {poste_origine.nom}",
            "Accès au poste d'origine non autorisé",
            request
        )
        messages.error(request, "Vous n'avez pas accès au poste d'origine.")
        return redirect('inventaire:selection_transfert_stock')
    
    logger.info(
        f"TRANSFERT_STOCK - Formulaire par {user.username}: "
        f"{poste_origine.nom} → {poste_destination.nom}"
    )
    
    # Récupérer le stock de l'origine
    stock_origine, _ = GestionStock.objects.get_or_create(
        poste=poste_origine,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    stock_destination, _ = GestionStock.objects.get_or_create(
        poste=poste_destination,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    if request.method == 'POST':
        try:
            montant = Decimal(request.POST.get('montant', '0'))
            commentaire = request.POST.get('commentaire', '')
            
            # Validations
            if montant <= 0:
                messages.error(request, "Le montant doit être positif")
                return redirect('inventaire:formulaire_transfert_stock', 
                              origine_id=origine_id, 
                              destination_id=destination_id)
            
            if montant > stock_origine.valeur_monetaire:
                messages.error(request, 
                             f"Stock insuffisant. Disponible : {stock_origine.valeur_monetaire:,.0f} FCFA")
                return redirect('inventaire:formulaire_transfert_stock', 
                              origine_id=origine_id, 
                              destination_id=destination_id)
            
            # Stocker en session pour confirmation
            request.session['transfert_stock'] = {
                'origine_id': origine_id,
                'destination_id': destination_id,
                'montant': str(montant),
                'commentaire': commentaire
            }
            
            log_user_action(
                user,
                "TRANSFERT_STOCK_SAISIE",
                f"Saisie transfert stock: {montant:,.0f} FCFA de {poste_origine.nom} vers {poste_destination.nom}",
                request
            )
            
            return redirect('inventaire:confirmation_transfert_stock')
            
        except Exception as e:
            logger.error(f"TRANSFERT_STOCK - Erreur saisie: {str(e)}")
            messages.error(request, f"Erreur : {str(e)}")
            return redirect('inventaire:formulaire_transfert_stock', 
                          origine_id=origine_id, 
                          destination_id=destination_id)
    
    context = {
        'poste_origine': poste_origine,
        'poste_destination': poste_destination,
        'stock_origine': stock_origine,
        'stock_destination': stock_destination,
        'title': 'Formulaire de Transfert'
    }
    
    return render(request, 'inventaire/formulaire_transfert_stock.html', context)


@login_required
def confirmation_transfert_stock(request):
    """
    Confirmation du transfert de stock (en montants)
    
    PERMISSIONS REQUISES: peut_transferer_stock_peage
    
    AVANT: @user_passes_test(is_admin) - Admin uniquement
    APRÈS: Permission peut_transferer_stock_peage
    
    VARIABLES CONTEXTE: poste_origine, poste_destination, montant, nombre_tickets, commentaire, title
    """
    user = request.user
    
    # Vérification des permissions
    if not peut_transferer_stock(user):
        log_acces_refuse(
            user,
            "Confirmation transfert stock",
            f"Permission peut_transferer_stock_peage manquante (habilitation: {user.habilitation})",
            request
        )
        messages.error(request, "Vous n'avez pas la permission de transférer du stock.")
        return redirect('common:dashboard')
    
    transfert_data = request.session.get('transfert_stock')
    
    if not transfert_data:
        messages.error(request, "Aucune donnée de transfert en attente")
        return redirect('inventaire:selection_transfert_stock')
    
    poste_origine = get_object_or_404(Poste, id=transfert_data['origine_id'])
    poste_destination = get_object_or_404(Poste, id=transfert_data['destination_id'])
    montant = Decimal(transfert_data['montant'])
    
    # Vérifier l'accès au poste d'origine
    if not user_has_acces_tous_postes(user) and not check_poste_access(user, poste_origine):
        log_acces_refuse(
            user,
            f"Confirmation transfert depuis {poste_origine.nom}",
            "Accès au poste d'origine non autorisé",
            request
        )
        messages.error(request, "Vous n'avez pas accès au poste d'origine.")
        if 'transfert_stock' in request.session:
            del request.session['transfert_stock']
        return redirect('inventaire:selection_transfert_stock')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirmer':
            try:
                logger.info(
                    f"TRANSFERT_STOCK - DEBUT: {montant:,.0f} FCFA de {poste_origine.code} "
                    f"vers {poste_destination.code} par {user.username}"
                )
                
                with transaction.atomic():
                    numero_bordereau = generer_numero_bordereau()
                    logger.info(f"TRANSFERT_STOCK - Bordereau généré: {numero_bordereau}")
                    
                    hist_origine, hist_destination = executer_transfert_stock(
                        poste_origine,
                        poste_destination,
                        montant,
                        user,
                        transfert_data['commentaire'],
                        numero_bordereau
                    )
                    
                    logger.info(
                        f"TRANSFERT_STOCK - Transaction OK - "
                        f"Hist Origine: {hist_origine.id}, Hist Dest: {hist_destination.id}"
                    )
                
                # Nettoyer la session ET rediriger vers page de succès
                if 'transfert_stock' in request.session:
                    del request.session['transfert_stock']
                
                log_user_action(
                    user,
                    "TRANSFERT_STOCK_EXECUTE",
                    f"Transfert exécuté: {montant:,.0f} FCFA de {poste_origine.nom} "
                    f"vers {poste_destination.nom} (Bordereau: {numero_bordereau})",
                    request
                )
                
                messages.success(
                    request, 
                    f"✅ Transfert réussi ! {montant:,.0f} FCFA transférés. Bordereau N°{numero_bordereau}"
                )
                
                return redirect('inventaire:detail_transfert_succes', numero_bordereau=numero_bordereau)
                
            except ValueError as ve:
                logger.error(f"TRANSFERT_STOCK - Erreur validation: {str(ve)}")
                messages.error(request, f"❌ Validation : {str(ve)}")
                return redirect('inventaire:formulaire_transfert_stock', 
                              origine_id=poste_origine.id, 
                              destination_id=poste_destination.id)
            
            except Exception as e:
                logger.error(f"TRANSFERT_STOCK - Erreur: {str(e)}", exc_info=True)
                messages.error(request, f"❌ Erreur : {str(e)}")
                return redirect('inventaire:selection_transfert_stock')
        
        elif action == 'annuler':
            if 'transfert_stock' in request.session:
                del request.session['transfert_stock']
            
            log_user_action(
                user,
                "TRANSFERT_STOCK_ANNULE",
                f"Transfert annulé: {poste_origine.nom} → {poste_destination.nom}",
                request
            )
            
            messages.info(request, "Transfert annulé")
            return redirect('inventaire:selection_transfert_stock')
    
    context = {
        'poste_origine': poste_origine,
        'poste_destination': poste_destination,
        'montant': montant,
        'nombre_tickets': int(montant / 500),
        'commentaire': transfert_data['commentaire'],
        'title': 'Confirmation du Transfert'
    }
    
    return render(request, 'inventaire/confirmation_transfert_stock.html', context)


@login_required
def detail_transfert_succes(request, numero_bordereau):
    """
    Page de succès après transfert avec liens de téléchargement
    
    PERMISSIONS REQUISES: peut_voir_bordereaux_peage OU poste concerné
    
    HABILITATIONS AVEC ACCÈS:
    - admin_principal, coord_psrr, serv_info (admins)
    - services centraux
    - cisop_peage
    - chef_peage, agent_inventaire (pour leurs postes)
    
    AVANT: @user_passes_test(is_admin) - Admin uniquement
    APRÈS: Permission peut_voir_bordereaux_peage
    
    VARIABLES CONTEXTE: numero_bordereau, hist_cession, hist_reception, 
                        poste_origine, poste_destination, montant, nombre_tickets, title
    """
    user = request.user
    
    # Récupérer les deux historiques
    hist_cession = get_object_or_404(
        HistoriqueStock,
        numero_bordereau=numero_bordereau,
        type_mouvement='DEBIT'
    )
    
    hist_reception = HistoriqueStock.objects.filter(
        numero_bordereau=numero_bordereau,
        type_mouvement='CREDIT'
    ).first()
    
    # Vérifier les permissions
    peut_voir_global = peut_voir_bordereaux(user)
    
    if not peut_voir_global:
        # Vérifier si l'utilisateur a accès à l'un des postes concernés
        postes_concernes = [hist_cession.poste_origine.id]
        if hist_cession.poste_destination:
            postes_concernes.append(hist_cession.poste_destination.id)
        
        poste_user = getattr(user, 'poste_affectation', None)
        
        if not poste_user or poste_user.id not in postes_concernes:
            log_acces_refuse(
                user,
                f"Détail transfert succès {numero_bordereau}",
                f"Ni permission peut_voir_bordereaux_peage ni poste concerné",
                request
            )
            messages.error(request, "Vous n'avez pas accès à ce bordereau.")
            return redirect('common:dashboard')
    
    logger.info(
        f"TRANSFERT_SUCCES - {user.username} consulte bordereau {numero_bordereau}"
    )
    
    context = {
        'numero_bordereau': numero_bordereau,
        'hist_cession': hist_cession,
        'hist_reception': hist_reception,
        'poste_origine': hist_cession.poste_origine,
        'poste_destination': hist_cession.poste_destination,
        'montant': hist_cession.montant,
        'nombre_tickets': hist_cession.nombre_tickets,
        'title': 'Transfert Réussi'
    }
    
    return render(request, 'inventaire/detail_transfert_succes.html', context)


# ===================================================================
# FONCTION D'EXÉCUTION DU TRANSFERT (avec Event Sourcing)
# ===================================================================

def executer_transfert_stock(poste_origine, poste_destination, montant, 
                            user, commentaire, numero_bordereau):
    """
    VERSION MODIFIÉE avec Event Sourcing
    Exécute le transfert de stock entre deux postes
    """
    
    # CORRECTION : Utiliser get_or_create au lieu de get
    stock_origine, created_origine = GestionStock.objects.select_for_update().get_or_create(
        poste=poste_origine,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    stock_destination, created_dest = GestionStock.objects.select_for_update().get_or_create(
        poste=poste_destination,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    # Vérification finale du stock disponible
    if stock_origine.valeur_monetaire < montant:
        raise ValueError(f"Stock insuffisant à l'origine. Disponible: {stock_origine.valeur_monetaire}, Demandé: {montant}")
    
    nombre_tickets = int(montant / 500)
    
    # Sauvegarder les états avant
    stock_origine_avant = stock_origine.valeur_monetaire
    stock_destination_avant = stock_destination.valeur_monetaire
    
    # Mettre à jour les stocks
    stock_origine.valeur_monetaire -= montant
    stock_origine.save()
    
    stock_destination.valeur_monetaire += montant
    stock_destination.save()
    
    # LOG pour débogage
    logger.info(f"TRANSFERT STOCK - Origine {poste_origine.code}: {stock_origine_avant} -> {stock_origine.valeur_monetaire}")
    logger.info(f"TRANSFERT STOCK - Destination {poste_destination.code}: {stock_destination_avant} -> {stock_destination.valeur_monetaire}")
    
    # ===== EVENT SOURCING =====
    timestamp = timezone.now()
    
    # Créer l'événement de SORTIE pour le poste origine
    StockEvent.objects.create(
        poste=poste_origine,
        event_type='TRANSFERT_OUT',
        event_datetime=timestamp,
        montant_variation=-montant,  # NÉGATIF car sortie
        nombre_tickets_variation=-nombre_tickets,
        stock_resultant=stock_origine.valeur_monetaire,
        tickets_resultants=int(stock_origine.valeur_monetaire / 500),
        effectue_par=user,
        metadata={
            'poste_destination': {
                'id': poste_destination.id,
                'nom': poste_destination.nom,
                'code': poste_destination.code
            },
            'numero_bordereau': numero_bordereau,
            'type_operation': 'cession'
        },
        commentaire=f"Transfert vers {poste_destination.nom} - {commentaire}"
    )
    
    # Créer l'événement d'ENTRÉE pour le poste destination
    StockEvent.objects.create(
        poste=poste_destination,
        event_type='TRANSFERT_IN',
        event_datetime=timestamp,
        montant_variation=montant,  # POSITIF car entrée
        nombre_tickets_variation=nombre_tickets,
        stock_resultant=stock_destination.valeur_monetaire,
        tickets_resultants=int(stock_destination.valeur_monetaire / 500),
        effectue_par=user,
        metadata={
            'poste_origine': {
                'id': poste_origine.id,
                'nom': poste_origine.nom,
                'code': poste_origine.code
            },
            'numero_bordereau': numero_bordereau,
            'type_operation': 'reception'
        },
        commentaire=f"Transfert depuis {poste_origine.nom} - {commentaire}"
    )
    
    # Créer l'historique pour le poste ORIGINE
    hist_origine = HistoriqueStock.objects.create(
        poste=poste_origine,
        type_mouvement='DEBIT',
        type_stock='reapprovisionnement',
        montant=montant,
        nombre_tickets=nombre_tickets,
        stock_avant=stock_origine_avant,
        stock_apres=stock_origine.valeur_monetaire,
        effectue_par=user,
        poste_origine=poste_origine,
        poste_destination=poste_destination,
        numero_bordereau=numero_bordereau,
        commentaire=f"{commentaire}"
    )
    
    logger.info(f"Historique ORIGINE créé - ID: {hist_origine.id}, Bordereau: {hist_origine.numero_bordereau}")
    
    # Créer l'historique pour le poste DESTINATION
    hist_destination = HistoriqueStock.objects.create(
        poste=poste_destination,
        type_mouvement='CREDIT',
        type_stock='reapprovisionnement',
        montant=montant,
        nombre_tickets=nombre_tickets,
        stock_avant=stock_destination_avant,
        stock_apres=stock_destination.valeur_monetaire,
        effectue_par=user,
        poste_origine=poste_origine,
        poste_destination=poste_destination,
        numero_bordereau=numero_bordereau,
        commentaire=f"{commentaire}"
    )
    
    logger.info(f"Historique DESTINATION créé - ID: {hist_destination.id}, Bordereau: {hist_destination.numero_bordereau}")
    
    # Notifier les chefs de poste concernés
    # Chef du poste origine
    chefs_origine = UtilisateurSUPPER.objects.filter(
        poste_affectation=poste_origine,
        habilitation__in=['chef_peage', 'chef_pesage'],
        is_active=True
    )
    
    for chef in chefs_origine:
        NotificationUtilisateur.objects.create(
            destinataire=chef,
            expediteur=user,
            titre="Stock cédé à un autre poste",
            message=f"Votre stock a été réduit de {montant:,.0f} FCFA ({nombre_tickets} tickets) au profit de {poste_destination.nom}. Bordereau N°{numero_bordereau}",
            type_notification='warning'
        )
    
    # Chef du poste destination
    chefs_destination = UtilisateurSUPPER.objects.filter(
        poste_affectation=poste_destination,
        habilitation__in=['chef_peage', 'chef_pesage'],
        is_active=True
    )
    
    for chef in chefs_destination:
        NotificationUtilisateur.objects.create(
            destinataire=chef,
            expediteur=user,
            titre="Nouveau stock reçu",
            message=f"Votre stock a été augmenté de {montant:,.0f} FCFA ({nombre_tickets} tickets) en provenance de {poste_origine.nom}. Bordereau N°{numero_bordereau}",
            type_notification='success'
        )
    
    # Journaliser l'action
    log_user_action(
        user,
        "TRANSFERT_STOCK_INTER_POSTES",
        f"Transfert : {montant:,.0f} FCFA de {poste_origine.nom} vers {poste_destination.nom}. Bordereau N°{numero_bordereau}",
        None
    )
    
    logger.info(f"Transfert stock TERMINÉ avec succès - Bordereau {numero_bordereau}")
    
    return hist_origine, hist_destination


def generer_numero_bordereau():
    """Génère un numéro unique de bordereau de transfert"""
    # Format : TR-YYYYMMDD-HHMMSS-XXX
    now = datetime.now()
    
    # Compter les transferts du jour
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    count_today = HistoriqueStock.objects.filter(
        type_stock='reapprovisionnement',
        date_mouvement__gte=today_start
    ).count()
    
    numero = f"TR-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}-{count_today+1:03d}"
    
    return numero


# ===================================================================
# GÉNÉRATION PDF DES BORDEREAUX
# ===================================================================

@login_required
def bordereaux_transfert(request, numero_bordereau):
    """
    Génère le PDF du bordereau (cession ou réception)
    
    PERMISSIONS REQUISES:
    - peut_voir_bordereaux_peage (accès global)
    - OU appartenance à l'un des postes concernés
    
    AVANT: Vérification manuelle is_admin + check poste
    APRÈS: Permission peut_voir_bordereaux_peage OU check poste concerné
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER
    
    user = request.user
    
    # Récupérer le type demandé (ou par défaut 'cession')
    type_bordereau = request.GET.get('type', 'cession')
    
    # Validation du type
    if type_bordereau not in ['cession', 'reception']:
        return HttpResponse("Type de bordereau invalide. Utilisez 'cession' ou 'reception'", status=400)
    
    # Récupérer l'historique selon le type
    try:
        if type_bordereau == 'cession':
            hist = HistoriqueStock.objects.select_related(
                'poste', 'poste_origine', 'poste_destination', 'effectue_par'
            ).get(
                numero_bordereau=numero_bordereau,
                type_mouvement='DEBIT'
            )
        else:
            hist = HistoriqueStock.objects.select_related(
                'poste', 'poste_origine', 'poste_destination', 'effectue_par'
            ).get(
                numero_bordereau=numero_bordereau,
                type_mouvement='CREDIT'
            )
    except HistoriqueStock.DoesNotExist:
        raise Http404(f"Bordereau {numero_bordereau} ({type_bordereau}) introuvable")
    
    # Vérifier les permissions
    peut_voir_global = peut_voir_bordereaux(user)
    
    if not peut_voir_global:
        # Vérifier si l'utilisateur a accès à l'un des postes concernés
        poste_user = getattr(user, 'poste_affectation', None)
        postes_concernes = []
        if hist.poste_origine:
            postes_concernes.append(hist.poste_origine.id)
        if hist.poste_destination:
            postes_concernes.append(hist.poste_destination.id)
        
        if not poste_user or poste_user.id not in postes_concernes:
            log_acces_refuse(
                user,
                f"PDF Bordereau {numero_bordereau}",
                f"Ni permission peut_voir_bordereaux_peage ni poste concerné",
                request
            )
            return HttpResponseForbidden("Vous n'avez pas accès à ce bordereau")
    
    logger.info(
        f"BORDEREAU_PDF - {user.username} télécharge bordereau {numero_bordereau} ({type_bordereau})"
    )
    
    # Récupérer les séries transférées
    if type_bordereau == 'cession':
        series_transferees = SerieTicket.objects.filter(
            poste=hist.poste_origine,
            statut='transfere',
            poste_destination_transfert=hist.poste_destination,
            date_utilisation=hist.date_mouvement.date()
        ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
    else:
        series_transferees = SerieTicket.objects.filter(
            poste=hist.poste_destination,
            type_entree='transfert_recu',
            date_reception__date=hist.date_mouvement.date()
        ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
    
    # Grouper par couleur
    series_par_couleur = {}
    for serie in series_transferees:
        couleur_key = serie.couleur.libelle_affichage
        if couleur_key not in series_par_couleur:
            series_par_couleur[couleur_key] = {
                'couleur': serie.couleur,
                'series': [],
                'total_tickets': 0,
                'valeur_totale': Decimal('0')
            }
        
        series_par_couleur[couleur_key]['series'].append(serie)
        series_par_couleur[couleur_key]['total_tickets'] += serie.nombre_tickets
        series_par_couleur[couleur_key]['valeur_totale'] += serie.valeur_monetaire
    
    # Générer le PDF
    response = HttpResponse(content_type='application/pdf')
    filename = f'bordereau_{type_bordereau}_{numero_bordereau}.pdf'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    
    doc = SimpleDocTemplate(
        response, 
        pagesize=A4,
        rightMargin=2*cm, 
        leftMargin=2*cm,
        topMargin=2*cm, 
        bottomMargin=2*cm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Récupérer la config globale
    from inventaire.models import ConfigurationGlobale
    config = ConfigurationGlobale.get_config()
    
    # En-tête
    from inventaire.views_rapports import creer_entete_bilingue
    poste_concerne = hist.poste_origine if type_bordereau == 'cession' else hist.poste_destination
    elements.append(creer_entete_bilingue(config, poste_concerne))
    elements.append(Spacer(1, 1*cm))
    
    # Titre
    titre_style = ParagraphStyle(
        'Titre',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#d32f2f' if type_bordereau == 'cession' else '#388e3c'),
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    titre_text = (
        "BORDEREAU DE CESSION DE TICKETS" 
        if type_bordereau == 'cession' 
        else "BORDEREAU DE RÉCEPTION DE TICKETS"
    )
    elements.append(Paragraph(titre_text, titre_style))
    elements.append(Spacer(1, 0.5*cm))
    
    # Informations générales
    data = [
        ['N° Bordereau:', numero_bordereau],
        ['Date et Heure:', hist.date_mouvement.strftime('%d/%m/%Y à %H:%M')],
        ['', ''],
    ]
    
    if type_bordereau == 'cession':
        data.extend([
            ['POSTE ÉMETTEUR (CÈDE):', f"{hist.poste_origine.nom} ({hist.poste_origine.code})"],
            ['POSTE DESTINATAIRE:', f"{hist.poste_destination.nom} ({hist.poste_destination.code})"],
        ])
    else:
        data.extend([
            ['POSTE BÉNÉFICIAIRE (REÇOIT):', f"{hist.poste_destination.nom} ({hist.poste_destination.code})"],
            ['POSTE ÉMETTEUR:', f"{hist.poste_origine.nom} ({hist.poste_origine.code})"],
        ])
    
    data.extend([
        ['', ''],
        ['MONTANT TOTAL TRANSFÉRÉ:', f"{hist.montant:,.0f} FCFA".replace(',', ' ')],
        ['NOMBRE TOTAL DE TICKETS:', f"{hist.nombre_tickets} tickets"],
    ])
    
    table = Table(data, colWidths=[6*cm, 10*cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Détail des séries
    titre_series = ParagraphStyle(
        'TitreSeries',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=10
    )
    
    elements.append(Paragraph("DÉTAIL DES SÉRIES TRANSFÉRÉES", titre_series))
    
    if series_par_couleur:
        for couleur_nom, groupe in series_par_couleur.items():
            couleur_header = [[
                Paragraph(f"<b>Couleur : {couleur_nom}</b>", styles['Normal']),
                f"Total: {groupe['total_tickets']} tickets",
                f"{groupe['valeur_totale']:,.0f} FCFA".replace(',', ' ')
            ]]
            
            for serie in groupe['series']:
                couleur_header.append([
                    f"Série #{serie.numero_premier} → #{serie.numero_dernier}",
                    f"{serie.nombre_tickets} tickets",
                    f"{serie.valeur_monetaire:,.0f} FCFA".replace(',', ' ')
                ])
            
            serie_table = Table(couleur_header, colWidths=[7*cm, 4*cm, 5*cm])
            serie_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            
            elements.append(serie_table)
            elements.append(Spacer(1, 0.3*cm))
    
    elements.append(Spacer(1, 0.5*cm))
    
    # État des stocks
    elements.append(Paragraph("ÉTAT DES STOCKS", titre_series))
    
    stock_data = [
        ['STOCK AVANT:', f"{hist.stock_avant:,.0f} FCFA".replace(',', ' ')],
        ['STOCK APRÈS:', f"{hist.stock_apres:,.0f} FCFA".replace(',', ' ')],
        ['EFFECTUÉ PAR:', hist.effectue_par.nom_complet],
    ]
    
    if hist.commentaire:
        stock_data.append(['COMMENTAIRE:', hist.commentaire[:100]])
    
    stock_table = Table(stock_data, colWidths=[6*cm, 10*cm])
    stock_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(stock_table)
    elements.append(Spacer(1, 1.5*cm))
    
    # Signatures
    signature_data = [
        ['LE CHEF ÉMETTEUR', 'LE CHEF DESTINATAIRE', 'L\'ADMINISTRATEUR'],
        ['', '', ''],
        ['_________________', '_________________', '_________________'],
        [hist.poste_origine.nom, hist.poste_destination.nom, hist.effectue_par.nom_complet]
    ]
    
    sig_table = Table(signature_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    sig_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    
    elements.append(sig_table)
    
    # Générer le PDF
    doc.build(elements)
    
    log_user_action(
        user,
        "BORDEREAU_PDF_GENERE",
        f"PDF bordereau {numero_bordereau} ({type_bordereau}) généré",
        request
    )
    
    return response


@login_required
def liste_bordereaux(request):
    """
    Liste de tous les bordereaux de transfert
    
    PERMISSIONS:
    - peut_voir_bordereaux_peage: voit TOUS les bordereaux
    - peut_voir_mon_stock_peage: voit les bordereaux de son poste uniquement
    - chef_peage/agent_inventaire: voit les bordereaux de son poste
    
    AVANT: Vérification manuelle is_admin + filtrage par poste
    APRÈS: Filtrage automatique basé sur les permissions
    
    VARIABLES CONTEXTE: page_obj, stats, postes, filters, title
    """
    user = request.user
    
    # Vérifier les permissions
    peut_voir_global = peut_voir_bordereaux(user)
    peut_voir_son_stock = has_permission(user, 'peut_voir_mon_stock_peage')
    
    if not peut_voir_global and not peut_voir_son_stock:
        log_acces_refuse(
            user,
            "Liste bordereaux",
            f"Ni peut_voir_bordereaux_peage ni peut_voir_mon_stock_peage (habilitation: {user.habilitation})",
            request
        )
        messages.error(request, "Vous n'avez pas la permission de voir les bordereaux.")
        return redirect('common:dashboard')
    
    logger.info(
        f"BORDEREAUX_LISTE - Accès par {user.username} "
        f"(global: {peut_voir_global}, son_stock: {peut_voir_son_stock})"
    )
    
    # Récupérer tous les transferts (un par bordereau)
    bordereaux = HistoriqueStock.objects.filter(
        type_stock='reapprovisionnement',
        type_mouvement='DEBIT'  # On prend uniquement les cessions pour éviter les doublons
    ).select_related('poste', 'poste_origine', 'poste_destination', 'effectue_par')
    
    # Filtrer selon les permissions
    if not peut_voir_global:
        # Utilisateur limité à son poste
        poste_user = getattr(user, 'poste_affectation', None)
        if poste_user:
            bordereaux = bordereaux.filter(
                Q(poste_origine=poste_user) |
                Q(poste_destination=poste_user)
            )
            logger.debug(
                f"BORDEREAUX_LISTE - Filtrage par poste {poste_user.code} pour {user.username}"
            )
        else:
            bordereaux = HistoriqueStock.objects.none()
            logger.warning(
                f"BORDEREAUX_LISTE - {user.username} n'a pas de poste d'affectation"
            )
    
    # Filtres additionnels (GET)
    poste_filter = request.GET.get('poste')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    
    if poste_filter:
        bordereaux = bordereaux.filter(
            Q(poste_origine_id=poste_filter) | Q(poste_destination_id=poste_filter)
        )
    
    if date_debut:
        bordereaux = bordereaux.filter(date_mouvement__gte=date_debut)
    
    if date_fin:
        bordereaux = bordereaux.filter(date_mouvement__lte=date_fin)
    
    bordereaux = bordereaux.order_by('-date_mouvement')
    
    # Pagination
    paginator = Paginator(bordereaux, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistiques
    stats = bordereaux.aggregate(
        total_transferts=Count('id'),
        montant_total=Sum('montant')
    )
    
    # Liste des postes pour le filtre (selon permissions)
    if peut_voir_global:
        postes = Poste.objects.filter(is_active=True).order_by('nom')
    else:
        poste_user = getattr(user, 'poste_affectation', None)
        if poste_user:
            postes = Poste.objects.filter(id=poste_user.id)
        else:
            postes = Poste.objects.none()
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'postes': postes,
        'filters': {
            'poste': poste_filter,
            'date_debut': date_debut,
            'date_fin': date_fin
        },
        'title': 'Liste des Bordereaux de Transfert'
    }
    
    return render(request, 'inventaire/liste_bordereaux.html', context)