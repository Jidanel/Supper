# ===================================================================
# inventaire/models_incident.py - Modèle pour la gestion des incidents SUPPER
# VERSION SIMPLIFIÉE - 4 statuts uniquement
# À AJOUTER dans le dossier inventaire/
# ===================================================================
"""
Modèle Incident pour la gestion des signalements et problèmes
remontés par les utilisateurs de SUPPER.

Workflow simplifié:
    1. Utilisateur crée un incident → statut "En attente"
    2. Admin traite → statut "Traité"
    3. Admin rejette → statut "Rejeté"
    4. Admin demande complément → statut "Complément requis" (utilisateur doit resaisir)
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from accounts.models import UtilisateurSUPPER

import logging
logger = logging.getLogger('supper')


class StatutIncident(models.TextChoices):
    """Statuts possibles d'un incident - VERSION SIMPLIFIÉE"""
    EN_ATTENTE = 'en_attente', _('En attente')
    TRAITE = 'traite', _('Traité')
    REJETE = 'rejete', _('Rejeté')
    COMPLEMENT_REQUIS = 'complement_requis', _('Complément d\'informations requis')


class PrioriteIncident(models.TextChoices):
    """Niveaux de priorité d'un incident"""
    BASSE = 'basse', _('Basse')
    NORMALE = 'normale', _('Normale')
    HAUTE = 'haute', _('Haute')
    CRITIQUE = 'critique', _('Critique')


class CategorieIncident(models.TextChoices):
    """Catégories d'incidents"""
    TECHNIQUE = 'technique', _('Problème technique')
    FONCTIONNEL = 'fonctionnel', _('Problème fonctionnel')
    ACCES = 'acces', _('Problème d\'accès')
    DONNEES = 'donnees', _('Problème de données')
    AUTRE = 'autre', _('Autre')


class Incident(models.Model):
    """
    Modèle pour la gestion des incidents signalés par les utilisateurs.
    
    Workflow simplifié:
        1. Utilisateur crée un incident avec sujet + détails → statut "En attente"
        2. Admin a 3 options:
           - Traiter → statut "Traité"
           - Rejeter → statut "Rejeté"  
           - Demander complément → statut "Complément requis"
    """
    
    # Référence unique de l'incident (auto-générée)
    reference = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        verbose_name=_("Référence"),
        help_text=_("Référence unique auto-générée")
    )
    
    # Informations de l'incident
    sujet = models.CharField(
        max_length=200,
        verbose_name=_("Sujet de l'incident"),
        help_text=_("Décrivez brièvement le problème rencontré")
    )
    
    description = models.TextField(
        verbose_name=_("Description détaillée"),
        help_text=_("Décrivez en détail le problème, les étapes pour le reproduire, etc.")
    )
    
    categorie = models.CharField(
        max_length=20,
        choices=CategorieIncident.choices,
        default=CategorieIncident.AUTRE,
        verbose_name=_("Catégorie")
    )
    
    priorite = models.CharField(
        max_length=20,
        choices=PrioriteIncident.choices,
        default=PrioriteIncident.NORMALE,
        verbose_name=_("Priorité")
    )
    
    # Statut
    statut = models.CharField(
        max_length=20,
        choices=StatutIncident.choices,
        default=StatutIncident.EN_ATTENTE,
        verbose_name=_("Statut"),
        db_index=True
    )
    
    # Utilisateur qui a créé l'incident
    cree_par = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.CASCADE,
        related_name='incidents_crees',
        verbose_name=_("Créé par")
    )
    
    # Administrateur qui traite l'incident
    traite_par = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incidents_traites',
        verbose_name=_("Traité par")
    )
    
    # Réponse de l'administrateur
    reponse = models.TextField(
        blank=True,
        verbose_name=_("Réponse de l'administrateur"),
        help_text=_("Réponse, résolution ou motif de rejet/demande de complément")
    )
    
    # Dates importantes
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )
    
    date_traitement = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Date de traitement")
    )
    
    class Meta:
        verbose_name = _("Incident")
        verbose_name_plural = _("Incidents")
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['statut', '-date_creation']),
            models.Index(fields=['cree_par', '-date_creation']),
            models.Index(fields=['traite_par', '-date_creation']),
            models.Index(fields=['categorie']),
            models.Index(fields=['priorite']),
        ]
    
    def __str__(self):
        return f"[{self.reference}] {self.sujet}"
    
    def save(self, *args, **kwargs):
        """Génère automatiquement la référence si non définie"""
        if not self.reference:
            self.reference = self._generer_reference()
        super().save(*args, **kwargs)
    
    def _generer_reference(self):
        """
        Génère une référence unique pour l'incident
        Format: INC-AAAAMM-XXXX (ex: INC-202501-0001)
        """
        from datetime import datetime
        prefix = f"INC-{datetime.now().strftime('%Y%m')}-"
        
        # Trouver le dernier numéro pour ce mois
        last_incident = Incident.objects.filter(
            reference__startswith=prefix
        ).order_by('-reference').first()
        
        if last_incident:
            try:
                last_num = int(last_incident.reference.split('-')[-1])
                new_num = last_num + 1
            except (ValueError, IndexError):
                new_num = 1
        else:
            new_num = 1
        
        return f"{prefix}{new_num:04d}"
    
    @property
    def est_en_attente(self):
        """Vérifie si l'incident est en attente"""
        return self.statut == StatutIncident.EN_ATTENTE
    
    @property
    def est_traite(self):
        """Vérifie si l'incident est traité"""
        return self.statut == StatutIncident.TRAITE
    
    @property
    def est_rejete(self):
        """Vérifie si l'incident est rejeté"""
        return self.statut == StatutIncident.REJETE
    
    @property
    def necessite_complement(self):
        """Vérifie si l'incident nécessite un complément d'informations"""
        return self.statut == StatutIncident.COMPLEMENT_REQUIS
    
    @property
    def peut_etre_traite(self):
        """Vérifie si l'incident peut encore être traité par un admin"""
        return self.statut in [StatutIncident.EN_ATTENTE, StatutIncident.COMPLEMENT_REQUIS]
    
    @classmethod
    def statistiques_globales(cls):
        """
        Retourne les statistiques globales sur les incidents
        """
        from django.db.models import Count
        
        total = cls.objects.count()
        par_statut = dict(
            cls.objects.values('statut').annotate(count=Count('id'))
            .values_list('statut', 'count')
        )
        
        return {
            'total': total,
            'en_attente': par_statut.get('en_attente', 0),
            'traites': par_statut.get('traite', 0),
            'rejetes': par_statut.get('rejete', 0),
            'complement_requis': par_statut.get('complement_requis', 0),
        }