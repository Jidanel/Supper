# Supper/inventaire/forms.py
from django import forms
from django.utils import timezone
from .models import *
from zoneinfo import ZoneInfo  

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