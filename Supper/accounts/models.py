# ===================================================================
# accounts/models.py - Modèles pour la gestion des utilisateurs SUPPER
# ===================================================================

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from django.urls import reverse


class TypePoste(models.TextChoices):
    """Types de postes d'affectation dans le réseau routier"""
    PEAGE = 'peage', _('Poste de Péage')
    PESAGE = 'pesage', _('Poste de Pesage')


class Habilitation(models.TextChoices):
    """Rôles et habilitations dans le système SUPPER"""
    ADMIN_PRINCIPAL = 'admin_principal', _('Administrateur Principal')
    CHEF_POSTE_PEAGE = 'chef_peage', _('Chef de Poste Péage')
    CHEF_POSTE_PESAGE = 'chef_pesage', _('Chef de Poste Pesage')
    POINT_FOCAL_REGIONAL = 'focal_regional', _('Point Focal Régional')
    CAISSIER = 'caissier', _('Caissier')
    AGENT_INVENTAIRE = 'agent_inventaire', _('Agent Inventaire')
    CHEF_SERVICE = 'chef_service', _('Chef de Service')
    COORDONNATEUR_PSRR = 'coord_psrr', _('Coordonnateur PSRR')
    SERVICE_INFORMATIQUE = 'serv_info', _('Service Informatique')
    SERVICE_EMISSION = 'serv_emission', _('Service Émission et Recouvrement')
    CHEF_AFFAIRES_GENERALES = 'chef_ag', _('Chef Service Affaires Générales')
    REGISSEUR = 'regisseur', _('Régisseur')
    COMPTABLE_MATIERES = 'comptable_mat', _('Comptable Matières')
    CHEF_SERVICE_ORDRE = 'chef_ordre', _('Chef Service Ordre')
    CHEF_SERVICE_CONTROLE = 'chef_controle', _('Chef Service Contrôle')
    IMPRIMERIE_NATIONALE = 'imprimerie', _('Imprimerie Nationale')


class RegionCameroun(models.TextChoices):
    """Régions administratives du Cameroun"""
    ADAMAOUA = 'adamaoua', _('Adamaoua')
    CENTRE = 'centre', _('Centre')
    EST = 'est', _('Est')
    EXTREME_NORD = 'extreme_nord', _('Extrême-Nord')
    LITTORAL = 'littoral', _('Littoral')
    NORD = 'nord', _('Nord')
    NORD_OUEST = 'nord_ouest', _('Nord-Ouest')
    OUEST = 'ouest', _('Ouest')
    SUD = 'sud', _('Sud')
    SUD_OUEST = 'sud_ouest', _('Sud-Ouest')


class Poste(models.Model):
    """
    Modèle représentant un poste de péage ou de pesage dans le réseau routier
    """
    
    nom = models.CharField(
        max_length=100,
        verbose_name=_("Nom du poste"),
        help_text=_("Nom complet du poste (ex: Péage de Yaoundé-Nord)")
    )
    
    code = models.CharField(
        max_length=15,
        unique=True,
        verbose_name=_("Code du poste"),
        help_text=_("Code unique du poste (ex: YDE-N-01)"),
        validators=[
            RegexValidator(
                regex=r'^[A-Z0-9-]{3,15}$',
                message=_("Le code doit contenir 3-15 caractères alphanumériques et tirets")
            )
        ]
    )
    
    type_poste = models.CharField(
        max_length=10,
        choices=TypePoste.choices,
        verbose_name=_("Type de poste")
    )
    
    localisation = models.CharField(
        max_length=200,
        verbose_name=_("Localisation"),
        help_text=_("Adresse ou description précise de la localisation")
    )
    
    region = models.CharField(
        max_length=20,
        choices=RegionCameroun.choices,
        verbose_name=_("Région administrative")
    )
    
    departement = models.CharField(
        max_length=100,
        verbose_name=_("Département"),
        help_text=_("Département dans la région")
    )
    
    arrondissement = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Arrondissement"),
        help_text=_("Arrondissement (optionnel)")
    )
    
    # Coordonnées GPS (optionnelles)
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name=_("Latitude"),
        help_text=_("Coordonnée GPS latitude")
    )
    
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name=_("Longitude"),
        help_text=_("Coordonnée GPS longitude")
    )
    
    # Informations administratives
    actif = models.BooleanField(
        default=True,
        verbose_name=_("Poste actif"),
        help_text=_("Indique si le poste est en service")
    )
    
    date_ouverture = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date d'ouverture"),
        help_text=_("Date de mise en service du poste")
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création dans le système")
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )
    
    # Informations complémentaires
    observations = models.TextField(
        blank=True,
        verbose_name=_("Observations"),
        help_text=_("Notes ou observations particulières sur le poste")
    )
    
    class Meta:
        verbose_name = _("Poste")
        verbose_name_plural = _("Postes")
        ordering = ['region', 'nom']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['region', 'type_poste']),
            models.Index(fields=['actif']),
        ]
    
    def __str__(self):
        return f"{self.nom} ({self.get_type_poste_display()})"
    
    def get_absolute_url(self):
        return reverse('poste_detail', kwargs={'pk': self.pk})
    
    @property
    def localisation_complete(self):
        """Retourne la localisation complète du poste"""
        localisation = [self.localisation]
        if self.arrondissement:
            localisation.append(self.arrondissement)
        localisation.extend([self.departement, self.get_region_display()])
        return ', '.join(localisation)


