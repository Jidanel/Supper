# ===================================================================
# inventaire/views_commandes.py - VUES COMMANDES ET LIVRAISONS
# Application SUPPER - Gestion des commandes de tickets
# ===================================================================
"""
Ce fichier contient les vues pour le système de commandes de tickets:

VUES COMMANDES:
- simulateur_commandes_etape1: Sélection des paramètres (postes, période, etc.)
- simulateur_commandes_etape2: Validation et génération codes QR/sécurisation
- liste_commandes: Liste avec filtres et actions admin
- detail_commande: Détail d'une commande avec tableau des postes
- modifier_commande: Modification (admin uniquement)
- supprimer_commande: Suppression (admin uniquement)

VUES LIVRAISONS:
- creer_livraison_etape1: Sélection commande, poste, date
- creer_livraison_etape2: Sélection des recharges à associer
- liste_livraisons: Liste avec suivi progression
- tableau_livraisons_commande: Vue par commande avec taux progression
- modifier_livraison: Modification
- supprimer_livraison: Suppression

API:
- api_postes_commande: Postes pour une commande (AJAX)
- api_recharges_poste: Recharges disponibles pour un poste (AJAX)
- api_verifier_qr: Vérification d'un QR code (public, sans auth)

PERMISSIONS:
- peut_simuler_commandes_peage: Accès au simulateur
- peut_gerer_commandes_admin: Modification/Suppression (admin)
- peut_gerer_livraisons: Création/gestion des livraisons
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Avg, Q, F, Count
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
import json
import logging
from django.db.models import Sum

from accounts.models import Poste, UtilisateurSUPPER
from .models import (
    RecetteJournaliere, HistoriqueStock, CouleurTicket, SerieTicket
)
from .models_commandes import (
    CommandeTickets, DetailCommandePoste, LivraisonTickets
)
from .forms_commandes import (
    ParametresCommandeForm, ConfirmationCommandeForm,
    LivraisonCreationForm, SelectionRechargesForm,
    ModificationCommandeForm, ModificationLivraisonForm,
    FiltreCommandesForm, FiltreLivraisonsForm
)
from inventaire.services.forecasting_service import ForecastingService
# Import des fonctions de permissions et logging
from common.permissions import (
    has_permission, has_any_permission, is_admin_user,
    is_service_central, log_acces_refuse
)
from common.utils import log_user_action

logger = logging.getLogger('supper')


# ===================================================================
# FONCTIONS UTILITAIRES
# ===================================================================

# Liste des habilitations autorisées pour les commandes et livraisons
HABILITATIONS_COMMANDES = [
    'admin_principal',   # Administrateur Principal
    'coord_psrr',        # Coordonnateur PSRR
    'serv_info',         # Chef Service Informatique
    'serv_emission',     # Chef Service Émission et Recouvrement
]


def peut_gerer_commandes(user):
    """
    Vérifie si l'utilisateur peut accéder au simulateur de commandes.

    RESTRICTION: Uniquement les administrateurs:
    - admin_principal (Administrateur Principal)
    - coord_psrr (Coordonnateur PSRR)
    - serv_info (Chef Service Informatique)
    - serv_emission (Chef Service Émission et Recouvrement)
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return getattr(user, 'habilitation', None) in HABILITATIONS_COMMANDES


def peut_administrer_commandes(user):
    """
    Vérifie si l'utilisateur peut modifier/supprimer les commandes.
    Mêmes habilitations que peut_gerer_commandes.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return getattr(user, 'habilitation', None) in HABILITATIONS_COMMANDES


def peut_gerer_livraisons(user):
    """
    Vérifie si l'utilisateur peut gérer les livraisons.
    Mêmes habilitations que peut_gerer_commandes.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return getattr(user, 'habilitation', None) in HABILITATIONS_COMMANDES


# ===================================================================
# FONCTION MODIFIÉE: calculer_montant_periode avec FORECASTING
# ===================================================================

def calculer_montant_periode(poste, exercice, type_periode, mois=None, trimestre=None, semestre=None):
    """
    Calcule le montant à commander pour un poste sur une période donnée.

    MISE À JOUR 15/04/2026: Utilise maintenant le ForecastingService pour:
    1. Analyser les tendances de ventes (historique)
    2. Calculer les jours restants jusqu'à la fin de période
    3. Estimer les ventes futures avec Holt-Winters
    4. Soustraire le stock actuel
    5. Retourner le montant net à commander

    FALLBACK: Si le forecasting échoue (pas assez de données historiques),
    utilise l'ancienne méthode basée sur les recettes passées.
    """
    try:
        # Essayer d'abord avec le forecasting intelligent
        resultat = ForecastingService.calculer_commande_periode(
            poste=poste,
            exercice=exercice,
            type_periode=type_periode,
            mois=mois,
            trimestre=trimestre,
            semestre=semestre
        )

        if resultat.get('success'):
            logger.debug(
                f"Forecasting {poste.nom}: "
                f"Carnets={resultat['nombre_carnets']}, "
                f"Tendance={resultat['details_analyse'].get('tendance', 'N/A')}, "
                f"Jours restants={resultat['jours_restants']}"
            )
            return resultat['montant_estime']
        else:
            # Forecasting a échoué, utiliser le fallback
            logger.warning(
                f"Forecasting échoué pour {poste.nom}: {resultat.get('error', 'Erreur inconnue')}. "
                f"Utilisation du calcul historique."
            )
            return _calculer_montant_periode_historique(
                poste, exercice, type_periode, mois, trimestre, semestre
            )

    except Exception as e:
        # En cas d'erreur, utiliser le fallback
        logger.error(f"Erreur forecasting pour {poste.nom}: {str(e)}")
        return _calculer_montant_periode_historique(
            poste, exercice, type_periode, mois, trimestre, semestre
        )


def _calculer_montant_periode_historique(poste, exercice, type_periode, mois=None, trimestre=None, semestre=None):
    """
    FALLBACK: Calcul basé sur les recettes historiques de la période.
    C'est l'ancienne méthode, conservée pour compatibilité.
    """
    # Définir les dates de début et fin selon la période
    if type_periode == 'mensuelle' and mois:
        mois = int(mois)
        date_debut = timezone.datetime(exercice, mois, 1).date()
        if mois == 12:
            date_fin = timezone.datetime(exercice + 1, 1, 1).date()
        else:
            date_fin = timezone.datetime(exercice, mois + 1, 1).date()
    elif type_periode == 'trimestrielle' and trimestre:
        trimestre = int(trimestre)
        mois_debut = (trimestre - 1) * 3 + 1
        date_debut = timezone.datetime(exercice, mois_debut, 1).date()
        if trimestre == 4:
            date_fin = timezone.datetime(exercice + 1, 1, 1).date()
        else:
            date_fin = timezone.datetime(exercice, mois_debut + 3, 1).date()
    elif type_periode == 'semestrielle' and semestre:
        semestre = int(semestre)
        if semestre == 1:
            date_debut = timezone.datetime(exercice, 1, 1).date()
            date_fin = timezone.datetime(exercice, 7, 1).date()
        else:
            date_debut = timezone.datetime(exercice, 7, 1).date()
            date_fin = timezone.datetime(exercice + 1, 1, 1).date()
    else:  # Annuelle
        date_debut = timezone.datetime(exercice, 1, 1).date()
        date_fin = timezone.datetime(exercice + 1, 1, 1).date()

    # Calculer le total des recettes déclarées
    total = RecetteJournaliere.objects.filter(
        poste=poste,
        date__gte=date_debut,
        date__lt=date_fin
    ).aggregate(total=Sum('montant_declare'))['total']

    return total or Decimal('0')


def obtenir_couleur_poste(poste):
    """
    Récupère la couleur des derniers tickets chargés pour un poste.
    Retourne la CouleurTicket ou None si aucun chargement trouvé.
    """
    dernier_chargement = SerieTicket.objects.filter(
        poste=poste,
        type_entree='imprimerie_nationale'
    ).order_by('-date_reception').first()

    if dernier_chargement:
        return dernier_chargement.couleur
    return None


# ===================================================================
# FONCTIONS QR CODE - VERSION OPTIMISÉE (15/04/2026)
# ===================================================================

import hashlib
import base64
from io import BytesIO

# Vérifier si qrcode est disponible
try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
    logger.warning("Le module qrcode n'est pas installé. Installation: pip install qrcode[pil] --break-system-packages")


def generer_code_securisation_temp(exercice, index):
    """
    Génère un code de sécurisation temporaire pour prévisualisation.
    Format: PSRR{année}{numéro séquentiel sur 6 chiffres}

    Args:
        exercice: Année de l'exercice
        index: Numéro d'ordre du poste dans la commande

    Returns:
        str: Code formaté ex: "PSRR2026000001"
    """
    return f"PSRR{exercice}{index:06d}"


def generer_code_securisation_final(exercice, detail_id):
    """
    Génère le code de sécurisation final pour un DetailCommandePoste validé.
    Format: PSRR{année}{ID sur 6 chiffres}

    Args:
        exercice: Année de l'exercice
        detail_id: ID du DetailCommandePoste

    Returns:
        str: Code formaté ex: "PSRR2026000042"
    """
    return f"PSRR{exercice}{detail_id:06d}"


def generer_hash_verification(qr_data):
    """
    Génère un hash SHA-256 tronqué pour vérifier l'intégrité des données du QR code.

    MISE À JOUR: Hash tronqué à 12 caractères pour réduire la taille du QR.

    Args:
        qr_data: dict des données du QR code

    Returns:
        str: Hash SHA-256 tronqué à 12 caractères
    """
    # Créer une chaîne déterministe à partir des données
    data_string = json.dumps(qr_data, sort_keys=True, ensure_ascii=False)
    # Tronquer à 12 caractères pour réduire la taille du QR
    return hashlib.sha256(data_string.encode('utf-8')).hexdigest()[:12]


