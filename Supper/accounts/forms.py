# ===================================================================
# accounts/forms.py - Formulaires pour l'application accounts SUPPER
# VERSION MISE À JOUR - Intégration complète des nouvelles habilitations
# selon la matrice PDF et le modèle UtilisateurSUPPER actualisé
# ===================================================================

from django import forms
from django.contrib.auth.views import LoginView
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm, PasswordChangeForm as DjangoPasswordChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import authenticate
from .models import Departement, UtilisateurSUPPER, Poste, Habilitation, Region
import re
import logging

logger = logging.getLogger('supper')


# ===================================================================
# DICTIONNAIRE DES DÉPARTEMENTS PAR RÉGION
# ===================================================================

DEPARTEMENTS_CAMEROUN = {
    'adamaoua': [
        'Djérem', 'Faro-et-Déo', 'Mayo-Banyo', 'Mbéré', 'Vina'
    ],
    'centre': [
        'Haute-Sanaga', 'Lekié', 'Mbam-et-Inoubou', 'Mbam-et-Kim',
        'Méfou-et-Afamba', 'Méfou-et-Akono', 'Mfoundi', 'Nyong-et-Kellé',
        'Nyong-et-Mfoumou', 'Nyong-et-So\'o'
    ],
    'est': [
        'Boumba-et-Ngoko', 'Haut-Nyong', 'Kadey', 'Lom-et-Djérem'
    ],
    'extreme_nord': [
        'Diamaré', 'Logone-et-Chari', 'Mayo-Danay', 'Mayo-Kani',
        'Mayo-Sava', 'Mayo-Tsanaga'
    ],
    'littoral': [
        'Moungo', 'Nkam', 'Sanaga-Maritime', 'Wouri'
    ],
    'nord': [
        'Bénoué', 'Faro', 'Mayo-Louti', 'Mayo-Rey'
    ],
    'nord_ouest': [
        'Boyo', 'Bui', 'Donga-Mantung', 'Menchum', 'Mezam',
        'Momo', 'Ngo-Ketunjia'
    ],
    'ouest': [
        'Bamboutos', 'Haut-Nkam', 'Hauts-Plateaux', 'Koung-Khi',
        'Menoua', 'Mifi', 'Ndé', 'Noun'
    ],
    'sud': [
        'Dja-et-Lobo', 'Mvila', 'Océan', 'Vallée-du-Ntem'
    ],
    'sud_ouest': [
        'Fako', 'Koupé-Manengouba', 'Lebialem', 'Manyu', 'Meme', 'Ndian'
    ]
}


# ===================================================================
# LISTES DE CLASSIFICATION DES HABILITATIONS
# MISE À JOUR COMPLÈTE selon matrice PDF avec tous les nouveaux rôles
# ===================================================================

# Habilitations qui DOIVENT être affectées à une station de PESAGE
HABILITATIONS_PESAGE = [
    'chef_station_pesage',      # Chef de Station Pesage (nouveau nom)
    'regisseur_pesage',         # Régisseur de Station Pesage
    'chef_equipe_pesage',       # Chef d'Équipe Pesage
    # Anciens noms pour compatibilité
    'chef_pesage',
]

# Habilitations qui DOIVENT être affectées à un poste de PÉAGE
HABILITATIONS_PEAGE = [
    'chef_peage',               # Chef de Poste Péage
    'agent_inventaire',         # Agent Inventaire
]

# Habilitations qui peuvent accéder à TOUS les postes (poste optionnel)
# MISE À JOUR COMPLÈTE: Ajout de tous les nouveaux rôles CISOP et services
HABILITATIONS_MULTI_POSTES = [
    # Administrateurs
    'admin_principal',          # Administrateur Principal
    'coord_psrr',               # Coordonnateur PSRR
    
    # Services centraux
    'serv_info',                # Service Informatique
    'serv_emission',            # Service Émission et Recouvrement
    'chef_ag',                  # Chef Service Affaires Générales
    'serv_controle',            # Service Contrôle et Validation (NOUVEAU)
    'serv_ordre',               # Service Ordre/Secrétariat (NOUVEAU)
    'imprimerie',               # Imprimerie Nationale
    
    # CISOP (NOUVEAUX)
    'cisop_peage',              # CISOP Péage
    'cisop_pesage',             # CISOP Pesage
    
    # Autres rôles multi-postes
    'focal_regional',           # Point Focal Régional
    'chef_service',             # Chef de Service
    'regisseur',                # Régisseur Central
    'comptable_mat',            # Comptable Matières
    
    # Anciens noms conservés pour rétrocompatibilité
    'chef_ordre',               # Alias -> serv_ordre
    'chef_controle',            # Alias -> serv_controle
]

# Liste complète de toutes les habilitations reconnues
TOUTES_HABILITATIONS = (
    HABILITATIONS_PESAGE + 
    HABILITATIONS_PEAGE + 
    HABILITATIONS_MULTI_POSTES
)


# ===================================================================
# FONCTIONS UTILITAIRES DE VALIDATION
# ===================================================================

def clean_habilitation_poste(habilitation, poste):
    """
    Fonction de validation réutilisable pour la cohérence habilitation/poste.
    Retourne None si valide, sinon retourne le message d'erreur.
    
    Usage dans clean():
        error = clean_habilitation_poste(habilitation, poste)
        if error:
            raise ValidationError({'poste_affectation': error})
    """
    if not habilitation:
        return None
    
    # Normaliser l'habilitation (gérer les alias)
    habilitation_normalisee = _normaliser_habilitation(habilitation)
    
    # Rôles pesage → station pesage obligatoire
    if habilitation_normalisee in HABILITATIONS_PESAGE:
        if not poste:
            return _(
                "Une station de pesage est obligatoire pour le rôle '%(role)s'."
            ) % {'role': _get_nom_habilitation(habilitation)}
        if poste.type != 'pesage':
            return _(
                "Le rôle '%(role)s' doit être affecté à une station de PESAGE, "
                "pas à un poste de péage."
            ) % {'role': _get_nom_habilitation(habilitation)}
    
    # Rôles péage → poste péage obligatoire
    elif habilitation_normalisee in HABILITATIONS_PEAGE:
        if not poste:
            return _(
                "Un poste de péage est obligatoire pour le rôle '%(role)s'."
            ) % {'role': _get_nom_habilitation(habilitation)}
        if poste.type != 'peage':
            return _(
                "Le rôle '%(role)s' doit être affecté à un poste de PÉAGE, "
                "pas à une station de pesage."
            ) % {'role': _get_nom_habilitation(habilitation)}
    
    # Rôles multi-postes → poste optionnel, pas de contrainte de type
    # (validation passe)
    
    return None


def _normaliser_habilitation(habilitation):
    """
    Normalise les alias d'habilitation vers leur forme canonique.
    """
    alias_map = {
        'chef_ordre': 'serv_ordre',
        'chef_controle': 'serv_controle',
        'chef_pesage': 'chef_station_pesage',
    }
    return alias_map.get(habilitation, habilitation)


