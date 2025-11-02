from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from datetime import datetime
from .models import *
from accounts.models import *
from django.db.models import Sum, Avg, Count, Q
from datetime import date
def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.habilitation == 'admin_principal')

@login_required
@user_passes_test(is_admin)
def inventaire_administratif(request):
    """Vue administrative pour saisie d'inventaire tous postes"""
    
    # Récupérer tous les postes actifs
    postes = Poste.objects.filter(is_active=True).order_by('nom')
    
    # Récupérer les inventaires existants pour aujourd'hui
    today = timezone.now().date()
    inventaires_existants = InventaireJournalier.objects.filter(
        date=today
    ).values_list('poste_id', flat=True)
    
    # Marquer les postes qui ont déjà un inventaire
    for poste in postes:
        poste.has_inventaire_today = poste.id in inventaires_existants
    
    context = {
        'postes': postes,
        'today': today,
        'inventaires_existants_count': len(inventaires_existants)
    }
    
    # Étape 1: Sélection du poste
    if request.method == 'POST' and 'select_poste' in request.POST:
        poste_id = request.POST.get('poste_id')
        date_str = request.POST.get('date')
        
        if poste_id and date_str:
            # Vérifier si un inventaire existe déjà
            try:
                poste = Poste.objects.get(id=poste_id)
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                
                inventaire_existe = InventaireJournalier.objects.filter(
                    poste=poste,
                    date=date_obj
                ).exists()
                
                if inventaire_existe:
                    messages.info(request, f"Un inventaire existe déjà pour {poste.nom} le {date_obj.strftime('%d/%m/%Y')}. Vous allez le modifier.")
                
            except (Poste.DoesNotExist, ValueError):
                pass
            
            return redirect('inventaire:inventaire_admin_saisie', 
                          poste_id=poste_id, date_str=date_str)
    
    return render(request, 'inventaire/inventaire_administratif.html', context)
@login_required
@user_passes_test(is_admin)
def inventaire_admin_saisie(request, poste_id, date_str):
    """Saisie administrative d'inventaire pour un poste et une date"""
    
    poste = get_object_or_404(Poste, id=poste_id)
    date_inventaire = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    # CORRECTION : Retirer type_inventaire de la recherche get_or_create
    # Car la contrainte unique est seulement sur ['poste', 'date']
    inventaire, created = InventaireJournalier.objects.get_or_create(
        poste=poste,
        date=date_inventaire,
        # ❌ NE PAS mettre type_inventaire ici
        defaults={
            'agent_saisie': request.user,
            'type_inventaire': 'administratif',
        }
    )
    
    # Si l'inventaire existait déjà, mettre à jour le type si nécessaire
    if not created and inventaire.type_inventaire != 'administratif':
        inventaire.type_inventaire = 'administratif'
        inventaire.derniere_modification_par = request.user
        inventaire.save(update_fields=['type_inventaire', 'derniere_modification_par'])
    
    if request.method == 'POST' and 'save_inventaire' in request.POST:
        # Vérifier les permissions de modification
        if not created and not request.user.is_admin:
            messages.error(request, "Seuls les administrateurs peuvent modifier un inventaire existant.")
            return redirect('inventaire:inventaire_administratif')
        
        # Traiter les périodes
        total_vehicules = 0
        nombre_periodes = 0
        
        for periode_choice in PeriodeHoraire.choices:
            periode_code, _ = periode_choice
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
                    except ValueError:
                        pass
        
        # Mettre à jour les totaux et tracer la modification
        inventaire.total_vehicules = total_vehicules
        inventaire.nombre_periodes_saisies = nombre_periodes
        inventaire.observations = request.POST.get('observations', '')
        inventaire.derniere_modification_par = request.user
        inventaire.save()
        
        # Calculer automatiquement la recette potentielle
        recette_potentielle = inventaire.calculer_recette_potentielle()
        
        # Message différencié selon création ou modification
        if created:
            messages.success(request, f"Inventaire créé avec succès. Recette potentielle: {recette_potentielle} FCFA")
        else:
            messages.success(request, f"Inventaire modifié avec succès. Recette potentielle: {recette_potentielle} FCFA")
        
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
        'is_modification': not created,  # Indiquer si c'est une modification
        'created_by': inventaire.agent_saisie if inventaire.agent_saisie else None,
        'last_modified_by': inventaire.derniere_modification_par if hasattr(inventaire, 'derniere_modification_par') else None
    }
    
    return render(request, 'inventaire/inventaire_admin_saisie.html', context)
