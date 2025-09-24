from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from datetime import datetime
from .models import *
from accounts.models import Poste

def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.habilitation == 'admin_principal')

@login_required
@user_passes_test(is_admin)
def inventaire_administratif(request):
    """Vue administrative pour saisie d'inventaire tous postes"""
    
    context = {
        'postes': Poste.objects.filter(is_active=True).order_by('nom'),
        'today': timezone.now().date()
    }
    
    # Étape 1: Sélection du poste
    if request.method == 'POST' and 'select_poste' in request.POST:
        poste_id = request.POST.get('poste_id')
        date_str = request.POST.get('date')
        
        if poste_id and date_str:
            return redirect('inventaire:inventaire_admin_saisie', 
                          poste_id=poste_id, date_str=date_str)
    
    return render(request, 'inventaire/inventaire_administratif.html', context)

@login_required
@user_passes_test(is_admin)
def inventaire_admin_saisie(request, poste_id, date_str):
    """Saisie administrative d'inventaire pour un poste et une date"""
    
    poste = get_object_or_404(Poste, id=poste_id)
    date_inventaire = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    # Récupérer ou créer l'inventaire
    inventaire, created = InventaireJournalier.objects.get_or_create(
        poste=poste,
        date=date_inventaire,
        defaults={'agent_saisie': request.user}
    )
    
    if request.method == 'POST' and 'save_inventaire' in request.POST:
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
        
        # Mettre à jour les totaux
        inventaire.total_vehicules = total_vehicules
        inventaire.nombre_periodes_saisies = nombre_periodes
        inventaire.observations = request.POST.get('observations', '')
        inventaire.save()
        
        # Calculer automatiquement la recette potentielle
        recette_potentielle = inventaire.calculer_recette_potentielle()
        
        messages.success(request, f"Inventaire sauvegardé. Recette potentielle: {recette_potentielle} FCFA")
        return redirect('inventaire:inventaire_administratif')
    
    # Récupérer les détails existants
    details = {d.periode: d.nombre_vehicules 
              for d in inventaire.details_periodes.all()}
    
    context = {
        'poste': poste,
        'date_inventaire': date_inventaire,
        'inventaire': inventaire,
        'periodes': PeriodeHoraire.choices,
        'details': details,
        'total_vehicules': 0,
        'recette_potentielle': 0
    }
    
    return render(request, 'inventaire/inventaire_admin_saisie.html', context)
@login_required
@user_passes_test(is_admin)
def liste_inventaires_administratifs(request):
    """Liste des inventaires saisis par les administrateurs"""
    
    # Récupérer tous les inventaires
    queryset = InventaireJournalier.objects.select_related(
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
        queryset = queryset.filter(date__gte=date_debut)
    if date_fin:
        queryset = queryset.filter(date__lte=date_fin)
    
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
    
    context = {
        'inventaires': inventaires,
        'postes': Poste.objects.filter(is_active=True).order_by('nom'),
        'title': 'Inventaires Administratifs'
    }
    
    return render(request, 'inventaire/liste_inventaires_administratifs.html', context)