def _get_nom_habilitation(habilitation):
    """
    Retourne le nom lisible d'une habilitation.
    """
    try:
        return dict(Habilitation.choices).get(habilitation, habilitation)
    except:
        return habilitation


def get_postes_pour_habilitation(habilitation):
    """
    Retourne le queryset de postes approprié selon l'habilitation.
    Utile pour le filtrage dynamique des champs de formulaire.
    """
    habilitation_norm = _normaliser_habilitation(habilitation)
    
    if habilitation_norm in HABILITATIONS_PESAGE:
        return Poste.objects.filter(is_active=True, type='pesage').order_by('nom')
    elif habilitation_norm in HABILITATIONS_PEAGE:
        return Poste.objects.filter(is_active=True, type='peage').order_by('nom')
    else:
        # Multi-postes ou rôle inconnu: tous les postes
        return Poste.objects.filter(is_active=True).order_by('type', 'nom')


def habilitation_requiert_poste(habilitation):
    """
    Retourne True si l'habilitation nécessite obligatoirement un poste.
    """
    habilitation_norm = _normaliser_habilitation(habilitation)
    return habilitation_norm in HABILITATIONS_PESAGE or habilitation_norm in HABILITATIONS_PEAGE


def get_type_poste_requis(habilitation):
    """
    Retourne le type de poste requis pour une habilitation.
    Retourne 'pesage', 'peage', ou None si pas de contrainte.
    """
    habilitation_norm = _normaliser_habilitation(habilitation)
    
    if habilitation_norm in HABILITATIONS_PESAGE:
        return 'pesage'
    elif habilitation_norm in HABILITATIONS_PEAGE:
        return 'peage'
    return None


def est_habilitation_admin(habilitation):
    """
    Vérifie si l'habilitation a des privilèges administrateur.
    """
    return habilitation in [
        'admin_principal',
        'coord_psrr',
        'serv_info',
    ]


def est_habilitation_centrale(habilitation):
    """
    Vérifie si l'habilitation est un service central (accès étendu).
    """
    return habilitation in [
        'admin_principal',
        'coord_psrr',
        'serv_info',
        'serv_emission',
        'chef_ag',
        'serv_controle',
        'serv_ordre',
        'cisop_peage',
        'cisop_pesage',
    ]


# ===================================================================
# FORMULAIRE POSTE
# ===================================================================

class PosteForm(forms.ModelForm):
    """Formulaire pour la création/modification de postes"""
    
    class Meta:
        model = Poste
        fields = [
            'code', 'nom', 'type', 'region', 'departement',
            'axe_routier', 'latitude', 'longitude', 'description',
            'is_active', 'nouveau'
        ]
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: PG001 ou PS001',
                'style': 'text-transform: uppercase;'
            }),
            'nom': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Péage de Yaoundé-Nord'
            }),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'region': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_region',
            }),
            'departement': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_departement',
            }),
            'axe_routier': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Yaoundé-Douala'
            }),
            'latitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001',
                'placeholder': 'Ex: 3.848034'
            }),
            'longitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001',
                'placeholder': 'Ex: 11.502134'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Description détaillée du poste...'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'nouveau': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filtrer les départements selon la région sélectionnée
        if self.instance and self.instance.pk and self.instance.region:
            self.fields['departement'].queryset = Departement.objects.filter(
                region=self.instance.region
            )
        else:
            self.fields['departement'].queryset = Departement.objects.none()
    
    def clean_code(self):
        """Valider et formater le code du poste"""
        code = self.cleaned_data.get('code')
        if code:
            code = code.upper().strip()
            
            # Vérifier l'unicité sauf pour l'instance actuelle
            qs = Poste.objects.filter(code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(_("Ce code de poste existe déjà."))
        
        return code


# ===================================================================
# FORMULAIRE DE CONNEXION
# ===================================================================

class CustomLoginForm(AuthenticationForm):
    """
    Formulaire de connexion personnalisé avec messages d'erreur détaillés
    """
    
    username = forms.CharField(
        label=_("Matricule"),
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: 1052105M',
            'autofocus': True,
            'required': True,
            'style': 'text-transform: uppercase;'
        })
    )
    
    password = forms.CharField(
        label=_("Mot de passe"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mot de passe',
            'required': True
        })
    )
    
    def clean(self):
        """Validation personnalisée avec messages spécifiques"""
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        
        if username and password:
            # Convertir le matricule en majuscules
            username = username.upper().strip()
            
            # Vérifier d'abord si l'utilisateur existe
            try:
                user = UtilisateurSUPPER.objects.get(username=username)
                
                # L'utilisateur existe, vérifier le mot de passe
                self.user_cache = authenticate(
                    self.request, 
                    username=username, 
                    password=password
                )
                
                if self.user_cache is None:
                    logger.warning(f"Tentative de connexion échouée pour {username} - Mot de passe incorrect")
                    raise ValidationError(
                        _("Mot de passe incorrect. Veuillez vérifier votre mot de passe et réessayer."),
                        code='invalid_password',
                    )
                elif not self.user_cache.is_active:
                    logger.warning(f"Tentative de connexion avec compte désactivé: {username}")
                    raise ValidationError(
                        _("Ce compte a été désactivé. Contactez un administrateur."),
                        code='inactive',
                    )
                    
            except UtilisateurSUPPER.DoesNotExist:
                logger.warning(f"Tentative de connexion avec matricule inexistant: {username}")
                raise ValidationError(
                    _("Le matricule '%(username)s' n'existe pas dans le système. Vérifiez votre matricule."),
                    code='invalid_username',
                    params={'username': username},
                )
        
        return self.cleaned_data
    
    def confirm_login_allowed(self, user):
        """Vérifications supplémentaires après authentification réussie"""
        if not user.is_active:
            raise ValidationError(
                _("Ce compte est désactivé."),
                code='inactive',
            )


# ===================================================================
# FORMULAIRES DE CRÉATION D'UTILISATEUR
# ===================================================================

class UtilisateurCreationForm(UserCreationForm):
    """Formulaire de création d'utilisateur SUPPER (simple)"""
    
    nom_complet = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nom et prénom(s) complets'
        }),
        label=_('Nom complet')
    )
    
    telephone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+237XXXXXXXXX'
        }),
        label=_('Numéro de téléphone')
    )
    
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'email@exemple.cm'
        }),
        label=_('Email (optionnel)')
    )
    
    poste_affectation = forms.ModelChoiceField(
        queryset=Poste.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label=_("Poste d'affectation")
    )
    
    class Meta:
        model = UtilisateurSUPPER
        fields = ('username', 'nom_complet', 'telephone', 'email', 
                 'habilitation', 'poste_affectation', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Matricule (ex: 1052105M)',
                'style': 'text-transform: uppercase;'
            }),
            'habilitation': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            username = username.upper().strip()
            if UtilisateurSUPPER.objects.filter(username=username).exists():
                raise ValidationError(_('Ce matricule existe déjà.'))
        return username
    
    def clean(self):
        """Validation croisée habilitation <-> poste"""
        cleaned_data = super().clean()
        habilitation = cleaned_data.get('habilitation')
        poste = cleaned_data.get('poste_affectation')
        
        error = clean_habilitation_poste(habilitation, poste)
        if error:
            raise ValidationError({'poste_affectation': error})
        
        return cleaned_data


