# ===================================================================
# accounts/forms.py - Formulaires pour l'application accounts SUPPER
# Version harmonisée finale - Correction des erreurs et optimisations
# ===================================================================

from django import forms
from django.contrib.auth.views import LoginView
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm, PasswordChangeForm as DjangoPasswordChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import authenticate
from .models import UtilisateurSUPPER, Poste
import re

# Créer/Modifier le fichier : Supper/accounts/forms.py
from django import forms
from .models import Poste, UtilisateurSUPPER

# Dictionnaire des départements par région du Cameroun
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

class PosteForm(forms.ModelForm):
    """Formulaire personnalisé pour la création/modification de postes"""
    
    departement = forms.ChoiceField(
        choices=[],
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_departement'
        })
    )
    
    class Meta:
        model = Poste
        fields = '__all__'
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'type_poste': forms.Select(attrs={'class': 'form-control'}),
            'localisation': forms.TextInput(attrs={'class': 'form-control'}),
            'region': forms.Select(attrs={
                'class': 'form-control',
                'id': 'id_region',
                'onchange': 'updateDepartements()'
            }),
            'arrondissement': forms.TextInput(attrs={'class': 'form-control'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control'}),
            'actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'date_ouverture': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'observations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Initialiser les départements basés sur la région
        if self.instance and self.instance.region:
            region = self.instance.region
            if region in DEPARTEMENTS_CAMEROUN:
                departements = DEPARTEMENTS_CAMEROUN[region]
                self.fields['departement'].choices = [
                    (dept, dept) for dept in departements
                ]
                
        # Si c'est une nouvelle instance, initialiser avec les départements du Centre
        elif not self.instance.pk:
            departements = DEPARTEMENTS_CAMEROUN.get('centre', [])
            self.fields['departement'].choices = [
                ('', '--- Sélectionner un département ---')
            ] + [(dept, dept) for dept in departements]


# Modifier le fichier : Supper/accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import UtilisateurSUPPER, Poste, JournalAudit, NotificationUtilisateur
from .forms import PosteForm

# @admin.register(Poste)
# class PosteAdmin(admin.ModelAdmin):
#     form = PosteForm
    
#     list_display = [
#         'nom', 'code', 'type', 
#         'region', 'departement', 'actif_status'
#     ]
#     list_filter = ['type', 'region', 'is_active']
#     search_fields = ['nom', 'code', 'localisation']
#     ordering = ['region', 'nom']
    
#     fieldsets = (
#         ('Informations générales', {
#             'fields': ('nom', 'code', 'type')
#         }),
#         ('Localisation', {
#             'fields': ('region', 'departement', 'arrondissement', 'localisation')
#         }),
#         ('Coordonnées GPS', {
#             'fields': ('latitude', 'longitude'),
#             'classes': ('collapse',)
#         }),
#         ('Informations complémentaires', {
#             'fields': ('actif', 'date_ouverture', 'observations')
#         }),
#     )
    
#     def type_poste_colored(self, obj):
#         colors = {
#             'peage': 'success',
#             'pesage': 'info'
#         }
#         color = colors.get(obj.type_poste, 'secondary')
#         return format_html(
#             '<span class="badge bg-{}">{}</span>',
#             color, obj.get_type_poste_display()
#         )
#     type_poste_colored.short_description = 'Type'
    
#     def actif_status(self, obj):
#         if obj.is_active:
#             return format_html(
#                 '<span class="badge bg-success">Actif</span>'
#             )
#         return format_html(
#             '<span class="badge bg-danger">Inactif</span>'
#         )
#     actif_status.short_description = 'Statut'
    
#     class Media:
#         js = ('admin/js/region_departement.js',)

class CustomLoginForm(LoginView):
    """
    Formulaire de connexion personnalisé pour SUPPER
    CORRIGÉ : Hérite d'AuthenticationForm pour compatibilité avec LoginView
    """
    
    username = forms.CharField(
        label=_("Matricule"),
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': _('Votre matricule'),
            'autofocus': True,
            'autocomplete': 'username',
            'style': 'text-transform: uppercase;'
        }),
        help_text=_("Saisissez votre matricule (ex: ADM001)")
    )
    
    password = forms.CharField(
        label=_("Mot de passe"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': _('Votre mot de passe'),
            'autocomplete': 'current-password',
        })
    )
    
    remember_me = forms.BooleanField(
        label=_("Se souvenir de moi"),
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        })
    )
    
    class Meta:
        model = UtilisateurSUPPER
        fields = ['username', 'password', 'remember_me']
    
    def __init__(self, request=None, *args, **kwargs):
        """
        CORRECTION : Accepter le paramètre request de LoginView
        """
        super().__init__(request, *args, **kwargs)
    
    def clean_username(self):
        """Nettoyer et valider le matricule"""
        username = self.cleaned_data.get('username')
        if username:
            # Convertir en majuscules
            username = username.upper().strip()
            
            # Valider le format
            if not re.match(r'^[A-Z0-9]{3,20}$', username):
                raise ValidationError(
                    _("Le matricule doit contenir entre 3 et 20 caractères alphanumériques.")
                )
        
        return username
    
    def confirm_login_allowed(self, user):
        """
        Vérifications supplémentaires après authentification
        """
        super().confirm_login_allowed(user)
        
        # Vérifier que l'utilisateur est actif dans SUPPER
        if not user.is_active:
            raise ValidationError(
                _("Ce compte a été désactivé. Contactez votre administrateur."),
                code='inactive',
            )


