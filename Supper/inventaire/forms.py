# Supper/inventaire/forms.py
from django import forms
from django.utils import timezone
from .models import *
from zoneinfo import ZoneInfo  
from django.core.exceptions import ValidationError

class InventaireJournalierForm(forms.ModelForm):
    """Formulaire personnalisé pour la saisie d'inventaire"""
        
    class Meta:
        model = InventaireJournalier
        fields = '__all__'
        widgets = {
            'date': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control',
                    'required': True
                }
            ),
            'date_validation': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local',
                    'class': 'form-control',
                    'readonly': True
                }
            ),
            'observations': forms.Textarea(
                attrs={
                    'rows': 3,
                    'class': 'form-control'
                }
            ),
        }
        
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
                
        # Configurer le champ valide_par en lecture seule avec l'utilisateur connecté
        if self.request and self.request.user.is_authenticated:
            if 'valide_par' in self.fields:
                self.fields['valide_par'].widget = forms.HiddenInput()
                self.initial['valide_par'] = self.request.user
                        
        # Si validation, définir automatiquement la date/heure du Cameroun
        if self.instance and self.instance.valide:
            # Utilisation de zoneinfo au lieu de pytz
            cameroon_tz = ZoneInfo('Africa/Douala')
            self.initial['date_validation'] = timezone.now().astimezone(cameroon_tz)
        
    def save(self, commit=True):
        instance = super().save(commit=False)
                
        # Si l'inventaire est validé, définir automatiquement les champs
        if instance.valide and not instance.date_validation:
            # Utilisation de zoneinfo au lieu de pytz
            cameroon_tz = ZoneInfo('Africa/Douala')
            instance.date_validation = timezone.now().astimezone(cameroon_tz)
                        
            if self.request and self.request.user.is_authenticated:
                instance.valide_par = self.request.user
                
        if commit:
            instance.save()
        return instance

