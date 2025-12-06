# ===================================================================
# inventaire/forms_pesage.py - Formulaires pour le module Pesage SUPPER
# ===================================================================

from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

from .models_pesage import (
    AmendeEmise, PeseesJournalieres, QuittancementPesage,
    StatutAmende
)


class AmendeEmiseForm(forms.ModelForm):
    """
    Formulaire de saisie d'amende par le chef d'équipe
    Nécessite une confirmation avant validation (modal JS)
    """
    
    # Champ de confirmation (géré côté JS)
    confirmation = forms.BooleanField(
        required=False,
        widget=forms.HiddenInput(),
        initial=False
    )
    
    class Meta:
        model = AmendeEmise
        fields = [
            'numero_ticket',
            'immatriculation',
            'transporteur',
            'provenance',
            'destination',
            'produit_transporte',
            'operateur',
            'est_surcharge',
            'est_hors_gabarit',
            'montant_amende',
            'observations',
        ]
        widgets = {
            'numero_ticket': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: TKT-2025-001234',
                'autofocus': True,
            }),
            'immatriculation': forms.TextInput(attrs={
                'class': 'form-control text-uppercase',
                'placeholder': 'Ex: CE 123 AB',
            }),
            'transporteur': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom du transporteur',
            }),
            'provenance': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ville de départ',
            }),
            'destination': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ville de destination',
            }),
            'produit_transporte': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nature de la marchandise',
            }),
            'operateur': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom du conducteur',
            }),
            'est_surcharge': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'est_hors_gabarit': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'montant_amende': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Montant en FCFA',
                'min': '0',
                'step': '1',
            }),
            'observations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observations éventuelles...',
            }),
        }
    
    def clean_immatriculation(self):
        """Normalise l'immatriculation en majuscules"""
        immat = self.cleaned_data.get('immatriculation', '')
        return immat.upper().strip()
    
    def clean_numero_ticket(self):
        """Vérifie l'unicité du numéro de ticket"""
        numero = self.cleaned_data.get('numero_ticket', '')
        numero = numero.strip()
        
        if AmendeEmise.objects.filter(numero_ticket=numero).exists():
            raise ValidationError(
                _("Ce numéro de ticket existe déjà dans le système.")
            )
        
        return numero
    
    def clean(self):
        """Validation globale du formulaire"""
        cleaned_data = super().clean()
        
        est_surcharge = cleaned_data.get('est_surcharge', False)
        est_hors_gabarit = cleaned_data.get('est_hors_gabarit', False)
        
        # Au moins un type d'infraction doit être sélectionné
        if not est_surcharge and not est_hors_gabarit:
            raise ValidationError(
                _("Vous devez sélectionner au moins un type d'infraction "
                  "(Surcharge et/ou Hors Gabarit).")
            )
        
        # Vérifier le montant
        montant = cleaned_data.get('montant_amende')
        if montant is not None and montant <= 0:
            raise ValidationError(
                _("Le montant de l'amende doit être supérieur à 0.")
            )
        
        return cleaned_data


class PeseesJournalieresForm(forms.ModelForm):
    """
    Formulaire de saisie du nombre de pesées journalières
    Une seule saisie par jour par station, non modifiable
    """
    
    class Meta:
        model = PeseesJournalieres
        fields = ['date', 'nombre_pesees', 'observations']
        widgets = {
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'nombre_pesees': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '10000',
                'placeholder': 'Nombre de pesées',
            }),
            'observations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Observations...',
            }),
        }
    
    def __init__(self, *args, station=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.station = station
    
    def clean_date(self):
        """Vérifie qu'aucune saisie n'existe déjà pour cette date"""
        date = self.cleaned_data.get('date')
        
        if self.station and date:
            exists = PeseesJournalieres.objects.filter(
                station=self.station,
                date=date
            ).exists()
            
            if exists:
                raise ValidationError(
                    _("Une saisie existe déjà pour cette date. "
                      "Les pesées journalières ne peuvent pas être modifiées.")
                )
        
        # Vérifier que la date n'est pas dans le futur
        if date and date > timezone.now().date():
            raise ValidationError(
                _("Vous ne pouvez pas saisir pour une date future.")
            )
        
        return date


class QuittancementPesageForm(forms.ModelForm):
    """
    Formulaire de saisie de quittancement par le régisseur
    """
    
    class Meta:
        model = QuittancementPesage
        fields = [
            'type_quittancement',
            'date_debut',
            'date_fin',
            'numero_quittance',
            'montant_quittance',
            'image_quittance',
            'observations',
        ]
        widgets = {
            'type_quittancement': forms.Select(attrs={
                'class': 'form-select',
            }),
            'date_debut': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'date_fin': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'numero_quittance': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Numéro de quittance',
            }),
            'montant_quittance': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '1',
                'placeholder': 'Montant en FCFA',
            }),
            'image_quittance': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'observations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
            }),
        }
    
    def clean(self):
        """Validation des dates"""
        cleaned_data = super().clean()
        
        type_quittancement = cleaned_data.get('type_quittancement')
        date_debut = cleaned_data.get('date_debut')
        date_fin = cleaned_data.get('date_fin')
        
        if date_debut and date_fin:
            if date_fin < date_debut:
                raise ValidationError(
                    _("La date de fin doit être postérieure à la date de début.")
                )
            
            # Pour quittancement journalier, même date
            if type_quittancement == 'journalier' and date_debut != date_fin:
                raise ValidationError(
                    _("Pour un quittancement journalier, les dates de début "
                      "et fin doivent être identiques.")
                )
        
        return cleaned_data


