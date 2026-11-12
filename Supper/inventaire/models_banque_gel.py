# inventaire/models_banque_gel.py
# BANQUE DE GEL : réserve de séries de tickets « gelées ».
# Principe d'harmonisation des stocks :
#   - GEL    : un poste a, dans SUPPER, des séries en stock qu'il n'a pas réellement. On les GÈLE : elles sortent
#              du stock du poste et vont dans la banque de gel (avec la couleur, les numéros et le poste d'origine).
#   - DÉGEL  : un autre poste a un stock SUPPER insuffisant (il a vendu plus que ce que SUPPER lui connaît).
#              On DÉGÈLE des séries de la banque vers ce poste : elles entrent dans son stock.
# Chaque ligne de la banque est un intervalle de numéros d'une couleur ; un dégel partiel découpe la ligne.

from django.db import models  # Outils de modélisation Django
from django.utils.translation import gettext_lazy as _  # Textes traduisibles (FR/EN)


class StatutGel(models.TextChoices):
    """État d'une ligne de la banque de gel."""
    GELE = 'gele', _('Gelée')  # Disponible dans la banque
    DEGELE = 'degele', _('Dégelée')  # Réaffectée à un autre poste
    ANNULE = 'annule', _('Gel annulé')  # Remise au poste d'origine


class BanqueGel(models.Model):
    """Une plage de tickets (une couleur, du n° premier au n° dernier) passée par la banque de gel."""

    couleur = models.ForeignKey(  # Couleur de la série
        'inventaire.CouleurTicket', on_delete=models.PROTECT, related_name='banque_gel', verbose_name=_("Couleur"))
    numero_premier = models.IntegerField(_("Premier numéro"))  # Début de la plage
    numero_dernier = models.IntegerField(_("Dernier numéro"))  # Fin de la plage
    nombre_tickets = models.IntegerField(_("Nombre de tickets"))  # Taille de la plage

    poste_origine = models.ForeignKey(  # Poste d'où la série a été gelée
        'accounts.Poste', on_delete=models.PROTECT, related_name='gels_origine', verbose_name=_("Poste d'origine"))
    date_reception_origine = models.DateTimeField(  # Date de réception d'origine (pour reconstituer le stock passé)
        null=True, blank=True, verbose_name=_("Reçue au poste d'origine le"))
    type_entree_origine = models.CharField(  # Type d'entrée d'origine (pour restituer la série en cas d'annulation)
        max_length=30, blank=True, default='', verbose_name=_("Type d'entrée d'origine"))
    historique_source_id = models.IntegerField(  # Chargement d'origine de la série (information)
        null=True, blank=True, verbose_name=_("Historique source d'origine"))
    date_effet_gel = models.DateField(_("Date d'effet du gel"))  # Date comptable du gel (ex. fin du mois harmonisé)
    gele_par = models.ForeignKey(  # Auteur du gel
        'accounts.UtilisateurSUPPER', on_delete=models.SET_NULL, null=True, related_name='gels_effectues',
        verbose_name=_("Gelée par"))
    motif_gel = models.TextField(_("Motif du gel"))  # Justification obligatoire
    date_operation_gel = models.DateTimeField(auto_now_add=True, verbose_name=_("Gel enregistré le"))  # Horodatage

    statut = models.CharField(  # Gelée / dégelée / gel annulé
        max_length=10, choices=StatutGel.choices, default=StatutGel.GELE, verbose_name=_("Statut"))

    poste_destination = models.ForeignKey(  # Poste qui a reçu la série au dégel
        'accounts.Poste', on_delete=models.PROTECT, null=True, blank=True, related_name='degels_recus',
        verbose_name=_("Poste destinataire"))
    date_effet_degel = models.DateField(null=True, blank=True, verbose_name=_("Date d'effet du dégel"))
    degele_par = models.ForeignKey(  # Auteur du dégel
        'accounts.UtilisateurSUPPER', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='degels_effectues', verbose_name=_("Dégelée par"))
    motif_degel = models.TextField(blank=True, verbose_name=_("Motif du dégel"))  # Justification du dégel
    date_operation_degel = models.DateTimeField(null=True, blank=True, verbose_name=_("Dégel enregistré le"))

    class Meta:
        verbose_name = _("Série de la banque de gel")  # Nom au singulier
        verbose_name_plural = _("Banque de gel")  # Nom au pluriel
        ordering = ['-date_operation_gel', 'couleur', 'numero_premier']  # Les gels récents d'abord
        indexes = [
            models.Index(fields=['statut', 'couleur']),  # Recherche des séries disponibles
            models.Index(fields=['poste_origine', 'date_effet_gel']),  # Reconstitution du stock d'un poste
            models.Index(fields=['poste_destination', 'date_effet_degel']),  # Idem pour les postes destinataires
        ]

    def __str__(self):
        """Libellé lisible : couleur, plage et statut."""
        return f"{self.couleur} {self.numero_premier}-{self.numero_dernier} ({self.get_statut_display()})"

    @property
    def montant(self):
        """Valeur en FCFA de la plage (500 FCFA par ticket)."""
        return self.nombre_tickets * 500