# def generer_qr_code_base64(code, poste, exercice, numero_commande, type_periode, montant, nombre_tickets, nombre_carnets):
#     """
#     Génère un QR code en base64 lisible par des utilisateurs lambda.

#     VERSION LISIBILITÉ TERRAIN:
#     - Données explicites (pas de clés abrégées)
#     - Informations compréhensibles directement après scan
#     - Suppression du hash technique
#     - Ajout d’un message d’authentification PSRR
#     """

#     if not QRCODE_AVAILABLE:
#         return None

#     try:
#         # 1. Données lisibles pour humains
#         qr_data = {
#             "code_securisation": code,
#             "commande": {
#                 "numero": numero_commande,
#                 "exercice": exercice,
#                 "periode": type_periode,
#             },
#             "poste": {
#                 "nom": poste.nom,
#                 "region": poste.region.nom if poste.region else None,
#             },
#             "details": {
#                 "montant_commande": str(montant),
#                 "nombre_tickets": nombre_tickets,
#             },
#             "authentification": "Ce ticket est authentifié par le PSRR"
#         }

#         # 2. JSON propre (lisible mais pas trop lourd)
#         qr_json = json.dumps(qr_data, ensure_ascii=False)

#         # 3. QR Code (équilibré lisibilité / performance)
#         qr = qrcode.QRCode(
#             version=None,  # auto
#             error_correction=qrcode.constants.ERROR_CORRECT_M,  # meilleur que L pour terrain
#             box_size=2,  # légèrement plus grand pour lisibilité
#             border=3,
#         )

#         qr.add_data(qr_json)
#         qr.make(fit=True)

#         # 4. Génération image
#         img = qr.make_image(
#             fill_color="black",
#             back_color="white"
#         )

#         # 5. Conversion base64
#         buffer = BytesIO()
#         img.save(buffer, format='PNG', optimize=True)
#         img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')

#         return f"data:image/png;base64,{img_str}"

#     except Exception as e:
#         logger.error(f"Erreur génération QR code: {e}")
#         return None

# def verifier_qr_code(qr_data_string):
#     """
#     Vérifie l'intégrité d'un QR code scanné.

#     MISE À JOUR: Supporte les deux formats (ancien et nouveau compact).

#     Args:
#         qr_data_string: Données JSON du QR code (string)

#     Returns:
#         tuple: (bool valide, dict données ou message erreur)
#     """
#     try:
#         qr_data = json.loads(qr_data_string)

#         # Supporter les deux formats (ancien et nouveau compact)
#         # Nouveau format: c, p, e, n, m, h
#         # Ancien format: code, poste_id, exercice, numero_commande, montant, hash

#         if 'c' in qr_data:
#             # Nouveau format compact
#             code = qr_data.get('c')
#             poste_id = qr_data.get('p')
#             exercice = qr_data.get('e')
#             hash_recu = qr_data.pop('h', None)

#             # Recalculer le hash (tronqué)
#             hash_calcule = generer_hash_verification(qr_data)
#         else:
#             # Ancien format
#             code = qr_data.get('code')
#             poste_id = qr_data.get('poste_id')
#             exercice = qr_data.get('exercice')
#             hash_recu = qr_data.pop('hash', None)

#             # Recalculer le hash (ancien format = hash complet)
#             data_string = json.dumps(qr_data, sort_keys=True, ensure_ascii=False)
#             hash_calcule = hashlib.sha256(data_string.encode('utf-8')).hexdigest()

#         # Vérifier les champs requis
#         if not all([code, poste_id, exercice]):
#             return False, "Champs manquants dans le QR code"

#         # Comparer les hash (supporter hash tronqué ou complet)
#         if hash_recu:
#             if len(hash_recu) == 12:
#                 # Hash tronqué (nouveau format)
#                 if hash_recu != hash_calcule[:12]:
#                     return False, "Données altérées - Hash invalide"
#             else:
#                 # Hash complet (ancien format)
#                 if hash_recu != hash_calcule:
#                     return False, "Données altérées - Hash invalide"

#         # Vérifier que le code existe dans la base
#         try:
#             detail = DetailCommandePoste.objects.select_related(
#                 'commande', 'poste'
#             ).get(code_securisation=code)

#             return True, {
#                 'valide': True,
#                 'code': code,
#                 'commande': {
#                     'id': detail.commande.id,
#                     'numero': detail.commande.numero_commande,
#                     'exercice': detail.commande.exercice,
#                     'statut': detail.commande.get_statut_display()
#                 },
#                 'poste': {
#                     'id': detail.poste.id,
#                     'nom': detail.poste.nom
#                 },
#                 'montant': str(detail.montant_commande),
#                 'nombre_carnets': detail.nombre_carnets,
#                 'est_livre': detail.est_complet
#             }

#         except DetailCommandePoste.DoesNotExist:
#             return False, "Code de sécurisation non trouvé dans la base"

#     except json.JSONDecodeError:
#         return False, "Format QR code invalide"
#     except Exception as e:
#         return False, f"Erreur de vérification: {str(e)}"

def generer_qr_code_base64(code, poste, exercice, numero_commande, type_periode, montant, nombre_tickets, nombre_carnets):
    """
    Génère un QR code optimisé pour scan terrain.
    CONTIENT UNIQUEMENT UNE URL DE VÉRIFICATION.
    """

    if not QRCODE_AVAILABLE:
        return None

    try:
        # 🔥 1. URL de vérification (clé du système)
        url = f"https://supper-cm.ink/inventaire/verifier/{code}/"

        # 🔥 2. Création QR code léger
        qr = qrcode.QRCode(
            version=None,  # auto
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=2,
            border=3,
        )

        qr.add_data(url)
        qr.make(fit=True)

        # 🔥 3. Génération image
        img = qr.make_image(
            fill_color="black",
            back_color="white"
        )

        # 🔥 4. Redimensionnement (~1.5 simulé)
        # from PIL import Image
        # largeur, hauteur = img.size
        # img = img.resize(
        #     (int(largeur * 0.75), int(hauteur * 0.75)),
        #     resample=Image.NEAREST
        # )

        # 🔥 5. Conversion base64
        buffer = BytesIO()
        img.save(buffer, format='PNG', optimize=True)
        img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return f"data:image/png;base64,{img_str}"

    except Exception as e:
        logger.error(f"Erreur génération QR code: {e}")
        return None

def verifier_qr_code(request, code):
    """
    Vérifie un QR code via le code de sécurisation
    """

    detail = DetailCommandePoste.objects.select_related(
        'poste', 'poste__region', 'commande'
    ).filter(code_securisation=code).first()

    if not detail:
        return render(request, 'inventaire/qr/verifier.html', {
            'valide': False,
            'message': "Code invalide ou inexistant"
        })

    return render(request, 'inventaire/qr/verifier.html', {
        'valide': True,
        'detail': detail,
        'commande': detail.commande,
        'poste': detail.poste,
    })

# ===================================================================
# VUES COMMANDES - ÉTAPE 1: PARAMÈTRES
# ===================================================================

@login_required
@require_GET
def simulateur_commandes_etape1(request):
    """
    Étape 1: Sélection des paramètres de la commande.
    - Sélection des postes (avec bouton tout sélectionner)
    - Numéro de commande (1-10)
    - Exercice (année)
    - Type de période et détails
    """
    user = request.user

    # Vérification des permissions
    if not peut_gerer_commandes(user):
        log_user_action(
            user=user,
            action="ACCÈS REFUSÉ - Simulateur commandes",
            description=f"Permission manquante: peut_simuler_commandes_peage",
            details={'habilitation': getattr(user, 'habilitation', 'N/A')},
            niveau='warning'
        )
        messages.error(request, "Vous n'avez pas la permission d'accéder au simulateur de commandes.")
        return redirect('common:dashboard')

    # Log de l'accès
    log_user_action(
        user=user,
        action="Accès simulateur commandes",
        description="Ouverture de l'étape 1 du simulateur de commandes",
        details={},
        niveau='info'
    )

    # Initialiser le formulaire
    form = ParametresCommandeForm()

    # Récupérer les postes groupés par région pour l'affichage
    postes_par_region = {}
    postes = Poste.objects.filter(
        is_active=True,
        type='peage'
    ).select_related('region').order_by('region__nom', 'nom')

    for poste in postes:
        region_nom = poste.region.nom if poste.region else "Sans région"
        if region_nom not in postes_par_region:
            postes_par_region[region_nom] = []
        postes_par_region[region_nom].append(poste)

    context = {
        'form': form,
        'postes_par_region': postes_par_region,
        'total_postes': postes.count(),
        'title': 'Simulateur de Commandes - Étape 1: Paramètres',
        'etape': 1,
        'etapes_total': 2,
    }

    return render(request, 'inventaire/commandes/etape1_parametres.html', context)


