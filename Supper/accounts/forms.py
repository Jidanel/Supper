# ===================================================================
# accounts/forms.py - Formulaires pour l'authentification et gestion utilisateurs
# ===================================================================

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm as DjangoPasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from .models import UtilisateurSUPPER, Poste, Habilitation


class CustomLoginForm(AuthenticationForm):
    """Formulaire de connexion personnalisé"""
    
    username = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Matricule (ex: INV001)',
            'autofocus': True
        }),
        label="Matricule"
    )
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mot de passe'
        }),
        label="Mot de passe"
    )
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            return username.upper()  # Convertir en majuscules
        return username


class PasswordChangeForm(DjangoPasswordChangeForm):
    """Formulaire de changement de mot de passe simplifié"""
    
    old_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mot de passe actuel'
        }),
        label="Mot de passe actuel"
    )
    
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nouveau mot de passe (min. 4 caractères)'
        }),
        label="Nouveau mot de passe",
        min_length=4,
        help_text="Minimum 4 caractères"
    )
    
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirmer le nouveau mot de passe'
        }),
        label="Confirmer le nouveau mot de passe"
    )


class UserCreateForm(forms.ModelForm):
    """Formulaire de création d'utilisateur"""
    
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mot de passe (min. 4 caractères)'
        }),
        label="Mot de passe",
        min_length=4,
        help_text="Minimum 4 caractères"
    )
    
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirmer le mot de passe'
        }),
        label="Confirmer le mot de passe"
    )
    
    class Meta:
        model = UtilisateurSUPPER
        fields = [
            'username', 'nom_complet', 'telephone', 'email',
            'poste_affectation', 'habilitation', 'password1', 'password2'
        ]
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Matricule (ex: INV001)'
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
                'placeholder': 'email@example.com (optionnel)'
            }),
            'poste_affectation': forms.Select(attrs={
                'class': 'form-select'
            }),
            'habilitation': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrer les postes actifs
        self.fields['poste_affectation'].queryset = Poste.objects.filter(actif=True)
        
        # Rendre l'email optionnel
        self.fields['email'].required = False
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            username = username.upper()
            # Vérifier l'unicité
            if UtilisateurSUPPER.objects.filter(username=username).exists():
                raise ValidationError("Ce matricule existe déjà.")
        return username
    
    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        
        if password1 and password2:
            if password1 != password2:
                raise ValidationError("Les mots de passe ne correspondent pas.")
        
        return password2
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        
        if commit:
            user.save()
        
        return user


