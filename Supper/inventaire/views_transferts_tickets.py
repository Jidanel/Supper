# ===================================================================
# inventaire/views_transferts_tickets.py - VERSION MISE À JOUR
# Vues pour le transfert de tickets avec saisie de séries
# MISE À JOUR: Intégration des permissions granulaires
# ===================================================================

from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from decimal import Decimal
from datetime import date
from django.utils import timezone

from accounts.models import Poste, NotificationUtilisateur
from inventaire.models import *
from inventaire.forms import *
from inventaire.services.transfert_service import TransfertTicketsService
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
# VUES DE TRANSFERT DE TICKETS
# ===================================================================

@login_required
def selection_postes_transfert_tickets(request):
    """
    ÉTAPE 1 AMÉLIORÉE : Sélection des postes avec pré-chargement du stock
    
    PERMISSIONS REQUISES: peut_transferer_stock_peage
    
    HABILITATIONS AUTORISÉES:
    - admin_principal, coord_psrr, serv_info (admins)
    - serv_emission (service émission)
    - chef_peage (chef de poste péage - peut transférer depuis son poste)
    
    COMPORTEMENT :
    - GET initial : Affiche le formulaire vide
    - POST avec poste_origine seul : Recharge la page avec le stock affiché
    - POST avec poste_origine ET poste_destination : Passe à l'étape 2
    
    AVANT: @user_passes_test(is_admin) - Admin uniquement
    APRÈS: Permission peut_transferer_stock_peage - Admin, serv_emission, chef_peage
    
    VARIABLES CONTEXTE: form, postes, poste_origine, stock_origine_data, title
    """
    user = request.user
    
    # Vérification des permissions
    if not peut_transferer_stock(user):
        log_acces_refuse(
            user, 
            "Selection postes transfert tickets",
            f"Permission peut_transferer_stock_peage manquante (habilitation: {user.habilitation})",
            request
        )
        messages.error(request, "Vous n'avez pas la permission de transférer du stock.")
        return redirect('common:dashboard')
    
    logger.info(
        f"TRANSFERT_TICKETS - Accès sélection postes par {user.username} "
        f"(habilitation: {user.habilitation})"
    )
    
    poste_origine = None
    stock_origine_data = None
    form_errors = []
    
    # Récupérer le poste origine depuis POST ou GET
    poste_origine_id = request.POST.get('poste_origine') or request.GET.get('poste_origine')
    poste_destination_id = request.POST.get('poste_destination')
    
    # ============================================================
    # CAS 1 : Pré-chargement du stock quand poste_origine est sélectionné
    # ============================================================
    if poste_origine_id:
        try:
            poste_origine = Poste.objects.get(id=poste_origine_id, is_active=True)
            
            # Vérifier l'accès au poste d'origine
            if not user_has_acces_tous_postes(user) and not check_poste_access(user, poste_origine):
                log_acces_refuse(
                    user,
                    f"Poste origine {poste_origine.nom}",
                    "Accès au poste non autorisé",
                    request
                )
                messages.error(request, "Vous n'avez pas accès à ce poste d'origine.")
                poste_origine = None
                poste_origine_id = None
            else:
                # Récupérer les séries en stock pour ce poste
                series_stock = SerieTicket.objects.filter(
                    poste=poste_origine,
                    statut='stock'
                ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
                
                # Grouper par couleur
                stock_par_couleur = {}
                for serie in series_stock:
                    couleur_key = serie.couleur.libelle_affichage
                    if couleur_key not in stock_par_couleur:
                        stock_par_couleur[couleur_key] = {
                            'couleur': serie.couleur,
                            'series': [],
                            'total_tickets': 0,
                            'valeur_totale': Decimal('0')
                        }
                    
                    stock_par_couleur[couleur_key]['series'].append({
                        'id': serie.id,
                        'numero_premier': serie.numero_premier,
                        'numero_dernier': serie.numero_dernier,
                        'nombre_tickets': serie.nombre_tickets,
                        'valeur_monetaire': serie.valeur_monetaire
                    })
                    stock_par_couleur[couleur_key]['total_tickets'] += serie.nombre_tickets
                    stock_par_couleur[couleur_key]['valeur_totale'] += serie.valeur_monetaire
                
                stock_origine_data = stock_par_couleur
                
                logger.debug(
                    f"TRANSFERT_TICKETS - Stock chargé pour {poste_origine.nom}: "
                    f"{len(series_stock)} séries, {sum(s.nombre_tickets for s in series_stock)} tickets"
                )
                
        except Poste.DoesNotExist:
            messages.error(request, "Poste origine introuvable")
            poste_origine = None
            poste_origine_id = None
    
    # ============================================================
    # CAS 2 : Soumission complète du formulaire (POST avec les 2 postes)
    # ============================================================
    if request.method == 'POST' and poste_origine_id and poste_destination_id:
        form = SelectionPostesTransfertFormAmeliore(request.POST)
        
        if form.is_valid():
            poste_origine_valid = form.cleaned_data['poste_origine']
            poste_destination_valid = form.cleaned_data['poste_destination']
            
            # Vérifier l'accès au poste d'origine
            if not user_has_acces_tous_postes(user) and not check_poste_access(user, poste_origine_valid):
                log_acces_refuse(
                    user,
                    f"Transfert depuis {poste_origine_valid.nom}",
                    "Accès au poste d'origine non autorisé",
                    request
                )
                messages.error(request, "Vous n'avez pas accès au poste d'origine sélectionné.")
                return redirect('inventaire:selection_postes_transfert_tickets')
            
            # Vérifier que le poste origine a du stock
            if not stock_origine_data:
                messages.error(request, f"Le poste {poste_origine_valid.nom} n'a aucun stock de tickets à transférer.")
            else:
                # Stocker en session
                request.session['transfert_tickets'] = {
                    'origine_id': poste_origine_valid.id,
                    'destination_id': poste_destination_valid.id
                }
                
                log_user_action(
                    user,
                    "TRANSFERT_TICKETS_SELECTION",
                    f"Sélection transfert: {poste_origine_valid.nom} → {poste_destination_valid.nom}",
                    request
                )
                
                messages.success(
                    request, 
                    f"Transfert de {poste_origine_valid.nom} vers {poste_destination_valid.nom}. "
                    f"Saisissez maintenant les tickets à transférer."
                )
                
                return redirect('inventaire:saisie_tickets_transfert')
        else:
            # Erreurs de validation du formulaire
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{error}")
    else:
        # Initialiser le formulaire avec les données existantes
        initial_data = {}
        if poste_origine_id:
            initial_data['poste_origine'] = poste_origine_id
        if poste_destination_id:
            initial_data['poste_destination'] = poste_destination_id
            
        form = SelectionPostesTransfertFormAmeliore(initial=initial_data)
    
    # ============================================================
    # Récupérer les postes accessibles à l'utilisateur
    # ============================================================
    if user_has_acces_tous_postes(user):
        postes = Poste.objects.filter(is_active=True).order_by('nom')
    else:
        # Utilisateur limité à son poste
        if user.poste_affectation:
            postes = Poste.objects.filter(id=user.poste_affectation.id, is_active=True)
        else:
            postes = Poste.objects.none()
    
    postes_data = []
    for poste in postes:
        stock = GestionStock.objects.filter(poste=poste).first()
        postes_data.append({
            'poste': poste,
            'stock_actuel': stock.valeur_monetaire if stock else Decimal('0'),
            'tickets_actuels': stock.nombre_tickets if stock else 0
        })
    
    context = {
        'form': form,
        'postes': postes_data,
        'poste_origine': poste_origine,
        'stock_origine_data': stock_origine_data,
        'title': 'Transférer des Tickets Entre Postes'
    }
    
    return render(request, 'inventaire/selection_postes_transfert_tickets.html', context)


@login_required
def saisie_tickets_transfert(request):
    """
    ÉTAPE 2 AMÉLIORÉE : Saisie avec couleurs pré-chargées et validation améliorée
    
    PERMISSIONS REQUISES: peut_transferer_stock_peage
    
    HABILITATIONS AUTORISÉES:
    - admin_principal, coord_psrr, serv_info (admins)
    - serv_emission (service émission)
    - chef_peage (chef de poste péage)
    
    AVANT: @user_passes_test(is_admin) - Admin uniquement
    APRÈS: Permission peut_transferer_stock_peage
    
    VARIABLES CONTEXTE: form, poste_origine, poste_destination, stock_origine, series_par_couleur, title
    """
    user = request.user
    
    # Vérification des permissions
    if not peut_transferer_stock(user):
        log_acces_refuse(
            user,
            "Saisie tickets transfert",
            f"Permission peut_transferer_stock_peage manquante (habilitation: {user.habilitation})",
            request
        )
        messages.error(request, "Vous n'avez pas la permission de transférer du stock.")
        return redirect('common:dashboard')
    
    # Récupérer les postes de la session
    postes_data = request.session.get('transfert_tickets')
    
    if not postes_data:
        messages.error(request, "Veuillez d'abord sélectionner les postes")
        return redirect('inventaire:selection_postes_transfert_tickets')
    
    poste_origine = get_object_or_404(Poste, id=postes_data['origine_id'])
    poste_destination = get_object_or_404(Poste, id=postes_data['destination_id'])
    
    # Vérifier l'accès au poste d'origine
    if not user_has_acces_tous_postes(user) and not check_poste_access(user, poste_origine):
        log_acces_refuse(
            user,
            f"Saisie transfert depuis {poste_origine.nom}",
            "Accès au poste d'origine non autorisé",
            request
        )
        messages.error(request, "Vous n'avez pas accès au poste d'origine.")
        if 'transfert_tickets' in request.session:
            del request.session['transfert_tickets']
        return redirect('inventaire:selection_postes_transfert_tickets')
    
    logger.info(
        f"TRANSFERT_TICKETS - Saisie par {user.username}: "
        f"{poste_origine.nom} → {poste_destination.nom}"
    )
    
    # Récupérer le stock et les séries disponibles
    stock_origine = GestionStock.objects.filter(poste=poste_origine).first()
    
    series_disponibles = SerieTicket.objects.filter(
        poste=poste_origine,
        statut='stock'
    ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
    
    if request.method == 'POST':
        form = TransfertStockTicketsFormDynamique(
            request.POST, 
            poste_origine=poste_origine
        )
        
        if form.is_valid():
            couleur_id = form.cleaned_data['couleur_disponible']
            numero_premier = form.cleaned_data['numero_premier']
            numero_dernier = form.cleaned_data['numero_dernier']
            commentaire = form.cleaned_data.get('commentaire', '')
            
            # Récupérer l'objet couleur
            couleur_obj = get_object_or_404(CouleurTicket, id=couleur_id)
            
            # === VÉRIFICATION AMÉLIORÉE ===
            # 1. Vérifier disponibilité au poste origine
            disponible, msg, _ = SerieTicket.verifier_disponibilite_serie_complete(
                poste_origine, couleur_obj, numero_premier, numero_dernier
            )
            
            if not disponible:
                messages.error(request, msg)
                return redirect('inventaire:saisie_tickets_transfert')
            
            # 2. Vérifier qu'aucun ticket n'a été vendu
            tickets_vendus = SerieTicket.objects.filter(
                couleur=couleur_obj,
                statut='vendu',
                numero_premier__lte=numero_dernier,
                numero_dernier__gte=numero_premier
            )
            
            if tickets_vendus.exists():
                ticket_vendu = tickets_vendus.first()
                messages.error(
                    request,
                    f"❌ TRANSFERT IMPOSSIBLE : Des tickets de cette série ont déjà été vendus. "
                    f"Série vendue: {couleur_obj.libelle_affichage} "
                    f"#{ticket_vendu.numero_premier}-{ticket_vendu.numero_dernier} "
                    f"le {ticket_vendu.date_utilisation.strftime('%d/%m/%Y') if ticket_vendu.date_utilisation else 'date inconnue'}. "
                    f"Un ticket vendu ne peut pas être transféré."
                )
                return redirect('inventaire:saisie_tickets_transfert')
            
            # Calculer montant
            nombre_tickets = numero_dernier - numero_premier + 1
            montant = Decimal(nombre_tickets) * Decimal('500')
            
            # Stocker en session pour confirmation
            request.session['transfert_tickets_details'] = {
                'couleur_id': couleur_obj.id,
                'couleur_libelle': couleur_obj.libelle_affichage,
                'numero_premier': numero_premier,
                'numero_dernier': numero_dernier,
                'nombre_tickets': nombre_tickets,
                'montant': str(montant),
                'commentaire': commentaire
            }
            
            log_user_action(
                user,
                "TRANSFERT_TICKETS_SAISIE",
                f"Saisie transfert: {nombre_tickets} tickets {couleur_obj.libelle_affichage} "
                f"#{numero_premier}-{numero_dernier} ({montant:,.0f} FCFA)",
                request
            )
            
            return redirect('inventaire:confirmation_transfert_tickets')
    else:
        form = TransfertStockTicketsFormDynamique(poste_origine=poste_origine)
    
    # Grouper séries par couleur pour affichage
    series_par_couleur = {}
    for serie in series_disponibles:
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
    
    context = {
        'form': form,
        'poste_origine': poste_origine,
        'poste_destination': poste_destination,
        'stock_origine': stock_origine,
        'series_par_couleur': series_par_couleur,
        'title': f'Saisie des Tickets à Transférer'
    }
    
    return render(request, 'inventaire/saisie_tickets_transfert.html', context)


@login_required
def confirmation_transfert_tickets(request):
    """
    ÉTAPE 3 : Confirmation avec le nouveau service
    
    PERMISSIONS REQUISES: peut_transferer_stock_peage
    
    HABILITATIONS AUTORISÉES:
    - admin_principal, coord_psrr, serv_info (admins)
    - serv_emission (service émission)
    - chef_peage (chef de poste péage)
    
    AVANT: @user_passes_test(is_admin) - Admin uniquement
    APRÈS: Permission peut_transferer_stock_peage
    
    VARIABLES CONTEXTE: poste_origine, poste_destination, couleur, numero_premier, 
                        numero_dernier, nombre_tickets, montant, commentaire,
                        stock_origine_avant, stock_origine_apres, 
                        stock_destination_avant, stock_destination_apres, title
    """
    user = request.user
    
    # Vérification des permissions
    if not peut_transferer_stock(user):
        log_acces_refuse(
            user,
            "Confirmation transfert tickets",
            f"Permission peut_transferer_stock_peage manquante (habilitation: {user.habilitation})",
            request
        )
        messages.error(request, "Vous n'avez pas la permission de transférer du stock.")
        return redirect('common:dashboard')
    
    postes_data = request.session.get('transfert_tickets')
    details_data = request.session.get('transfert_tickets_details')
    
    if not postes_data or not details_data:
        messages.error(request, "Données de transfert manquantes")
        return redirect('inventaire:selection_postes_transfert_tickets')
    
    poste_origine = get_object_or_404(Poste, id=postes_data['origine_id'])
    poste_destination = get_object_or_404(Poste, id=postes_data['destination_id'])
    couleur = get_object_or_404(CouleurTicket, id=details_data['couleur_id'])
    
    # Vérifier l'accès au poste d'origine
    if not user_has_acces_tous_postes(user) and not check_poste_access(user, poste_origine):
        log_acces_refuse(
            user,
            f"Confirmation transfert depuis {poste_origine.nom}",
            "Accès au poste d'origine non autorisé",
            request
        )
        messages.error(request, "Vous n'avez pas accès au poste d'origine.")
        if 'transfert_tickets' in request.session:
            del request.session['transfert_tickets']
        if 'transfert_tickets_details' in request.session:
            del request.session['transfert_tickets_details']
        return redirect('inventaire:selection_postes_transfert_tickets')
    
    # Récupérer stocks actuels pour affichage
    stock_origine, _ = GestionStock.objects.get_or_create(
        poste=poste_origine,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    stock_destination, _ = GestionStock.objects.get_or_create(
        poste=poste_destination,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    montant = Decimal(details_data['montant'])
    
    # Calculer stocks après transfert (pour affichage)
    stock_origine_apres = stock_origine.valeur_monetaire - montant
    stock_destination_apres = stock_destination.valeur_monetaire + montant
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirmer':
            numero_premier = details_data['numero_premier']
            numero_dernier = details_data['numero_dernier']
            commentaire = details_data.get('commentaire', '')
            
            # ============================================================
            # VALIDATION via le service
            # ============================================================
            est_valide, msg_validation, _ = TransfertTicketsService.valider_transfert(
                poste_origine, poste_destination, couleur,
                numero_premier, numero_dernier
            )
            
            if not est_valide:
                messages.error(request, msg_validation)
                return redirect('inventaire:saisie_tickets_transfert')
            
            # ============================================================
            # EXÉCUTION via le service
            # ============================================================
            success, message, serie_origine, serie_destination = TransfertTicketsService.executer_transfert(
                poste_origine=poste_origine,
                poste_destination=poste_destination,
                couleur=couleur,
                numero_premier=numero_premier,
                numero_dernier=numero_dernier,
                user=user,
                commentaire=commentaire
            )
            
            if success:
                # Nettoyer la session
                del request.session['transfert_tickets']
                del request.session['transfert_tickets_details']
                
                messages.success(request, f"✅ {message}")
                
                # Journaliser avec détails complets
                log_user_action(
                    user,
                    "TRANSFERT_TICKETS_EXECUTE",
                    f"Transfert exécuté: {details_data['nombre_tickets']} tickets "
                    f"{couleur.libelle_affichage} #{numero_premier}-{numero_dernier} "
                    f"de {poste_origine.nom} vers {poste_destination.nom} "
                    f"(montant: {montant:,.0f} FCFA)",
                    request
                )
                
                logger.info(
                    f"TRANSFERT_TICKETS_SUCCES - Par {user.username}: "
                    f"{details_data['nombre_tickets']} tickets {couleur.libelle_affichage} "
                    f"#{numero_premier}-{numero_dernier} | "
                    f"{poste_origine.code} → {poste_destination.code} | "
                    f"Montant: {montant:,.0f} FCFA"
                )
                
                return redirect('inventaire:liste_bordereaux')
            else:
                messages.error(request, f"❌ {message}")
                
                logger.error(
                    f"TRANSFERT_TICKETS_ECHEC - Par {user.username}: "
                    f"{details_data['nombre_tickets']} tickets {couleur.libelle_affichage} "
                    f"| Erreur: {message}"
                )
                
                return redirect('inventaire:saisie_tickets_transfert')
        
        elif action == 'annuler':
            if 'transfert_tickets' in request.session:
                del request.session['transfert_tickets']
            if 'transfert_tickets_details' in request.session:
                del request.session['transfert_tickets_details']
            
            log_user_action(
                user,
                "TRANSFERT_TICKETS_ANNULE",
                f"Transfert annulé: {poste_origine.nom} → {poste_destination.nom}",
                request
            )
            
            messages.info(request, "Transfert annulé")
            return redirect('inventaire:selection_postes_transfert_tickets')
    
    context = {
        'poste_origine': poste_origine,
        'poste_destination': poste_destination,
        'couleur': couleur,
        'numero_premier': details_data['numero_premier'],
        'numero_dernier': details_data['numero_dernier'],
        'nombre_tickets': details_data['nombre_tickets'],
        'montant': montant,
        'commentaire': details_data.get('commentaire', ''),
        'stock_origine_avant': stock_origine.valeur_monetaire,
        'stock_origine_apres': stock_origine_apres,
        'stock_destination_avant': stock_destination.valeur_monetaire,
        'stock_destination_apres': stock_destination_apres,
        'title': 'Confirmation du transfert'
    }
    
    return render(request, 'inventaire/confirmation_transfert_tickets.html', context)


@login_required
def ajax_series_par_couleur(request):
    """
    Vue AJAX pour récupérer les séries disponibles par couleur
    
    PERMISSIONS REQUISES: 
    - peut_transferer_stock_peage (pour transferts)
    - OU peut_voir_mon_stock_peage (pour consultation de son propre stock)
    
    AVANT: @user_passes_test(is_admin) - Admin uniquement
    APRÈS: Permissions peut_transferer_stock_peage OU peut_voir_mon_stock_peage
    """
    user = request.user
    poste_id = request.GET.get('poste_id')
    couleur_id = request.GET.get('couleur_id')
    
    if not poste_id or not couleur_id:
        return JsonResponse({'error': 'Paramètres manquants'}, status=400)
    
    # Vérifier les permissions
    peut_transferer = peut_transferer_stock(user)
    peut_voir_stock = has_permission(user, 'peut_voir_mon_stock_peage')
    
    if not peut_transferer and not peut_voir_stock:
        log_acces_refuse(
            user,
            f"AJAX series par couleur (poste {poste_id})",
            f"Permissions manquantes (habilitation: {user.habilitation})",
            request
        )
        return JsonResponse({
            'error': 'Permission refusée',
            'code': 'permission_denied'
        }, status=403)
    
    # Vérifier l'accès au poste
    try:
        poste = Poste.objects.get(id=poste_id, is_active=True)
    except Poste.DoesNotExist:
        return JsonResponse({'error': 'Poste introuvable'}, status=404)
    
    if not user_has_acces_tous_postes(user) and not check_poste_access(user, poste):
        log_acces_refuse(
            user,
            f"AJAX series par couleur - Poste {poste.nom}",
            "Accès au poste non autorisé",
            request
        )
        return JsonResponse({
            'error': 'Accès au poste refusé',
            'code': 'poste_access_denied'
        }, status=403)
    
    try:
        series = SerieTicket.objects.filter(
            poste_id=poste_id,
            couleur_id=couleur_id,
            statut='stock'
        ).order_by('numero_premier').values(
            'id', 'numero_premier', 'numero_dernier', 
            'nombre_tickets', 'valeur_monetaire'
        )
        
        logger.debug(
            f"AJAX_SERIES - {user.username} consulte {series.count()} séries "
            f"(poste: {poste.code}, couleur_id: {couleur_id})"
        )
        
        return JsonResponse({
            'series': list(series),
            'count': series.count()
        })
        
    except Exception as e:
        logger.error(f"AJAX_SERIES - Erreur: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def detail_bordereau_transfert(request, numero_bordereau):
    """
    Vue qui affiche CESSION + RÉCEPTION sur une seule page
    
    PERMISSIONS REQUISES:
    - peut_voir_bordereaux_peage (accès global à tous les bordereaux)
    - OU appartenance à l'un des postes concernés par le transfert
    
    HABILITATIONS AVEC ACCÈS GLOBAL:
    - admin_principal, coord_psrr, serv_info (admins)
    - services centraux (serv_emission, serv_controle, serv_ordre)
    - cisop_peage
    
    HABILITATIONS AVEC ACCÈS LIMITÉ À LEUR POSTE:
    - chef_peage, agent_inventaire
    
    AVANT: Vérification manuelle is_admin + check poste
    APRÈS: Permission peut_voir_bordereaux_peage OU check poste concerné
    
    VARIABLES CONTEXTE: numero_bordereau, hist_cession, hist_reception, poste_origine,
                        poste_destination, montant, nombre_tickets, date_transfert,
                        effectue_par, series_par_couleur, title
    """
    user = request.user
    
    # Récupérer les 2 historiques
    hist_cession = get_object_or_404(
        HistoriqueStock,
        numero_bordereau=numero_bordereau,
        type_mouvement='DEBIT'
    )
    
    hist_reception = get_object_or_404(
        HistoriqueStock,
        numero_bordereau=numero_bordereau,
        type_mouvement='CREDIT'
    )
    
    # Vérifier permissions
    peut_voir_global = peut_voir_bordereaux(user)
    
    if not peut_voir_global:
        # Vérifier si l'utilisateur a accès à l'un des postes concernés
        postes_autorises = [hist_cession.poste.id, hist_reception.poste.id]
        poste_user = getattr(user, 'poste_affectation', None)
        
        if not poste_user or poste_user.id not in postes_autorises:
            log_acces_refuse(
                user,
                f"Bordereau {numero_bordereau}",
                f"Ni permission peut_voir_bordereaux_peage ni poste concerné "
                f"(habilitation: {user.habilitation}, poste: {poste_user.code if poste_user else 'Aucun'})",
                request
            )
            messages.error(request, "Vous n'avez pas accès à ce bordereau.")
            return redirect('common:dashboard')
    
    logger.info(
        f"BORDEREAU_DETAIL - {user.username} consulte bordereau {numero_bordereau} "
        f"(habilitation: {user.habilitation})"
    )
    
    # Récupérer les séries transférées
    series_transferees = SerieTicket.objects.filter(
        poste=hist_cession.poste,
        statut='transfere',
        poste_destination_transfert=hist_reception.poste,
        date_utilisation=hist_cession.date_mouvement.date()
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
    
    context = {
        'numero_bordereau': numero_bordereau,
        'hist_cession': hist_cession,
        'hist_reception': hist_reception,
        'poste_origine': hist_cession.poste,
        'poste_destination': hist_reception.poste,
        'montant': hist_cession.montant,
        'nombre_tickets': hist_cession.nombre_tickets,
        'date_transfert': hist_cession.date_mouvement,
        'effectue_par': hist_cession.effectue_par,
        'series_par_couleur': series_par_couleur,
        'title': f'Bordereau de Transfert N°{numero_bordereau}'
    }
    
    return render(request, 'inventaire/detail_bordereau_transfert.html', context)