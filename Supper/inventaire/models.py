# ===================================================================
# inventaire/models.py - Modèles pour la gestion des inventaires SUPPER
# ===================================================================

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from accounts.models import UtilisateurSUPPER, Poste
from django.urls import reverse
import calendar

class MoisChoices(models.TextChoices):
    """Choix des mois pour l'inventaire mensuel"""
    JANVIER = '01', _('Janvier')
    FEVRIER = '02', _('Février')
    MARS = '03', _('Mars')
    AVRIL = '04', _('Avril')
    MAI = '05', _('Mai')
    JUIN = '06', _('Juin')
    JUILLET = '07', _('Juillet')
    AOUT = '08', _('Août')
    SEPTEMBRE = '09', _('Septembre')
    OCTOBRE = '10', _('Octobre')
    NOVEMBRE = '11', _('Novembre')
    DECEMBRE = '12', _('Décembre')


# ===================================================================
# CORRECTION DANS inventaire/models.py
# Remplacer la classe InventaireMensuel
# ===================================================================

class InventaireMensuel(models.Model):
    """
    Modèle pour organiser les inventaires par mois
    Permet d'activer/désactiver des jours spécifiques pour la saisie
    """
    
    titre = models.CharField(
        max_length=200,
        verbose_name=_("Titre de l'inventaire"),
        help_text=_("Titre descriptif pour cet inventaire mensuel")
    )
    
    mois = models.CharField(
        max_length=2,
        choices=MoisChoices.choices,
        verbose_name=_("Mois")
    )
    
    annee = models.IntegerField(
        verbose_name=_("Année"),
        help_text=_("Année de l'inventaire")
    )
    
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Description détaillée de cet inventaire mensuel")
    )
    
    # 🔧 CORRECTION : JSONField simplifié
    jours_actifs = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Jours actifs"),
        help_text=_("Liste des jours du mois où la saisie est autorisée"),
        encoder= None
    )
    
    # Métadonnées
    cree_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        related_name='inventaires_mensuels_crees',
        verbose_name=_("Créé par")
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name=_("Inventaire actif"),
        help_text=_("Indique si cet inventaire mensuel est en cours")
    )
    
    def get_jours_actifs_display(self):
        """Retourne une représentation textuelle des jours actifs"""
        if not self.jours_actifs:
            return "Aucun jour sélectionné"
        
        if isinstance(self.jours_actifs, list):
            if len(self.jours_actifs) == 0:
                return "Aucun jour sélectionné"
            elif len(self.jours_actifs) <= 5:
                return f"Jours: {', '.join(map(str, sorted(self.jours_actifs)))}"
            else:
                return f"{len(self.jours_actifs)} jours sélectionnés"
        
        return str(self.jours_actifs)
    
    def clean(self):
        """Validation du modèle"""
        from django.core.exceptions import ValidationError
        import json
        
        # Validation et nettoyage des jours_actifs
        if self.jours_actifs is not None:
            if not isinstance(self.jours_actifs, list):
                if isinstance(self.jours_actifs, str):
                    try:
                        self.jours_actifs = json.loads(self.jours_actifs)
                    except (json.JSONDecodeError, ValueError):
                        self.jours_actifs = []
                else:
                    self.jours_actifs = []
            
            # Valider que tous les éléments sont des entiers valides
            jours_valides = []
            for jour in self.jours_actifs:
                try:
                    jour_int = int(jour)
                    if 1 <= jour_int <= 31:
                        jours_valides.append(jour_int)
                except (ValueError, TypeError):
                    continue
            
            self.jours_actifs = sorted(list(set(jours_valides)))  # Supprimer les doublons
    
    def save(self, *args, **kwargs):
        """Surcharge pour validation automatique"""
        self.clean()
        super().save(*args, **kwargs)
    
    def get_mois_display(self):
        """Retourne le nom du mois en français"""
        if isinstance(self.mois, str):
            mois_num = int(self.mois)
        else:
            mois_num = self.mois
            
        mois_noms = {
            1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
            5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
            9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
        }
        return mois_noms.get(mois_num, f'Mois {mois_num}')

    def get_nombre_postes(self):
        """Retourne le nombre de postes dans le système"""
        from accounts.models import Poste
        return Poste.objects.filter(actif=True).count()
    
    def get_calendrier_mois(self):
        """Génère le calendrier du mois sous forme de grille"""
        import calendar
        mois_int = int(self.mois)
        cal = calendar.monthcalendar(int(self.annee), mois_int)
        return cal
    
    def est_jour_actif(self, jour):
        """Vérifie si un jour donné est actif pour la saisie"""
        if not self.jours_actifs or not isinstance(self.jours_actifs, list):
            return False
        return jour in self.jours_actifs
    
    def activer_jour(self, jour):
        """Active un jour pour la saisie"""
        if not self.jours_actifs:
            self.jours_actifs = []
        elif not isinstance(self.jours_actifs, list):
            self.jours_actifs = []
            
        if jour not in self.jours_actifs and 1 <= jour <= 31:
            self.jours_actifs.append(jour)
            self.jours_actifs = sorted(self.jours_actifs)
            self.save()
    
    def desactiver_jour(self, jour):
        """Désactive un jour pour la saisie"""
        if self.jours_actifs and isinstance(self.jours_actifs, list) and jour in self.jours_actifs:
            self.jours_actifs.remove(jour)
            self.save()
    
    def activer_jours_ouvres(self):
        """Active automatiquement tous les jours ouvrés (lundi à vendredi)"""
        import calendar
        
        mois_int = int(self.mois)
        cal = calendar.monthcalendar(int(self.annee), mois_int)
        jours_ouvres = []
        
        for semaine in cal:
            for i, jour in enumerate(semaine):
                if jour != 0 and i < 5:  # Lundi à vendredi
                    jours_ouvres.append(jour)
        
        self.jours_actifs = sorted(jours_ouvres)
        self.save()
        
    def generer_configurations_jours(self):
        """Génère automatiquement les ConfigurationJour pour tous les jours actifs"""
        from datetime import date
        
        if not self.jours_actifs or not isinstance(self.jours_actifs, list):
            return []
        
        configurations_creees = []
        
        for jour in self.jours_actifs:
            try:
                mois_int = int(self.mois)
                date_jour = date(int(self.annee), mois_int, jour)
                
                # 🔧 CORRECTION : Import local pour éviter circular import
                from . import models as inv_models
                
                config, created = inv_models.ConfigurationJour.objects.get_or_create(
                    date=date_jour,
                    defaults={
                        'statut': inv_models.StatutJour.OUVERT,
                        'cree_par': self.cree_par,
                        'commentaire': f'Généré automatiquement depuis {self.titre}'
                    }
                )
                
                if created:
                    configurations_creees.append(config)
                    
            except ValueError:
                # Jour invalide (ex: 31 février)
                continue
        
        return configurations_creees
    
    # 🔧 CORRECTION : Une seule classe Meta
    class Meta:
        verbose_name = _("Inventaire mensuel")
        verbose_name_plural = _("Inventaires mensuels")
        unique_together = [['mois', 'annee']]
        ordering = ['-annee', '-mois']
        indexes = [
            models.Index(fields=['mois', 'annee']),
            models.Index(fields=['actif']),
        ]
    
    def __str__(self):
        return f"{self.titre} - {self.get_mois_display()} {self.annee}"
    
    def get_absolute_url(self):
        return reverse('admin:inventaire_inventairemensuel_change', kwargs={'object_id': self.pk})
    