class UserCreateForm(forms.ModelForm):
    """
    Formulaire de création d'utilisateur avec filtrage dynamique des postes
    selon l'habilitation sélectionnée - Version complète pour admins
    """
    password = forms.CharField(
        label=_("Mot de passe"),
        initial='supper2025',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'value': 'supper2025'
        }),
        help_text=_("Mot de passe par défaut: supper2025")
    )
    
    class Meta:
        model = UtilisateurSUPPER
        fields = [
            'username',
            'nom_complet',
            'telephone',
            'email',
            'habilitation',
            'poste_affectation',
        ]
        
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: 1052105M',
                'style': 'text-transform: uppercase;'
            }),
            'nom_complet': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom et prénom(s)'
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: +237XXXXXXXXX'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@exemple.cm (optionnel)'
            }),
            'habilitation': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_habilitation',
            }),
            'poste_affectation': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_poste_affectation'
            }),
        }
        
        labels = {
            'username': _("Matricule"),
            'nom_complet': _("Nom complet"),
            'telephone': _("Téléphone"),
            'email': _("Email (optionnel)"),
            'habilitation': _("Rôle"),
            'poste_affectation': _("Poste d'affectation"),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Par défaut, afficher tous les postes actifs
        self.fields['poste_affectation'].queryset = Poste.objects.filter(
            is_active=True
        ).order_by('type', 'nom')
        
        self.fields['poste_affectation'].required = False
        self.fields['email'].required = False
    
    def clean_username(self):
        """Nettoyer et valider le matricule"""
        username = self.cleaned_data.get('username')
        if username:
            username = username.upper().strip()
            if UtilisateurSUPPER.objects.filter(username=username).exists():
                raise ValidationError(_("Ce matricule est déjà utilisé."))
        return username
    
    def clean_telephone(self):
        """Validation du numéro de téléphone camerounais"""
        telephone = self.cleaned_data.get('telephone')
        if telephone:
            telephone = telephone.replace(' ', '').replace('-', '')
            if not re.match(r'^(\+237)?[0-9]{8,9}$', telephone):
                raise ValidationError(
                    _("Format invalide. Utilisez le format: +237XXXXXXXXX ou XXXXXXXXX")
                )
        return telephone
    
    def clean(self):
        """Validation croisée habilitation <-> type de poste"""
        cleaned_data = super().clean()
        habilitation = cleaned_data.get('habilitation')
        poste = cleaned_data.get('poste_affectation')
        
        error = clean_habilitation_poste(habilitation, poste)
        if error:
            raise ValidationError({'poste_affectation': error})
        
        return cleaned_data
    
    def save(self, commit=True, created_by=None):
        """Créer l'utilisateur avec le mot de passe"""
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        
        if created_by:
            user.cree_par = created_by
        
        if commit:
            user.save()
            
        return user


# ===================================================================
# FORMULAIRES DE MODIFICATION D'UTILISATEUR
# ===================================================================

class UtilisateurChangeForm(UserChangeForm):
    """Formulaire de modification d'utilisateur SUPPER (simple)"""
    
    password = None  # Masquer le champ mot de passe
    
    class Meta:
        model = UtilisateurSUPPER
        fields = ('username', 'nom_complet', 'telephone', 'email', 
                 'habilitation', 'poste_affectation', 'is_active')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'readonly': True}),
            'nom_complet': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'habilitation': forms.Select(attrs={'class': 'form-select'}),
            'poste_affectation': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class UserUpdateForm(forms.ModelForm):
    """
    Formulaire de modification d'utilisateur avec validation croisée
    et toutes les permissions affichables (version complète)
    MISE À JOUR: Intégration de toutes les nouvelles permissions granulaires
    """
    
    class Meta:
        model = UtilisateurSUPPER
        fields = [
            # Informations de base
            'nom_complet', 
            'telephone', 
            'email', 
            'habilitation', 
            'poste_affectation',
            'is_active',
            
            # Permissions globales
            'acces_tous_postes',
            'peut_saisir_peage',
            'peut_saisir_pesage',
            'voir_recettes_potentielles',
            'voir_taux_deperdition',
            'voir_statistiques_globales',
            'peut_saisir_pour_autres_postes',
            
            # Anciennes permissions modules (rétrocompatibilité)
            'peut_gerer_peage',
            'peut_gerer_pesage',
            'peut_gerer_personnel',
            'peut_gerer_budget',
            'peut_gerer_inventaire',
            'peut_gerer_archives',
            'peut_gerer_stocks_psrr',
            'peut_gerer_stock_info',
            
            # ===== NOUVELLES PERMISSIONS INVENTAIRES =====
            'peut_saisir_inventaire_normal',
            'peut_saisir_inventaire_admin',
            'peut_programmer_inventaire',
            'peut_voir_programmation_active',
            'peut_desactiver_programmation',
            'peut_voir_programmation_desactivee',
            'peut_voir_liste_inventaires',
            'peut_voir_liste_inventaires_admin',
            'peut_voir_jours_impertinents',
            'peut_voir_stats_deperdition',
            
            # ===== NOUVELLES PERMISSIONS RECETTES PÉAGE =====
            'peut_saisir_recette_peage',
            'peut_voir_liste_recettes_peage',
            'peut_voir_stats_recettes_peage',
            'peut_importer_recettes_peage',
            'peut_voir_evolution_peage',
            'peut_voir_objectifs_peage',
            
            # ===== NOUVELLES PERMISSIONS QUITTANCES PÉAGE =====
            'peut_saisir_quittance_peage',
            'peut_voir_liste_quittances_peage',
            'peut_comptabiliser_quittances_peage',
            
            # ===== NOUVELLES PERMISSIONS PESAGE =====
            'peut_voir_historique_vehicule_pesage',
            'peut_saisir_amende',
            'peut_saisir_pesee_jour',
            'peut_voir_objectifs_pesage',
            'peut_valider_paiement_amende',
            'peut_lister_amendes',
            'peut_saisir_quittance_pesage',
            'peut_comptabiliser_quittances_pesage',
            'peut_voir_liste_quittancements_pesage',
            'peut_voir_historique_pesees',
            'peut_voir_recettes_pesage',
            'peut_voir_stats_pesage',
            
            # ===== NOUVELLES PERMISSIONS STOCK PÉAGE =====
            'peut_charger_stock_peage',
            'peut_voir_liste_stocks_peage',
            'peut_voir_stock_date_peage',
            'peut_transferer_stock_peage',
            'peut_voir_tracabilite_tickets',
            'peut_voir_bordereaux_peage',
            'peut_voir_mon_stock_peage',
            'peut_voir_historique_stock_peage',
            'peut_simuler_commandes_peage',
            
            # ===== NOUVELLES PERMISSIONS GESTION =====
            'peut_gerer_postes',
            'peut_ajouter_poste',
            'peut_creer_poste_masse',
            'peut_gerer_utilisateurs',
            'peut_creer_utilisateur',
            'peut_voir_journal_audit',
            
            # ===== NOUVELLES PERMISSIONS RAPPORTS =====
            'peut_voir_rapports_defaillants_peage',
            'peut_voir_rapports_defaillants_pesage',
            'peut_voir_rapport_inventaires',
            'peut_voir_classement_peage_rendement',
            'peut_voir_classement_station_pesage',
            'peut_voir_classement_peage_deperdition',
            'peut_voir_classement_agents_inventaire',
            
            # ===== NOUVELLES PERMISSIONS AUTRES =====
            'peut_parametrage_global',
            'peut_voir_compte_emploi',
            'peut_voir_pv_confrontation',
            'peut_authentifier_document',
            'peut_voir_tous_postes',
        ]
        
        widgets = {
            'nom_complet': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom et prénom(s) complets'
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: +237XXXXXXXXX'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@exemple.cm'
            }),
            'habilitation': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_habilitation',
            }),
            'poste_affectation': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_poste_affectation'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'acces_tous_postes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_saisir_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_saisir_pesage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'voir_recettes_potentielles': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'voir_taux_deperdition': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'voir_statistiques_globales': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_saisir_pour_autres_postes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_gerer_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_gerer_pesage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_gerer_personnel': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_gerer_budget': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_gerer_inventaire': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_gerer_archives': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_gerer_stocks_psrr': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_gerer_stock_info': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            # Nouvelles permissions - Inventaires
            'peut_saisir_inventaire_normal': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_saisir_inventaire_admin': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_programmer_inventaire': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_programmation_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_desactiver_programmation': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_programmation_desactivee': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_liste_inventaires': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_liste_inventaires_admin': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_jours_impertinents': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_stats_deperdition': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            # Nouvelles permissions - Recettes péage
            'peut_saisir_recette_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_liste_recettes_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_stats_recettes_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_importer_recettes_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_evolution_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_objectifs_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            # Nouvelles permissions - Quittances péage
            'peut_saisir_quittance_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_liste_quittances_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_comptabiliser_quittances_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            # Nouvelles permissions - Pesage
            'peut_voir_historique_vehicule_pesage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_saisir_amende': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_saisir_pesee_jour': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_objectifs_pesage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_valider_paiement_amende': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_lister_amendes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_saisir_quittance_pesage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_comptabiliser_quittances_pesage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_liste_quittancements_pesage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_historique_pesees': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_recettes_pesage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_stats_pesage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            # Nouvelles permissions - Stock péage
            'peut_charger_stock_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_liste_stocks_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_stock_date_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_transferer_stock_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_tracabilite_tickets': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_bordereaux_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_mon_stock_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_historique_stock_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_simuler_commandes_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            # Nouvelles permissions - Gestion
            'peut_gerer_postes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_ajouter_poste': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_creer_poste_masse': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_gerer_utilisateurs': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_creer_utilisateur': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_journal_audit': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            # Nouvelles permissions - Rapports
            'peut_voir_rapports_defaillants_peage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_rapports_defaillants_pesage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_rapport_inventaires': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_classement_peage_rendement': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_classement_station_pesage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_classement_peage_deperdition': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_classement_agents_inventaire': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            # Nouvelles permissions - Autres
            'peut_parametrage_global': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_compte_emploi': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_pv_confrontation': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_authentifier_document': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'peut_voir_tous_postes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        
        labels = {
            'nom_complet': _("Nom complet"),
            'telephone': _("Téléphone"),
            'email': _("Email (optionnel)"),
            'habilitation': _("Rôle"),
            'poste_affectation': _("Poste d'affectation"),
            'is_active': _("Compte actif"),
            'acces_tous_postes': _("Accès à tous les postes"),
            'peut_saisir_peage': _("Peut saisir données péage"),
            'peut_saisir_pesage': _("Peut saisir données pesage"),
            'voir_recettes_potentielles': _("Voir recettes potentielles"),
            'voir_taux_deperdition': _("Voir taux déperdition"),
            'voir_statistiques_globales': _("Voir statistiques globales"),
            'peut_saisir_pour_autres_postes': _("Saisir pour autres postes"),
            'peut_gerer_peage': _("Gérer le péage"),
            'peut_gerer_pesage': _("Gérer le pesage"),
            'peut_gerer_personnel': _("Gérer le personnel"),
            'peut_gerer_budget': _("Gérer le budget"),
            'peut_gerer_inventaire': _("Gérer l'inventaire"),
            'peut_gerer_archives': _("Gérer les archives"),
            'peut_gerer_stocks_psrr': _("Gérer les stocks PSRR"),
            'peut_gerer_stock_info': _("Gérer le stock informatique"),
            # Labels nouvelles permissions - Inventaires
            'peut_saisir_inventaire_normal': _("Saisir inventaire normal"),
            'peut_saisir_inventaire_admin': _("Saisir inventaire administratif"),
            'peut_programmer_inventaire': _("Programmer inventaire"),
            'peut_voir_programmation_active': _("Voir programmation active"),
            'peut_desactiver_programmation': _("Désactiver programmation"),
            'peut_voir_programmation_desactivee': _("Voir programmations désactivées"),
            'peut_voir_liste_inventaires': _("Voir liste inventaires"),
            'peut_voir_liste_inventaires_admin': _("Voir liste inventaires admin"),
            'peut_voir_jours_impertinents': _("Voir jours impertinents"),
            'peut_voir_stats_deperdition': _("Voir stats déperdition"),
            # Labels nouvelles permissions - Recettes péage
            'peut_saisir_recette_peage': _("Saisir recette péage"),
            'peut_voir_liste_recettes_peage': _("Voir liste recettes péage"),
            'peut_voir_stats_recettes_peage': _("Voir stats recettes péage"),
            'peut_importer_recettes_peage': _("Importer recettes péage"),
            'peut_voir_evolution_peage': _("Voir évolution péage"),
            'peut_voir_objectifs_peage': _("Voir objectifs péage"),
            # Labels nouvelles permissions - Quittances péage
            'peut_saisir_quittance_peage': _("Saisir quittance péage"),
            'peut_voir_liste_quittances_peage': _("Voir liste quittances péage"),
            'peut_comptabiliser_quittances_peage': _("Comptabiliser quittances péage"),
            # Labels nouvelles permissions - Pesage
            'peut_voir_historique_vehicule_pesage': _("Voir historique véhicule pesage"),
            'peut_saisir_amende': _("Saisir amende"),
            'peut_saisir_pesee_jour': _("Saisir pesée du jour"),
            'peut_voir_objectifs_pesage': _("Voir objectifs pesage"),
            'peut_valider_paiement_amende': _("Valider paiement amende"),
            'peut_lister_amendes': _("Lister amendes"),
            'peut_saisir_quittance_pesage': _("Saisir quittance pesage"),
            'peut_comptabiliser_quittances_pesage': _("Comptabiliser quittances pesage"),
            'peut_voir_liste_quittancements_pesage': _("Voir liste quittancements pesage"),
            'peut_voir_historique_pesees': _("Voir historique pesées"),
            'peut_voir_recettes_pesage': _("Voir recettes pesage"),
            'peut_voir_stats_pesage': _("Voir stats pesage"),
            # Labels nouvelles permissions - Stock péage
            'peut_charger_stock_peage': _("Charger stock péage"),
            'peut_voir_liste_stocks_peage': _("Voir liste stocks péage"),
            'peut_voir_stock_date_peage': _("Voir stock à date péage"),
            'peut_transferer_stock_peage': _("Transférer stock péage"),
            'peut_voir_tracabilite_tickets': _("Voir traçabilité tickets"),
            'peut_voir_bordereaux_peage': _("Voir bordereaux péage"),
            'peut_voir_mon_stock_peage': _("Voir mon stock péage"),
            'peut_voir_historique_stock_peage': _("Voir historique stock péage"),
            'peut_simuler_commandes_peage': _("Simuler commandes péage"),
            # Labels nouvelles permissions - Gestion
            'peut_gerer_postes': _("Gérer les postes"),
            'peut_ajouter_poste': _("Ajouter un poste"),
            'peut_creer_poste_masse': _("Créer postes en masse"),
            'peut_gerer_utilisateurs': _("Gérer utilisateurs"),
            'peut_creer_utilisateur': _("Créer utilisateur"),
            'peut_voir_journal_audit': _("Voir journal audit"),
            # Labels nouvelles permissions - Rapports
            'peut_voir_rapports_defaillants_peage': _("Voir rapports défaillants péage"),
            'peut_voir_rapports_defaillants_pesage': _("Voir rapports défaillants pesage"),
            'peut_voir_rapport_inventaires': _("Voir rapport inventaires"),
            'peut_voir_classement_peage_rendement': _("Voir classement péage rendement"),
            'peut_voir_classement_station_pesage': _("Voir classement station pesage"),
            'peut_voir_classement_peage_deperdition': _("Voir classement péage déperdition"),
            'peut_voir_classement_agents_inventaire': _("Voir classement agents inventaire"),
            # Labels nouvelles permissions - Autres
            'peut_parametrage_global': _("Paramétrage global"),
            'peut_voir_compte_emploi': _("Voir compte d'emploi"),
            'peut_voir_pv_confrontation': _("Voir PV confrontation"),
            'peut_authentifier_document': _("Authentifier document"),
            'peut_voir_tous_postes': _("Voir tous les postes"),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['poste_affectation'].queryset = Poste.objects.filter(
            is_active=True
        ).order_by('type', 'nom')
        self.fields['poste_affectation'].required = False
        self.fields['email'].required = False
    
    def clean_telephone(self):
        """Validation du numéro de téléphone camerounais"""
        telephone = self.cleaned_data.get('telephone')
        if telephone:
            telephone = telephone.replace(' ', '').replace('-', '')
            if not re.match(r'^(\+237)?[0-9]{8,9}$', telephone):
                raise ValidationError(
                    _("Format invalide. Utilisez le format: +237XXXXXXXXX ou XXXXXXXXX")
                )
        return telephone
    
    def clean(self):
        """Validation croisée habilitation <-> type de poste"""
        cleaned_data = super().clean()
        habilitation = cleaned_data.get('habilitation')
        poste = cleaned_data.get('poste_affectation')
        
        error = clean_habilitation_poste(habilitation, poste)
        if error:
            raise ValidationError({'poste_affectation': error})
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    """
    Formulaire de modification d'utilisateur simplifié
    """
    class Meta:
        model = UtilisateurSUPPER
        fields = [
            'nom_complet',
            'telephone',
            'email',
            'habilitation',
            'poste_affectation',
            'is_active',
        ]
        
        widgets = {
            'nom_complet': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'habilitation': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_habilitation',
            }),
            'poste_affectation': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_poste_affectation'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['poste_affectation'].queryset = Poste.objects.filter(
            is_active=True
        ).order_by('type', 'nom')
        self.fields['poste_affectation'].required = False
        self.fields['email'].required = False
    
    def clean(self):
        """Validation croisée habilitation <-> type de poste"""
        cleaned_data = super().clean()
        habilitation = cleaned_data.get('habilitation')
        poste = cleaned_data.get('poste_affectation')
        
        error = clean_habilitation_poste(habilitation, poste)
        if error:
            raise ValidationError({'poste_affectation': error})
        
        return cleaned_data


