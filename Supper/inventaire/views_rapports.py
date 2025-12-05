# inventaire/views_rapports.py
# VERSION 2 - Compte d'emploi avec nouveau format de tableau
# ===================================================================

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum, Q
from django.http import HttpResponse
from datetime import date, timedelta, datetime
from decimal import Decimal
import logging

from accounts.models import Poste
from inventaire.models import (
    SerieTicket, StockEvent, HistoriqueStock, CouleurTicket,
    GestionStock
)
from inventaire.models_config import ConfigurationGlobale

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, 
    Spacer, Image, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

import os
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('supper')


# ===================================================================
# SÉLECTION DU COMPTE D'EMPLOI
# ===================================================================

@login_required
def selection_compte_emploi(request):
    """
    Permet de choisir entre aperçu et génération directe PDF
    """
    # Vérifier les permissions
    if not (request.user.is_admin or request.user.is_chef_poste):
        messages.error(request, "Accès non autorisé")
        return redirect('common:dashboard')
    
    # Postes accessibles
    if request.user.is_admin:
        postes = Poste.objects.filter(is_active=True).order_by('nom')
    else:
        postes = [request.user.poste_affectation] if request.user.poste_affectation else []
    
    # Dates par défaut suggérées
    today = date.today()
    
    # Suggestion : début du mois précédent → fin du mois précédent
    premier_jour_mois_actuel = today.replace(day=1)
    dernier_jour_mois_precedent = premier_jour_mois_actuel - timedelta(days=1)
    premier_jour_mois_precedent = dernier_jour_mois_precedent.replace(day=1)
    
    date_debut_suggestion = premier_jour_mois_precedent
    date_fin_suggestion = dernier_jour_mois_precedent
    
    if request.method == 'POST':
        poste_id = request.POST.get('poste_id')
        date_debut_str = request.POST.get('date_debut')
        date_fin_str = request.POST.get('date_fin')
        action = request.POST.get('action', 'apercu')
        
        # Validations
        if not poste_id:
            messages.error(request, "Veuillez sélectionner un poste")
        elif not date_debut_str or not date_fin_str:
            messages.error(request, "Veuillez sélectionner une date de début et une date de fin")
        else:
            try:
                date_debut = date.fromisoformat(date_debut_str)
                date_fin = date.fromisoformat(date_fin_str)
                
                if date_debut > date_fin:
                    messages.error(request, "La date de début doit être antérieure à la date de fin")
                elif date_fin > today:
                    messages.error(request, "La date de fin ne peut pas être dans le futur")
                elif (date_fin - date_debut).days > 365:
                    messages.error(request, "La période ne peut pas dépasser 1 an")
                else:
                    if action == 'apercu':
                        return redirect('inventaire:apercu_compte_emploi', 
                                      poste_id=poste_id,
                                      date_debut=date_debut_str,
                                      date_fin=date_fin_str)
                    else:
                        return redirect('inventaire:generer_compte_emploi', 
                                      poste_id=poste_id,
                                      date_debut=date_debut_str,
                                      date_fin=date_fin_str)
            
            except ValueError:
                messages.error(request, "Format de date invalide")
    
    context = {
        'postes': postes,
        'date_debut_suggestion': date_debut_suggestion,
        'date_fin_suggestion': date_fin_suggestion,
        'date_max': today,
        'title': "Compte d'Emploi des Tickets"
    }
    
    return render(request, 'inventaire/selection_compte_emploi.html', context)


# ===================================================================
# CALCUL DES DONNÉES DU COMPTE D'EMPLOI - VERSION 2
# ===================================================================

def calculer_stock_event_sourcing(poste, date_reference):
    """
    Calcule le stock à une date donnée via Event Sourcing
    Somme de tous les mouvements jusqu'à cette date
    """
    # Convertir la date en datetime avec fin de journée
    if isinstance(date_reference, date) and not isinstance(date_reference, datetime):
        date_reference_dt = timezone.make_aware(
            datetime.combine(date_reference, datetime.max.time().replace(microsecond=999999))
        )
    else:
        date_reference_dt = date_reference
    
    # Via StockEvent
    events = StockEvent.objects.filter(
        poste=poste,
        event_datetime__lte=date_reference_dt,
        is_cancelled=False
    ).aggregate(
        total_valeur=Sum('montant_variation'),
        total_tickets=Sum('nombre_tickets_variation')
    )
    
    valeur = events['total_valeur'] or Decimal('0')
    tickets = events['total_tickets'] or 0
    
    return max(Decimal('0'), valeur), max(0, tickets)