@login_required
@user_passes_test(is_admin)
def liste_inventaires_administratifs(request):
    """Liste des inventaires saisis par les administrateurs"""
    
    # Récupérer tous les inventaires
    queryset = InventaireJournalier.objects.filter(
        type_inventaire='administratif'  # Seulement les inventaires administratifs
    ).select_related(
        'poste', 'agent_saisie'
    ).prefetch_related('details_periodes')
    
    # Filtrer par administrateur si nécessaire
    if request.GET.get('admin_only'):
        queryset = queryset.filter(
            agent_saisie__habilitation__in=['admin_principal', 'coord_psrr', 'serv_info']
        )
    
    # Filtres
    poste_id = request.GET.get('poste')
    if poste_id:
        queryset = queryset.filter(poste_id=poste_id)
    
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    if date_debut:
        try:
            date_debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
            queryset = queryset.filter(date__gte=date_debut)
        except ValueError:
            pass
    
    if date_fin:
        try:
            date_fin = datetime.strptime(date_fin, '%Y-%m-%d').date()
            queryset = queryset.filter(date__lte=date_fin)
        except ValueError:
            pass
    # Recherche
    search = request.GET.get('search')
    if search:
        queryset = queryset.filter(
            Q(poste__nom__icontains=search) |
            Q(poste__code__icontains=search) |
            Q(agent_saisie__nom_complet__icontains=search)
        )
    
    # Tri
    queryset = queryset.order_by('-date', 'poste__nom')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(queryset.order_by('-date'), 20)
    page = request.GET.get('page')
    inventaires = paginator.get_page(page)
    
    # Calculer les taux pour chaque inventaire
    for inv in inventaires:
        # Récupérer la recette associée si elle existe
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
                
                # Couleur selon le taux
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
    
    stats = {
        'total': queryset.count(),
        'today': queryset.filter(date=timezone.now().date()).count(),
        'this_month': queryset.filter(
            date__month=timezone.now().month,
            date__year=timezone.now().year
        ).count()
    }
    
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
        }
    }
    
    return render(request, 'inventaire/liste_inventaires_administratifs.html', context)

@login_required
@user_passes_test(is_admin)
def recherche_tracabilite_ticket(request):
    """
    Vue administrative de recherche et traçabilité des tickets
    VERSION AMÉLIORÉE : Gestion des tickets sur plusieurs années
    
    FONCTIONNALITÉ :
    - Recherche un ticket sur toutes les années ou une année spécifique
    - Affiche l'historique complet avec les différentes occurrences par année
    - Permet de tracer le cycle de vie d'un numéro de ticket
    """
    
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
                
                # Recherche dans TOUTES les années si non spécifiée
                query = Q(
                    numero_premier__lte=numero,
                    numero_dernier__gte=numero,
                    couleur=couleur
                )
                
                if annee_recherche:
                    annee = int(annee_recherche)
                    debut_annee = date(annee, 1, 1)
                    fin_annee = date(annee, 12, 31)
                    query &= Q(date_reception__range=[debut_annee, fin_annee])
                
                series_trouvees = SerieTicket.objects.filter(query).select_related(
                    'poste', 'couleur', 'reference_recette', 
                    'poste_destination_transfert'
                ).order_by('date_reception')
                
                if series_trouvees.exists():
                    # ===== GROUPEMENT PAR ANNÉE =====
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
                        
                        # Commentaire si présent
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
                    
                    # Message de succès détaillé
                    total_occurrences = sum(r['nombre'] for r in resultats)
                    annees_concernees = [str(r['annee']) for r in resultats]
                    
                    messages.success(
                        request,
                        f"✅ {total_occurrences} occurrence(s) trouvée(s) pour le ticket "
                        f"{couleur.libelle_affichage} #{numero} "
                        f"sur {len(annees_concernees)} année(s) : {', '.join(annees_concernees)}"
                    )
                else:
                    messages.warning(
                        request,
                        f"Aucune trace du ticket {couleur.libelle_affichage} #{numero} "
                        f"dans le système" + (f" pour l'année {annee_recherche}" if annee_recherche else "")
                    )
            
            except ValueError:
                messages.error(request, "Numéro de ticket ou année invalide")
            except CouleurTicket.DoesNotExist:
                messages.error(request, "Couleur de ticket invalide")
            except Exception as e:
                messages.error(request, f"Erreur lors de la recherche : {str(e)}")
        else:
            messages.error(request, "Veuillez renseigner le numéro de ticket et la couleur")
    
    # Liste de toutes les couleurs pour le formulaire
    couleurs = CouleurTicket.objects.all().order_by('code_normalise')
    
    # Années disponibles pour le filtre (10 dernières années)
    annees_disponibles = []
    annee_actuelle = date.today().year
    for i in range(10):  # 10 dernières années
        annees_disponibles.append(annee_actuelle - i)
    
    context = {
        'couleurs': couleurs,
        'annees_disponibles': annees_disponibles,
        'numero_recherche': numero_recherche,
        'couleur_recherche': couleur_recherche,
        'annee_recherche': annee_recherche,
        'resultats': resultats,
        'title': 'Traçabilité des Tickets'
    }
    
    return render(request, 'inventaire/recherche_tracabilite_ticket.html', context)

@login_required
@user_passes_test(is_admin)
def verifier_unicite_ticket_annee(request):
    """
    API pour vérifier l'unicité d'un ticket dans une année
    Utilisé lors de la saisie pour validation en temps réel
    """
    from django.http import JsonResponse
    
    if request.method == 'POST':
        numero = request.POST.get('numero')
        couleur_id = request.POST.get('couleur_id')
        annee = request.POST.get('annee')
        
        if not all([numero, couleur_id, annee]):
            return JsonResponse({
                'success': False,
                'message': 'Paramètres manquants'
            })
        
        try:
            numero = int(numero)
            annee = int(annee)
            couleur = CouleurTicket.objects.get(id=couleur_id)
            
            est_unique, message, historique = SerieTicket.verifier_unicite_annuelle(
                numero, couleur, annee
            )
            
            return JsonResponse({
                'success': True,
                'est_unique': est_unique,
                'message': message,
                'historique': historique
            })
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})