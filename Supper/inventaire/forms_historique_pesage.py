# ===================================================================
# FICHIER: inventaire/forms_historique_pesage.py
# ===================================================================
# Formulaires pour la gestion des historiques de pesage
# ===================================================================

from decimal import Decimal
from datetime import date

from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.validators import FileExtensionValidator

from accounts.models import Poste


class HistoriquePesageForm(forms.Form):
    """
    Formulaire de saisie d'un historique de pesage.

    Champs:
    - station: Station de pesage
    - mois/annee: Période (mois passés et mois actuel uniquement)
    - montant_global: Montant total versé à la perception
    - montant_reel: Part de cette station
    - image_page1: Image obligatoire (page 1)
    - image_page2: Image optionnelle (page 2)
    - image_page3: Image optionnelle (page 3)
    - observations
    """

    # Station
    station = forms.ModelChoiceField(
        queryset=Poste.objects.none(),
        label=_("Station de pesage"),
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_station'
        })
    )

    # Période - Mois
    MOIS_CHOICES = [
        ('', '-- Sélectionner --'),
        ('01', 'Janvier'),
        ('02', 'Février'),
        ('03', 'Mars'),
        ('04', 'Avril'),
        ('05', 'Mai'),
        ('06', 'Juin'),
        ('07', 'Juillet'),
        ('08', 'Août'),
        ('09', 'Septembre'),
        ('10', 'Octobre'),
        ('11', 'Novembre'),
        ('12', 'Décembre'),
    ]

    mois = forms.ChoiceField(
        choices=MOIS_CHOICES,
        label=_("Mois"),
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_mois'
        })
    )

    # Période - Année
    annee = forms.ChoiceField(
        label=_("Année"),
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_annee'
        })
    )

    # Montant global
    montant_global = forms.DecimalField(
        label=_("Montant global versé à la perception (FCFA)"),
        min_value=Decimal('0'),
        max_digits=15,
        decimal_places=0,
        required=True,
        help_text=_("Montant TOTAL versé à la perception (peut inclure plusieurs stations)"),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: 5 000 000',
            'id': 'id_montant_global',
            'min': '0',
            'step': '1'
        })
    )

    # Montant réel
    montant_reel = forms.DecimalField(
        label=_("Montant réel de cette station (FCFA)"),
        min_value=Decimal('0'),
        max_digits=15,
        decimal_places=0,
        required=True,
        help_text=_("Part de CETTE station dans le montant global (toujours ≤ montant global)"),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: 3 500 000',
            'id': 'id_montant_reel',
            'min': '0',
            'step': '1'
        })
    )

    # =========================================================================
    # IMAGES DU DOCUMENT ACCT
    # =========================================================================

    image_page1 = forms.ImageField(
        label=_("Image Page 1 (obligatoire)"),
        required=True,
        help_text=_("Première page du document ACCT - Formats acceptés: JPG, JPEG, PNG, PDF (max 5 Mo)"),
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf', 'webp'])
        ],
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'id': 'id_image_page1',
            'accept': 'image/*,.pdf'
        })
    )

    image_page2 = forms.ImageField(
        label=_("Image Page 2 (optionnelle)"),
        required=False,
        help_text=_("Deuxième page si nécessaire"),
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf', 'webp'])
        ],
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'id': 'id_image_page2',
            'accept': 'image/*,.pdf'
        })
    )

    image_page3 = forms.ImageField(
        label=_("Image Page 3 (optionnelle)"),
        required=False,
        help_text=_("Troisième page si nécessaire"),
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf', 'webp'])
        ],
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'id': 'id_image_page3',
            'accept': 'image/*,.pdf'
        })
    )

    # Observations
    observations = forms.CharField(
        label=_("Observations"),
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Informations complémentaires...'
        })
    )

    def __init__(self, *args, **kwargs):
        stations_accessibles = kwargs.pop('stations_accessibles', None)
        station_preselect = kwargs.pop('station_preselect', None)
        super().__init__(*args, **kwargs)

        # Configurer les stations accessibles
        if stations_accessibles is not None:
            self.fields['station'].queryset = stations_accessibles
        else:
            self.fields['station'].queryset = Poste.objects.filter(
                type='pesage',
                is_active=True
            ).order_by('nom')

        # Présélectionner la station si spécifiée
        if station_preselect:
            try:
                self.fields['station'].initial = int(station_preselect)
            except (ValueError, TypeError):
                pass

        # Générer les choix d'année (5 dernières années + année en cours, PAS d'année future)
        current_year = date.today().year
        annee_choices = [('', '-- Sélectionner --')]
        for year in range(current_year, current_year - 6, -1):
            annee_choices.append((str(year), str(year)))
        self.fields['annee'].choices = annee_choices
        self.fields['annee'].initial = str(current_year)

    def clean(self):
        """Validation globale du formulaire."""
        cleaned_data = super().clean()

        montant_global = cleaned_data.get('montant_global')
        montant_reel = cleaned_data.get('montant_reel')
        mois = cleaned_data.get('mois')
        annee = cleaned_data.get('annee')

        # Validation: montant_reel <= montant_global
        if montant_global and montant_reel:
            if montant_reel > montant_global:
                self.add_error('montant_reel', _(
                    "Le montant réel ne peut pas être supérieur au montant global. "
                    "Le montant réel représente la part de cette station dans le versement total."
                ))

        # Validation: pas de mois futur
        if mois and annee:
            try:
                mois_int = int(mois)
                annee_int = int(annee)
                today = date.today()
                
                # Vérifier que ce n'est pas un mois futur
                if annee_int > today.year:
                    self.add_error('annee', _("Vous ne pouvez pas saisir un historique pour une année future."))
                elif annee_int == today.year and mois_int > today.month:
                    self.add_error('mois', _("Vous ne pouvez pas saisir un historique pour un mois futur."))
                else:
                    # Reconstruire la chaîne mois au format YYYY-MM
                    cleaned_data['mois'] = f"{annee}-{mois}"
            except (ValueError, TypeError):
                pass

        # Validation taille des images (max 5 Mo)
        max_size = 5 * 1024 * 1024  # 5 Mo en bytes

        for field_name in ['image_page1', 'image_page2', 'image_page3']:
            image = cleaned_data.get(field_name)
            if image and hasattr(image, 'size'):
                if image.size > max_size:
                    self.add_error(field_name, _(
                        "L'image est trop volumineuse. Taille maximale: 5 Mo. "
                        "Taille actuelle: %(size).2f Mo"
                    ) % {'size': image.size / (1024 * 1024)})

        return cleaned_data