def extraire_series_depuis_historique(hist):
    """
    VERSION CORRIGÉE - Extrait les informations des séries depuis un HistoriqueStock
    
    ORDRE DE PRIORITÉ (données immuables d'abord):
    1. Champs structurés (numero_premier_ticket, numero_dernier_ticket, couleur_principale)
       → Données immuables, remplies lors de la création
    2. JSONField details_approvisionnement  
       → Données immuables, snapshot au moment de l'opération
    3. Parser le commentaire 
       → Données IMMUABLES ! Contient les numéros originaux
    4. ManyToMany series_tickets_associees (DERNIER RECOURS)
       → Données MUTABLES ! Les séries peuvent être modifiées après chargement
    
    CHANGEMENT CLÉ : Le parsing du commentaire est maintenant AVANT le ManyToMany
    """
    import re
    from decimal import Decimal
    
    # Import du modèle CouleurTicket - adapter selon votre structure
    try:
        from inventaire.models import CouleurTicket
    except ImportError:
        from .models import CouleurTicket
    
    # Logger (optionnel, pour debug)
    import logging
    logger = logging.getLogger('supper')
    
    series = []
    
    logger.debug(f"  Extraction séries pour historique {hist.id}:")
    logger.debug(f"    - couleur_principale: {getattr(hist, 'couleur_principale', None)}")
    logger.debug(f"    - numero_premier_ticket: {getattr(hist, 'numero_premier_ticket', None)}")
    logger.debug(f"    - numero_dernier_ticket: {getattr(hist, 'numero_dernier_ticket', None)}")
    
    # =====================================================================
    # SOURCE 1: Champs structurés directs (PRIORITÉ MAXIMALE)
    # Ces champs sont remplis au moment de la création et ne changent pas
    # =====================================================================
    if (hasattr(hist, 'couleur_principale') and hist.couleur_principale and 
        hasattr(hist, 'numero_premier_ticket') and hist.numero_premier_ticket and 
        hasattr(hist, 'numero_dernier_ticket') and hist.numero_dernier_ticket):
        
        nb_tickets = hist.numero_dernier_ticket - hist.numero_premier_ticket + 1
        series.append({
            'couleur': hist.couleur_principale,
            'couleur_nom': hist.couleur_principale.libelle_affichage,
            'numero_premier': hist.numero_premier_ticket,
            'numero_dernier': hist.numero_dernier_ticket,
            'nombre_tickets': nb_tickets,
            'valeur': Decimal(nb_tickets) * Decimal('500')
        })
        logger.debug(f"    ✓ Source 1 (champs structurés): {hist.couleur_principale.libelle_affichage} "
                    f"#{hist.numero_premier_ticket}-{hist.numero_dernier_ticket}")
        return series
    
    # =====================================================================
    # SOURCE 2: JSONField details_approvisionnement
    # Snapshot des données au moment de l'opération - immuable
    # =====================================================================
    if (hasattr(hist, 'details_approvisionnement') and 
        hist.details_approvisionnement and 
        isinstance(hist.details_approvisionnement, dict)):
        
        series_data = hist.details_approvisionnement.get('series', [])
        
        for serie_data in series_data:
            couleur = None
            couleur_nom = serie_data.get('couleur_nom', 'Inconnu')
            
            # Essayer de récupérer l'objet couleur
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
            logger.debug(f"    ✓ Source 2 (JSON): {len(series)} série(s) trouvée(s)")
            return series
    
    # =====================================================================
    # SOURCE 3: Parser le commentaire (AVANT ManyToMany - CORRECTION MAJEURE!)
    # Le commentaire est IMMUABLE et contient les numéros ORIGINAUX
    # =====================================================================
    if hasattr(hist, 'commentaire') and hist.commentaire and '#' in hist.commentaire:
        # Patterns pour extraire les infos du commentaire
        # Exemples: "Série Rouge #123453648-123554099" ou "Bleu #100-200"
        patterns = [
            # Pattern 1: "Série Couleur #premier-dernier"
            r"(?:Série\s+)?(\w+(?:\s+\w+)?)\s*#(\d+)[–\-](\d+)",
            # Pattern 2: "Couleur #premier-dernier" (sans "Série")
            r"(\w+)\s*#(\d+)[–\-](\d+)",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, hist.commentaire)
            if matches:
                for match in matches:
                    couleur_nom = match[0].strip()
                    num_premier = int(match[1])
                    num_dernier = int(match[2])
                    
                    # Essayer de trouver la couleur correspondante
                    couleur = CouleurTicket.objects.filter(
                        libelle_affichage__icontains=couleur_nom
                    ).first()
                    
                    if not couleur:
                        # Essayer avec le code normalisé
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
                    logger.debug(f"    ✓ Source 3 (commentaire parsé): {len(series)} série(s)")
                    return series
    
    # =====================================================================
    # SOURCE 4: ManyToMany series_tickets_associees (DERNIER RECOURS)
    # ⚠️ ATTENTION: Les séries peuvent avoir été MODIFIÉES depuis le chargement!
    # (découpées par des ventes, transferts, etc.)
    # =====================================================================
    if hasattr(hist, 'series_tickets_associees'):
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
            logger.warning(f"    ⚠ Source 4 (ManyToMany): {len(series)} série(s) - "
                          f"Attention: données potentiellement modifiées depuis le chargement!")
            return series
    
    logger.warning(f"    ✗ Aucune série trouvée pour historique {hist.id}")
    return series