class RechercheAmendeForm(forms.Form):
    """
    Formulaire de recherche d'amendes
    """
    
    numero_ticket = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Numéro de ticket',
        }),
        label=_("Numéro de ticket")
    )
    
    immatriculation = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-uppercase',
            'placeholder': 'Immatriculation',
        }),
        label=_("Immatriculation")
    )
    
    transporteur = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Transporteur',
        }),
        label=_("Transporteur")
    )
    
    statut = forms.ChoiceField(
        required=False,
        choices=[('', 'Tous les statuts')] + list(StatutAmende.choices),
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label=_("Statut")
    )
    
    date_debut = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        label=_("Date début")
    )
    
    date_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        label=_("Date fin")
    )
    
    type_infraction = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Tous les types'),
            ('surcharge', 'Surcharge uniquement'),
            ('hors_gabarit', 'Hors Gabarit uniquement'),
            ('mixte', 'Surcharge + Hors Gabarit'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label=_("Type d'infraction")
    )
    
    def get_queryset(self, station):
        """
        Retourne le queryset filtré selon les critères
        """
        queryset = AmendeEmise.objects.filter(station=station)
        
        # Filtrer par numéro de ticket
        numero = self.cleaned_data.get('numero_ticket')
        if numero:
            queryset = queryset.filter(numero_ticket__icontains=numero)
        
        # Filtrer par immatriculation
        immat = self.cleaned_data.get('immatriculation')
        if immat:
            queryset = queryset.filter(immatriculation__icontains=immat.upper())
        
        # Filtrer par transporteur
        transporteur = self.cleaned_data.get('transporteur')
        if transporteur:
            queryset = queryset.filter(transporteur__icontains=transporteur)
        
        # Filtrer par statut
        statut = self.cleaned_data.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)
        
        # Filtrer par date
        date_debut = self.cleaned_data.get('date_debut')
        if date_debut:
            debut_dt = AmendeEmise.get_date_debut_journee(date_debut)
            queryset = queryset.filter(date_heure_emission__gte=debut_dt)
        
        date_fin = self.cleaned_data.get('date_fin')
        if date_fin:
            fin_dt = AmendeEmise.get_date_fin_journee(date_fin)
            queryset = queryset.filter(date_heure_emission__lte=fin_dt)
        
        # Filtrer par type d'infraction
        type_infraction = self.cleaned_data.get('type_infraction')
        if type_infraction == 'surcharge':
            queryset = queryset.filter(est_surcharge=True, est_hors_gabarit=False)
        elif type_infraction == 'hors_gabarit':
            queryset = queryset.filter(est_surcharge=False, est_hors_gabarit=True)
        elif type_infraction == 'mixte':
            queryset = queryset.filter(est_surcharge=True, est_hors_gabarit=True)
        
        return queryset.order_by('-date_heure_emission')


class ValidationPaiementForm(forms.Form):
    """
    Formulaire simple pour la validation de paiement par le régisseur
    """
    
    confirmation = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        }),
        label=_("Je confirme la validation du paiement")
    )
    
    observations = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Observations (optionnel)',
        }),
        label=_("Observations")
    )


class FiltreStatistiquesForm(forms.Form):
    """
    Formulaire de filtrage pour les statistiques
    """
    
    TYPE_PERIODE_CHOICES = [
        ('journalier', 'Journalier'),
        ('hebdomadaire', 'Hebdomadaire'),
        ('mensuel', 'Mensuel'),
        ('annuel', 'Annuel'),
    ]
    
    type_periode = forms.ChoiceField(
        choices=TYPE_PERIODE_CHOICES,
        initial='journalier',
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label=_("Type de période")
    )
    
    date_debut = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        label=_("Date de début")
    )
    
    date_fin = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        label=_("Date de fin")
    )
    
    def clean(self):
        cleaned_data = super().clean()
        date_debut = cleaned_data.get('date_debut')
        date_fin = cleaned_data.get('date_fin')
        
        if date_debut and date_fin and date_fin < date_debut:
            raise ValidationError(
                _("La date de fin doit être postérieure à la date de début.")
            )
        
        return cleaned_data