from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Avg, Q
from decimal import Decimal
from django.db import models
from datetime import date, timedelta
from inventaire.models import GestionStock, HistoriqueStock, RecetteJournaliere
from accounts.models import NotificationUtilisateur, Poste, UtilisateurSUPPER
from common.utils import log_user_action

def is_admin(user):
    """Fonction de test pour vérifier si l'utilisateur est admin"""
    return user.is_authenticated and (
        user.is_superuser or 
        user.is_staff or
        (hasattr(user, 'is_admin') and user.is_admin) or
        (hasattr(user, 'habilitation') and user.habilitation in [
            'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'
        ])
    )

@login_required
@user_passes_test(is_admin)
def liste_postes_stocks(request):
    """Vue pour afficher tous les stocks des postes avec calcul de date d'épuisement"""
    
    # Récupérer tous les postes actifs
    postes = Poste.objects.filter(is_active=True)
    
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
            # Date d'épuisement = aujourd'hui + jours restants - 1 semaine de sécurité
            date_epuisement = date_fin + timedelta(days=jours_restants - 7)
            
            # Déterminer le niveau d'alerte
            if jours_restants <= 7:
                alerte_stock = 'danger'  # Stock critique
            elif jours_restants <= 14:
                alerte_stock = 'warning'  # Stock faible
            elif jours_restants <= 30:
                alerte_stock = 'info'  # Stock à surveiller
        
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
    
    # Pagination
    paginator = Paginator(stocks_data, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistiques globales
    total_stock = sum(s['valeur_monetaire'] for s in stocks_data)
    total_tickets = sum(s['nombre_tickets'] for s in stocks_data)
    stocks_critiques = len([s for s in stocks_data if s['alerte'] == 'danger'])
    stocks_faibles = len([s for s in stocks_data if s['alerte'] == 'warning'])
    
    context = {
        'page_obj': page_obj,
        'total_stock': total_stock,
        'total_tickets': total_tickets,
        'stocks_critiques': stocks_critiques,
        'stocks_faibles': stocks_faibles,
        'title': 'Gestion des Stocks - Vue d\'ensemble'
    }
    
    return render(request, 'inventaire/liste_stocks.html', context)

@login_required
@user_passes_test(is_admin)
def charger_stock_selection(request):
    """Vue pour sélectionner un poste avant de charger son stock"""
    
    if request.method == 'POST':
        poste_id = request.POST.get('poste_id')
        if poste_id:
            return redirect('inventaire:charger_stock', poste_id=poste_id)
        else:
            messages.error(request, "Veuillez sélectionner un poste")
    
    # Récupérer les postes avec leurs stocks actuels
    postes = Poste.objects.filter(is_active=True).order_by('nom')
    postes_data = []
    
    for poste in postes:
        stock = GestionStock.objects.filter(poste=poste).first()
        postes_data.append({
            'poste': poste,
            'stock_actuel': stock.valeur_monetaire if stock else 0,
            'tickets_actuels': stock.nombre_tickets if stock else 0
        })
    
    return render(request, 'inventaire/charger_stock_selection.html', {
        'postes': postes_data,
        'title': 'Charger un stock'
    })

@login_required
@user_passes_test(is_admin)
def charger_stock(request, poste_id):
    """Vue pour charger/créditer le stock d'un poste"""
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Récupérer le stock actuel
    stock, created = GestionStock.objects.get_or_create(
        poste=poste,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    if request.method == 'POST':
        montant = Decimal(request.POST.get('montant', '0'))
        commentaire = request.POST.get('commentaire', '')
        
        if montant <= 0:
            messages.error(request, "Le montant doit être positif")
            return redirect('inventaire:charger_stock', poste_id=poste_id)
        
        with transaction.atomic():
            stock_avant = stock.valeur_monetaire
            
            # Mettre à jour le stock
            stock.valeur_monetaire += montant
            stock.save()
            
            # Créer l'historique
            HistoriqueStock.objects.create(
                poste=poste,
                type_mouvement='CREDIT',
                montant=montant,
                nombre_tickets=int(montant / 500),
                stock_avant=stock_avant,
                stock_apres=stock.valeur_monetaire,
                effectue_par=request.user,
                commentaire=commentaire or f"Approvisionnement du {date.today().strftime('%d/%m/%Y')}"
            )
            
            # Envoyer notification au chef de poste
            chefs = UtilisateurSUPPER.objects.filter(
                poste_affectation=poste,
                habilitation__in=['chef_peage', 'chef_pesage']
            )
            
            for chef in chefs:
                NotificationUtilisateur.objects.create(
                    destinataire=chef,
                    expediteur=request.user,
                    titre="Nouveau stock disponible",
                    message=f"Un stock de {montant:,.0f} FCFA ({int(montant/500)} tickets) a été crédité pour votre poste",
                    type_notification='info'
                )
            
            # Journaliser
            log_user_action(
                request.user,
                "Chargement stock",
                f"Stock crédité: {montant:,.0f} FCFA pour {poste.nom}",
                request
            )
            
            messages.success(request, f"Stock crédité avec succès : {montant:,.0f} FCFA ({int(montant/500)} tickets)")
            return redirect('inventaire:liste_postes_stocks')
    
    # Historique récent
    historique_recent = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='CREDIT'
    ).order_by('-date_mouvement')[:5]
    
    context = {
        'poste': poste,
        'stock': stock,
        'historique_recent': historique_recent,
        'title': f'Charger stock - {poste.nom}'
    }
    
    return render(request, 'inventaire/charger_stock.html', context)

@login_required
def mon_stock(request):
    """Vue pour qu'un chef de poste consulte son stock"""
    
    if not request.user.poste_affectation:
        messages.error(request, "Vous n'êtes affecté à aucun poste")
        return redirect('common:dashboard')
    
    poste = request.user.poste_affectation
    stock, created = GestionStock.objects.get_or_create(
        poste=poste,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    # Calculer les statistiques
    date_fin = date.today()
    date_debut = date_fin - timedelta(days=30)
    
    # Ventes du mois
    ventes_mois = RecetteJournaliere.objects.filter(
        poste=poste,
        date__range=[date_debut, date_fin]
    ).aggregate(
        total=Sum('montant_declare'),
        nombre=models.Count('id')
    )
    
    # Historique récent
    historique = HistoriqueStock.objects.filter(
        poste=poste
    ).order_by('-date_mouvement')[:10]
    
    context = {
        'poste': poste,
        'stock': stock,
        'ventes_mois': ventes_mois,
        'historique': historique,
        'title': f'Mon stock - {poste.nom}'
    }
    
    return render(request, 'inventaire/mon_stock.html', context)

@login_required
def historique_stock(request, poste_id):
    """Vue complète de l'historique d'un poste"""
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Vérifier les permissions
    if not (is_admin(request.user) or request.user.peut_acceder_poste(poste)):
        messages.error(request, "Accès non autorisé")
        return redirect('inventaire:inventaire_list')
    
    # Filtres
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
        'title': f'Historique stock - {poste.nom}'
    }
    
    return render(request, 'inventaire/historique_stock.html', context)