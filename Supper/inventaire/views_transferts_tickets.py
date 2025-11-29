# ===================================================================
# inventaire/views_transferts_tickets.py - NOUVEAU FICHIER
# Vues pour le transfert de tickets avec saisie de séries
# ===================================================================

from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from decimal import Decimal
from datetime import date, timezone

from accounts.models import Poste, NotificationUtilisateur
from inventaire.models import *
from inventaire.forms import *
from inventaire.services.transfert_service import TransfertTicketsService
from common.utils import log_user_action
import logging

logger = logging.getLogger('supper')

def is_admin(user):
    return user.is_authenticated and (
        user.is_superuser or 
        user.is_staff or
        (hasattr(user, 'is_admin') and user.is_admin())
    )


@login_required
@user_passes_test(is_admin)
def selection_postes_transfert_tickets(request):
    """
    ÉTAPE 1 AMÉLIORÉE : Sélection des postes avec pré-chargement du stock
    
    COMPORTEMENT :
    - GET initial : Affiche le formulaire vide
    - POST avec poste_origine seul : Recharge la page avec le stock affiché
    - POST avec poste_origine ET poste_destination : Passe à l'étape 2
    """
    
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
            
            # Vérifier que le poste origine a du stock
            if not stock_origine_data:
                messages.error(request, f"Le poste {poste_origine_valid.nom} n'a aucun stock de tickets à transférer.")
            else:
                # Stocker en session
                request.session['transfert_tickets'] = {
                    'origine_id': poste_origine_valid.id,
                    'destination_id': poste_destination_valid.id
                }
                
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
    # Récupérer tous les postes avec leur stock pour la vue d'ensemble
    # ============================================================
    postes = Poste.objects.filter(is_active=True).order_by('nom')
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
@user_passes_test(is_admin)
def saisie_tickets_transfert(request):
    """
    ÉTAPE 2 AMÉLIORÉE : Saisie avec couleurs pré-chargées et validation améliorée
    """
    
    # Récupérer les postes de la session
    postes_data = request.session.get('transfert_tickets')
    
    if not postes_data:
        messages.error(request, "Veuillez d'abord sélectionner les postes")
        return redirect('inventaire:selection_postes_transfert_tickets')
    
    poste_origine = get_object_or_404(Poste, id=postes_data['origine_id'])
    poste_destination = get_object_or_404(Poste, id=postes_data['destination_id'])
    
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
            
            # 3. NOTE: Pas de vérification de chevauchement au poste destination
            # Les tickets peuvent coexister avec d'autres séries de même couleur
            
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
@user_passes_test(is_admin)
def confirmation_transfert_tickets(request):
    """
    ÉTAPE 3 : Confirmation avec le nouveau service
    """
    postes_data = request.session.get('transfert_tickets')
    details_data = request.session.get('transfert_tickets_details')
    
    if not postes_data or not details_data:
        messages.error(request, "Données de transfert manquantes")
        return redirect('inventaire:selection_postes_transfert_tickets')
    
    poste_origine = get_object_or_404(Poste, id=postes_data['origine_id'])
    poste_destination = get_object_or_404(Poste, id=postes_data['destination_id'])
    couleur = get_object_or_404(CouleurTicket, id=details_data['couleur_id'])
    
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
                user=request.user,
                commentaire=commentaire
            )
            
            if success:
                # Nettoyer la session
                del request.session['transfert_tickets']
                del request.session['transfert_tickets_details']
                
                messages.success(request, f"✅ {message}")
                
                # Journaliser
                log_user_action(
                    request.user,
                    "Transfert de tickets",
                    f"{details_data['nombre_tickets']} tickets {couleur.libelle_affichage} "
                    f"#{numero_premier}-{numero_dernier} de {poste_origine.nom} vers {poste_destination.nom}",
                    request
                )
                
                return redirect('inventaire:liste_bordereaux')
            else:
                messages.error(request, f"❌ {message}")
                return redirect('inventaire:saisie_tickets_transfert')
        
        elif action == 'annuler':
            if 'transfert_tickets' in request.session:
                del request.session['transfert_tickets']
            if 'transfert_tickets_details' in request.session:
                del request.session['transfert_tickets_details']
            
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
@user_passes_test(is_admin)
def ajax_series_par_couleur(request):
    """
    Vue AJAX pour récupérer les séries disponibles par couleur
    """
    poste_id = request.GET.get('poste_id')
    couleur_id = request.GET.get('couleur_id')
    
    if not poste_id or not couleur_id:
        return JsonResponse({'error': 'Paramètres manquants'}, status=400)
    
    try:
        series = SerieTicket.objects.filter(
            poste_id=poste_id,
            couleur_id=couleur_id,
            statut='stock'
        ).order_by('numero_premier').values(
            'id', 'numero_premier', 'numero_dernier', 
            'nombre_tickets', 'valeur_monetaire'
        )
        
        return JsonResponse({
            'series': list(series),
            'count': series.count()
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)



@login_required
def detail_bordereau_transfert(request, numero_bordereau):
    """
    Vue qui affiche CESSION + RÉCEPTION sur une seule page
    (pas besoin de spécifier type_bordereau)
    """
    
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
    if not request.user.is_admin:
        postes_autorises = [hist_cession.poste.id, hist_reception.poste.id]
        if not request.user.poste_affectation or \
           request.user.poste_affectation.id not in postes_autorises:
            messages.error(request, "Accès non autorisé")
            return redirect('common:dashboard')
    
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