#inventaire/views_stocks.py
from django.http import HttpResponseForbidden
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
from accounts.models import *
from collections import defaultdict
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

# @login_required
# @user_passes_test(is_admin)
# def charger_stock_selection(request):
#     """Vue pour sélectionner un poste avant de charger son stock"""
    
#     if request.method == 'POST':
#         poste_id = request.POST.get('poste_id')
#         if poste_id:
#             return redirect('inventaire:charger_stock', poste_id=poste_id)
#         else:
#             messages.error(request, "Veuillez sélectionner un poste")
    
#     # Récupérer les postes avec leurs stocks actuels
#     postes = Poste.objects.filter(is_active=True).order_by('nom')
#     postes_data = []
    
#     for poste in postes:
#         stock = GestionStock.objects.filter(poste=poste).first()
#         postes_data.append({
#             'poste': poste,
#             'stock_actuel': stock.valeur_monetaire if stock else 0,
#             'tickets_actuels': stock.nombre_tickets if stock else 0
#         })
    
#     return render(request, 'inventaire/charger_stock_selection.html', {
#         'postes': postes_data,
#         'title': 'Charger un stock'
#     })

# Vue charger_stock_selection corrigée pour inventaire/views.py

def charger_stock_selection(request, poste_id):
    """
    Vue pour charger le stock utilisant la fonction corrigée
    sans les champs inexistants historique_lie et serie_concernee
    """
    from django.shortcuts import render, redirect, get_object_or_404
    from django.contrib import messages
    from inventaire.models import Poste, GestionStock, SerieTicket
    from inventaire.forms import ChargementStockForm
    import logging
    
    logger = logging.getLogger('supper')
    
    poste = get_object_or_404(Poste, id=poste_id, is_active=True)
    
    # Vérification des permissions
    if not request.user.peut_acceder_poste(poste):
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        return redirect('inventaire:liste_postes_stocks')
    
    if request.method == 'POST':
        form = ChargementStockForm(request.POST)
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
                    # Vérifier le chevauchement
                    if not (numero_dernier < serie.numero_premier or 
                            numero_premier > serie.numero_dernier):
                        messages.error(
                            request,
                            f"Conflit avec la série existante {serie.couleur.libelle_affichage} "
                            f"#{serie.numero_premier}-{serie.numero_dernier}"
                        )
                        return render(request, 'inventaire/charger_stock_selection.html', {
                            'form': form,
                            'poste': poste,
                            'title': f'Charger le stock - {poste.nom}'
                        })
                
                # Utiliser la fonction corrigée
                success, message, serie, historique = executer_chargement_stock_avec_series(
                    poste=poste,
                    couleur=couleur,
                    numero_premier=numero_premier,
                    numero_dernier=numero_dernier,
                    type_stock=type_stock,
                    user=request.user,
                    commentaire=observations
                )
                
                if success:
                    messages.success(request, message)
                    logger.info(f"Chargement réussi par {request.user.username}: {message}")
                    return redirect('inventaire:detail_stock', poste_id=poste.id)
                else:
                    messages.error(request, message)
                    logger.error(f"Échec chargement par {request.user.username}: {message}")
                    
            except Exception as e:
                logger.error(f"Erreur inattendue dans charger_stock_selection: {str(e)}", exc_info=True)
                messages.error(request, f"Erreur inattendue: {str(e)}")
    else:
        form = ChargementStockForm()
    
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
    
    context = {
        'form': form,
        'poste': poste,
        'series_actuelles': series_actuelles,
        'stock_total': stock_total,
        'title': f'Charger le stock - {poste.nom}'
    }
    
    return render(request, 'inventaire/charger_stock_selection.html', context)
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
                                          type_stock, user, commentaire=None):
    """
    VERSION CORRIGÉE : Avec remplissage des champs structurés de HistoriqueStock
    
    Cette fonction garantit que:
    - Les séries sont bien associées à l'historique
    - Les champs structurés (numero_premier_ticket, numero_dernier_ticket, couleur_principale) sont remplis
    - Le JSONField details_approvisionnement est rempli
    
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
    from django.db import transaction
    from decimal import Decimal
    from inventaire.models import SerieTicket, GestionStock, HistoriqueStock, StockEvent
    from django.utils import timezone
    from accounts.models import NotificationUtilisateur, UtilisateurSUPPER
    from common.utils import log_user_action
    import logging
    
    logger = logging.getLogger('supper')
    
    try:
        with transaction.atomic():
            # 1. Créer la série de tickets
            now = timezone.now()
            nombre_tickets = numero_dernier - numero_premier + 1
            montant = Decimal(nombre_tickets) * Decimal('500')
            
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
            
            # 3. Préparer les labels et les détails structurés
            type_stock_label = (
                "Régularisation" if type_stock == 'regularisation' 
                else "Imprimerie Nationale"
            )
            
            # Normaliser le type_stock pour l'historique
            type_stock_historique = 'imprimerie_nationale' if type_stock in ['imprimerie', 'imprimerie_nationale'] else type_stock
            
            commentaire_historique = (
                f"{type_stock_label} - Série {couleur.libelle_affichage} "
                f"#{numero_premier}-{numero_dernier}"
            )
            if commentaire:
                commentaire_historique += f"\n{commentaire}"
            
            # ===== NOUVEAU: Préparer le JSONField details_approvisionnement =====
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
            
            # 4. Créer l'historique AVEC CHAMPS STRUCTURÉS (CORRECTION MAJEURE)
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
                # ===== NOUVEAUX CHAMPS STRUCTURÉS =====
                numero_premier_ticket=numero_premier,
                numero_dernier_ticket=numero_dernier,
                couleur_principale=couleur,
                details_approvisionnement=details_approvisionnement
                # =====================================
            )
            
            # 5. ASSOCIER LA SÉRIE À L'HISTORIQUE (CRUCIAL)
            historique.series_tickets_associees.add(serie)
            
            # 6. Créer l'événement Event Sourcing avec métadonnées complètes
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
            
            stock_event = StockEvent.objects.create(
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
            
            # 7. Envoyer notifications aux chefs de poste
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
            
            # 8. Journaliser l'action
            log_user_action(
                user,
                f"Chargement stock {type_stock_label}",
                (
                    f"Stock crédité: Série {couleur.libelle_affichage} "
                    f"#{numero_premier}-{numero_dernier} "
                    f"({nombre_tickets:,} tickets = {montant:,.0f} FCFA) "
                    f"pour {poste.nom}"
                ),
                None
            )
            
            # 9. Log de débogage avec confirmation des champs structurés
            logger.info(
                f"✅ Chargement stock réussi : {couleur.libelle_affichage} "
                f"#{numero_premier}-{numero_dernier} pour {poste.nom}"
            )
            logger.info(
                f"  Historique ID: {historique.id} | "
                f"Champs structurés: couleur_principale={historique.couleur_principale}, "
                f"tickets=#{historique.numero_premier_ticket}-{historique.numero_dernier_ticket} | "
                f"Séries associées: {historique.series_tickets_associees.count()}"
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
    
# Fonction pour vérifier et corriger les associations manquantes
def verifier_et_corriger_associations(poste_id=None):
    """
    Vérifie et corrige les associations manquantes entre historiques et séries
    """
    from inventaire.models import HistoriqueStock, SerieTicket
    from django.db.models import Q
    import re
    import logging
    
    logger = logging.getLogger('supper')
    
    # Filtrer par poste si spécifié
    query = Q(type_mouvement='CREDIT')
    if poste_id:
        query &= Q(poste_id=poste_id)
    
    historiques = HistoriqueStock.objects.filter(query).prefetch_related('series_tickets_associees')
    
    corrections = 0
    
    for historique in historiques:
        # Si pas de séries associées mais un commentaire avec infos
        if not historique.series_tickets_associees.exists() and historique.commentaire:
            # Essayer d'extraire les infos du commentaire
            # Pattern : "Série Bleu #25896547-25956546"
            pattern = r"Série\s+(\w+)\s+#(\d+)-(\d+)"
            match = re.search(pattern, historique.commentaire)
            
            if match:
                couleur_nom = match.group(1)
                num_premier = int(match.group(2))
                num_dernier = int(match.group(3))
                
                # Chercher la série correspondante
                serie = SerieTicket.objects.filter(
                    poste=historique.poste,
                    numero_premier=num_premier,
                    numero_dernier=num_dernier,
                    date_reception=historique.date_mouvement.date()
                ).first()
                
                if serie:
                    # Associer la série à l'historique
                    historique.series_tickets_associees.add(serie)
                    corrections += 1
                    logger.info(
                        f"Association corrigée : Historique {historique.id} "
                        f"-> Série {serie.id} ({couleur_nom} #{num_premier}-{num_dernier})"
                    )
                else:
                    logger.warning(
                        f"Série introuvable pour Historique {historique.id} : "
                        f"{couleur_nom} #{num_premier}-{num_dernier}"
                    )
    
    logger.info(f"Vérification terminée : {corrections} associations corrigées")
    return corrections

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



def detail_historique_stock(request, historique_id):
    """
    Vue pour afficher les détails complets d'une opération de stock.
    
    CORRECTIONS:
    - Transfert sortant (DEBIT) → action "transférée" (pas "vendue")
    - Transfert entrant (CREDIT) → action "créditée"  
    - Vente (DEBIT avec reference_recette) → action "vendue"
    - Approvisionnement (CREDIT) → action "ajoutée"
    """
    from django.http import HttpResponseForbidden
    from django.shortcuts import render, get_object_or_404
    from django.db.models import Sum
    from decimal import Decimal
    from collections import defaultdict
    import logging
    import re
    
    # Imports des modèles - adapter selon votre structure
    try:
        from inventaire.models import (
            SerieTicket, StockEvent, HistoriqueStock, CouleurTicket
        )
    except ImportError:
        from .models import SerieTicket, StockEvent, HistoriqueStock, CouleurTicket
    
    logger = logging.getLogger('supper')
    
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
    
    # Vérification des permissions
    if hasattr(request.user, 'peut_acceder_poste'):
        if not request.user.peut_acceder_poste(poste):
            return HttpResponseForbidden("Vous n'avez pas accès à ce poste")
    
    logger.info(f"=" * 60)
    logger.info(f"DETAIL HISTORIQUE STOCK ID: {historique_id}")
    logger.info(f"  Poste: {poste.nom}")
    logger.info(f"  Type mouvement: {historique.type_mouvement}")
    logger.info(f"  Type stock: {historique.type_stock}")
    logger.info(f"  Poste origine: {historique.poste_origine}")
    logger.info(f"  Poste destination: {historique.poste_destination}")
    logger.info(f"  Numéro bordereau: {historique.numero_bordereau}")
    
    # ===================================================================
    # FONCTION: CALCUL DU STOCK VIA HISTORIQUES
    # ===================================================================
    
    def calculer_stock_via_historiques(poste_cible, date_reference):
        """Calcule le stock en sommant tous les mouvements jusqu'à la date"""
        
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
    # FONCTION: EXTRACTION DES SÉRIES DEPUIS UN HISTORIQUE
    # ===================================================================
    
    def extraire_series_depuis_historique(hist):
        """
        Extrait les séries de tickets depuis un historique.
        Utilise plusieurs sources dans l'ordre de priorité.
        """
        series = []
        
        logger.info(f"  Extraction séries pour historique {hist.id}:")
        logger.info(f"    - couleur_principale: {hist.couleur_principale}")
        logger.info(f"    - numero_premier_ticket: {hist.numero_premier_ticket}")
        logger.info(f"    - numero_dernier_ticket: {hist.numero_dernier_ticket}")
        logger.info(f"    - details_approvisionnement: {bool(hist.details_approvisionnement)}")
        logger.info(f"    - series_tickets_associees count: {hist.series_tickets_associees.count()}")
        
        # SOURCE 1: Champs structurés directs
        if hist.couleur_principale and hist.numero_premier_ticket and hist.numero_dernier_ticket:
            nb_tickets = hist.numero_dernier_ticket - hist.numero_premier_ticket + 1
            series.append({
                'couleur': hist.couleur_principale,
                'couleur_nom': hist.couleur_principale.libelle_affichage,
                'numero_premier': hist.numero_premier_ticket,
                'numero_dernier': hist.numero_dernier_ticket,
                'nombre_tickets': nb_tickets,
                'valeur': Decimal(nb_tickets) * Decimal('500')
            })
            logger.info(f"    ✓ Source 1 (champs structurés): {hist.couleur_principale.libelle_affichage} "
                       f"#{hist.numero_premier_ticket}-{hist.numero_dernier_ticket}")
            return series
        
        # SOURCE 2: JSONField details_approvisionnement
        if hist.details_approvisionnement and isinstance(hist.details_approvisionnement, dict):
            series_data = hist.details_approvisionnement.get('series', [])
            
            for serie_data in series_data:
                couleur = None
                couleur_nom = serie_data.get('couleur_nom', 'Inconnu')
                
                # Récupérer l'objet couleur
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
                logger.info(f"    ✓ Source 2 (JSON): {len(series)} série(s) trouvée(s)")
                return series
        
        # SOURCE 3: Relation ManyToMany series_tickets_associees
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
            logger.info(f"    ✓ Source 3 (ManyToMany): {len(series)} série(s) trouvée(s)")
            return series
        
        # SOURCE 4: Parser le commentaire
        if hist.commentaire and '#' in hist.commentaire:
            patterns = [
                r"(?:Série\s+)?(\w+(?:\s+\w+)?)\s*#(\d+)[–-](\d+)",
                r"(\w+)\s*#(\d+)[–-](\d+)",
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
                        logger.info(f"    ✓ Source 4 (commentaire): {len(series)} série(s) parsée(s)")
                        return series
        
        logger.warning(f"    ✗ Aucune série trouvée pour historique {hist.id}")
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
    else:  # DEBIT
        stock_apres_valeur = max(Decimal('0'), stock_avant_valeur - historique.montant)
        stock_apres_qte = max(0, stock_avant_qte - historique.nombre_tickets)
    
    # ===================================================================
    # INITIALISATION DES VARIABLES DE CONTEXTE
    # ===================================================================
    
    details_approvisionnement = None
    details_vente = None
    info_transfert = None
    
    # Dictionnaires pour les séries avant/après groupées par couleur
    series_avant_groupees = defaultdict(list)
    series_apres_groupees = defaultdict(list)
    
    # ===================================================================
    # DÉTERMINATION DU TYPE D'OPÉRATION ET TRAITEMENT
    # ===================================================================
    
    # -----------------------------------------------------------------
    # CAS 1: TRANSFERT SORTANT (DEBIT avec poste_destination)
    # -----------------------------------------------------------------
    if historique.type_mouvement == 'DEBIT' and historique.poste_destination:
        logger.info("  → Type: TRANSFERT SORTANT")
        
        info_transfert = {
            'poste_origine': poste,
            'poste_destination': historique.poste_destination,
            'numero_bordereau': historique.numero_bordereau,
            'type': 'sortant',
            'series': []
        }
        
        # Extraire les séries
        series_extraites = extraire_series_depuis_historique(historique)
        
        # Si pas de séries trouvées, chercher les SerieTicket marquées transférées
        if not series_extraites:
            logger.info("  → Recherche SerieTicket transférées...")
            series_transferees = SerieTicket.objects.filter(
                poste=poste,
                statut='transfere',
                poste_destination_transfert=historique.poste_destination
            ).select_related('couleur')
            
            if historique.date_mouvement:
                series_transferees = series_transferees.filter(
                    date_utilisation=historique.date_mouvement.date()
                )
            
            for serie in series_transferees:
                series_extraites.append({
                    'couleur': serie.couleur,
                    'couleur_nom': serie.couleur.libelle_affichage if serie.couleur else 'Inconnu',
                    'numero_premier': serie.numero_premier,
                    'numero_dernier': serie.numero_dernier,
                    'nombre_tickets': serie.nombre_tickets,
                    'valeur': serie.valeur_monetaire
                })
        
        # Remplir info_transfert ET series_avant_groupees
        for serie in series_extraites:
            couleur_nom = serie.get('couleur_nom', 'Inconnu')
            
            # Pour info_transfert
            info_transfert['series'].append({
                'couleur': serie.get('couleur'),
                'numero_premier': serie.get('numero_premier'),
                'numero_dernier': serie.get('numero_dernier'),
                'nombre_tickets': serie.get('nombre_tickets'),
                'valeur_monetaire': serie.get('valeur')
            })
            
            # Pour series_avant_groupees - ACTION "transférée" (PAS "vendue")
            series_avant_groupees[couleur_nom].append({
                'numero_premier': serie.get('numero_premier'),
                'numero_dernier': serie.get('numero_dernier'),
                'nombre_tickets': serie.get('nombre_tickets'),
                'valeur': serie.get('valeur'),
                'action': 'transférée'  # ← CORRECTION ICI
            })
        
        logger.info(f"  → Séries transférées: {len(info_transfert['series'])}")
    
    # -----------------------------------------------------------------
    # CAS 2: TRANSFERT ENTRANT (CREDIT avec poste_origine)
    # -----------------------------------------------------------------
    elif historique.type_mouvement == 'CREDIT' and historique.poste_origine:
        logger.info("  → Type: TRANSFERT ENTRANT")
        
        info_transfert = {
            'poste_origine': historique.poste_origine,
            'poste_destination': poste,
            'numero_bordereau': historique.numero_bordereau,
            'type': 'entrant',
            'series': []
        }
        
        # Extraire les séries de cet historique
        series_extraites = extraire_series_depuis_historique(historique)
        
        # Si pas de séries trouvées, chercher dans l'historique DEBIT correspondant
        if not series_extraites and historique.numero_bordereau:
            logger.info(f"  → Recherche historique DEBIT avec bordereau: {historique.numero_bordereau}")
            hist_debit = HistoriqueStock.objects.filter(
                numero_bordereau=historique.numero_bordereau,
                type_mouvement='DEBIT'
            ).select_related('couleur_principale').prefetch_related(
                'series_tickets_associees',
                'series_tickets_associees__couleur'
            ).first()
            
            if hist_debit:
                logger.info(f"  → Historique DEBIT trouvé: ID {hist_debit.id}")
                series_extraites = extraire_series_depuis_historique(hist_debit)
        
        # Si toujours pas de séries, chercher les SerieTicket reçues
        if not series_extraites:
            logger.info("  → Recherche SerieTicket reçues par transfert...")
            series_recues = SerieTicket.objects.filter(
                poste=poste,
                origine='transfert',
                serie_origine_transfert__poste=historique.poste_origine
            ).select_related('couleur')
            
            if historique.date_mouvement:
                series_recues = series_recues.filter(
                    date_reception=historique.date_mouvement.date()
                )
            
            for serie in series_recues:
                series_extraites.append({
                    'couleur': serie.couleur,
                    'couleur_nom': serie.couleur.libelle_affichage if serie.couleur else 'Inconnu',
                    'numero_premier': serie.numero_premier,
                    'numero_dernier': serie.numero_dernier,
                    'nombre_tickets': serie.nombre_tickets,
                    'valeur': serie.valeur_monetaire
                })
        
        # Remplir info_transfert ET series_apres_groupees
        for serie in series_extraites:
            couleur_nom = serie.get('couleur_nom', 'Inconnu')
            
            # Pour info_transfert
            info_transfert['series'].append({
                'couleur': serie.get('couleur'),
                'numero_premier': serie.get('numero_premier'),
                'numero_dernier': serie.get('numero_dernier'),
                'nombre_tickets': serie.get('nombre_tickets'),
                'valeur_monetaire': serie.get('valeur')
            })
            
            # Pour series_apres_groupees - ACTION "créditée"
            series_apres_groupees[couleur_nom].append({
                'numero_premier': serie.get('numero_premier'),
                'numero_dernier': serie.get('numero_dernier'),
                'nombre_tickets': serie.get('nombre_tickets'),
                'valeur': serie.get('valeur'),
                'action': 'créditée'  # ← ACTION CRÉDIT
            })
        
        logger.info(f"  → Séries reçues: {len(info_transfert['series'])}")
    
    # -----------------------------------------------------------------
    # CAS 3: VENTE (DEBIT avec reference_recette)
    # -----------------------------------------------------------------
    elif historique.type_mouvement == 'DEBIT' and historique.reference_recette:
        logger.info("  → Type: VENTE")
        
        details_vente = historique.reference_recette.details_ventes_tickets.select_related(
            'couleur'
        ).all()
        
        for detail in details_vente:
            couleur_nom = detail.couleur.libelle_affichage if detail.couleur else 'Inconnu'
            
            # Pour series_avant_groupees - ACTION "vendue" (uniquement pour les vraies ventes)
            series_avant_groupees[couleur_nom].append({
                'numero_premier': detail.numero_premier,
                'numero_dernier': detail.numero_dernier,
                'nombre_tickets': detail.nombre_tickets,
                'valeur': detail.montant,
                'action': 'vendue'  # ← ACTION VENTE uniquement ici
            })
        
        logger.info(f"  → Détails vente: {len(list(details_vente))} ligne(s)")
    
    # -----------------------------------------------------------------
    # CAS 4: APPROVISIONNEMENT (CREDIT - Imprimerie ou Régularisation)
    # -----------------------------------------------------------------
    elif historique.type_mouvement == 'CREDIT':
        logger.info("  → Type: APPROVISIONNEMENT")
        
        if historique.type_stock == 'regularisation':
            type_label = "Régularisation"
        else:
            type_label = "Imprimerie Nationale"
        
        details_approvisionnement = {
            'type': type_label,
            'montant': historique.montant,
            'nombre_tickets': historique.nombre_tickets,
            'series': []
        }
        
        series_extraites = extraire_series_depuis_historique(historique)
        
        for serie in series_extraites:
            couleur_nom = serie.get('couleur_nom', 'Inconnu')
            
            # Pour details_approvisionnement
            details_approvisionnement['series'].append(serie)
            
            # Pour series_apres_groupees - ACTION "ajoutée"
            series_apres_groupees[couleur_nom].append({
                'numero_premier': serie.get('numero_premier'),
                'numero_dernier': serie.get('numero_dernier'),
                'nombre_tickets': serie.get('nombre_tickets'),
                'valeur': serie.get('valeur'),
                'action': 'ajoutée'  # ← ACTION AJOUT
            })
        
        logger.info(f"  → Séries approvisionnées: {len(details_approvisionnement['series'])}")
    
    # -----------------------------------------------------------------
    # CAS 5: AUTRE DEBIT (sans poste_destination ni reference_recette)
    # -----------------------------------------------------------------
    elif historique.type_mouvement == 'DEBIT':
        logger.info("  → Type: AUTRE DÉBIT")
        
        series_extraites = extraire_series_depuis_historique(historique)
        
        for serie in series_extraites:
            couleur_nom = serie.get('couleur_nom', 'Inconnu')
            
            # Pour series_avant_groupees - ACTION "débitée"
            series_avant_groupees[couleur_nom].append({
                'numero_premier': serie.get('numero_premier'),
                'numero_dernier': serie.get('numero_dernier'),
                'nombre_tickets': serie.get('nombre_tickets'),
                'valeur': serie.get('valeur'),
                'action': 'débitée'  # ← ACTION DÉBIT générique
            })
    
    # ===================================================================
    # CONVERSION DES DEFAULTDICT EN DICT STANDARD
    # ===================================================================
    
    series_avant_groupees = dict(series_avant_groupees)
    series_apres_groupees = dict(series_apres_groupees)
    
    # ===================================================================
    # LOG FINAL
    # ===================================================================
    
    logger.info(f"=" * 60)
    logger.info(f"RÉSUMÉ FINAL:")
    logger.info(f"  Stock avant: {stock_avant_valeur} FCFA ({stock_avant_qte} tickets)")
    logger.info(f"  Stock après: {stock_apres_valeur} FCFA ({stock_apres_qte} tickets)")
    logger.info(f"  Series avant groupées: {len(series_avant_groupees)} couleur(s)")
    logger.info(f"  Series après groupées: {len(series_apres_groupees)} couleur(s)")
    if info_transfert:
        logger.info(f"  Info transfert ({info_transfert['type']}): {len(info_transfert['series'])} série(s)")
    logger.info(f"=" * 60)
    
    # ===================================================================
    # CONTEXTE POUR LE TEMPLATE
    # ===================================================================
    
    context = {
        'historique': historique,
        'poste': poste,
        
        # Stocks calculés
        'stock_avant_valeur': stock_avant_valeur,
        'stock_avant_qte': stock_avant_qte,
        'stock_apres_valeur': stock_apres_valeur,
        'stock_apres_qte': stock_apres_qte,
        
        # Séries groupées pour la comparaison avant/après
        'series_avant_groupees': series_avant_groupees,
        'series_apres_groupees': series_apres_groupees,
        
        # Détails spécifiques par type d'opération
        'details_vente': details_vente,
        'info_transfert': info_transfert,
        'details_approvisionnement': details_approvisionnement,
        
        'title': f'Détail opération - {poste.nom}',
    }
    
    return render(request, 'inventaire/detail_historique_stock.html', context)