class UtilisateurSUPPER(AbstractUser):
    """
    Modèle utilisateur personnalisé pour l'application SUPPER
    Étend AbstractUser avec les champs spécifiques au projet
    """
    
    # Redéfinition du champ username pour utiliser le matricule
    username = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=_("Matricule"),
        help_text=_("Matricule unique de l'agent (identifiant de connexion)"),
        validators=[
            RegexValidator(
                regex=r'^[A-Z0-9]{6,20}$',
                message=_("Le matricule doit contenir 6-20 caractères alphanumériques majuscules")
            )
        ]
    )
    
    # Informations personnelles obligatoires
    nom_complet = models.CharField(
        max_length=150,
        verbose_name=_("Nom complet"),
        help_text=_("Nom et prénom(s) complets de l'agent")
    )
    
    telephone = models.CharField(
        max_length=20,
        verbose_name=_("Numéro de téléphone"),
        validators=[
            RegexValidator(
                regex=r'^\+?237?[0-9]{8,9}$',
                message=_("Format: +237XXXXXXXXX ou XXXXXXXXX (Cameroun)")
            )
        ]
    )
    
    # Email optionnel pour réinitialisation mot de passe
    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name=_("Adresse email"),
        help_text=_("Email optionnel pour la réinitialisation de mot de passe")
    )
    
    # Affectation professionnelle
    poste_affectation = models.ForeignKey(
        Poste,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agents_affectes',
        verbose_name=_("Poste d'affectation"),
        help_text=_("Poste principal où l'agent est affecté")
    )
    
    # Rôle et habilitation dans le système
    habilitation = models.CharField(
        max_length=30,
        choices=Habilitation.choices,
        default=Habilitation.AGENT_INVENTAIRE,
        verbose_name=_("Habilitation"),
        help_text=_("Rôle de l'utilisateur dans le système SUPPER")
    )
    
    # Permissions d'accès aux données
    peut_saisir_peage = models.BooleanField(
        default=False,
        verbose_name=_("Peut saisir données péage"),
        help_text=_("Autorisation de créer/modifier les données de péage")
    )
    
    peut_saisir_pesage = models.BooleanField(
        default=False,
        verbose_name=_("Peut saisir données pesage"),
        help_text=_("Autorisation de créer/modifier les données de pesage")
    )
    
    acces_tous_postes = models.BooleanField(
        default=False,
        verbose_name=_("Accès à tous les postes"),
        help_text=_("Si False, accès limité au poste d'affectation uniquement")
    )
    
    # Permissions sur les modules fonctionnels
    peut_gerer_peage = models.BooleanField(
        default=False, 
        verbose_name=_("Gérer le péage")
    )
    peut_gerer_pesage = models.BooleanField(
        default=False, 
        verbose_name=_("Gérer le pesage")
    )
    peut_gerer_personnel = models.BooleanField(
        default=False, 
        verbose_name=_("Gérer le personnel")
    )
    peut_gerer_budget = models.BooleanField(
        default=False, 
        verbose_name=_("Gérer le budget")
    )
    peut_gerer_inventaire = models.BooleanField(
        default=True, 
        verbose_name=_("Gérer l'inventaire")
    )
    peut_gerer_archives = models.BooleanField(
        default=False, 
        verbose_name=_("Gérer les archives")
    )
    peut_gerer_stocks_psrr = models.BooleanField(
        default=False, 
        verbose_name=_("Gérer les stocks PSRR")
    )
    peut_gerer_stock_info = models.BooleanField(
        default=False, 
        verbose_name=_("Gérer le stock informatique")
    )
    
    # Informations de suivi
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création du compte")
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )
    
    cree_par = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comptes_crees',
        verbose_name=_("Créé par"),
        help_text=_("Administrateur qui a créé ce compte")
    )
    
    # Informations supplémentaires
    photo_profil = models.ImageField(
        upload_to='photos_profil/',
        null=True,
        blank=True,
        verbose_name=_("Photo de profil"),
        help_text=_("Photo optionnelle pour le profil utilisateur")
    )
    
    commentaires = models.TextField(
        blank=True,
        verbose_name=_("Commentaires"),
        help_text=_("Notes ou commentaires sur cet utilisateur")
    )
    
    class Meta:
        verbose_name = _("Utilisateur SUPPER")
        verbose_name_plural = _("Utilisateurs SUPPER")
        ordering = ['nom_complet']
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['habilitation']),
            models.Index(fields=['poste_affectation']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.nom_complet} ({self.username})"
    
    def get_absolute_url(self):
        return reverse('user_detail', kwargs={'pk': self.pk})
    
    def get_permissions_list(self):
        """Retourne la liste des permissions accordées à l'utilisateur"""
        permissions = []
        if self.peut_saisir_peage:
            permissions.append(_("Saisie péage"))
        if self.peut_saisir_pesage:
            permissions.append(_("Saisie pesage"))
        if self.peut_gerer_personnel:
            permissions.append(_("Gestion personnel"))
        if self.peut_gerer_inventaire:
            permissions.append(_("Gestion inventaire"))
        if self.peut_gerer_budget:
            permissions.append(_("Gestion budget"))
        if self.peut_gerer_archives:
            permissions.append(_("Gestion archives"))
        if self.peut_gerer_stocks_psrr:
            permissions.append(_("Gestion stocks PSRR"))
        if self.peut_gerer_stock_info:
            permissions.append(_("Gestion stock informatique"))
        return permissions
    
    def is_admin(self):
        """Vérifie si l'utilisateur a des privilèges administrateur"""
        return self.habilitation in [
            Habilitation.ADMIN_PRINCIPAL,
            Habilitation.COORDONNATEUR_PSRR,
            Habilitation.SERVICE_INFORMATIQUE,
            Habilitation.SERVICE_EMISSION
        ]
    
    def is_chef_poste(self):
        """Vérifie si l'utilisateur est chef de poste"""
        return self.habilitation in [
            Habilitation.CHEF_POSTE_PEAGE,
            Habilitation.CHEF_POSTE_PESAGE
        ]
    
    def peut_acceder_poste(self, poste):
        """
        Vérifie si l'utilisateur peut accéder aux données d'un poste donné
        """
        if self.acces_tous_postes or self.is_admin():
            return True
        return self.poste_affectation == poste
    
    def get_postes_accessibles(self):
        """
        Retourne la liste des postes auxquels l'utilisateur a accès
        """
        if self.acces_tous_postes or self.is_admin():
            return Poste.objects.filter(actif=True)
        elif self.poste_affectation:
            return Poste.objects.filter(id=self.poste_affectation.id)
        else:
            return Poste.objects.none()
    
    def save(self, *args, **kwargs):
        """
        Surcharge de la méthode save pour des validations et configurations automatiques
        """
        # Conversion du matricule en majuscules
        self.username = self.username.upper()
        
        # Attribution automatique de permissions selon l'habilitation
        self._configure_permissions_by_role()
        
        super().save(*args, **kwargs)
    
    def _configure_permissions_by_role(self):
        """
        Configure automatiquement les permissions selon le rôle
        """
        # Réinitialiser toutes les permissions
        permission_fields = [
            'peut_saisir_peage', 'peut_saisir_pesage', 'peut_gerer_peage',
            'peut_gerer_pesage', 'peut_gerer_personnel', 'peut_gerer_budget',
            'peut_gerer_inventaire', 'peut_gerer_archives', 'peut_gerer_stocks_psrr',
            'peut_gerer_stock_info'
        ]
        
        # Configuration selon le rôle
        if self.habilitation == Habilitation.ADMIN_PRINCIPAL:
            # Administrateur principal : tous les droits
            self.is_staff = True
            self.is_superuser = True
            self.acces_tous_postes = True
            for field in permission_fields:
                setattr(self, field, True)
        
        elif self.habilitation == Habilitation.COORDONNATEUR_PSRR:
            # Coordonnateur PSRR : droits étendus
            self.is_staff = True
            self.acces_tous_postes = True
            self.peut_gerer_personnel = True
            self.peut_gerer_peage = True
            self.peut_gerer_pesage = True
            self.peut_gerer_inventaire = True
            self.peut_gerer_stocks_psrr = True
            self.peut_saisir_peage = True
            self.peut_saisir_pesage = True
        
        elif self.habilitation == Habilitation.SERVICE_INFORMATIQUE:
            # Service informatique : maintenance et suivi
            self.is_staff = True
            self.acces_tous_postes = True
            self.peut_gerer_stock_info = True
            self.peut_gerer_inventaire = True
            for field in permission_fields:
                setattr(self, field, True)
        
        elif self.habilitation == Habilitation.SERVICE_EMISSION:
            # Service émission et recouvrement
            self.acces_tous_postes = True
            self.peut_gerer_peage = True
            self.peut_gerer_stocks_psrr = True
            self.peut_saisir_peage = True
        
        elif self.habilitation == Habilitation.CHEF_POSTE_PEAGE:
            # Chef de poste péage
            self.peut_gerer_peage = True
            self.peut_saisir_peage = True
            self.peut_gerer_inventaire = True
        
        elif self.habilitation == Habilitation.CHEF_POSTE_PESAGE:
            # Chef de poste pesage
            self.peut_gerer_pesage = True
            self.peut_saisir_pesage = True
            self.peut_gerer_inventaire = True
        
        elif self.habilitation == Habilitation.AGENT_INVENTAIRE:
            # Agent inventaire : droits limités à l'inventaire
            self.peut_gerer_inventaire = True
            # Autres permissions restent False
        
        elif self.habilitation == Habilitation.CHEF_AFFAIRES_GENERALES:
            # Chef affaires générales : gestion personnel
            self.peut_gerer_personnel = True
            self.acces_tous_postes = True
        
        elif self.habilitation == Habilitation.REGISSEUR:
            # Régisseur : gestion budget
            self.peut_gerer_budget = True
            self.acces_tous_postes = True
        
        elif self.habilitation == Habilitation.COMPTABLE_MATIERES:
            # Comptable matières : archives
            self.peut_gerer_archives = True
            self.acces_tous_postes = True
        
        elif self.habilitation in [
            Habilitation.CHEF_SERVICE_ORDRE,
            Habilitation.CHEF_SERVICE_CONTROLE
        ]:
            # Chefs de service : archives et validation
            self.peut_gerer_archives = True
            self.acces_tous_postes = True
        
        elif self.habilitation == Habilitation.IMPRIMERIE_NATIONALE:
            # Imprimerie nationale : gestion stocks
            self.peut_gerer_stocks_psrr = True
        
        # Les autres rôles gardent leurs permissions par défaut