class StatutJour(models.TextChoices):
    """Statut d'un jour pour la saisie d'inventaire"""
    OUVERT = 'ouvert', _('Ouvert pour saisie')
    FERME = 'ferme', _('Fermé - saisie verrouillée')
    IMPERTINENT = 'impertinent', _('Journée impertinente')


class PeriodeHoraire(models.TextChoices):
    """Créneaux horaires pour l'inventaire"""
    H08_09 = '08h-09h', _('08h-09h')
    H09_10 = '09h-10h', _('09h-10h')
    H10_11 = '10h-11h', _('10h-11h')
    H11_12 = '11h-12h', _('11h-12h')
    H12_13 = '12h-13h', _('12h-13h')
    H13_14 = '13h-14h', _('13h-14h')
    H14_15 = '14h-15h', _('14h-15h')
    H15_16 = '15h-16h', _('15h-16h')
    H16_17 = '16h-17h', _('16h-17h')
    H17_18 = '17h-18h', _('17h-18h')


class ConfigurationJour(models.Model):
    """
    Configuration des jours ouverts/fermés pour la saisie d'inventaire
    Permet aux administrateurs de contrôler quels jours sont disponibles pour la saisie
    """
    
    date = models.DateField(
        unique=True,
        verbose_name=_("Date"),
        help_text=_("Date concernée par cette configuration")
    )
    
    statut = models.CharField(
        max_length=15,
        choices=StatutJour.choices,
        default=StatutJour.OUVERT,
        verbose_name=_("Statut du jour")
    )
    
    # Métadonnées de gestion
    cree_par = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        related_name='jours_configures',
        verbose_name=_("Configuré par")
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    commentaire = models.TextField(
        blank=True,
        verbose_name=_("Commentaire"),
        help_text=_("Raison de la configuration ou notes particulières")
    )
    
    class Meta:
        verbose_name = _("Configuration de jour")
        verbose_name_plural = _("Configurations de jours")
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['statut']),
        ]
    
    def __str__(self):
        return f"{self.date.strftime('%d/%m/%Y')} - {self.get_statut_display()}"
    
    @classmethod
    def est_jour_ouvert(cls, date):
        """Vérifie si un jour donné est ouvert pour la saisie"""
        try:
            config = cls.objects.get(date=date)
            return config.statut == StatutJour.OUVERT
        except cls.DoesNotExist:
            # Par défaut, les jours non configurés sont fermés
            return False
    
    @classmethod
    def marquer_impertinent(cls, date, admin_user, commentaire=""):
        """Marque un jour comme impertinent"""
        config, created = cls.objects.get_or_create(
            date=date,
            defaults={
                'statut': StatutJour.IMPERTINENT,
                'cree_par': admin_user,
                'commentaire': commentaire
            }
        )
        
        if not created and config.statut != StatutJour.IMPERTINENT:
            config.statut = StatutJour.IMPERTINENT
            config.commentaire = commentaire
            config.save()
        
        return config


