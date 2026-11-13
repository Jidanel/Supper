# inventaire/models_import_stock.py
# LOT D'IMPORT DE RECETTES AVEC STOCKS.
# Un lot = un fichier Excel (postes en lignes, dates en colonnes) + une période (date début / date fin).
# Le lot garde les montants lus dans le fichier (pour la simulation) et le résultat de chaque poste validé
# (recettes créées, séries consommées) afin de pouvoir ANNULER un poste : les tickets retournent en stock.

from django.conf import settings  # Modèle utilisateur configuré
from django.db import models  # Outils de modélisation Django
from django.utils.translation import gettext_lazy as _  # Textes traduisibles (FR/EN)


class ImportRecettesStock(models.Model):
    """Lot d'import de recettes qui consomment les stocks des postes (avec simulation avant validation)."""

    fichier_nom = models.CharField(_("Nom du fichier"), max_length=255)  # Nom du fichier Excel d'origine
    date_debut = models.DateField(_("Date de début"))  # Première date de recette importée
    date_fin = models.DateField(_("Date de fin"))  # Dernière date de recette importée
    donnees = models.JSONField(_("Montants lus"), default=dict)  # {poste_id: {"AAAA-MM-JJ": "montant"}}
    postes_non_trouves = models.JSONField(_("Postes non trouvés"), default=list)  # Noms du fichier sans poste SUPPER
    resultats = models.JSONField(_("Résultats par poste"), default=dict)  # {poste_id: infos du poste validé}
    cree_par = models.ForeignKey(  # Utilisateur qui a téléversé le fichier
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='imports_recettes_stock',
        verbose_name=_("Créé par"))
    date_creation = models.DateTimeField(_("Date de création"), auto_now_add=True)  # Horodatage du téléversement

    class Meta:
        verbose_name = _("Import de recettes avec stocks")  # Nom au singulier
        verbose_name_plural = _("Imports de recettes avec stocks")  # Nom au pluriel
        ordering = ['-date_creation']  # Les plus récents d'abord

    def __str__(self):
        return f"Import #{self.pk} — {self.fichier_nom} ({self.date_debut} → {self.date_fin})"
