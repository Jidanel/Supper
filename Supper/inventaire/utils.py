from datetime import date, timedelta
from django.db.models import Avg, Q, Count

def calculer_taux_deperdition_periode(poste, date_debut, date_fin, exclure_impertinents=True):
    """Calcule le taux de déperdition moyen pour une période"""
    from .models import RecetteJournaliere, ConfigurationJour

    query = RecetteJournaliere.objects.filter(
        poste=poste,
        date__range=[date_debut, date_fin],
        taux_deperdition__isnull=False
    )

    if exclure_impertinents:
        # Exclure les jours impertinents
        jours_impertinents = ConfigurationJour.objects.filter(
            statut='impertinent',
            date__range=[date_debut, date_fin]
        ).values_list('date', flat=True)

        query = query.exclude(date__in=jours_impertinents)

    return query.aggregate(
        taux_moyen=Avg('taux_deperdition'),
        nombre_jours=Count('id')
    )

def generer_statistiques_taux(poste=None, annee=None):
    """Génère les statistiques de taux pour graphiques"""
    if not annee:
        annee = date.today().year

    stats = {
        'journalier': [],
        'hebdomadaire': [],
        'mensuel': [],
        'trimestriel': [],
        'semestriel': [],
        'annuel': None
    }

    # Calculer pour chaque mois
    for mois in range(1, 13):
        date_debut = date(annee, mois, 1)
        if mois == 12:
            date_fin = date(annee, 12, 31)
        else:
            date_fin = date(annee, mois + 1, 1) - timedelta(days=1)

        result = calculer_taux_deperdition_periode(
            poste, date_debut, date_fin
        )

        stats['mensuel'].append({
            'mois': mois,
            'taux': result['taux_moyen'],
            'nombre_jours': result['nombre_jours']
        })

    return stats
# ===================================================================
# inventaire/utils/qr_code_generator.py
# Générateur de QR codes optimisé pour tickets de péage
# ===================================================================
"""
Ce module génère des QR codes en petite taille native, optimisés pour
l'impression sur tickets de péage.

Caractéristiques:
- Taille native petite (pas de redimensionnement CSS)
- Version QR minimale pour lisibilité
- Correction d'erreur optimale pour impression
- Compatible avec scanners de péage
"""

import qrcode
from qrcode.constants import ERROR_CORRECT_M, ERROR_CORRECT_L, ERROR_CORRECT_H
import base64
from io import BytesIO
from typing import Optional
import hashlib
import json
from decimal import Decimal


# ===================================================================
# CONFIGURATION
# ===================================================================

# Taille du QR code en pixels (natif, pas de redimensionnement CSS)
QR_SIZE_TICKET_SMALL = 80    # Pour mini-tickets
QR_SIZE_TICKET_NORMAL = 100  # Pour tickets standards
QR_SIZE_TICKET_LARGE = 120   # Pour affichage écran

# Marge autour du QR (en modules)
QR_BORDER = 2  # Minimale pour économiser de l'espace

# Version QR - Plus basse = plus petit mais moins de données
# Version 1 = 21x21 modules, peut contenir ~17 caractères alphanumériques
# Version 2 = 25x25 modules, peut contenir ~32 caractères
# Version 3 = 29x29 modules, peut contenir ~53 caractères
QR_VERSION_AUTO = None  # Auto-détection basée sur la taille des données


# ===================================================================
# FONCTION PRINCIPALE
# ===================================================================

def generer_qr_code_ticket(
    code: str,
    poste_code: str,
    poste_nom: str,
    exercice: int,
    numero_commande: int,
    type_periode: str = None,
    montant: Decimal = None,
    nombre_carnets: int = None,
    taille: str = 'normal'
) -> str:
    """
    Génère un QR code optimisé pour ticket de péage.

    Le QR code contient des données minimales pour vérification:
    - Code de sécurisation
    - Hash de vérification

    Args:
        code: Code de sécurisation unique
        poste_code: Code du poste (ex: 'NSM')
        poste_nom: Nom du poste
        exercice: Année
        numero_commande: Numéro de la commande
        type_periode: Type de période (optionnel)
        montant: Montant de la commande (optionnel)
        nombre_carnets: Nombre de carnets (optionnel)
        taille: 'small' (80px), 'normal' (100px), ou 'large' (120px)

    Returns:
        String base64 du QR code (data:image/png;base64,...)
    """
    # Sélectionner la taille
    if taille == 'small':
        box_size = 2  # Chaque module = 2 pixels
        target_size = QR_SIZE_TICKET_SMALL
    elif taille == 'large':
        box_size = 3
        target_size = QR_SIZE_TICKET_LARGE
    else:  # normal
        box_size = 2
        target_size = QR_SIZE_TICKET_NORMAL

    # Construire les données du QR (format compact)
    # Format: CODE|HASH_VERIFICATION
    # Le hash permet de vérifier l'authenticité sans stocker toutes les données
    verification_string = f"{code}:{poste_code}:{exercice}:{numero_commande}"
    hash_verification = hashlib.sha256(verification_string.encode()).hexdigest()[:12]

    qr_data = f"{code}|{hash_verification}"

    # Créer le QR code
    qr = qrcode.QRCode(
        version=QR_VERSION_AUTO,  # Auto-détection
        error_correction=ERROR_CORRECT_M,  # Correction moyenne (15%)
        box_size=box_size,
        border=QR_BORDER,
    )

    qr.add_data(qr_data)
    qr.make(fit=True)

    # Générer l'image
    img = qr.make_image(fill_color="black", back_color="white")

    # Redimensionner à la taille exacte si nécessaire
    actual_size = img.size[0]
    if actual_size != target_size:
        from PIL import Image
        img = img.resize((target_size, target_size), Image.Resampling.NEAREST)

    # Convertir en base64
    buffer = BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)

    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return f"data:image/png;base64,{img_base64}"


