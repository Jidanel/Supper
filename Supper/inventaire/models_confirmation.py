# ===================================================================
# inventaire/models_confirmation.py - Modèle pour les demandes de 
# confirmation inter-stations pour le module Pesage SUPPER
# ===================================================================

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.urls import reverse
import logging

logger = logging.getLogger('supper')


class StatutDemandeConfirmation(models.TextChoices):
    """Statuts possibles d'une demande de confirmation"""
    EN_ATTENTE = 'en_attente', _('En attente de confirmation')
    CONFIRME = 'confirme', _('Confirmé - Paiement autorisé')
    REFUSE = 'refuse', _('Refusé - Paiement bloqué')
    EXPIRE = 'expire', _('Expiré')
    ANNULE = 'annule', _('Annulé par le demandeur')


class DemandeConfirmationPaiement(models.Model):
    """
    Demande de confirmation entre stations pour paiement d'amende
    quand un véhicule a des amendes non payées dans une autre station.
    
    Workflow:
    1. Régisseur A veut valider paiement amende X à Station A
    2. Système détecte amende Y non payée à Station B
    3. Régisseur A crée une demande de confirmation
    4. Régisseur B reçoit notification et peut confirmer ou refuser
    5. Si confirmé, Régisseur A peut valider le paiement
    """
    
    # === IDENTIFICATION ===
    reference = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Référence"),
        help_text=_("Référence unique de la demande (auto-générée)")
    )
    
    # === STATION DEMANDEUR ===
    station_demandeur = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='demandes_confirmation_envoyees',
        verbose_name=_("Station demandeur"),
        help_text=_("Station qui demande la confirmation")
    )
    
    regisseur_demandeur = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.CASCADE,
        related_name='demandes_confirmation_creees',
        verbose_name=_("Régisseur demandeur")
    )
    
    # === AMENDE À VALIDER (dans la station demandeur) ===
    amende_a_valider = models.ForeignKey(
        'inventaire.AmendeEmise',
        on_delete=models.CASCADE,
        related_name='demandes_confirmation_pour_validation',
        verbose_name=_("Amende à valider"),
        help_text=_("Amende dont le paiement est en attente de confirmation")
    )
    
    # === STATION CONCERNÉE (où il y a l'amende non payée) ===
    station_concernee = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='demandes_confirmation_recues',
        verbose_name=_("Station concernée"),
        help_text=_("Station où se trouve l'amende non payée")
    )
    
    amende_non_payee = models.ForeignKey(
        'inventaire.AmendeEmise',
        on_delete=models.CASCADE,
        related_name='demandes_confirmation_bloquantes',
        verbose_name=_("Amende non payée"),
        help_text=_("Amende non payée qui bloque la validation")
    )
    
    # === STATUT ===
    statut = models.CharField(
        max_length=15,
        choices=StatutDemandeConfirmation.choices,
        default=StatutDemandeConfirmation.EN_ATTENTE,
        verbose_name=_("Statut")
    )
    
    # === RÉPONSE ===
    regisseur_confirmeur = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='demandes_confirmation_traitees',
        verbose_name=_("Régisseur confirmeur"),
        help_text=_("Régisseur qui a traité la demande")
    )
    
    date_reponse = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Date de réponse")
    )
    
    commentaire_demande = models.TextField(
        blank=True,
        verbose_name=_("Commentaire du demandeur"),
        help_text=_("Explication ou justification de la demande")
    )
    
    commentaire_reponse = models.TextField(
        blank=True,
        verbose_name=_("Commentaire de réponse"),
        help_text=_("Explication du régisseur confirmeur")
    )
    
    # === DATES ===
    date_demande = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de demande")
    )
    
    date_expiration = models.DateTimeField(
        verbose_name=_("Date d'expiration"),
        help_text=_("La demande expire automatiquement après cette date")
    )
    
    # === MÉTADONNÉES ===
    vehicule_immatriculation = models.CharField(
        max_length=20,
        verbose_name=_("Immatriculation véhicule"),
        help_text=_("Pour référence rapide")
    )
    
    vehicule_transporteur = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Transporteur"),
    )
    
    class Meta:
        verbose_name = _("Demande de confirmation paiement")
        verbose_name_plural = _("Demandes de confirmation paiement")
        ordering = ['-date_demande']
        indexes = [
            models.Index(fields=['station_demandeur', '-date_demande']),
            models.Index(fields=['station_concernee', 'statut']),
            models.Index(fields=['statut', '-date_demande']),
            models.Index(fields=['reference']),
            models.Index(fields=['vehicule_immatriculation']),
        ]
    
    def __str__(self):
        return f"Demande {self.reference} - {self.vehicule_immatriculation} ({self.get_statut_display()})"
    
    def get_absolute_url(self):
        return reverse('inventaire:detail_demande_confirmation', kwargs={'pk': self.pk})
    
    def save(self, *args, **kwargs):
        # Générer la référence si nouvelle demande
        if not self.reference:
            self.reference = self._generer_reference()
        
        # Définir la date d'expiration (48h par défaut)
        if not self.date_expiration:
            self.date_expiration = timezone.now() + timezone.timedelta(hours=48)
        
        # Pré-remplir les infos véhicule
        if self.amende_a_valider and not self.vehicule_immatriculation:
            self.vehicule_immatriculation = self.amende_a_valider.immatriculation
            self.vehicule_transporteur = self.amende_a_valider.transporteur
        
        super().save(*args, **kwargs)
    
    def _generer_reference(self):
        """Génère une référence unique pour la demande"""
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"CONF-{timestamp}-{self.station_demandeur_id or 0}"
    
    @property
    def est_en_attente(self):
        """Vérifie si la demande est toujours en attente"""
        return self.statut == StatutDemandeConfirmation.EN_ATTENTE
    
    @property
    def est_expiree(self):
        """Vérifie si la demande a expiré"""
        if self.statut == StatutDemandeConfirmation.EXPIRE:
            return True
        return timezone.now() > self.date_expiration
    
    @property
    def peut_etre_traitee(self):
        """Vérifie si la demande peut encore être traitée"""
        return self.est_en_attente and not self.est_expiree
    
    def confirmer(self, regisseur, commentaire=""):
        """
        Confirme la demande (autorise le paiement).
        
        Args:
            regisseur: UtilisateurSUPPER qui confirme
            commentaire: Commentaire optionnel
        
        Returns:
            bool: True si succès
        """
        if not self.peut_etre_traitee:
            return False
        
        self.statut = StatutDemandeConfirmation.CONFIRME
        self.regisseur_confirmeur = regisseur
        self.date_reponse = timezone.now()
        self.commentaire_reponse = commentaire
        self.save()
        
        logger.info(
            f"Demande {self.reference} CONFIRMÉE par {regisseur.username} "
            f"- Véhicule: {self.vehicule_immatriculation}"
        )
        
        return True
    
    def refuser(self, regisseur, commentaire=""):
        """
        Refuse la demande (bloque le paiement).
        
        Args:
            regisseur: UtilisateurSUPPER qui refuse
            commentaire: Commentaire (recommandé)
        
        Returns:
            bool: True si succès
        """
        if not self.peut_etre_traitee:
            return False
        
        self.statut = StatutDemandeConfirmation.REFUSE
        self.regisseur_confirmeur = regisseur
        self.date_reponse = timezone.now()
        self.commentaire_reponse = commentaire
        self.save()
        
        logger.info(
            f"Demande {self.reference} REFUSÉE par {regisseur.username} "
            f"- Véhicule: {self.vehicule_immatriculation}"
        )
        
        return True
    
    def annuler(self):
        """Annule la demande par le demandeur"""
        if self.statut != StatutDemandeConfirmation.EN_ATTENTE:
            return False
        
        self.statut = StatutDemandeConfirmation.ANNULE
        self.date_reponse = timezone.now()
        self.save()
        
        return True
    
    def verifier_expiration(self):
        """Vérifie et met à jour le statut si expiré"""
        if self.statut == StatutDemandeConfirmation.EN_ATTENTE and self.est_expiree:
            self.statut = StatutDemandeConfirmation.EXPIRE
            self.save(update_fields=['statut'])
            return True
        return False
    
    @classmethod
    def get_demandes_en_attente_pour_station(cls, station):
        """
        Retourne les demandes en attente pour une station donnée.
        
        Args:
            station: Poste de pesage
        
        Returns:
            QuerySet
        """
        # Mettre à jour les demandes expirées
        cls.objects.filter(
            station_concernee=station,
            statut=StatutDemandeConfirmation.EN_ATTENTE,
            date_expiration__lt=timezone.now()
        ).update(statut=StatutDemandeConfirmation.EXPIRE)
        
        return cls.objects.filter(
            station_concernee=station,
            statut=StatutDemandeConfirmation.EN_ATTENTE
        ).select_related(
            'station_demandeur', 'regisseur_demandeur',
            'amende_a_valider', 'amende_non_payee'
        ).order_by('-date_demande')
    
    @classmethod
    def get_demandes_envoyees_par_station(cls, station):
        """Retourne les demandes envoyées par une station"""
        return cls.objects.filter(
            station_demandeur=station
        ).select_related(
            'station_concernee', 'regisseur_confirmeur',
            'amende_a_valider', 'amende_non_payee'
        ).order_by('-date_demande')
    
    @classmethod
    def existe_demande_en_attente(cls, amende_a_valider, amende_non_payee):
        """
        Vérifie si une demande existe déjà pour ces amendes.
        
        Returns:
            DemandeConfirmationPaiement ou None
        """
        return cls.objects.filter(
            amende_a_valider=amende_a_valider,
            amende_non_payee=amende_non_payee,
            statut=StatutDemandeConfirmation.EN_ATTENTE
        ).first()
    
    @classmethod
    def a_confirmation_valide(cls, amende_a_valider):
        """
        Vérifie si l'amende a une confirmation validée pour TOUTES ses amendes bloquantes.
        
        Returns:
            bool: True si toutes les confirmations sont obtenues
        """
        # Récupérer les demandes pour cette amende
        demandes = cls.objects.filter(amende_a_valider=amende_a_valider)
        
        if not demandes.exists():
            return False
        
        # Vérifier que toutes les demandes sont confirmées
        return not demandes.exclude(
            statut=StatutDemandeConfirmation.CONFIRME
        ).exists()