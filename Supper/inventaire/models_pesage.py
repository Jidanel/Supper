# ===================================================================
# inventaire/models_pesage.py - Modèles pour le module Pesage SUPPER
# Gestion des amendes, pesées et quittancements stations de pesage
# ===================================================================

from django.db import models
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.urls import reverse
from django.utils import timezone
from django.db.models import Sum, Count, Q
from decimal import Decimal
from datetime import datetime, time, timedelta
import logging

logger = logging.getLogger('supper')


class StatutAmende(models.TextChoices):
    """Statuts possibles d'une amende"""
    NON_PAYE = 'non_paye', _('Non Payé')
    PAYE = 'paye', _('Payé')


class TypeInfraction(models.TextChoices):
    """Types d'infractions pour les amendes"""
    SURCHARGE = 'surcharge', _('Surcharge uniquement')
    HORS_GABARIT = 'hors_gabarit', _('Hors Gabarit uniquement')
    SURCHARGE_ET_HORS_GABARIT = 'surcharge_hors_gabarit', _('Surcharge + Hors Gabarit')


# ===================================================================
# MODÈLE PRINCIPAL : AMENDE ÉMISE
# ===================================================================

class AmendeEmise(models.Model):
    """
    Modèle pour les amendes émises par les stations de pesage
    Une amende ne peut pas être modifiée/supprimée après création
    Seul le statut peut être changé (non_paye → paye) par le régisseur
    """
    
    # Identification unique
    numero_ticket = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Numéro du ticket"),
        help_text=_("Numéro unique de l'ordre de paiement")
    )
    
    # Station de pesage (uniquement type='pesage')
    station = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.PROTECT,
        related_name='amendes_emises',
        verbose_name=_("Station de pesage"),
        limit_choices_to={'type': 'pesage'}
    )
    
    # Informations véhicule
    immatriculation = models.CharField(
        max_length=20,
        verbose_name=_("Immatriculation"),
        help_text=_("Plaque d'immatriculation du véhicule")
    )
    
    transporteur = models.CharField(
        max_length=100,
        verbose_name=_("Transporteur"),
        help_text=_("Nom du transporteur ou de la société")
    )
    
    provenance = models.CharField(
        max_length=100,
        verbose_name=_("Provenance"),
        help_text=_("Ville de départ")
    )
    
    destination = models.CharField(
        max_length=100,
        verbose_name=_("Destination"),
        help_text=_("Ville de destination")
    )
    
    produit_transporte = models.CharField(
        max_length=100,
        verbose_name=_("Produit transporté"),
        help_text=_("Nature de la marchandise")
    )
    
    operateur = models.CharField(
        max_length=100,
        verbose_name=_("Opérateur"),
        help_text=_("Nom de l'opérateur/conducteur")
    )
    
    # Types d'infractions (cases à cocher)
    est_surcharge = models.BooleanField(
        default=False,
        verbose_name=_("Surcharge"),
        help_text=_("Cocher si infraction pour surcharge")
    )
    
    est_hors_gabarit = models.BooleanField(
        default=False,
        verbose_name=_("Hors Gabarit"),
        help_text=_("Cocher si infraction pour hors gabarit")
    )
    
    # Montant de l'amende
    montant_amende = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name=_("Montant de l'amende (FCFA)"),
        help_text=_("Montant total de la pénalité")
    )
    
    # Statut du paiement
    statut = models.CharField(
        max_length=15,
        choices=StatutAmende.choices,
        default=StatutAmende.NON_PAYE,
        verbose_name=_("Statut du paiement")
    )
    
    # Dates et heures
    date_heure_emission = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Date et heure d'émission")
    )
    
    date_paiement = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Date de paiement")
    )
    
    # Traçabilité
    saisi_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.PROTECT,
        related_name='amendes_saisies',
        verbose_name=_("Saisi par"),
        help_text=_("Chef d'équipe qui a saisi l'amende")
    )
    
    valide_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='amendes_validees',
        verbose_name=_("Validé par"),
        help_text=_("Régisseur qui a validé le paiement")
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    observations = models.TextField(
        blank=True,
        verbose_name=_("Observations"),
        help_text=_("Notes ou commentaires supplémentaires")
    )
    
    class Meta:
        verbose_name = _("Amende émise")
        verbose_name_plural = _("Amendes émises")
        ordering = ['-date_heure_emission']
        indexes = [
            models.Index(fields=['station', '-date_heure_emission']),
            models.Index(fields=['numero_ticket']),
            models.Index(fields=['immatriculation']),
            models.Index(fields=['statut']),
            models.Index(fields=['date_heure_emission']),
        ]
    
    def __str__(self):
        return f"Amende {self.numero_ticket} - {self.immatriculation} ({self.get_statut_display()})"
    
    def get_absolute_url(self):
        return reverse('inventaire:amende_detail', kwargs={'pk': self.pk})
    
    # ===================================================================
    # MÉTHODES DE CALCUL DE PÉRIODE (9h-9h)
    # ===================================================================
    
    @staticmethod
    def get_date_debut_journee(date_cible):
        """
        Retourne le début de la journée pesage (9h00 du jour donné)
        Une journée pesage va de 9h du jour à 8h59 du lendemain
        """
        if isinstance(date_cible, datetime):
            date_cible = date_cible.date()
        
        return timezone.make_aware(
            datetime.combine(date_cible, time(9, 0, 0))
        )
    
    @staticmethod
    def get_date_fin_journee(date_cible):
        """
        Retourne la fin de la journée pesage (8h59:59 du lendemain)
        """
        if isinstance(date_cible, datetime):
            date_cible = date_cible.date()
        
        lendemain = date_cible + timedelta(days=1)
        return timezone.make_aware(
            datetime.combine(lendemain, time(8, 59, 59))
        )
    
    @classmethod
    def get_amendes_journee(cls, station, date_cible):
        """
        Retourne les amendes pour une journée pesage (9h à 9h)
        
        Args:
            station: Instance de Poste (type pesage)
            date_cible: Date de la journée
        
        Returns:
            QuerySet des amendes de cette journée
        """
        debut = cls.get_date_debut_journee(date_cible)
        fin = cls.get_date_fin_journee(date_cible)
        
        return cls.objects.filter(
            station=station,
            date_heure_emission__gte=debut,
            date_heure_emission__lte=fin
        )
    
    @classmethod
    def get_statistiques_journee(cls, station, date_cible):
        """
        Calcule les statistiques d'une journée de pesage
        
        Returns:
            dict: {
                'nombre_emissions': int,
                'nombre_hors_gabarit': int,
                'montant_emis': Decimal,
                'montant_recouvre': Decimal,
                'reste_a_recouvrer': Decimal,
                'nombre_surcharges': int,
                'nombre_mixtes': int (surcharge + hors gabarit)
            }
        """
        amendes = cls.get_amendes_journee(station, date_cible)
        
        # Calculs d'agrégation
        stats = amendes.aggregate(
            montant_total_emis=Sum('montant_amende'),
            montant_recouvre=Sum('montant_amende', filter=Q(statut=StatutAmende.PAYE)),
        )
        
        montant_emis = stats['montant_total_emis'] or Decimal('0')
        montant_recouvre = stats['montant_recouvre'] or Decimal('0')
        
        # Comptages détaillés
        # Une amende avec surcharge ET hors gabarit compte pour 2 amendes
        nombre_surcharges_seules = amendes.filter(est_surcharge=True, est_hors_gabarit=False).count()
        nombre_hors_gabarit_seuls = amendes.filter(est_surcharge=False, est_hors_gabarit=True).count()
        nombre_mixtes = amendes.filter(est_surcharge=True, est_hors_gabarit=True).count()
        
        # Total des émissions (les mixtes comptent double)
        nombre_emissions = nombre_surcharges_seules + nombre_hors_gabarit_seuls + (nombre_mixtes * 2)
        
        # Nombre de hors gabarit total
        nombre_hors_gabarit = nombre_hors_gabarit_seuls + nombre_mixtes
        
        return {
            'nombre_emissions': nombre_emissions,
            'nombre_hors_gabarit': nombre_hors_gabarit,
            'nombre_surcharges': nombre_surcharges_seules + nombre_mixtes,
            'nombre_mixtes': nombre_mixtes,
            'nombre_tickets': amendes.count(),  # Nombre réel de tickets
            'montant_emis': montant_emis,
            'montant_recouvre': montant_recouvre,
            'reste_a_recouvrer': montant_emis - montant_recouvre,
        }
    
    # ===================================================================
    # MÉTHODES MÉTIER
    # ===================================================================
    
    @property
    def nombre_amendes_comptabilisees(self):
        """
        Une amende surcharge + hors gabarit compte pour 2 amendes
        """
        if self.est_surcharge and self.est_hors_gabarit:
            return 2
        return 1
    
    @property
    def type_infraction_display(self):
        """Retourne le type d'infraction formaté"""
        if self.est_surcharge and self.est_hors_gabarit:
            return "Surcharge + Hors Gabarit"
        elif self.est_surcharge:
            return "Surcharge"
        elif self.est_hors_gabarit:
            return "Hors Gabarit"
        return "Non défini"
    
    def valider_paiement(self, regisseur):
        """
        Valide le paiement de l'amende (passage à statut payé)
        Seul un régisseur peut effectuer cette action
        
        Args:
            regisseur: Instance UtilisateurSUPPER (régisseur)
        
        Returns:
            bool: True si validation réussie
        """
        if self.statut == StatutAmende.PAYE:
            return False  # Déjà payé
        
        self.statut = StatutAmende.PAYE
        self.date_paiement = timezone.now()
        self.valide_par = regisseur
        self.save(update_fields=['statut', 'date_paiement', 'valide_par'])
        
        # Créer l'événement de paiement
        AmendeEvent.creer_evenement_paiement(self, regisseur)
        
        logger.info(
            f"Amende {self.numero_ticket} validée par {regisseur.username} "
            f"- Montant: {self.montant_amende} FCFA"
        )
        
        return True
    
    def save(self, *args, **kwargs):
        """
        Sauvegarde avec validation métier
        """
        # Vérifier qu'au moins un type d'infraction est coché
        if not self.est_surcharge and not self.est_hors_gabarit:
            raise ValueError("Au moins un type d'infraction doit être sélectionné")
        
        is_new = self.pk is None
        
        super().save(*args, **kwargs)
        
        # Créer l'événement d'émission si nouvelle amende
        if is_new:
            AmendeEvent.creer_evenement_emission(self)


