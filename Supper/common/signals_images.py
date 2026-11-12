# common/signals_images.py
# Compression AUTOMATIQUE de toute image téléversée, quel que soit le formulaire ou l'écran d'administration.
# Principe : avant l'enregistrement (pre_save) de chaque modèle qui possède un ImageField, si une NOUVELLE
# image vient d'être téléversée, elle est réduite et recompressée par common.image_service.
# Les fichiers déjà enregistrés ne sont jamais retraités ici (voir la commande compresser_images).

import logging  # Journal technique

from django.apps import apps  # Registre des modèles
from django.db.models import ImageField  # Type de champ concerné
from django.db.models.signals import pre_save  # Signal avant enregistrement

from common.image_service import compresser_fichier_televerse  # Service de compression

logger = logging.getLogger('supper')

# Champs à ne PAS compresser (qualité d'origine voulue), au format 'app.Modele.champ'
CHAMPS_EXCLUS = {'inventaire.ConfigurationGlobale.logo'}


def _compresser_avant_enregistrement(sender, instance, **kwargs):
    """Réduit les nouvelles images de l'instance avant leur écriture sur le disque."""
    for champ in sender._meta.get_fields():
        if not isinstance(champ, ImageField):
            continue  # On ne traite que les champs image
        if f"{sender._meta.label}.{champ.name}" in CHAMPS_EXCLUS:
            continue  # Champ exclu (ex. logo)
        fichier = getattr(instance, champ.name, None)  # FieldFile du champ
        if not fichier or getattr(fichier, '_committed', True):
            continue  # Aucun fichier, ou fichier déjà enregistré : rien à faire
        try:
            nouveau = compresser_fichier_televerse(fichier.file)  # Compression du fichier téléversé
            if nouveau is not fichier.file:  # Un fichier plus léger a été produit
                setattr(instance, champ.name, nouveau)  # Remplace le fichier avant l'écriture
        except Exception:
            logger.exception("Compression impossible pour %s.%s : original conservé", sender._meta.label, champ.name)


def connecter_signaux_images():
    """Branche le signal sur tous les modèles qui ont au moins un ImageField (appelé au démarrage)."""
    for modele in apps.get_models():  # Tous les modèles installés
        if any(isinstance(f, ImageField) for f in modele._meta.get_fields()):
            pre_save.connect(_compresser_avant_enregistrement, sender=modele,
                             dispatch_uid=f"compresser_images_{modele._meta.label}")  # dispatch_uid évite les doublons