# ===================================================================
# FORMULAIRE DE PROFIL UTILISATEUR
# ===================================================================

# ===================================================================
# FORMULAIRES POUR LA GESTION DU PROFIL UTILISATEUR
# À ajouter dans accounts/forms.py
# ===================================================================

from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from .models import UtilisateurSUPPER


class ProfileEditForm(forms.ModelForm):
    """
    Formulaire pour permettre à un utilisateur de modifier son propre profil.
    Seuls les champs autorisés sont modifiables (nom, téléphone, email, photo).
    """
    
    nom_complet = forms.CharField(
        max_length=150,
        label=_("Nom complet"),
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Ex: Jean DUPONT KAMGA'),
        }),
        help_text=_("Votre nom complet tel qu'il apparaîtra dans le système")
    )
    
    telephone = forms.CharField(
        max_length=20,
        label=_("Numéro de téléphone"),
        validators=[
            RegexValidator(
                regex=r'^\+?237?[0-9]{8,9}$',
                message=_("Format: +237XXXXXXXXX ou 6XXXXXXXX")
            )
        ],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+237 6XX XXX XXX',
        }),
        help_text=_("Votre numéro de téléphone au format camerounais")
    )
    
    email = forms.EmailField(
        required=False,
        label=_("Adresse email"),
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'exemple@email.com',
        }),
        help_text=_("Optionnel - Utilisé pour la récupération de mot de passe")
    )
    
    photo_profil = forms.ImageField(
        required=False,
        label=_("Photo de profil"),
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*',
        }),
        help_text=_("Formats acceptés : JPG, PNG. Taille maximale : 2 Mo")
    )
    
    class Meta:
        model = UtilisateurSUPPER
        fields = ['nom_complet', 'telephone', 'email', 'photo_profil']
    
    def clean_telephone(self):
        """Nettoie et valide le numéro de téléphone"""
        telephone = self.cleaned_data.get('telephone', '')
        
        # Supprimer les espaces
        telephone = telephone.replace(' ', '').replace('-', '')
        
        # Ajouter le préfixe +237 si absent
        if telephone.startswith('6') or telephone.startswith('2'):
            telephone = '+237' + telephone
        elif telephone.startswith('237'):
            telephone = '+' + telephone
        
        return telephone
    
    def clean_photo_profil(self):
        """Valide la photo de profil (taille et format)"""
        photo = self.cleaned_data.get('photo_profil')
        
        if photo:
            # Vérifier la taille (max 2 Mo)
            if photo.size > 2 * 1024 * 1024:
                raise forms.ValidationError(
                    _("La photo ne doit pas dépasser 2 Mo")
                )
            
            # Vérifier le type MIME
            content_type = getattr(photo, 'content_type', '')
            if content_type and not content_type.startswith('image/'):
                raise forms.ValidationError(
                    _("Le fichier doit être une image (JPG, PNG)")
                )
        
        return photo