@login_required
@require_POST
def simulateur_commandes_etape1_submit(request):
    """
    Traitement du formulaire de l'étape 1.
    Stocke les données en session et redirige vers l'étape 2.
    """
    user = request.user

    if not peut_gerer_commandes(user):
        messages.error(request, "Vous n'avez pas la permission d'accéder au simulateur de commandes.")
        return redirect('common:dashboard')

    form = ParametresCommandeForm(request.POST)

    if form.is_valid():
        # Extraire les données validées
        postes = form.cleaned_data['postes']
        numero_commande = int(form.cleaned_data['numero_commande'])
        exercice = int(form.cleaned_data['exercice'])
        type_periode = form.cleaned_data['type_periode']
        mois = form.cleaned_data.get('mois')
        trimestre = form.cleaned_data.get('trimestre')
        semestre = form.cleaned_data.get('semestre')
        description = form.cleaned_data.get('description', '')

        # Stocker les IDs des postes en session
        request.session['commande_postes_ids'] = [p.id for p in postes]
        request.session['commande_numero'] = numero_commande
        request.session['commande_exercice'] = exercice
        request.session['commande_type_periode'] = type_periode
        request.session['commande_mois'] = mois
        request.session['commande_trimestre'] = trimestre
        request.session['commande_semestre'] = semestre
        request.session['commande_description'] = description

        # Log de l'action
        log_user_action(
            user=user,
            action="Paramètres commande validés",
            description=f"Étape 1 validée: {len(postes)} postes sélectionnés pour commande n°{numero_commande}",
            details={
                'exercice': exercice,
                'type_periode': type_periode,
                'nb_postes': len(postes),
                'postes': [p.nom for p in postes[:10]]  # Max 10 pour le log
            },
            niveau='info'
        )

        return redirect('inventaire:simulateur_commandes_etape2')

    # Formulaire invalide, réafficher avec erreurs
    postes_par_region = {}
    postes = Poste.objects.filter(
        is_active=True,
        type='peage'
    ).select_related('region').order_by('region__nom', 'nom')

    for poste in postes:
        region_nom = poste.region.nom if poste.region else "Sans région"
        if region_nom not in postes_par_region:
            postes_par_region[region_nom] = []
        postes_par_region[region_nom].append(poste)

    context = {
        'form': form,
        'postes_par_region': postes_par_region,
        'total_postes': postes.count(),
        'title': 'Simulateur de Commandes - Étape 1: Paramètres',
        'etape': 1,
        'etapes_total': 2,
    }

    return render(request, 'inventaire/commandes/etape1_parametres.html', context)


# ===================================================================
# VUES COMMANDES - ÉTAPE 2: VALIDATION
# ===================================================================


@login_required
def simulateur_commandes_etape2(request):
    """
    Étape 2: Validation de la commande.
    """
    user = request.user

    if not peut_gerer_commandes(user):
        messages.error(request, "Vous n'avez pas la permission d'accéder au simulateur de commandes.")
        return redirect('common:dashboard')

    # Récupérer les données de session
    postes_ids = request.session.get('commande_postes_ids', [])
    numero_commande = request.session.get('commande_numero')
    exercice = request.session.get('commande_exercice')
    type_periode = request.session.get('commande_type_periode')
    mois = request.session.get('commande_mois')
    trimestre = request.session.get('commande_trimestre')
    semestre = request.session.get('commande_semestre')
    description = request.session.get('commande_description', '')

    if not postes_ids or not numero_commande or not exercice:
        messages.warning(request, "Session expirée. Veuillez recommencer.")
        return redirect('inventaire:simulateur_commandes_etape1')

    postes = Poste.objects.filter(id__in=postes_ids).select_related('region').order_by('region__nom', 'nom')

    commande_existante = CommandeTickets.objects.filter(
        numero_commande=numero_commande,
        exercice=exercice
    ).first()

    postes_existants = []
    if commande_existante:
        postes_existants = list(commande_existante.details.values_list('poste_id', flat=True))

    # Calculer les montants pour chaque poste
    details_postes = []
    montant_total = Decimal('0')
    nombre_tickets_total = 0
    nombre_carnets_total = 0

    for idx, poste in enumerate(postes, start=1):
        montant = calculer_montant_periode(
            poste, exercice, type_periode, mois, trimestre, semestre
        )
        nombre_tickets = int(montant / 500) if montant else 0
        nombre_carnets = nombre_tickets // 100
        couleur = obtenir_couleur_poste(poste)
        existe_deja = poste.id in postes_existants
        code_temp = generer_code_securisation_temp(exercice, idx)

        qr_base64 = generer_qr_code_base64(
            code=code_temp,
            poste=poste,
            exercice=exercice,
            numero_commande=numero_commande,
            type_periode=type_periode,
            montant=montant,
            nombre_tickets=nombre_tickets,
            nombre_carnets=nombre_carnets
        )

        details_postes.append({
            'numero_ordre': idx,
            'poste': poste,
            'region': poste.region.nom if poste.region else "N/A",
            'montant': montant,
            'nombre_tickets': nombre_tickets,
            'nombre_carnets': nombre_carnets,
            'couleur': couleur.libelle_affichage if couleur else "Non définie",
            'couleur_obj': couleur,
            'existe_deja': existe_deja,
            'code_securisation': code_temp,
            'qr_base64': qr_base64,
        })

        montant_total += montant
        nombre_tickets_total += nombre_tickets
        nombre_carnets_total += nombre_carnets

    # Traitement POST
    if request.method == 'POST':
        form = ConfirmationCommandeForm(request.POST)

        if form.is_valid():
            ecraser = form.cleaned_data.get('ecraser_existants', False)

            try:
                with transaction.atomic():
                    if commande_existante:
                        commande = commande_existante
                        action_type = "mise à jour"
                    else:
                        commande = CommandeTickets.objects.create(
                            numero_commande=numero_commande,
                            exercice=exercice,
                            type_periode=type_periode,
                            mois=int(mois) if mois else None,
                            trimestre=int(trimestre) if trimestre else None,
                            semestre=int(semestre) if semestre else None,
                            description=description,
                            cree_par=user,
                            statut='brouillon'
                        )
                        action_type = "création"

                    details_crees = 0
                    details_ecrases = 0
                    carnets_modifies = 0

                    for detail_data in details_postes:
                        poste = detail_data['poste']

                        carnets_form = request.POST.get(f'carnets_{poste.id}')
                        if carnets_form:
                            try:
                                nombre_carnets_final = int(carnets_form)
                                if nombre_carnets_final != detail_data['nombre_carnets']:
                                    carnets_modifies += 1
                            except (ValueError, TypeError):
                                nombre_carnets_final = detail_data['nombre_carnets']
                        else:
                            nombre_carnets_final = detail_data['nombre_carnets']

                        nombre_tickets_final = nombre_carnets_final * 100
                        montant_final = Decimal(nombre_carnets_final * 50000)

                        detail_existant = DetailCommandePoste.objects.filter(
                            commande=commande,
                            poste=poste
                        ).first()

                        if detail_existant:
                            if ecraser:
                                detail_existant.delete()
                                details_ecrases += 1
                            else:
                                continue

                        nouveau_detail = DetailCommandePoste.objects.create(
                            commande=commande,
                            poste=poste,
                            numero_ordre=detail_data['numero_ordre'],
                            montant_commande=montant_final,
                            nombre_tickets=nombre_tickets_final,
                            nombre_carnets=nombre_carnets_final,
                            couleur_tickets=detail_data['couleur_obj']
                        )

                        # Générer et sauvegarder le code de sécurisation
                        nouveau_detail.code_securisation = generer_code_securisation_final(
                            exercice,
                            nouveau_detail.id
                        )
                        nouveau_detail.save(update_fields=['code_securisation'])

                        details_crees += 1

                    commande.recalculer_totaux()

                    # Nettoyer la session
                    for key in ['commande_postes_ids', 'commande_numero', 'commande_exercice',
                               'commande_type_periode', 'commande_mois', 'commande_trimestre',
                               'commande_semestre', 'commande_description']:
                        request.session.pop(key, None)

                    log_user_action(
                        user,
                        f"Commande tickets {action_type}",
                        f"Commande n°{numero_commande} ({exercice}) - {details_crees} poste(s) - Montant: {commande.montant_total} FCFA",
                        request
                    )

                    messages.success(
                        request,
                        f"✅ Commande n°{numero_commande} enregistrée avec succès ! "
                        f"{details_crees} poste(s) ajouté(s)"
                        f"{f', {details_ecrases} écrasé(s)' if details_ecrases else ''}"
                        f"{f', {carnets_modifies} quantité(s) ajustée(s)' if carnets_modifies else ''}"
                    )

                    return redirect('inventaire:detail_commande', commande_id=commande.id)

            except Exception as e:
                logger.error(f"Erreur création commande: {str(e)}", exc_info=True)
                messages.error(request, f"Erreur lors de l'enregistrement: {str(e)}")
    else:
        form = ConfirmationCommandeForm()

    ordinal = CommandeTickets._get_ordinal(numero_commande)
    titre_commande = f"{ordinal} Commande des tickets de l'année {exercice}"

    periode_desc = ""
    if type_periode == 'mensuelle' and mois:
        mois_noms = dict(CommandeTickets.MOIS_CHOICES)
        periode_desc = f"Mois de {mois_noms.get(int(mois), mois)}"
    elif type_periode == 'trimestrielle' and trimestre:
        trim_noms = dict(CommandeTickets.TRIMESTRE_CHOICES)
        periode_desc = trim_noms.get(int(trimestre), f"Trimestre {trimestre}")
    elif type_periode == 'semestrielle' and semestre:
        sem_noms = dict(CommandeTickets.SEMESTRE_CHOICES)
        periode_desc = sem_noms.get(int(semestre), f"Semestre {semestre}")
    else:
        periode_desc = f"Année {exercice}"

    context = {
        'form': form,
        'titre_commande': titre_commande,
        'periode_desc': periode_desc,
        'details_postes': details_postes,
        'montant_total': montant_total,
        'nombre_tickets_total': nombre_tickets_total,
        'nombre_carnets_total': nombre_carnets_total,
        'nb_postes': len(details_postes),
        'commande_existante': commande_existante,
        'has_postes_existants': len(postes_existants) > 0,
        'postes_ids': ','.join(map(str, postes_ids)),
        'title': 'Simulateur de Commandes - Étape 2: Validation',
        'etape': 2,
        'etapes_total': 2,
        'exercice': exercice,
        'numero_commande': numero_commande,
    }

    return render(request, 'inventaire/commandes/etape2_validation.html', context)
    # ===================================================================
# VUES COMMANDES - LISTE ET DÉTAIL
# ===================================================================