def calculer_donnees_compte_emploi_v2(poste, date_debut, date_fin):
    """
    VERSION CORRIGÉE - Calcul des données du compte d'emploi
    
    AMÉLIORATIONS:
    - Les ventes incluent maintenant la date individuelle de chaque opération
    - Les ventes sont triées chronologiquement au sein de chaque semaine
    - Les ventes sont récupérées via HistoriqueStock (source fiable)
    """
    from collections import defaultdict
    from django.db.models import Sum
    from decimal import Decimal
    from datetime import timedelta
    import logging
    
    # Imports des modèles
    try:
        from inventaire.models import (
            SerieTicket, StockEvent, HistoriqueStock, CouleurTicket
        )
    except ImportError:
        from .models import SerieTicket, StockEvent, HistoriqueStock, CouleurTicket
    
    logger = logging.getLogger('supper')
    
    logger.info(f"=" * 60)
    logger.info(f"CALCUL COMPTE D'EMPLOI V2 CORRIGÉ - {poste.nom}")
    logger.info(f"Période: {date_debut} → {date_fin}")
    
    # Initialiser la structure de données
    donnees = {
        # Ligne Stock de début
        'stock_debut': {
            'stocks': Decimal('0'),
            'ventes': Decimal('0'),
            'stock_final': Decimal('0'),
            'stocks_qte': 0,
            'ventes_qte': 0,
        },
        
        # Ligne Approvisionnement Imprimerie Nationale
        'approv_imprimerie': {
            'stocks': Decimal('0'),
            'ventes': Decimal('0'),
            'stock_final': Decimal('0'),
            'stocks_qte': 0,
            'ventes_qte': 0,
            'details': [],
        },
        
        # Ligne Réapprovisionnement Reçu (transferts entrants)
        'reapprov_recu': {
            'stocks': Decimal('0'),
            'ventes': Decimal('0'),
            'stock_final': Decimal('0'),
            'stocks_qte': 0,
            'ventes_qte': 0,
            'details': [],
        },
        
        # Ligne Réapprovisionnement Cédé (transferts sortants)
        'reapprov_cede': {
            'stocks': Decimal('0'),
            'ventes': Decimal('0'),
            'stock_final': Decimal('0'),
            'stocks_qte': 0,
            'ventes_qte': 0,
            'details': [],
        },
        
        # Totaux
        'total': {
            'stocks': Decimal('0'),
            'ventes': Decimal('0'),
            'stock_final': Decimal('0'),
        },
        
        # Ventes par semaine personnalisée
        'ventes_par_semaine': {},
        
        # Stock final calculé
        'stock_final_calcule': Decimal('0'),
        'stock_final_qte': 0,
    }
    
    # ========== 1. STOCK DE DÉBUT (veille de date_debut) ==========
    
    veille_debut = date_debut - timedelta(days=1)
    stock_debut_valeur, stock_debut_qte = calculer_stock_event_sourcing(poste, veille_debut)
    
    donnees['stock_debut']['stocks'] = stock_debut_valeur
    donnees['stock_debut']['stocks_qte'] = stock_debut_qte
    
    logger.info(f"Stock de début (au {veille_debut}): {stock_debut_valeur} FCFA ({stock_debut_qte} tickets)")
    
    # ========== 2. APPROVISIONNEMENTS IMPRIMERIE NATIONALE ==========
    
    historiques_imprimerie = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='CREDIT',
        type_stock__in=['imprimerie_nationale', 'imprimerie'],
        date_mouvement__date__gte=date_debut,
        date_mouvement__date__lte=date_fin
    ).select_related(
        'couleur_principale', 'effectue_par'
    ).prefetch_related(
        'series_tickets_associees',
        'series_tickets_associees__couleur'
    ).order_by('date_mouvement')
    
    for hist in historiques_imprimerie:
        montant = hist.montant or Decimal('0')
        nb_tickets = hist.nombre_tickets or 0
        
        donnees['approv_imprimerie']['stocks'] += montant
        donnees['approv_imprimerie']['stocks_qte'] += nb_tickets
        
        series = extraire_series_depuis_historique(hist)
        
        if series:
            observation_parts = []
            for s in series:
                observation_parts.append(
                    f"{s['couleur_nom']} #{s['numero_premier']}-{s['numero_dernier']}"
                )
            observation = ", ".join(observation_parts)
        else:
            observation = hist.commentaire or f"{nb_tickets} tickets"
        
        donnees['approv_imprimerie']['details'].append({
            'date': hist.date_mouvement,
            'observation': observation,
            'montant': montant,
            'nombre_tickets': nb_tickets,
            'series': series,
            'historique_id': hist.id
        })
    
    logger.info(f"Approv Imprimerie: {donnees['approv_imprimerie']['stocks']} FCFA")
    
    # ========== 3. TRANSFERTS REÇUS (Réapprovisionnement reçu) ==========
    
    historiques_recus = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='CREDIT',
        poste_origine__isnull=False,
        date_mouvement__date__gte=date_debut,
        date_mouvement__date__lte=date_fin
    ).select_related(
        'poste_origine', 'couleur_principale', 'effectue_par'
    ).prefetch_related(
        'series_tickets_associees',
        'series_tickets_associees__couleur'
    ).order_by('date_mouvement')
    
    for hist in historiques_recus:
        montant = hist.montant or Decimal('0')
        nb_tickets = hist.nombre_tickets or 0
        
        donnees['reapprov_recu']['stocks'] += montant
        donnees['reapprov_recu']['stocks_qte'] += nb_tickets
        
        series = extraire_series_depuis_historique(hist)
        
        if series:
            observation_parts = []
            for s in series:
                observation_parts.append(
                    f"{s['couleur_nom']} #{s['numero_premier']}-{s['numero_dernier']}"
                )
            observation = f"Reçu de {hist.poste_origine.nom}: " + ", ".join(observation_parts)
        else:
            observation = f"Reçu de {hist.poste_origine.nom}: {hist.commentaire or f'{nb_tickets} tickets'}"
        
        donnees['reapprov_recu']['details'].append({
            'date': hist.date_mouvement,
            'observation': observation,
            'montant': montant,
            'nombre_tickets': nb_tickets,
            'poste_origine': hist.poste_origine,
            'numero_bordereau': hist.numero_bordereau,
            'series': series,
            'historique_id': hist.id
        })
    
    logger.info(f"Transferts reçus: {donnees['reapprov_recu']['stocks']} FCFA")
    
    # ========== 4. TRANSFERTS CÉDÉS (Réapprovisionnement cédé) ==========
    
    historiques_cedes = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='DEBIT',
        poste_destination__isnull=False,
        date_mouvement__date__gte=date_debut,
        date_mouvement__date__lte=date_fin
    ).select_related(
        'poste_destination', 'couleur_principale', 'effectue_par'
    ).prefetch_related(
        'series_tickets_associees',
        'series_tickets_associees__couleur'
    ).order_by('date_mouvement')
    
    for hist in historiques_cedes:
        montant = hist.montant or Decimal('0')
        nb_tickets = hist.nombre_tickets or 0
        
        donnees['reapprov_cede']['stocks'] -= montant
        donnees['reapprov_cede']['stocks_qte'] -= nb_tickets
        
        series = extraire_series_depuis_historique(hist)
        
        if series:
            observation_parts = []
            for s in series:
                observation_parts.append(
                    f"{s['couleur_nom']} #{s['numero_premier']}-{s['numero_dernier']}"
                )
            observation = f"Cédé à {hist.poste_destination.nom}: " + ", ".join(observation_parts)
        else:
            observation = f"Cédé à {hist.poste_destination.nom}: {hist.commentaire or f'{nb_tickets} tickets'}"
        
        donnees['reapprov_cede']['details'].append({
            'date': hist.date_mouvement,
            'observation': observation,
            'montant': -montant,
            'nombre_tickets': -nb_tickets,
            'poste_destination': hist.poste_destination,
            'numero_bordereau': hist.numero_bordereau,
            'series': series,
            'historique_id': hist.id
        })
    
    logger.info(f"Transferts cédés: {donnees['reapprov_cede']['stocks']} FCFA")
    
    # ========== 5. VENTES - Via HistoriqueStock ==========
    
    logger.info(f"=" * 40)
    logger.info(f"RÉCUPÉRATION DES VENTES (via HistoriqueStock)")
    
    # Récupérer les ventes via HistoriqueStock
    historiques_ventes = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='DEBIT',
        reference_recette__isnull=False,
        poste_destination__isnull=True,
        date_mouvement__date__gte=date_debut,
        date_mouvement__date__lte=date_fin
    ).select_related(
        'reference_recette', 'couleur_principale', 'effectue_par'
    ).prefetch_related(
        'series_tickets_associees',
        'series_tickets_associees__couleur'
    ).order_by('date_mouvement')
    
    logger.info(f"  Nombre d'historiques de vente trouvés: {historiques_ventes.count()}")
    
    total_ventes_valeur = Decimal('0')
    total_ventes_qte = 0
    
    # Structure pour les ventes par semaine personnalisée
    ventes_par_semaine = {}
    
    for hist in historiques_ventes:
        montant = hist.montant or Decimal('0')
        nb_tickets = hist.nombre_tickets or 0
        
        total_ventes_valeur += montant
        total_ventes_qte += nb_tickets
        
        # Déterminer la date de la vente
        if hist.date_mouvement:
            if hasattr(hist.date_mouvement, 'date'):
                event_date = hist.date_mouvement.date()
            else:
                event_date = hist.date_mouvement
        elif hist.reference_recette:
            event_date = hist.reference_recette.date
        else:
            event_date = date_debut
        
        # Déterminer la semaine personnalisée
        jours_depuis_debut = (event_date - date_debut).days
        numero_semaine = max(0, jours_depuis_debut // 7)
        
        semaine_debut = date_debut + timedelta(days=numero_semaine * 7)
        semaine_fin_theorique = semaine_debut + timedelta(days=6)
        semaine_fin = min(semaine_fin_theorique, date_fin)
        
        semaine_key = f"{semaine_debut.strftime('%d/%m')} au {semaine_fin.strftime('%d/%m/%Y')}"
        
        if semaine_key not in ventes_par_semaine:
            ventes_par_semaine[semaine_key] = {
                'date_debut': semaine_debut,
                'date_fin': semaine_fin,
                'total_valeur': Decimal('0'),
                'total_tickets': 0,
                'series_vendues': [],
                'historiques': []
            }
        
        ventes_par_semaine[semaine_key]['total_valeur'] += montant
        ventes_par_semaine[semaine_key]['total_tickets'] += nb_tickets
        ventes_par_semaine[semaine_key]['historiques'].append(hist)
        
        # Extraire les séries vendues avec la DATE
        series = extraire_series_depuis_historique(hist)
        for s in series:
            # ============================================
            # AJOUT DE LA DATE À CHAQUE SÉRIE VENDUE
            # ============================================
            s['date_vente'] = event_date
            s['historique_id'] = hist.id
            # Référence de la recette si disponible
            if hist.reference_recette:
                s['reference_recette'] = str(hist.reference_recette)
            ventes_par_semaine[semaine_key]['series_vendues'].append(s)
    
    logger.info(f"  Total ventes via HistoriqueStock: {total_ventes_valeur} FCFA ({total_ventes_qte} tickets)")
    
    # ========== FALLBACK: StockEvent si aucune vente trouvée ==========
    
    if total_ventes_valeur == 0:
        logger.info(f"  → Tentative fallback via StockEvent...")
        
        events_ventes = StockEvent.objects.filter(
            poste=poste,
            event_type='VENTE',
            event_datetime__date__gte=date_debut,
            event_datetime__date__lte=date_fin,
            is_cancelled=False
        ).order_by('event_datetime')
        
        for event in events_ventes:
            montant = abs(event.montant_variation)
            nb_tickets = abs(event.nombre_tickets_variation)
            
            total_ventes_valeur += montant
            total_ventes_qte += nb_tickets
            
            event_date = event.event_datetime.date()
            jours_depuis_debut = (event_date - date_debut).days
            numero_semaine = max(0, jours_depuis_debut // 7)
            
            semaine_debut = date_debut + timedelta(days=numero_semaine * 7)
            semaine_fin_theorique = semaine_debut + timedelta(days=6)
            semaine_fin = min(semaine_fin_theorique, date_fin)
            
            semaine_key = f"{semaine_debut.strftime('%d/%m')} au {semaine_fin.strftime('%d/%m/%Y')}"
            
            if semaine_key not in ventes_par_semaine:
                ventes_par_semaine[semaine_key] = {
                    'date_debut': semaine_debut,
                    'date_fin': semaine_fin,
                    'total_valeur': Decimal('0'),
                    'total_tickets': 0,
                    'series_vendues': [],
                    'events': []
                }
            
            ventes_par_semaine[semaine_key]['total_valeur'] += montant
            ventes_par_semaine[semaine_key]['total_tickets'] += nb_tickets
    
    # ========== Enrichir les semaines sans séries via SerieTicket ==========
    
    for semaine_key, semaine_data in ventes_par_semaine.items():
        if not semaine_data['series_vendues']:
            series_vendues = SerieTicket.objects.filter(
                poste=poste,
                statut__in=['vendu', 'epuise'],
                date_utilisation__gte=semaine_data['date_debut'],
                date_utilisation__lte=semaine_data['date_fin']
            ).select_related('couleur').order_by('date_utilisation', 'couleur__code_normalise', 'numero_premier')
            
            for serie in series_vendues:
                semaine_data['series_vendues'].append({
                    'couleur': serie.couleur,
                    'couleur_nom': serie.couleur.libelle_affichage if serie.couleur else 'Inconnu',
                    'numero_premier': serie.numero_premier,
                    'numero_dernier': serie.numero_dernier,
                    'nombre_tickets': serie.nombre_tickets,
                    'valeur': serie.valeur_monetaire,
                    'date_vente': serie.date_utilisation,  # Date de la vente
                })
        
        # ============================================
        # TRIER LES SÉRIES PAR DATE DE VENTE
        # ============================================
        semaine_data['series_vendues'].sort(
            key=lambda x: (x.get('date_vente') or date_debut, x.get('couleur_nom', ''))
        )
    
    donnees['ventes_par_semaine'] = ventes_par_semaine
    
    logger.info(f"Total ventes FINAL: {total_ventes_valeur} FCFA ({total_ventes_qte} tickets)")
    
    # ========== 6. RÉPARTITION DES VENTES PAR CATÉGORIE ==========
    
    total_entrees = (
        donnees['stock_debut']['stocks'] +
        donnees['approv_imprimerie']['stocks'] +
        donnees['reapprov_recu']['stocks']
    )
    
    if total_entrees > 0:
        ratio_stock_debut = donnees['stock_debut']['stocks'] / total_entrees
        ratio_approv = donnees['approv_imprimerie']['stocks'] / total_entrees
        ratio_recu = donnees['reapprov_recu']['stocks'] / total_entrees
        
        donnees['stock_debut']['ventes'] = total_ventes_valeur * ratio_stock_debut
        donnees['stock_debut']['ventes_qte'] = int(total_ventes_qte * float(ratio_stock_debut))
        
        donnees['approv_imprimerie']['ventes'] = total_ventes_valeur * ratio_approv
        donnees['approv_imprimerie']['ventes_qte'] = int(total_ventes_qte * float(ratio_approv))
        
        donnees['reapprov_recu']['ventes'] = total_ventes_valeur * ratio_recu
        donnees['reapprov_recu']['ventes_qte'] = int(total_ventes_qte * float(ratio_recu))
    
    donnees['reapprov_cede']['ventes'] = Decimal('0')
    donnees['reapprov_cede']['ventes_qte'] = 0
    
    # ========== 7. CALCUL DES STOCKS FINAUX PAR LIGNE ==========
    
    donnees['stock_debut']['stock_final'] = (
        donnees['stock_debut']['stocks'] - donnees['stock_debut']['ventes']
    )
    
    donnees['approv_imprimerie']['stock_final'] = (
        donnees['approv_imprimerie']['stocks'] - donnees['approv_imprimerie']['ventes']
    )
    
    donnees['reapprov_recu']['stock_final'] = (
        donnees['reapprov_recu']['stocks'] - donnees['reapprov_recu']['ventes']
    )
    
    donnees['reapprov_cede']['stock_final'] = donnees['reapprov_cede']['stocks']
    
    # ========== 8. CALCUL DES TOTAUX ==========
    
    donnees['total']['stocks'] = (
        donnees['stock_debut']['stocks'] +
        donnees['approv_imprimerie']['stocks'] +
        donnees['reapprov_recu']['stocks'] +
        donnees['reapprov_cede']['stocks']
    )
    
    donnees['total']['ventes'] = total_ventes_valeur
    
    donnees['total']['stock_final'] = (
        donnees['stock_debut']['stock_final'] +
        donnees['approv_imprimerie']['stock_final'] +
        donnees['reapprov_recu']['stock_final'] +
        donnees['reapprov_cede']['stock_final']
    )
    
    # Stock final via Event Sourcing pour vérification
    stock_fin_valeur, stock_fin_qte = calculer_stock_event_sourcing(poste, date_fin)
    donnees['stock_final_calcule'] = stock_fin_valeur
    donnees['stock_final_qte'] = stock_fin_qte
    
    # Vérification cohérence
    ecart = abs(donnees['total']['stock_final'] - stock_fin_valeur)
    if ecart > Decimal('1000'):
        logger.warning(
            f"Écart détecté: Calcul tableau={donnees['total']['stock_final']}, "
            f"Event Sourcing={stock_fin_valeur}, Écart={ecart}"
        )
    
    logger.info(f"=" * 60)
    logger.info(f"RÉSUMÉ COMPTE D'EMPLOI:")
    logger.info(f"  Stock début: {donnees['stock_debut']['stocks']}")
    logger.info(f"  Approv IMP: {donnees['approv_imprimerie']['stocks']}")
    logger.info(f"  Reçu: {donnees['reapprov_recu']['stocks']}")
    logger.info(f"  Cédé: {donnees['reapprov_cede']['stocks']}")
    logger.info(f"  Ventes: {donnees['total']['ventes']}")
    logger.info(f"  Stock final: {donnees['total']['stock_final']}")
    logger.info(f"=" * 60)
    
    return donnees

# ===================================================================
# APERÇU HTML DU COMPTE D'EMPLOI
# ===================================================================

@login_required
def apercu_compte_emploi(request, poste_id, date_debut, date_fin):
    """
    Vue pour afficher un aperçu du compte d'emploi avant génération du PDF
    """
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Vérifier les permissions
    if not request.user.is_admin:
        if not request.user.poste_affectation or request.user.poste_affectation != poste:
            messages.error(request, "Accès non autorisé")
            return redirect('inventaire:selection_compte_emploi')
    
    # Parser les dates
    try:
        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
    except:
        messages.error(request, "Format de dates invalide")
        return redirect('inventaire:selection_compte_emploi')
    
    nombre_jours = (date_fin_obj - date_debut_obj).days + 1
    
    # Calculer les données avec la nouvelle fonction
    donnees = calculer_donnees_compte_emploi_v2(poste, date_debut_obj, date_fin_obj)
    
    # Vérifier la cohérence
    coherence_ok = abs(donnees['total']['stock_final'] - donnees['stock_final_calcule']) < 1000
    
    if not coherence_ok:
        messages.warning(
            request,
            f"⚠️ Écart détecté dans le calcul. "
            f"Stock final tableau: {donnees['total']['stock_final']:,.0f} FCFA, "
            f"Stock final calculé: {donnees['stock_final_calcule']:,.0f} FCFA"
        )
    
    context = {
        'poste': poste,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'date_debut_obj': date_debut_obj,
        'date_fin_obj': date_fin_obj,
        'nombre_jours': nombre_jours,
        'donnees': donnees,
        'coherence_ok': coherence_ok,
        'title': f"Compte d'Emploi - {poste.nom}"
    }
    
    return render(request, 'inventaire/compte_emploi_v2.html', context)


# ===================================================================
# GÉNÉRATION PDF DU COMPTE D'EMPLOI
# ===================================================================

def creer_entete_bilingue(config, poste):
    """Crée l'en-tête bilingue du document"""
    styles = getSampleStyleSheet()
    
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_CENTER,
        leading=10
    )
    
    col_gauche = [
        Paragraph(f"<b>{config.republique_fr}</b>", header_style),
        Paragraph(config.devise_fr, header_style),
        Paragraph("*****", header_style),
        Paragraph(f"<b>{config.ministere_fr}</b>", header_style),
        Paragraph("*****", header_style),
        Paragraph(f"<b>{config.direction_fr}</b>", header_style),
        Paragraph("**********", header_style),
        Paragraph(f"<b>{config.programme_fr}</b>", header_style),
        Paragraph("*********", header_style),
        Paragraph(f"<b>POSTE DE {poste.nom.upper()}</b>", header_style),
        Paragraph("*********", header_style)
    ]
    
    logo_cell = ""
    if config.logo:
        try:
            logo_path = os.path.join(settings.MEDIA_ROOT, config.logo.name)
            if os.path.exists(logo_path):
                logo_cell = Image(logo_path, width=3*cm, height=3*cm)
        except:
            pass
    
    col_droite = [
        Paragraph(f"<b>{config.republique_en}</b>", header_style),
        Paragraph(config.devise_en, header_style),
        Paragraph("*****", header_style),
        Paragraph(f"<b>{config.ministere_en}</b>", header_style),
        Paragraph("*****", header_style),
        Paragraph(f"<b>{config.direction_en}</b>", header_style),
        Paragraph("**********", header_style),
        Paragraph(f"<b>{config.programme_en}</b>", header_style),
        Paragraph("*********", header_style),
        Paragraph(f"<b>POST OF {poste.nom.upper()}</b>", header_style),
        Paragraph("*********", header_style)
    ]
    
    if logo_cell:
        header_data = [[col_gauche, logo_cell, col_droite]]
    else:
        header_data = [[col_gauche, "DGI", col_droite]]
    
    header_table = Table(header_data, colWidths=[8*cm, 4*cm, 8*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
    ]))
    
    return header_table


