# ==============================================================================
# inventaire/models_historique_pesage.py - VERSION SIMPLIFIÉE
# ==============================================================================
# Historique ACCT pour les stations de pesage
# ==============================================================================

import os
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from accounts.models import Poste, UtilisateurSUPPER


def historique_pesage_upload_path(instance, filename):
    """
    Génère le chemin de stockage pour les images d'historique pesage.
    Format: historiques_pesage/YYYY/MM/station_code/filename
    """
    ext = filename.split('.')[-1].lower()
    station_code = instance.station.code if instance.station else 'unknown'
    new_filename = f"{station_code}_{instance.annee}_{instance.mois:02d}_{timezone.now().strftime('%Y%m%d%H%M%S')}.{ext}"
    return f"historiques_pesage/{instance.annee}/{instance.mois:02d}/{station_code}/{new_filename}"


def historique_pesage_page2_upload_path(instance, filename):
    """Chemin pour la page 2."""
    ext = filename.split('.')[-1].lower()
    station_code = instance.station.code if instance.station else 'unknown'
    new_filename = f"{station_code}_{instance.annee}_{instance.mois:02d}_p2_{timezone.now().strftime('%Y%m%d%H%M%S')}.{ext}"
    return f"historiques_pesage/{instance.annee}/{instance.mois:02d}/{station_code}/{new_filename}"


def historique_pesage_page3_upload_path(instance, filename):
    """Chemin pour la page 3."""
    ext = filename.split('.')[-1].lower()
    station_code = instance.station.code if instance.station else 'unknown'
    new_filename = f"{station_code}_{instance.annee}_{instance.mois:02d}_p3_{timezone.now().strftime('%Y%m%d%H%M%S')}.{ext}"
    return f"historiques_pesage/{instance.annee}/{instance.mois:02d}/{station_code}/{new_filename}"