@login_required
def liste_commandes(request):
    """
    Liste des commandes avec filtres.
    Les boutons modifier/supprimer sont visibles uniquement pour les admins.
    """
    user = request.user

    if not peut_gerer_commandes(user):
        messages.error(request, "Vous n'avez pas la permission d'accéder aux commandes.")
        return redirect('common:dashboard')

    # Formulaire de filtrage
    form = FiltreCommandesForm(request.GET)

    # Requête de base
    queryset = CommandeTickets.objects.all().select_related(
        'cree_par', 'valide_par'
    ).prefetch_related('details').order_by('-exercice', '-numero_commande', '-date_creation')

    # Appliquer les filtres
    if form.is_valid():
        if form.cleaned_data.get('exercice'):
            queryset = queryset.filter(exercice=form.cleaned_data['exercice'])
        if form.cleaned_data.get('numero_commande'):
            queryset = queryset.filter(numero_commande=form.cleaned_data['numero_commande'])
        if form.cleaned_data.get('statut'):
            queryset = queryset.filter(statut=form.cleaned_data['statut'])
        if form.cleaned_data.get('type_periode'):
            queryset = queryset.filter(type_periode=form.cleaned_data['type_periode'])

    # Pagination
    paginator = Paginator(queryset, 20)
    page = request.GET.get('page', 1)
    commandes = paginator.get_page(page)

    # Calculer les taux de livraison pour chaque commande
    for commande in commandes:
        commande.taux_livraison = commande.get_taux_livraison()

    # Log de l'accès
    log_user_action(
        user,
        "Consultation liste commandes",
        f"Affichage de la liste des commandes - Page {page}",
        request
        )


    # ===== CALCUL DES STATISTIQUES =====
    # Totaux commandes/montant/carnets commandés (sur le queryset filtré,
    # donc respecte automatiquement le filtre Exercice/Statut/Période
    # choisi par l'utilisateur, pas seulement la page affichée).
    stats_agg = queryset.aggregate(
        total_commandes=Count('id'),
        total_montant=Sum('montant_total'),
        total_carnets=Sum('nombre_carnets_total'),
    )

    # Carnets réellement livrés, calculé séparément pour éviter le
    # gonflement des totaux par jointure (aggregate direct sur
    # CommandeTickets + Sum('details__carnets_livres') dans le MÊME
    # appel ferait remonter des doublons à cause du JOIN vers
    # DetailCommandePoste).
    carnets_livres_agg = queryset.aggregate(
        total_carnets_livres=Sum('details__carnets_livres')
    )
    total_carnets_livres = carnets_livres_agg['total_carnets_livres'] or 0
    total_carnets_commandes = stats_agg['total_carnets'] or 0

    # Taux de livraison moyen pondéré par les carnets:
    # (carnets livrés de toutes les commandes filtrées) / (carnets
    # commandés de toutes les commandes filtrées) x 100.
    # Remplace l'ancienne moyenne simple des % par commande, qui
    # donnait le même poids à une petite commande qu'à une grosse.
    taux_livraison_moyen = (
        (total_carnets_livres / total_carnets_commandes) * 100
    ) if total_carnets_commandes > 0 else 0

    stats = {
        'total_commandes': stats_agg['total_commandes'] or 0,
        'total_montant': stats_agg['total_montant'] or Decimal('0'),
        'total_carnets': total_carnets_commandes,
        'taux_livraison_moyen': round(taux_livraison_moyen, 2),
    }

    context = {
        'commandes': commandes,
        'form': form,
        'stats': stats,
        'peut_administrer': peut_administrer_commandes(user),
        'title': 'Liste des Commandes de Tickets',
    }

    return render(request, 'inventaire/commandes/liste_commandes.html', context)


@login_required
def detail_commande(request, commande_id):
    """
    Détail d'une commande avec tableau des postes.
    """
    user = request.user

    if not peut_gerer_commandes(user):
        messages.error(request, "Vous n'avez pas la permission d'accéder à cette commande.")
        return redirect('common:dashboard')

    commande = get_object_or_404(
        CommandeTickets.objects.select_related('cree_par', 'valide_par'),
        id=commande_id
    )

    details = commande.details.all().select_related(
        'poste', 'poste__region', 'couleur_tickets'
    ).order_by('numero_ordre')

    # ✅ CORRECTION: Vérifier les carnets_livres au lieu des livraisons
    # Un poste peut être supprimé si carnets_livres == 0
    for detail in details:
        # Si carnets_livres > 0, le poste ne peut pas être supprimé
        detail.peut_supprimer = (detail.carnets_livres or 0) == 0

    log_user_action(
        user,
        "Consultation détail commande",
        f"Détail commande n°{commande.numero_commande} ({commande.exercice})",
        request
    )

    context = {
        'commande': commande,
        'details': details,
        'peut_administrer': peut_administrer_commandes(user),
        'peut_livrer': peut_gerer_livraisons(user),
        'title': f"Détail Commande n°{commande.numero_commande} - {commande.exercice}",
    }

    return render(request, 'inventaire/commandes/detail_commande.html', context)

@login_required
def modifier_commande(request, commande_id):
    """
    Modification d'une commande (admin uniquement).
    Limité aux champs modifiables.
    """
    user = request.user

    if not peut_administrer_commandes(user):
        log_user_action(
            user=user,
            action="ACCÈS REFUSÉ - Modification commande",
            description=f"Tentative de modification de la commande {commande_id} sans autorisation",
            details={},
            niveau='warning'
        )
        messages.error(request, "Vous n'avez pas la permission de modifier cette commande.")
        return redirect('inventaire:liste_commandes')

    commande = get_object_or_404(CommandeTickets, id=commande_id)

    if request.method == 'POST':
        form = ModificationCommandeForm(request.POST, instance=commande)

        if form.is_valid():
            ancien_statut = commande.statut
            commande = form.save()

            # Si passage à validée, enregistrer la validation
            if ancien_statut != 'validee' and commande.statut == 'validee':
                commande.valider(user)

            log_user_action(
                user=user,
                action="Modification commande",
                description=(
                    f"{user.get_full_name() or user.username} a modifié la commande "
                    f"n°{commande.numero_commande} ({commande.exercice})"
                ),
                details={
                    'commande_id': commande.id,
                    'ancien_statut': ancien_statut,
                    'nouveau_statut': commande.statut,
                },
                niveau='info'
            )

            messages.success(request, "Commande modifiée avec succès.")
            return redirect('inventaire:detail_commande', commande_id=commande.id)
    else:
        form = ModificationCommandeForm(instance=commande)

    context = {
        'form': form,
        'commande': commande,
        'title': f"Modifier Commande n°{commande.numero_commande}",
    }

    return render(request, 'inventaire/commandes/modifier_commande.html', context)


@login_required
@require_POST
def supprimer_commande(request, commande_id):
    """
    Suppression d'une commande (admin uniquement).
    """
    user = request.user

    if not peut_administrer_commandes(user):
        log_user_action(
            user=user,
            action="ACCÈS REFUSÉ - Suppression commande",
            description=f"Tentative de suppression de la commande {commande_id} sans autorisation",
            details={},
            niveau='warning'
        )
        messages.error(request, "Vous n'avez pas la permission de supprimer cette commande.")
        return redirect('inventaire:liste_commandes')

    commande = get_object_or_404(CommandeTickets, id=commande_id)

    # Vérifier si des livraisons sont associées
    if commande.livraisons.exists():
        messages.error(
            request,
            "Impossible de supprimer cette commande car des livraisons y sont associées. "
            "Supprimez d'abord les livraisons."
        )
        return redirect('inventaire:detail_commande', commande_id=commande.id)

    # Stocker les infos avant suppression
    numero = commande.numero_commande
    exercice = commande.exercice
    nb_details = commande.details.count()

    # Supprimer
    commande.delete()

    log_user_action(
        user=user,
        action="Suppression commande",
        description=(
            f"{user.get_full_name() or user.username} a supprimé la commande "
            f"n°{numero} de l'exercice {exercice} ({nb_details} poste(s))"
        ),
        details={
            'numero_commande': numero,
            'exercice': exercice,
            'nb_postes': nb_details,
        },
        niveau='warning'
    )

    messages.success(request, f"Commande n°{numero} supprimée avec succès.")
    return redirect('inventaire:liste_commandes')

@login_required
@require_POST
def supprimer_detail_commande(request, detail_id):
    """
    Supprime un poste (DetailCommandePoste) d'une commande.
    """
    user = request.user

    if not peut_administrer_commandes(user):
        log_user_action(
            user,
            "ACCÈS REFUSÉ - Suppression poste commande",
            f"Tentative suppression détail {detail_id} sans autorisation",
            request
        )
        messages.error(request, "Vous n'avez pas la permission de supprimer ce poste.")
        return redirect('inventaire:liste_commandes')

    detail = get_object_or_404(
        DetailCommandePoste.objects.select_related('commande', 'poste'),
        id=detail_id
    )

    commande = detail.commande
    poste_nom = detail.poste.nom
    commande_id = commande.id

    # ✅ CORRECTION: Vérifier carnets_livres au lieu de chercher des livraisons
    carnets_livres = detail.carnets_livres or 0

    if carnets_livres > 0:
        messages.error(
            request,
            f"Impossible de supprimer le poste {poste_nom} car {carnets_livres} carnet(s) "
            f"ont déjà été livrés. Supprimez d'abord les livraisons de ce poste."
        )
        return redirect('inventaire:detail_commande', commande_id=commande_id)

    # Vérifier qu'il reste au moins 2 postes dans la commande
    nb_postes = commande.details.count()
    if nb_postes <= 1:
        messages.error(
            request,
            "Impossible de supprimer le dernier poste de la commande. "
            "Supprimez plutôt la commande entière."
        )
        return redirect('inventaire:detail_commande', commande_id=commande_id)

    # Stocker les infos avant suppression
    montant_supprime = detail.montant_commande or Decimal('0')
    carnets_supprimes = detail.nombre_carnets or 0

    # Supprimer aussi les livraisons vides associées (si elles existent)
    LivraisonTickets.objects.filter(
        commande=commande,
        poste=detail.poste,
        nombre_carnets_livres=0  # Seulement les livraisons vides
    ).delete()

    # Supprimer le détail
    detail.delete()

    # Recalculer les totaux de la commande
    commande.recalculer_totaux()

    # Renuméroter les postes restants
    for idx, d in enumerate(commande.details.order_by('numero_ordre'), start=1):
        if d.numero_ordre != idx:
            d.numero_ordre = idx
            d.save(update_fields=['numero_ordre'])

    log_user_action(
        user,
        "Suppression poste commande",
        f"Poste {poste_nom} supprimé de la commande n°{commande.numero_commande} - "
        f"Montant: {montant_supprime} FCFA, Carnets: {carnets_supprimes}",
        request
    )

    messages.success(
        request,
        f"✅ Poste {poste_nom} supprimé de la commande. "
        f"({carnets_supprimes} carnets, {montant_supprime:,.0f} FCFA retirés)"
    )

    return redirect('inventaire:detail_commande', commande_id=commande_id)

