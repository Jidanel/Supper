# ===================================================================
# inventaire/views_transferts_tickets.py - NOUVEAU FICHIER
# Vues pour le transfert de tickets avec saisie de séries
# ===================================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from decimal import Decimal
from datetime import date, timezone

from accounts.models import Poste, NotificationUtilisateur
from inventaire.models import *
from inventaire.forms import TransfertStockTicketsForm, SelectionPostesTransfertForm
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
    ÉTAPE 1 : Sélection des postes origine et destination
    """
    
    if request.method == 'POST':
        form = SelectionPostesTransfertForm(request.POST)
        
        if form.is_valid():
            poste_origine = form.cleaned_data['poste_origine']
            poste_destination = form.cleaned_data['poste_destination']
            
            # Stocker en session
            request.session['transfert_tickets_postes'] = {
                'origine_id': poste_origine.id,
                'destination_id': poste_destination.id
            }
            
            return redirect('inventaire:saisie_tickets_transfert')
    else:
        form = SelectionPostesTransfertForm()
    
    # Récupérer les stocks actuels pour affichage
    postes = Poste.objects.filter(is_active=True).order_by('nom')
    postes_data = []
    
    for poste in postes:
        stock = GestionStock.objects.filter(poste=poste).first()
        
        # Récupérer séries en stock
        series = SerieTicket.objects.filter(
            poste=poste,
            statut='stock'
        ).select_related('couleur')
        
        postes_data.append({
            'poste': poste,
            'stock_actuel': stock.valeur_monetaire if stock else Decimal('0'),
            'series_disponibles': series
        })
    
    context = {
        'form': form,
        'postes': postes_data,
        'title': 'Transférer des Tickets Entre Postes'
    }
    
    return render(request, 'inventaire/selection_postes_transfert_tickets.html', context)


@login_required
@user_passes_test(is_admin)
def saisie_tickets_transfert(request):
    """
    ÉTAPE 2 : Saisie des séries de tickets à transférer
    """
    
    # Récupérer les postes de la session
    postes_data = request.session.get('transfert_tickets_postes')
    
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
        form = TransfertStockTicketsForm(request.POST)
        
        if form.is_valid():
            couleur_saisie = form.cleaned_data['couleur_saisie']
            numero_premier = form.cleaned_data['numero_premier']
            numero_dernier = form.cleaned_data['numero_dernier']
            commentaire = form.cleaned_data.get('commentaire', '')
            
            # Obtenir ou créer la couleur
            couleur_obj = CouleurTicket.obtenir_ou_creer(couleur_saisie)
            
            # Vérifier disponibilité COMPLÈTE (incluant vérification tickets vendus)
            disponible, msg, _ = SerieTicket.verifier_disponibilite_serie_complete(
                poste_origine, couleur_obj, numero_premier, numero_dernier
            )
            
            if not disponible:
                messages.error(request, msg)
                return redirect('inventaire:saisie_tickets_transfert')
            
            # Vérifier qu'aucun ticket n'a été vendu cette année
            annee_actuelle = date.today().year
            
            tickets_vendus = SerieTicket.objects.filter(
                couleur=couleur_obj,
                statut='vendu',
                numero_premier__lte=numero_dernier,
                numero_dernier__gte=numero_premier,
                date_utilisation__year=annee_actuelle
            )
            
            if tickets_vendus.exists():
                messages.error(
                    request,
                    f"❌ TRANSFERT IMPOSSIBLE : Des tickets de cette série ont déjà été vendus en {annee_actuelle}. "
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
            
            return redirect('inventaire:confirmation_transfert_tickets')
    else:
        form = TransfertStockTicketsForm()
    
    # Grouper séries par couleur
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


# inventaire/views_transferts_tickets.py
# FONCTION COMPLÈTE confirmation_transfert_tickets avec Event Sourcing

@login_required
@user_passes_test(is_admin)
def confirmation_transfert_tickets(request):
    """
    VERSION COMPLÈTE avec Event Sourcing intégré
    ÉTAPE 3 : Confirmation du transfert avec affichage complet
    """
    from django.db import transaction
    from decimal import Decimal
    from datetime import date, datetime
    from django.utils import timezone
    from inventaire.models import (
        GestionStock, HistoriqueStock, SerieTicket, 
        CouleurTicket, StockEvent
    )
    from accounts.models import NotificationUtilisateur, UtilisateurSUPPER
    from common.utils import log_user_action
    
    # Récupérer données session
    postes_data = request.session.get('transfert_tickets_postes')
    details_data = request.session.get('transfert_tickets_details')
    
    if not postes_data or not details_data:
        messages.error(request, "Données de transfert manquantes")
        return redirect('inventaire:selection_postes_transfert_tickets')
    
    poste_origine = get_object_or_404(Poste, id=postes_data['origine_id'])
    poste_destination = get_object_or_404(Poste, id=postes_data['destination_id'])
    couleur = get_object_or_404(CouleurTicket, id=details_data['couleur_id'])
    
    # Récupérer stocks actuels
    stock_origine, _ = GestionStock.objects.get_or_create(
        poste=poste_origine,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    stock_destination, _ = GestionStock.objects.get_or_create(
        poste=poste_destination,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    montant = Decimal(details_data['montant'])
    
    # Calculer stocks après transfert
    stock_origine_apres = stock_origine.valeur_monetaire - montant
    stock_destination_apres = stock_destination.valeur_monetaire + montant
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirmer':
            try:
                with transaction.atomic():
                    # ===== 1. EXÉCUTER LE TRANSFERT DE SÉRIE =====
                    numero_premier = details_data['numero_premier']
                    numero_dernier = details_data['numero_dernier']
                    nombre_tickets = details_data['nombre_tickets']
                    commentaire = details_data['commentaire']
                    
                    # Appeler la méthode transferer_serie (version modifiée avec Event Sourcing)
                    success, message, serie_origine, serie_destination = SerieTicket.transferer_serie(
                        poste_origine=poste_origine,
                        poste_destination=poste_destination,
                        couleur=couleur,
                        numero_premier=numero_premier,
                        numero_dernier=numero_dernier,
                        user=request.user,
                        commentaire=commentaire
                    )
                    
                    if not success:
                        raise Exception(message)
                    
                    # ===== 2. CRÉER LES ÉVÉNEMENTS EVENT SOURCING =====
                    timestamp = timezone.now()
                    
                    # Récupérer le numéro de bordereau depuis l'historique créé
                    hist_recent = HistoriqueStock.objects.filter(
                        poste_origine=poste_origine,
                        poste_destination=poste_destination,
                        type_mouvement='DEBIT'
                    ).order_by('-date_mouvement').first()
                    
                    numero_bordereau = hist_recent.numero_bordereau if hist_recent else f"TR-{timestamp.strftime('%Y%m%d%H%M%S')}"
                    
                    # Métadonnées de la série transférée
                    serie_metadata = {
                        'couleur': couleur.libelle_affichage,
                        'couleur_code': couleur.code_normalise,
                        'numero_premier': numero_premier,
                        'numero_dernier': numero_dernier,
                        'nombre_tickets': nombre_tickets,
                        'valeur': str(montant)
                    }
                    
                    # ÉVÉNEMENT 1 : Sortie du poste origine
                    event_sortie = StockEvent.objects.create(
                        poste=poste_origine,
                        event_type='TRANSFERT_OUT',
                        event_datetime=timestamp,
                        montant_variation=-montant,  # NÉGATIF car c'est une sortie
                        nombre_tickets_variation=-nombre_tickets,  # NÉGATIF
                        stock_resultant=stock_origine_apres,
                        tickets_resultants=int(stock_origine_apres / 500),
                        effectue_par=request.user,
                        reference_id=str(serie_origine.id) if serie_origine else '',
                        reference_type='SerieTicket',
                        metadata={
                            'operation': 'transfert_tickets_sortie',
                            'poste_destination': {
                                'id': poste_destination.id,
                                'nom': poste_destination.nom,
                                'code': poste_destination.code
                            },
                            'serie_transferee': serie_metadata,
                            'numero_bordereau': numero_bordereau,
                            'commentaire': commentaire
                        },
                        commentaire=f"Transfert série {couleur.libelle_affichage} #{numero_premier}-{numero_dernier} vers {poste_destination.nom}"
                    )
                    
                    # ÉVÉNEMENT 2 : Entrée au poste destination
                    event_entree = StockEvent.objects.create(
                        poste=poste_destination,
                        event_type='TRANSFERT_IN',
                        event_datetime=timestamp,
                        montant_variation=montant,  # POSITIF car c'est une entrée
                        nombre_tickets_variation=nombre_tickets,  # POSITIF
                        stock_resultant=stock_destination_apres,
                        tickets_resultants=int(stock_destination_apres / 500),
                        effectue_par=request.user,
                        reference_id=str(serie_destination.id) if serie_destination else '',
                        reference_type='SerieTicket',
                        metadata={
                            'operation': 'transfert_tickets_entree',
                            'poste_origine': {
                                'id': poste_origine.id,
                                'nom': poste_origine.nom,
                                'code': poste_origine.code
                            },
                            'serie_recue': serie_metadata,
                            'numero_bordereau': numero_bordereau,
                            'commentaire': commentaire
                        },
                        commentaire=f"Réception série {couleur.libelle_affichage} #{numero_premier}-{numero_dernier} depuis {poste_origine.nom}"
                    )
                    
                    # ===== 3. NETTOYER LA SESSION =====
                    del request.session['transfert_tickets_postes']
                    del request.session['transfert_tickets_details']
                    
                    # ===== 4. JOURNALISER L'ACTION =====
                    log_user_action(
                        request.user,
                        "Transfert de tickets avec séries",
                        f"Transfert réussi : {nombre_tickets} tickets {couleur.libelle_affichage} "
                        f"#{numero_premier}-{numero_dernier} de {poste_origine.nom} vers {poste_destination.nom}. "
                        f"Bordereau: {numero_bordereau}",
                        request
                    )
                    
                    # ===== 5. MESSAGE DE SUCCÈS =====
                    messages.success(
                        request,
                        f"✅ Transfert réussi ! {nombre_tickets} tickets "
                        f"{couleur.libelle_affichage} #{numero_premier}-"
                        f"{numero_dernier} transférés. "
                        f"Stock origine: {stock_origine_apres:,.0f} FCFA, "
                        f"Stock destination: {stock_destination_apres:,.0f} FCFA"
                    )
                    
                    # ===== 6. REDIRECTION =====
                    if hist_recent and hist_recent.numero_bordereau:
                        return redirect('inventaire:detail_bordereau_transfert', 
                                      numero_bordereau=hist_recent.numero_bordereau)
                    else:
                        return redirect('inventaire:liste_bordereaux')
                    
            except Exception as e:
                logger.error(f"Erreur transfert tickets : {str(e)}", exc_info=True)
                messages.error(request, f"❌ Erreur lors du transfert : {str(e)}")
                return redirect('inventaire:saisie_tickets_transfert')
        
        elif action == 'annuler':
            # Nettoyer la session
            if 'transfert_tickets_postes' in request.session:
                del request.session['transfert_tickets_postes']
            if 'transfert_tickets_details' in request.session:
                del request.session['transfert_tickets_details']
            
            messages.info(request, "Transfert annulé")
            return redirect('inventaire:selection_postes_transfert_tickets')
    
    # ===== AFFICHAGE DE LA PAGE DE CONFIRMATION (GET) =====
    # Vérifier rapidement s'il y a des conflits potentiels
    annee_actuelle = date.today().year
    tickets_existants = []
    
    for num in range(details_data['numero_premier'], 
                     min(details_data['numero_premier'] + 10, details_data['numero_dernier'] + 1)):
        est_unique, msg, hist = SerieTicket.verifier_unicite_annuelle(
            num, couleur, annee_actuelle
        )
        if not est_unique:
            tickets_existants.append({'numero': num, 'historique': hist})
    
    context = {
        'poste_origine': poste_origine,
        'poste_destination': poste_destination,
        'couleur': couleur,
        'numero_premier': details_data['numero_premier'],
        'numero_dernier': details_data['numero_dernier'],
        'nombre_tickets': details_data['nombre_tickets'],
        'montant': montant,
        'commentaire': details_data['commentaire'],
        'stock_origine_avant': stock_origine.valeur_monetaire,
        'stock_origine_apres': stock_origine_apres,
        'stock_destination_avant': stock_destination.valeur_monetaire,
        'stock_destination_apres': stock_destination_apres,
        'tickets_existants': tickets_existants,
        'annee_actuelle': annee_actuelle,
        'title': 'Confirmation du transfert'
    }
    
    return render(request, 'inventaire/confirmation_transfert_tickets.html', context)

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