class HistoriquesPesage(models.Model):
    """
    Historique mensuel ACCT pour les stations de pesage.
    
    Explication des montants:
    - montant_global: Montant TOTAL versé à la perception (peut inclure plusieurs stations
      qui versent dans la même perception)
    - montant_reel: Part de CETTE station dans le montant global
    
    Règle: montant_reel <= montant_global (toujours)
    
    Images:
    - image_page1: Page 1 du document ACCT (obligatoire via formulaire, nullable en DB)
    - image_page2: Page 2 du document ACCT (optionnelle)
    - image_page3: Page 3 du document ACCT (optionnelle)
    """
    
    # Station concernée
    station = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='historiques_pesage',
        verbose_name="Station de pesage",
        limit_choices_to={'type': 'pesage'}
    )
    
    # Période (mois/année)
    mois = models.PositiveSmallIntegerField(
        verbose_name="Mois",
        choices=[(i, f"{i:02d}") for i in range(1, 13)]
    )
    annee = models.PositiveIntegerField(
        verbose_name="Année"
    )
    
    # Montants
    montant_global = models.DecimalField(
        max_digits=15,
        decimal_places=0,
        verbose_name="Montant global (FCFA)",
        help_text="Montant TOTAL versé à la perception (peut inclure plusieurs stations)"
    )
    
    montant_reel = models.DecimalField(
        max_digits=15,
        decimal_places=0,
        verbose_name="Montant réel station (FCFA)",
        help_text="Part de CETTE station dans le montant global"
    )
    
    # =========================================================================
    # IMAGES DU DOCUMENT ACCT (3 pages possibles)
    # Note: image_page1 est nullable en DB mais obligatoire via le formulaire
    # Cela permet d'ajouter le champ sans valeur par défaut pour les anciens enregistrements
    # =========================================================================
    
    image_page1 = models.ImageField(
        upload_to=historique_pesage_upload_path,
        verbose_name="Image Page 1",
        help_text="Première page du document ACCT - Format: JPG, PNG, PDF (max 5 Mo)",
        blank=True,
        null=True
    )
    
    image_page2 = models.ImageField(
        upload_to=historique_pesage_page2_upload_path,
        verbose_name="Image Page 2 (optionnelle)",
        help_text="Deuxième page du document ACCT si nécessaire",
        blank=True,
        null=True
    )
    
    image_page3 = models.ImageField(
        upload_to=historique_pesage_page3_upload_path,
        verbose_name="Image Page 3 (optionnelle)",
        help_text="Troisième page du document ACCT si nécessaire",
        blank=True,
        null=True
    )
    
    # Observations
    observations = models.TextField(
        blank=True,
        null=True,
        verbose_name="Observations"
    )
    
    # Métadonnées
    cree_par = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        related_name='historiques_pesage_crees',
        verbose_name="Créé par"
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )
    
    class Meta:
        verbose_name = "Historique Pesage ACCT"
        verbose_name_plural = "Historiques Pesage ACCT"
        ordering = ['-annee', '-mois', 'station__nom']
        unique_together = ['station', 'mois', 'annee']
        indexes = [
            models.Index(fields=['station', 'mois', 'annee']),
            models.Index(fields=['annee', 'mois']),
        ]
    
    def clean(self):
        """Validation personnalisée."""
        super().clean()
        
        # Validation: montant_reel <= montant_global
        if self.montant_reel and self.montant_global:
            if self.montant_reel > self.montant_global:
                raise ValidationError({
                    'montant_reel': (
                        f"Le montant réel ({self.montant_reel:,.0f} FCFA) ne peut pas "
                        f"être supérieur au montant global ({self.montant_global:,.0f} FCFA). "
                        f"Le montant réel représente la part de cette station dans le versement total."
                    )
                })
        
        # Validation: montants positifs
        if self.montant_global and self.montant_global < 0:
            raise ValidationError({
                'montant_global': "Le montant global doit être positif."
            })
        
        if self.montant_reel and self.montant_reel < 0:
            raise ValidationError({
                'montant_reel': "Le montant réel doit être positif."
            })
        
        # Validation: mois entre 1 et 12
        if self.mois and (self.mois < 1 or self.mois > 12):
            raise ValidationError({
                'mois': "Le mois doit être compris entre 1 et 12."
            })
        
        # Validation: année raisonnable
        annee_courante = timezone.now().year
        if self.annee and (self.annee < 2020 or self.annee > annee_courante):
            raise ValidationError({
                'annee': f"L'année doit être comprise entre 2020 et {annee_courante}."
            })
        
        # Validation: pas de mois futur
        if self.annee and self.mois:
            from datetime import date
            today = date.today()
            if self.annee == today.year and self.mois > today.month:
                raise ValidationError({
                    'mois': "Vous ne pouvez pas saisir un historique pour un mois futur."
                })
    
    def save(self, *args, **kwargs):
        """Validation avant sauvegarde."""
        # Ne pas appeler full_clean() si c'est une mise à jour partielle (images)
        if not kwargs.pop('skip_validation', False):
            self.full_clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.station.nom} - {self.mois:02d}/{self.annee}"
    
    # ===========================================================================
    # MÉTHODES DE CLASSE (classmethod)
    # ===========================================================================
    
    @classmethod
    def existe_pour_mois(cls, station, mois_str):
        """
        Vérifie si un historique existe déjà pour une station et un mois donné.
        
        Args:
            station: Instance de Poste
            mois_str: Chaîne au format 'YYYY-MM' (ex: '2026-03')
        
        Returns:
            bool: True si un historique existe, False sinon
        """
        try:
            annee, mois = mois_str.split('-')
            return cls.objects.filter(
                station=station,
                annee=int(annee),
                mois=int(mois)
            ).exists()
        except (ValueError, AttributeError):
            return False
    
    @classmethod
    def get_historique_mois(cls, station, mois_str):
        """
        Récupère l'historique pour une station et un mois donné.
        
        Args:
            station: Instance de Poste
            mois_str: Chaîne au format 'YYYY-MM' (ex: '2026-03')
        
        Returns:
            HistoriquesPesage ou None
        """
        try:
            annee, mois = mois_str.split('-')
            return cls.objects.get(
                station=station,
                annee=int(annee),
                mois=int(mois)
            )
        except (ValueError, AttributeError, cls.DoesNotExist):
            return None
    
    @classmethod
    def get_historiques_station(cls, station, annee=None):
        """
        Récupère tous les historiques d'une station, optionnellement filtrés par année.
        
        Args:
            station: Instance de Poste
            annee: Année de filtrage (optionnel)
        
        Returns:
            QuerySet d'HistoriquesPesage
        """
        queryset = cls.objects.filter(station=station)
        if annee:
            queryset = queryset.filter(annee=annee)
        return queryset.order_by('-annee', '-mois')
    
    @classmethod
    def get_montant_reel_pour_periode(cls, station, mois_str):
        """
        Récupère le montant réel pour une station et un mois donné.
        Utilisé par le CSP Pesage.
        
        Args:
            station: Instance de Poste
            mois_str: Chaîne au format 'YYYY-MM' (ex: '2026-03')
        
        Returns:
            Decimal: montant_reel ou 0
        """
        from decimal import Decimal
        historique = cls.get_historique_mois(station, mois_str)
        if historique:
            return historique.montant_reel
        return Decimal('0')
    
    # ===========================================================================
    # PROPRIÉTÉS
    # ===========================================================================
    
    @property
    def mois_str(self):
        """Retourne le mois au format 'YYYY-MM'."""
        return f"{self.annee}-{self.mois:02d}"
    
    @property
    def periode_display(self):
        """Affichage formaté de la période."""
        mois_noms = [
            '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
        ]
        return f"{mois_noms[self.mois]} {self.annee}"
    
    def get_mois_display(self):
        """Alias pour periode_display (compatibilité avec les vues)."""
        return self.periode_display
    
    @property
    def ecart_montants(self):
        """Différence entre montant global et montant réel (part des autres stations)."""
        if self.montant_global and self.montant_reel:
            return self.montant_global - self.montant_reel
        return 0
    
    @property
    def pourcentage_station(self):
        """Pourcentage de la station dans le montant global."""
        if self.montant_global and self.montant_global > 0 and self.montant_reel:
            return (self.montant_reel / self.montant_global) * 100
        return 100
    
    @property
    def nombre_pages(self):
        """Retourne le nombre de pages d'images."""
        count = 1 if self.image_page1 else 0
        if self.image_page2:
            count += 1
        if self.image_page3:
            count += 1
        return count
    
    @property
    def has_multiple_pages(self):
        """Indique si l'historique a plusieurs pages."""
        return self.image_page2 or self.image_page3
    
    def get_all_images(self):
        """Retourne une liste de toutes les images disponibles."""
        images = []
        if self.image_page1:
            images.append({'page': 1, 'image': self.image_page1, 'label': 'Page 1'})
        if self.image_page2:
            images.append({'page': 2, 'image': self.image_page2, 'label': 'Page 2'})
        if self.image_page3:
            images.append({'page': 3, 'image': self.image_page3, 'label': 'Page 3'})
        return images