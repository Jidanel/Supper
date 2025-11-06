#inventaire/views_stocks.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Avg, Q
from decimal import Decimal, InvalidOperation
from django.db import models
from datetime import date, timedelta
from .models import *
from .forms import *
from accounts.models import NotificationUtilisateur, Poste, UtilisateurSUPPER
from common.utils import log_user_action
import logging
logger = logging.getLogger('supper')

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

# @login_required
# @user_passes_test(is_admin)
# def charger_stock(request, poste_id):
#     """Vue pour charger/créditer le stock d'un poste avec choix du type"""
#     poste = get_object_or_404(Poste, id=poste_id)
    
#     # Récupérer le stock actuel
#     stock, created = GestionStock.objects.get_or_create(
#         poste=poste,
#         defaults={'valeur_monetaire': Decimal('0')}
#     )
    
#     if request.method == 'POST':
#         # Récupération des données du formulaire
#         type_stock = request.POST.get('type_stock')
#         montant = request.POST.get('montant', '0')
#         commentaire = request.POST.get('commentaire', '')
        
#         # Validation du type de stock
#         if not type_stock or type_stock not in ['regularisation', 'imprimerie_nationale']:
#             messages.error(request, "Veuillez sélectionner un type de stock valide")
#             return redirect('inventaire:charger_stock', poste_id=poste_id)
        
#         # Validation du montant
#         try:
#             montant = Decimal(montant)
#             if montant <= 0:
#                 messages.error(request, "Le montant doit être positif")
#                 return redirect('inventaire:charger_stock', poste_id=poste_id)
#         except (ValueError, InvalidOperation):
#             messages.error(request, "Montant invalide")
#             return redirect('inventaire:charger_stock', poste_id=poste_id)
        
#         # Stocker les données en session pour la page de confirmation
#         request.session['chargement_stock'] = {
#             'poste_id': poste_id,
#             'type_stock': type_stock,
#             'montant': str(montant),
#             'commentaire': commentaire
#         }
        
#         return redirect('inventaire:confirmation_chargement_stock')
    
#     # Historique récent avec type de stock
#     historique_recent = HistoriqueStock.objects.filter(
#         poste=poste,
#         type_mouvement='CREDIT'
#     ).select_related('effectue_par').order_by('-date_mouvement')[:5]
    
#     context = {
#         'poste': poste,
#         'stock': stock,
#         'historique_recent': historique_recent,
#         'title': f'Charger stock - {poste.nom}'
#     }
    
#     return render(request, 'inventaire/charger_stock.html', context)


# @login_required
# @user_passes_test(is_admin)
# def confirmation_chargement_stock(request):
#     """Page de confirmation du chargement de stock avec affichage du type"""
    
#     # Récupérer les données de session
#     chargement_data = request.session.get('chargement_stock')
    
#     if not chargement_data:
#         messages.error(request, "Aucune donnée de chargement en attente")
#         return redirect('inventaire:liste_postes_stocks')
    
#     poste = get_object_or_404(Poste, id=chargement_data['poste_id'])
    
#     if request.method == 'POST':
#         action = request.POST.get('action')
        
#         if action == 'confirmer':
#             try:
#                 with transaction.atomic():
#                     # Récupérer ou créer le stock
#                     stock, _ = GestionStock.objects.get_or_create(
#                         poste=poste,
#                         defaults={'valeur_monetaire': Decimal('0')}
#                     )
                    
#                     stock_avant = stock.valeur_monetaire
#                     montant = Decimal(chargement_data['montant'])
                    
#                     # Mettre à jour le stock
#                     stock.valeur_monetaire += montant
#                     stock.save()
                    
#                     # Créer l'historique avec le type de stock
#                     type_stock_label = "Régularisation" if chargement_data['type_stock'] == 'regularisation' else "Imprimerie Nationale"
                    
