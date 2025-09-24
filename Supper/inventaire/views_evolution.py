from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from datetime import date, datetime, timedelta
import json
from .models import *

@login_required
def taux_evolution_view(request):
    """Vue pour afficher les taux d'évolution des recettes"""
    
    # Récupération des paramètres
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    poste_id = request.GET.get('poste', 'tous')
    
    if not date_debut or not date_fin:
        # Dates par défaut : du 1er janvier à aujourd'hui
        date_fin = date.today()
        date_debut = date(date_fin.year, 1, 1)
    else:
        date_debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin = datetime.strptime(date_fin, '%Y-%m-%d').date()
    
    # Calculs pour l'année en cours
    filters_n = Q(date__gte=date_debut, date__lte=date_fin)
    if poste_id != 'tous':
        filters_n &= Q(poste_id=poste_id)
    
    montant_n = RecetteJournaliere.objects.filter(filters_n).aggregate(
        total=Sum('montant_declare')
    )['total'] or 0
    
    # Calculs pour N-1
    date_debut_n1 = date(date_debut.year - 1, date_debut.month, date_debut.day)
    date_fin_n1 = date(date_fin.year - 1, date_fin.month, date_fin.day)
    
    filters_n1 = Q(date__gte=date_debut_n1, date__lte=date_fin_n1)
    if poste_id != 'tous':
        filters_n1 &= Q(poste_id=poste_id)
    
    montant_n1 = RecetteJournaliere.objects.filter(filters_n1).aggregate(
        total=Sum('montant_declare')
    )['total'] or 0
    
    # Calculs pour N-2
    date_debut_n2 = date(date_debut.year - 2, date_debut.month, date_debut.day)
    date_fin_n2 = date(date_fin.year - 2, date_fin.month, date_fin.day)
    
    filters_n2 = Q(date__gte=date_debut_n2, date__lte=date_fin_n2)
    if poste_id != 'tous':
        filters_n2 &= Q(poste_id=poste_id)
    
    montant_n2 = RecetteJournaliere.objects.filter(filters_n2).aggregate(
        total=Sum('montant_declare')
    )['total'] or 0
    
    # Calcul des taux d'évolution
    taux_n1 = ((montant_n - montant_n1) / montant_n1 * 100) if montant_n1 > 0 else None
    taux_n2 = ((montant_n - montant_n2) / montant_n2 * 100) if montant_n2 > 0 else None
    
    context = {
        'date_debut': date_debut,
        'date_fin': date_fin,
        'montant_n': montant_n,
        'montant_n1': montant_n1,
        'montant_n2': montant_n2,
        'taux_evolution_n1': taux_n1,
        'taux_evolution_n2': taux_n2,
        'postes': Poste.objects.filter(is_active=True),
        'poste_selectionne': poste_id
    }
    
    return render(request, 'inventaire/taux_evolution.html', context)