class JournalAudit(models.Model):
    """
    Modèle pour la journalisation complète des actions utilisateur
    Trace toutes les actions importantes dans le système SUPPER
    """
    
    utilisateur = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.CASCADE,
        related_name='actions_journal',
        verbose_name=_("Utilisateur")
    )
    
    action = models.CharField(
        max_length=100,
        verbose_name=_("Action effectuée"),
        help_text=_("Description courte de l'action")
    )
    
    details = models.TextField(
        blank=True,
        verbose_name=_("Détails"),
        help_text=_("Description détaillée de l'action et données associées")
    )
    
    # Informations techniques
    adresse_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("Adresse IP")
    )
    
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("User Agent"),
        help_text=_("Informations sur le navigateur utilisé")
    )
    
    session_key = models.CharField(
        max_length=40,
        blank=True,
        verbose_name=_("Clé de session")
    )
    
    # Informations contextuelles
    url_acces = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("URL d'accès"),
        help_text=_("URL de la page où l'action a été effectuée")
    )
    
    methode_http = models.CharField(
        max_length=10,
        blank=True,
        verbose_name=_("Méthode HTTP"),
        help_text=_("GET, POST, PUT, DELETE, etc.")
    )
    
    # Timing
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date et heure")
    )
    
    duree_execution = models.DurationField(
        null=True,
        blank=True,
        verbose_name=_("Durée d'exécution"),
        help_text=_("Temps d'exécution de l'action")
    )
    
    # Statut de l'action
    statut_reponse = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Code de statut HTTP"),
        help_text=_("200, 404, 500, etc.")
    )
    
    succes = models.BooleanField(
        default=True,
        verbose_name=_("Action réussie"),
        help_text=_("Indique si l'action s'est déroulée avec succès")
    )
    
    class Meta:
        verbose_name = _("Entrée journal d'audit")
        verbose_name_plural = _("Journal d'audit")
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['utilisateur', '-timestamp']),
            models.Index(fields=['action']),
            models.Index(fields=['-timestamp']),
            models.Index(fields=['succes']),
        ]
    
    def __str__(self):
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.utilisateur.username} - {self.action}"
    
    def get_absolute_url(self):
        return reverse('journal_detail', kwargs={'pk': self.pk})
    
    @property
    def duree_formatee(self):
        """Retourne la durée d'exécution formatée"""
        if self.duree_execution:
            total_seconds = self.duree_execution.total_seconds()
            if total_seconds < 1:
                return f"{total_seconds*1000:.0f} ms"
            else:
                return f"{total_seconds:.2f} s"
        return "N/A"
    
    @classmethod
    def nettoyer_anciens_logs(cls, jours_retention=180):
        """
        Supprime les logs plus anciens que le nombre de jours spécifié
        """
        from django.utils import timezone
        from datetime import timedelta
        
        date_limite = timezone.now() - timedelta(days=jours_retention)
        logs_supprimes = cls.objects.filter(timestamp__lt=date_limite).delete()
        
        return logs_supprimes[0]  # Nombre d'objets supprimés