#                     HistoriqueStock.objects.create(
#                         poste=poste,
#                         type_mouvement='CREDIT',
#                         type_stock=chargement_data['type_stock'],
#                         montant=montant,
#                         nombre_tickets=int(montant / 500),
#                         stock_avant=stock_avant,
#                         stock_apres=stock.valeur_monetaire,
#                         effectue_par=request.user,
#                         commentaire=chargement_data['commentaire'] or f"Approvisionnement {type_stock_label} du {date.today().strftime('%d/%m/%Y')}"
#                     )
                    
#                     # Envoyer notification aux chefs de poste
#                     chefs = UtilisateurSUPPER.objects.filter(
#                         poste_affectation=poste,
#                         habilitation__in=['chef_peage', 'chef_pesage'],
#                         is_active=True
#                     )
                    
#                     for chef in chefs:
#                         NotificationUtilisateur.objects.create(
#                             destinataire=chef,
#                             expediteur=request.user,
#                             titre="Nouveau stock disponible",
#                             message=f"Stock {type_stock_label} crédité : {montant:,.0f} FCFA ({int(montant/500)} tickets) pour {poste.nom}",
#                             type_notification='info'
#                         )
                    
#                     # Journaliser l'action
#                     log_user_action(
#                         request.user,
#                         f"Chargement stock {type_stock_label}",
#                         f"Stock crédité: {montant:,.0f} FCFA pour {poste.nom}",
#                         request
#                     )
                    
#                     # Nettoyer la session
#                     del request.session['chargement_stock']
                    
#                     messages.success(
#                         request, 
#                         f"Stock {type_stock_label} crédité avec succès : {montant:,.0f} FCFA ({int(montant/500)} tickets)"
#                     )
#                     return redirect('inventaire:liste_postes_stocks')
                    
#             except Exception as e:
#                 logger.error(f"Erreur lors du chargement de stock: {str(e)}")
#                 messages.error(request, f"Erreur lors du chargement : {str(e)}")
#                 return redirect('inventaire:charger_stock', poste_id=poste.id)
        
#         elif action == 'annuler':
#             # Supprimer les données de session
#             del request.session['chargement_stock']
#             messages.info(request, "Chargement annulé")
#             return redirect('inventaire:charger_stock', poste_id=poste.id)
    
#     # Préparer les données pour l'affichage
#     try:
#         montant = Decimal(chargement_data['montant'])
#     except (ValueError, InvalidOperation):
#         del request.session['chargement_stock']
#         messages.error(request, "Données invalides")
#         return redirect('inventaire:charger_stock', poste_id=poste.id)
    
#     context = {
#         'poste': poste,
#         'type_stock': chargement_data['type_stock'],
#         'type_stock_label': 'Régularisation' if chargement_data['type_stock'] == 'regularisation' else 'Imprimerie Nationale',
#         'montant': montant,
#         'nombre_tickets': int(montant / 500),
#         'commentaire': chargement_data['commentaire'],
#         'title': 'Confirmation du chargement de stock'
#     }
    
#     return render(request, 'inventaire/confirmation_chargement_stock.html', context)


