# inventaire/views_stock_event_sourcing.py
# Vues pour exploiter le système Event Sourcing
# CORRIGÉ: get_stock_at_date retourne un tuple (valeur, tickets), pas un dict

from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages
from datetime import datetime, date, timedelta
from decimal import Decimal
import csv

from accounts.models import Poste
from inventaire.models import StockEvent, StockSnapshot
import logging

logger = logging.getLogger('supper')


def is_admin(user):
    """Vérifie si l'utilisateur est admin"""
    return user.is_authenticated and (
        user.is_superuser or 
        user.is_staff or
        (hasattr(user, 'is_admin') and user.is_admin)
    )


@login_required
def stock_historique_date(request, poste_id=None):
    """
    Vue pour afficher le stock à une date précise
    Admin : peut sélectionner n'importe quel poste
    Chef de poste : voit uniquement son poste
    """
    
    # Si pas de poste_id, rediriger vers la vue de sélection
    if poste_id is None:
        return stock_selection_date(request)
    
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Vérification des permissions
    if not request.user.is_admin:
        if not request.user.peut_acceder_poste(poste):
            return HttpResponseForbidden("Accès non autorisé à ce poste")
    
    # Récupérer la date demandée (par défaut aujourd'hui)
    date_str = request.GET.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()
    
    # ========================================
    # CORRECTION: get_stock_at_date retourne un tuple (valeur, tickets)
    # ========================================
    stock_valeur, stock_tickets = StockEvent.get_stock_at_date(poste, target_date)
    
    # Obtenir le dernier événement jusqu'à cette date
    dernier_event = StockEvent.objects.filter(
        poste=poste,
        event_datetime__date__lte=target_date,
        is_cancelled=False
    ).order_by('-event_datetime').first()
    
    # Compter le nombre total d'événements jusqu'à cette date
    nombre_events = StockEvent.objects.filter(
        poste=poste,
        event_datetime__date__lte=target_date,
        is_cancelled=False
    ).count()
    
    # Obtenir l'historique des 30 derniers jours
    date_debut = target_date - timedelta(days=30)
    history = StockEvent.get_stock_history(poste, date_debut, target_date, interval='daily')
    
    # Obtenir les événements de ce jour
    events_jour = StockEvent.objects.filter(
        poste=poste,
        event_datetime__date=target_date,
        is_cancelled=False
    ).order_by('event_datetime')
    
    # Ajouter la liste des postes pour admin
    postes_disponibles = []
    if request.user.is_admin:
        postes_disponibles = Poste.objects.filter(is_active=True).order_by('nom')
    
    context = {
        'poste': poste,
        'date_selectionnee': target_date,
        'stock_valeur': stock_valeur,
        'stock_tickets': stock_tickets,
        'dernier_event': dernier_event,
        'nombre_events_total': nombre_events,
        'events_jour': events_jour,
        'history': history,
        'postes_disponibles': postes_disponibles,
        'is_admin': request.user.is_admin,
        'title': f'Stock de {poste.nom} au {target_date.strftime("%d/%m/%Y")}'
    }
    
    return render(request, 'inventaire/stock_historique_date.html', context)


@login_required
def stock_selection_date(request):
    """
    Vue pour sélectionner poste et date (admin) ou seulement date (chef de poste)
    """
    # Déterminer les postes accessibles
    if request.user.is_admin:
        postes = Poste.objects.filter(is_active=True).order_by('nom')
    else:
        # Chef de poste : seulement son poste
        postes = request.user.get_postes_accessibles()
    
    # Si soumission du formulaire
    if request.method == 'POST':
        poste_id = request.POST.get('poste_id')
        date_str = request.POST.get('date')
        
        if poste_id:
            # Vérifier l'accès au poste
            try:
                poste = Poste.objects.get(id=poste_id)
                if request.user.peut_acceder_poste(poste):
                    url = reverse('inventaire:stock_historique_date', kwargs={'poste_id': poste_id})
                    if date_str:
                        url += f'?date={date_str}'
                    return redirect(url)
            except Poste.DoesNotExist:
                pass
        
        messages.error(request, "Veuillez sélectionner un poste valide.")
    
    # Pour un chef de poste avec un seul poste, rediriger directement
    if postes.count() == 1 and not request.user.is_admin:
        poste = postes.first()
        return redirect('inventaire:stock_historique_date', poste_id=poste.id)
    
    context = {
        'postes': postes,
        'date_selectionnee': date.today(),
        'title': 'Sélection du poste et de la date'
    }
    
    return render(request, 'inventaire/stock_selection_date.html', context)


