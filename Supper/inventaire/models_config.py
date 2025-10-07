from django.db import models
from django.utils.translation import gettext_lazy as _
from accounts.models import Poste

class ConfigurationGlobale(models.Model):
    """Configuration globale unique pour tous les postes"""
    
    # Logo unique
    logo = models.ImageField(
        upload_to='logos/',
        null=True,
        blank=True,
        verbose_name=_("Logo")
    )
    
    # Français
    republique_fr = models.CharField(
        max_length=200,
        default="RÉPUBLIQUE DU CAMEROUN",
        verbose_name=_("République (FR)")
    )
    
    devise_fr = models.CharField(
        max_length=200,
        default="Paix-Travail-Patrie",
        verbose_name=_("Devise (FR)")
    )
    
    ministere_fr = models.CharField(
        max_length=300,
        default="MINISTÈRE DES FINANCES",
        verbose_name=_("Ministère (FR)")
    )
    
    direction_fr = models.CharField(
        max_length=300,
        default="DIRECTION GÉNÉRALE DES IMPÔTS",
        verbose_name=_("Direction (FR)")
    )
    
    programme_fr = models.CharField(
        max_length=300,
        default="PROGRAMME DE SÉCURISATION DES RECETTES ROUTIÈRES",
        verbose_name=_("Programme (FR)")
    )
    
    # Anglais
    republique_en = models.CharField(
        max_length=200,
        default="REPUBLIC OF CAMEROON",
        verbose_name=_("République (EN)")
    )
    
    devise_en = models.CharField(
        max_length=200,
        default="Peace-Work-Fatherland",
        verbose_name=_("Devise (EN)")
    )
    
    ministere_en = models.CharField(
        max_length=300,
        default="MINISTRY OF FINANCE",
        verbose_name=_("Ministère (EN)")
    )
    
    direction_en = models.CharField(
        max_length=300,
        default="GENERAL DIRECTORATE OF TAXATION",
        verbose_name=_("Direction (EN)")
    )
    
    programme_en = models.CharField(
        max_length=300,
        default="REGIONAL TAXATION CENTER",
        verbose_name=_("Programme (EN)")
    )
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Configuration globale")
        verbose_name_plural = _("Configuration globale")
    
    def __str__(self):
        return "Configuration globale SUPPER"
    
    @classmethod
    def get_config(cls):
        """Récupère ou crée la configuration unique"""
        config, created = cls.objects.get_or_create(id=1)
        return config