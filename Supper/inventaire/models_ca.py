# inventaire/models_ca.py
# ===================================================================
# MODÈLES - CHIFFRE D'AFFAIRES ESTIMÉ DES TRANSPORTEURS DE PERSONNES
#
# Trois tables, toutes NOUVELLES (aucune table existante n'est modifiée) :
#   1. PosteMaillage     : un poste de péage du « maillage » (document des postes voisins)
#   2. LiaisonMaillage   : le tarif de transport entre deux postes voisins (par passager)
#   3. ParametresCA      : les paramètres de la méthode de calcul (une seule ligne)
#
# Le calcul lui-même est dans inventaire/services_ca.py (sans accès base de données,
# donc facile à tester). Les vues sont dans inventaire/views_ca.py.
# ===================================================================

from decimal import Decimal                                          # nombres décimaux exacts (argent / fractions)

from django.db import models                                         # champs et modèles Django
from django.utils.translation import gettext_lazy as _               # textes traduisibles FR/EN


class PosteMaillage(models.Model):
    """Un poste de péage tel qu'il figure dans le document « Maillage des postes voisins »."""

    nom = models.CharField(                                          # nom du document (ex. « Okoa-Maria (Mbankomo) »)
        max_length=120, unique=True, verbose_name=_("Nom dans le maillage"))
    region = models.CharField(                                       # région du poste (sert à compter les régions d'un trajet)
        max_length=40, verbose_name=_("Région"))
    poste = models.ForeignKey(                                       # lien vers le poste SUPPER correspondant
        'accounts.Poste', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='maillages', verbose_name=_("Poste SUPPER correspondant"))

    class Meta:
        verbose_name = _("Poste du maillage")
        verbose_name_plural = _("Postes du maillage")
        ordering = ['region', 'nom']                                 # classement par région puis nom

    def __str__(self):
        return f"{self.nom} ({self.region})"                         # affichage lisible


class LiaisonMaillage(models.Model):
    """Tarif de transport (FCFA par passager) entre deux postes voisins. Liaison non orientée."""

    poste_a = models.ForeignKey(                                     # première extrémité
        PosteMaillage, on_delete=models.CASCADE, related_name='liaisons_a')
    poste_b = models.ForeignKey(                                     # seconde extrémité
        PosteMaillage, on_delete=models.CASCADE, related_name='liaisons_b')
    tarif = models.PositiveIntegerField(                             # FCFA par passager, sens simple
        verbose_name=_("Tarif par passager (FCFA)"))

    class Meta:
        verbose_name = _("Liaison du maillage")
        verbose_name_plural = _("Liaisons du maillage")
        unique_together = [('poste_a', 'poste_b')]                   # une seule ligne par couple
        ordering = ['poste_a__nom', 'poste_b__nom']

    def __str__(self):
        return f"{self.poste_a.nom} ↔ {self.poste_b.nom} : {self.tarif}"

    def save(self, *args, **kwargs):
        """Range toujours la paire dans l'ordre des identifiants pour éviter les doublons A-B / B-A."""
        if self.poste_a_id and self.poste_b_id and self.poste_a_id > self.poste_b_id:
            self.poste_a_id, self.poste_b_id = self.poste_b_id, self.poste_a_id   # permutation
        super().save(*args, **kwargs)                                # enregistrement normal


class ParametresCA(models.Model):
    """
    Paramètres de la méthode d'estimation (ligne unique, pk=1).
    Modifiables par un administrateur sans toucher au code.
    """

    # --- Rythme des voyages (aller-retour complets par semaine) ---
    tours_longs = models.PositiveSmallIntegerField(                  # voyages qui traversent beaucoup de régions
        default=2, verbose_name=_("Aller-retour / semaine (long trajet)"))
    tours_courts = models.PositiveSmallIntegerField(                 # voyages courts
        default=4, verbose_name=_("Aller-retour / semaine (trajet court)"))
    seuil_regions = models.PositiveSmallIntegerField(                # « plus de 3 régions » = long trajet
        default=3, verbose_name=_("Seuil de régions (au-delà : long trajet)"))

    # --- Choix du chemin entre deux postes ---
    routage_regions = models.BooleanField(                           # chemin limité aux régions des 2 postes
        default=True, verbose_name=_("Chemin limité aux régions des deux postes"),
        help_text=_("Une région supplémentaire n'est ajoutée que si aucun chemin n'existe sans elle."))

    # --- Majoration des bus climatisés ---
    majoration_clim = models.DecimalField(                           # 2/3 du tarif normal en plus
        max_digits=6, decimal_places=4, default=Decimal('0.6667'),
        verbose_name=_("Majoration bus climatisé (fraction du tarif)"))

    # --- Nombre de places retenu par type (borne inférieure de la fourchette de la fiche) ---
    places_coaster = models.PositiveSmallIntegerField(default=29, verbose_name=_("Places Coaster"))
    places_bus_ordinaire = models.PositiveSmallIntegerField(default=75, verbose_name=_("Places grand bus ordinaire"))
    places_bus_clim = models.PositiveSmallIntegerField(default=55, verbose_name=_("Places grand bus climatisé"))
    places_hiace = models.PositiveSmallIntegerField(default=16, verbose_name=_("Places Hiace"))

    modifie_le = models.DateTimeField(auto_now=True)                 # dernière modification

    class Meta:
        verbose_name = _("Paramètres du chiffre d'affaires")
        verbose_name_plural = _("Paramètres du chiffre d'affaires")

    def __str__(self):
        return "Paramètres CA transporteurs"

    @classmethod
    def charger(cls):
        """Retourne l'unique ligne de paramètres (la crée avec les valeurs par défaut si absente)."""
        obj, _cree = cls.objects.get_or_create(pk=1)                 # pk fixe = ligne unique
        return obj

    def places_par_type(self):
        """Dictionnaire {code du type de véhicule: nombre de places retenu}."""
        return {
            'coaster': self.places_coaster,
            'bus_ordinaire': self.places_bus_ordinaire,
            'bus_clim': self.places_bus_clim,
            'hiace': self.places_hiace,
        }