class PasswordChangeForm(forms.Form):
    """
    Formulaire pour le changement de mot de passe par l'utilisateur.
    Validation simplifiée : minimum 4 caractères selon les specs SUPPER.
    """
    
    ancien_mot_de_passe = forms.CharField(
        label=_("Mot de passe actuel"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'current-password',
        }),
        help_text=_("Entrez votre mot de passe actuel")
    )
    
    nouveau_mot_de_passe = forms.CharField(
        min_length=4,
        label=_("Nouveau mot de passe"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
        }),
        help_text=_("Minimum 4 caractères")
    )
    
    confirmation_mot_de_passe = forms.CharField(
        min_length=4,
        label=_("Confirmer le nouveau mot de passe"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
        }),
        help_text=_("Répétez le nouveau mot de passe")
    )
    
    def __init__(self, *args, user=None, **kwargs):
        """Initialise le formulaire avec l'utilisateur"""
        self.user = user
        super().__init__(*args, **kwargs)
    
    def clean_ancien_mot_de_passe(self):
        """Vérifie que l'ancien mot de passe est correct"""
        ancien = self.cleaned_data.get('ancien_mot_de_passe')
        
        if self.user and not self.user.check_password(ancien):
            raise forms.ValidationError(
                _("Le mot de passe actuel est incorrect")
            )
        
        return ancien
    
    def clean(self):
        """Vérifie que les deux nouveaux mots de passe correspondent"""
        cleaned_data = super().clean()
        nouveau = cleaned_data.get('nouveau_mot_de_passe')
        confirmation = cleaned_data.get('confirmation_mot_de_passe')
        ancien = cleaned_data.get('ancien_mot_de_passe')
        
        if nouveau and confirmation:
            if nouveau != confirmation:
                raise forms.ValidationError(
                    _("Les deux mots de passe ne correspondent pas")
                )
            
            # Vérifier que le nouveau mot de passe est différent de l'ancien
            if ancien and nouveau == ancien:
                raise forms.ValidationError(
                    _("Le nouveau mot de passe doit être différent de l'ancien")
                )
        
        return cleaned_data