@login_required
def api_stock_timeline(request, poste_id):
    """
    API JSON pour obtenir l'évolution du stock sur une période
    Utilisé pour les graphiques
    """
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Vérification des permissions
    if not request.user.is_admin:
        if not request.user.peut_acceder_poste(poste):
            return JsonResponse({'error': 'Accès non autorisé'}, status=403)
    
    # Récupérer les paramètres
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    interval = request.GET.get('interval', 'daily')  # daily, weekly, monthly
    
    try:
        if date_debut_str:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        else:
            date_debut = date.today() - timedelta(days=30)
        
        if date_fin_str:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
        else:
            date_fin = date.today()
    except ValueError:
        return JsonResponse({'error': 'Format de date invalide'}, status=400)
    
    # Obtenir l'historique (retourne une liste de dicts avec 'date', 'valeur', 'nombre_tickets')
    history = StockEvent.get_stock_history(poste, date_debut, date_fin, interval)
    
    # Formater pour Chart.js
    data = {
        'labels': [h['date'].strftime('%Y-%m-%d') for h in history],
        'datasets': [
            {
                'label': 'Valeur du stock (FCFA)',
                'data': [float(h['valeur']) for h in history],
                'borderColor': 'rgb(59, 130, 246)',
                'backgroundColor': 'rgba(59, 130, 246, 0.1)',
                'tension': 0.1
            }
        ]
    }
    
    # Ajouter les événements marquants
    events = StockEvent.objects.filter(
        poste=poste,
        event_datetime__date__range=[date_debut, date_fin],
        is_cancelled=False
    ).order_by('event_datetime')
    
    annotations = []
    for event in events:
        if abs(event.montant_variation) > 100000:  # Événements significatifs
            annotations.append({
                'date': event.event_datetime.strftime('%Y-%m-%d'),
                'label': event.get_event_type_display(),
                'value': float(event.montant_variation)
            })
    
    # Calculer le résumé
    stock_debut = history[0]['valeur'] if history else Decimal('0')
    stock_fin = history[-1]['valeur'] if history else Decimal('0')
    
    return JsonResponse({
        'chart_data': data,
        'annotations': annotations,
        'summary': {
            'stock_debut': float(stock_debut),
            'stock_fin': float(stock_fin),
            'variation': float(stock_fin - stock_debut),
            'nombre_events': events.count()
        }
    })


@login_required
@user_passes_test(is_admin)
def comparer_stocks_dates(request):
    """
    Vue pour comparer les stocks de plusieurs postes à différentes dates
    Réservé aux admins
    """
    postes = Poste.objects.filter(is_active=True).order_by('nom')
    
    # Récupérer les dates de comparaison
    date1_str = request.GET.get('date1')
    date2_str = request.GET.get('date2')
    
    comparaison_data = []
    date1 = None
    date2 = None
    
    if date1_str and date2_str:
        try:
            date1 = datetime.strptime(date1_str, '%Y-%m-%d').date()
            date2 = datetime.strptime(date2_str, '%Y-%m-%d').date()
            
            for poste in postes:
                # ========================================
                # CORRECTION: get_stock_at_date retourne un tuple
                # ========================================
                stock1_valeur, stock1_tickets = StockEvent.get_stock_at_date(poste, date1)
                stock2_valeur, stock2_tickets = StockEvent.get_stock_at_date(poste, date2)
                
                # Calculer la variation en pourcentage
                if stock1_valeur > 0:
                    variation_pourcentage = ((stock2_valeur - stock1_valeur) / stock1_valeur * 100)
                else:
                    variation_pourcentage = Decimal('0')
                
                comparaison_data.append({
                    'poste': poste,
                    'stock_date1': stock1_valeur,
                    'tickets_date1': stock1_tickets,
                    'stock_date2': stock2_valeur,
                    'tickets_date2': stock2_tickets,
                    'variation_valeur': stock2_valeur - stock1_valeur,
                    'variation_tickets': stock2_tickets - stock1_tickets,
                    'variation_pourcentage': variation_pourcentage
                })
                
        except ValueError:
            messages.error(request, "Format de date invalide.")
            date1 = date2 = None
    
    context = {
        'postes': postes,
        'date1': date1,
        'date2': date2,
        'comparaison_data': comparaison_data,
        'title': 'Comparaison des stocks entre dates'
    }
    
    return render(request, 'inventaire/comparer_stocks_dates.html', context)