# ===================================================================
# VUES LIVRAISONS
# ===================================================================
@login_required
def creer_livraison_etape1(request):
    """
    Étape 1: Sélection de la commande et de PLUSIEURS postes.

    MISE À JOUR: On peut maintenant sélectionner plusieurs postes
    via des cases à cocher au lieu d'une liste déroulante.
    """
    user = request.user

    if not peut_gerer_livraisons(user):
        messages.error(request, "Vous n'avez pas la permission de créer des livraisons.")
        return redirect('common:dashboard')

    # Récupérer les commandes disponibles (validées ou en cours)
    commandes = CommandeTickets.objects.filter(
        statut__in=['validee', 'en_cours']
    ).prefetch_related('details', 'details__poste').order_by('-exercice', '-numero_commande')

    # Valeurs par défaut
    commande_selectionnee = None
    postes_disponibles = []

    # Récupérer la commande pré-sélectionnée (GET ou POST)
    commande_id = request.POST.get('commande') or request.GET.get('commande')

    if commande_id:
        try:
            commande_selectionnee = CommandeTickets.objects.prefetch_related(
                'details', 'details__poste', 'details__poste__region'
            ).get(id=commande_id, statut__in=['validee', 'en_cours'])

            # Récupérer les postes de cette commande avec leur statut de livraison
            for detail in commande_selectionnee.details.select_related('poste', 'poste__region').order_by('poste__nom'):
                carnets_commandes = detail.nombre_carnets or 0
                carnets_livres = detail.carnets_livres or 0
                est_complet = carnets_livres >= carnets_commandes if carnets_commandes > 0 else False

                postes_disponibles.append({
                    'id': detail.poste.id,
                    'nom': detail.poste.nom,
                    'code': detail.poste.code if hasattr(detail.poste, 'code') else '',
                    'region': detail.poste.region.nom if detail.poste.region else 'N/A',
                    'carnets_commandes': carnets_commandes,
                    'carnets_livres': carnets_livres,
                    'carnets_restants': max(0, carnets_commandes - carnets_livres),
                    'est_complet': est_complet,
                    'taux_livraison': round((carnets_livres / carnets_commandes * 100) if carnets_commandes > 0 else 0, 2),
                })

        except CommandeTickets.DoesNotExist:
            messages.warning(request, "Commande non trouvée ou non disponible.")
            commande_id = None

    # Traitement du formulaire complet (commande + postes sélectionnés)
    if request.method == 'POST':
        # Récupérer les postes cochés (MULTIPLE)
        postes_ids = request.POST.getlist('postes')
        date_livraison = request.POST.get('date_livraison')
        exercice_recharges = request.POST.get('exercice_recharges')
        observations = request.POST.get('observations', '')

        # Si tous les champs requis sont remplis, passer à l'étape 2
        if commande_id and postes_ids and date_livraison and exercice_recharges:
            # Vérifier que les postes appartiennent à la commande
            try:
                details_valides = DetailCommandePoste.objects.filter(
                    commande_id=commande_id,
                    poste_id__in=postes_ids
                ).select_related('poste')

                if details_valides.count() != len(postes_ids):
                    messages.error(request, "Certains postes sélectionnés n'appartiennent pas à cette commande.")
                else:
                    # Stocker en session
                    request.session['livraison_commande_id'] = int(commande_id)
                    request.session['livraison_postes_ids'] = [int(pid) for pid in postes_ids]
                    request.session['livraison_date'] = date_livraison
                    request.session['livraison_exercice'] = int(exercice_recharges)
                    request.session['livraison_observations'] = observations

                    log_user_action(
                        user=user,
                        action="Création livraison multi-postes - Étape 1 validée",
                        description=f"Sélection commande n°{commande_selectionnee.numero_commande}, {len(postes_ids)} poste(s)",
                        details={
                            'commande_id': commande_id,
                            'postes_ids': postes_ids,
                            'date_livraison': date_livraison,
                        },
                        niveau='info'
                    )

                    return redirect('inventaire:creer_livraison_etape2')

            except Exception as e:
                messages.error(request, f"Erreur: {str(e)}")

        elif commande_id and not postes_ids:
            # Commande sélectionnée mais pas de postes cochés
            # On reste sur la page pour afficher les postes
            pass

    # Préparer les choix d'exercice
    annee_courante = timezone.now().year
    exercices = [
        (annee_courante - 1, str(annee_courante - 1)),
        (annee_courante, str(annee_courante)),
    ]

    # Date par défaut
    date_defaut = timezone.now().date().isoformat()

    # Postes pré-cochés (en cas de rechargement)
    postes_coches = request.POST.getlist('postes') if request.method == 'POST' else []

    context = {
        'commandes': commandes,
        'commande_selectionnee': commande_selectionnee,
        'postes_disponibles': postes_disponibles,
        'postes_coches': [int(p) for p in postes_coches],
        'exercices': exercices,
        'exercice_defaut': annee_courante,
        'date_defaut': date_defaut,
        'title': 'Créer une Livraison - Étape 1: Sélection',
        'etape': 1,
        # Conserver les valeurs du formulaire
        'date_livraison': request.POST.get('date_livraison', date_defaut),
        'exercice_recharges': request.POST.get('exercice_recharges', str(annee_courante)),
        'observations': request.POST.get('observations', ''),
    }

    return render(request, 'inventaire/commandes/livraisons/creer_etape1.html', context)


