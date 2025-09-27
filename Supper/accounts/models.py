# ===================================================================
# Fichier : Supper/accounts/models.py
# Modèles pour la gestion des utilisateurs SUPPER - VERSION COMPLÈTE
# Inclut toutes les corrections selon les clarifications
# ===================================================================

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from django.urls import reverse
from django.utils import timezone
import logging
from decimal import Decimal

# Configuration du logger pour l'application
logger = logging.getLogger('supper')


# ===================================================================
# CHOIX ET CONSTANTES
# ===================================================================

class TypePoste(models.TextChoices):
    """Types de postes d'affectation dans le réseau routier"""
    PEAGE = 'peage', _('Poste de Péage')
    PESAGE = 'pesage', _('Poste de Pesage')

class Region(models.Model):
    nom = models.CharField(max_length=50, unique=True, verbose_name=_("Région"))

    class Meta:
        verbose_name = _("Région")
        verbose_name_plural = _("Régions")
        ordering = ['nom']

    def __str__(self):
        return self.nom

class Departement(models.Model):
    region = models.ForeignKey(
        Region, on_delete=models.CASCADE, related_name='departements', verbose_name=_("Région")
    )
    nom = models.CharField(max_length=50, verbose_name=_("Département"))

    class Meta:
        verbose_name = _("Département")
        verbose_name_plural = _("Départements")
        unique_together = ('region', 'nom')
        ordering = ['region__nom', 'nom']

    def __str__(self):
        return f"{self.nom} ({self.region.nom})"
    
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


class TypeNotification(models.TextChoices):
    """Types de notifications dans le système"""
    INFO = 'info', _('Information')
    SUCCES = 'succes', _('Succès')
    AVERTISSEMENT = 'avertissement', _('Avertissement')
    ERREUR = 'erreur', _('Erreur')


# ===================================================================
# MODÈLE POSTE
# ===================================================================

class Poste(models.Model):
    """
    Modèle représentant un poste de péage ou de pesage
    67 postes de péage + ~40 postes de pesage au Cameroun
    """
    
    # Identification unique du poste
    code = models.CharField(
        max_length=10,
        unique=True,
        verbose_name=_("Code du poste"),
        help_text=_("Code unique d'identification (ex: PG001, PS001)")
    )
    
    nom = models.CharField(
        max_length=100,
        verbose_name=_("Nom du poste"),
        help_text=_("Nom complet du poste (ex: Péage de Douala-Nord)")
    )
    
    type = models.CharField(
        max_length=10,
        choices=TypePoste.choices,
        default=TypePoste.PEAGE,
        verbose_name=_("Type de poste")
    )
    
    # Localisation géographique
    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        verbose_name=_("Région")
    )
    
    departement = models.ForeignKey(
        Departement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name=_("Département")
    )
    # CHANGEMENT : arrondissement → axe_routier
    axe_routier = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Axe routier"),
        help_text=_("Axe routier où se situe le poste (ex: Yaoundé-Douala, Douala-Bafoussam)")
    )
    
    # Coordonnées GPS optionnelles
    latitude = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Latitude"),
        help_text=_("Coordonnée GPS latitude")
    )
    
    longitude = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Longitude"),
        help_text=_("Coordonnée GPS longitude")
    )
    
    # Informations complémentaires
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Description détaillée du poste et de sa situation")
    )
    
    # Statut
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Actif"),
        help_text=_("Le poste est-il en service ?")
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    date_modification = models.DateTimeField(
        auto_now=True,  # CORRIGÉ : auto_now au lieu de auto_now_add
        verbose_name=_("Date de modification")
    )
    objectif_annuel = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Objectif annuel (FCFA)"),
        help_text=_("Objectif de recettes annuelles pour ce poste")
    )
    
    class Meta:
        verbose_name = _("Poste")
        verbose_name_plural = _("Postes")
        ordering = ['region', 'nom']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['region', 'type']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        """Affichage optimisé pour éviter la coupure dans les listes déroulantes"""
        # Format court pour les listes : Code - Nom (Type)
        return f"{self.code} - {self.nom[:30]}{'...' if len(self.nom) > 30 else ''} ({self.get_type_display()})"

    def get_nom_complet(self):
        """Retourne le nom complet du poste pour l'affichage détaillé"""
        return f"{self.nom} ({self.get_type_display()}) - {self.region}"
    
    def get_realisation_annee(self, annee=None):
        """Calcule le total réalisé pour une année donnée"""
        from inventaire.models import RecetteJournaliere
        from django.db.models import Sum
        
        if annee is None:
            annee = timezone.now().year
            
        total = RecetteJournaliere.objects.filter(
            poste=self,
            date__year=annee
        ).aggregate(total=Sum('montant_declare'))['total']
        
        return Decimal(str(total or 0))
    
    def get_taux_realisation(self, annee=None):
        """Calcule le taux de réalisation par rapport à l'objectif"""
        if not self.objectif_annuel:
            return None
        realise = self.get_realisation_annee(annee)
        if self.objectif_annuel > 0:
            return (realise / self.objectif_annuel * 100)
        return 0
    
    def get_nom_court(self):
        """Nom court pour l'administration"""
        return f"{self.code} - {self.nom[:25]}{'...' if len(self.nom) > 25 else ''}"
    get_nom_court.short_description = "Poste"
    
    def get_absolute_url(self):
        return reverse('accounts:poste_detail', kwargs={'pk': self.pk})
    
    @property
    def nom_complet(self):
        """Retourne le nom complet avec type et région"""
        return f"{self.get_type_display()} {self.nom} ({self.region})"
    
    @property
    def coordonnees_gps(self):
        """Retourne les coordonnées GPS formatées"""
        if self.latitude and self.longitude:
            return f"{self.latitude:.6f}, {self.longitude:.6f}"
        return None