@login_required
def export_stock_history_csv(request, poste_id):
    """
    Exporte l'historique complet du stock en CSV
    """
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Vérification des permissions
    if not request.user.is_admin:
        if not request.user.peut_acceder_poste(poste):
            return HttpResponseForbidden("Accès non autorisé")
    
    # Récupérer tous les événements
    events = StockEvent.objects.filter(
        poste=poste,
        is_cancelled=False
    ).order_by('event_datetime')
    
    # Créer la réponse CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="stock_history_{poste.code}_{date.today()}.csv"'
    
    # Ajouter le BOM UTF-8 pour Excel
    response.write('\ufeff')
    
    writer = csv.writer(response, delimiter=';')
    
    # En-tête
    writer.writerow([
        'Date/Heure',
        'Type',
        'Variation',
        'Stock Avant',
        'Stock Après',
        'Nombre Tickets',
        'Effectué Par',
        'Commentaire'
    ])
    
    stock_precedent = Decimal('0')
    
    # Lignes de données
    for event in events:
        writer.writerow([
            event.event_datetime.strftime('%d/%m/%Y %H:%M'),
            event.get_event_type_display(),
            f"{'+' if event.montant_variation >= 0 else ''}{event.montant_variation}",
            stock_precedent,
            event.stock_resultant,
            event.tickets_resultants,
            event.effectue_par.nom_complet if event.effectue_par else '-',
            event.commentaire[:100] if event.commentaire else ''
        ])
        stock_precedent = event.stock_resultant
    
    return response


@login_required
@user_passes_test(is_admin)
def rebuild_stock_events(request, poste_id):
    """
    Recalcule tous les stocks résultants pour un poste
    Utile en cas de correction ou d'incohérence
    """
    poste = get_object_or_404(Poste, id=poste_id)
    
    if request.method == 'POST':
        # Reconstruire l'historique
        events = StockEvent.objects.filter(
            poste=poste,
            is_cancelled=False
        ).order_by('event_datetime')
        
        stock_courant = Decimal('0')
        events_corriges = 0
        
        for event in events:
            stock_courant += event.montant_variation
            
            if event.stock_resultant != stock_courant:
                event.stock_resultant = stock_courant
                event.tickets_resultants = int(stock_courant / 500)
                event.save(update_fields=['stock_resultant', 'tickets_resultants'])
                events_corriges += 1
        
        # Mettre à jour le stock actuel dans GestionStock
        try:
            from inventaire.models import GestionStock
            stock_obj, created = GestionStock.objects.get_or_create(poste=poste)
            stock_obj.valeur_monetaire = stock_courant
            stock_obj.save()
        except Exception as e:
            logger.warning(f"Impossible de mettre à jour GestionStock: {e}")
        
        messages.success(
            request,
            f"Reconstruction terminée : {events_corriges} événements corrigés. "
            f"Stock final : {stock_courant:,.0f} FCFA"
        )
        
        return redirect('inventaire:stock_historique_date', poste_id=poste.id)
    
    # GET : Afficher la page de confirmation
    events = StockEvent.objects.filter(poste=poste).order_by('event_datetime')
    
    # Détecter les incohérences
    incoherences = []
    stock_calcule = Decimal('0')
    
    for event in events:
        if not event.is_cancelled:
            stock_calcule += event.montant_variation
            
            if abs(event.stock_resultant - stock_calcule) > Decimal('0.01'):
                incoherences.append({
                    'event': event,
                    'stock_attendu': stock_calcule,
                    'stock_enregistre': event.stock_resultant,
                    'difference': event.stock_resultant - stock_calcule
                })
    
    context = {
        'poste': poste,
        'total_events': events.count(),
        'incoherences': incoherences,
        'stock_calcule_final': stock_calcule,
        'title': f'Reconstruire stock - {poste.nom}'
    }
    
    return render(request, 'inventaire/rebuild_stock_events.html', context)


@login_required
def api_stock_at_date(request, poste_id):
    """
    API JSON pour obtenir le stock à une date précise
    Utilisé pour les requêtes AJAX
    """
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Vérification des permissions
    if not request.user.is_admin:
        if not request.user.peut_acceder_poste(poste):
            return JsonResponse({'error': 'Accès non autorisé'}, status=403)
    
    # Récupérer la date
    date_str = request.GET.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'error': 'Format de date invalide'}, status=400)
    else:
        target_date = date.today()
    
    # Obtenir le stock (tuple)
    stock_valeur, stock_tickets = StockEvent.get_stock_at_date(poste, target_date)
    
    # Compter les événements du jour
    events_jour = StockEvent.objects.filter(
        poste=poste,
        event_datetime__date=target_date,
        is_cancelled=False
    ).count()
    
    return JsonResponse({
        'poste': {
            'id': poste.id,
            'nom': poste.nom,
            'code': poste.code
        },
        'date': target_date.strftime('%Y-%m-%d'),
        'stock': {
            'valeur': float(stock_valeur),
            'tickets': stock_tickets
        },
        'events_jour': events_jour
    })