@login_required
def creer_livraison_etape2(request):
    """
    Étape 2: Sélection des recharges imprimerie nationale pour CHAQUE poste.

    MISE À JOUR: Affiche un tableau séparé par poste avec les recharges
    disponibles pour chaque poste. Chaque poste a ses propres checkboxes.
    """
    user = request.user

    if not peut_gerer_livraisons(user):
        messages.error(request, "Vous n'avez pas la permission de créer des livraisons.")
        return redirect('common:dashboard')

    # Récupérer les données de session
    commande_id = request.session.get('livraison_commande_id')
    postes_ids = request.session.get('livraison_postes_ids', [])
    date_str = request.session.get('livraison_date')
    exercice = request.session.get('livraison_exercice')
    observations = request.session.get('livraison_observations', '')

    if not all([commande_id, postes_ids, date_str, exercice]):
        messages.warning(request, "Session expirée. Veuillez recommencer.")
        return redirect('inventaire:creer_livraison_etape1')

    commande = get_object_or_404(CommandeTickets, id=commande_id)

    # Parser la date
    try:
        date_livraison = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        date_livraison = timezone.now().date()

    # Récupérer les postes et leurs détails de commande
    postes_data = []

    for poste_id in postes_ids:
        try:
            poste = Poste.objects.select_related('region').get(id=poste_id)
            detail_commande = DetailCommandePoste.objects.get(
                commande=commande,
                poste=poste
            )

            # Récupérer les recharges disponibles pour ce poste
            recharges_query = HistoriqueStock.objects.filter(
                poste=poste,
                type_mouvement='CREDIT',
                type_stock='imprimerie_nationale',
                date_mouvement__year=exercice
            ).order_by('-date_mouvement')

            # Exclure les recharges déjà associées à des livraisons
            livrees_ids = LivraisonTickets.objects.filter(
                poste=poste
            ).values_list('historiques_associes__id', flat=True)
            recharges_disponibles = recharges_query.exclude(id__in=livrees_ids)

            # Préparer les données des recharges
            recharges_list = []
            for r in recharges_disponibles:
                recharges_list.append({
                    'id': r.id,
                    'date': r.date_mouvement,
                    'montant': r.montant or Decimal('0'),
                    'nombre_tickets': r.nombre_tickets or 0,
                    'nombre_carnets': (r.nombre_tickets or 0) // 100,
                    'commentaire': r.commentaire or '',
                })

            # Calculer les besoins
            carnets_commandes = detail_commande.nombre_carnets or 0
            carnets_deja_livres = detail_commande.carnets_livres or 0
            carnets_restants = max(0, carnets_commandes - carnets_deja_livres)

            postes_data.append({
                'poste': poste,
                'detail_commande': detail_commande,
                'recharges': recharges_list,
                'carnets_commandes': carnets_commandes,
                'carnets_deja_livres': carnets_deja_livres,
                'carnets_restants': carnets_restants,
                'taux_livraison': round((carnets_deja_livres / carnets_commandes * 100) if carnets_commandes > 0 else 0, 2),
                'has_recharges': len(recharges_list) > 0,
            })

        except (Poste.DoesNotExist, DetailCommandePoste.DoesNotExist):
            continue

    if not postes_data:
        messages.error(request, "Aucun poste valide trouvé.")
        return redirect('inventaire:creer_livraison_etape1')

    # Traitement POST: création des livraisons
    if request.method == 'POST':
        try:
            with transaction.atomic():
                livraisons_creees = 0
                total_carnets_livres = 0
                postes_livres = []

                for poste_data in postes_data:
                    poste = poste_data['poste']
                    detail_commande = poste_data['detail_commande']

                    # Récupérer les recharges cochées pour ce poste
                    recharges_ids = request.POST.getlist(f'recharges_{poste.id}')

                    if not recharges_ids:
                        # Pas de recharges sélectionnées pour ce poste, on passe
                        continue

                    # Récupérer les recharges sélectionnées
                    recharges_selectionnees = HistoriqueStock.objects.filter(
                        id__in=recharges_ids,
                        poste=poste
                    )

                    if not recharges_selectionnees.exists():
                        continue

                    # Calculer les totaux
                    montant_livre = sum(r.montant or 0 for r in recharges_selectionnees)
                    tickets_livres = sum(r.nombre_tickets or 0 for r in recharges_selectionnees)
                    carnets_livres = tickets_livres // 100

                    # Créer la livraison
                    livraison = LivraisonTickets.objects.create(
                        commande=commande,
                        detail_commande=detail_commande,
                        poste=poste,
                        date_livraison=date_livraison,
                        montant_livre=montant_livre,
                        nombre_tickets_livres=tickets_livres,
                        nombre_carnets_livres=carnets_livres,
                        observations=observations,
                        cree_par=user,
                    )

                    # Associer les recharges
                    livraison.historiques_associes.add(*recharges_selectionnees)

                    livraisons_creees += 1
                    total_carnets_livres += carnets_livres
                    postes_livres.append(poste.nom)

                if livraisons_creees == 0:
                    messages.warning(request, "Aucune recharge sélectionnée. Aucune livraison créée.")
                    return redirect('inventaire:creer_livraison_etape2')

                # Nettoyer la session
                for key in ['livraison_commande_id', 'livraison_postes_ids',
                           'livraison_date', 'livraison_exercice', 'livraison_observations']:
                    request.session.pop(key, None)

                log_user_action(
                    user=user,
                    action="Création livraison multi-postes",
                    description=(
                        f"{user.get_full_name() or user.username} a créé {livraisons_creees} livraison(s) "
                        f"pour la commande n°{commande.numero_commande} "
                        f"({total_carnets_livres} carnets au total)"
                    ),
                    details={
                        'commande_id': commande.id,
                        'nb_livraisons': livraisons_creees,
                        'postes': postes_livres,
                        'total_carnets': total_carnets_livres,
                    },
                    niveau='info'
                )

                messages.success(
                    request,
                    f"✅ {livraisons_creees} livraison(s) créée(s) avec succès ! "
                    f"{total_carnets_livres} carnets livrés au total pour: {', '.join(postes_livres)}"
                )

                return redirect('inventaire:detail_commande', commande_id=commande.id)

        except Exception as e:
            logger.error(f"Erreur création livraisons multi-postes: {str(e)}", exc_info=True)
            messages.error(request, f"Erreur lors de l'enregistrement: {str(e)}")

    context = {
        'commande': commande,
        'postes_data': postes_data,
        'date_livraison': date_livraison,
        'exercice': exercice,
        'observations': observations,
        'nb_postes': len(postes_data),
        'title': 'Créer une Livraison - Étape 2: Sélection des recharges',
        'etape': 2,
    }

    return render(request, 'inventaire/commandes/livraisons/creer_etape2.html', context)

@login_required
def liste_livraisons(request):
    """
    Liste des livraisons avec filtres.
    CORRECTION: Affichage correct du créateur.
    """
    user = request.user

    if not peut_gerer_livraisons(user):
        messages.error(request, "Vous n'avez pas la permission d'accéder aux livraisons.")
        return redirect('common:dashboard')

    form = FiltreLivraisonsForm(request.GET)

    queryset = LivraisonTickets.objects.all().select_related(
        'commande', 'poste', 'poste__region', 'detail_commande', 'cree_par'
    ).prefetch_related('historiques_associes').order_by('-date_livraison', '-date_creation')

    # Appliquer les filtres
    if form.is_valid():
        if form.cleaned_data.get('commande'):
            queryset = queryset.filter(commande=form.cleaned_data['commande'])
        if form.cleaned_data.get('poste'):
            queryset = queryset.filter(poste=form.cleaned_data['poste'])
        if form.cleaned_data.get('date_debut'):
            queryset = queryset.filter(date_livraison__gte=form.cleaned_data['date_debut'])
        if form.cleaned_data.get('date_fin'):
            queryset = queryset.filter(date_livraison__lte=form.cleaned_data['date_fin'])

    # Enrichir les données pour l'affichage
    livraisons_data = []
    for livraison in queryset:
        # Correction affichage créateur
        if livraison.cree_par:
            nom_createur = livraison.cree_par.nom_complet or livraison.cree_par.username
        else:
            nom_createur = "N/A"

        livraisons_data.append({
            'livraison': livraison,
            'nom_createur': nom_createur,
            'nb_recharges': livraison.historiques_associes.count(),
        })

    paginator = Paginator(livraisons_data, 20)
    page = request.GET.get('page', 1)
    livraisons_page = paginator.get_page(page)

    context = {
        'livraisons': livraisons_page,
        'form': form,
        'peut_administrer': peut_administrer_commandes(user),
        'title': 'Liste des Livraisons',
    }

    return render(request, 'inventaire/commandes/livraisons/liste.html', context)


@login_required
def tableau_livraisons_commande(request, commande_id):
    """
    Tableau de suivi des livraisons pour une commande spécifique.
    Affiche le taux de progression pour chaque poste.

    CORRECTION: Calculer toutes les variables nécessaires au template.
    """
    user = request.user

    if not peut_gerer_livraisons(user):
        messages.error(request, "Vous n'avez pas la permission d'accéder à cette fonctionnalité.")
        return redirect('common:dashboard')

    commande = get_object_or_404(
        CommandeTickets.objects.select_related('cree_par'),
        id=commande_id
    )

    # Récupérer les détails avec annotations
    details = commande.details.all().select_related(
        'poste', 'poste__region'
    ).prefetch_related('livraisons').annotate(
        montant_livre_total=Sum('livraisons__montant_livre')
    ).order_by('numero_ordre')

    # Préparer les données enrichies pour le template
    details_suivi = []
    total_carnets_commande = 0
    total_carnets_livres = 0
    total_montant_commande = Decimal('0')
    total_montant_livre = Decimal('0')
    postes_complets = 0

    for detail in details:
        # Calculs pour ce poste
        carnets_commandes = detail.nombre_carnets or 0
        carnets_livres = detail.carnets_livres or 0
        carnets_restants = max(0, carnets_commandes - carnets_livres)

        montant_commande = detail.montant_commande or Decimal('0')
        montant_livre = detail.montant_livre_total or Decimal('0')
        montant_restant = max(Decimal('0'), montant_commande - montant_livre)

        # Taux de progression
        taux = round((carnets_livres / carnets_commandes * 100) if carnets_commandes > 0 else 0, 2)

        # Statut
        est_complet = carnets_livres >= carnets_commandes if carnets_commandes > 0 else False

        # Dernière livraison
        derniere_livraison = detail.livraisons.order_by('-date_livraison').first()

        details_suivi.append({
            'poste': detail.poste,
            'nombre_carnets': carnets_commandes,
            'carnets_livres': carnets_livres,
            'carnets_restants': carnets_restants,
            'montant_commande': montant_commande,
            'montant_livre': montant_livre,
            'montant_restant': montant_restant,
            'taux': taux,
            'est_complet': est_complet,
            'derniere_livraison': derniere_livraison,
        })

        # Totaux
        total_carnets_commande += carnets_commandes
        total_carnets_livres += carnets_livres
        total_montant_commande += montant_commande
        total_montant_livre += montant_livre

        if est_complet:
            postes_complets += 1

    # Calculs globaux
    total_montant_restant = max(Decimal('0'), total_montant_commande - total_montant_livre)
    taux_global = round((total_carnets_livres / total_carnets_commande * 100) if total_carnets_commande > 0 else 0, 2)

    context = {
        'commande': commande,
        'details_suivi': details_suivi,
        'taux_global': taux_global,
        'postes_complets': postes_complets,
        'total_carnets_commande': total_carnets_commande,
        'total_carnets_livres': total_carnets_livres,
        'total_montant_commande': total_montant_commande,
        'total_montant_livre': total_montant_livre,
        'total_montant_restant': total_montant_restant,
        'title': f"Suivi Livraisons - Commande n°{commande.numero_commande}",
    }

    return render(request, 'inventaire/commandes/livraisons/tableau_commande.html', context)


@login_required
def modifier_livraison(request, livraison_id):
    """
    Modification d'une livraison.
    """
    user = request.user

    if not peut_administrer_commandes(user):
        messages.error(request, "Vous n'avez pas la permission de modifier cette livraison.")
        return redirect('inventaire:liste_livraisons')

    livraison = get_object_or_404(LivraisonTickets, id=livraison_id)

    if request.method == 'POST':
        form = ModificationLivraisonForm(request.POST, instance=livraison)

        if form.is_valid():
            livraison = form.save()

            log_user_action(
                user=user,
                action="Modification livraison",
                description=(
                    f"{user.get_full_name() or user.username} a modifié la livraison "
                    f"du poste {livraison.poste.nom}"
                ),
                details={
                    'livraison_id': livraison.id,
                    'commande_id': livraison.commande.id,
                },
                niveau='info'
            )

            messages.success(request, "Livraison modifiée avec succès.")
            return redirect('inventaire:detail_commande', commande_id=livraison.commande.id)
    else:
        form = ModificationLivraisonForm(instance=livraison)

    context = {
        'form': form,
        'livraison': livraison,
        'title': f"Modifier Livraison - {livraison.poste.nom}",
    }

    return render(request, 'inventaire/commandes/livraisons/modifier.html', context)