class InventaireJournalier(models.Model):
    """
    Modèle principal pour l'inventaire journalier d'un poste
    Un enregistrement par jour et par poste
    """
    
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='inventaires',
        verbose_name=_("Poste")
    )
    
    date = models.DateField(
        verbose_name=_("Date de l'inventaire"),
        help_text=_("Date pour laquelle l'inventaire est effectué")
    )
    
    agent_saisie = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        related_name='inventaires_saisis',
        verbose_name=_("Agent de saisie")
    )
    
    # État de l'inventaire
    verrouille = models.BooleanField(
        default=False,
        verbose_name=_("Inventaire verrouillé"),
        help_text=_("Une fois verrouillé, l'inventaire ne peut plus être modifié")
    )
    
    valide = models.BooleanField(
        default=False,
        verbose_name=_("Inventaire validé"),
        help_text=_("Validation par un responsable")
    )
    
    valide_par = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventaires_valides',
        verbose_name=_("Validé par")
    )
    
    date_validation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Date de validation")
    )
    
    # Totaux calculés automatiquement
    total_vehicules = models.IntegerField(
        default=0,
        verbose_name=_("Total véhicules comptés"),
        help_text=_("Somme de tous les véhicules comptés dans les périodes")
    )
    
    nombre_periodes_saisies = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de périodes saisies"),
        help_text=_("Nombre de créneaux horaires avec données")
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )
    
    observations = models.TextField(
        blank=True,
        verbose_name=_("Observations"),
        help_text=_("Notes particulières sur cet inventaire")
    )
    
    class Meta:
        verbose_name = _("Inventaire journalier")
        verbose_name_plural = _("Inventaires journaliers")
        unique_together = [['poste', 'date']]
        ordering = ['-date', 'poste__nom']
        indexes = [
            models.Index(fields=['poste', '-date']),
            models.Index(fields=['date']),
            models.Index(fields=['agent_saisie']),
            models.Index(fields=['verrouille']),
        ]
    
    def __str__(self):
        return f"Inventaire {self.poste.nom} - {self.date.strftime('%d/%m/%Y')}"
    
    def get_absolute_url(self):
        return reverse('inventaire_detail', kwargs={'pk': self.pk})
    
    def peut_etre_modifie(self):
        """Vérifie si l'inventaire peut encore être modifié"""
        return not self.verrouille and not self.valide
    
    def verrouiller(self, user=None):
        """Verrouille l'inventaire"""
        if not self.verrouille:
            self.verrouille = True
            self.save()
            
            # Log de l'action
            if user:
                from common.utils import log_user_action
                log_user_action(
                    user, 
                    "Verrouillage inventaire",
                    f"Poste: {self.poste.nom}, Date: {self.date}"
                )
    
    def calculer_moyenne_horaire(self):
        """Calcule la moyenne de véhicules par heure"""
        if self.nombre_periodes_saisies > 0:
            return self.total_vehicules / self.nombre_periodes_saisies
        return 0
    
    def estimer_total_24h(self):
        """Estime le total de véhicules sur 24h basé sur la moyenne"""
        moyenne = self.calculer_moyenne_horaire()
        return moyenne * 24
    
    def calculer_recette_potentielle(self):
        """
        Calcule la recette potentielle selon la formule SUPPER
        Formule: (Total estimé 24h × 75% × 500 FCFA) / 100
        """
        from django.conf import settings
        
        config = getattr(settings, 'SUPPER_CONFIG', {})
        tarif = config.get('TARIF_VEHICULE_LEGER', 500)
        pourcentage_legers = config.get('POURCENTAGE_VEHICULES_LEGERS', 75)
        
        total_estime = self.estimer_total_24h()
        recette = (total_estime * pourcentage_legers * tarif) / 100
        
        return Decimal(str(recette))
    
    def recalculer_totaux(self):
        """Recalcule les totaux basés sur les détails de périodes"""
        details = self.details_periodes.all()
        self.total_vehicules = sum(detail.nombre_vehicules for detail in details)
        self.nombre_periodes_saisies = details.count()
        self.save(update_fields=['total_vehicules', 'nombre_periodes_saisies'])
    
    def save(self, *args, **kwargs):
        """Surcharge pour logs automatiques"""
        super().save(*args, **kwargs)
    
    def link_to_inventaire_mensuel(self):
    # """Lie cet inventaire journalier à un inventaire mensuel s'il existe"""
        from datetime import date
    
        # Chercher l'inventaire mensuel correspondant
        inventaire_mensuel = InventaireMensuel.objects.filter(
            mois=self.date.month,
            annee=self.date.year,
            actif=True
        ).first()
        
        if inventaire_mensuel:
            # Vérifier si le poste est dans l'inventaire mensuel
            return PosteInventaireMensuel.objects.filter(
                inventaire_mensuel=inventaire_mensuel,
                poste=self.poste
            ).first()
        
        return None


