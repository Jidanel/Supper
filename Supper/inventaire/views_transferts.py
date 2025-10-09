# inventaire/views_transferts.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from decimal import Decimal
from datetime import datetime
from django.db.models import Sum, Avg, Count, Q

from accounts.models import Poste, NotificationUtilisateur
from inventaire.models import GestionStock, HistoriqueStock
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
def selection_transfert_stock(request):
    """Sélection des postes pour le transfert"""
    
    postes = Poste.objects.filter(is_active=True).order_by('nom')
    
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
        
        return redirect('inventaire:formulaire_transfert_stock', 
                       origine_id=poste_origine_id,
                       destination_id=poste_destination_id)
    
    context = {
        'postes': postes_data,
        'title': 'Transférer du Stock Entre Postes'
    }
    
    return render(request, 'inventaire/selection_transfert_stock.html', context)


@login_required
@user_passes_test(is_admin)
def formulaire_transfert_stock(request, origine_id, destination_id):
    """Formulaire de saisie du montant à transférer"""
    
    poste_origine = get_object_or_404(Poste, id=origine_id)
    poste_destination = get_object_or_404(Poste, id=destination_id)
    
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
            
            return redirect('inventaire:confirmation_transfert_stock')
            
        except Exception as e:
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
@user_passes_test(is_admin)
def confirmation_transfert_stock(request):
    """Confirmation du transfert avant exécution - VERSION CORRIGÉE"""
    
    transfert_data = request.session.get('transfert_stock')
    
    if not transfert_data:
        messages.error(request, "Aucune donnée de transfert en attente")
        return redirect('inventaire:selection_transfert_stock')
    
    poste_origine = get_object_or_404(Poste, id=transfert_data['origine_id'])
    poste_destination = get_object_or_404(Poste, id=transfert_data['destination_id'])
    montant = Decimal(transfert_data['montant'])
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirmer':
            try:
                # LOG avant exécution
                logger.info(f"DEBUT TRANSFERT : {montant} FCFA de {poste_origine.code} vers {poste_destination.code}")
                
                with transaction.atomic():
                    # Générer le numéro de bordereau
                    numero_bordereau = generer_numero_bordereau()
                    logger.info(f"Bordereau généré : {numero_bordereau}")
                    
                    # Exécuter le transfert
                    hist_origine, hist_destination = executer_transfert_stock(
                        poste_origine,
                        poste_destination,
                        montant,
                        request.user,
                        transfert_data['commentaire'],
                        numero_bordereau
                    )
                    
                    logger.info(f"Transaction terminée - Hist Origine ID: {hist_origine.id}, Hist Dest ID: {hist_destination.id}")
                
                # Si on arrive ici, la transaction a réussi
                # Nettoyer la session
                if 'transfert_stock' in request.session:
                    del request.session['transfert_stock']
                
                messages.success(
                    request, 
                    f"✅ Transfert réussi ! {montant:,.0f} FCFA transférés de {poste_origine.nom} vers {poste_destination.nom}"
                )
                
                # Rediriger vers les bordereaux
                return redirect('inventaire:bordereaux_transfert', numero_bordereau=numero_bordereau)
                
            except ValueError as ve:
                logger.error(f"Erreur de validation transfert : {str(ve)}")
                messages.error(request, f"Erreur de validation : {str(ve)}")
                return redirect('inventaire:formulaire_transfert_stock', 
                              origine_id=poste_origine.id, 
                              destination_id=poste_destination.id)
            
            except Exception as e:
                logger.error(f"Erreur transfert stock : {str(e)}", exc_info=True)
                messages.error(request, f"❌ Erreur lors du transfert : {str(e)}")
                return redirect('inventaire:selection_transfert_stock')
        
        elif action == 'annuler':
            if 'transfert_stock' in request.session:
                del request.session['transfert_stock']
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

