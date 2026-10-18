# inventaire/models_transporteurs.py
# ===================================================================
# MODÈLES - FICHE D'INVENTAIRE DES TRANSPORTEURS DE PERSONNES
# Fiche papier DGI / PSRR : une fiche = un poste de péage + une date,
# contenant les agences de transport et leurs véhicules passés.
#
# Trois modèles :
#   1. AgenceTransport            : annuaire des agences (noms normalisés)
#   2. InventaireTransporteur     : l'en-tête (poste + date) = la "fiche"
#   3. DetailVehiculeTransporteur : une ligne = un véhicule d'une agence
# ===================================================================

import re                                           # expressions régulières (nettoyage des textes)
import unicodedata                                  # suppression des accents pour la clé de comparaison
import logging                                      # journal technique Django

from django.conf import settings                    # pour référencer le modèle utilisateur
from django.db import models                        # classes de base des modèles
from django.utils import timezone                   # date/heure avec fuseau horaire
from django.utils.translation import gettext_lazy as _   # textes traduisibles FR/EN

logger = logging.getLogger('supper')                # même logger que le reste de SUPPER

# Noms exportés quand models.py fait « from inventaire.models_transporteurs import * »
__all__ = [
    'AgenceTransport', 'InventaireTransporteur', 'DetailVehiculeTransporteur',
    'TypeVehicule', 'normaliser_nom_agence', 'cle_unicite_agence',
    'normaliser_plaque', 'afficher_plaque', 'poste_programme_pour_transporteurs',
]


# ===================================================================
# FONCTIONS DE NORMALISATION (utilisées par les modèles, les vues et l'import)
# ===================================================================

def normaliser_nom_agence(nom):
    """
    Nom d'AFFICHAGE d'une agence : MAJUSCULES, sans espace avant/après,
    un seul espace entre les mots.
    Ex. '  Général   Voyages ' -> 'GÉNÉRAL VOYAGES'
    """
    texte = unicodedata.normalize('NFC', str(nom or ''))   # unifie la forme des caractères accentués
    texte = re.sub(r'\s+', ' ', texte)                      # toute suite d'espaces/tabulations -> un espace
    return texte.strip().upper()                            # retire les bords puis met en majuscules


def cle_unicite_agence(nom):
    """
    Clé de COMPARAISON : deux noms qui donnent la même clé sont la même agence.
    Règles : sans accent, ponctuation = espace, majuscules, et le « S » final
    des mots de plus de 3 lettres est ignoré (VOYAGE = VOYAGES).
    Ex. 'Général voyage' / 'GENERAL  VOYAGES' -> 'GENERAL VOYAGE'
    """
    texte = normaliser_nom_agence(nom)                                   # 1) nom propre
    texte = unicodedata.normalize('NFD', texte)                          # 2) sépare lettre + accent
    texte = ''.join(c for c in texte if unicodedata.category(c) != 'Mn')  # 3) supprime les accents
    texte = re.sub(r'[^A-Z0-9]+', ' ', texte).strip()                    # 4) tout sauf lettres/chiffres -> espace
    mots = []                                                            # liste des mots nettoyés
    for mot in texte.split(' '):                                         # 5) mot par mot
        if len(mot) > 3 and mot.endswith('S'):                           #    pluriel probable
            mot = mot[:-1]                                               #    on retire le S final
        mots.append(mot)                                                 #    on garde le mot
    return ' '.join(mots)                                                # 6) recolle avec un seul espace


def normaliser_plaque(plaque):
    """
    Plaque pour la RECHERCHE : majuscules sans espace, tiret ni point.
    'lt 123-ab' et 'LT123AB' deviennent identiques : 'LT123AB'.
    """
    return re.sub(r'[\s\-\.]+', '', str(plaque or '')).upper()           # supprime séparateurs + majuscules


def afficher_plaque(plaque):
    """Plaque pour l'AFFICHAGE : majuscules, espaces nettoyés."""
    return re.sub(r'\s+', ' ', str(plaque or '')).strip().upper()