class DetailInventairePeriode(models.Model):
    """
    Détails de l'inventaire par période horaire
    Stocke le nombre de véhicules comptés pour chaque créneau
    """
    
    inventaire = models.ForeignKey(
        InventaireJournalier,
        on_delete=models.CASCADE,
        related_name='details_periodes',
        verbose_name=_("Inventaire")
    )
    
    periode = models.CharField(
        max_length=10,
        choices=PeriodeHoraire.choices,
        verbose_name=_("Période horaire")
    )
    
    nombre_vehicules = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(1000)],
        verbose_name=_("Nombre de véhicules"),
        help_text=_("Nombre de véhicules comptés pendant cette période")
    )
    
    # Métadonnées de saisie
    heure_saisie = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Heure de saisie")
    )
    
    modifie_le = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )
    
    observations_periode = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Observations"),
        help_text=_("Notes sur cette période (incidents, conditions particulières)")
    )
    
    class Meta:
        verbose_name = _("Détail inventaire période")
        verbose_name_plural = _("Détails inventaire par période")
        unique_together = [['inventaire', 'periode']]
        ordering = ['periode']
        indexes = [
            models.Index(fields=['inventaire', 'periode']),
        ]
    
    def __str__(self):
        return f"{self.inventaire} - {self.get_periode_display()}: {self.nombre_vehicules}"
    
    def save(self, *args, **kwargs):
        """Surcharge pour recalculer les totaux de l'inventaire"""
        super().save(*args, **kwargs)
        
        # Recalculer directement sans sauvegarder l'inventaire
        self.inventaire.recalculer_totaux()