class PasswordResetForm(forms.Form):
    """
    Formulaire pour la réinitialisation de mot de passe par un administrateur.
    Permet de définir un nouveau mot de passe sans connaître l'ancien.
    """
    
    nouveau_mot_de_passe = forms.CharField(
        min_length=4,
        label=_("Nouveau mot de passe"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
        }),
        help_text=_("Minimum 4 caractères")
    )
    
    confirmation_mot_de_passe = forms.CharField(
        min_length=4,
        label=_("Confirmer le mot de passe"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
        }),
        help_text=_("Répétez le mot de passe")
    )
    
    def clean(self):
        """Vérifie que les deux mots de passe correspondent"""
        cleaned_data = super().clean()
        nouveau = cleaned_data.get('nouveau_mot_de_passe')
        confirmation = cleaned_data.get('confirmation_mot_de_passe')
        
        if nouveau and confirmation and nouveau != confirmation:
            raise forms.ValidationError(
                _("Les deux mots de passe ne correspondent pas")
            )
        
        return cleaned_data
# ===================================================================
# FORMULAIRE DE CRÉATION EN MASSE
# ===================================================================

class BulkUserCreateForm(forms.Form):
    """
    Formulaire pour la création en masse d'utilisateurs
    """
    
    poste_commun = forms.ModelChoiceField(
        queryset=Poste.objects.filter(is_active=True),
        label=_("Poste d'affectation commun"),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True
    )
    
    habilitation_commune = forms.ChoiceField(
        label=_("Habilitation commune"),
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial='agent_inventaire'
    )
    
    mot_de_passe_commun = forms.CharField(
        label=_("Mot de passe commun"),
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        help_text=_("Minimum 4 caractères - sera attribué à tous les utilisateurs créés")
    )
    
    utilisateurs_data = forms.CharField(
        label=_("Données des utilisateurs"),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 10,
            'placeholder': 'Matricule;Nom Complet;Téléphone;Email\nAGT001;Agent Un;+237600000001;agent1@supper.cm\nAGT002;Agent Deux;+237600000002;agent2@supper.cm'
        }),
        help_text=_("Format: Matricule;Nom Complet;Téléphone;Email (un par ligne)")
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['habilitation_commune'].choices = Habilitation.choices
    
    def clean_mot_de_passe_commun(self):
        """Valider le mot de passe"""
        password = self.cleaned_data.get('mot_de_passe_commun')
        if password and len(password) < 4:
            raise ValidationError(_("Le mot de passe doit contenir au moins 4 caractères."))
        return password
    
    def clean(self):
        """Validation croisée habilitation <-> type de poste"""
        cleaned_data = super().clean()
        habilitation = cleaned_data.get('habilitation_commune')
        poste = cleaned_data.get('poste_commun')
        
        error = clean_habilitation_poste(habilitation, poste)
        if error:
            raise ValidationError({'poste_commun': error})
        
        return cleaned_data
    
    def clean_utilisateurs_data(self):
        """Valider et parser les données des utilisateurs"""
        data = self.cleaned_data.get('utilisateurs_data')
        
        if not data:
            raise ValidationError(_("Les données des utilisateurs sont requises."))
        
        lignes = [ligne.strip() for ligne in data.split('\n') if ligne.strip()]
        
        if not lignes:
            raise ValidationError(_("Aucune donnée utilisateur valide trouvée."))
        
        utilisateurs_parsed = []
        matricules_vus = set()
        
        for i, ligne in enumerate(lignes, 1):
            parts = [part.strip() for part in ligne.split(';')]
            
            if len(parts) != 4:
                raise ValidationError(
                    _("Ligne %(num)d: Format invalide. Attendu: Matricule;Nom;Téléphone;Email") % {'num': i}
                )
            
            matricule, nom, telephone, email = parts
            
            # Valider matricule
            matricule = matricule.upper()
            
            if matricule in matricules_vus:
                raise ValidationError(
                    _("Ligne %(num)d: Matricule '%(matricule)s' en double") % {'num': i, 'matricule': matricule}
                )
            
            if UtilisateurSUPPER.objects.filter(username=matricule).exists():
                raise ValidationError(
                    _("Ligne %(num)d: Matricule '%(matricule)s' déjà existant") % {'num': i, 'matricule': matricule}
                )
            
            matricules_vus.add(matricule)
            
            # Valider téléphone
            if not re.match(r'^\+?237?[0-9]{8,9}$', telephone):
                raise ValidationError(
                    _("Ligne %(num)d: Numéro de téléphone '%(tel)s' invalide") % {'num': i, 'tel': telephone}
                )
            
            utilisateurs_parsed.append({
                'matricule': matricule,
                'nom_complet': nom,
                'telephone': telephone,
                'email': email if email else None
            })
        
        return utilisateurs_parsed
    
    def create_users(self, created_by=None):
        """Créer les utilisateurs en masse"""
        utilisateurs_data = self.cleaned_data['utilisateurs_data']
        poste = self.cleaned_data['poste_commun']
        habilitation = self.cleaned_data['habilitation_commune']
        password = self.cleaned_data['mot_de_passe_commun']
        
        users_created = []
        
        for user_data in utilisateurs_data:
            user = UtilisateurSUPPER.objects.create_user(
                username=user_data['matricule'],
                nom_complet=user_data['nom_complet'],
                telephone=user_data['telephone'],
                email=user_data['email'],
                password=password,
                poste_affectation=poste,
                habilitation=habilitation,
                cree_par=created_by
            )
            users_created.append(user)
        
        return users_created