# ===================================================================
# MODÈLE : PESÉES JOURNALIÈRES
# ===================================================================

class PeseesJournalieres(models.Model):
    """
    Nombre de pesées effectuées par jour par station
    Saisi une fois par jour par le chef d'équipe, non modifiable
    """
    
    station = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='pesees_journalieres',
        verbose_name=_("Station de pesage"),
        limit_choices_to={'type': 'pesage'}
    )
    
    # Date de la journée (9h à 9h du lendemain)
    date = models.DateField(
        verbose_name=_("Date"),
        help_text=_("Date de la journée de pesage (9h à 9h)")
    )
    
    nombre_pesees = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(10000)],
        verbose_name=_("Nombre de pesées"),
        help_text=_("Total des pesées effectuées")
    )
    
    # Traçabilité
    saisi_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.PROTECT,
        related_name='pesees_saisies',
        verbose_name=_("Saisi par")
    )
    
    date_saisie = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de saisie")
    )
    
    observations = models.TextField(
        blank=True,
        verbose_name=_("Observations")
    )
    
    class Meta:
        verbose_name = _("Pesées journalières")
        verbose_name_plural = _("Pesées journalières")
        unique_together = [['station', 'date']]
        ordering = ['-date', 'station__nom']
        indexes = [
            models.Index(fields=['station', '-date']),
        ]
    
    def __str__(self):
        return f"Pesées {self.station.nom} - {self.date}: {self.nombre_pesees}"


