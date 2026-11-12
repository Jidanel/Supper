# common/management/commands/compresser_images.py
# Commande de maintenance : compresse les images DÉJÀ enregistrées (quittances, historiques ACCT, etc.).
# Exemples :
#   python manage.py compresser_images --dry-run            (simulation : affiche le gain sans rien modifier)
#   python manage.py compresser_images                      (compresse et remplace les fichiers)
#   python manage.py compresser_images --min-ko 500 --max-px 1400 --qualite 75
# Sécurité : faites une sauvegarde du dossier media/ avant la première exécution réelle.
# Les originaux sont supprimés après remplacement sauf avec --garder-originaux.

import os  # Taille et suppression de fichiers

from django.apps import apps  # Registre des modèles
from django.core.files.base import ContentFile  # Contenu en mémoire pour l'enregistrement
from django.core.files.storage import default_storage  # Stockage des fichiers (media/)
from django.core.management.base import BaseCommand  # Base d'une commande
from django.db.models import ImageField  # Type de champ concerné

from common.image_service import compresser_octets, nom_jpeg  # Service de compression
from common.signals_images import CHAMPS_EXCLUS  # Champs à ne pas toucher


class Command(BaseCommand):
    help = "Compresse les images déjà enregistrées (réduction de taille et passage en JPEG)."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="Simulation : ne modifie rien")
        parser.add_argument('--min-ko', type=int, default=300, help="Ne traite que les fichiers > N Ko (défaut 300)")
        parser.add_argument('--max-px', type=int, default=None, help="Côté le plus long en pixels (défaut 1600)")
        parser.add_argument('--qualite', type=int, default=None, help="Qualité JPEG 1-95 (défaut 80)")
        parser.add_argument('--garder-originaux', action='store_true', help="Ne supprime pas les anciens fichiers")

    def handle(self, *args, **options):
        total_avant = total_apres = nb_traites = nb_ignores = nb_erreurs = 0  # Compteurs du rapport
        for modele in apps.get_models():  # Parcourt tous les modèles
            for champ in modele._meta.get_fields():
                if not isinstance(champ, ImageField) or f"{modele._meta.label}.{champ.name}" in CHAMPS_EXCLUS:
                    continue  # Ne garde que les champs image non exclus
                for obj in modele.objects.exclude(**{champ.name: ''}).exclude(**{f"{champ.name}__isnull": True}).iterator():
                    ancien_nom = getattr(obj, champ.name).name  # Chemin relatif du fichier actuel
                    if not default_storage.exists(ancien_nom):
                        nb_ignores += 1  # Fichier absent du disque
                        continue
                    taille = default_storage.size(ancien_nom)  # Taille actuelle en octets
                    if taille < options['min_ko'] * 1024:
                        nb_ignores += 1  # Déjà léger : on ne touche pas
                        continue
                    with default_storage.open(ancien_nom, 'rb') as f:
                        donnees = f.read()  # Contenu actuel
                    compresse = compresser_octets(donnees, options['max_px'], options['qualite'])
                    if compresse is None:
                        nb_ignores += 1  # Pas une image, ou aucun gain
                        continue
                    total_avant += taille
                    total_apres += len(compresse)
                    nb_traites += 1
                    self.stdout.write(f"{modele._meta.label}#{obj.pk} {ancien_nom} : "
                                      f"{taille // 1024} Ko -> {len(compresse) // 1024} Ko")
                    if options['dry_run']:
                        continue  # Simulation : rien n'est écrit
                    dossier, nom = os.path.split(nom_jpeg(ancien_nom))  # Même dossier, extension .jpg
                    cible = os.path.join(dossier, nom)  # Nom visé (identique si le fichier était déjà .jpg)
                    if len(cible) > champ.max_length:
                        self.stdout.write(self.style.WARNING(f"   ignoré : nom trop long pour la base ({len(cible)} car.)"))
                        nb_erreurs += 1
                        continue
                    nouveau_nom = None  # Nom réellement enregistré
                    try:
                        if cible == ancien_nom and not options['garder_originaux']:
                            default_storage.delete(ancien_nom)  # Même nom : on libère la place (sinon Django ajoute un suffixe aléatoire)
                        nouveau_nom = default_storage.save(cible, ContentFile(compresse))  # Écrit la version compressée
                        if len(nouveau_nom) > champ.max_length:  # Un suffixe a rendu le nom trop long pour la colonne
                            default_storage.delete(nouveau_nom)  # Annule : pas de fichier orphelin
                            raise ValueError("nom trop long après ajout d'un suffixe")
                        modele.objects.filter(pk=obj.pk).update(**{champ.name: nouveau_nom})  # update() : pas de signal
                    except Exception as exc:  # Une erreur sur une image n'arrête pas toute la commande
                        nb_erreurs += 1
                        self.stdout.write(self.style.ERROR(f"   ERREUR : {exc}"))
                        if cible == ancien_nom and not default_storage.exists(ancien_nom):
                            default_storage.save(ancien_nom, ContentFile(donnees))  # Remet l'original en place
                        continue
                    if nouveau_nom != ancien_nom and not options['garder_originaux']:
                        default_storage.delete(ancien_nom)  # Supprime l'ancien fichier (extension différente)
        gain = (total_avant - total_apres) / 1024 / 1024  # Gain total en Mo
        etat = "SIMULATION - " if options['dry_run'] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{etat}{nb_traites} image(s) compressée(s), {nb_ignores} ignorée(s), {nb_erreurs} erreur(s), gain : {gain:.1f} Mo "
            f"({total_avant / 1024 / 1024:.1f} Mo -> {total_apres / 1024 / 1024:.1f} Mo)"))