class UtilisateurCreationForm(UserCreationForm):
    """Formulaire de création d'utilisateur SUPPER"""
    
    nom_complet = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nom et prénom(s) complets'
        }),
        label='Nom complet'
    )
    
    telephone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+237XXXXXXXXX'
        }),
        label='Numéro de téléphone'
    )
    
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'email@exemple.com'
        }),
        label='Email (optionnel)'
    )
    
    poste_affectation = forms.ModelChoiceField(
        queryset=Poste.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Poste d\'affectation'
    )
    
    class Meta:
        model = UtilisateurSUPPER
        fields = ('username', 'nom_complet', 'telephone', 'email', 
                 'habilitation', 'poste_affectation', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Matricule (ex: AGENT001)',
                'style': 'text-transform: uppercase;'
            }),
            'habilitation': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            username = username.upper()
            if UtilisateurSUPPER.objects.filter(username=username).exists():
                raise ValidationError('Ce matricule existe déjà.')
        return username


class UtilisateurChangeForm(UserChangeForm):
    """Formulaire de modification d'utilisateur SUPPER"""
    
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


class PasswordChangeForm(DjangoPasswordChangeForm):
    """
    Formulaire de changement de mot de passe personnalisé
    Validation simplifiée selon les specs SUPPER
    """
    
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        
        # Personnaliser les widgets
        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'form-control',
                'autocomplete': 'off' if 'new' in field_name else 'current-password'
            })
    
    def clean_new_password1(self):
        """
        Validation simplifiée du mot de passe selon specs SUPPER
        Minimum 4 caractères au lieu des validations Django standard
        """
        password = self.cleaned_data.get('new_password1')
        
        if password and len(password) < 4:
            raise ValidationError(
                _("Le mot de passe doit contenir au moins 4 caractères."),
                code='password_too_short',
            )
        
        return password


