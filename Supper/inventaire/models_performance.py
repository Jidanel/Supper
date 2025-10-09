# ===================================================================
# inventaire/models_performance.py - Modèles pour le classement
# ===================================================================

from django.db import models
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from datetime import date
from accounts.models import UtilisateurSUPPER, Poste

class PerformancePoste(models.Model):
    """
    Stocke les performances calculées d'un poste sur une période
    """
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='performances',
        verbose_name=_("Poste")
    )
    
    date_debut = models.DateField(
        verbose_name=_("Date de début période")
    )
    
    date_fin = models.DateField(
        verbose_name=_("Date de fin période")
    )
    
    # Motifs identifiés
    motifs = models.JSONField(
        default=list,
        verbose_name=_("Motifs identifiés"),
        help_text=_("Liste des motifs sur la période")
    )
    
    # Métriques financières
    taux_moyen_deperdition = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux moyen déperdition (%)")
    )
    
    taux_plus_bas = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux le plus bas (%)")
    )
    
    taux_plus_eleve = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux le plus élevé (%)")
    )
    
    # Stock
    date_epuisement_debut = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date épuisement début")
    )
    
    date_epuisement_fin = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date épuisement fin")
    )
    
    evolution_stock_jours = models.IntegerField(
        default=0,
        verbose_name=_("Évolution stock (jours)"),
        help_text=_("Positif = rapproché, Négatif = éloigné")
    )
    
    # Évolution recettes
    recettes_periode = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Recettes période")
    )
    
    recettes_periode_precedente = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Recettes période précédente")
    )
    
    taux_evolution_recettes = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux évolution recettes (%)")
    )
    
    # Jours impertinents
    nombre_jours_impertinents = models.IntegerField(
        default=0,
        verbose_name=_("Nombre jours impertinents")
    )
    
    # Métadonnées
    date_calcul = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Date du calcul")
    )
    
    class Meta:
        verbose_name = _("Performance poste")
        verbose_name_plural = _("Performances postes")
        unique_together = [['poste', 'date_debut', 'date_fin']]
        ordering = ['-date_debut', 'poste__nom']


class PerformanceAgent(models.Model):
    """
    Stocke les performances d'un agent à un poste sur une période
    """
    agent = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.CASCADE,
        related_name='performances_agent',
        verbose_name=_("Agent")
    )
    
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='performances_agents',
        verbose_name=_("Poste")
    )
    
    date_debut = models.DateField(
        verbose_name=_("Date début passage")
    )
    
    date_fin = models.DateField(
        verbose_name=_("Date fin passage")
    )
    
    # Situation avant passage
    taux_moyen_avant = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux moyen avant (%)")
    )
    
    date_stock_avant = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date stock avant")
    )
    
    recettes_mois_avant = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Recettes mois avant")
    )
    
    # Situation après passage
    taux_moyen_apres = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux moyen après (%)")
    )
    
    date_stock_apres = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date stock après")
    )
    
    recettes_mois_apres = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Recettes mois après")
    )
    
    # Notation par motif
    note_stock = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Note stock /20")
    )
    
    note_recettes = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Note recettes /20")
    )
    
    note_taux = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Note taux /20")
    )
    
    note_moyenne = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Note moyenne /20")
    )
    
    # Jours impertinents
    nombre_jours_impertinents = models.IntegerField(
        default=0,
        verbose_name=_("Jours impertinents")
    )
    
    # Métadonnées
    date_calcul = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Date calcul")
    )
    
    class Meta:
        verbose_name = _("Performance agent")
        verbose_name_plural = _("Performances agents")
        unique_together = [['agent', 'poste', 'date_debut']]
        ordering = ['-note_moyenne', 'agent__nom_complet']