class RecetteJournaliereForm(forms.ModelForm):
    """
    Formulaire personnalisé pour RecetteJournaliere avec widget calendrier
    """
    
    class Meta:
        model = RecetteJournaliere
        fields = [
            'poste', 'date', 'montant_declare', 'chef_poste', 
            'observations', 'verrouille', 'valide'
        ]
        
        widgets = {
            'date': forms.DateInput(
                attrs={
                    'type': 'date',  # Widget calendrier HTML5
                    'class': 'form-control',
                    'placeholder': 'Sélectionner une date',
                    'style': 'max-width: 200px;'
                }
            ),
            'montant_declare': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Montant en FCFA',
                    'min': '0',
                    'step': '0.01'
                }
            ),
            'poste': forms.Select(
                attrs={
                    'class': 'form-control'
                }
            ),
            'chef_poste': forms.Select(
                attrs={
                    'class': 'form-control'
                }
            ),
            'observations': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Observations sur cette recette (optionnel)'
                }
            ),
            'verrouille': forms.CheckboxInput(
                attrs={
                    'class': 'form-check-input'
                }
            ),
            'valide': forms.CheckboxInput(
                attrs={
                    'class': 'form-check-input'
                }
            )
        }
        
        labels = {
            'poste': 'Poste *',
            'date': 'Date de la recette *',
            'montant_declare': 'Montant déclaré (FCFA) *',
            'chef_poste': 'Chef de poste *',
            'observations': 'Observations',
            'verrouille': 'Recette verrouillée',
            'valide': 'Recette validée'
        }
        
        help_texts = {
            'date': 'Cliquez pour ouvrir le calendrier et sélectionner la date',
            'montant_declare': 'Recette déclarée par le chef de poste en FCFA',
            'observations': 'Commentaires optionnels sur cette recette',
            'verrouille': 'Une fois verrouillée, la recette ne peut plus être modifiée',
            'valide': 'Validation par un responsable'
        }
    
    def __init__(self, *args, **kwargs):
        # Récupérer l'utilisateur connecté si fourni
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filtrer les postes selon les permissions de l'utilisateur
        if self.user and hasattr(self.user, 'get_postes_accessibles'):
            postes_accessibles = self.user.get_postes_accessibles()
            self.fields['poste'].queryset = postes_accessibles
        
        # Filtrer les chefs de poste
        self.fields['chef_poste'].queryset = UtilisateurSUPPER.objects.filter(
            habilitation__in=['chef_peage', 'chef_pesage', 'admin_principal']
        )
        
        # Définir l'utilisateur connecté comme chef de poste par défaut
        if self.user and not self.instance.pk:
            self.fields['chef_poste'].initial = self.user
        
        # Définir la date d'aujourd'hui par défaut
        if not self.instance.pk:
            self.fields['date'].initial = timezone.now().date()
    
    def clean_date(self):
        """Validation de la date"""
        date = self.cleaned_data.get('date')
        
        if not date:
            raise ValidationError("La date est obligatoire.")
        
        # Vérifier que la date n'est pas dans le futur
        if date > timezone.now().date():
            raise ValidationError("La date ne peut pas être dans le futur.")
        
        # Vérifier si le jour est ouvert pour la saisie de recettes
        poste = self.cleaned_data.get('poste')
        if poste and not ConfigurationJour.est_jour_ouvert_pour_recette(date, poste):
            raise ValidationError(
                f"La saisie de recettes n'est pas autorisée pour le {date.strftime('%d/%m/%Y')} "
                f"au poste {poste.nom}. Contactez un administrateur pour ouvrir ce jour."
            )
        
        return date
    
    def clean_montant_declare(self):
        """Validation du montant déclaré"""
        montant = self.cleaned_data.get('montant_declare')
        
        if montant is None:
            raise ValidationError("Le montant déclaré est obligatoire.")
        
        if montant < 0:
            raise ValidationError("Le montant ne peut pas être négatif.")
        
        # Limite raisonnable pour éviter les erreurs de saisie
        if montant > 10000000:  # 10 millions FCFA
            raise ValidationError(
                "Montant très élevé. Veuillez vérifier votre saisie. "
                "Si ce montant est correct, contactez un administrateur."
            )
        
        return montant
    
    def clean(self):
        """Validations globales"""
        cleaned_data = super().clean()
        poste = cleaned_data.get('poste')
        date = cleaned_data.get('date')
        
        # Vérifier l'unicité poste/date si c'est une nouvelle recette
        if poste and date and not self.instance.pk:
            if RecetteJournaliere.objects.filter(poste=poste, date=date).exists():
                raise ValidationError(
                    f"Une recette existe déjà pour le poste {poste.nom} "
                    f"à la date du {date.strftime('%d/%m/%Y')}."
                )
        
        # Vérifier que l'utilisateur peut modifier cette recette
        if self.instance.pk and self.instance.verrouille:
            if not (self.user and self.user.is_admin()):
                raise ValidationError(
                    "Cette recette est verrouillée et ne peut plus être modifiée."
                )
        
        return cleaned_data
    
    def save(self, commit=True):
        """Sauvegarde personnalisée"""
        recette = super().save(commit=False)
        
        # Calculer automatiquement les indicateurs
        if commit:
            recette.save()
            recette.calculer_indicateurs()
            recette.save()
        
        return recette