def creer_tableau_principal(donnees, date_debut, date_fin, styles):
    """
    Crée le tableau principal du compte d'emploi
    Format: Période | Stocks | Ventes | Stock Final
    """
    periode_str = f"{date_debut.strftime('%d/%m/%Y')} - {date_fin.strftime('%d/%m/%Y')}"
    
    # Fonction pour formater les montants
    def fmt_montant(val):
        if val == 0 or val == Decimal('0'):
            return "-"
        return f"{val:,.0f}".replace(',', ' ')
    
    table_data = [
        # En-tête
        [
            Paragraph(f"<b>Période: {periode_str}</b>", styles['Normal']),
            Paragraph("<b>Stocks</b>", styles['Normal']),
            Paragraph("<b>Ventes</b>", styles['Normal']),
            Paragraph("<b>Stock Final</b>", styles['Normal'])
        ],
        # Stock de début
        [
            "Stock de début",
            fmt_montant(donnees['stock_debut']['stocks']),
            fmt_montant(donnees['stock_debut']['ventes']),
            fmt_montant(donnees['stock_debut']['stock_final'])
        ],
        # Approvisionnement Imprimerie
        [
            "Approv. (Imprimerie Nationale)",
            fmt_montant(donnees['approv_imprimerie']['stocks']),
            fmt_montant(donnees['approv_imprimerie']['ventes']),
            fmt_montant(donnees['approv_imprimerie']['stock_final'])
        ],
        # Réapprovisionnement Reçu
        [
            "Réapprov. reçu",
            fmt_montant(donnees['reapprov_recu']['stocks']),
            fmt_montant(donnees['reapprov_recu']['ventes']),
            fmt_montant(donnees['reapprov_recu']['stock_final'])
        ],
        # Réapprovisionnement Cédé
        [
            "Réapprov. cédé",
            fmt_montant(donnees['reapprov_cede']['stocks']),
            "/",  # Pas de ventes pour les cessions
            fmt_montant(donnees['reapprov_cede']['stock_final'])
        ],
        # Total
        [
            Paragraph("<b>TOTAL</b>", styles['Normal']),
            Paragraph(f"<b>{fmt_montant(donnees['total']['stocks'])}</b>", styles['Normal']),
            Paragraph(f"<b>{fmt_montant(donnees['total']['ventes'])}</b>", styles['Normal']),
            Paragraph(f"<b>{fmt_montant(donnees['total']['stock_final'])}</b>", styles['Normal'])
        ]
    ]
    
    col_widths = [6*cm, 4*cm, 4*cm, 4*cm]
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # En-tête
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        
        # Corps
        ('FONTSIZE', (0, 1), (-1, -2), 9),
        ('BACKGROUND', (0, 1), (-1, -2), colors.whitesmoke),
        
        # Ligne Total
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e2e8f0')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        
        # Alignement
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Bordures
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        
        # Padding
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    return table