@login_required
@require_POST
def supprimer_livraison(request, livraison_id):
    """
    Suppression d'une livraison.
    """
    user = request.user

    if not peut_administrer_commandes(user):
        messages.error(request, "Vous n'avez pas la permission de supprimer cette livraison.")
        return redirect('inventaire:liste_livraisons')

    livraison = get_object_or_404(LivraisonTickets, id=livraison_id)
    commande_id = livraison.commande.id
    poste_nom = livraison.poste.nom

    with transaction.atomic():
        livraison.delete()

    log_user_action(
        user=user,
        action="Suppression livraison",
        description=(
            f"{user.get_full_name() or user.username} a supprimé la livraison "
            f"du poste {poste_nom}"
        ),
        details={
            'commande_id': commande_id,
            'poste': poste_nom,
        },
        niveau='warning'
    )

    messages.success(request, f"Livraison du poste {poste_nom} supprimée.")
    return redirect('inventaire:detail_commande', commande_id=commande_id)


# ===================================================================
# API ENDPOINTS
# ===================================================================

@login_required
def api_postes_commande(request, commande_id):
    """
    API: Retourne les postes disponibles pour une commande.
    Utilisé pour le rechargement dynamique du formulaire de livraison.
    """
    try:
        commande = CommandeTickets.objects.get(id=commande_id)
        postes = commande.details.select_related('poste', 'poste__region').values(
            'poste__id', 'poste__nom', 'poste__code', 'poste__region__nom',
            'nombre_carnets', 'carnets_livres', 'est_complet'
        )

        data = []
        for p in postes:
            data.append({
                'id': p['poste__id'],
                'nom': p['poste__nom'],
                'code': p['poste__code'],
                'region': p['poste__region__nom'] or 'N/A',
                'carnets_commandes': p['nombre_carnets'],
                'carnets_livres': p['carnets_livres'],
                'est_complet': p['est_complet'],
            })

        return JsonResponse({'success': True, 'postes': data})

    except CommandeTickets.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Commande non trouvée'}, status=404)


@login_required
def api_recharges_poste(request, poste_id):
    """
    API: Retourne les recharges disponibles pour un poste et un exercice.
    """
    exercice = request.GET.get('exercice', timezone.now().year)

    try:
        poste = Poste.objects.get(id=poste_id)

        recharges = HistoriqueStock.objects.filter(
            poste=poste,
            type_mouvement='CREDIT',
            type_stock='imprimerie_nationale',
            date_mouvement__year=exercice
        ).order_by('-date_mouvement')

        # Exclure les déjà livrées
        livrees_ids = LivraisonTickets.objects.filter(
            poste=poste
        ).values_list('historiques_associes__id', flat=True)
        recharges = recharges.exclude(id__in=livrees_ids)

        data = []
        for r in recharges:
            data.append({
                'id': r.id,
                'date': r.date_mouvement.strftime('%d/%m/%Y'),
                'montant': str(r.montant),
                'tickets': r.nombre_tickets,
                'carnets': r.nombre_tickets // 100,
                'commentaire': r.commentaire or '',
            })

        return JsonResponse({'success': True, 'recharges': data})

    except Poste.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Poste non trouvé'}, status=404)