# ===================================================================
# FORMULAIRE D'INVENTAIRE
# ===================================================================

class InventaireForm(forms.Form):
    """Formulaire pour la saisie d'inventaire"""
    
    poste = forms.ModelChoiceField(
        queryset=Poste.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            'class': 'form-select select-modern',
            'required': True
        }),
        label=_('Poste')
    )
    
    date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control select-modern',
            'type': 'date',
            'required': True
        }),
        label=_("Date de l'inventaire")
    )
    
    observations = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control select-modern',
            'rows': 3,
            'placeholder': 'Observations sur cet inventaire...'
        }),
        label=_('Observations')
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Créer les champs pour chaque période
        periodes = [
            '08h-09h', '09h-10h', '10h-11h', '11h-12h', '12h-13h',
            '13h-14h', '14h-15h', '15h-16h', '16h-17h', '17h-18h'
        ]
        
        for periode in periodes:
            field_name = f'vehicules_{periode.replace("h", "").replace("-", "_")}'
            self.fields[field_name] = forms.IntegerField(
                required=False,
                min_value=0,
                max_value=1000,
                widget=forms.NumberInput(attrs={
                    'class': 'periode-input-field',
                    'placeholder': '0',
                    'min': '0',
                    'max': '1000',
                    'data-periode': periode
                }),
                label=f'Véhicules {periode}'
            )


# ===================================================================
# FORMULAIRES DE RECHERCHE ET EXPORT
# ===================================================================

class RechercheUtilisateurForm(forms.Form):
    """Formulaire de recherche d'utilisateurs"""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Rechercher par nom, matricule...',
            'autocomplete': 'off'
        }),
        label=_('Recherche')
    )
    
    habilitation = forms.ChoiceField(
        required=False,
        choices=[('', 'Toutes les habilitations')],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label=_('Filtrer par habilitation')
    )
    
    poste = forms.ModelChoiceField(
        queryset=Poste.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label=_('Filtrer par poste')
    )
    
    is_active = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Tous'),
            ('True', 'Actifs seulement'),
            ('False', 'Inactifs seulement')
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label=_('Statut')
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [('', 'Toutes les habilitations')] + list(Habilitation.choices)
        self.fields['habilitation'].choices = choices


class ExportForm(forms.Form):
    """Formulaire pour les exports de données"""
    
    TYPE_EXPORT_CHOICES = [
        ('users', 'Utilisateurs'),
        ('postes', 'Postes'),
        ('inventaires', 'Inventaires'),
        ('recettes', 'Recettes'),
        ('audit', "Journal d'audit")
    ]
    
    FORMAT_CHOICES = [
        ('csv', 'CSV'),
        ('excel', 'Excel'),
        ('pdf', 'PDF')
    ]
    
    type_export = forms.ChoiceField(
        choices=TYPE_EXPORT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label=_('Type de données')
    )
    
    format_export = forms.ChoiceField(
        choices=FORMAT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label=_('Format de fichier')
    )
    
    date_debut = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label=_('Date de début (optionnel)')
    )
    
    date_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label=_('Date de fin (optionnel)')
    )
    
    postes = forms.ModelMultipleChoiceField(
        queryset=Poste.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label=_('Postes spécifiques (optionnel)')
    )


# ===================================================================
# FORMULAIRE DE PERMISSIONS GROUPÉES
# Pour faciliter l'attribution de permissions par catégorie
# ===================================================================

class PermissionsGroupeForm(forms.Form):
    """
    Formulaire pour attribuer des groupes de permissions
    basé sur les catégories fonctionnelles
    """
    
    # Groupes de permissions
    GROUPE_INVENTAIRE = forms.BooleanField(
        required=False,
        label=_("Toutes les permissions Inventaires"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input groupe-check',
            'data-groupe': 'inventaire'
        })
    )
    
    GROUPE_RECETTES_PEAGE = forms.BooleanField(
        required=False,
        label=_("Toutes les permissions Recettes Péage"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input groupe-check',
            'data-groupe': 'recettes_peage'
        })
    )
    
    GROUPE_QUITTANCES_PEAGE = forms.BooleanField(
        required=False,
        label=_("Toutes les permissions Quittances Péage"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input groupe-check',
            'data-groupe': 'quittances_peage'
        })
    )
    
    GROUPE_PESAGE = forms.BooleanField(
        required=False,
        label=_("Toutes les permissions Pesage"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input groupe-check',
            'data-groupe': 'pesage'
        })
    )
    
    GROUPE_STOCK_PEAGE = forms.BooleanField(
        required=False,
        label=_("Toutes les permissions Stock Péage"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input groupe-check',
            'data-groupe': 'stock_peage'
        })
    )
    
    GROUPE_GESTION = forms.BooleanField(
        required=False,
        label=_("Toutes les permissions Gestion"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input groupe-check',
            'data-groupe': 'gestion'
        })
    )
    
    GROUPE_RAPPORTS = forms.BooleanField(
        required=False,
        label=_("Toutes les permissions Rapports"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input groupe-check',
            'data-groupe': 'rapports'
        })
    )