def poste_programme_pour_transporteurs(poste, date_saisie):
    """
    RÈGLE MÉTIER : un poste programmé pour l'inventaire (au mois de la date)
    est automatiquement programmé pour les transporteurs.
    On interroge donc ProgrammationInventaire, sans table supplémentaire.
    """
    from inventaire.models import ProgrammationInventaire                # import tardif (évite les imports circulaires)
    return ProgrammationInventaire.objects.filter(                       # cherche une programmation...
        poste=poste,                                                     # ...pour ce poste
        mois=date_saisie.replace(day=1),                                 # ...au mois de la date (1er du mois)
        actif=True,                                                      # ...encore active
    ).exists()                                                           # True / False


# ===================================================================
# TYPES DE VÉHICULES (les 4 cases de la fiche papier)
# ===================================================================

class TypeVehicule(models.TextChoices):
    """Valeur stockée en base = 1re valeur ; libellé affiché = 2e valeur."""
    COASTER = 'coaster', _('Coaster 29-33 places')                       # colonne 1 de la fiche
    BUS_ORDINAIRE = 'bus_ordinaire', _('Grand bus ordinaire 75-80 places')   # colonne 2
    BUS_CLIM = 'bus_clim', _('Grand bus climatisé 55-65 places')         # colonne 3
    HIACE = 'hiace', _('Hiace 16-22 places')                             # colonne 4


# ===================================================================
# 1. AGENCE DE TRANSPORT
# ===================================================================

class AgenceTransport(models.Model):
    """Annuaire des agences de transport de personnes."""

    nom = models.CharField(                                              # nom affiché
        max_length=150, verbose_name=_("Nom de l'agence"))
    cle_unicite = models.CharField(                                      # clé de comparaison (unique)
        max_length=200, unique=True, editable=False,
        verbose_name=_("Clé d'unicité"))
    est_active = models.BooleanField(                                    # agence proposée dans la saisie ?
        default=True, verbose_name=_("Active"))
    cree_par = models.ForeignKey(                                        # qui l'a ajoutée
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='agences_transport_creees',
        verbose_name=_("Créée par"))
    date_creation = models.DateTimeField(                                # quand
        default=timezone.now, verbose_name=_("Date de création"))

    class Meta:
        verbose_name = _("Agence de transport")
        verbose_name_plural = _("Agences de transport")
        ordering = ['nom']                                               # ordre alphabétique par défaut

    def __str__(self):
        return self.nom                                                  # affichage admin / select

    def save(self, *args, **kwargs):
        """Normalise toujours le nom et recalcule la clé avant d'enregistrer."""
        self.nom = normaliser_nom_agence(self.nom)                       # nom propre
        self.cle_unicite = cle_unicite_agence(self.nom)                  # clé de comparaison
        super().save(*args, **kwargs)                                    # enregistrement standard

    @classmethod
    def trouver_par_nom(cls, nom):
        """Retourne l'agence équivalente au nom donné (même clé) ou None."""
        return cls.objects.filter(cle_unicite=cle_unicite_agence(nom)).first()

    @classmethod
    def creer_si_absente(cls, nom, utilisateur=None):
        """
        Crée l'agence si aucune équivalente n'existe.
        Retourne (agence, cree) ; cree=False si elle existait déjà (nom ignoré).
        """
        nom_propre = normaliser_nom_agence(nom)                          # nom normalisé
        if not nom_propre:                                               # nom vide -> rien à créer
            return None, False
        existante = cls.trouver_par_nom(nom_propre)                      # déjà présente ?
        if existante:
            return existante, False                                      # oui : on saute
        agence = cls.objects.create(nom=nom_propre, cree_par=utilisateur)    # non : on crée
        return agence, True


# ===================================================================
# 2. FICHE (EN-TÊTE) : POSTE + DATE
# ===================================================================