def creer_section_details_approvisionnement(donnees, styles, titre="DÉTAILS DES APPROVISIONNEMENTS - IMPRIMERIE NATIONALE"):
    """
    Crée la section des détails d'approvisionnement
    Format: Date | Observation (couleur, numéros de série) | Montant
    """
    elements = []
    
    # Titre
    titre_style = ParagraphStyle(
        'TitreSection',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=colors.HexColor('#2d3748'),
        spaceAfter=10,
        spaceBefore=15
    )
    elements.append(Paragraph(titre, titre_style))
    
    details = donnees['approv_imprimerie']['details']
    
    if not details:
        elements.append(Paragraph("<i>Aucun approvisionnement sur cette période</i>", styles['Normal']))
        return elements
    
    table_data = [
        ['Date', 'Observation (Couleur, Séries)', 'Montant (FCFA)']
    ]
    
    for detail in details:
        date_str = detail['date'].strftime('%d/%m/%Y') if detail['date'] else '-'
        observation = detail['observation'][:80] + "..." if len(detail['observation']) > 80 else detail['observation']
        montant = f"{detail['montant']:,.0f}".replace(',', ' ')
        
        table_data.append([date_str, observation, montant])
    
    table = Table(table_data, colWidths=[2.5*cm, 11*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3182ce')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    
    elements.append(table)
    return elements


def creer_section_transferts_recus(donnees, styles):
    """Crée la section des transferts reçus"""
    elements = []
    
    titre_style = ParagraphStyle(
        'TitreSection',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=colors.HexColor('#38a169'),
        spaceAfter=10,
        spaceBefore=15
    )
    elements.append(Paragraph("DÉTAILS DES TRANSFERTS REÇUS", titre_style))
    
    details = donnees['reapprov_recu']['details']
    
    if not details:
        elements.append(Paragraph("<i>Aucun transfert reçu sur cette période</i>", styles['Normal']))
        return elements
    
    table_data = [
        ['Date', 'Observation (Origine, Séries)', 'Montant (FCFA)']
    ]
    
    for detail in details:
        date_str = detail['date'].strftime('%d/%m/%Y') if detail['date'] else '-'
        observation = detail['observation'][:80] + "..." if len(detail['observation']) > 80 else detail['observation']
        montant = f"{detail['montant']:,.0f}".replace(',', ' ')
        
        table_data.append([date_str, observation, montant])
    
    table = Table(table_data, colWidths=[2.5*cm, 11*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#38a169')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    
    elements.append(table)
    return elements


def creer_section_transferts_cedes(donnees, styles):
    """Crée la section des transferts cédés"""
    elements = []
    
    titre_style = ParagraphStyle(
        'TitreSection',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=colors.HexColor('#e53e3e'),
        spaceAfter=10,
        spaceBefore=15
    )
    elements.append(Paragraph("DÉTAILS DES TRANSFERTS CÉDÉS", titre_style))
    
    details = donnees['reapprov_cede']['details']
    
    if not details:
        elements.append(Paragraph("<i>Aucun transfert cédé sur cette période</i>", styles['Normal']))
        return elements
    
    table_data = [
        ['Date', 'Observation (Destination, Séries)', 'Montant (FCFA)']
    ]
    
    for detail in details:
        date_str = detail['date'].strftime('%d/%m/%Y') if detail['date'] else '-'
        observation = detail['observation'][:80] + "..." if len(detail['observation']) > 80 else detail['observation']
        montant = f"{abs(detail['montant']):,.0f}".replace(',', ' ')  # Valeur absolue pour affichage
        
        table_data.append([date_str, observation, f"-{montant}"])
    
    table = Table(table_data, colWidths=[2.5*cm, 11*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e53e3e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#e53e3e')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    
    elements.append(table)
    return elements


def creer_section_ventes_par_semaine(donnees, styles):
    """
    Crée la section des ventes par semaine personnalisée
    Affiche les séries vendues par semaine
    """
    elements = []
    
    titre_style = ParagraphStyle(
        'TitreSection',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=colors.HexColor('#dd6b20'),
        spaceAfter=10,
        spaceBefore=15
    )
    elements.append(Paragraph("DÉTAILS DES VENTES PAR SEMAINE", titre_style))
    
    ventes_par_semaine = donnees['ventes_par_semaine']
    
    if not ventes_par_semaine:
        elements.append(Paragraph("<i>Aucune vente sur cette période</i>", styles['Normal']))
        return elements
    
    # Trier les semaines chronologiquement
    semaines_triees = sorted(
        ventes_par_semaine.items(),
        key=lambda x: x[1]['date_debut']
    )
    
    for semaine_key, semaine_data in semaines_triees:
        # En-tête de semaine
        semaine_header = Paragraph(
            f"<b>SEMAINE DU {semaine_key}</b>",
            ParagraphStyle(
                'SemaineHeader',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.whitesmoke,
                alignment=TA_CENTER
            )
        )
        
        table_data = [[semaine_header, '', '']]
        
        # Regrouper les séries par couleur
        series_par_couleur = {}
        for serie in semaine_data['series_vendues']:
            couleur_nom = serie.get('couleur_nom', 'Inconnu')
            if couleur_nom not in series_par_couleur:
                series_par_couleur[couleur_nom] = {
                    'series': [],
                    'total_tickets': 0,
                    'total_valeur': Decimal('0')
                }
            series_par_couleur[couleur_nom]['series'].append(serie)
            series_par_couleur[couleur_nom]['total_tickets'] += serie.get('nombre_tickets', 0)
            series_par_couleur[couleur_nom]['total_valeur'] += serie.get('valeur', Decimal('0'))
        
        # Afficher par couleur
        for couleur_nom, couleur_data in series_par_couleur.items():
            # Construire la liste des séries
            series_str_list = []
            for s in couleur_data['series'][:5]:  # Limiter à 5 séries par couleur
                series_str_list.append(f"#{s['numero_premier']}-{s['numero_dernier']}")
            
            if len(couleur_data['series']) > 5:
                series_str_list.append(f"... (+{len(couleur_data['series']) - 5})")
            
            series_str = ", ".join(series_str_list)
            
            table_data.append([
                f"{couleur_nom}",
                f"{series_str}",
                f"{couleur_data['total_valeur']:,.0f} FCFA".replace(',', ' ')
            ])
        
        # Ligne total semaine
        table_data.append([
            Paragraph("<b>Total semaine</b>", styles['Normal']),
            f"{semaine_data['total_tickets']} tickets",
            f"{semaine_data['total_valeur']:,.0f} FCFA".replace(',', ' ')
        ])
        
        table = Table(table_data, colWidths=[4*cm, 8*cm, 3.5*cm])
        table.setStyle(TableStyle([
            # En-tête semaine
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dd6b20')),
            ('SPAN', (0, 0), (-1, 0)),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            
            # Corps
            ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#fef3e2')),
            ('FONTSIZE', (0, 1), (-1, -2), 7),
            
            # Total
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fed7aa')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 8),
            
            # Alignement
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Bordures
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dd6b20')),
            
            # Padding
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 0.3*cm))
    
    return elements


def creer_pied_page(poste, config, user):
    """Crée le pied de page avec signature et horodatage"""
    styles = getSampleStyleSheet()
    
    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_CENTER
    )
    
    date_impression = datetime.now().strftime("%d/%m/%Y à %H:%M")
    
    footer_data = [
        [Paragraph(f"le {date_impression}", footer_style)],
        [Spacer(1, 0.3*cm)],
        [Paragraph("<b>LE CHEF DE POSTE</b>", footer_style)],
        [Spacer(1, 1*cm)],
        [Paragraph("_________________________", footer_style)],
        [Spacer(1, 0.3*cm)],
        [Paragraph(
            f"<i>Document généré par SUPPER - Utilisateur: {user.nom_complet}</i>", 
            ParagraphStyle('FooterItalic', parent=footer_style, fontSize=7, textColor=colors.grey)
        )]
    ]
    
    footer_table = Table(footer_data, colWidths=[20*cm])
    
    return footer_table


@login_required
def generer_compte_emploi_pdf(request, poste_id, date_debut, date_fin):
    """
    Génère le PDF du compte d'emploi avec le nouveau format
    """
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Vérifier les permissions
    if not request.user.is_admin:
        if not request.user.poste_affectation or request.user.poste_affectation != poste:
            messages.error(request, "Accès non autorisé")
            return redirect('inventaire:selection_compte_emploi')
    
    # Parser les dates
    try:
        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
    except:
        messages.error(request, "Format de dates invalide")
        return redirect('inventaire:selection_compte_emploi')
    
    # Récupérer config
    config = ConfigurationGlobale.get_config()
    
    # Calcul des données
    donnees = calculer_donnees_compte_emploi_v2(poste, date_debut_obj, date_fin_obj)
    
    # Générer PDF
    response = HttpResponse(content_type='application/pdf')
    filename = f'compte_emploi_{poste.code}_{date_debut}_au_{date_fin}.pdf'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    
    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(A4),
        rightMargin=1*cm,
        leftMargin=1*cm,
        topMargin=1*cm,
        bottomMargin=1*cm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # En-tête bilingue
    elements.append(creer_entete_bilingue(config, poste))
    elements.append(Spacer(1, 0.5*cm))
    
    # Titre
    titre_style = ParagraphStyle(
        'TitreCompte',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=colors.HexColor('#1a1a1a'),
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    titre = Paragraph(
        f"COMPTE D'EMPLOI DES TICKETS<br/>"
        f"Période du {date_debut_obj.strftime('%d/%m/%Y')} au {date_fin_obj.strftime('%d/%m/%Y')}",
        titre_style
    )
    elements.append(titre)
    elements.append(Spacer(1, 0.5*cm))
    
    # Tableau principal (nouveau format)
    elements.append(creer_tableau_principal(donnees, date_debut_obj, date_fin_obj, styles))
    elements.append(Spacer(1, 0.5*cm))
    
    # Section Approvisionnements Imprimerie
    elements.extend(creer_section_details_approvisionnement(donnees, styles))
    
    # Section Transferts reçus
    elements.extend(creer_section_transferts_recus(donnees, styles))
    
    # Section Transferts cédés
    elements.extend(creer_section_transferts_cedes(donnees, styles))
    
    # Saut de page si nécessaire
    elements.append(PageBreak())
    
    # Section Ventes par semaine
    elements.extend(creer_section_ventes_par_semaine(donnees, styles))
    
    # Note de vérification
    elements.append(Spacer(1, 0.5*cm))
    
    note_style = ParagraphStyle(
        'Note',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor('#4b5563'),
        alignment=TA_CENTER
    )
    
    ecart = abs(donnees['total']['stock_final'] - donnees['stock_final_calcule'])
    
    if ecart < Decimal('1000'):
        note_text = "✓ Cohérence vérifiée : Stock final tableau = Stock calculé par Event Sourcing"
        note_color = '#10b981'
    else:
        note_text = f"⚠ Écart détecté : {ecart:,.0f} FCFA".replace(',', ' ')
        note_color = '#ef4444'
    
    elements.append(Paragraph(f"<font color='{note_color}'>{note_text}</font>", note_style))
    
    # Pied de page
    elements.append(Spacer(1, 0.5*cm))
    elements.append(creer_pied_page(poste, config, request.user))
    
    # Générer le PDF
    doc.build(elements)
    
    return response


# ===================================================================
# PARAMÉTRAGE GLOBAL
# ===================================================================

@login_required
@user_passes_test(lambda u: u.is_admin)
def parametrage_global(request):
    """Vue de paramétrage global pour tous les postes"""
    
    config = ConfigurationGlobale.get_config()
    
    if request.method == 'POST':
        config.republique_fr = request.POST.get('republique_fr', config.republique_fr)
        config.devise_fr = request.POST.get('devise_fr', config.devise_fr)
        config.ministere_fr = request.POST.get('ministere_fr', config.ministere_fr)
        config.direction_fr = request.POST.get('direction_fr', config.direction_fr)
        config.programme_fr = request.POST.get('programme_fr', config.programme_fr)
        
        config.republique_en = request.POST.get('republique_en', config.republique_en)
        config.devise_en = request.POST.get('devise_en', config.devise_en)
        config.ministere_en = request.POST.get('ministere_en', config.ministere_en)
        config.direction_en = request.POST.get('direction_en', config.direction_en)
        config.programme_en = request.POST.get('programme_en', config.programme_en)
        
        if 'logo' in request.FILES:
            config.logo = request.FILES['logo']
        
        config.save()
        
        messages.success(request, "Configuration globale mise à jour avec succès")
        return redirect('inventaire:parametrage_global')
    
    context = {
        'config': config,
        'title': 'Paramétrage Global des Documents'
    }
    
    return render(request, 'inventaire/parametrage_global.html', context)