@csrf_exempt
def api_verifier_qr(request):
    """
    API PUBLIQUE: Vérifie l'authenticité d'un QR code.
    Accessible sans authentification pour permettre la vérification mobile.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)

    try:
        data = json.loads(request.body)
        qr_data = data.get('qr_data')

        if not qr_data:
            return JsonResponse({'success': False, 'error': 'Données QR manquantes'})

        # Utiliser la fonction de vérification locale
        valide, resultat = verifier_qr_code(qr_data)

        if not valide:
            return JsonResponse({
                'success': False,
                'error': resultat
            })

        return JsonResponse({
            'success': True,
            'valid': True,
            'data': resultat
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)
    except Exception as e:
        logger.error(f"Erreur vérification QR: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Erreur serveur'}, status=500)


# ===================================================================
# VUES DE MODIFICATION COMPLÈTE D'UNE COMMANDE
# ===================================================================

@login_required
def modifier_commande_etape1(request, commande_id):
    """
    Étape 1 de modification: Paramètres de la commande.
    Permet de modifier les postes sélectionnés, la période, etc.
    """
    user = request.user

    if not peut_administrer_commandes(user):
        messages.error(request, "Vous n'avez pas la permission de modifier cette commande.")
        return redirect('inventaire:liste_commandes')

    commande = get_object_or_404(
        CommandeTickets.objects.prefetch_related('details', 'details__poste'),
        id=commande_id
    )

    # Vérifier si la commande a des livraisons
    has_livraisons = commande.livraisons.exists()
    if has_livraisons:
        messages.warning(
            request,
            "⚠️ Cette commande a des livraisons associées. "
            "Vous ne pourrez pas retirer les postes ayant déjà reçu des livraisons."
        )

    # Récupérer les IDs des postes actuellement dans la commande
    postes_actuels_ids = list(commande.details.values_list('poste_id', flat=True))

    # Postes avec livraisons (non modifiables)
    postes_avec_livraisons = set(
        commande.livraisons.values_list('poste_id', flat=True)
    )

    # Log de l'accès
    log_user_action(
        user=user,
        action="Accès modification commande",
        description=f"Ouverture de la modification de la commande n°{commande.numero_commande} ({commande.exercice})",
        details={'commande_id': commande.id},
        niveau='info'
    )

    if request.method == 'POST':
        form = ParametresCommandeForm(request.POST)

        if form.is_valid():
            # Extraire les données validées
            postes = form.cleaned_data['postes']
            numero_commande = int(form.cleaned_data['numero_commande'])
            exercice = int(form.cleaned_data['exercice'])
            type_periode = form.cleaned_data['type_periode']
            mois = form.cleaned_data.get('mois')
            trimestre = form.cleaned_data.get('trimestre')
            semestre = form.cleaned_data.get('semestre')
            description = form.cleaned_data.get('description', '')

            # Vérifier que les postes avec livraisons sont toujours inclus
            nouveaux_postes_ids = set(p.id for p in postes)
            postes_manquants = postes_avec_livraisons - nouveaux_postes_ids

            if postes_manquants:
                postes_noms = Poste.objects.filter(id__in=postes_manquants).values_list('nom', flat=True)
                messages.error(
                    request,
                    f"Impossible de retirer les postes ayant des livraisons: {', '.join(postes_noms)}"
                )
            else:
                # Vérifier unicité numéro/exercice si changé
                if (numero_commande != commande.numero_commande or exercice != commande.exercice):
                    autre_commande = CommandeTickets.objects.filter(
                        numero_commande=numero_commande,
                        exercice=exercice
                    ).exclude(id=commande.id).exists()

                    if autre_commande:
                        messages.error(
                            request,
                            f"Une commande n°{numero_commande} existe déjà pour l'exercice {exercice}."
                        )
                        # Continuer l'affichage du formulaire avec l'erreur
                    else:
                        # Stocker en session et passer à l'étape 2
                        request.session['mod_commande_id'] = commande.id
                        request.session['mod_postes_ids'] = [p.id for p in postes]
                        request.session['mod_numero'] = numero_commande
                        request.session['mod_exercice'] = exercice
                        request.session['mod_type_periode'] = type_periode
                        request.session['mod_mois'] = mois
                        request.session['mod_trimestre'] = trimestre
                        request.session['mod_semestre'] = semestre
                        request.session['mod_description'] = description

                        return redirect('inventaire:modifier_commande_etape2', commande_id=commande.id)
                else:
                    # Pas de changement numéro/exercice
                    request.session['mod_commande_id'] = commande.id
                    request.session['mod_postes_ids'] = [p.id for p in postes]
                    request.session['mod_numero'] = numero_commande
                    request.session['mod_exercice'] = exercice
                    request.session['mod_type_periode'] = type_periode
                    request.session['mod_mois'] = mois
                    request.session['mod_trimestre'] = trimestre
                    request.session['mod_semestre'] = semestre
                    request.session['mod_description'] = description

                    return redirect('inventaire:modifier_commande_etape2', commande_id=commande.id)
    else:
        # Pré-remplir le formulaire avec les données actuelles
        initial_data = {
            'numero_commande': commande.numero_commande,
            'exercice': commande.exercice,
            'type_periode': commande.type_periode,
            'mois': commande.mois,
            'trimestre': commande.trimestre,
            'semestre': commande.semestre,
            'description': commande.description or '',
            'postes': Poste.objects.filter(id__in=postes_actuels_ids),
        }
        form = ParametresCommandeForm(initial=initial_data)

    # Récupérer les postes groupés par région
    postes_par_region = {}
    postes = Poste.objects.filter(
        is_active=True,
        type='peage'
    ).select_related('region').order_by('region__nom', 'nom')

    for poste in postes:
        region_nom = poste.region.nom if poste.region else "Sans région"
        if region_nom not in postes_par_region:
            postes_par_region[region_nom] = []

        # Marquer les postes avec livraisons comme verrouillés
        poste.est_verrouille = poste.id in postes_avec_livraisons
        postes_par_region[region_nom].append(poste)

    context = {
        'form': form,
        'commande': commande,
        'postes_par_region': postes_par_region,
        'total_postes': Poste.objects.filter(is_active=True, type='peage').count(),
        'postes_selectionnes': postes_actuels_ids,
        'postes_verrouilles': list(postes_avec_livraisons),
        'title': f'Modifier Commande n°{commande.numero_commande} - Étape 1: Paramètres',
        'etape': 1,
        'etapes_total': 2,
        'has_livraisons': has_livraisons,
    }

    return render(request, 'inventaire/commandes/modifier_etape1.html', context)


@login_required
def modifier_commande_etape2(request, commande_id):
    """
    Étape 2 de modification: Validation et ajustement des quantités.
    """
    user = request.user

    if not peut_administrer_commandes(user):
        messages.error(request, "Vous n'avez pas la permission de modifier cette commande.")
        return redirect('inventaire:liste_commandes')

    commande = get_object_or_404(CommandeTickets, id=commande_id)

    # Récupérer les données de session
    session_commande_id = request.session.get('mod_commande_id')
    postes_ids = request.session.get('mod_postes_ids', [])
    numero_commande = request.session.get('mod_numero')
    exercice = request.session.get('mod_exercice')
    type_periode = request.session.get('mod_type_periode')
    mois = request.session.get('mod_mois')
    trimestre = request.session.get('mod_trimestre')
    semestre = request.session.get('mod_semestre')
    description = request.session.get('mod_description', '')

    # Vérifier que les données sont présentes et cohérentes
    if not postes_ids or session_commande_id != commande.id:
        messages.warning(request, "Session expirée. Veuillez recommencer la modification.")
        return redirect('inventaire:modifier_commande_etape1', commande_id=commande.id)

    # Récupérer les postes
    postes = Poste.objects.filter(id__in=postes_ids).select_related('region').order_by('region__nom', 'nom')

    # Récupérer les détails existants pour pré-charger les valeurs
    details_existants = {
        d.poste_id: d for d in commande.details.select_related('poste', 'couleur_tickets')
    }

    # Calculer les montants et préparer les données pour chaque poste
    details_postes = []
    montant_total = Decimal('0')
    nombre_tickets_total = 0
    nombre_carnets_total = 0

    for idx, poste in enumerate(postes, start=1):
        # Vérifier si ce poste existait déjà dans la commande
        detail_existant = details_existants.get(poste.id)

        if detail_existant:
            # Utiliser les valeurs existantes
            montant = detail_existant.montant_commande or Decimal('0')
            nombre_tickets = detail_existant.nombre_tickets or 0
            nombre_carnets = detail_existant.nombre_carnets or 0
            couleur = detail_existant.couleur_tickets
            code_securisation = detail_existant.code_securisation or generer_code_securisation_temp(exercice, idx)
        else:
            # Nouveau poste: calculer à partir des ventes (avec forecasting)
            montant = calculer_montant_periode(
                poste, exercice, type_periode, mois, trimestre, semestre
            )
            nombre_tickets = int(montant / 500) if montant else 0
            nombre_carnets = nombre_tickets // 100
            couleur = obtenir_couleur_poste(poste)
            code_securisation = generer_code_securisation_temp(exercice, idx)

        # Générer le QR code
        qr_base64 = generer_qr_code_base64(
            code=code_securisation,
            poste=poste,
            exercice=exercice,
            numero_commande=numero_commande,
            type_periode=type_periode,
            montant=montant,
            nombre_tickets=nombre_tickets,
            nombre_carnets=nombre_carnets
        )

        details_postes.append({
            'numero_ordre': idx,
            'poste': poste,
            'region': poste.region.nom if poste.region else "N/A",
            'montant': montant,
            'nombre_tickets': nombre_tickets,
            'nombre_carnets': nombre_carnets,
            'couleur': couleur.libelle_affichage if couleur else "Non définie",
            'couleur_obj': couleur,
            'est_nouveau': detail_existant is None,
            'code_securisation': code_securisation,
            'qr_base64': qr_base64,
        })

        montant_total += montant
        nombre_tickets_total += nombre_tickets
        nombre_carnets_total += nombre_carnets

    # Traitement POST: mise à jour de la commande
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Mettre à jour les champs de la commande
                commande.numero_commande = numero_commande
                commande.exercice = exercice
                commande.type_periode = type_periode
                commande.mois = int(mois) if mois else None
                commande.trimestre = int(trimestre) if trimestre else None
                commande.semestre = int(semestre) if semestre else None
                commande.description = description
                commande.save()

                # Identifier les postes à supprimer (sauf ceux avec livraisons)
                anciens_postes_ids = set(details_existants.keys())
                nouveaux_postes_ids = set(postes_ids)
                postes_a_supprimer = anciens_postes_ids - nouveaux_postes_ids

                # Postes avec livraisons (ne pas supprimer)
                postes_avec_livraisons = set(
                    commande.livraisons.values_list('poste_id', flat=True)
                )
                postes_a_supprimer -= postes_avec_livraisons

                if postes_a_supprimer:
                    DetailCommandePoste.objects.filter(
                        commande=commande,
                        poste_id__in=postes_a_supprimer
                    ).delete()

                # Mettre à jour ou créer les détails
                details_modifies = 0
                details_crees = 0
                carnets_ajustes = 0

                for detail_data in details_postes:
                    poste = detail_data['poste']

                    # Récupérer le nombre de carnets du formulaire
                    carnets_form = request.POST.get(f'carnets_{poste.id}')
                    if carnets_form:
                        try:
                            nombre_carnets_final = int(carnets_form)
                            if nombre_carnets_final != detail_data['nombre_carnets']:
                                carnets_ajustes += 1
                        except (ValueError, TypeError):
                            nombre_carnets_final = detail_data['nombre_carnets']
                    else:
                        nombre_carnets_final = detail_data['nombre_carnets']

                    # Recalculer tickets et montant
                    nombre_tickets_final = nombre_carnets_final * 100
                    montant_final = Decimal(nombre_carnets_final * 50000)

                    # Vérifier si le détail existe
                    detail_existant = details_existants.get(poste.id)

                    if detail_existant:
                        # Mettre à jour
                        detail_existant.numero_ordre = detail_data['numero_ordre']
                        detail_existant.montant_commande = montant_final
                        detail_existant.nombre_tickets = nombre_tickets_final
                        detail_existant.nombre_carnets = nombre_carnets_final
                        detail_existant.couleur_tickets = detail_data['couleur_obj']
                        detail_existant.save()
                        details_modifies += 1
                    else:
                        # Créer nouveau
                        DetailCommandePoste.objects.create(
                            commande=commande,
                            poste=poste,
                            numero_ordre=detail_data['numero_ordre'],
                            montant_commande=montant_final,
                            nombre_tickets=nombre_tickets_final,
                            nombre_carnets=nombre_carnets_final,
                            couleur_tickets=detail_data['couleur_obj']
                        )
                        details_crees += 1

                # Recalculer les totaux
                commande.recalculer_totaux()

                # Nettoyer la session
                for key in ['mod_commande_id', 'mod_postes_ids', 'mod_numero',
                           'mod_exercice', 'mod_type_periode', 'mod_mois',
                           'mod_trimestre', 'mod_semestre', 'mod_description']:
                    request.session.pop(key, None)

                # Log détaillé
                nom_utilisateur = user.nom_complet or user.username
                log_user_action(
                    user=user,
                    action="Modification commande complète",
                    description=(
                        f"{nom_utilisateur} a modifié la commande "
                        f"n°{commande.numero_commande} de l'exercice {commande.exercice}: "
                        f"{details_modifies} mis à jour, {details_crees} créé(s), "
                        f"{len(postes_a_supprimer)} supprimé(s)"
                        f"{f', {carnets_ajustes} quantité(s) ajustée(s)' if carnets_ajustes else ''}"
                    ),
                    details={
                        'commande_id': commande.id,
                        'details_modifies': details_modifies,
                        'details_crees': details_crees,
                        'details_supprimes': len(postes_a_supprimer),
                        'carnets_ajustes': carnets_ajustes,
                        'montant_total': str(commande.montant_total),
                    },
                    niveau='info'
                )

                messages.success(
                    request,
                    f"✅ Commande n°{commande.numero_commande} mise à jour avec succès ! "
                    f"{details_modifies} poste(s) modifié(s), {details_crees} ajouté(s)"
                    f"{f', {len(postes_a_supprimer)} retiré(s)' if postes_a_supprimer else ''}"
                )

                return redirect('inventaire:detail_commande', commande_id=commande.id)

        except Exception as e:
            logger.error(f"Erreur modification commande: {str(e)}", exc_info=True)
            messages.error(request, f"Erreur lors de l'enregistrement: {str(e)}")

    # Générer le titre
    ordinal = CommandeTickets._get_ordinal(numero_commande)
    titre_commande = f"{ordinal} Commande des tickets de l'année {exercice}"

    # Description de la période
    periode_desc = ""
    if type_periode == 'mensuelle' and mois:
        mois_noms = dict(CommandeTickets.MOIS_CHOICES)
        periode_desc = f"Mois de {mois_noms.get(int(mois), mois)}"
    elif type_periode == 'trimestrielle' and trimestre:
        trim_noms = dict(CommandeTickets.TRIMESTRE_CHOICES)
        periode_desc = trim_noms.get(int(trimestre), f"Trimestre {trimestre}")
    elif type_periode == 'semestrielle' and semestre:
        sem_noms = dict(CommandeTickets.SEMESTRE_CHOICES)
        periode_desc = sem_noms.get(int(semestre), f"Semestre {semestre}")
    else:
        periode_desc = f"Année {exercice}"

    context = {
        'commande': commande,
        'titre_commande': titre_commande,
        'periode_desc': periode_desc,
        'details_postes': details_postes,
        'montant_total': montant_total,
        'nombre_tickets_total': nombre_tickets_total,
        'nombre_carnets_total': nombre_carnets_total,
        'nb_postes': len(details_postes),
        'nb_nouveaux': sum(1 for d in details_postes if d['est_nouveau']),
        'title': f'Modifier Commande n°{commande.numero_commande} - Étape 2: Validation',
        'etape': 2,
        'etapes_total': 2,
        'exercice': exercice,
        'numero_commande': numero_commande,
    }

    return render(request, 'inventaire/commandes/modifier_etape2.html', context)