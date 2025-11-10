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
    VERSION CORRIGÉE : Sans les champs historique_lie et serie_concernee qui n'existent pas
    
    Cette fonction garantit que les séries sont bien associées à l'historique
    lors du chargement de stock.
    
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
            serie = SerieTicket.objects.create(
                poste=poste,
                couleur=couleur,
                numero_premier=numero_premier,
                numero_dernier=numero_dernier,
                statut='stock',
                type_entree=type_stock,  # 'imprimerie_nationale' ou 'regularisation'
                commentaire=commentaire or f"Chargement {type_stock}",
                date_reception=now
            )
            
            # 2. Mettre à jour le stock global
            stock, created = GestionStock.objects.get_or_create(
                poste=poste,
                defaults={'valeur_monetaire': Decimal('0'), 'nombre_tickets': 0}
            )
            
            stock_avant = stock.valeur_monetaire
            montant = serie.valeur_monetaire  # Calculé automatiquement dans le modèle
            nombre_tickets = serie.nombre_tickets
            
            stock.valeur_monetaire += montant
            stock.nombre_tickets += nombre_tickets
            stock.save()
            
            # 3. Créer l'historique
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
                date_mouvement=now
            )
            
            # 4. ASSOCIER LA SÉRIE À L'HISTORIQUE (CRUCIAL)
            historique.series_tickets_associees.add(serie)
            
            # 5. Créer l'événement Event Sourcing SANS historique_lie
            event_type = 'REGULARISATION' if type_stock == 'regularisation' else 'CHARGEMENT'
            
            # Créer les métadonnées complètes
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
                'historique_id': historique.id,  # Stocker l'ID de l'historique dans metadata
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
                reference_id=str(historique.id),  # Lien vers l'historique via reference_id
                reference_type='HistoriqueStock',
                # historique_lie=historique,  # SUPPRIMÉ - ce champ n'existe pas
                metadata=metadata,
                commentaire=commentaire or f"Chargement série {couleur.libelle_affichage}"
            )
            
            # Note: serie_concernee n'existe pas non plus, on utilise metadata pour stocker l'info
            # stock_event.serie_concernee = serie  # SUPPRIMÉ - ce champ n'existe pas
            
            # 6. Envoyer notifications aux chefs de poste
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
            
            # 7. Journaliser l'action
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
            
            # 8. Log de débogage
            logger.info(
                f"Chargement stock réussi : {couleur.libelle_affichage} "
                f"#{numero_premier}-{numero_dernier} pour {poste.nom} "
                f"- Historique ID: {historique.id} avec "
                f"{historique.series_tickets_associees.count()} série(s) associée(s)"
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


# Modification de inventaire/views.py - fonction detail_historique_stock

def detail_historique_stock(request, historique_id):
    """
    Vue améliorée utilisant les champs structurés pour l'approvisionnement
    """
    from django.http import HttpResponseForbidden
    from django.shortcuts import render, get_object_or_404
    from inventaire.models import SerieTicket, StockEvent, HistoriqueStock
    from datetime import timedelta
    from decimal import Decimal
    from collections import defaultdict
    import logging
    
    logger = logging.getLogger('supper')
    
    # Récupérer l'historique avec toutes les relations
    historique = get_object_or_404(
        HistoriqueStock.objects.select_related(
            'poste',
            'effectue_par',
            'reference_recette',
            'poste_origine',
            'poste_destination',
            'couleur_principale'  # Nouveau champ
        ).prefetch_related(
            'series_tickets_associees',
            'series_tickets_associees__couleur'
        ),
        id=historique_id
    )
    
    poste = historique.poste
    if not request.user.peut_acceder_poste(poste):
        return HttpResponseForbidden("Vous n'avez pas accès à ce poste")
    
    # ===================================================================
    # CALCUL DU STOCK AVANT/APRÈS
    # ===================================================================
    
    def calculer_stock_via_historiques(poste, date_reference, exclure_historique_id=None):
        """Calcule le stock en sommant tous les mouvements jusqu'à la date"""
        from django.db.models import Sum
        
        historiques_query = HistoriqueStock.objects.filter(
            poste=poste,
            date_mouvement__lt=date_reference
        )
        
        if exclure_historique_id:
            historiques_query = historiques_query.exclude(id=exclure_historique_id)
        
        # Somme des crédits
        totaux_credit = historiques_query.filter(
            type_mouvement='CREDIT'
        ).aggregate(
            total_montant=Sum('montant'),
            total_tickets=Sum('nombre_tickets')
        )
        
        # Somme des débits
        totaux_debit = historiques_query.filter(
            type_mouvement='DEBIT'
        ).aggregate(
            total_montant=Sum('montant'),
            total_tickets=Sum('nombre_tickets')
        )
        
        montant_credit = totaux_credit['total_montant'] or Decimal('0')
        montant_debit = totaux_debit['total_montant'] or Decimal('0')
        tickets_credit = totaux_credit['total_tickets'] or 0
        tickets_debit = totaux_debit['total_tickets'] or 0
        
        stock_valeur = montant_credit - montant_debit
        stock_tickets = tickets_credit - tickets_debit
        
        # Éviter les valeurs négatives
        if stock_valeur < 0:
            stock_valeur = Decimal('0')
        if stock_tickets < 0:
            stock_tickets = 0
        
        return stock_valeur, stock_tickets
    
    # Calculer le stock avant cette opération
    stock_avant_valeur, stock_avant_qte = calculer_stock_via_historiques(
        poste=poste,
        date_reference=historique.date_mouvement,
        exclure_historique_id=None
    )
    
    # Calculer le stock après
    if historique.type_mouvement == 'CREDIT':
        stock_apres_valeur = stock_avant_valeur + historique.montant
        stock_apres_qte = stock_avant_qte + historique.nombre_tickets
    else:  # DEBIT
        stock_apres_valeur = stock_avant_valeur - historique.montant
        stock_apres_qte = stock_avant_qte - historique.nombre_tickets
        if stock_apres_valeur < 0:
            stock_apres_valeur = Decimal('0')
        if stock_apres_qte < 0:
            stock_apres_qte = 0
    
    # ===================================================================
    # RÉCUPÉRATION DES DÉTAILS D'APPROVISIONNEMENT STRUCTURÉS
    # ===================================================================
    
    series_operation = []
    details_approvisionnement = None
    details_vente = None
    info_transfert = None
    
    if historique.type_mouvement == 'CREDIT':
        if historique.type_stock in ['imprimerie_nationale', 'imprimerie', 'regularisation']:
            
            # Utiliser la méthode du modèle pour récupérer les détails structurés
            details_structurees = historique.get_details_approvisionnement_formattes()
            
            details_approvisionnement = {
                'type': details_structurees['type'],
                'montant': historique.montant,
                'nombre_tickets': historique.nombre_tickets,
                'series': details_structurees['series']
            }
            
            # Si on n'a pas de séries dans les détails structurés, utiliser les séries associées
            if not details_approvisionnement['series'] and historique.series_tickets_associees.exists():
                for serie in historique.series_tickets_associees.all():
                    details_approvisionnement['series'].append({
                        'couleur': serie.couleur,
                        'numero_premier': serie.numero_premier,
                        'numero_dernier': serie.numero_dernier,
                        'nombre_tickets': serie.nombre_tickets,
                        'valeur_monetaire': Decimal(str(serie.nombre_tickets)) * Decimal('500')
                    })
            
            # Ajouter à series_operation pour l'affichage
            for serie_detail in details_approvisionnement['series']:
                series_operation.append({
                    'type': 'approvisionnement',
                    'couleur': serie_detail.get('couleur'),
                    'numero_premier': serie_detail.get('numero_premier'),
                    'numero_dernier': serie_detail.get('numero_dernier'),
                    'nombre_tickets': serie_detail.get('nombre_tickets'),
                    'valeur': serie_detail.get('valeur') or serie_detail.get('valeur_monetaire'),
                    'action': 'ajoutee'
                })
        
        elif historique.type_stock == 'transfert_recu' or historique.poste_origine:
            # Transfert entrant
            series_recues = historique.series_tickets_associees.all()
            
            info_transfert = {
                'poste_origine': historique.poste_origine,
                'poste_destination': poste,
                'numero_bordereau': historique.numero_bordereau,
                'type': 'entrant',
                'series': []
            }
            
            for serie in series_recues:
                info_transfert['series'].append({
                    'couleur': serie.couleur,
                    'numero_premier': serie.numero_premier,
                    'numero_dernier': serie.numero_dernier,
                    'nombre_tickets': serie.nombre_tickets,
                    'valeur_monetaire': Decimal(str(serie.nombre_tickets)) * Decimal('500')
                })
    
    elif historique.type_mouvement == 'DEBIT':
        if historique.reference_recette:
            # Vente
            details_vente = historique.reference_recette.details_ventes_tickets.select_related(
                'couleur'
            ).all()
            
            for detail in details_vente:
                series_operation.append({
                    'type': 'vente',
                    'couleur': detail.couleur,
                    'numero_premier': detail.numero_premier,
                    'numero_dernier': detail.numero_dernier,
                    'nombre_tickets': detail.nombre_tickets,
                    'valeur': detail.montant,
                    'action': 'vendue'
                })
        
        elif historique.poste_destination:
            # Transfert sortant
            series_transferees = historique.series_tickets_associees.all()
            
            info_transfert = {
                'poste_origine': poste,
                'poste_destination': historique.poste_destination,
                'numero_bordereau': historique.numero_bordereau,
                'type': 'sortant',
                'series': []
            }
            
            for serie in series_transferees:
                info_transfert['series'].append({
                    'couleur': serie.couleur,
                    'numero_premier': serie.numero_premier,
                    'numero_dernier': serie.numero_dernier,
                    'nombre_tickets': serie.nombre_tickets,
                    'valeur_monetaire': Decimal(str(serie.nombre_tickets)) * Decimal('500')
                })
    
    # ===================================================================
    # VARIATION ET VÉRIFICATION
    # ===================================================================
    
    variation_valeur = stock_apres_valeur - stock_avant_valeur
    variation_qte = stock_apres_qte - stock_avant_qte
    
    # Vérification de cohérence
    if historique.type_mouvement == 'DEBIT':
        variation_attendue = -historique.montant
    else:
        variation_attendue = historique.montant
    
    if abs(variation_valeur - variation_attendue) > Decimal('0.01'):
        logger.warning(
            f"Incohérence variation - Historique {historique_id}: "
            f"Calculée={variation_valeur}, Attendue={variation_attendue}"
        )
    
    # Log de débogage avec les nouvelles données structurées
    logger.info(f"Détail historique {historique_id}:")
    logger.info(f"  Type: {historique.type_mouvement} - {historique.type_stock}")
    logger.info(f"  Montant: {historique.montant}")
    logger.info(f"  Stock avant: {stock_avant_valeur} ({stock_avant_qte} tickets)")
    logger.info(f"  Stock après: {stock_apres_valeur} ({stock_apres_qte} tickets)")
    
    if historique.numero_premier_ticket and historique.numero_dernier_ticket:
        logger.info(f"  Série principale: #{historique.numero_premier_ticket}-{historique.numero_dernier_ticket}")
    
    if historique.couleur_principale:
        logger.info(f"  Couleur principale: {historique.couleur_principale.libelle_affichage}")
    
    if details_approvisionnement:
        logger.info(f"  Séries approvisionnement: {len(details_approvisionnement.get('series', []))}")
    
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
        
        # Variations
        'variation_valeur': variation_valeur,
        'variation_qte': variation_qte,
        
        # Séries et opérations
        'series_operation': series_operation,
        
        # Détails spécifiques
        'details_vente': details_vente,
        'info_transfert': info_transfert,
        'details_approvisionnement': details_approvisionnement,
        
        # Affichage direct des champs structurés si disponibles
        'serie_principale': {
            'couleur': historique.couleur_principale,
            'numero_premier': historique.numero_premier_ticket,
            'numero_dernier': historique.numero_dernier_ticket,
            'nombre_tickets': (historique.numero_dernier_ticket - historique.numero_premier_ticket + 1) 
                            if historique.numero_premier_ticket and historique.numero_dernier_ticket else None
        } if historique.couleur_principale else None,
        
        'title': f'Détail opération - {poste.nom}',
        'is_admin': request.user.is_admin if hasattr(request.user, 'is_admin') else False,
    }
    
    return render(request, 'inventaire/detail_historique_stock.html', context)