def executer_transfert_stock(poste_origine, poste_destination, montant, 
                            user, commentaire, numero_bordereau):
    """
    Exécute le transfert de stock entre deux postes
    VERSION CORRIGÉE avec get_or_create
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
    
    # Créer l'historique pour le poste ORIGINE (DEBIT - Cession)
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
        commentaire=f"CESSION vers {poste_destination.nom} - {commentaire}"
    )
    
    logger.info(f"Historique ORIGINE créé - ID: {hist_origine.id}, Bordereau: {hist_origine.numero_bordereau}")
    
    # Créer l'historique pour le poste DESTINATION (CREDIT - Réception)
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
        commentaire=f"RÉCEPTION depuis {poste_origine.nom} - {commentaire}"
    )
    
    logger.info(f"Historique DESTINATION créé - ID: {hist_destination.id}, Bordereau: {hist_destination.numero_bordereau}")
    
    # Notifier les chefs de poste concernés
    from accounts.models import UtilisateurSUPPER
    
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
        "Transfert de stock inter-postes",
        f"Transfert : {montant:,.0f} FCFA de {poste_origine.nom} vers {poste_destination.nom}. Bordereau N°{numero_bordereau}",
        None
    )
    
    logger.info(f"Transfert stock TERMINÉ avec succès - Bordereau {numero_bordereau}")
    
    return hist_origine, hist_destination

def generer_numero_bordereau():
    """Génère un numéro unique de bordereau de transfert"""
    from datetime import datetime
    
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


@login_required
def bordereaux_transfert(request, numero_bordereau):
    """
    Affiche les bordereaux de cession et d'approvisionnement
    VERSION CORRIGÉE avec meilleur débogage
    """
    
    logger.info(f"Recherche bordereau : {numero_bordereau}")
    
    # Récupérer les deux historiques liés à ce bordereau
    historiques = HistoriqueStock.objects.filter(
        numero_bordereau=numero_bordereau
    ).select_related('poste', 'poste_origine', 'poste_destination', 'effectue_par')
    
    logger.info(f"Nombre d'historiques trouvés : {historiques.count()}")
    
    if not historiques.exists():
        # LOG de débogage
        logger.error(f"❌ Bordereau {numero_bordereau} introuvable")
        
        # Chercher des bordereaux similaires pour aider au débogage
        tous_bordereaux = HistoriqueStock.objects.filter(
            type_stock='reapprovisionnement'
        ).values_list('numero_bordereau', flat=True).distinct()
        
        logger.info(f"Bordereaux existants : {list(tous_bordereaux)}")
        
        messages.error(request, f"Bordereau N°{numero_bordereau} introuvable. Vérifiez les logs.")
        return redirect('inventaire:liste_bordereaux')
    
    # Séparer cession et réception
    hist_cession = historiques.filter(type_mouvement='DEBIT').first()
    hist_reception = historiques.filter(type_mouvement='CREDIT').first()
    
    if not hist_cession or not hist_reception:
        logger.error(f"Données incomplètes - Cession: {hist_cession}, Réception: {hist_reception}")
        messages.error(request, "Données de transfert incomplètes")
        return redirect('inventaire:liste_bordereaux')
    
    # Contrôle d'accès
    if not request.user.is_admin:
        postes_autorises = [hist_cession.poste.id, hist_reception.poste.id]
        
        if not request.user.poste_affectation or \
           request.user.poste_affectation.id not in postes_autorises:
            messages.error(request, "Accès non autorisé à ce bordereau")
            return redirect('common:dashboard')
    
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
        'title': f'Bordereau de Transfert N°{numero_bordereau}'
    }
    
    return render(request, 'inventaire/bordereaux_transfert.html', context)

@login_required
def liste_bordereaux(request):
    """
    Liste de tous les bordereaux de transfert
    Admin : tous les bordereaux
    Chef : uniquement les bordereaux de son poste
    """
    
    # Récupérer tous les transferts (un par bordereau)
    bordereaux = HistoriqueStock.objects.filter(
        type_stock='reapprovisionnement',
        type_mouvement='DEBIT'  # On prend uniquement les cessions pour éviter les doublons
    ).select_related('poste', 'poste_origine', 'poste_destination', 'effectue_par')
    
    # Filtrer selon les permissions
    if not request.user.is_admin:
        if request.user.poste_affectation:
            # Chef de poste : voir les transferts qui concernent son poste
            bordereaux = bordereaux.filter(
                Q(poste_origine=request.user.poste_affectation) |
                Q(poste_destination=request.user.poste_affectation)
            )
        else:
            bordereaux = HistoriqueStock.objects.none()
    
    # Filtres
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
    from django.core.paginator import Paginator
    paginator = Paginator(bordereaux, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistiques
    stats = bordereaux.aggregate(
        total_transferts=Count('id'),
        montant_total=Sum('montant')
    )
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'postes': Poste.objects.filter(is_active=True).order_by('nom'),
        'filters': {
            'poste': poste_filter,
            'date_debut': date_debut,
            'date_fin': date_fin
        },
        'title': 'Liste des Bordereaux de Transfert'
    }
    
    return render(request, 'inventaire/liste_bordereaux.html', context)