class UserCreateForm(forms.ModelForm):
    """
    Formulaire de création d'utilisateur pour les administrateurs
    """
    
    password1 = forms.CharField(
        label=_("Mot de passe"),
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        help_text=_("Minimum 4 caractères")
    )
    
    password2 = forms.CharField(
        label=_("Confirmation du mot de passe"),
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = UtilisateurSUPPER
        fields = [
            'username', 'nom_complet', 'telephone', 'email',
            'poste_affectation', 'habilitation'
        ]
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'style': 'text-transform: uppercase;',
                'placeholder': 'Ex: ADM001'
            }),
            'nom_complet': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom et prénom complets'
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+237XXXXXXXXX'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@example.com'
            }),
            'poste_affectation': forms.Select(attrs={'class': 'form-select'}),
            'habilitation': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def clean_username(self):
        """Valider et formater le matricule"""
        username = self.cleaned_data.get('username')
        if username:
            username = username.upper().strip()
            
            if not re.match(r'^[A-Z0-9]{6,20}$', username):
                raise ValidationError(
                    _("Le matricule doit contenir entre 6 et 20 caractères alphanumériques.")
                )
            
            # Vérifier l'unicité
            if UtilisateurSUPPER.objects.filter(username=username).exists():
                raise ValidationError(_("Ce matricule est déjà utilisé."))
        
        return username
    
    def clean_password2(self):
        """Vérifier que les mots de passe correspondent"""
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        
        if password1 and password2 and password1 != password2:
            raise ValidationError(_("Les mots de passe ne correspondent pas."))
        
        if password1 and len(password1) < 4:
            raise ValidationError(_("Le mot de passe doit contenir au moins 4 caractères."))
        
        return password2
    
    def save(self, commit=True):
        """Sauvegarder avec mot de passe crypté"""
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        
        if commit:
            user.save()
        
        return user


class UserUpdateForm(forms.ModelForm):
    """
    Formulaire de modification d'utilisateur
    """
    
    class Meta:
        model = UtilisateurSUPPER
        fields = [
            'nom_complet', 'telephone', 'email',
            'poste_affectation', 'habilitation', 'is_active'
        ]
        widgets = {
            'nom_complet': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'poste_affectation': forms.Select(attrs={'class': 'form-select'}),
            'habilitation': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ProfileEditForm(forms.ModelForm):
    """
    Formulaire pour permettre aux utilisateurs de modifier leur profil
    """
    
    class Meta:
        model = UtilisateurSUPPER
        fields = ['nom_complet', 'telephone', 'email']
        widgets = {
            'nom_complet': forms.TextInput(attrs={
                'class': 'form-control',
                'readonly': True  # Nom complet ne peut pas être modifié par l'utilisateur
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+237XXXXXXXXX'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@example.com'
            }),
        }


class PosteForm(forms.ModelForm):
    """Formulaire pour les postes"""
    
    class Meta:
        model = Poste
        fields = '__all__'
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Péage de Yaoundé-Nord'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: YDE-N-01',
                'pattern': r'^[A-Z0-9-]{3,15}$'
            }),
            'type_poste': forms.Select(attrs={'class': 'form-select'}),
            'localisation': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Adresse précise du poste'
            }),
            'region': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_region'
            }),
            'departement': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_departement'
            }),
            'arrondissement': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optionnel'
            }),
            'latitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.0000001',
                'placeholder': 'Ex: 3.8480'
            }),
            'longitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.0000001',
                'placeholder': 'Ex: 11.5021'
            }),
            'date_ouverture': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'observations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Notes particulières sur ce poste...'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean_code(self):
        code = self.cleaned_data.get('code')
        if code:
            code = code.upper()
            # Vérifier l'unicité sauf pour l'instance actuelle
            if self.instance.pk:
                if Poste.objects.filter(code=code).exclude(pk=self.instance.pk).exists():
                    raise ValidationError('Ce code de poste existe déjà.')
            else:
                if Poste.objects.filter(code=code).exists():
                    raise ValidationError('Ce code de poste existe déjà.')
        return code