class HistoriquePesageFiltreForm(forms.Form):
    """
    Formulaire de filtrage pour la liste des historiques de pesage.
    """

    station = forms.ModelChoiceField(
        queryset=Poste.objects.filter(type='pesage', is_active=True).order_by('nom'),
        label=_("Station"),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'filter_station'
        }),
        empty_label=_("Toutes les stations")
    )

    annee = forms.ChoiceField(
        label=_("Année"),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'filter_annee'
        })
    )

    mois = forms.ChoiceField(
        label=_("Mois"),
        required=False,
        choices=[
            ('', _("Tous les mois")),
            ('01', _("Janvier")),
            ('02', _("Février")),
            ('03', _("Mars")),
            ('04', _("Avril")),
            ('05', _("Mai")),
            ('06', _("Juin")),
            ('07', _("Juillet")),
            ('08', _("Août")),
            ('09', _("Septembre")),
            ('10', _("Octobre")),
            ('11', _("Novembre")),
            ('12', _("Décembre")),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'filter_mois'
        })
    )

    def __init__(self, *args, **kwargs):
        stations_accessibles = kwargs.pop('stations_accessibles', None)
        super().__init__(*args, **kwargs)

        # Restreindre les stations si spécifié
        if stations_accessibles is not None:
            self.fields['station'].queryset = stations_accessibles

        # Générer les années (année courante jusqu'à 5 ans en arrière)
        current_year = date.today().year
        annees = [(str(y), str(y)) for y in range(current_year, current_year - 6, -1)]
        self.fields['annee'].choices = [('', _("Toutes les années"))] + annees