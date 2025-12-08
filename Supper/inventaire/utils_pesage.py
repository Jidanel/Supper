# ===================================================================
# inventaire/utils_pesage.py - VERSION CORRIGÉE
# ===================================================================

import re
from django.db.models import Q, Sum, Count
from decimal import Decimal
import logging

logger = logging.getLogger('supper')


def normalize_search_text(text):
    """
    Normalise un texte pour la recherche uniforme.
    """
    if not text:
        return ""
    
    text = str(text).strip()
    text = text.lower()
    text = re.sub(r'\s+', '_', text)
    text = text.strip('_')
    
    return text


def normalize_immatriculation(immat):
    """
    Normalise une immatriculation pour recherche uniforme.
    """
    if not immat:
        return ""
    
    immat = re.sub(r'[\s\-]+', '', str(immat))
    immat = immat.upper()
    
    return immat


def rechercher_historique_vehicule(immatriculation=None, transporteur=None, operateur=None, 
                                    station_exclue=None, limit=100):
    """
    Recherche l'historique des amendes pour un véhicule/transporteur/chauffeur.
    
    IMPORTANT: Cherche sur les champs normalisés ET originaux pour compatibilité
    avec les données existantes qui n'ont pas encore été normalisées.
    """
    from inventaire.models_pesage import AmendeEmise
    
    # Construire les filtres
    filters = Q()
    has_filter = False
    
    # Recherche par immatriculation
    # Chercher sur le champ normalisé ET le champ original
    if immatriculation:
        immat_norm = normalize_immatriculation(immatriculation)
        immat_original = immatriculation.strip()
        
        if immat_norm:
            # Chercher sur les DEUX champs (normalisé OU original)
            immat_filter = (
                Q(immatriculation_normalise__icontains=immat_norm) |
                Q(immatriculation__icontains=immat_original) |
                Q(immatriculation__iexact=immat_norm)
            )
            filters &= immat_filter
            has_filter = True
    
    # Recherche par transporteur
    if transporteur:
        transp_norm = normalize_search_text(transporteur)
        transp_original = transporteur.strip()
        
        if transp_norm or transp_original:
            transp_filter = (
                Q(transporteur_normalise__icontains=transp_norm) |
                Q(transporteur__icontains=transp_original)
            )
            filters &= transp_filter
            has_filter = True
    
    # Recherche par opérateur/chauffeur
    if operateur:
        op_norm = normalize_search_text(operateur)
        op_original = operateur.strip()
        
        if op_norm or op_original:
            op_filter = (
                Q(operateur_normalise__icontains=op_norm) |
                Q(operateur__icontains=op_original)
            )
            filters &= op_filter
            has_filter = True
    
    if not has_filter:
        return AmendeEmise.objects.none()
    
    # Requête de base
    queryset = AmendeEmise.objects.filter(filters)
    
    # Exclure une station si demandé
    if station_exclue:
        queryset = queryset.exclude(station=station_exclue)
    
    # Ordonner par date décroissante (plus récent en premier)
    queryset = queryset.select_related('station', 'saisi_par', 'valide_par')
    queryset = queryset.order_by('-date_heure_emission')
    
    # IMPORTANT: Ne pas faire de slice ici pour permettre la pagination
    # Le limit sera géré par la pagination dans la vue
    return queryset