# ===================================================================
# MODÈLE UTILISATEUR SUPPER - VERSION COMPLÈTE
# ===================================================================

class UtilisateurSupperManager(BaseUserManager):
    """Manager personnalisé pour UtilisateurSUPPER"""
    
    def create_user(self, username, password=None, **extra_fields):
        """Créer un utilisateur normal"""
        if not username:
            raise ValueError('Le matricule est obligatoire')
        
        # Nettoyer le username (matricule)
        username = username.upper().strip()
        
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, username, password=None, **extra_fields):
        """Créer un superutilisateur"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        
        # Valeurs par défaut pour les champs obligatoires
        extra_fields.setdefault('nom_complet', f'Admin {username}')
        extra_fields.setdefault('telephone', '+237600000000')
        extra_fields.setdefault('habilitation', 'admin_principal')
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(username, password, **extra_fields)
class UtilisateurSUPPER(AbstractUser):
    """
    Utilisateur personnalisé pour le système SUPPER
    Étend AbstractUser avec champs spécifiques métier
    """
    
    # Redéfinir les champs de base
    objects = UtilisateurSupperManager()
    username = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=_("Matricule"),
        help_text=_("Matricule unique de l'agent (ex: 1052105M)")
        #     RegexValidator(
        #         regex=r'^[A-Z]{2,4}[0-9]{3,4}$',
        #         message=_("Format: 2-4 lettres + 3-4 chiffres (ex: INV001)")
        #     )
        # ]
    )
    
    first_name = None  # Supprimer first_name
    last_name = None   # Supprimer last_name
    
    # Informations personnelles
    nom_complet = models.CharField(
        max_length=100,
        verbose_name=_("Nom complet"),
        help_text=_("Nom et prénom(s) de l'agent")
    )
    
    telephone = models.CharField(
        max_length=15,
        verbose_name=_("Numéro de téléphone"),
        help_text=_("Numéro de téléphone camerounais"),
        validators=[
            RegexValidator(
                regex=r'^(\+237)?[0-9]{8,9}$',
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
    
    # ===============================================================
    # PERMISSIONS D'ACCÈS AUX DONNÉES
    # ===============================================================
    
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
    
    # ===============================================================
    # NOUVEAUX CHAMPS - CONTRÔLE D'AFFICHAGE PRÉCIS
    # ===============================================================
    
    voir_recettes_potentielles = models.BooleanField(
        default=True,
        verbose_name=_("Peut voir recettes potentielles"),
        help_text=_("Autorisation de voir les calculs de recettes potentielles")
    )
    
    voir_taux_deperdition = models.BooleanField(
        default=True,
        verbose_name=_("Peut voir taux déperdition"),
        help_text=_("Autorisation de voir les calculs de taux de déperdition")
    )
    
    voir_statistiques_globales = models.BooleanField(
        default=False,
        verbose_name=_("Peut voir statistiques globales"),
        help_text=_("Autorisation de voir stats tous postes (admin/service émission)")
    )
    
    peut_saisir_pour_autres_postes = models.BooleanField(
        default=False,
        verbose_name=_("Peut saisir pour autres postes"),
        help_text=_("Admin peut saisir inventaires/recettes sur tous postes")
    )
    
    # ===============================================================
    # PERMISSIONS SUR LES MODULES FONCTIONNELS
    # ===============================================================
    
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
        default=False, 
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
    
    # ===============================================================
    # MÉTADONNÉES ET TRAÇABILITÉ
    # ===============================================================
    
    cree_par = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='utilisateurs_crees',
        verbose_name=_("Créé par"),
        help_text=_("Administrateur qui a créé ce compte")
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Date de modification")
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
        return f"{self.username} - {self.nom_complet}"
    
    def save(self, *args, **kwargs):
        """Sauvegarde avec attribution automatique des permissions"""
        # Attribuer automatiquement les permissions selon l'habilitation
        self.attribuer_permissions_automatiques()
        
        # Sauvegarder l'objet
        super().save(*args, **kwargs)
        
        # Logger la création/modification
        if hasattr(self, '_state') and self._state.adding:
            logger.info(f"Nouvel utilisateur créé: {self.username} ({self.nom_complet})")
        else:
            logger.info(f"Utilisateur modifié: {self.username}")
    @property
    def is_admin(self):
        # Tu adaptes la logique de _check_admin_permission
        return (
            self.is_superuser or
            self.is_staff or
            self.habilitation in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission']
        )
    @property
    def is_chef_poste(self):
        return self.habilitation in ['chef_peage', 'chef_pesage']
    
    def get_absolute_url(self):
        return reverse('accounts:user_detail', kwargs={'pk': self.pk})
    
    # ===============================================================
    # MÉTHODES POUR ATTRIBUTION AUTOMATIQUE DES PERMISSIONS
    # ===============================================================
    
    def attribuer_permissions_automatiques(self):
        """
        Attribue automatiquement les permissions selon l'habilitation
        MISE À JOUR selon les nouvelles spécifications :
        - Agent inventaire : accès très restreint, pas de recettes potentielles
        - Chef péage : taux déperdition seulement (pas recettes potentielles)
        - Admin : accès complet à tout
        """
        # Réinitialiser toutes les permissions
        permission_fields = [
            'peut_gerer_peage', 'peut_gerer_pesage', 'peut_gerer_personnel',
            'peut_gerer_budget', 'peut_gerer_inventaire', 'peut_gerer_archives',
            'peut_gerer_stocks_psrr', 'peut_gerer_stock_info'
        ]
        
        for field in permission_fields:
            setattr(self, field, False)
        
        # Attribution selon le rôle avec nouvelles restrictions
        if self.habilitation == Habilitation.ADMIN_PRINCIPAL:
            # Admin principal : ACCÈS COMPLET À TOUT
            self.is_staff = True
            self.is_superuser = True
            self.acces_tous_postes = True
            self.peut_saisir_peage = True
            self.peut_saisir_pesage = True
            # PEUT TOUT VOIR
            self.voir_recettes_potentielles = True
            self.voir_taux_deperdition = True
            self.voir_statistiques_globales = True
            self.peut_saisir_pour_autres_postes = True
            # Tous les modules
            for field in permission_fields:
                setattr(self, field, True)
        
        elif self.habilitation == Habilitation.COORDONNATEUR_PSRR:
            # Coordonnateur : accès global mais pas superuser
            self.acces_tous_postes = True
            self.is_staff = True
            self.peut_saisir_peage = True
            self.peut_saisir_pesage = True
            # PEUT TOUT VOIR
            self.voir_recettes_potentielles = True
            self.voir_taux_deperdition = True
            self.voir_statistiques_globales = True
            self.peut_saisir_pour_autres_postes = True
            # Tous les modules
            for field in permission_fields:
                setattr(self, field, True)
        
        elif self.habilitation == Habilitation.SERVICE_INFORMATIQUE:
            # Service informatique : maintenance et suivi complet
            self.is_staff = True
            self.is_staff = True
            self.acces_tous_postes = True
            self.peut_saisir_peage = True
            self.peut_saisir_pesage = True
            # PEUT TOUT VOIR
            self.voir_recettes_potentielles = True
            self.voir_taux_deperdition = True
            self.voir_statistiques_globales = True
            self.peut_saisir_pour_autres_postes = True
            # Tous les modules
            for field in permission_fields:
                setattr(self, field, True)
        
        elif self.habilitation == Habilitation.SERVICE_EMISSION:
            # Service émission : PEUT VOIR les recettes potentielles + graphiques
            self.acces_tous_postes = True
            self.is_staff = True
            self.peut_gerer_peage = True
            self.peut_gerer_stocks_psrr = True
            self.peut_saisir_peage = True
            # PEUT VOIR recettes potentielles (spécifié dans clarifications)
            self.voir_recettes_potentielles = True
            self.voir_taux_deperdition = True
            self.voir_statistiques_globales = True
        
        elif self.habilitation == Habilitation.CHEF_POSTE_PEAGE:
            # Chef péage : SEULEMENT taux déperdition (PAS recettes potentielles)
            self.peut_gerer_peage = True
            self.peut_saisir_peage = True
            self.peut_gerer_inventaire = False
            # RESTRICTIONS IMPORTANTES
            self.voir_recettes_potentielles = False  # PAS les recettes potentielles
            self.voir_taux_deperdition = True        # SEULEMENT le taux
            self.voir_statistiques_globales = False
            self.acces_tous_postes = False           # Son poste seulement
        
        elif self.habilitation == Habilitation.CHEF_POSTE_PESAGE:
            # Chef pesage : similaire chef péage
            self.peut_gerer_pesage = True
            self.peut_saisir_pesage = True
            self.peut_gerer_inventaire = True
            # RESTRICTIONS IMPORTANTES
            self.voir_recettes_potentielles = False  # PAS les recettes potentielles
            self.voir_taux_deperdition = True        # SEULEMENT le taux
            self.voir_statistiques_globales = False
            self.acces_tous_postes = False           # Son poste seulement
        
        elif self.habilitation == Habilitation.AGENT_INVENTAIRE:
            # Agent inventaire : DROITS TRÈS LIMITÉS
            self.peut_gerer_inventaire = True
            # RESTRICTIONS MAXIMALES
            self.voir_recettes_potentielles = False  # NE VOIT PAS les recettes potentielles
            self.voir_taux_deperdition = False       # NE VOIT PAS les taux de déperdition
            self.voir_statistiques_globales = False
            self.acces_tous_postes = False           # Son poste seulement
            self.peut_saisir_peage = False
            self.peut_saisir_pesage = False
        
        elif self.habilitation == Habilitation.CHEF_AFFAIRES_GENERALES:
            # Chef affaires générales : gestion personnel
            self.peut_gerer_personnel = True
            self.acces_tous_postes = True
            self.voir_statistiques_globales = True
        
        elif self.habilitation == Habilitation.REGISSEUR:
            # Régisseur : gestion budget
            self.peut_gerer_budget = True
            self.acces_tous_postes = True
            self.voir_statistiques_globales = True
        
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
    
    def peut_voir_poste(self, poste):
        """Vérifie si l'utilisateur peut voir les données d'un poste"""
        if self.acces_tous_postes:
            return True
        return self.poste_affectation == poste
    
    def peut_modifier_poste(self, poste):
        """Vérifie si l'utilisateur peut modifier les données d'un poste"""
        if self.peut_saisir_pour_autres_postes:
            return True
        return self.peut_voir_poste(poste)
    def get_postes_accessibles(self):
        """Retourne la liste des postes auxquels l'utilisateur a accès"""
        if self.acces_tous_postes or self.is_admin:
            return Poste.objects.filter(is_active=True)
        elif self.poste_affectation:
            return Poste.objects.filter(id=self.poste_affectation.id)
        else:
            return Poste.objects.none()

    def peut_acceder_poste(self, poste):
        """Vérifie si l'utilisateur peut accéder aux données d'un poste"""
        if self.acces_tous_postes or self.is_admin:
            return True
        return self.poste_affectation == poste
    
    @property
    def nom_role(self):
        """Retourne le nom du rôle en français"""
        return self.get_habilitation_display()
    
    @property
    def niveau_acces(self):
        """Retourne le niveau d'accès de l'utilisateur"""
        if self.habilitation in ['admin_principal', 'coord_psrr', 'serv_info'] or self.is_superuser:
            return 'COMPLET'
        elif self.habilitation in ['chef_peage', 'chef_pesage']:
            return 'RESTREINT'
        elif self.habilitation == 'agent_inventaire':
            return 'LIMITÉ'
        else:
            return 'STANDARD'


