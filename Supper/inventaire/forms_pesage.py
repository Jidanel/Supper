# ===================================================================
# inventaire/forms_pesage.py - Formulaires pour le module pesage
# ===================================================================

from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from .models_pesage import AmendeEmise, PeseesJournalieres


class AmendeEmiseForm(forms.ModelForm):
    """
    Formulaire pour la saisie des amendes de pesage.
    Inclut tous les champs nécessaires avec validation personnalisée.
    """
    
    # Champs BooleanField pour les types d'infraction
    est_surcharge = forms.BooleanField(
        required=False,
        label=_("Surcharge"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        })
    )
    
    est_hors_gabarit = forms.BooleanField(
        required=False,
        label=_("Hors Gabarit"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        })
    )
    
    class Meta:
        model = AmendeEmise
        fields = [
            'numero_ticket',
            'immatriculation',
            'transporteur',
            'operateur',
            'provenance',
            'destination',
            'produit_transporte',
            'est_surcharge',
            'est_hors_gabarit',
            'montant_amende',
            'observations',
        ]
        widgets = {
            'numero_ticket': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Ex: TK-2024-00001'),
            }),
            'immatriculation': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Ex: CE 123 AB'),
                'style': 'text-transform: uppercase;',
            }),
            'transporteur': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Nom ou raison sociale'),
            }),
            'operateur': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Nom du chauffeur'),
            }),
            'provenance': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Ville de départ'),
            }),
            'destination': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Ville de destination'),
            }),
            'produit_transporte': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Ex: Ciment, Bois...'),
            }),
            'montant_amende': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '1',
                'placeholder': '0',
            }),
            'observations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Remarques ou observations...'),
            }),
        }
    
    def clean_immatriculation(self):
        """Convertit l'immatriculation en majuscules."""
        value = self.cleaned_data.get('immatriculation', '')
        return value.upper().strip() if value else value
    
    def clean_numero_ticket(self):
        """Convertit le numéro de ticket en majuscules."""
        value = self.cleaned_data.get('numero_ticket', '')
        return value.upper().strip() if value else value
    
    def clean(self):
        """Validation globale du formulaire."""
        cleaned_data = super().clean()
        
        est_surcharge = cleaned_data.get('est_surcharge', False)
        est_hors_gabarit = cleaned_data.get('est_hors_gabarit', False)
        
        # Au moins un type d'infraction doit être sélectionné
        if not est_surcharge and not est_hors_gabarit:
            raise ValidationError(
                _("Vous devez sélectionner au moins un type d'infraction "
                  "(Surcharge ou Hors Gabarit)")
            )
        
        return cleaned_data


class PeseesJournalieresForm(forms.ModelForm):
    """
    Formulaire pour la saisie des pesées journalières.
    Correspond au modèle PeseesJournalieres.
    """
    
    class Meta:
        model = PeseesJournalieres
        fields = [
            'date',
            'nombre_pesees',
            'observations',
        ]
        widgets = {
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'nombre_pesees': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '10000',
                'step': '1',
                'placeholder': '0',
            }),
            'observations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Remarques ou observations...'),
            }),
        }
    
    def clean_nombre_pesees(self):
        """Valide que le nombre de pesées est positif."""
        value = self.cleaned_data.get('nombre_pesees', 0)
        if value < 0:
            raise ValidationError(_("Le nombre de pesées ne peut pas être négatif."))
        if value > 10000:
            raise ValidationError(_("Le nombre de pesées semble trop élevé (max 10000)."))
        return value


class FiltreAmendesForm(forms.Form):
    """
    Formulaire pour filtrer la liste des amendes.
    """
    
    TYPE_INFRACTION_CHOICES = [
        ('', _('Tous')),
        ('S', _('Surcharge')),
        ('HG', _('Hors Gabarit')),
        ('S+HG', _('Surcharge + Hors Gabarit')),
    ]
    
    STATUT_CHOICES = [
        ('', _('Tous')),
        ('non_paye', _('Non payé')),
        ('paye', _('Payé')),
    ]
    
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
        choices=TYPE_INFRACTION_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label=_("Type d'infraction")
    )
    
    statut = forms.ChoiceField(
        required=False,
        choices=STATUT_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label=_("Statut")
    )
    
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Rechercher...'),
        }),
        label=_("Recherche")
    )


class RechercheAmendeForm(forms.Form):
    """
    Formulaire de recherche rapide d'amendes.
    """
    
    query = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('N° ticket, immatriculation, transporteur...'),
        }),
        label=_("Recherche")
    )


class ValidationPaiementForm(forms.Form):
    """
    Formulaire pour la validation d'un paiement.
    """
    
    confirmer = forms.BooleanField(
        required=True,
        label=_("Je confirme la validation du paiement"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        })
    )


class FiltreStatistiquesForm(forms.Form):
    """
    Formulaire pour filtrer les statistiques de pesage.
    """
    
    PERIODE_CHOICES = [
        ('jour', _('Par jour')),
        ('semaine', _('Par semaine')),
        ('mois', _('Par mois')),
        ('annee', _('Par année')),
    ]
    
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
    
    periode = forms.ChoiceField(
        required=False,
        choices=PERIODE_CHOICES,
        initial='jour',
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label=_("Période")
    )


class QuittancementPesageForm(forms.Form):
    """
    Formulaire pour le quittancement journalier du pesage.
    """
    
    date_quittancement = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        label=_("Date")
    )
    
    montant_encaisse = forms.DecimalField(
        required=True,
        min_value=0,
        decimal_places=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'step': '1',
            'placeholder': '0',
        }),
        label=_("Montant encaissé (FCFA)")
    )
    
    numero_quittance = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Ex: H631XXXXX'),
        }),
        label=_("N° quittance")
    )
    
    piece_jointe = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.jpg,.jpeg,.png',
        }),
        label=_("Pièce justificative")
    )
    
    observations = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('Remarques ou observations...'),
        }),
        label=_("Observations")
    )