def generer_qr_code_verification(
    code_securisation: str,
    url_verification: str = None
) -> str:
    """
    Génère un QR code de vérification pointant vers l'API.

    Ce QR code peut être scanné pour vérifier l'authenticité du ticket
    en ligne via l'API publique.

    Args:
        code_securisation: Code unique du ticket
        url_verification: URL de base de l'API (optionnel)

    Returns:
        String base64 du QR code
    """
    if url_verification:
        qr_data = f"{url_verification}?code={code_securisation}"
    else:
        qr_data = code_securisation

    qr = qrcode.QRCode(
        version=QR_VERSION_AUTO,
        error_correction=ERROR_CORRECT_L,  # Correction légère pour URL
        box_size=2,
        border=QR_BORDER,
    )

    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Redimensionner à 100x100
    from PIL import Image
    img = img.resize((100, 100), Image.Resampling.NEAREST)

    buffer = BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)

    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('utf-8')}"


# ===================================================================
# FONCTION DE COMPATIBILITÉ AVEC LE CODE EXISTANT
# ===================================================================

def generer_qr_code_base64(
    code: str,
    poste,  # Instance Poste
    exercice: int,
    numero_commande: int,
    type_periode: str = None,
    montant = None,
    nombre_tickets: int = None,
    nombre_carnets: int = None,
    taille: str = 'normal'
) -> str:
    """
    Fonction de compatibilité avec le code existant.

    Remplace la fonction generer_qr_code_base64() existante avec
    une génération optimisée pour les tickets de péage.

    Args:
        code: Code de sécurisation
        poste: Instance du modèle Poste
        exercice: Année
        numero_commande: Numéro de commande
        type_periode: Type de période
        montant: Montant (Decimal ou int)
        nombre_tickets: Nombre de tickets
        nombre_carnets: Nombre de carnets
        taille: 'small', 'normal', ou 'large'

    Returns:
        String base64 du QR code
    """
    return generer_qr_code_ticket(
        code=code,
        poste_code=poste.code if hasattr(poste, 'code') else str(poste),
        poste_nom=poste.nom if hasattr(poste, 'nom') else str(poste),
        exercice=exercice,
        numero_commande=numero_commande,
        type_periode=type_periode,
        montant=montant,
        nombre_carnets=nombre_carnets,
        taille=taille
    )


# ===================================================================
# FONCTIONS UTILITAIRES
# ===================================================================

def generer_code_securisation_temp(exercice: int, index: int) -> str:
    """
    Génère un code de sécurisation temporaire.

    Format: SUPPER-AAAA-XXXXX
    Où AAAA = exercice et XXXXX = index sur 5 chiffres

    Args:
        exercice: Année de l'exercice
        index: Index unique

    Returns:
        Code de sécurisation
    """
    return f"SUPPER-{exercice}-{index:05d}"


def verifier_hash_qr(qr_data: str, poste_code: str, exercice: int, numero_commande: int) -> bool:
    """
    Vérifie le hash d'un QR code scanné.

    Args:
        qr_data: Données du QR (format: CODE|HASH)
        poste_code: Code du poste
        exercice: Année
        numero_commande: Numéro de commande

    Returns:
        True si le hash est valide
    """
    try:
        parts = qr_data.split('|')
        if len(parts) != 2:
            return False

        code, hash_recu = parts

        # Recalculer le hash
        verification_string = f"{code}:{poste_code}:{exercice}:{numero_commande}"
        hash_attendu = hashlib.sha256(verification_string.encode()).hexdigest()[:12]

        return hash_recu == hash_attendu
    except Exception:
        return False


# ===================================================================
# CONFIGURATION DE TAILLE POUR LES VUES
# ===================================================================

QR_SIZES = {
    'ticket': 'small',      # 80x80 - Pour impression sur ticket physique
    'preview': 'normal',    # 100x100 - Pour aperçu dans l'interface
    'detail': 'large',      # 120x120 - Pour page de détail/vérification
}

def get_qr_size_for_context(context: str) -> str:
    """
    Retourne la taille de QR appropriée selon le contexte.

    Args:
        context: 'ticket', 'preview', ou 'detail'

    Returns:
        Taille ('small', 'normal', 'large')
    """
    return QR_SIZES.get(context, 'normal')