class RecetteJournaliere(models.Model):
    """
    Modèle pour la saisie des recettes déclarées par les chefs de poste
    """
    
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='recettes',
        verbose_name=_("Poste")
    )
    
    date = models.DateField(
        verbose_name=_("Date de la recette")
    )
    
    montant_declare = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name=_("Montant déclaré (FCFA)"),
        help_text=_("Recette déclarée par le chef de poste")
    )
    
    chef_poste = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        related_name='recettes_saisies',
        verbose_name=_("Chef de poste")
    )
    
    # Liaison avec l'inventaire pour calculs
    inventaire_associe = models.OneToOneField(
        InventaireJournalier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recette',
        verbose_name=_("Inventaire associé")
    )
    
    # Calculs automatiques
    recette_potentielle = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Recette potentielle (FCFA)"),
        help_text=_("Calculée automatiquement à partir de l'inventaire")
    )
    
    ecart = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Écart (FCFA)"),
        help_text=_("Différence entre recette déclarée et potentielle")
    )
    
    taux_deperdition = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux de déperdition (%)"),
        help_text=_("Taux de déperdition calculé")
    )
    
    # État de la saisie
    verrouille = models.BooleanField(
        default=False,
        verbose_name=_("Recette verrouillée")
    )
    
    valide = models.BooleanField(
        default=False,
        verbose_name=_("Recette validée")
    )
    
    # Métadonnées
    date_saisie = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de saisie")
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )
    
    observations = models.TextField(
        blank=True,
        verbose_name=_("Observations"),
        help_text=_("Commentaires sur cette recette")
    )
    
    class Meta:
        verbose_name = _("Recette journalière")
        verbose_name_plural = _("Recettes journalières")
        unique_together = [['poste', 'date']]
        ordering = ['-date', 'poste__nom']
        indexes = [
            models.Index(fields=['poste', '-date']),
            models.Index(fields=['date']),
            models.Index(fields=['chef_poste']),
        ]
    
    def __str__(self):
        return f"Recette {self.poste.nom} - {self.date.strftime('%d/%m/%Y')}: {self.montant_declare} FCFA"
    
    def get_absolute_url(self):
        return reverse('recette_detail', kwargs={'pk': self.pk})
    
    def calculer_indicateurs(self):
        """
        Calcule tous les indicateurs basés sur l'inventaire associé
        """
        if not self.inventaire_associe:
            return
        
        # Recette potentielle
        self.recette_potentielle = self.inventaire_associe.calculer_recette_potentielle()
        
        # Écart
        self.ecart = self.montant_declare - self.recette_potentielle
        
        # Taux de déperdition
        if self.recette_potentielle > 0:
            self.taux_deperdition = (self.ecart / self.recette_potentielle) * 100
        else:
            self.taux_deperdition = Decimal('0')
        
        # Vérifier si journée impertinente
        if self.ecart >= 0:
            self._marquer_journee_impertinente()
    
    def _marquer_journee_impertinente(self):
        """Marque la journée comme impertinente si nécessaire"""
        ConfigurationJour.marquer_impertinent(
            self.date,
            self.chef_poste,
            f"Recette déclarée supérieure à la potentielle: {self.montant_declare} > {self.recette_potentielle}"
        )
        
        # Recalculer avec la valeur max des périodes
        if self.inventaire_associe:
            details = self.inventaire_associe.details_periodes.all()
            if details:
                valeur_max = max(detail.nombre_vehicules for detail in details)
                # Utiliser cette valeur pour recalculer
                total_estime_corrige = valeur_max * 24
                from django.conf import settings
                config = getattr(settings, 'SUPPER_CONFIG', {})
                tarif = config.get('TARIF_VEHICULE_LEGER', 500)
                pourcentage_legers = config.get('POURCENTAGE_VEHICULES_LEGERS', 75)
                
                self.recette_potentielle = Decimal(str((total_estime_corrige * pourcentage_legers * tarif) / 100))
                self.ecart = self.montant_declare - self.recette_potentielle
                if self.recette_potentielle > 0:
                    self.taux_deperdition = (self.ecart / self.recette_potentielle) * 100
    
    def get_couleur_alerte(self):
        """Retourne la couleur d'alerte selon le taux de déperdition"""
        if self.taux_deperdition is None:
            return 'secondary'
        
        from django.conf import settings
        config = getattr(settings, 'SUPPER_CONFIG', {})
        seuil_orange = config.get('SEUIL_ALERTE_ORANGE', -10)
        seuil_rouge = config.get('SEUIL_ALERTE_ROUGE', -30)
        
        if self.taux_deperdition > seuil_orange:
            return 'success'  # Vert
        elif self.taux_deperdition >= seuil_rouge:
            return 'warning'  # Orange
        else:
            return 'danger'   # Rouge
    
    def get_classe_css_alerte(self):
        """Retourne la classe CSS Bootstrap pour l'alerte"""
        couleur = self.get_couleur_alerte()
        return f'alert-{couleur}'
    
    def save(self, *args, **kwargs):
        """Surcharge pour calculer automatiquement les indicateurs"""
        # Calculer les indicateurs avant la sauvegarde
        self.calculer_indicateurs()
        
        super().save(*args, **kwargs)