class InventaireTransporteur(models.Model):
    """Une fiche d'inventaire des transporteurs pour un poste et un jour."""

    poste = models.ForeignKey(                                           # poste de péage
        'accounts.Poste', on_delete=models.CASCADE,
        related_name='inventaires_transporteurs', verbose_name=_("Poste"))
    date = models.DateField(verbose_name=_("Date"))                      # jour concerné
    agent_saisie = models.ForeignKey(                                    # agent ayant validé la fiche
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name='inventaires_transporteurs_saisis', verbose_name=_("Saisi par"))
    date_saisie = models.DateTimeField(                                  # horodatage de la validation
        default=timezone.now, verbose_name=_("Validé le"))
    derniere_modification_par = models.ForeignKey(                       # dernier admin ayant modifié
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='inventaires_transporteurs_modifies',
        verbose_name=_("Dernière modification par"))
    date_derniere_modification = models.DateTimeField(                   # horodatage de cette modification
        null=True, blank=True, verbose_name=_("Dernière modification le"))

    class Meta:
        verbose_name = _("Inventaire des transporteurs")
        verbose_name_plural = _("Inventaires des transporteurs")
        unique_together = [('poste', 'date')]                            # une seule fiche par poste et par jour
        ordering = ['-date', 'poste__nom']
        indexes = [models.Index(fields=['date']), models.Index(fields=['poste', 'date'])]

    def __str__(self):
        return f"{self.poste} - {self.date:%d/%m/%Y}"

    # ---- Totaux (calculés en base à la demande) ----
    @property
    def total_vehicules(self):
        return self.vehicules.count()                                    # nombre de lignes véhicule

    @property
    def nombre_agences(self):
        # une agence supprimée garde son nom (agence_nom) : on compte donc les noms distincts
        return self.vehicules.values('agence_nom').distinct().count()

    def totaux_par_type(self):
        """Dictionnaire {code_type: nombre} avec les 4 types toujours présents."""
        resultat = {code: 0 for code, _libelle in TypeVehicule.choices}  # tous à 0 au départ
        for ligne in self.vehicules.values('type_vehicule').annotate(n=models.Count('id')):
            resultat[ligne['type_vehicule']] = ligne['n']                # remplace par la valeur réelle
        return resultat

    def regrouper_par_agence(self):
        """
        Liste [{'agence': nom, 'vehicules': [lignes], 'total': n, 'par_type': {...}}]
        triée par nom d'agence : sert à la fiche détail et à la confirmation.
        """
        groupes = {}                                                     # nom d'agence -> lignes
        for v in self.vehicules.all().order_by('agence_nom', 'id'):      # lignes triées
            groupes.setdefault(v.agence_nom, []).append(v)               # regroupe par agence
        sortie = []                                                      # résultat final
        for nom, lignes in groupes.items():
            par_type = {code: 0 for code, _l in TypeVehicule.choices}    # compteur par type
            for v in lignes:
                par_type[v.type_vehicule] += 1
            sortie.append({'agence': nom, 'vehicules': lignes,
                           'total': len(lignes), 'par_type': par_type})
        return sortie


# ===================================================================
# 3. LIGNE : UN VÉHICULE D'UNE AGENCE
# ===================================================================

class DetailVehiculeTransporteur(models.Model):
    """Un véhicule (plaque + type) passé au poste pour une agence."""

    inventaire = models.ForeignKey(                                      # fiche parente
        InventaireTransporteur, on_delete=models.CASCADE,
        related_name='vehicules', verbose_name=_("Fiche"))
    agence = models.ForeignKey(                                          # agence (NULL si agence supprimée plus tard)
        AgenceTransport, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='vehicules', verbose_name=_("Agence"))
    agence_nom = models.CharField(                                       # copie du nom : l'historique survit à la suppression
        max_length=150, db_index=True, verbose_name=_("Nom de l'agence"))
    plaque = models.CharField(                                           # plaque telle qu'affichée
        max_length=30, verbose_name=_("Plaque d'immatriculation"))
    plaque_normalisee = models.CharField(                                # plaque sans séparateurs (recherche)
        max_length=30, db_index=True, editable=False)
    type_vehicule = models.CharField(                                    # un des 4 types
        max_length=20, choices=TypeVehicule.choices, verbose_name=_("Type de véhicule"))

    class Meta:
        verbose_name = _("Véhicule transporteur")
        verbose_name_plural = _("Véhicules transporteurs")
        ordering = ['agence_nom', 'id']
        indexes = [models.Index(fields=['plaque_normalisee', 'inventaire'])]

    def __str__(self):
        return f"{self.agence_nom} - {self.plaque}"

    def save(self, *args, **kwargs):
        self.plaque = afficher_plaque(self.plaque)                       # plaque propre
        self.plaque_normalisee = normaliser_plaque(self.plaque)          # version de recherche
        self.agence_nom = normaliser_nom_agence(self.agence_nom or (self.agence.nom if self.agence else ''))
        super().save(*args, **kwargs)