# ===================================================================
# JAVASCRIPT DE FILTRAGE DYNAMIQUE
# À inclure dans les templates qui utilisent les formulaires utilisateur
# MISE À JOUR avec tous les nouveaux rôles
# ===================================================================

FILTRAGE_POSTES_JS = """
<script>
// Configuration des habilitations par type de poste - MISE À JOUR COMPLÈTE
const HABILITATIONS_PESAGE = [
    'chef_station_pesage', 
    'regisseur_pesage', 
    'chef_equipe_pesage',
    'chef_pesage'  // ancien nom pour compatibilité
];

const HABILITATIONS_PEAGE = [
    'chef_peage', 
    'agent_inventaire'
];

const HABILITATIONS_MULTI = [
    // Administrateurs
    'admin_principal', 
    'coord_psrr', 
    
    // Services centraux
    'serv_info', 
    'serv_emission',
    'chef_ag', 
    'serv_controle',    // NOUVEAU
    'serv_ordre',       // NOUVEAU
    'imprimerie',
    
    // CISOP (NOUVEAUX)
    'cisop_peage',
    'cisop_pesage',
    
    // Autres rôles multi-postes
    'focal_regional', 
    'chef_service',
    'regisseur', 
    'comptable_mat', 
    
    // Anciens noms pour compatibilité
    'chef_ordre', 
    'chef_controle'
];

// Stocker toutes les options de postes au chargement
let allPostesOptions = [];

document.addEventListener('DOMContentLoaded', function() {
    const habilitationSelect = document.getElementById('id_habilitation');
    const posteSelect = document.getElementById('id_poste_affectation');
    
    if (!habilitationSelect || !posteSelect) return;
    
    // Sauvegarder toutes les options avec leur type
    allPostesOptions = Array.from(posteSelect.options).map(opt => ({
        value: opt.value,
        text: opt.text,
        type: opt.dataset.type || opt.text.toLowerCase().includes('pesage') ? 'pesage' : 'peage'
    }));
    
    // Fonction de filtrage
    function filterPostes() {
        const habilitation = habilitationSelect.value;
        const currentValue = posteSelect.value;
        
        // Vider le select
        posteSelect.innerHTML = '<option value="">---------</option>';
        
        // Déterminer le filtre et si le poste est requis
        let filterType = null;
        let isRequired = false;
        let helpText = '';
        
        if (HABILITATIONS_PESAGE.includes(habilitation)) {
            filterType = 'pesage';
            isRequired = true;
            helpText = 'Station de pesage obligatoire pour ce rôle';
        } else if (HABILITATIONS_PEAGE.includes(habilitation)) {
            filterType = 'peage';
            isRequired = true;
            helpText = 'Poste de péage obligatoire pour ce rôle';
        } else if (HABILITATIONS_MULTI.includes(habilitation)) {
            helpText = 'Poste optionnel - accès multi-postes disponible';
        }
        
        // Ajouter les options filtrées
        allPostesOptions.forEach(opt => {
            if (!opt.value) return; // Ignorer l'option vide
            
            if (!filterType || opt.type === filterType) {
                const option = document.createElement('option');
                option.value = opt.value;
                option.text = opt.text;
                option.dataset.type = opt.type;
                if (opt.value === currentValue) option.selected = true;
                posteSelect.appendChild(option);
            }
        });
        
        // Mettre à jour l'indicateur required sur le label
        const label = document.querySelector('label[for="id_poste_affectation"]');
        if (label) {
            // Nettoyer le label
            let labelText = label.textContent.replace(' *', '').replace(' (obligatoire)', '');
            
            if (isRequired) {
                label.classList.add('required');
                label.textContent = labelText + ' *';
            } else {
                label.classList.remove('required');
                label.textContent = labelText;
            }
        }
        
        // Afficher/mettre à jour le texte d'aide
        let helpElement = posteSelect.parentElement.querySelector('.form-text.habilitation-help');
        if (!helpElement && helpText) {
            helpElement = document.createElement('small');
            helpElement.className = 'form-text text-muted habilitation-help';
            posteSelect.parentElement.appendChild(helpElement);
        }
        if (helpElement) {
            helpElement.textContent = helpText;
            helpElement.style.display = helpText ? 'block' : 'none';
        }
        
        // Changer la couleur du cadre selon le type requis
        if (filterType === 'pesage') {
            posteSelect.style.borderColor = '#28a745';  // Vert pour pesage
        } else if (filterType === 'peage') {
            posteSelect.style.borderColor = '#007bff';  // Bleu pour péage
        } else {
            posteSelect.style.borderColor = '';  // Couleur par défaut
        }
    }
    
    // Écouter les changements
    habilitationSelect.addEventListener('change', filterPostes);
    
    // Appliquer le filtre initial
    filterPostes();
});

// Fonction utilitaire pour vérifier si un poste est requis
function posteRequis(habilitation) {
    return HABILITATIONS_PESAGE.includes(habilitation) || 
           HABILITATIONS_PEAGE.includes(habilitation);
}

// Fonction pour obtenir le type de poste requis
function getTypePosteRequis(habilitation) {
    if (HABILITATIONS_PESAGE.includes(habilitation)) return 'pesage';
    if (HABILITATIONS_PEAGE.includes(habilitation)) return 'peage';
    return null;
}
</script>
"""


# ===================================================================
# CSS POUR LES GROUPES DE PERMISSIONS
# À inclure dans les templates de modification d'utilisateur
# ===================================================================

PERMISSIONS_CSS = """
<style>
/* Styles pour les groupes de permissions */
.permissions-section {
    margin-bottom: 1.5rem;
    padding: 1rem;
    border: 1px solid #dee2e6;
    border-radius: 0.375rem;
    background-color: #f8f9fa;
}

.permissions-section h5 {
    color: #495057;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #6f42c1;
}

.permissions-section .form-check {
    margin-bottom: 0.5rem;
}

.permissions-section .form-check-label {
    font-size: 0.9rem;
}

/* Groupe de permissions header */
.groupe-check {
    transform: scale(1.2);
}

.groupe-header {
    background-color: #6f42c1;
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 0.25rem;
    margin-bottom: 0.75rem;
}

/* Indicateurs de rôle requis */
.required::after {
    content: ' *';
    color: #dc3545;
}

/* Info-bulle pour les types de postes */
.habilitation-help {
    font-style: italic;
    margin-top: 0.25rem;
}

/* Catégories de permissions */
.perm-category-inventaire { border-left: 4px solid #28a745; }
.perm-category-peage { border-left: 4px solid #007bff; }
.perm-category-pesage { border-left: 4px solid #fd7e14; }
.perm-category-stock { border-left: 4px solid #6c757d; }
.perm-category-gestion { border-left: 4px solid #dc3545; }
.perm-category-rapports { border-left: 4px solid #17a2b8; }
.perm-category-autres { border-left: 4px solid #6f42c1; }
</style>
"""