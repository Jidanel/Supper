# ===================================================================
# Fichier : Supper/accounts/models.py
# Modèles pour la gestion des utilisateurs SUPPER - VERSION FINALE
# Fusion : Structure existante + Nouvelles habilitations selon matrice PDF
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


class TypeNotification(models.TextChoices):
    """Types de notifications dans le système"""
    INFO = 'info', _('Information')
    SUCCES = 'succes', _('Succès')
    AVERTISSEMENT = 'avertissement', _('Avertissement')
    ERREUR = 'erreur', _('Erreur')


class Habilitation(models.TextChoices):
    """
    Rôles et habilitations dans le système SUPPER
    MISE À JOUR selon la matrice PDF des habilitations
    """
    # Rôles administratifs centraux
    ADMIN_PRINCIPAL = 'admin_principal', _('Administrateur Principal')
    COORDONNATEUR_PSRR = 'coord_psrr', _('Coordonnateur PSRR')
    SERVICE_INFORMATIQUE = 'serv_info', _('Service Informatique')
    SERVICE_EMISSION = 'serv_emission', _('Service Émissions et Recouvrement')
    
    # Services support
    CHEF_AFFAIRES_GENERALES = 'chef_ag', _('Service des Affaires Générales')
    SERVICE_CONTROLE_VALIDATION = 'serv_controle', _('Service Contrôle et Validation')
    SERVICE_ORDRE_SECRETARIAT = 'serv_ordre', _('Service Ordre/Secrétariat')
    IMPRIMERIE_NATIONALE = 'imprimerie', _('Imprimerie Nationale')
    
    # CISOP (Cellules d'Intervention et de Suivi des Opérations) - NOUVEAUX
    CISOP_PEAGE = 'cisop_peage', _('CISOP Péage')
    CISOP_PESAGE = 'cisop_pesage', _('CISOP Pesage')
    
    # Rôles terrain péage
    CHEF_POSTE_PEAGE = 'chef_peage', _('Chef de Poste Péage')
    AGENT_INVENTAIRE = 'agent_inventaire', _('Agent Inventaire')
    
    # Rôles terrain pesage
    CHEF_STATION_PESAGE = 'chef_station_pesage', _('Chef de Station Pesage')
    REGISSEUR_PESAGE = 'regisseur_pesage', _('Régisseur de Station Pesage')
    CHEF_EQUIPE_PESAGE = 'chef_equipe_pesage', _("Chef d'Équipe Pesage")
    
    # Rôles supplémentaires (conservés pour compatibilité)
    POINT_FOCAL_REGIONAL = 'focal_regional', _('Point Focal Régional')
    CHEF_SERVICE = 'chef_service', _('Chef de Service')
    REGISSEUR = 'regisseur', _('Régisseur Central')
    COMPTABLE_MATIERES = 'comptable_mat', _('Comptable Matières')
    
    # Anciens noms conservés pour compatibilité (alias)
    CHEF_SERVICE_ORDRE = 'chef_ordre', _('Chef Service Ordre')
    CHEF_SERVICE_CONTROLE = 'chef_controle', _('Chef Service Contrôle')


# ===================================================================
# MODÈLE REGION
# ===================================================================

class Region(models.Model):
    """Région administrative du Cameroun"""
    nom = models.CharField(
        max_length=50, 
        unique=True, 
        verbose_name=_("Région")
    )

    class Meta:
        verbose_name = _("Région")
        verbose_name_plural = _("Régions")
        ordering = ['nom']

    def __str__(self):
        return self.nom


# ===================================================================
# MODÈLE DEPARTEMENT
# ===================================================================