# ===================================================================
# MODÈLE JOURNAL AUDIT
# ===================================================================

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
        verbose_name=_("Succès"),
        help_text=_("L'action s'est-elle déroulée avec succès ?")
    )
    
    class Meta:
        verbose_name = _("Journal d'audit")
        verbose_name_plural = _("Journal d'audit")
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['utilisateur', 'timestamp']),
            models.Index(fields=['action']),
            models.Index(fields=['succes']),
            models.Index(fields=['-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.timestamp} - {self.utilisateur.username} - {self.action}"
    
   # Ajout à la classe JournalAudit dans accounts/models.py
# Remplacer la méthode duree_formatee existante

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

def __str__(self):
    """Représentation string sécurisée"""
    try:
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.utilisateur.username} - {self.action}"
    except (AttributeError, ValueError):
        return f"Journal #{self.pk} - {self.action}"

def get_details_safe(self):
    """Retourne les détails de manière sécurisée pour l'affichage"""
    if not self.details:
        return "Aucun détail"
    
    # Limiter la taille pour l'affichage en liste
    if len(self.details) > 100:
        return self.details[:97] + "..."
    return self.details

def get_ip_display(self):
    """Affichage sécurisé de l'IP"""
    return self.adresse_ip or "Non disponible"

def get_user_agent_short(self):
    """Version courte du user agent"""
    if not self.user_agent:
        return "Non disponible"
    
    # Extraire les informations principales du user agent
    if 'Chrome' in self.user_agent:
        return "Chrome"
    elif 'Firefox' in self.user_agent:
        return "Firefox"
    elif 'Safari' in self.user_agent:
        return "Safari"
    elif 'Edge' in self.user_agent:
        return "Edge"
    else:
        return "Autre navigateur"

# ===================================================================
# MODÈLE NOTIFICATIONS UTILISATEUR
# ===================================================================

class NotificationUtilisateur(models.Model):
    """
    Système de notifications internes pour les utilisateurs SUPPER
    """
    
    destinataire = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.CASCADE,
        related_name='notifications_recues',
        verbose_name=_("Destinataire")
    )
    
    cree_par = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications_creees',
        verbose_name=_("Créé par")
    )
    
    titre = models.CharField(
        max_length=200,
        verbose_name=_("Titre"),
        help_text=_("Titre court de la notification")
    )
    
    message = models.TextField(
        verbose_name=_("Message"),
        help_text=_("Contenu détaillé de la notification")
    )
    
    type_notification = models.CharField(
        max_length=20,
        choices=TypeNotification.choices,
        default=TypeNotification.INFO,
        verbose_name=_("Type de notification")
    )
    
    # Statut de lecture
    lu = models.BooleanField(
        default=False,
        verbose_name=_("Lu"),
        help_text=_("La notification a-t-elle été lue ?")
    )
    
    date_lecture = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Date de lecture")
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    class Meta:
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['destinataire', 'lu']),
            models.Index(fields=['type_notification']),
            models.Index(fields=['-date_creation']),
        ]
    
    def __str__(self):
        statut = "✓" if self.lu else "●"
        return f"{statut} {self.titre} → {self.destinataire.nom_complet}"
    
    def marquer_comme_lue(self):
        """Marque la notification comme lue"""
        if not self.lu:
            self.lu = True
            self.date_lecture = timezone.now()
            self.save(update_fields=['lu', 'date_lecture'])
    
    @property
    def age_formatee(self):
        """Retourne l'âge de la notification formatée"""
        delta = timezone.now() - self.date_creation
        
        if delta.days > 0:
            return f"il y a {delta.days} jour(s)"
        elif delta.seconds > 3600:
            heures = delta.seconds // 3600
            return f"il y a {heures}h"
        elif delta.seconds > 60:
            minutes = delta.seconds // 60
            return f"il y a {minutes} minute(s)"