@login_required
@user_passes_test(is_admin)
def charger_stock_tickets(request, poste_id):
    """
    Vue MISE À JOUR pour charger le stock avec gestion des tickets par séries
    REMPLACE la fonction charger_stock existante
    """
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Récupérer le stock actuel (ancien système)
    stock, created = GestionStock.objects.get_or_create(
        poste=poste,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    # Récupérer les séries en stock (nouveau système)
    series_en_stock = SerieTicket.objects.filter(
        poste=poste,
        statut='stock'
    ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
    
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
            
            return redirect('inventaire:confirmation_chargement_stock_tickets')
    else:
        form = ChargementStockTicketsForm()
    
    # Historique récent avec type de stock
    historique_recent = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='CREDIT'
    ).select_related('effectue_par').order_by('-date_mouvement')[:5]
    
    # Grouper les séries par couleur pour affichage
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
    
    context = {
        'poste': poste,
        'stock': stock,
        'form': form,
        'series_par_couleur': series_par_couleur,
        'historique_recent': historique_recent,
        'title': f'Charger stock - {poste.nom}'
    }
    
    return render(request, 'inventaire/charger_stock_tickets.html', context)


@login_required
@user_passes_test(is_admin)
def confirmation_chargement_stock_tickets(request):
    """
    VERSION AVEC VÉRIFICATION D'UNICITÉ ANNUELLE (conservée pour le chargement)
    
    RÈGLE MÉTIER :
    - Un numéro de ticket ne peut être chargé qu'UNE SEULE FOIS par année
    - Exemple : Ticket #100 chargé en 2025 → IMPOSSIBLE de recharger #100 en 2025
    - Exemple : Ticket #100 chargé en 2025 → POSSIBLE de charger #100 en 2026
    """
    
    # Récupérer les données de session
    chargement_data = request.session.get('chargement_stock_tickets')
    
    if not chargement_data:
        messages.error(request, "Aucune donnée de chargement en attente")
        return redirect('inventaire:liste_postes_stocks')
    
    poste = get_object_or_404(Poste, id=chargement_data['poste_id'])
    couleur = get_object_or_404(CouleurTicket, id=chargement_data['couleur_id'])
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirmer':
            try:
                numero_premier = chargement_data['numero_premier']
                numero_dernier = chargement_data['numero_dernier']
                type_stock = chargement_data['type_stock']
                commentaire = chargement_data['commentaire']
                
                # ===== VÉRIFICATION D'UNICITÉ ANNUELLE (CONSERVÉE) =====
                # Cette vérification S'APPLIQUE UNIQUEMENT au chargement de stock
                from datetime import date
                annee_actuelle = date.today().year
                
                erreurs_unicite = []
                
                # Vérifier chaque ticket de la plage
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
                
                # Si des tickets existent déjà cette année, bloquer le chargement
                if erreurs_unicite:
                    messages.error(
                        request,
                        f"❌ CHARGEMENT IMPOSSIBLE : {len(erreurs_unicite)} ticket(s) "
                        f"de cette série existent déjà en {annee_actuelle}"
                    )
                    
                    # Afficher le détail des tickets problématiques
                    for erreur in erreurs_unicite[:5]:  # Limiter à 5 pour ne pas surcharger
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
                    
                    # Nettoyer la session et rediriger
                    del request.session['chargement_stock_tickets']
                    return redirect('inventaire:charger_stock_tickets', poste_id=poste.id)
                
                # ===== Si l'unicité est respectée, procéder au chargement =====
                success, message, serie, historique = executer_chargement_stock_avec_series(
                    poste=poste,
                    couleur=couleur,
                    numero_premier=numero_premier,
                    numero_dernier=numero_dernier,
                    type_stock=type_stock,
                    user=request.user,
                    commentaire=commentaire
                )
                
                if success:
                    # Nettoyer la session
                    del request.session['chargement_stock_tickets']
                    
                    montant = Decimal(chargement_data['montant'])
                    
                    messages.success(
                        request,
                        f"✅ Stock crédité avec succès : Série {couleur.libelle_affichage} "
                        f"#{numero_premier}-{numero_dernier} "
                        f"({chargement_data['nombre_tickets']} tickets = {montant:,.0f} FCFA)"
                    )
                    
                    return redirect('inventaire:liste_postes_stocks')
                else:
                    raise Exception(message)
                    
            except Exception as e:
                logger.error(f"Erreur chargement stock tickets: {str(e)}", exc_info=True)
                messages.error(request, f"❌ Erreur lors du chargement : {str(e)}")
                return redirect('inventaire:charger_stock_tickets', poste_id=poste.id)
        
        elif action == 'annuler':
            del request.session['chargement_stock_tickets']
            messages.info(request, "Chargement annulé")
            return redirect('inventaire:charger_stock_tickets', poste_id=poste.id)
    
    # Préparer les données pour l'affichage
    montant = Decimal(chargement_data['montant'])
    
    # ===== AFFICHER UN AVERTISSEMENT si des tickets similaires existent =====
    from datetime import date
    annee_actuelle = date.today().year
    
    # Vérifier rapidement s'il y a des conflits potentiels
    tickets_existants = []
    for num in range(chargement_data['numero_premier'], 
                     min(chargement_data['numero_premier'] + 10, chargement_data['numero_dernier'] + 1)):
        est_unique, msg, hist = SerieTicket.verifier_unicite_annuelle(
            num, couleur, annee_actuelle
        )
        if not est_unique:
            tickets_existants.append({'numero': num, 'historique': hist})
    
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
        'tickets_existants': tickets_existants,  # Pour afficher l'avertissement
        'annee_actuelle': annee_actuelle,
        'title': 'Confirmation du chargement de stock'
    }
    
    return render(request, 'inventaire/confirmation_chargement_stock_tickets.html', context)