class Departement(models.Model):
    """Département administratif du Cameroun"""
    region = models.ForeignKey(
        Region, 
        on_delete=models.CASCADE, 
        related_name='departements', 
        verbose_name=_("Région")
    )
    nom = models.CharField(
        max_length=50, 
        verbose_name=_("Département")
    )

    class Meta:
        verbose_name = _("Département")
        verbose_name_plural = _("Départements")
        unique_together = ('region', 'nom')
        ordering = ['region__nom', 'nom']

    def __str__(self):
        return f"{self.nom} ({self.region.nom})"


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

    nouveau = models.BooleanField(
        default=False,
        help_text="Cocher si c'est un nouveau poste pour l'année en cours",
        verbose_name="Nouveau poste"
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
    
    axe_routier = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Axe routier"),
        help_text=_("Axe routier où se situe le poste (ex: Yaoundé-Douala)")
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
        auto_now=True,
        verbose_name=_("Date de modification")
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
        """Calcule le taux de réalisation par rapport à l'objectif de l'année"""
        from inventaire.models import ObjectifAnnuel
        
        if annee is None:
            annee = timezone.now().year
        
        try:
            objectif = ObjectifAnnuel.objects.get(poste=self, annee=annee)
            objectif_annuel = objectif.montant_objectif
        except:
            return None
        
        if objectif_annuel and objectif_annuel > 0:
            realise = self.get_realisation_annee(annee)
            return (realise / objectif_annuel * 100)
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
# MANAGER UTILISATEUR PERSONNALISÉ
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


# ===================================================================
# MODÈLE UTILISATEUR SUPPER - VERSION COMPLÈTE
# ===================================================================

class UtilisateurSUPPER(AbstractUser):
    """
    Utilisateur personnalisé pour le système SUPPER
    Étend AbstractUser avec champs spécifiques métier
    """
    
    # Manager personnalisé
    objects = UtilisateurSupperManager()
    
    # Redéfinir le champ username
    username = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=_("Matricule"),
        help_text=_("Matricule unique de l'agent (ex: 1052105M)")
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
    
    # Email optionnel
    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name=_("Adresse email"),
        help_text=_("Email optionnel pour la réinitialisation de mot de passe")
    )

    permissions_personnalisees = models.BooleanField(
        default=False,
        verbose_name=_("Permissions personnalisées"),
        help_text=_("Si True, les permissions ont été modifiées manuellement et ne seront pas écrasées par fix_user_permissions")
    )

    date_personnalisation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Date de personnalisation"),
        help_text=_("Date de la dernière modification manuelle des permissions")
    )

    personnalise_par = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='utilisateurs_personnalises',
        verbose_name=_("Personnalisé par"),
        help_text=_("Administrateur qui a personnalisé les permissions")
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
    
    # Rôle et habilitation
    habilitation = models.CharField(
        max_length=30,
        choices=Habilitation.choices,
        default=Habilitation.AGENT_INVENTAIRE,
        verbose_name=_("Habilitation"),
        help_text=_("Rôle de l'utilisateur dans le système SUPPER")
    )
    
    # ===============================================================
    # PERMISSIONS D'ACCÈS GLOBALES
    # ===============================================================
    
    acces_tous_postes = models.BooleanField(
        default=False,
        verbose_name=_("Accès à tous les postes"),
        help_text=_("Si False, accès limité au poste d'affectation uniquement")
    )
    
    peut_saisir_peage = models.BooleanField(
        default=False,
        verbose_name=_("Peut saisir données péage")
    )
    
    peut_saisir_pesage = models.BooleanField(
        default=False,
        verbose_name=_("Peut saisir données pesage")
    )
    
    voir_recettes_potentielles = models.BooleanField(
        default=False,
        verbose_name=_("Peut voir recettes potentielles")
    )
    
    voir_taux_deperdition = models.BooleanField(
        default=False,
        verbose_name=_("Peut voir taux déperdition")
    )
    
    voir_statistiques_globales = models.BooleanField(
        default=False,
        verbose_name=_("Peut voir statistiques globales")
    )
    
    peut_saisir_pour_autres_postes = models.BooleanField(
        default=False,
        verbose_name=_("Peut saisir pour autres postes")
    )
    
    # ===============================================================
    # ANCIENNES PERMISSIONS MODULES (conservées pour compatibilité)
    # ===============================================================
    
    peut_gerer_peage = models.BooleanField(default=False, verbose_name=_("Gérer le péage"))
    peut_gerer_pesage = models.BooleanField(default=False, verbose_name=_("Gérer le pesage"))
    peut_gerer_personnel = models.BooleanField(default=False, verbose_name=_("Gérer le personnel"))
    peut_gerer_budget = models.BooleanField(default=False, verbose_name=_("Gérer le budget"))
    peut_gerer_inventaire = models.BooleanField(default=False, verbose_name=_("Gérer l'inventaire"))
    peut_gerer_archives = models.BooleanField(default=False, verbose_name=_("Gérer les archives"))
    peut_gerer_stocks_psrr = models.BooleanField(default=False, verbose_name=_("Gérer les stocks PSRR"))
    peut_gerer_stock_info = models.BooleanField(default=False, verbose_name=_("Gérer le stock info"))
    
    # ===============================================================
    # NOUVELLES PERMISSIONS INVENTAIRES (selon matrice PDF)
    # ===============================================================
    
    peut_saisir_inventaire_normal = models.BooleanField(
        default=False, verbose_name=_("Saisir inventaire normal"))
    peut_saisir_inventaire_admin = models.BooleanField(
        default=False, verbose_name=_("Saisir inventaire administratif"))
    peut_programmer_inventaire = models.BooleanField(
        default=False, verbose_name=_("Programmer inventaire"))
    peut_voir_programmation_active = models.BooleanField(
        default=False, verbose_name=_("Voir programmation active"))
    peut_desactiver_programmation = models.BooleanField(
        default=False, verbose_name=_("Désactiver programmation"))
    peut_voir_programmation_desactivee = models.BooleanField(
        default=False, verbose_name=_("Voir programmations désactivées"))
    peut_voir_liste_inventaires = models.BooleanField(
        default=False, verbose_name=_("Voir liste inventaires"))
    peut_voir_liste_inventaires_admin = models.BooleanField(
        default=False, verbose_name=_("Voir liste inventaires admin"))
    peut_voir_jours_impertinents = models.BooleanField(
        default=False, verbose_name=_("Voir jours impertinents"))
    peut_voir_stats_deperdition = models.BooleanField(
        default=False, verbose_name=_("Voir stats déperdition"))
    
    # ===============================================================
    # NOUVELLES PERMISSIONS RECETTES PEAGE
    # ===============================================================
    
    peut_saisir_recette_peage = models.BooleanField(
        default=False, verbose_name=_("Saisir recette péage"))
    peut_voir_liste_recettes_peage = models.BooleanField(
        default=False, verbose_name=_("Voir liste recettes péage"))
    peut_voir_stats_recettes_peage = models.BooleanField(
        default=False, verbose_name=_("Voir stats recettes péage"))
    peut_importer_recettes_peage = models.BooleanField(
        default=False, verbose_name=_("Importer recettes péage"))
    peut_voir_evolution_peage = models.BooleanField(
        default=False, verbose_name=_("Voir évolution péage"))
    peut_voir_objectifs_peage = models.BooleanField(
        default=False, verbose_name=_("Voir objectifs péage"))
    
    # ===============================================================
    # NOUVELLES PERMISSIONS QUITTANCES PEAGE
    # ===============================================================
    
    peut_saisir_quittance_peage = models.BooleanField(
        default=False, verbose_name=_("Saisir quittance péage"))
    peut_voir_liste_quittances_peage = models.BooleanField(
        default=False, verbose_name=_("Voir liste quittances péage"))
    peut_comptabiliser_quittances_peage = models.BooleanField(
        default=False, verbose_name=_("Comptabiliser quittances péage"))
    
    # ===============================================================
    # NOUVELLES PERMISSIONS PESAGE
    # ===============================================================
    
    peut_voir_historique_vehicule_pesage = models.BooleanField(
        default=False, verbose_name=_("Voir historique véhicule pesage"))
    peut_saisir_amende = models.BooleanField(
        default=False, verbose_name=_("Saisir amende"))
    peut_saisir_pesee_jour = models.BooleanField(
        default=False, verbose_name=_("Saisir pesée du jour"))
    peut_voir_objectifs_pesage = models.BooleanField(
        default=False, verbose_name=_("Voir objectifs pesage"))
    peut_valider_paiement_amende = models.BooleanField(
        default=False, verbose_name=_("Valider paiement amende"))
    peut_lister_amendes = models.BooleanField(
        default=False, verbose_name=_("Lister amendes"))
    peut_saisir_quittance_pesage = models.BooleanField(
        default=False, verbose_name=_("Saisir quittance pesage"))
    peut_comptabiliser_quittances_pesage = models.BooleanField(
        default=False, verbose_name=_("Comptabiliser quittances pesage"))
    peut_voir_liste_quittancements_pesage = models.BooleanField(
        default=False, verbose_name=_("Voir liste quittancements pesage"))
    peut_voir_historique_pesees = models.BooleanField(
        default=False, verbose_name=_("Voir historique pesées"))
    peut_voir_recettes_pesage = models.BooleanField(
        default=False, verbose_name=_("Voir recettes pesage"))
    peut_voir_stats_pesage = models.BooleanField(
        default=False, verbose_name=_("Voir stats pesage"))
    
    # ===============================================================
    # NOUVELLES PERMISSIONS STOCK PEAGE
    # ===============================================================
    
    peut_charger_stock_peage = models.BooleanField(
        default=False, verbose_name=_("Charger stock péage"))
    peut_voir_liste_stocks_peage = models.BooleanField(
        default=False, verbose_name=_("Voir liste stocks péage"))
    peut_voir_stock_date_peage = models.BooleanField(
        default=False, verbose_name=_("Voir stock à date péage"))
    peut_transferer_stock_peage = models.BooleanField(
        default=False, verbose_name=_("Transférer stock péage"))
    peut_voir_tracabilite_tickets = models.BooleanField(
        default=False, verbose_name=_("Voir traçabilité tickets"))
    peut_voir_bordereaux_peage = models.BooleanField(
        default=False, verbose_name=_("Voir bordereaux péage"))
    peut_voir_mon_stock_peage = models.BooleanField(
        default=False, verbose_name=_("Voir mon stock péage"))
    peut_voir_historique_stock_peage = models.BooleanField(
        default=False, verbose_name=_("Voir historique stock péage"))
    peut_simuler_commandes_peage = models.BooleanField(
        default=False, verbose_name=_("Simuler commandes péage"))
    
    # ===============================================================
    # NOUVELLES PERMISSIONS GESTION
    # ===============================================================
    
    peut_gerer_postes = models.BooleanField(
        default=False, verbose_name=_("Gérer les postes"))
    peut_ajouter_poste = models.BooleanField(
        default=False, verbose_name=_("Ajouter un poste"))
    peut_creer_poste_masse = models.BooleanField(
        default=False, verbose_name=_("Créer postes en masse"))
    peut_gerer_utilisateurs = models.BooleanField(
        default=False, verbose_name=_("Gérer utilisateurs"))
    peut_creer_utilisateur = models.BooleanField(
        default=False, verbose_name=_("Créer utilisateur"))
    peut_voir_journal_audit = models.BooleanField(
        default=False, verbose_name=_("Voir journal audit"))
    
    # ===============================================================
    # NOUVELLES PERMISSIONS RAPPORTS
    # ===============================================================
    
    peut_voir_rapports_defaillants_peage = models.BooleanField(
        default=False, verbose_name=_("Voir rapports défaillants péage"))
    peut_voir_rapports_defaillants_pesage = models.BooleanField(
        default=False, verbose_name=_("Voir rapports défaillants pesage"))
    peut_voir_rapport_inventaires = models.BooleanField(
        default=False, verbose_name=_("Voir rapport inventaires"))
    peut_voir_classement_peage_rendement = models.BooleanField(
        default=False, verbose_name=_("Voir classement péage rendement"))
    peut_voir_classement_station_pesage = models.BooleanField(
        default=False, verbose_name=_("Voir classement station pesage"))
    peut_voir_classement_peage_deperdition = models.BooleanField(
        default=False, verbose_name=_("Voir classement péage déperdition"))
    peut_voir_classement_agents_inventaire = models.BooleanField(
        default=False, verbose_name=_("Voir classement agents inventaire"))
    
    # ===============================================================
    # NOUVELLES PERMISSIONS AUTRES
    # ===============================================================
    
    peut_parametrage_global = models.BooleanField(
        default=False, verbose_name=_("Paramétrage global"))
    peut_voir_compte_emploi = models.BooleanField(
        default=False, verbose_name=_("Voir compte d'emploi"))
    peut_voir_pv_confrontation = models.BooleanField(
        default=False, verbose_name=_("Voir PV confrontation"))
    peut_authentifier_document = models.BooleanField(
        default=False, verbose_name=_("Authentifier document"))
    peut_voir_tous_postes = models.BooleanField(
        default=False, verbose_name=_("Voir tous les postes"))
    
    # ===============================================================
    # MÉTADONNÉES ET TRAÇABILITÉ
    # ===============================================================
    
    cree_par = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='utilisateurs_crees',
        verbose_name=_("Créé par")
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
        """
        Sauvegarde l'utilisateur avec gestion intelligente des permissions.
        
        Paramètres kwargs spéciaux:
            - skip_auto_permissions: Ne pas recalculer les permissions automatiques
            - force_auto_permissions: Forcer le recalcul (réinitialise permissions_personnalisees)
            - mark_customized: Marquer comme personnalisé (avec qui et quand)
            - customized_by: Utilisateur qui personnalise (pour mark_customized)
        
        Comportement:
            - Création: Toujours attribuer les permissions automatiques
            - Modification avec skip: Conserver les permissions actuelles
            - Modification avec force: Recalculer et retirer le flag personnalisé
        """
        from django.utils import timezone
        
        # Extraire les paramètres spéciaux
        skip_auto_permissions = kwargs.pop('skip_auto_permissions', False)
        force_auto_permissions = kwargs.pop('force_auto_permissions', False)
        mark_customized = kwargs.pop('mark_customized', False)
        customized_by = kwargs.pop('customized_by', None)
        
        # Détecter si c'est une création
        is_new = self._state.adding or self.pk is None
        
        # Gestion des permissions
        if force_auto_permissions:
            # Forcer le recalcul et retirer le flag personnalisé
            self.attribuer_permissions_automatiques()
            self.permissions_personnalisees = False
            self.date_personnalisation = None
            self.personnalise_par = None
        elif is_new:
            # Nouvelle création: permissions par défaut
            self.attribuer_permissions_automatiques()
        elif not skip_auto_permissions:
            # Modification standard: recalculer
            self.attribuer_permissions_automatiques()
        # Si skip_auto_permissions=True: ne pas toucher aux permissions
        
        # Marquer comme personnalisé si demandé
        if mark_customized:
            self.permissions_personnalisees = True
            self.date_personnalisation = timezone.now()
            if customized_by:
                self.personnalise_par = customized_by
        
        super().save(*args, **kwargs)
        
        if is_new:
            logger.info(f"Nouvel utilisateur créé: {self.username} ({self.nom_complet})")
        else:
            logger.info(f"Utilisateur modifié: {self.username}" + 
                    (" [permissions personnalisées]" if self.permissions_personnalisees else ""))

    
    # ===============================================================
    # PROPRIÉTÉS
    # ===============================================================
    
    @property
    def is_admin(self):
        """Vérifie si l'utilisateur est administrateur"""
        return (
            self.is_superuser or
            self.is_staff or
            self.habilitation in [
                Habilitation.ADMIN_PRINCIPAL,
                Habilitation.COORDONNATEUR_PSRR,
                Habilitation.SERVICE_INFORMATIQUE,
                Habilitation.SERVICE_EMISSION
            ]
        )
    
    @property
    def is_chef_poste(self):
        """Vérifie si l'utilisateur est chef de poste"""
        return self.habilitation in [
            Habilitation.CHEF_POSTE_PEAGE,
            Habilitation.CHEF_STATION_PESAGE
        ]
    
    @property
    def nom_role(self):
        """Retourne le nom du rôle en français"""
        return self.get_habilitation_display()
    
    @property
    def niveau_acces(self):
        """Retourne le niveau d'accès de l'utilisateur"""
        if self.habilitation in [
            Habilitation.ADMIN_PRINCIPAL,
            Habilitation.COORDONNATEUR_PSRR,
            Habilitation.SERVICE_INFORMATIQUE
        ] or self.is_superuser:
            return 'COMPLET'
        elif self.habilitation in [
            Habilitation.SERVICE_EMISSION,
            Habilitation.CHEF_AFFAIRES_GENERALES,
            Habilitation.SERVICE_CONTROLE_VALIDATION,
            Habilitation.SERVICE_ORDRE_SECRETARIAT
        ]:
            return 'ÉTENDU'
        elif self.habilitation in [
            Habilitation.CISOP_PEAGE,
            Habilitation.CISOP_PESAGE,
            Habilitation.CHEF_POSTE_PEAGE,
            Habilitation.CHEF_STATION_PESAGE
        ]:
            return 'STANDARD'
        else:
            return 'LIMITÉ'
    
    # ===============================================================
    # MÉTHODES D'ACCÈS
    # ===============================================================
    
    def get_absolute_url(self):
        return reverse('accounts:user_detail', kwargs={'pk': self.pk})
    
    def peut_voir_poste(self, poste):
        """Vérifie si l'utilisateur peut voir les données d'un poste"""
        if self.acces_tous_postes or self.peut_voir_tous_postes:
            return True
        return self.poste_affectation == poste
    
    def peut_modifier_poste(self, poste):
        """Vérifie si l'utilisateur peut modifier les données d'un poste"""
        if self.peut_saisir_pour_autres_postes:
            return True
        return self.peut_voir_poste(poste)
    
    def get_postes_accessibles(self):
        """Retourne la liste des postes auxquels l'utilisateur a accès"""
        if self.acces_tous_postes or self.is_admin or self.peut_voir_tous_postes:
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
    
    # ===============================================================
    # ATTRIBUTION AUTOMATIQUE DES PERMISSIONS
    # ===============================================================
    
    def attribuer_permissions_automatiques(self):
        """
        Attribue les permissions automatiquement selon l'habilitation.
        Appelle d'abord _reinitialiser_toutes_permissions() puis la méthode
        de configuration spécifique au rôle.
        """
        # D'abord réinitialiser toutes les permissions à False
        self._reinitialiser_toutes_permissions()
        
        # Mapping habilitation → méthode de configuration
        CONFIG_MAP = {
            'admin_principal': self._configurer_admin_principal,
            'coord_psrr': self._configurer_coordonnateur_psrr,
            'serv_info': self._configurer_service_informatique,
            'serv_emission': self._configurer_service_emission,
            'chef_ag': self._configurer_chef_affaires_generales,
            'serv_controle': self._configurer_service_controle_validation,
            'serv_ordre': self._configurer_service_ordre_secretariat,
            'imprimerie': self._configurer_imprimerie_nationale,
            'cisop_peage': self._configurer_cisop_peage,
            'cisop_pesage': self._configurer_cisop_pesage,
            'chef_peage': self._configurer_chef_poste_peage,
            'chef_station_pesage': self._configurer_chef_station_pesage,
            'regisseur_pesage': self._configurer_regisseur_pesage,
            'chef_equipe_pesage': self._configurer_chef_equipe_pesage,
            'agent_inventaire': self._configurer_agent_inventaire,
            'comptable_mat': self._configurer_comptable_matieres,
        }
        
        # Appeler la méthode de configuration correspondante
        if self.habilitation and self.habilitation in CONFIG_MAP:
            CONFIG_MAP[self.habilitation]()
        else:
            logger.warning(f"Habilitation non reconnue: {self.habilitation}")

    
    def _reinitialiser_toutes_permissions(self):
        """Réinitialise toutes les permissions à False"""
        self.is_staff = False
        self.is_superuser = False
        self.acces_tous_postes = False
        self.peut_saisir_peage = False
        self.peut_saisir_pesage = False
        self.voir_recettes_potentielles = False
        self.voir_taux_deperdition = False
        self.voir_statistiques_globales = False
        self.peut_saisir_pour_autres_postes = False
        
        # Anciennes permissions
        for field in ['peut_gerer_peage', 'peut_gerer_pesage', 'peut_gerer_personnel',
                      'peut_gerer_budget', 'peut_gerer_inventaire', 'peut_gerer_archives',
                      'peut_gerer_stocks_psrr', 'peut_gerer_stock_info']:
            setattr(self, field, False)
        
        # Nouvelles permissions granulaires
        permission_fields = [
            'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin',
            'peut_programmer_inventaire', 'peut_voir_programmation_active',
            'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
            'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin',
            'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
            'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage',
            'peut_voir_stats_recettes_peage', 'peut_importer_recettes_peage',
            'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
            'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage',
            'peut_comptabiliser_quittances_peage', 'peut_voir_historique_vehicule_pesage',
            'peut_saisir_amende', 'peut_saisir_pesee_jour', 'peut_voir_objectifs_pesage',
            'peut_valider_paiement_amende', 'peut_lister_amendes',
            'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage',
            'peut_voir_liste_quittancements_pesage', 'peut_voir_historique_pesees',
            'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
            'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage',
            'peut_voir_stock_date_peage', 'peut_transferer_stock_peage',
            'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
            'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage',
            'peut_simuler_commandes_peage', 'peut_gerer_postes', 'peut_ajouter_poste',
            'peut_creer_poste_masse', 'peut_gerer_utilisateurs', 'peut_creer_utilisateur',
            'peut_voir_journal_audit', 'peut_voir_rapports_defaillants_peage',
            'peut_voir_rapports_defaillants_pesage', 'peut_voir_rapport_inventaires',
            'peut_voir_classement_peage_rendement', 'peut_voir_classement_station_pesage',
            'peut_voir_classement_peage_deperdition', 'peut_voir_classement_agents_inventaire',
            'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
            'peut_authentifier_document', 'peut_voir_tous_postes'
        ]
        for field in permission_fields:
            setattr(self, field, False)
    
    def _activer_toutes_permissions(self):
        """Active toutes les permissions (pour admins)"""
        # Anciennes permissions
        for field in ['peut_gerer_peage', 'peut_gerer_pesage', 'peut_gerer_personnel',
                      'peut_gerer_budget', 'peut_gerer_inventaire', 'peut_gerer_archives',
                      'peut_gerer_stocks_psrr', 'peut_gerer_stock_info']:
            setattr(self, field, True)
        
        # Nouvelles permissions
        permission_fields = [
            'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin',
            'peut_programmer_inventaire', 'peut_voir_programmation_active',
            'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
            'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin',
            'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
            'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage',
            'peut_voir_stats_recettes_peage', 'peut_importer_recettes_peage',
            'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
            'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage',
            'peut_comptabiliser_quittances_peage', 'peut_voir_historique_vehicule_pesage',
            'peut_saisir_amende', 'peut_saisir_pesee_jour', 'peut_voir_objectifs_pesage',
            'peut_valider_paiement_amende', 'peut_lister_amendes',
            'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage',
            'peut_voir_liste_quittancements_pesage', 'peut_voir_historique_pesees',
            'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
            'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage',
            'peut_voir_stock_date_peage', 'peut_transferer_stock_peage',
            'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
            'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage',
            'peut_simuler_commandes_peage', 'peut_gerer_postes', 'peut_ajouter_poste',
            'peut_creer_poste_masse', 'peut_gerer_utilisateurs', 'peut_creer_utilisateur',
            'peut_voir_journal_audit', 'peut_voir_rapports_defaillants_peage',
            'peut_voir_rapports_defaillants_pesage', 'peut_voir_rapport_inventaires',
            'peut_voir_classement_peage_rendement', 'peut_voir_classement_station_pesage',
            'peut_voir_classement_peage_deperdition', 'peut_voir_classement_agents_inventaire',
            'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
            'peut_authentifier_document', 'peut_voir_tous_postes'
        ]
        for field in permission_fields:
            setattr(self, field, True)
    
    # ===============================================================
    # CONFIGURATIONS PAR RÔLE (basées sur la matrice PDF)
    # ===============================================================
    
    def _configurer_admin_principal(self):
        """ADMINISTRATEUR PRINCIPAL - Accès complet"""
        self.is_staff = True
        self.is_superuser = True
        self.acces_tous_postes = True
        self.peut_saisir_peage = True
        self.peut_saisir_pesage = True
        self.voir_recettes_potentielles = True
        self.voir_taux_deperdition = True
        self.voir_statistiques_globales = True
        self.peut_saisir_pour_autres_postes = True
        self._activer_toutes_permissions()
    
    def _configurer_coordonnateur_psrr(self):
        """COORDONNATEUR PSRR - Accès complet similaire à admin"""
        self.is_staff = True
        self.acces_tous_postes = True
        self.peut_saisir_peage = True
        self.peut_saisir_pesage = True
        self.voir_recettes_potentielles = True
        self.voir_taux_deperdition = True
        self.voir_statistiques_globales = True
        self.peut_saisir_pour_autres_postes = True
        self._activer_toutes_permissions()
    
    def _configurer_service_informatique(self):
        """SERVICE INFORMATIQUE - Accès complet pour maintenance"""
        self.is_staff = True
        self.acces_tous_postes = True
        self.peut_saisir_peage = True
        self.peut_saisir_pesage = True
        self.voir_recettes_potentielles = True
        self.voir_taux_deperdition = True
        self.voir_statistiques_globales = True
        self.peut_saisir_pour_autres_postes = True
        self._activer_toutes_permissions()
    
    def _configurer_service_emission(self):
        """SERVICE EMISSIONS ET RECOUVREMENT"""
        self.is_staff = True
        self.acces_tous_postes = True
        self.voir_statistiques_globales = True
        self.voir_recettes_potentielles = True
        self.voir_taux_deperdition = True
        
        # Inventaires
        self.peut_programmer_inventaire = True
        self.peut_voir_programmation_active = True
        self.peut_voir_programmation_desactivee = True
        self.peut_voir_liste_inventaires = True
        self.peut_voir_liste_inventaires_admin = True
        self.peut_voir_jours_impertinents = True
        self.peut_voir_stats_deperdition = True
        
        # Recettes péage
        self.peut_voir_liste_recettes_peage = True
        self.peut_voir_stats_recettes_peage = True
        self.peut_voir_evolution_peage = True
        self.peut_voir_objectifs_peage = True
        
        # Quittances péage
        self.peut_voir_liste_quittances_peage = True
        self.peut_comptabiliser_quittances_peage = True
        
        # Pesage
        self.peut_voir_objectifs_pesage = True
        self.peut_lister_amendes = True
        self.peut_comptabiliser_quittances_pesage = True
        self.peut_voir_liste_quittancements_pesage = True
        self.peut_voir_historique_pesees = True
        self.peut_voir_recettes_pesage = True
        self.peut_voir_stats_pesage = True
        
        # Stock péage
        self.peut_charger_stock_peage = True
        self.peut_voir_liste_stocks_peage = True
        self.peut_voir_stock_date_peage = True
        self.peut_transferer_stock_peage = True
        self.peut_voir_tracabilite_tickets = True
        self.peut_voir_bordereaux_peage = True
        self.peut_voir_mon_stock_peage = True
        self.peut_voir_historique_stock_peage = True
        self.peut_simuler_commandes_peage = True
        
        # Rapports
        self.peut_voir_rapports_defaillants_peage = True
        self.peut_voir_rapport_inventaires = True
        self.peut_voir_classement_peage_rendement = True
        self.peut_voir_classement_station_pesage = True
        self.peut_voir_classement_peage_deperdition = True
        self.peut_voir_classement_agents_inventaire = True
        
        # Autres
        self.peut_voir_compte_emploi = True
        self.peut_voir_pv_confrontation = True
        self.peut_authentifier_document = True
        self.peut_voir_tous_postes = True
        
        # Anciennes permissions
        self.peut_gerer_peage = True
        self.peut_gerer_stocks_psrr = True
        self.peut_saisir_peage = True
    
    def _configurer_chef_affaires_generales(self):
        """SERVICE DES AFFAIRES GENERALES"""
        self.acces_tous_postes = True
        self.peut_gerer_personnel = True
        
        self.peut_gerer_postes = True
        self.peut_ajouter_poste = True
        self.peut_creer_poste_masse = True
        self.peut_gerer_utilisateurs = True
        self.peut_creer_utilisateur = True
        self.peut_voir_journal_audit = True
        self.peut_parametrage_global = True
        self.peut_voir_tous_postes = True
    
    def _configurer_service_controle_validation(self):
        """SERVICE CONTROLE ET VALIDATION"""
        self.acces_tous_postes = True
        
        # Recettes péage
        self.peut_voir_liste_recettes_peage = True
        self.peut_voir_stats_recettes_peage = True
        self.peut_voir_evolution_peage = True
        self.peut_voir_objectifs_peage = True
        
        # Quittances péage
        self.peut_voir_liste_quittances_peage = True
        self.peut_comptabiliser_quittances_peage = True
        
        # Pesage
        self.peut_voir_objectifs_pesage = True
        self.peut_lister_amendes = True
        self.peut_comptabiliser_quittances_pesage = True
        self.peut_voir_liste_quittancements_pesage = True
        self.peut_voir_historique_pesees = True
        self.peut_voir_recettes_pesage = True
        self.peut_voir_stats_pesage = True
        
        # Stock péage
        self.peut_voir_liste_stocks_peage = True
        self.peut_voir_stock_date_peage = True
        self.peut_voir_tracabilite_tickets = True
        self.peut_voir_bordereaux_peage = True
        self.peut_voir_historique_stock_peage = True
        
        # Gestion
        self.peut_voir_journal_audit = True
        
        # Rapports
        self.peut_voir_rapports_defaillants_peage = True
        self.peut_voir_rapports_defaillants_pesage = True
        self.peut_voir_rapport_inventaires = True
        self.peut_voir_classement_peage_rendement = True
        self.peut_voir_classement_station_pesage = True
        self.peut_voir_classement_peage_deperdition = True
        self.peut_voir_classement_agents_inventaire = True
        
        # Autres
        self.peut_parametrage_global = True
        self.peut_voir_compte_emploi = True
        self.peut_voir_pv_confrontation = True
        self.peut_authentifier_document = True
        self.peut_voir_tous_postes = True
    
    def _configurer_service_ordre_secretariat(self):
        """SERVICE ORDRE/SECRETARIAT"""
        self.acces_tous_postes = True
        
        # Recettes péage
        self.peut_voir_liste_recettes_peage = True
        self.peut_voir_stats_recettes_peage = True
        self.peut_voir_evolution_peage = True
        self.peut_voir_objectifs_peage = True
        
        # Quittances péage
        self.peut_voir_liste_quittances_peage = True
        self.peut_comptabiliser_quittances_peage = True
        
        # Pesage
        self.peut_voir_objectifs_pesage = True
        self.peut_lister_amendes = True
        self.peut_comptabiliser_quittances_pesage = True
        self.peut_voir_liste_quittancements_pesage = True
        self.peut_voir_historique_pesees = True
        self.peut_voir_recettes_pesage = True
        self.peut_voir_stats_pesage = True
        
        # Stock péage
        self.peut_voir_liste_stocks_peage = True
        self.peut_voir_stock_date_peage = True
        self.peut_voir_tracabilite_tickets = True
        self.peut_voir_bordereaux_peage = True
        self.peut_voir_historique_stock_peage = True
        
        # Gestion postes et utilisateurs
        self.peut_gerer_postes = True
        self.peut_ajouter_poste = True
        self.peut_creer_poste_masse = True
        self.peut_gerer_utilisateurs = True
        self.peut_creer_utilisateur = True
        self.peut_voir_journal_audit = True
        
        # Rapports
        self.peut_voir_rapport_inventaires = True
        self.peut_voir_classement_peage_rendement = True
        self.peut_voir_classement_station_pesage = True
        self.peut_voir_classement_peage_deperdition = True
        self.peut_voir_classement_agents_inventaire = True
        
        # Autres
        self.peut_parametrage_global = True
        self.peut_voir_compte_emploi = True
        self.peut_voir_pv_confrontation = True
        self.peut_authentifier_document = True
        self.peut_voir_tous_postes = True
    
    def _configurer_imprimerie_nationale(self):
        """IMPRIMERIE NATIONALE"""
        self.peut_voir_historique_stock_peage = True
        self.peut_voir_tous_postes = True
    
    def _configurer_cisop_peage(self):
        """CISOP PEAGE"""
        self.acces_tous_postes = True
        self.voir_taux_deperdition = True
        
        self.peut_voir_stats_deperdition = True
        self.peut_voir_liste_recettes_peage = True
        self.peut_voir_stats_recettes_peage = True
        self.peut_voir_evolution_peage = True
        self.peut_voir_objectifs_peage = True
        self.peut_voir_liste_quittances_peage = True
        self.peut_comptabiliser_quittances_peage = True
        self.peut_voir_liste_stocks_peage = True
        self.peut_voir_tracabilite_tickets = True
        self.peut_voir_bordereaux_peage = True
        self.peut_voir_historique_stock_peage = True
        self.peut_voir_classement_peage_rendement = True
        self.peut_voir_classement_peage_deperdition = True
        self.peut_voir_compte_emploi = True
        self.peut_voir_pv_confrontation = True
        self.peut_authentifier_document = True
        self.peut_voir_tous_postes = True
    
    def _configurer_cisop_pesage(self):
        """CISOP PESAGE"""
        self.acces_tous_postes = True
        
        self.peut_voir_objectifs_pesage = True
        self.peut_lister_amendes = True
        self.peut_comptabiliser_quittances_pesage = True
        self.peut_voir_liste_quittancements_pesage = True
        self.peut_voir_historique_pesees = True
        self.peut_voir_recettes_pesage = True
        self.peut_voir_stats_pesage = True
        self.peut_voir_rapports_defaillants_pesage = True
        self.peut_voir_classement_station_pesage = True
        self.peut_voir_tous_postes = True
    
    def _configurer_chef_poste_peage(self):
        """CHEF DE POSTE PEAGE"""
        self.peut_saisir_peage = True
        self.voir_taux_deperdition = True
        self.voir_recettes_potentielles = False  # RESTRICTION IMPORTANTE
        
        self.peut_voir_liste_inventaires = True
        self.peut_voir_jours_impertinents = True
        self.peut_voir_stats_deperdition = True
        self.peut_saisir_recette_peage = True
        self.peut_voir_liste_recettes_peage = True
        self.peut_voir_stats_recettes_peage = True
        self.peut_voir_evolution_peage = True
        self.peut_voir_objectifs_peage = True
        self.peut_saisir_quittance_peage = True
        self.peut_voir_liste_quittances_peage = True
        self.peut_comptabiliser_quittances_peage = True
        self.peut_voir_liste_stocks_peage = True
        self.peut_voir_stock_date_peage = True
        self.peut_transferer_stock_peage = True
        self.peut_voir_tracabilite_tickets = True
        self.peut_voir_bordereaux_peage = True
        self.peut_voir_mon_stock_peage = True
        self.peut_voir_historique_stock_peage = True
        self.peut_voir_classement_peage_rendement = True
        self.peut_voir_classement_peage_deperdition = True
        self.peut_voir_classement_agents_inventaire = True
        self.peut_voir_compte_emploi = True
        self.peut_voir_pv_confrontation = True
        self.peut_authentifier_document = True
        
        # Anciennes permissions
        self.peut_gerer_peage = True
    
    def _configurer_chef_station_pesage(self):
        """CHEF DE STATION PESAGE"""
        self.peut_saisir_pesage = True
        
        self.peut_voir_historique_vehicule_pesage = True
        self.peut_saisir_pesee_jour = True
        self.peut_voir_objectifs_pesage = True
        self.peut_lister_amendes = True
        self.peut_comptabiliser_quittances_pesage = True
        self.peut_voir_liste_quittancements_pesage = True
        self.peut_voir_historique_pesees = True
        self.peut_voir_recettes_pesage = True
        self.peut_voir_stats_pesage = True
        self.peut_voir_classement_station_pesage = True
        
    
    def _configurer_regisseur_pesage(self):
        """REGISSEUR DE STATION PESAGE"""
        self.peut_voir_historique_vehicule_pesage = True
        self.peut_voir_objectifs_pesage = True
        self.peut_valider_paiement_amende = True
        self.peut_lister_amendes = True
        self.peut_saisir_quittance_pesage = True
        self.peut_comptabiliser_quittances_pesage = True
        self.peut_voir_liste_quittancements_pesage = True
        self.peut_voir_historique_pesees = True
        self.peut_voir_recettes_pesage = True
        self.peut_voir_stats_pesage = True
        self.peut_voir_classement_station_pesage = True
        
        # Anciennes permissions
        self.peut_gerer_pesage = True
    
    def _configurer_chef_equipe_pesage(self):
        """CHEF D'EQUIPE PESAGE"""
        self.peut_saisir_pesage = True
        
        self.peut_voir_historique_vehicule_pesage = True
        self.peut_saisir_amende = True
        self.peut_saisir_pesee_jour = True
        self.peut_voir_objectifs_pesage = True
        self.peut_lister_amendes = True
        self.peut_voir_historique_pesees = True
        self.peut_voir_recettes_pesage = True
        self.peut_voir_stats_pesage = True
    
    def _configurer_agent_inventaire(self):
        """AGENT INVENTAIRE - Droits limités"""
        self.voir_recettes_potentielles = False  # RESTRICTION
        self.voir_taux_deperdition = True 
        self.voir_statistiques_globales = False
        
        self.peut_saisir_inventaire_normal = True
        self.peut_voir_liste_inventaires = True
        self.peut_voir_jours_impertinents = True
        self.peut_voir_stats_deperdition = True
        
        # Anciennes permissions
        self.peut_gerer_inventaire = True
    
    def _configurer_comptable_matieres(self):
        """COMPTABLE MATIERES"""
        self.peut_gerer_archives = True
        self.acces_tous_postes = True


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
        try:
            return f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.utilisateur.username} - {self.action}"
        except (AttributeError, ValueError):
            return f"Journal #{self.pk} - {self.action}"
    
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
    
    def get_details_safe(self):
        """Retourne les détails de manière sécurisée pour l'affichage"""
        if not self.details:
            return "Aucun détail"
        
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
        else:
            return "À l'instant"