# ===================================================================
# MODÈLE : EVENT SOURCING POUR LES AMENDES
# ===================================================================

class AmendeEvent(models.Model):
    """
    Event Sourcing pour tracer tous les événements liés aux amendes
    Permet de reconstituer l'état à n'importe quelle date
    """
    
    EVENT_TYPES = [
        ('EMISSION', 'Émission de l\'amende'),
        ('PAIEMENT', 'Paiement validé'),
        ('ANNULATION', 'Annulation'),
    ]
    
    amende = models.ForeignKey(
        AmendeEmise,
        on_delete=models.CASCADE,
        related_name='events',
        verbose_name=_("Amende")
    )
    
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPES,
        verbose_name=_("Type d'événement")
    )
    
    event_datetime = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Date/heure de l'événement"),
        db_index=True
    )
    
    montant = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Montant")
    )
    
    effectue_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("Effectué par")
    )
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Métadonnées"),
        help_text=_("Données additionnelles de l'événement")
    )
    
    class Meta:
        verbose_name = _("Événement amende")
        verbose_name_plural = _("Événements amendes")
        ordering = ['-event_datetime']
        indexes = [
            models.Index(fields=['amende', '-event_datetime']),
            models.Index(fields=['event_type']),
        ]
    
    def __str__(self):
        return f"{self.get_event_type_display()} - {self.amende.numero_ticket}"
    
    @classmethod
    def creer_evenement_emission(cls, amende):
        """Crée un événement d'émission d'amende"""
        return cls.objects.create(
            amende=amende,
            event_type='EMISSION',
            event_datetime=amende.date_heure_emission,
            montant=amende.montant_amende,
            effectue_par=amende.saisi_par,
            metadata={
                'numero_ticket': amende.numero_ticket,
                'immatriculation': amende.immatriculation,
                'est_surcharge': amende.est_surcharge,
                'est_hors_gabarit': amende.est_hors_gabarit,
                'station_id': amende.station_id,
            }
        )
    
    @classmethod
    def creer_evenement_paiement(cls, amende, regisseur):
        """Crée un événement de paiement d'amende"""
        return cls.objects.create(
            amende=amende,
            event_type='PAIEMENT',
            event_datetime=amende.date_paiement,
            montant=amende.montant_amende,
            effectue_par=regisseur,
            metadata={
                'numero_ticket': amende.numero_ticket,
                'validated_by': regisseur.username,
            }
        )
    
    @classmethod
    def get_statistiques_periode(cls, station, date_debut, date_fin):
        """
        Calcule les statistiques via Event Sourcing pour une période
        
        Args:
            station: Poste de pesage
            date_debut: Date de début
            date_fin: Date de fin
        
        Returns:
            dict avec les statistiques
        """
        # Convertir en datetime si nécessaire
        if not isinstance(date_debut, datetime):
            debut_dt = AmendeEmise.get_date_debut_journee(date_debut)
        else:
            debut_dt = date_debut
            
        if not isinstance(date_fin, datetime):
            fin_dt = AmendeEmise.get_date_fin_journee(date_fin)
        else:
            fin_dt = date_fin
        
        # Récupérer les événements de la période
        events = cls.objects.filter(
            amende__station=station,
            event_datetime__gte=debut_dt,
            event_datetime__lte=fin_dt
        )
        
        # Agrégations
        emissions = events.filter(event_type='EMISSION')
        paiements = events.filter(event_type='PAIEMENT')
        
        montant_emis = emissions.aggregate(total=Sum('montant'))['total'] or Decimal('0')
        montant_recouvre = paiements.aggregate(total=Sum('montant'))['total'] or Decimal('0')
        
        # Comptage des types d'infractions via metadata
        nombre_hors_gabarit = 0
        nombre_surcharges = 0
        nombre_mixtes = 0
        
        for event in emissions:
            metadata = event.metadata or {}
            est_surcharge = metadata.get('est_surcharge', False)
            est_hors_gabarit = metadata.get('est_hors_gabarit', False)
            
            if est_surcharge and est_hors_gabarit:
                nombre_mixtes += 1
            elif est_surcharge:
                nombre_surcharges += 1
            elif est_hors_gabarit:
                nombre_hors_gabarit += 1
        
        # Calculer le nombre total d'émissions (mixtes = 2)
        nombre_emissions_total = nombre_surcharges + nombre_hors_gabarit + (nombre_mixtes * 2)
        
        return {
            'nombre_emissions': nombre_emissions_total,
            'nombre_tickets': emissions.count(),
            'nombre_hors_gabarit': nombre_hors_gabarit + nombre_mixtes,
            'nombre_surcharges': nombre_surcharges + nombre_mixtes,
            'montant_emis': montant_emis,
            'montant_recouvre': montant_recouvre,
            'reste_a_recouvrer': montant_emis - montant_recouvre,
        }


