# ===================================================================
# accounts/forms.py - Formulaires pour l'application accounts
# ===================================================================
# 🔄 REMPLACE le contenu existant du fichier accounts/forms.py OU CRÉER si inexistant

from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from .models import UtilisateurSUPPER, Poste


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
                'placeholder': 'Matricule (ex: AGENT001)'
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

from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate
from .models import UtilisateurSUPPER, Poste


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
                'placeholder': 'Matricule (ex: AGENT001)'
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


class CustomLoginForm(forms.Form):
    """Formulaire de connexion personnalisé avec matricule"""
    
    username = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Votre matricule',
            'autofocus': True
        }),
        label='Matricule'
    )
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Votre mot de passe'
        }),
        label='Mot de passe'
    )
    
    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')
        
        if username and password:
            username = username.upper()
            user = authenticate(username=username, password=password)
            if user is None:
                raise ValidationError('Matricule ou mot de passe incorrect.')
            if not user.is_active:
                raise ValidationError('Ce compte est désactivé.')
        
        return cleaned_data


class ProfileEditForm(forms.ModelForm):
    """Formulaire pour que l'utilisateur modifie son profil"""
    
    class Meta:
        model = UtilisateurSUPPER
        fields = ('telephone', 'email')
        widgets = {
            'telephone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+237XXXXXXXXX'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@exemple.com'
            }),
        }


class PasswordChangeForm(forms.Form):
    """Formulaire de changement de mot de passe"""
    
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mot de passe actuel'
        }),
        label='Mot de passe actuel'
    )
    
    new_password = forms.CharField(
        min_length=4,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nouveau mot de passe (min. 4 caractères)'
        }),
        label='Nouveau mot de passe'
    )
    
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirmer le nouveau mot de passe'
        }),
        label='Confirmer le mot de passe'
    )
    
    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if new_password and confirm_password:
            if new_password != confirm_password:
                raise ValidationError('Les mots de passe ne correspondent pas.')
        
        return cleaned_data


class UserCreateForm(forms.ModelForm):
    """Formulaire de création d'utilisateur par admin"""
    
    password1 = forms.CharField(
        label='Mot de passe',
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    password2 = forms.CharField(
        label='Confirmer mot de passe',
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = UtilisateurSUPPER
        fields = ('username', 'nom_complet', 'telephone', 'email', 
                 'habilitation', 'poste_affectation')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'nom_complet': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'habilitation': forms.Select(attrs={'class': 'form-select'}),
            'poste_affectation': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError('Les mots de passe ne correspondent pas.')
        return password2
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class UserUpdateForm(forms.ModelForm):
    """Formulaire de modification d'utilisateur par admin"""
    
    class Meta:
        model = UtilisateurSUPPER
        fields = ('nom_complet', 'telephone', 'email', 'habilitation', 
                 'poste_affectation', 'is_active')
        widgets = {
            'nom_complet': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'habilitation': forms.Select(attrs={'class': 'form-select'}),
            'poste_affectation': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BulkUserCreateForm(forms.Form):
    """Formulaire pour création en masse d'utilisateurs"""
    
    base_username = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'AGENT'
        }),
        label='Préfixe des matricules'
    )
    
    count = forms.IntegerField(
        min_value=1,
        max_value=50,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 1,
            'max': 50
        }),
        label='Nombre d\'utilisateurs'
    )
    
    default_password = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'value': 'supper2025'
        }),
        label='Mot de passe par défaut'
    )
    
    habilitation = forms.ChoiceField(
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Habilitation par défaut'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Habilitation
        self.fields['habilitation'].choices = Habilitation.choices
    
    def create_users(self, created_by=None):
        """Crée les utilisateurs en masse"""
        users_created = []
        base = self.cleaned_data['base_username']
        count = self.cleaned_data['count']
        password = self.cleaned_data['default_password']
        habilitation = self.cleaned_data['habilitation']
        
        for i in range(1, count + 1):
            username = f"{base}{i:03d}"
            if not UtilisateurSUPPER.objects.filter(username=username).exists():
                user = UtilisateurSUPPER.objects.create_user(
                    username=username,
                    nom_complet=f"Utilisateur {username}",
                    telephone=f"+237600{i:06d}",
                    habilitation=habilitation,
                    password=password,
                    cree_par=created_by
                )
                users_created.append(user)
        
        return users_created


class PasswordResetForm(forms.Form):
    """Formulaire de réinitialisation de mot de passe par admin"""
    
    nouveau_mot_de_passe = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'value': 'supper2025'
        }),
        label='Nouveau mot de passe'
    )
    
    confirmation = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Je confirme vouloir réinitialiser ce mot de passe'
    )
