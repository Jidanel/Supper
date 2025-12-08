# ===================================================================
# FICHIER: inventaire/utils_quittancement.py (NOUVEAU FICHIER)
# Fonctions utilitaires pour la validation des quittancements
# ===================================================================

from datetime import datetime, timedelta
from django.db.models import Q


def get_dates_deja_quittancees_peage(poste, exercice, mois):
    """
    Retourne l'ensemble des dates déjà quittancées pour un poste de péage
    (combinaison journalier + décade)
    
    Args:
        poste: Instance du Poste
        exercice: Année (int)
        mois: Mois au format 'YYYY-MM'
    
    Returns:
        set: Ensemble des dates (datetime.date) déjà couvertes
    """
    from inventaire.models import Quittancement
    
    dates_couvertes = set()
    
    # Récupérer tous les quittancements existants pour ce poste/exercice/mois
    quittancements = Quittancement.objects.filter(
        poste=poste,
        exercice=exercice,
        mois=mois
    )
    
    for q in quittancements:
        if q.type_declaration == 'journaliere' and q.date_recette:
            # Ajouter la date unique
            dates_couvertes.add(q.date_recette)
        elif q.type_declaration == 'decade' and q.date_debut_decade and q.date_fin_decade:
            # Ajouter toutes les dates de la période
            current = q.date_debut_decade
            while current <= q.date_fin_decade:
                dates_couvertes.add(current)
                current += timedelta(days=1)
    
    return dates_couvertes


def get_dates_deja_quittancees_pesage(station, exercice, mois):
    """
    Retourne l'ensemble des dates déjà quittancées pour une station de pesage
    (combinaison journalier + décade)
    
    Args:
        station: Instance du Poste (station pesage)
        exercice: Année (int)
        mois: Mois au format 'YYYY-MM'
    
    Returns:
        set: Ensemble des dates (datetime.date) déjà couvertes
    """
    from inventaire.models_pesage import QuittancementPesage
    
    dates_couvertes = set()
    
    # Récupérer tous les quittancements existants pour cette station/exercice/mois
    quittancements = QuittancementPesage.objects.filter(
        station=station,
        exercice=exercice,
        mois=mois
    )
    
    for q in quittancements:
        if q.type_declaration == 'journaliere' and q.date_recette:
            # Ajouter la date unique
            dates_couvertes.add(q.date_recette)
        elif q.type_declaration == 'decade' and q.date_debut_decade and q.date_fin_decade:
            # Ajouter toutes les dates de la période
            current = q.date_debut_decade
            while current <= q.date_fin_decade:
                dates_couvertes.add(current)
                current += timedelta(days=1)
    
    return dates_couvertes


def valider_dates_quittancement_peage(poste, exercice, mois, type_declaration, 
                                       date_recette=None, date_debut=None, date_fin=None):
    """
    Valide que les dates du nouveau quittancement ne chevauchent pas des dates existantes
    
    Args:
        poste: Instance du Poste
        exercice: Année (int)
        mois: Mois au format 'YYYY-MM'
        type_declaration: 'journaliere' ou 'decade'
        date_recette: Date pour type journalier (datetime.date ou str)
        date_debut: Date début pour type décade (datetime.date ou str)
        date_fin: Date fin pour type décade (datetime.date ou str)
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None, dates_en_conflit: list)
    """
    # Convertir les chaînes en dates si nécessaire
    if isinstance(date_recette, str):
        date_recette = datetime.strptime(date_recette, '%Y-%m-%d').date()
    if isinstance(date_debut, str):
        date_debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
    if isinstance(date_fin, str):
        date_fin = datetime.strptime(date_fin, '%Y-%m-%d').date()
    
    # Récupérer les dates déjà quittancées
    dates_existantes = get_dates_deja_quittancees_peage(poste, exercice, mois)
    
    # Déterminer les nouvelles dates à vérifier
    nouvelles_dates = set()
    
    if type_declaration == 'journaliere' and date_recette:
        nouvelles_dates.add(date_recette)
    elif type_declaration == 'decade' and date_debut and date_fin:
        current = date_debut
        while current <= date_fin:
            nouvelles_dates.add(current)
            current += timedelta(days=1)
    
    # Trouver les conflits
    dates_en_conflit = nouvelles_dates & dates_existantes
    
    if dates_en_conflit:
        # Formater les dates pour le message d'erreur
        dates_formatees = sorted([d.strftime('%d/%m/%Y') for d in dates_en_conflit])
        
        if len(dates_formatees) == 1:
            message = f"La date du {dates_formatees[0]} a déjà été quittancée"
        else:
            message = f"Les dates suivantes ont déjà été quittancées : {', '.join(dates_formatees)}"
        
        return False, message, list(dates_en_conflit)
    
    return True, None, []


def valider_dates_quittancement_pesage(station, exercice, mois, type_declaration,
                                        date_recette=None, date_debut=None, date_fin=None):
    """
    Valide que les dates du nouveau quittancement pesage ne chevauchent pas des dates existantes
    
    Args:
        station: Instance du Poste (station pesage)
        exercice: Année (int)
        mois: Mois au format 'YYYY-MM'
        type_declaration: 'journaliere' ou 'decade'
        date_recette: Date pour type journalier (datetime.date ou str)
        date_debut: Date début pour type décade (datetime.date ou str)
        date_fin: Date fin pour type décade (datetime.date ou str)
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None, dates_en_conflit: list)
    """
    # Convertir les chaînes en dates si nécessaire
    if isinstance(date_recette, str):
        date_recette = datetime.strptime(date_recette, '%Y-%m-%d').date()
    if isinstance(date_debut, str):
        date_debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
    if isinstance(date_fin, str):
        date_fin = datetime.strptime(date_fin, '%Y-%m-%d').date()
    
    # Récupérer les dates déjà quittancées
    dates_existantes = get_dates_deja_quittancees_pesage(station, exercice, mois)
    
    # Déterminer les nouvelles dates à vérifier
    nouvelles_dates = set()
    
    if type_declaration == 'journaliere' and date_recette:
        nouvelles_dates.add(date_recette)
    elif type_declaration == 'decade' and date_debut and date_fin:
        current = date_debut
        while current <= date_fin:
            nouvelles_dates.add(current)
            current += timedelta(days=1)
    
    # Trouver les conflits
    dates_en_conflit = nouvelles_dates & dates_existantes
    
    if dates_en_conflit:
        # Formater les dates pour le message d'erreur
        dates_formatees = sorted([d.strftime('%d/%m/%Y') for d in dates_en_conflit])
        
        if len(dates_formatees) == 1:
            message = f"La date du {dates_formatees[0]} a déjà été quittancée"
        else:
            message = f"Les dates suivantes ont déjà été quittancées : {', '.join(dates_formatees)}"
        
        return False, message, list(dates_en_conflit)
    
    return True, None, []