# ===================================================================
# MODÈLE : QUITTANCEMENT PESAGE
# ===================================================================

class TypeDeclarationPesage(models.TextChoices):
    """Types de déclaration pour quittancement pesage"""
    JOURNALIERE = 'journaliere', _('Journalière (Par Jour)')
    DECADE = 'decade', _('Par Décade')


class QuittancementPesage(models.Model):
    """
    Modèle pour gérer les quittancements des recettes de pesage (amendes)
    Calqué sur le modèle Quittancement du péage
    
    IMPORTANT: N'obéit PAS au principe 9h-9h (dates normales)
    Compare avec les amendes payées (AmendeEmise.statut=PAYE)
    """
    
    # Identification
    numero_quittance = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Numéro de quittance"),
        help_text=_("Numéro unique de la quittance")
    )
    
    station = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='quittancements_pesage',
        verbose_name=_("Station de pesage"),
        limit_choices_to={'type': 'pesage'}
    )
    
    # Période
    exercice = models.IntegerField(
        verbose_name=_("Exercice (Année)"),
        validators=[MinValueValidator(2020), MaxValueValidator(2099)],
        default=timezone.now().year
    )
    
    mois = models.CharField(
        max_length=7,
        verbose_name=_("Mois concerné"),
        help_text=_("Format: YYYY-MM"),
        blank=True
    )
    
    type_declaration = models.CharField(
        max_length=15,
        choices=TypeDeclarationPesage.choices,
        default=TypeDeclarationPesage.JOURNALIERE,
        verbose_name=_("Type de déclaration")
    )
    
    # Dates
    date_quittancement = models.DateField(
        verbose_name=_("Date de quittancement"),
        help_text=_("Date du jour du quittancement"),
        default=timezone.now().date()
    )
    
    # Pour JOURNALIERE
    date_recette = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date des amendes"),
        help_text=_("Date des amendes payées (si type = JOURNALIERE)")
    )
    
    # Pour DECADE
    date_debut_decade = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date début décade"),
        help_text=_("Si type = DECADE")
    )
    
    date_fin_decade = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date fin décade"),
        help_text=_("Si type = DECADE")
    )
    
    # Données financières
    montant_quittance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name=_("Montant quittancé (FCFA)")
    )
    
    # Montant calculé automatiquement depuis les amendes payées
    montant_attendu = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Montant attendu (FCFA)"),
        help_text=_("Calculé depuis les amendes payées")
    )
    
    ecart = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Écart (FCFA)"),
        help_text=_("Quittancé - Attendu")
    )
    
    # Document
    image_quittance = models.ImageField(
        upload_to='quittances_pesage/%Y/%m/',
        blank=True,
        null=True,
        verbose_name=_("Image de la quittance"),
        help_text=_("Scan ou photo de la quittance")
    )
    
    # Métadonnées
    saisi_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        related_name='quittancements_pesage_saisis',
        verbose_name=_("Saisi par")
    )
    
    date_saisie = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de saisie")
    )
    
    observations = models.TextField(
        blank=True,
        verbose_name=_("Observations"),
        help_text=_("Observations optionnelles")
    )
    
    # Verrouillage (non modifiable après création)
    verrouille = models.BooleanField(
        default=True,
        verbose_name=_("Verrouillé"),
        help_text=_("Les quittancements sont verrouillés dès leur création")
    )
    
    class Meta:
        verbose_name = _("Quittancement pesage")
        verbose_name_plural = _("Quittancements pesage")
        ordering = ['-date_quittancement', 'station__nom']
        indexes = [
            models.Index(fields=['station', 'exercice']),
            models.Index(fields=['station', 'mois']),
            models.Index(fields=['numero_quittance']),
            models.Index(fields=['date_quittancement']),
            models.Index(fields=['type_declaration']),
        ]
    
    def __str__(self):
        return f"Quittance Pesage {self.numero_quittance} - {self.station.nom}"
    
    def clean(self):
        """
        Validation métier stricte
        - Empêche le chevauchement des décades
        - Vérifie l'unicité des quittancements journaliers
        - Contrôle les dates futures
        - Vérifie les conflits entre journalier et decade
        """
        today = timezone.now().date()
        errors = {}
        
        # 1. Vérifier la date de quittancement
        if self.date_quittancement and self.date_quittancement > today:
            errors['date_quittancement'] = "La date de quittancement ne peut pas être dans le futur."
        
        # 2. Validation selon le type de déclaration
        if self.type_declaration == 'journaliere':
            # === VALIDATION JOURNALIÈRE ===
            if not self.date_recette:
                errors['date_recette'] = "Date des amendes obligatoire pour type journalière."
            
            elif self.date_recette > today:
                errors['date_recette'] = "La date des amendes ne peut pas être dans le futur."
            
            # Vérifier l'unicité pour ce jour et cette station
            elif self.date_recette and self.station_id:
                existing = QuittancementPesage.objects.filter(
                    station_id=self.station_id,
                    type_declaration='journaliere',
                    date_recette=self.date_recette
                ).exclude(pk=self.pk if self.pk else None)
                
                if existing.exists():
                    errors['date_recette'] = (
                        f"Un quittancement existe déjà pour le {self.date_recette.strftime('%d/%m/%Y')} "
                        f"sur cette station (N°{existing.first().numero_quittance})."
                    )
                
                # Vérifier si ce jour est inclus dans une décade existante
                decades_existantes = QuittancementPesage.objects.filter(
                    station_id=self.station_id,
                    type_declaration='decade',
                    date_debut_decade__lte=self.date_recette,
                    date_fin_decade__gte=self.date_recette
                ).exclude(pk=self.pk if self.pk else None)
                
                if decades_existantes.exists():
                    q = decades_existantes.first()
                    errors['date_recette'] = (
                        f"Ce jour est déjà couvert par la décade N°{q.numero_quittance} "
                        f"({q.date_debut_decade.strftime('%d/%m/%Y')} au {q.date_fin_decade.strftime('%d/%m/%Y')})."
                    )
            
            # Nettoyer les champs de décade
            self.date_debut_decade = None
            self.date_fin_decade = None
            
        elif self.type_declaration == 'decade':
            # === VALIDATION DÉCADE ===
            if not self.date_debut_decade:
                errors['date_debut_decade'] = "Date de début de décade obligatoire."
            
            if not self.date_fin_decade:
                errors['date_fin_decade'] = "Date de fin de décade obligatoire."
            
            # Vérifier les dates futures
            if self.date_debut_decade and self.date_debut_decade > today:
                errors['date_debut_decade'] = "La date de début ne peut pas être dans le futur."
            
            if self.date_fin_decade and self.date_fin_decade > today:
                errors['date_fin_decade'] = "La date de fin ne peut pas être dans le futur."
            
            # Vérifier la cohérence des dates
            if self.date_debut_decade and self.date_fin_decade:
                if self.date_debut_decade > self.date_fin_decade:
                    errors['date_fin_decade'] = "La date de fin doit être après la date de début."
                
                # Vérifier que la décade ne dépasse pas 31 jours
                delta = (self.date_fin_decade - self.date_debut_decade).days
                if delta > 30:
                    errors['date_fin_decade'] = "Une décade ne peut pas dépasser 31 jours."
                
                # === VÉRIFICATION CHEVAUCHEMENT ===
                if self.station_id:
                    # 1. Vérifier les chevauchements avec d'autres décades
                    chevauchements_decade = QuittancementPesage.objects.filter(
                        station_id=self.station_id,
                        type_declaration='decade'
                    ).exclude(pk=self.pk if self.pk else None)
                    
                    for q in chevauchements_decade:
                        if (self.date_debut_decade <= q.date_fin_decade and 
                            self.date_fin_decade >= q.date_debut_decade):
                            
                            debut_conflit = max(self.date_debut_decade, q.date_debut_decade)
                            fin_conflit = min(self.date_fin_decade, q.date_fin_decade)
                            jours_conflit = (fin_conflit - debut_conflit).days + 1
                            
                            errors['date_debut_decade'] = (
                                f"Cette période chevauche avec le quittancement N°{q.numero_quittance} "
                                f"({q.date_debut_decade.strftime('%d/%m/%Y')} au "
                                f"{q.date_fin_decade.strftime('%d/%m/%Y')}). "
                                f"{jours_conflit} jour(s) en conflit."
                            )
                            break
                    
                    # 2. Vérifier avec les quittancements journaliers
                    dates_decade = []
                    current_date = self.date_debut_decade
                    while current_date <= self.date_fin_decade:
                        dates_decade.append(current_date)
                        current_date += timedelta(days=1)
                    
                    quittancements_journaliers = QuittancementPesage.objects.filter(
                        station_id=self.station_id,
                        type_declaration='journaliere',
                        date_recette__in=dates_decade
                    ).exclude(pk=self.pk if self.pk else None)
                    
                    if quittancements_journaliers.exists():
                        jours_conflits = list(quittancements_journaliers.values_list('date_recette', flat=True))
                        jours_str = ', '.join([d.strftime('%d/%m/%Y') for d in jours_conflits[:3]])
                        if len(jours_conflits) > 3:
                            jours_str += f" et {len(jours_conflits) - 3} autre(s)"
                        
                        errors['date_debut_decade'] = (
                            f"Cette décade contient des jours déjà quittancés individuellement : {jours_str}"
                        )
            
            # Nettoyer le champ date_recette
            self.date_recette = None
        
        if errors:
            raise ValidationError(errors)
    
    def calculer_montant_attendu(self):
        """
        Calcule le montant attendu depuis les amendes payées
        
        IMPORTANT: Utilise date_paiement__date (dates normales, PAS 9h-9h)
        
        Returns:
            Decimal: Somme des amendes payées sur la période
        """
        # Import local pour éviter les imports circulaires
        try:
            from inventaire.models_pesage import AmendeEmise, StatutAmende
        except ImportError:
            # Fallback si import direct ne fonctionne pas
            AmendeEmise = self.__class__._meta.apps.get_model('inventaire', 'AmendeEmise')
            StatutAmende = type('StatutAmende', (), {'PAYE': 'paye'})
        
        if self.type_declaration == 'journaliere':
            if not self.date_recette:
                return Decimal('0')
            
            # Amendes payées ce jour (date normale)
            amendes = AmendeEmise.objects.filter(
                station=self.station,
                statut='paye',  # StatutAmende.PAYE
                date_paiement__date=self.date_recette
            )
        else:  # decade
            if not self.date_debut_decade or not self.date_fin_decade:
                return Decimal('0')
            
            # Amendes payées dans la période (dates normales)
            amendes = AmendeEmise.objects.filter(
                station=self.station,
                statut='paye',  # StatutAmende.PAYE
                date_paiement__date__gte=self.date_debut_decade,
                date_paiement__date__lte=self.date_fin_decade
            )
        
        total = amendes.aggregate(
            total=Sum('montant_amende')
        )['total'] or Decimal('0')
        
        return total
    
    def save(self, *args, **kwargs):
        """Sauvegarde avec validation, calcul automatique et verrouillage"""
        self.full_clean()
        
        # Calculer le montant attendu
        self.montant_attendu = self.calculer_montant_attendu()
        
        # Calculer l'écart
        self.ecart = self.montant_quittance - self.montant_attendu
        
        # Toujours verrouillé
        self.verrouille = True
        
        super().save(*args, **kwargs)
    
    def get_periode_display(self):
        """Affichage de la période"""
        if self.type_declaration == 'journaliere':
            return f"Jour : {self.date_recette.strftime('%d/%m/%Y') if self.date_recette else 'N/A'}"
        else:
            if self.date_debut_decade and self.date_fin_decade:
                return f"Décade : {self.date_debut_decade.strftime('%d/%m/%Y')} au {self.date_fin_decade.strftime('%d/%m/%Y')}"
            return "Décade : N/A"
    
    def get_amendes_periode(self):
        """
        Retourne les amendes payées correspondant à la période
        
        Returns:
            QuerySet: Amendes payées de la période
        """
        try:
            from inventaire.models_pesage import AmendeEmise
        except ImportError:
            AmendeEmise = self.__class__._meta.apps.get_model('inventaire', 'AmendeEmise')
        
        if self.type_declaration == 'journaliere':
            if not self.date_recette:
                return AmendeEmise.objects.none()
            
            return AmendeEmise.objects.filter(
                station=self.station,
                statut='paye',
                date_paiement__date=self.date_recette
            )
        else:
            if not self.date_debut_decade or not self.date_fin_decade:
                return AmendeEmise.objects.none()
            
            return AmendeEmise.objects.filter(
                station=self.station,
                statut='paye',
                date_paiement__date__gte=self.date_debut_decade,
                date_paiement__date__lte=self.date_fin_decade
            )