def executer_chargement_stock_avec_series(poste, couleur, numero_premier, numero_dernier, 
                                         type_stock, user, commentaire):
    """
    VERSION MODIFIÉE avec Event Sourcing
    Exécute le chargement de stock ET crée la liaison avec l'historique + EVENT
    """
    from django.db import transaction
    
    with transaction.atomic():
        # 1. Créer la série de tickets (CODE EXISTANT)
        serie = SerieTicket.objects.create(
            poste=poste,
            couleur=couleur,
            numero_premier=numero_premier,
            numero_dernier=numero_dernier,
            statut='stock',
            type_entree=type_stock,
            commentaire=commentaire
        )
        
        # 2. Mettre à jour le stock global (CODE EXISTANT)
        stock, _ = GestionStock.objects.get_or_create(
            poste=poste,
            defaults={'valeur_monetaire': Decimal('0')}
        )
        
        stock_avant = stock.valeur_monetaire
        montant = serie.valeur_monetaire
        
        stock.valeur_monetaire += montant
        stock.save()
        
        # ===== NOUVEAU CODE EVENT SOURCING (AJOUTER) =====
        # Créer l'événement Event Sourcing
        event_type = 'REGULARISATION' if type_stock == 'regularisation' else 'CHARGEMENT'
        
        StockEvent.objects.create(
            poste=poste,
            event_type=event_type,
            event_datetime=timezone.now(),
            montant_variation=montant,
            nombre_tickets_variation=serie.nombre_tickets,
            stock_resultant=stock.valeur_monetaire,  # Utiliser la nouvelle valeur
            tickets_resultants=int(stock.valeur_monetaire / 500),
            effectue_par=user,
            reference_id=str(serie.id),
            reference_type='SerieTicket',
            metadata={
                'type_stock': type_stock,
                'serie': {
                    'couleur': couleur.libelle_affichage,
                    'numero_premier': numero_premier,
                    'numero_dernier': numero_dernier,
                    'nombre_tickets': serie.nombre_tickets,
                    'valeur': str(montant)
                }
            },
            commentaire=commentaire or f"Chargement série {couleur.libelle_affichage}"
        )
        # ===== FIN NOUVEAU CODE =====
        
        # 3. Créer l'historique (CODE EXISTANT - garder tel quel)
        type_stock_label = (
            "Régularisation" if type_stock == 'regularisation' 
            else "Imprimerie Nationale"
        )
        
        historique = HistoriqueStock.objects.create(
            poste=poste,
            type_mouvement='CREDIT',
            type_stock=type_stock,
            montant=montant,
            nombre_tickets=serie.nombre_tickets,
            stock_avant=stock_avant,
            stock_apres=stock.valeur_monetaire,
            effectue_par=user,
            commentaire=(
                f"{commentaire or ''} - Série {couleur.libelle_affichage} "
                f"#{numero_premier}-{numero_dernier}"
            )
        )
        
        # Reste du code existant (notifications, etc.) - GARDER TEL QUEL
        historique.associer_series_tickets([serie])
        
        # 4. Envoyer notifications aux chefs de poste
        chefs = UtilisateurSUPPER.objects.filter(
            poste_affectation=poste,
            habilitation__in=['chef_peage', 'chef_pesage'],
            is_active=True
        )
        
        for chef in chefs:
            NotificationUtilisateur.objects.create(
                destinataire=chef,
                expediteur=user,
                titre="Nouveau stock de tickets disponible",
                message=(
                    f"Stock {type_stock_label} crédité : "
                    f"Série {couleur.libelle_affichage} "
                    f"#{numero_premier}-{numero_dernier} "
                    f"({serie.nombre_tickets} tickets = {montant:,.0f} FCFA) "
                    f"pour {poste.nom}"
                ),
                type_notification='info'
            )
        
        # 5. Journaliser l'action
        log_user_action(
            user,
            f"Chargement stock {type_stock_label} avec tickets",
            (
                f"Stock crédité: Série {couleur.libelle_affichage} "
                f"#{numero_premier}-{numero_dernier} "
                f"= {montant:,.0f} FCFA pour {poste.nom}"
            ),
            None
        )
        
        logger.info(
            f"Chargement stock avec série : {couleur.libelle_affichage} "
            f"#{numero_premier}-{numero_dernier} pour {poste.nom}"
        )
        
        return True, "Chargement réussi", serie, historique


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
    
    # Calcul vente moyenne journalière
    vente_moyenne_journaliere = Decimal('0')
    if ventes_mois['total'] and ventes_mois['nombre'] > 0:
        vente_moyenne_journaliere = ventes_mois['total'] / ventes_mois['nombre']
    
    # Calcul date d'épuisement
    date_epuisement = None
    if vente_moyenne_journaliere > 0:
        jours_restants = int(stock.valeur_monetaire / vente_moyenne_journaliere)
        date_epuisement = date_fin + timedelta(days=jours_restants - 7)  # en retirant 7 jours de sécurité
    
    # Historique récent
    historique = HistoriqueStock.objects.filter(
        poste=poste
    ).order_by('-date_mouvement')[:10]
    
    context = {
        'poste': poste,
        'stock': stock,
        'ventes_mois': ventes_mois,
        'date_epuisement': date_epuisement,
        'historique': historique,
        'title': f'Mon stock - {poste.nom}',
    }
    
    return render(request, 'inventaire/mon_stock.html', context)