class ConfigurationJourForm(forms.ModelForm):
    """
    Formulaire pour ConfigurationJour avec widget calendrier et validation robuste
    """
    
    class Meta:
        model = ConfigurationJour
        fields = [
            'date', 'poste', 'statut', 'permet_saisie_inventaire', 
            'permet_saisie_recette', 'commentaire'
        ]
        
        widgets = {
            'date': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control calendrier-widget',
                    'style': 'max-width: 200px;'
                }
            ),
            'poste': forms.Select(
                attrs={
                    'class': 'form-control',
                    'style': 'max-width: 300px;'
                }
            ),
            'statut': forms.Select(
                attrs={
                    'class': 'form-control',
                    'style': 'max-width: 200px;'
                }
            ),
            'permet_saisie_inventaire': forms.CheckboxInput(
                attrs={
                    'class': 'form-check-input'
                }
            ),
            'permet_saisie_recette': forms.CheckboxInput(
                attrs={
                    'class': 'form-check-input'
                }
            ),
            'commentaire': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Raison de cette configuration (optionnel)'
                }
            )
        }
        
        labels = {
            'date': 'Date *',
            'poste': 'Poste (optionnel)',
            'statut': 'Statut du jour *',
            'permet_saisie_inventaire': 'Autoriser saisie inventaire',
            'permet_saisie_recette': 'Autoriser saisie recette',
            'commentaire': 'Commentaire'
        }
        
        help_texts = {
            'date': 'Date à configurer',
            'poste': 'Laisser vide pour une configuration globale',
            'permet_saisie_inventaire': 'Cocher pour permettre la saisie d\'inventaires',
            'permet_saisie_recette': 'Cocher pour permettre la saisie de recettes',
            'commentaire': 'Explication de cette configuration'
        }
    
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # 🔧 GESTION SÉCURISÉE des postes
        try:
            if self.user and hasattr(self.user, 'get_postes_accessibles'):
                postes_accessibles = self.user.get_postes_accessibles()
                self.fields['poste'].queryset = postes_accessibles
            else:
                # Fallback : tous les postes actifs
                self.fields['poste'].queryset = Poste.objects.filter(actif=True)
        except Exception:
            # En cas d'erreur, utiliser tous les postes
            self.fields['poste'].queryset = Poste.objects.all()
        
        # Ajouter une option vide pour configuration globale
        self.fields['poste'].empty_label = "Configuration globale"
        
        # Valeurs par défaut
        if not self.instance.pk:
            self.fields['statut'].initial = 'ouvert'
            self.fields['permet_saisie_inventaire'].initial = True
            self.fields['permet_saisie_recette'].initial = True
    
    def clean_date(self):
        """Validation de la date"""
        date = self.cleaned_data.get('date')
        
        if not date:
            raise ValidationError("La date est obligatoire.")
        
        return date
    
    def clean(self):
        """Validations globales"""
        cleaned_data = super().clean()
        date = cleaned_data.get('date')
        poste = cleaned_data.get('poste')
        
        # Vérifier l'unicité date/poste (si c'est une nouvelle configuration)
        if date and not self.instance.pk:
            existing = ConfigurationJour.objects.filter(date=date, poste=poste)
            if existing.exists():
                if poste:
                    raise ValidationError(
                        f"Une configuration existe déjà pour le poste {poste.nom} "
                        f"à la date du {date.strftime('%d/%m/%Y')}."
                    )
                else:
                    raise ValidationError(
                        f"Une configuration globale existe déjà "
                        f"pour la date du {date.strftime('%d/%m/%Y')}."
                    )
        
        return cleaned_data
    
    def save(self, commit=True):
        """Sauvegarde avec utilisateur créateur"""
        config = super().save(commit=False)
        
        if not config.pk and self.user:
            config.cree_par = self.user
        
        if commit:
            config.save()
        
        return config
# ===================================================================
# WIDGET CALENDRIER AVANCÉ (OPTIONNEL)
# Pour une interface encore plus riche
# ===================================================================

class CalendrierWidget(forms.DateInput):
    """
    Widget calendrier personnalisé avec Bootstrap et JavaScript
    """
    
    def __init__(self, attrs=None):
        default_attrs = {
            'type': 'date',
            'class': 'form-control calendrier-widget',
            'data-bs-toggle': 'tooltip',
            'data-bs-placement': 'top',
            'title': 'Cliquez pour ouvrir le calendrier'
        }
        
        if attrs:
            default_attrs.update(attrs)
        
        super().__init__(attrs=default_attrs)
    
    class Media:
        css = {
            'all': ('css/calendrier-widget.css',)
        }
        js = ('js/calendrier-widget.js',)


class RecetteJournaliereAdminForm(RecetteJournaliereForm):
    """
    Formulaire spécifique pour l'admin Django avec validations renforcées
    """
    
    class Meta(RecetteJournaliereForm.Meta):
        widgets = {
            **RecetteJournaliereForm.Meta.widgets,
            'date': CalendrierWidget(),  # Widget calendrier avancé
        }