class JustificationEcartPesage(models.Model):
    """
    Modèle pour justifier les écarts de comptabilisation pesage
    Entre montants quittancés et amendes payées
    """
    
    station = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='justifications_ecart_pesage',
        verbose_name=_("Station de pesage"),
        limit_choices_to={'type': 'pesage'}
    )
    
    # Période de justification
    date_debut = models.DateField(
        verbose_name=_("Date début période")
    )
    
    date_fin = models.DateField(
        verbose_name=_("Date fin période")
    )
    
    # Montants calculés
    montant_quittance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_("Montant total quittancé")
    )
    
    montant_attendu = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_("Montant attendu (amendes payées)")
    )
    
    ecart = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_("Écart"),
        help_text=_("Quittancé - Attendu")
    )
    
    # Justification
    justification = models.TextField(
        verbose_name=_("Justification de l'écart"),
        help_text=_("Explication détaillée de l'écart constaté (min. 20 caractères)")
    )
    
    # Métadonnées
    justifie_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        related_name='justifications_pesage_effectuees',
        verbose_name=_("Justifié par")
    )
    
    date_justification = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de justification")
    )
    
    class Meta:
        verbose_name = _("Justification d'écart pesage")
        verbose_name_plural = _("Justifications d'écarts pesage")
        ordering = ['-date_justification']
        unique_together = [['station', 'date_debut', 'date_fin']]
        indexes = [
            models.Index(fields=['station', '-date_justification']),
        ]
    
    def __str__(self):
        return f"Justification Pesage {self.station.nom} - {self.date_debut} au {self.date_fin}"
    
    def clean(self):
        """Validation de la justification"""
        if self.justification and len(self.justification.strip()) < 20:
            raise ValidationError({
                'justification': "La justification doit contenir au moins 20 caractères."
            })