class BulkUserCreateForm(forms.Form):
    """
    Formulaire pour la création en masse d'utilisateurs - Version améliorée
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
        # Charger les choix d'habilitation depuis le modèle
        try:
            from .models import Habilitation
            self.fields['habilitation_commune'].choices = Habilitation.choices
        except:
            # Fallback si le modèle n'est pas disponible
            self.fields['habilitation_commune'].choices = [
                ('agent_inventaire', 'Agent Inventaire'),
                ('chef_poste', 'Chef de Poste'),
                ('superviseur', 'Superviseur'),
            ]
    
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
            if not re.match(r'^[A-Z0-9]{6,20}$', matricule):
                raise ValidationError(
                    _("Ligne %(num)d: Matricule '%(matricule)s' invalide") % {'num': i, 'matricule': matricule}
                )
            
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


class PasswordResetForm(forms.Form):
    """
    Formulaire pour la réinitialisation de mot de passe par un admin
    """
    
    nouveau_mot_de_passe = forms.CharField(
        label=_("Nouveau mot de passe"),
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        help_text=_("Minimum 4 caractères")
    )
    
    confirmer_mot_de_passe = forms.CharField(
        label=_("Confirmer le mot de passe"),
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    
    def clean(self):
        """Vérifier que les mots de passe correspondent"""
        cleaned_data = super().clean()
        password1 = cleaned_data.get('nouveau_mot_de_passe')
        password2 = cleaned_data.get('confirmer_mot_de_passe')
        
        if password1 and password2:
            if password1 != password2:
                raise ValidationError(_("Les mots de passe ne correspondent pas."))
            
            if len(password1) < 4:
                raise ValidationError(_("Le mot de passe doit contenir au moins 4 caractères."))
        
        return cleaned_data


class InventaireForm(forms.Form):
    """Formulaire pour la saisie d'inventaire"""
    
    poste = forms.ModelChoiceField(
        queryset=Poste.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            'class': 'form-select select-modern',
            'required': True
        }),
        label='Poste'
    )
    
    date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control select-modern',
            'type': 'date',
            'required': True
        }),
        label='Date de l\'inventaire'
    )
    
    observations = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control select-modern',
            'rows': 3,
            'placeholder': 'Observations sur cet inventaire...'
        }),
        label='Observations'
    )
    
    # Champs dynamiques pour les périodes
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
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Vérifier qu'au moins une période est renseignée
        has_data = False
        for field_name, value in cleaned_data.items():
            if field_name.startswith('vehicules_') and value and value > 0:
                has_data = True
                break
        
        if not has_data:
            # C'est un avertissement, pas une erreur bloquante
            pass
        
        return cleaned_data


# Formulaires supplémentaires conservés du fichier original
class RechercheUtilisateurForm(forms.Form):
    """Formulaire de recherche d'utilisateurs"""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Rechercher par nom, matricule...',
            'autocomplete': 'off'
        }),
        label='Recherche'
    )
    
    habilitation = forms.ChoiceField(
        required=False,
        choices=[('', 'Toutes les habilitations')],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Filtrer par habilitation'
    )
    
    poste = forms.ModelChoiceField(
        queryset=Poste.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Filtrer par poste'
    )
    
    is_active = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Tous'),
            ('True', 'Actifs seulement'),
            ('False', 'Inactifs seulement')
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Statut'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from .models import Habilitation
            choices = [('', 'Toutes les habilitations')] + list(Habilitation.choices)
            self.fields['habilitation'].choices = choices
        except:
            pass


class ExportForm(forms.Form):
    """Formulaire pour les exports de données"""
    
    TYPE_EXPORT_CHOICES = [
        ('users', 'Utilisateurs'),
        ('postes', 'Postes'),
        ('inventaires', 'Inventaires'),
        ('recettes', 'Recettes'),
        ('audit', 'Journal d\'audit')
    ]
    
    FORMAT_CHOICES = [
        ('csv', 'CSV'),
        ('excel', 'Excel'),
        ('pdf', 'PDF')
    ]
    
    type_export = forms.ChoiceField(
        choices=TYPE_EXPORT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Type de données'
    )
    
    format_export = forms.ChoiceField(
        choices=FORMAT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Format de fichier'
    )
    
    date_debut = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label='Date de début (optionnel)'
    )
    
    date_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label='Date de fin (optionnel)'
    )
    
    postes = forms.ModelMultipleChoiceField(
        queryset=Poste.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label='Postes spécifiques (optionnel)'
    )