@login_required
def historique_stock(request, poste_id):
    """Vue complète de l'historique d'un poste"""
    poste = get_object_or_404(Poste, id=poste_id)
    
    # CORRECTION : Les admins peuvent voir tous les historiques
    if not request.user.is_admin:
        # Pour les non-admins, vérifier les permissions
        if not request.user.peut_acceder_poste(poste):
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
    
    # AJOUT : Liste de tous les postes pour le filtre admin
    postes_liste = None
    if request.user.is_admin:
        postes_liste = Poste.objects.filter(is_active=True).order_by('nom')
    
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
        'postes_liste': postes_liste,  # Pour le sélecteur de poste
        'is_admin': request.user.is_admin
    }
    
    return render(request, 'inventaire/historique_stock.html', context)

@login_required
def detail_historique_stock(request, historique_id):
    """
    Vue complète pour afficher le détail d'une opération d'historique
    
    Affiche :
    - Informations générales de l'opération
    - Impact sur le stock (avant/après)
    - État détaillé des séries de tickets AVANT l'opération
    - État détaillé des séries de tickets APRÈS l'opération
    - Séries transférées (si transfert)
    - Séries vendues (si vente)
    """
    
    # Récupérer l'historique
    historique = get_object_or_404(
        HistoriqueStock.objects.select_related(
            'poste',
            'effectue_par',
            'reference_recette',
            'poste_origine',
            'poste_destination'
        ),
        id=historique_id
    )
    
    # Vérifier les permissions
    poste = historique.poste
    if not request.user.peut_acceder_poste(poste):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Vous n'avez pas accès à ce poste")
    
    # ===================================================================
    # CALCUL DE L'ÉTAT DU STOCK AVANT ET APRÈS L'OPÉRATION
    # ===================================================================
    
    # 1. État du stock AVANT l'opération
    series_avant = []
    
    if historique.type_mouvement == 'DEBIT':
        # Pour un débit (vente/transfert sortant), on cherche les séries qui existaient avant
        # On cherche les séries en 'vendu' ou 'transfere' avec date <= date de l'historique
        # PLUS les séries actuellement en stock
        
        if historique.reference_recette:
            # CAS VENTE : Récupérer les séries vendues
            details_vente = historique.reference_recette.details_ventes_tickets.all()
            
            for detail in details_vente:
                # Trouver la série d'origine (qui était en stock avant la vente)
                serie_origine = SerieTicket.objects.filter(
                    poste=poste,
                    couleur=detail.couleur,
                    statut='vendu',
                    numero_premier__lte=detail.numero_premier,
                    numero_dernier__gte=detail.numero_dernier,
                    date_utilisation=historique.reference_recette.date
                ).first()
                
                if serie_origine:
                    series_avant.append({
                        'couleur': detail.couleur,
                        'numero_premier': detail.numero_premier,
                        'numero_dernier': detail.numero_dernier,
                        'nombre_tickets': detail.nombre_tickets,
                        'valeur': detail.montant,
                        'statut': 'stock',  # Était en stock avant
                        'action': 'vendue'  # A été vendue
                    })
        
        # Ajouter les séries qui sont restées en stock
        series_restantes = SerieTicket.objects.filter(
            poste=poste,
            statut='stock',
            date_reception__lte=historique.date_mouvement
        ).order_by('couleur__code_normalise', 'numero_premier')
        
        for serie in series_restantes:
            series_avant.append({
                'couleur': serie.couleur,
                'numero_premier': serie.numero_premier,
                'numero_dernier': serie.numero_dernier,
                'nombre_tickets': serie.nombre_tickets,
                'valeur': serie.valeur_monetaire,
                'statut': 'stock',
                'action': 'conservee'  # Est restée en stock
            })
    
    elif historique.type_mouvement == 'CREDIT':
        # Pour un crédit, l'état AVANT = stock actuel MOINS les séries ajoutées
        series_actuelles = SerieTicket.objects.filter(
            poste=poste,
            statut='stock',
            date_reception__lte=historique.date_mouvement
        ).exclude(
            date_reception=historique.date_mouvement
        ).order_by('couleur__code_normalise', 'numero_premier')
        
        for serie in series_actuelles:
            series_avant.append({
                'couleur': serie.couleur,
                'numero_premier': serie.numero_premier,
                'numero_dernier': serie.numero_dernier,
                'nombre_tickets': serie.nombre_tickets,
                'valeur': serie.valeur_monetaire,
                'statut': 'stock',
                'action': 'conservee'
            })
    
    # 2. État du stock APRÈS l'opération
    series_apres = []
    
    if historique.type_mouvement == 'DEBIT':
        # Après un débit, on a le stock actuel (sans les séries vendues/transférées)
        series_actuelles = SerieTicket.objects.filter(
            poste=poste,
            statut='stock'
        ).order_by('couleur__code_normalise', 'numero_premier')
        
        for serie in series_actuelles:
            series_apres.append({
                'couleur': serie.couleur,
                'numero_premier': serie.numero_premier,
                'numero_dernier': serie.numero_dernier,
                'nombre_tickets': serie.nombre_tickets,
                'valeur': serie.valeur_monetaire,
                'statut': 'stock',
                'action': 'conservee'
            })
    
    elif historique.type_mouvement == 'CREDIT':
        # Après un crédit, on a tout le stock actuel
        series_actuelles = SerieTicket.objects.filter(
            poste=poste,
            statut='stock',
            date_reception__lte=historique.date_mouvement
        ).order_by('couleur__code_normalise', 'numero_premier')
        
        for serie in series_actuelles:
            # Identifier les nouvelles séries ajoutées
            est_nouvelle = serie.date_reception == historique.date_mouvement.date()
            
            series_apres.append({
                'couleur': serie.couleur,
                'numero_premier': serie.numero_premier,
                'numero_dernier': serie.numero_dernier,
                'nombre_tickets': serie.nombre_tickets,
                'valeur': serie.valeur_monetaire,
                'statut': 'stock',
                'action': 'ajoutee' if est_nouvelle else 'conservee'
            })
    
    # ===================================================================
    # INFORMATIONS SPÉCIFIQUES SELON LE TYPE D'OPÉRATION
    # ===================================================================
    
    # Détails de vente (si applicable)
    details_vente = None
    if historique.type_mouvement == 'DEBIT' and historique.reference_recette:
        details_vente = historique.reference_recette.details_ventes_tickets.select_related(
            'couleur'
        ).all()
    
    # Détails de transfert (si applicable)
    info_transfert = None
    if historique.type_mouvement == 'CREDIT' and historique.type_stock == 'reapprovisionnement':
        if historique.poste_origine:
            # Trouver les séries transférées
            series_transferees = SerieTicket.objects.filter(
                poste=historique.poste_destination,  # Poste actuel (destination)
                type_entree='transfert_recu',
                date_reception=historique.date_mouvement.date()
            ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
            
            info_transfert = {
                'poste_origine': historique.poste_origine,
                'poste_destination': historique.poste_destination,
                'numero_bordereau': historique.numero_bordereau,
                'series': series_transferees
            }
    
    elif historique.type_mouvement == 'DEBIT' and historique.poste_destination:
        # C'est un transfert sortant
        series_transferees = SerieTicket.objects.filter(
            poste=historique.poste,  # Poste d'origine
            statut='transfere',
            poste_destination_transfert=historique.poste_destination,
            date_utilisation=historique.date_mouvement.date()
        ).select_related('couleur', 'poste_destination_transfert').order_by(
            'couleur__code_normalise', 'numero_premier'
        )
        
        info_transfert = {
            'poste_origine': historique.poste,
            'poste_destination': historique.poste_destination,
            'numero_bordereau': historique.numero_bordereau,
            'series': series_transferees
        }
    
    # ===================================================================
    # GROUPEMENT DES SÉRIES PAR COULEUR pour affichage
    # ===================================================================
    
    def grouper_series_par_couleur(series_list):
        """Groupe les séries par couleur pour un affichage plus clair"""
        from collections import defaultdict
        
        grouped = defaultdict(list)
        for serie in series_list:
            couleur_key = serie['couleur'].libelle_affichage
            grouped[couleur_key].append(serie)
        
        return dict(grouped)
    
    series_avant_groupees = grouper_series_par_couleur(series_avant)
    series_apres_groupees = grouper_series_par_couleur(series_apres)
    
    # ===================================================================
    # CONTEXTE POUR LE TEMPLATE
    # ===================================================================
    
    context = {
        'historique': historique,
        'poste': poste,
        'series_avant': series_avant,
        'series_apres': series_apres,
        'series_avant_groupees': series_avant_groupees,
        'series_apres_groupees': series_apres_groupees,
        'details_vente': details_vente,
        'info_transfert': info_transfert,
        'title': f'Détail opération - {poste.nom}',
        'is_admin': request.user.is_admin if hasattr(request.user, 'is_admin') else False,
    }
    
    return render(request, 'inventaire/detail_historique_stock.html', context)