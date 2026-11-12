# common/image_service.py
# Service de compression des images téléversées dans SUPPER (quittances, historiques ACCT, etc.).
# Objectif : une photo de 4 Mo prise au téléphone devient une image de 200 à 400 Ko, toujours lisible.
# Règles :
#   - les images sont réduites à IMAGE_MAX_PX pixels (côté le plus long) et recompressées en JPEG ;
#   - l'orientation des photos de téléphone (EXIF) est corrigée avant la réduction ;
#   - les fichiers qui ne sont pas des images (ex. PDF) ne sont jamais modifiés ;
#   - si le résultat n'est pas plus léger que l'original, l'original est conservé.

import io  # Tampon mémoire pour écrire l'image compressée
import os  # Manipulation des noms de fichiers
import logging  # Journal technique

from django.conf import settings  # Paramètres optionnels du projet
from django.core.files.uploadedfile import InMemoryUploadedFile  # Fichier téléversé en mémoire

logger = logging.getLogger('supper')  # Journal commun de l'application

# Valeurs par défaut, modifiables dans settings.py (IMAGE_MAX_PX, IMAGE_QUALITE)
IMAGE_MAX_PX_DEFAUT = 1600  # Côté le plus long, en pixels
IMAGE_QUALITE_DEFAUT = 80  # Qualité JPEG (1-95)
SEUIL_OCTETS = 200 * 1024  # Les images de moins de 200 Ko sont laissées intactes (déjà légères, texte net)


def _parametres(max_px=None, qualite=None):
    """Retourne (max_px, qualite) en tenant compte des paramètres passés puis de settings.py."""
    max_px = max_px or getattr(settings, 'IMAGE_MAX_PX', IMAGE_MAX_PX_DEFAUT)  # Taille maximale
    qualite = qualite or getattr(settings, 'IMAGE_QUALITE', IMAGE_QUALITE_DEFAUT)  # Qualité JPEG
    return max_px, qualite


def compresser_octets(donnees, max_px=None, qualite=None):
    """Compresse une image donnée en octets.
    Retourne les octets JPEG compressés, ou None si ce n'est pas une image lisible ou si le gain est nul."""
    from PIL import Image, ImageOps  # Import local : Pillow n'est chargé que si on compresse
    max_px, qualite = _parametres(max_px, qualite)
    try:
        img = Image.open(io.BytesIO(donnees))  # Ouvre l'image ; échoue si ce n'est pas une image
        img.load()  # Force la lecture complète (détecte les fichiers corrompus)
    except Exception:
        return None  # PDF, fichier corrompu, etc. : on ne touche à rien
    img = ImageOps.exif_transpose(img)  # Applique la rotation EXIF des photos de téléphone
    if img.mode in ('RGBA', 'LA', 'P'):  # Images avec transparence ou palette
        img = img.convert('RGBA')  # Normalise avant de supprimer la transparence
        fond = Image.new('RGB', img.size, (255, 255, 255))  # Fond blanc (le JPEG n'a pas de transparence)
        fond.paste(img, mask=img.split()[-1])  # Colle l'image sur le fond blanc
        img = fond
    elif img.mode != 'RGB':
        img = img.convert('RGB')  # Niveaux de gris, CMJN, etc. -> RGB
    if max(img.size) > max_px:  # Réduit seulement si l'image est plus grande que la limite
        img.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)  # Garde les proportions
    sortie = io.BytesIO()  # Tampon de sortie
    img.save(sortie, format='JPEG', quality=qualite, optimize=True)  # Écriture JPEG compressée
    resultat = sortie.getvalue()
    return resultat if len(resultat) < len(donnees) else None  # Garde l'original si aucun gain


def nom_jpeg(nom):
    """Remplace l'extension d'un nom de fichier par .jpg."""
    base, _ext = os.path.splitext(nom)  # Sépare le nom et l'extension
    return f"{base}.jpg"


def compresser_fichier_televerse(fichier, max_px=None, qualite=None):
    """Compresse un fichier téléversé (UploadedFile).
    Retourne un nouvel InMemoryUploadedFile compressé, ou le fichier d'origine s'il n'y a rien à gagner."""
    try:
        fichier.seek(0)  # Se place au début du fichier
        donnees = fichier.read()  # Lit tout le contenu
        fichier.seek(0)  # Remet le curseur (le fichier d'origine reste utilisable)
    except Exception:
        return fichier  # Fichier illisible : on ne fait rien
    if len(donnees) < SEUIL_OCTETS:
        return fichier  # Déjà légère : on ne la retouche pas
    compresse = compresser_octets(donnees, max_px, qualite)  # Tente la compression
    if compresse is None:
        return fichier  # Pas une image, ou aucun gain : original conservé
    nom = nom_jpeg(os.path.basename(getattr(fichier, 'name', 'image')))  # Nouveau nom en .jpg
    logger.info("Image compressée : %s (%d Ko -> %d Ko)", nom, len(donnees) // 1024, len(compresse) // 1024)
    return InMemoryUploadedFile(io.BytesIO(compresse), getattr(fichier, 'field_name', None), nom,
                                'image/jpeg', len(compresse), None)  # Fichier prêt à être enregistré