class StatistiquesPeriodiques(models.Model):
    """
    Modèle pour stocker les statistiques calculées par période
    (hebdomadaire, mensuelle, trimestrielle, annuelle)
    """
    
    TYPE_PERIODE_CHOICES = [
        ('hebdomadaire', _('Hebdomadaire')),
        ('mensuelle', _('Mensuelle')),
        ('trimestrielle', _('Trimestrielle')),
        ('annuelle', _('Annuelle')),
    ]
    
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='statistiques',
        verbose_name=_("Poste")
    )
    
    type_periode = models.CharField(
        max_length=15,
        choices=TYPE_PERIODE_CHOICES,
        verbose_name=_("Type de période")
    )
    
    date_debut = models.DateField(
        verbose_name=_("Date de début de période")
    )
    
    date_fin = models.DateField(
        verbose_name=_("Date de fin de période")
    )
    
    # Données consolidées
    nombre_jours_actifs = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de jours avec données")
    )
    
    total_recettes_declarees = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Total recettes déclarées")
    )
    
    total_recettes_potentielles = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Total recettes potentielles")
    )
    
    taux_deperdition_moyen = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux de déperdition moyen (%)")
    )
    
    nombre_jours_impertinents = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de jours impertinents")
    )
    
    # Métadonnées
    date_calcul = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Date du calcul")
    )
    
    class Meta:
        verbose_name = _("Statistiques périodiques")
        verbose_name_plural = _("Statistiques périodiques")
        unique_together = [['poste', 'type_periode', 'date_debut']]
        ordering = ['-date_debut', 'poste__nom']
        indexes = [
            models.Index(fields=['poste', 'type_periode', '-date_debut']),
        ]
    
    def __str__(self):
        return f"Stats {self.get_type_periode_display()} {self.poste.nom} - {self.date_debut}"
    
    @classmethod
    def calculer_statistiques_periode(cls, poste, type_periode, date_debut, date_fin):
        """
        Calcule et sauvegarde les statistiques pour une période donnée
        """
        recettes = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[date_debut, date_fin]
        )
        
        if not recettes.exists():
            return None
        
        # Calculer les totaux
        total_declarees = sum(r.montant_declare for r in recettes)
        total_potentielles = sum(r.recette_potentielle or 0 for r in recettes)
        
        # Calculer le taux moyen
        taux_moyen = None
        if total_potentielles > 0:
            ecart_total = total_declarees - total_potentielles
            taux_moyen = (ecart_total / total_potentielles) * 100
        
        # Compter les jours impertinents
        jours_impertinents = ConfigurationJour.objects.filter(
            date__range=[date_debut, date_fin],
            statut=StatutJour.IMPERTINENT
        ).count()
        
        # Créer ou mettre à jour les statistiques
        stats, created = cls.objects.update_or_create(
            poste=poste,
            type_periode=type_periode,
            date_debut=date_debut,
            defaults={
                'date_fin': date_fin,
                'nombre_jours_actifs': recettes.count(),
                'total_recettes_declarees': total_declarees,
                'total_recettes_potentielles': total_potentielles,
                'taux_deperdition_moyen': taux_moyen,
                'nombre_jours_impertinents': jours_impertinents,
            }
        )
        
        return stats

