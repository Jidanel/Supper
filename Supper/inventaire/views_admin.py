# ===================================================================
# inventaire/views.py - Vues Inventaire avec Permissions Granulaires
# VERSION MODIFIÉE - Utilisation des 73 permissions SUPPER
# ===================================================================
"""
Vues pour le module inventaire utilisant le système de permissions granulaires.

PERMISSIONS UTILISÉES:
- peut_saisir_inventaire_admin: Saisie inventaire administratif
- peut_voir_liste_inventaires_admin: Liste inventaires administratifs  
- peut_voir_tracabilite_tickets: Recherche traçabilité tickets

DÉCORATEURS DISPONIBLES:
- @inventaire_admin_required(): Pour saisie inventaire admin
- @liste_inventaires_admin_required(): Pour liste inventaires admin
- @tracabilite_tickets_required(): Pour traçabilité tickets
- @api_permission_required(): Pour endpoints API
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Avg, Count, Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, date

# Import des modèles
from .models import (
    InventaireJournalier, DetailInventairePeriode, RecetteJournaliere,
    ConfigurationJour, PeriodeHoraire, SerieTicket, CouleurTicket
)
from accounts.models import Poste, UtilisateurSUPPER

# Import du système de permissions granulaires
from common.permissions import (
    has_permission,
    has_any_permission,
    get_postes_accessibles,
    check_poste_access,
    is_admin_user,
    peut_saisir_inventaire_admin,
    peut_voir_liste_inventaires_admin,
    peut_voir_tracabilite_tickets,
    get_permissions_summary,
)

from common.decorators import (
    inventaire_admin_required,
    liste_inventaires_admin_required,
    tracabilite_tickets_required,
    api_permission_required,
    permission_required_granular,
)

# Import des utilitaires de logging
from common.utils import log_user_action

import logging
logger = logging.getLogger('supper.inventaire')


# ===================================================================
# VUE: INVENTAIRE ADMINISTRATIF - Sélection poste/date
# Permission: peut_saisir_inventaire_admin
# URL: /inventaire/administratif/
# ===================================================================

@login_required
@inventaire_admin_required()
def inventaire_administratif(request):
    """
    Vue administrative pour saisie d'inventaire tous postes.
    
    Permissions requises:
    - peut_saisir_inventaire_admin
    
    Fonctionnalités:
    - Sélection du poste parmi tous les postes actifs
    - Sélection de la date d'inventaire
    - Indication visuelle des postes ayant déjà un inventaire
    """
    user = request.user
    today = timezone.now().date()
    
    # Récupérer tous les postes actifs (admin a accès à tous)
    postes = Poste.objects.filter(is_active=True).order_by('nom')
    
    # Récupérer les inventaires existants pour aujourd'hui
    inventaires_existants = InventaireJournalier.objects.filter(
        date=today
    ).values_list('poste_id', flat=True)
    
    # Marquer les postes qui ont déjà un inventaire
    for poste in postes:
        poste.has_inventaire_today = poste.id in inventaires_existants
    
    context = {
        'postes': postes,
        'today': today,
        'inventaires_existants_count': len(inventaires_existants),
        'user_permissions': get_permissions_summary(user),
    }
    
    # Traitement POST: Sélection du poste
    if request.method == 'POST' and 'select_poste' in request.POST:
        poste_id = request.POST.get('poste_id')
        date_str = request.POST.get('date')
        
        if poste_id and date_str:
            try:
                poste = Poste.objects.get(id=poste_id)
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                
                # Vérifier si un inventaire existe déjà
                inventaire_existe = InventaireJournalier.objects.filter(
                    poste=poste,
                    date=date_obj
                ).exists()
                
                if inventaire_existe:
                    messages.info(
                        request, 
                        f"Un inventaire existe déjà pour {poste.nom} le {date_obj.strftime('%d/%m/%Y')}. "
                        f"Vous allez le modifier."
                    )
                
                # Log de l'action
                log_user_action(
                    user=user,
                    action="Sélection poste inventaire admin",
                    details=f"Poste: {poste.nom} ({poste.code}) | Date: {date_obj.strftime('%d/%m/%Y')} | "
                           f"Modification: {'Oui' if inventaire_existe else 'Non'}",
                    request=request
                )
                
                return redirect('inventaire:inventaire_admin_saisie', 
                              poste_id=poste_id, date_str=date_str)
                              
            except Poste.DoesNotExist:
                messages.error(request, "Poste non trouvé.")
                log_user_action(
                    user=user,
                    action="Erreur sélection poste inventaire",
                    details=f"Poste ID {poste_id} introuvable",
                    request=request
                )
            except ValueError:
                messages.error(request, "Format de date invalide.")
    
    return render(request, 'inventaire/inventaire_administratif.html', context)


# ===================================================================
# VUE: SAISIE INVENTAIRE ADMINISTRATIF
# Permission: peut_saisir_inventaire_admin
# URL: /inventaire/administratif/saisie/<poste_id>/<date_str>/
# ===================================================================

@login_required
@inventaire_admin_required()
def inventaire_admin_saisie(request, poste_id, date_str):
    """
    Saisie administrative d'inventaire pour un poste et une date.
    
    Permissions requises:
    - peut_saisir_inventaire_admin
    
    Fonctionnalités:
    - Création ou modification d'inventaire
    - Saisie par créneaux horaires
    - Calcul automatique des totaux et recette potentielle
    - Traçabilité des modifications
    """
    user = request.user
    poste = get_object_or_404(Poste, id=poste_id)
    date_inventaire = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    # Créer ou récupérer l'inventaire
    inventaire, created = InventaireJournalier.objects.get_or_create(
        poste=poste,
        date=date_inventaire,
        defaults={
            'agent_saisie': user,
            'type_inventaire': 'administratif',
        }
    )
    
    # Si l'inventaire existait déjà, mettre à jour le type si nécessaire
    if not created and inventaire.type_inventaire != 'administratif':
        inventaire.type_inventaire = 'administratif'
        inventaire.derniere_modification_par = user
        inventaire.save(update_fields=['type_inventaire', 'derniere_modification_par'])
    
    # Traitement POST: Sauvegarde de l'inventaire
    if request.method == 'POST' and 'save_inventaire' in request.POST:
        # Traiter les périodes
        total_vehicules = 0
        nombre_periodes = 0
        periodes_saisies = []
        
        for periode_choice in PeriodeHoraire.choices:
            periode_code, periode_label = periode_choice
            field_name = f'periode_{periode_code}'
            
            if field_name in request.POST:
                nombre_str = request.POST[field_name]
                if nombre_str and nombre_str.strip():
                    try:
                        nombre = int(nombre_str)
                        if nombre >= 0:
                            DetailInventairePeriode.objects.update_or_create(
                                inventaire=inventaire,
                                periode=periode_code,
                                defaults={'nombre_vehicules': nombre}
                            )
                            total_vehicules += nombre
                            nombre_periodes += 1
                            periodes_saisies.append(f"{periode_label}: {nombre}")
                    except ValueError:
                        pass
        
        # Mettre à jour les totaux et tracer la modification
        inventaire.total_vehicules = total_vehicules
        inventaire.nombre_periodes_saisies = nombre_periodes
        inventaire.observations = request.POST.get('observations', '')
        inventaire.derniere_modification_par = user
        inventaire.save()
        
        # Calculer automatiquement la recette potentielle
        recette_potentielle = inventaire.calculer_recette_potentielle()
        
        # Log détaillé de l'action
        action_type = "Création" if created else "Modification"
        log_user_action(
            user=user,
            action=f"{action_type} inventaire administratif",
            details=f"Poste: {poste.nom} ({poste.code}) | Date: {date_inventaire.strftime('%d/%m/%Y')} | "
                   f"Total véhicules: {total_vehicules} | Périodes saisies: {nombre_periodes} | "
                   f"Recette potentielle: {recette_potentielle:,.0f} FCFA | "
                   f"Détail: {', '.join(periodes_saisies[:5])}{'...' if len(periodes_saisies) > 5 else ''}",
            request=request
        )
        
        # Message de succès
        if created:
            messages.success(
                request, 
                f"✅ Inventaire créé avec succès pour {poste.nom}. "
                f"Recette potentielle: {recette_potentielle:,.0f} FCFA"
            )
        else:
            messages.success(
                request, 
                f"✅ Inventaire modifié avec succès pour {poste.nom}. "
                f"Recette potentielle: {recette_potentielle:,.0f} FCFA"
            )
        
        return redirect('inventaire:inventaire_administratif')
    
    # Préparer les données pour l'affichage
    periodes_data = []
    details = {d.periode: d.nombre_vehicules 
              for d in inventaire.details_periodes.all()}
    
    for periode_code, periode_display in PeriodeHoraire.choices:
        periodes_data.append({
            'code': periode_code,
            'display': periode_display,
            'value': details.get(periode_code, '')
        })
    
    context = {
        'poste': poste,
        'date_inventaire': date_inventaire,
        'inventaire': inventaire,
        'periodes_data': periodes_data,
        'total_vehicules': inventaire.total_vehicules,
        'recette_potentielle': inventaire.calculer_recette_potentielle(),
        'is_modification': not created,
        'created_by': inventaire.agent_saisie if inventaire.agent_saisie else None,
        'last_modified_by': getattr(inventaire, 'derniere_modification_par', None),
        'user_permissions': get_permissions_summary(user),
    }
    
    return render(request, 'inventaire/inventaire_admin_saisie.html', context)


# ===================================================================
# VUE: LISTE INVENTAIRES ADMINISTRATIFS
# Permission: peut_voir_liste_inventaires_admin
# URL: /inventaire/administratifs/liste/
# ===================================================================

@login_required
@liste_inventaires_admin_required()
def liste_inventaires_administratifs(request):
    """
    Liste des inventaires saisis par les administrateurs.
    
    Permissions requises:
    - peut_voir_liste_inventaires_admin
    
    Fonctionnalités:
    - Filtrage par poste, date, recherche
    - Calcul du taux de déperdition avec code couleur
    - Pagination
    - Export possible
    """
    user = request.user
    
    # Queryset de base: inventaires administratifs
    queryset = InventaireJournalier.objects.filter(
        type_inventaire='administratif'
    ).select_related(
        'poste', 'agent_saisie'
    ).prefetch_related('details_periodes')
    
    # Filtrer par administrateur si demandé
    if request.GET.get('admin_only'):
        queryset = queryset.filter(
            agent_saisie__habilitation__in=['admin_principal', 'coord_psrr', 'serv_info']
        )
    
    # Filtre par poste
    poste_id = request.GET.get('poste')
    if poste_id:
        queryset = queryset.filter(poste_id=poste_id)
    
    # Filtre par dates
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    
    if date_debut:
        try:
            date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
            queryset = queryset.filter(date__gte=date_debut_obj)
        except ValueError:
            pass
    
    if date_fin:
        try:
            date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
            queryset = queryset.filter(date__lte=date_fin_obj)
        except ValueError:
            pass
    
    # Recherche textuelle
    search = request.GET.get('search')
    if search:
        queryset = queryset.filter(
            Q(poste__nom__icontains=search) |
            Q(poste__code__icontains=search) |
            Q(agent_saisie__nom_complet__icontains=search)
        )
    
    # Tri par date décroissante puis par poste
    queryset = queryset.order_by('-date', 'poste__nom')
    
    # Pagination
    paginator = Paginator(queryset, 20)
    page = request.GET.get('page')
    inventaires = paginator.get_page(page)
    
    # Calculer les taux pour chaque inventaire
    for inv in inventaires:
        try:
            recette = RecetteJournaliere.objects.get(
                poste=inv.poste,
                date=inv.date
            )
            inv.montant_declare = recette.montant_declare
            inv.recette_potentielle = inv.calculer_recette_potentielle()
            
            if inv.recette_potentielle > 0:
                ecart = recette.montant_declare - inv.recette_potentielle
                inv.taux_deperdition = (ecart / inv.recette_potentielle) * 100
                
                # Code couleur selon le taux
                if inv.taux_deperdition > -5:
                    inv.couleur_alerte = 'secondary'
                elif inv.taux_deperdition >= -29.99:
                    inv.couleur_alerte = 'success'
                else:
                    inv.couleur_alerte = 'danger'
            else:
                inv.taux_deperdition = None
                inv.couleur_alerte = 'secondary'
        except RecetteJournaliere.DoesNotExist:
            inv.montant_declare = None
            inv.taux_deperdition = None
            inv.couleur_alerte = 'secondary'
    
    # Statistiques
    today = timezone.now().date()
    stats = {
        'total': queryset.count(),
        'today': queryset.filter(date=today).count(),
        'this_month': queryset.filter(
            date__month=today.month,
            date__year=today.year
        ).count()
    }
    
    # Log de consultation
    filtres_appliques = []
    if poste_id:
        filtres_appliques.append(f"poste={poste_id}")
    if date_debut:
        filtres_appliques.append(f"depuis={date_debut}")
    if date_fin:
        filtres_appliques.append(f"jusqu'à={date_fin}")
    if search:
        filtres_appliques.append(f"recherche='{search}'")
    
    log_user_action(
        user=user,
        action="Consultation liste inventaires admin",
        details=f"Total: {stats['total']} inventaires | Page: {page or 1} | "
               f"Filtres: {', '.join(filtres_appliques) if filtres_appliques else 'Aucun'}",
        request=request
    )
    
    context = {
        'inventaires': inventaires,
        'postes': Poste.objects.filter(is_active=True).order_by('nom'),
        'stats': stats,
        'title': 'Inventaires Administratifs',
        'current_filters': {
            'poste': request.GET.get('poste', ''),
            'date_debut': request.GET.get('date_debut', ''),
            'date_fin': request.GET.get('date_fin', ''),
            'search': request.GET.get('search', ''),
        },
        'user_permissions': get_permissions_summary(user),
    }
    
    return render(request, 'inventaire/liste_inventaires_administratifs.html', context)


# ===================================================================
# VUE: RECHERCHE TRAÇABILITÉ TICKET
# Permission: peut_voir_tracabilite_tickets
# URL: /inventaire/tracabilite-ticket/
# ===================================================================

@login_required
@tracabilite_tickets_required()
def recherche_tracabilite_ticket(request):
    """
    Vue administrative de recherche et traçabilité des tickets.
    
    Permissions requises:
    - peut_voir_tracabilite_tickets
    
    Fonctionnalités:
    - Recherche multi-années ou année spécifique
    - Affichage historique complet par année
    - Traçage du cycle de vie d'un numéro de ticket
    """
    user = request.user
    resultats = None
    numero_recherche = None
    couleur_recherche = None
    annee_recherche = None
    
    if request.method == 'POST':
        numero_recherche = request.POST.get('numero_ticket')
        couleur_id = request.POST.get('couleur_id')
        annee_recherche = request.POST.get('annee')
        
        if numero_recherche and couleur_id:
            try:
                numero = int(numero_recherche)
                couleur = CouleurTicket.objects.get(id=couleur_id)
                
                # Construire la requête
                query = Q(
                    numero_premier__lte=numero,
                    numero_dernier__gte=numero,
                    couleur=couleur
                )
                
                # Filtre par année si spécifiée
                if annee_recherche:
                    annee = int(annee_recherche)
                    debut_annee = date(annee, 1, 1)
                    fin_annee = date(annee, 12, 31)
                    query &= Q(date_reception__range=[debut_annee, fin_annee])
                
                # Exécuter la recherche
                series_trouvees = SerieTicket.objects.filter(query).select_related(
                    'poste', 'couleur', 'reference_recette', 
                    'poste_destination_transfert'
                ).order_by('date_reception')
                
                if series_trouvees.exists():
                    # Groupement par année
                    resultats_par_annee = {}
                    
                    for serie in series_trouvees:
                        annee_serie = serie.date_reception.year
                        
                        if annee_serie not in resultats_par_annee:
                            resultats_par_annee[annee_serie] = []
                        
                        info = {
                            'serie': serie,
                            'annee': annee_serie,
                            'couleur': couleur.libelle_affichage,
                            'numero': numero,
                            'statut': serie.get_statut_display(),
                            'poste_initial': serie.poste,
                            'date_reception': serie.date_reception,
                            'type_entree': serie.get_type_entree_display() if serie.type_entree else 'Non défini'
                        }
                        
                        # Informations selon le statut
                        if serie.statut == 'stock':
                            info['message'] = f"✅ Actuellement en stock au poste {serie.poste.nom}"
                            info['classe_badge'] = 'success'
                        
                        elif serie.statut == 'vendu':
                            info['date_vente'] = serie.date_utilisation
                            info['poste_vente'] = serie.poste.nom
                            
                            if serie.reference_recette:
                                info['recette_id'] = serie.reference_recette.id
                                info['montant_recette'] = serie.reference_recette.montant_declare
                            
                            info['message'] = (
                                f"💰 Vendu le {serie.date_utilisation.strftime('%d/%m/%Y')} "
                                f"au poste {serie.poste.nom}"
                            )
                            info['classe_badge'] = 'primary'
                        
                        elif serie.statut == 'transfere':
                            if serie.poste_destination_transfert:
                                info['poste_destination'] = serie.poste_destination_transfert.nom
                                info['message'] = (
                                    f"📦 Transféré du poste {serie.poste.nom} "
                                    f"vers {serie.poste_destination_transfert.nom}"
                                )
                            else:
                                info['message'] = f"📦 Transféré depuis {serie.poste.nom}"
                            
                            info['classe_badge'] = 'warning'
                        
                        if serie.commentaire:
                            info['commentaire'] = serie.commentaire
                        
                        resultats_par_annee[annee_serie].append(info)
                    
                    # Convertir en liste triée par année (décroissant)
                    resultats = [
                        {
                            'annee': annee,
                            'occurrences': occurrences,
                            'nombre': len(occurrences)
                        }
                        for annee, occurrences in sorted(
                            resultats_par_annee.items(), 
                            reverse=True
                        )
                    ]
                    
                    # Message de succès
                    total_occurrences = sum(r['nombre'] for r in resultats)
                    annees_concernees = [str(r['annee']) for r in resultats]
                    
                    messages.success(
                        request,
                        f"✅ {total_occurrences} occurrence(s) trouvée(s) pour le ticket "
                        f"{couleur.libelle_affichage} #{numero} "
                        f"sur {len(annees_concernees)} année(s) : {', '.join(annees_concernees)}"
                    )
                    
                    # Log de recherche réussie
                    log_user_action(
                        user=user,
                        action="Recherche traçabilité ticket - Trouvé",
                        details=f"Ticket: {couleur.libelle_affichage} #{numero} | "
                               f"Année filtre: {annee_recherche or 'Toutes'} | "
                               f"Résultats: {total_occurrences} occurrence(s) sur {len(annees_concernees)} année(s) | "
                               f"Années: {', '.join(annees_concernees)}",
                        request=request
                    )
                else:
                    messages.warning(
                        request,
                        f"Aucune trace du ticket {couleur.libelle_affichage} #{numero} "
                        f"dans le système" + (f" pour l'année {annee_recherche}" if annee_recherche else "")
                    )
                    
                    # Log de recherche sans résultat
                    log_user_action(
                        user=user,
                        action="Recherche traçabilité ticket - Non trouvé",
                        details=f"Ticket: {couleur.libelle_affichage} #{numero} | "
                               f"Année filtre: {annee_recherche or 'Toutes'} | "
                               f"Résultat: Aucune occurrence",
                        request=request
                    )
            
            except ValueError:
                messages.error(request, "Numéro de ticket ou année invalide")
                log_user_action(
                    user=user,
                    action="Erreur recherche traçabilité",
                    details=f"Erreur de format - Numéro: {numero_recherche} | Année: {annee_recherche}",
                    request=request
                )
            except CouleurTicket.DoesNotExist:
                messages.error(request, "Couleur de ticket invalide")
            except Exception as e:
                messages.error(request, f"Erreur lors de la recherche : {str(e)}")
                logger.error(f"Erreur recherche traçabilité: {str(e)}")
        else:
            messages.error(request, "Veuillez renseigner le numéro de ticket et la couleur")
    
    # Préparation du contexte
    couleurs = CouleurTicket.objects.all().order_by('code_normalise')
    
    # Années disponibles (10 dernières)
    annee_actuelle = date.today().year
    annees_disponibles = [annee_actuelle - i for i in range(10)]
    
    context = {
        'couleurs': couleurs,
        'annees_disponibles': annees_disponibles,
        'numero_recherche': numero_recherche,
        'couleur_recherche': couleur_recherche,
        'annee_recherche': annee_recherche,
        'resultats': resultats,
        'title': 'Traçabilité des Tickets',
        'user_permissions': get_permissions_summary(user),
    }
    
    return render(request, 'inventaire/recherche_tracabilite_ticket.html', context)


# ===================================================================
# API: VÉRIFICATION UNICITÉ TICKET PAR ANNÉE
# Permission: peut_voir_tracabilite_tickets
# URL: /inventaire/api/verifier-unicite-ticket/
# ===================================================================

@login_required
@api_permission_required('peut_voir_tracabilite_tickets')
def verifier_unicite_ticket_annee(request):
    """
    API pour vérifier l'unicité d'un ticket dans une année.
    Utilisé lors de la saisie pour validation en temps réel.
    
    Permissions requises:
    - peut_voir_tracabilite_tickets
    
    Méthode: POST
    Paramètres:
    - numero: Numéro du ticket
    - couleur_id: ID de la couleur
    - annee: Année à vérifier
    
    Retourne: JSON avec est_unique, message, historique
    """
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': 'Méthode non autorisée'
        }, status=405)
    
    numero = request.POST.get('numero')
    couleur_id = request.POST.get('couleur_id')
    annee = request.POST.get('annee')
    
    if not all([numero, couleur_id, annee]):
        return JsonResponse({
            'success': False,
            'message': 'Paramètres manquants (numero, couleur_id, annee requis)'
        })
    
    try:
        numero = int(numero)
        annee = int(annee)
        couleur = CouleurTicket.objects.get(id=couleur_id)
        
        # Vérification d'unicité
        est_unique, message, historique = SerieTicket.verifier_unicite_annuelle(
            numero, couleur, annee
        )
        
        # Log de la vérification API
        log_user_action(
            user=request.user,
            action="API vérification unicité ticket",
            details=f"Ticket: {couleur.libelle_affichage} #{numero} | "
                   f"Année: {annee} | Unique: {'Oui' if est_unique else 'Non'}",
            request=request
        )
        
        return JsonResponse({
            'success': True,
            'est_unique': est_unique,
            'message': message,
            'historique': historique
        })
    
    except CouleurTicket.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Couleur de ticket non trouvée'
        })
    except ValueError:
        return JsonResponse({
            'success': False,
            'message': 'Numéro ou année invalide'
        })
    except Exception as e:
        logger.error(f"Erreur API vérification unicité: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'Erreur serveur: {str(e)}'
        })