def rechercher_par_criteres_multiples(criteres, station_exclue=None):
    """
    Recherche avancée avec plusieurs critères combinés (OR).
    Compatible avec données non normalisées.
    """
    from inventaire.models_pesage import AmendeEmise
    
    filters = Q()
    
    # Immatriculation
    if criteres.get('immatriculation'):
        immat = criteres['immatriculation'].strip()
        immat_norm = normalize_immatriculation(immat)
        if immat:
            filters |= Q(immatriculation_normalise__icontains=immat_norm)
            filters |= Q(immatriculation__icontains=immat)
    
    # Transporteur
    if criteres.get('transporteur'):
        transp = criteres['transporteur'].strip()
        transp_norm = normalize_search_text(transp)
        if transp:
            filters |= Q(transporteur_normalise__icontains=transp_norm)
            filters |= Q(transporteur__icontains=transp)
    
    # Opérateur/Chauffeur
    if criteres.get('operateur'):
        op = criteres['operateur'].strip()
        op_norm = normalize_search_text(op)
        if op:
            filters |= Q(operateur_normalise__icontains=op_norm)
            filters |= Q(operateur__icontains=op)
    
    if not filters:
        return AmendeEmise.objects.none()
    
    queryset = AmendeEmise.objects.filter(filters)
    
    if station_exclue:
        queryset = queryset.exclude(station=station_exclue)
    
    return queryset.select_related('station', 'saisi_par', 'valide_par').order_by('-date_heure_emission')


def verifier_amendes_non_payees_autres_stations(immatriculation, station_actuelle):
    """
    Vérifie si un véhicule a des amendes non payées dans d'autres stations.
    Compatible avec données non normalisées.
    """
    from inventaire.models_pesage import AmendeEmise
    
    if not immatriculation:
        return False, AmendeEmise.objects.none()
    
    immat_norm = normalize_immatriculation(immatriculation)
    immat_original = immatriculation.strip()
    
    # Chercher sur les DEUX champs
    amendes_non_payees = AmendeEmise.objects.filter(
        Q(immatriculation_normalise__iexact=immat_norm) |
        Q(immatriculation__iexact=immat_original) |
        Q(immatriculation__iexact=immat_norm),
        statut='non_paye'
    ).exclude(
        station=station_actuelle
    ).select_related('station', 'saisi_par').order_by('-date_heure_emission')
    
    return amendes_non_payees.exists(), amendes_non_payees


def get_resume_historique_vehicule(immatriculation):
    """
    Génère un résumé statistique pour un véhicule.
    Compatible avec données non normalisées.
    """
    from inventaire.models_pesage import AmendeEmise
    
    if not immatriculation:
        return {
            'total_amendes': 0,
            'total_payees': 0,
            'total_non_payees': 0,
            'montant_total': 0,
            'montant_paye': 0,
            'montant_impaye': 0,
            'stations_distinctes': 0,
        }
    
    immat_norm = normalize_immatriculation(immatriculation)
    immat_original = immatriculation.strip()
    
    # Chercher sur les DEUX champs
    amendes_qs = AmendeEmise.objects.filter(
        Q(immatriculation_normalise__iexact=immat_norm) |
        Q(immatriculation__iexact=immat_original) |
        Q(immatriculation__iexact=immat_norm)
    )
    
    if not amendes_qs.exists():
        return {
            'total_amendes': 0,
            'total_payees': 0,
            'total_non_payees': 0,
            'montant_total': 0,
            'montant_paye': 0,
            'montant_impaye': 0,
            'stations_distinctes': 0,
        }
    
    stats = amendes_qs.aggregate(
        total_amendes=Count('id'),
        total_payees=Count('id', filter=Q(statut='paye')),
        total_non_payees=Count('id', filter=Q(statut='non_paye')),
        montant_total=Sum('montant_amende'),
        montant_paye=Sum('montant_amende', filter=Q(statut='paye')),
        montant_impaye=Sum('montant_amende', filter=Q(statut='non_paye')),
        stations_distinctes=Count('station', distinct=True)
    )
    
    return {
        'total_amendes': stats['total_amendes'] or 0,
        'total_payees': stats['total_payees'] or 0,
        'total_non_payees': stats['total_non_payees'] or 0,
        'montant_total': stats['montant_total'] or 0,
        'montant_paye': stats['montant_paye'] or 0,
        'montant_impaye': stats['montant_impaye'] or 0,
        'stations_distinctes': stats['stations_distinctes'] or 0,
    }