# ===================================================================
# MODÈLE : STATISTIQUES PESAGE PÉRIODIQUES
# ===================================================================

class StatistiquesPesagePeriodique(models.Model):
    """
    Statistiques consolidées pour les stations de pesage
    """
    
    TYPE_PERIODE = [
        ('journalier', 'Journalier'),
        ('hebdomadaire', 'Hebdomadaire'),
        ('mensuel', 'Mensuel'),
        ('annuel', 'Annuel'),
    ]
    
    station = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='statistiques_pesage',
        verbose_name=_("Station de pesage"),
        limit_choices_to={'type': 'pesage'}
    )
    
    type_periode = models.CharField(
        max_length=15,
        choices=TYPE_PERIODE,
        verbose_name=_("Type de période")
    )
    
    date_debut = models.DateField(
        verbose_name=_("Date de début")
    )
    
    date_fin = models.DateField(
        verbose_name=_("Date de fin")
    )
    
    # Statistiques
    nombre_pesees = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Nombre de pesées")
    )
    
    nombre_emissions = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Nombre d'émissions"),
        help_text=_("Surcharge + HG comptent double")
    )
    
    nombre_hors_gabarit = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Nombre de hors gabarit")
    )
    
    montant_emis = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Montant total émis")
    )
    
    montant_recouvre = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Montant recouvré")
    )
    
    reste_a_recouvrer = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Reste à recouvrer")
    )
    
    date_calcul = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Date du calcul")
    )
    
    class Meta:
        verbose_name = _("Statistiques pesage")
        verbose_name_plural = _("Statistiques pesage")
        unique_together = [['station', 'type_periode', 'date_debut']]
        ordering = ['-date_debut']
        indexes = [
            models.Index(fields=['station', 'type_periode', '-date_debut']),
        ]
    
    def __str__(self):
        return f"Stats {self.station.nom} - {self.type_periode} ({self.date_debut})"
    
    @classmethod
    def calculer_et_sauvegarder(cls, station, type_periode, date_debut, date_fin):
        """
        Calcule et sauvegarde les statistiques pour une période
        """
        # Utiliser l'Event Sourcing pour les stats
        stats = AmendeEvent.get_statistiques_periode(station, date_debut, date_fin)
        
        # Récupérer le nombre de pesées
        pesees = PeseesJournalieres.objects.filter(
            station=station,
            date__gte=date_debut,
            date__lte=date_fin
        ).aggregate(total=Sum('nombre_pesees'))['total'] or 0
        
        # Créer ou mettre à jour
        obj, created = cls.objects.update_or_create(
            station=station,
            type_periode=type_periode,
            date_debut=date_debut,
            defaults={
                'date_fin': date_fin,
                'nombre_pesees': pesees,
                'nombre_emissions': stats['nombre_emissions'],
                'nombre_hors_gabarit': stats['nombre_hors_gabarit'],
                'montant_emis': stats['montant_emis'],
                'montant_recouvre': stats['montant_recouvre'],
                'reste_a_recouvrer': stats['reste_a_recouvrer'],
            }
        )
        
        return obj
