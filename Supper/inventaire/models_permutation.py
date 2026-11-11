# inventaire/models_permutation.py
# Modèle d'historique des PERMUTATIONS de séries de tickets.
# Cas d'usage : un chef de poste a déclaré dans SUPPER la vente de la série 10 à 20 (jaune) alors qu'il a
# réellement vendu la série 30 à 40 (vert). On RÉVEILLE 10-20 (vendu -> en stock) et on TUE 30-40
# (en stock -> vendu, même recette, même date). Les deux plages ont la même valeur en FCFA ; les
# couleurs peuvent différer. Chaque permutation est tracée ici.

from django.db import models  # Outils de modélisation Django
from django.utils.translation import gettext_lazy as _  # Textes traduisibles (FR/EN)


class StatutPermutation(models.TextChoices):
    """État d'une permutation."""
    EFFECTUEE = 'effectuee', _('Effectuée')  # Permutation appliquée au stock
    ANNULEE = 'annulee', _('Annulée')  # Permutation inversée par la suite


class PermutationSeries(models.Model):
    """Une permutation entre une plage 'vendue dans SUPPER' et une plage 'en stock' d'un même poste."""

    poste = models.ForeignKey(  # Poste concerné (les deux plages sont dans ce poste)
        'accounts.Poste', on_delete=models.PROTECT,
        related_name='permutations_series', verbose_name=_("Poste"))

    couleur_reveil = models.ForeignKey(  # Couleur des tickets RÉVEILLÉS (vendu -> en stock)
        'inventaire.CouleurTicket', on_delete=models.PROTECT,
        related_name='permutations_reveil', verbose_name=_("Couleur réveillée"))
    reveil_premier = models.IntegerField(_("Premier n° réveillé"))  # Début de la plage réveillée
    reveil_dernier = models.IntegerField(_("Dernier n° réveillé"))  # Fin de la plage réveillée

    couleur_tue = models.ForeignKey(  # Couleur des tickets TUÉS (en stock -> vendu)
        'inventaire.CouleurTicket', on_delete=models.PROTECT,
        related_name='permutations_tue', verbose_name=_("Couleur tuée"))
    tue_premier = models.IntegerField(_("Premier n° tué"))  # Début de la plage tuée
    tue_dernier = models.IntegerField(_("Dernier n° tué"))  # Fin de la plage tuée

    nombre_tickets = models.IntegerField(_("Nombre de tickets échangés"))  # Même nombre des deux côtés

    recette = models.ForeignKey(  # Première recette concernée (le détail complet est dans `details`)
        'inventaire.RecetteJournaliere', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='permutations_series', verbose_name=_("Recette concernée"))
    date_vente = models.DateField(_("Date de la vente"), null=True, blank=True)  # Date de vente de la 1re recette
    details = models.JSONField(default=list, blank=True, verbose_name=_("Détail des échanges"))  # Paires échangées

    motif = models.TextField(_("Motif de la permutation"))  # Justification obligatoire (traçabilité)

    statut = models.CharField(  # Effectuée ou annulée
        max_length=12, choices=StatutPermutation.choices, default=StatutPermutation.EFFECTUEE,
        verbose_name=_("Statut"))
    effectue_par = models.ForeignKey(  # Auteur de la permutation
        'accounts.UtilisateurSUPPER', on_delete=models.SET_NULL, null=True,
        related_name='permutations_effectuees', verbose_name=_("Effectuée par"))
    date_operation = models.DateTimeField(auto_now_add=True, verbose_name=_("Date de l'opération"))  # Horodatage

    annulee_par = models.ForeignKey(  # Auteur de l'annulation éventuelle
        'accounts.UtilisateurSUPPER', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='permutations_annulees', verbose_name=_("Annulée par"))
    date_annulation = models.DateTimeField(null=True, blank=True, verbose_name=_("Date d'annulation"))  # Horodatage
    motif_annulation = models.TextField(blank=True, verbose_name=_("Motif de l'annulation"))  # Justification

    class Meta:
        verbose_name = _("Permutation de séries")  # Nom au singulier
        verbose_name_plural = _("Permutations de séries")  # Nom au pluriel
        ordering = ['-date_operation']  # Les plus récentes d'abord
        indexes = [
            models.Index(fields=['poste']),  # Recherche par poste
            models.Index(fields=['statut', 'date_operation']),  # Filtre par statut et date
        ]

    def __str__(self):
        """Libellé lisible : poste, plages réveillée et tuée."""
        return (f"Permutation {self.poste} : réveil {self.couleur_reveil} {self.reveil_premier}-{self.reveil_dernier}"
                f" / tue {self.couleur_tue} {self.tue_premier}-{self.tue_dernier}")

    @property
    def montant(self):
        """Valeur en FCFA des tickets échangés (500 FCFA par ticket) : identique des deux côtés."""
        return self.nombre_tickets * 500