class CreationMasseForm(forms.Form):
    """Formulaire pour la création d'utilisateurs en masse"""
    
    base_username = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'AGENT',
            'pattern': r'^[A-Z]{3,10}'
        }),
        label='Préfixe des matricules',
        help_text='Ex: AGENT générera AGENT001, AGENT002, etc.'
    )
    
    count = forms.IntegerField(
        min_value=1,
        max_value=50,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 1,
            'max': 50
        }),
        label='Nombre d\'utilisateurs à créer'
    )
    
    default_password = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'value': 'supper2025'
        }),
        label='Mot de passe par défaut'
    )
    
    habilitation = forms.ChoiceField(
        choices=[],  # Sera rempli dans __init__
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Habilitation par défaut'
    )
    
    poste_affectation = forms.ModelChoiceField(
        queryset=Poste.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Poste d\'affectation (optionnel)'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Habilitation
        self.fields['habilitation'].choices = Habilitation.choices


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
        from .models import Habilitation
        choices = [('', 'Toutes les habilitations')] + list(Habilitation.choices)
        self.fields['habilitation'].choices = choices


class ConfigurationJourForm(forms.Form):
    """Formulaire pour configurer les jours de saisie"""
    
    date_debut = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label='Date de début'
    )
    
    date_fin = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label='Date de fin'
    )
    
    statut = forms.ChoiceField(
        choices=[
            ('ouvert', 'Ouvrir pour saisie'),
            ('ferme', 'Fermer pour saisie'),
            ('impertinent', 'Marquer comme impertinent')
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Action à effectuer'
    )
    
    commentaire = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Raison de cette configuration...'
        }),
        label='Commentaire'
    )
    
    def clean(self):
        cleaned_data = super().clean()
        date_debut = cleaned_data.get('date_debut')
        date_fin = cleaned_data.get('date_fin')
        
        if date_debut and date_fin:
            if date_debut > date_fin:
                raise ValidationError('La date de début doit être antérieure à la date de fin.')
            
            # Limiter à 31 jours maximum
            if (date_fin - date_debut).days > 31:
                raise ValidationError('La période ne peut pas dépasser 31 jours.')
        
        return cleaned_data


class NotificationForm(forms.Form):
    """Formulaire pour envoyer des notifications"""
    
    destinataires = forms.ModelMultipleChoiceField(
        queryset=UtilisateurSUPPER.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label='Destinataires'
    )
    
    titre = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Titre de la notification'
        }),
        label='Titre'
    )
    
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'Contenu du message...'
        }),
        label='Message'
    )
    
    type_notification = forms.ChoiceField(
        choices=[
            ('info', 'Information'),
            ('warning', 'Avertissement'),
            ('success', 'Succès'),
            ('system', 'Système')
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Type de notification'
    )


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


class ResetPasswordForm(forms.Form):
    """Formulaire pour réinitialiser le mot de passe"""
    
    utilisateurs = forms.ModelMultipleChoiceField(
        queryset=UtilisateurSUPPER.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label='Utilisateurs concernés'
    )
    
    nouveau_mot_de_passe = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'value': 'supper2025'
        }),
        label='Nouveau mot de passe'
    )
    
    confirmation = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Je confirme vouloir réinitialiser les mots de passe'
    )