class NotificationUtilisateur(models.Model):
    """
    Modèle pour le système de notifications internes
    """
    
    destinataire = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.CASCADE,
        related_name='notifications_recues',
        verbose_name=_("Destinataire")
    )
    
    expediteur = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications_envoyees',
        verbose_name=_("Expéditeur")
    )
    
    titre = models.CharField(
        max_length=200,
        verbose_name=_("Titre de la notification")
    )
    
    message = models.TextField(
        verbose_name=_("Message")
    )
    
    type_notification = models.CharField(
        max_length=20,
        choices=[
            ('info', _('Information')),
            ('warning', _('Avertissement')),
            ('error', _('Erreur')),
            ('success', _('Succès')),
            ('system', _('Système')),
        ],
        default='info',
        verbose_name=_("Type de notification")
    )
    
    lue = models.BooleanField(
        default=False,
        verbose_name=_("Notification lue")
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    date_lecture = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Date de lecture")
    )
    
    class Meta:
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['destinataire', '-date_creation']),
            models.Index(fields=['lue']),
        ]
    
    def __str__(self):
        return f"{self.titre} - {self.destinataire.username}"
    
    def marquer_comme_lue(self):
        """Marque la notification comme lue"""
        if not self.lue:
            from django.utils import timezone
            self.lue = True
            self.date_lecture = timezone.now()
            self.save(update_fields=['lue', 'date_lecture'])