class UserUpdateForm(forms.ModelForm):
    """Formulaire de modification d'utilisateur (sans mot de passe)"""
    
    class Meta:
        model = UtilisateurSUPPER
        fields = [
            'nom_complet', 'telephone', 'email', 'poste_affectation',
            'habilitation', 'is_active'
        ]
        widgets = {
            'nom_complet': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'poste_affectation': forms.Select(attrs={'class': 'form-select'}),
            'habilitation': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['poste_affectation'].queryset = Poste.objects.filter(actif=True)
        self.fields['email'].required = False


class BulkUserCreateForm(forms.Form):
    """Formulaire pour création en masse d'utilisateurs"""
    
    # Données communes
    poste_commun = forms.ModelChoiceField(
        queryset=Poste.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Poste d'affectation commun",
        required=True
    )
    
    habilitation_commune = forms.ChoiceField(
        choices=Habilitation.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Habilitation commune",
        initial='agent_inventaire'
    )
    
    mot_de_passe_commun = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mot de passe commun (min. 4 caractères)'
        }),
        label="Mot de passe commun",
        min_length=4,
        help_text="Ce mot de passe sera attribué à tous les utilisateurs créés"
    )
    
    # Liste des utilisateurs (format: matricule,nom_complet,telephone)
    liste_utilisateurs = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 10,
            'placeholder': 'Format: MATRICULE,Nom Complet,Téléphone\n'
                          'Exemple:\n'
                          'INV001,Jean Mballa,+237690123456\n'
                          'INV002,Marie Nkomo,+237691234567\n'
                          'INV003,Paul Fouda,+237692345678'
        }),
        label="Liste des utilisateurs",
        help_text="Un utilisateur par ligne, format: MATRICULE,Nom Complet,Téléphone"
    )
    
    def clean_liste_utilisateurs(self):
        liste = self.cleaned_data.get('liste_utilisateurs')
        if not liste:
            raise ValidationError("La liste des utilisateurs est requise.")
        
        lignes = [ligne.strip() for ligne in liste.split('\n') if ligne.strip()]
        utilisateurs_valides = []
        erreurs = []
        
        for i, ligne in enumerate(lignes, 1):
            try:
                parties = [p.strip() for p in ligne.split(',')]
                if len(parties) != 3:
                    erreurs.append(f"Ligne {i}: Format incorrect (3 éléments requis)")
                    continue
                
                matricule, nom, telephone = parties
                
                # Validation matricule
                if not matricule or len(matricule) < 3:
                    erreurs.append(f"Ligne {i}: Matricule invalide")
                    continue
                
                matricule = matricule.upper()
                
                # Vérifier unicité
                if UtilisateurSUPPER.objects.filter(username=matricule).exists():
                    erreurs.append(f"Ligne {i}: Matricule {matricule} existe déjà")
                    continue
                
                # Validation nom
                if not nom or len(nom) < 2:
                    erreurs.append(f"Ligne {i}: Nom invalide")
                    continue
                
                # Validation téléphone (simple)
                if not telephone or len(telephone) < 8:
                    erreurs.append(f"Ligne {i}: Téléphone invalide")
                    continue
                
                utilisateurs_valides.append({
                    'matricule': matricule,
                    'nom': nom,
                    'telephone': telephone
                })
                
            except Exception as e:
                erreurs.append(f"Ligne {i}: Erreur de format - {str(e)}")
        
        if erreurs:
            raise ValidationError(erreurs)
        
        if not utilisateurs_valides:
            raise ValidationError("Aucun utilisateur valide trouvé.")
        
        return utilisateurs_valides
    
    def create_users(self, created_by=None):
        """Crée les utilisateurs en masse"""
        if not self.is_valid():
            raise ValidationError("Formulaire invalide")
        
        utilisateurs_donnees = self.cleaned_data['liste_utilisateurs']
        poste = self.cleaned_data['poste_commun']
        habilitation = self.cleaned_data['habilitation_commune']
        mot_de_passe = self.cleaned_data['mot_de_passe_commun']
        
        users_created = []
        
        with transaction.atomic():
            for user_data in utilisateurs_donnees:
                user = UtilisateurSUPPER.objects.create_user(
                    username=user_data['matricule'],
                    nom_complet=user_data['nom'],
                    telephone=user_data['telephone'],
                    password=mot_de_passe,
                    poste_affectation=poste,
                    habilitation=habilitation,
                    cree_par=created_by
                )
                users_created.append(user)
        
        return users_created


class PasswordResetForm(forms.Form):
    """Formulaire de réinitialisation de mot de passe par admin"""
    
    nouveau_mot_de_passe = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nouveau mot de passe (min. 4 caractères)'
        }),
        label="Nouveau mot de passe",
        min_length=4
    )
    
    confirmer_mot_de_passe = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirmer le nouveau mot de passe'
        }),
        label="Confirmer le mot de passe"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('nouveau_mot_de_passe')
        password2 = cleaned_data.get('confirmer_mot_de_passe')
        
        if password1 and password2:
            if password1 != password2:
                raise ValidationError("Les mots de passe ne correspondent pas.")
        
        return cleaned_data
    
# ===================================================================
# Formulaire ProfileEditForm à ajouter dans Supper/accounts/forms.py
# ===================================================================

class ProfileEditForm(forms.ModelForm):
    """
    Formulaire pour modification du profil utilisateur
    Seuls certains champs sont modifiables par l'utilisateur
    """
    
    class Meta:
        model = UtilisateurSUPPER
        fields = [
            'nom_complet',
            'telephone', 
            'email'
        ]
        widgets = {
            'nom_complet': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Nom et prénom complets')
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+237XXXXXXXXX'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@exemple.com'
            }),
        }
        labels = {
            'nom_complet': _('Nom complet'),
            'telephone': _('Téléphone'),
            'email': _('Email (optionnel)'),
        }
        help_texts = {
            'telephone': _('Format: +237XXXXXXXXX ou XXXXXXXXX'),
            'email': _('Email pour récupération de mot de passe'),
        }
    
    def clean_telephone(self):
        """Validation du numéro de téléphone"""
        telephone = self.cleaned_data.get('telephone')
        if telephone:
            # Supprimer espaces et tirets
            telephone = telephone.replace(' ', '').replace('-', '')
            
            # Ajouter +237 si manquant
            if not telephone.startswith('+237') and len(telephone) == 9:
                telephone = '+237' + telephone
            
            # Validation format camerounais
            import re
            if not re.match(r'^\+237[0-9]{8,9}$', telephone):
                raise forms.ValidationError(
                    _("Format invalide. Utilisez: +237XXXXXXXXX")
                )
        
        return telephone