class MotifInventaire(models.TextChoices):
    """Motifs pour l'inventaire d'un poste"""
    TAUX_DEPERDITION = 'taux_deperdition', _('Taux de déperdition')
    GRAND_RISQUE_STOCK = 'grand_risque', _('Grand risque de stock au 31 décembre')
    RISQUE_BAISSE_ANNUEL = 'risque_baisse', _('Risque de baisse annuel')



class PosteInventaireMensuel(models.Model):
    """
    Association entre un inventaire mensuel et un poste avec ses motifs
    """
    
    inventaire_mensuel = models.ForeignKey(
        InventaireMensuel,
        on_delete=models.CASCADE,
        related_name='postes_inventaire',
        verbose_name=_("Inventaire mensuel")
    )
    
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='inventaires_mensuels',
        verbose_name=_("Poste")
    )
    
    # Motifs multiples possibles
    motif_taux_deperdition = models.BooleanField(
        default=False,
        verbose_name=_("Taux de déperdition"),
        help_text=_("Cocher si le poste est concerné par le taux de déperdition")
    )
    
    motif_grand_risque = models.BooleanField(
        default=False,
        verbose_name=_("Grand risque de stock au 31 décembre"),
        help_text=_("Cocher si risque de stock important en fin d'année")
    )
    
    motif_risque_baisse = models.BooleanField(
        default=False,
        verbose_name=_("Risque de baisse annuel"),
        help_text=_("Cocher si risque de baisse annuelle")
    )
    
    observations = models.TextField(
        blank=True,
        verbose_name=_("Observations"),
        help_text=_("Notes spécifiques pour ce poste dans cet inventaire")
    )
    
    date_ajout = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date d'ajout")
    )
    
    class Meta:
        verbose_name = _("Poste d'inventaire mensuel")
        verbose_name_plural = _("Postes d'inventaires mensuels")
        unique_together = [['inventaire_mensuel', 'poste']]
        ordering = ['poste__region', 'poste__nom']
        indexes = [
            models.Index(fields=['inventaire_mensuel', 'poste']),
        ]
    
    def __str__(self):
        motifs = self.get_motifs_list()
        motifs_str = ', '.join(motifs) if motifs else 'Aucun motif'
        return f"{self.poste.nom} - {motifs_str}"
    
    def get_motifs_list(self):
        """Retourne la liste des motifs sélectionnés"""
        motifs = []
        if self.motif_taux_deperdition:
            motifs.append("Taux déperdition")
        if self.motif_grand_risque:
            motifs.append("Grand risque stock")
        if self.motif_risque_baisse:
            motifs.append("Risque baisse")
        return motifs
    
    def get_motifs_count(self):
        """Retourne le nombre de motifs sélectionnés"""
        count = 0
        if self.motif_taux_deperdition:
            count += 1
        if self.motif_grand_risque:
            count += 1
        if self.motif_risque_baisse:
            count += 1
        return count
    
    def get_inventaires_journaliers(self):
        """Retourne tous les inventaires journaliers de ce poste pour le mois"""
        from datetime import date
        import calendar
        
        # Obtenir le premier et dernier jour du mois
        premier_jour = date(
            self.inventaire_mensuel.annee, 
            self.inventaire_mensuel.mois, 
            1
        )
        
        dernier_jour = date(
            self.inventaire_mensuel.annee,
            self.inventaire_mensuel.mois,
            calendar.monthrange(
                self.inventaire_mensuel.annee, 
                self.inventaire_mensuel.mois
            )[1]
        )
        
        return InventaireJournalier.objects.filter(
            poste=self.poste,
            date__range=[premier_jour, dernier_jour]
        )
