"""
Middleware « filet de sécurité » : transforme toute erreur d'intégrité de la base (doublon non prévu
par une vue) en message clair et détaillé, au lieu d'une page d'erreur 500.
"""
import re  # Analyse du message d'erreur PostgreSQL / SQLite
import logging  # Journalisation technique de l'incident
from django.apps import apps  # Accès à tous les modèles pour retrouver l'enregistrement existant
from django.contrib import messages  # Messages affichés à l'utilisateur
from django.db import IntegrityError  # Exception interceptée
from django.http import HttpResponseRedirect, JsonResponse  # Réponses de remplacement
from django.utils.deprecation import MiddlewareMixin  # Base des middlewares

logger = logging.getLogger('SUPPER')  # Journal applicatif SUPPER


def _extraire_cle(exc):
    """Retourne (champ, valeur) d'un message 'Key (champ)=(valeur) already exists' ; sinon (None, None)."""
    texte = str(exc)  # Message brut de la base
    m = re.search(r"Key \(([^)]+)\)=\(([^)]*)\)", texte)  # Format PostgreSQL
    if m:
        return m.group(1).split(',')[-1].strip(), m.group(2).split(',')[-1].strip()
    m = re.search(r"UNIQUE constraint failed: \w+\.(\w+)", texte)  # Format SQLite (valeur non fournie)
    return (m.group(1), None) if m else (None, None)


def _trouver_existant(champ, valeur):
    """Cherche dans tous les modèles la ligne portant déjà cette valeur unique."""
    from inventaire.services.messages_detail import decrire_objet
    if not champ or not valeur:
        return None
    for modele in apps.get_models():
        try:
            if champ in [f.name for f in modele._meta.concrete_fields]:
                obj = modele.objects.filter(**{champ: valeur}).first()
                if obj:
                    return decrire_objet(obj)  # Description détaillée de l'existant
        except Exception:
            continue
    return None


class ErreurIntegriteMiddleware(MiddlewareMixin):
    """Intercepte IntegrityError et affiche un message détaillé."""

    def process_exception(self, request, exception):
        if not isinstance(exception, IntegrityError):
            return None  # Autres erreurs : comportement normal
        champ, valeur = _extraire_cle(exception)  # Quel champ est en doublon ?
        existant = _trouver_existant(champ, valeur)  # Que contient déjà la base ?
        logger.error("IntegrityError interceptée sur %s : %s", request.path, exception)  # Trace technique
        if champ and ('duplicate' in str(exception).lower() or 'UNIQUE' in str(exception)):
            texte = (f"❌ Enregistrement impossible : la valeur « {valeur or '?'} » du champ « {champ} » existe DÉJÀ."
                     + (f" Déjà enregistré : {existant}." if existant else ""))
        else:
            texte = "❌ Enregistrement impossible : la donnée entre en conflit avec une donnée existante ou manquante."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': texte}, status=409)  # Appels AJAX
        messages.error(request, texte)  # Message visible dans l'interface
        return HttpResponseRedirect(request.META.get('HTTP_REFERER') or request.path)  # Retour au formulaire
