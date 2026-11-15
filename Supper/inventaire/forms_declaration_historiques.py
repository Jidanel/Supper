# inventaire/forms_declaration_historiques.py
# ===================================================================
# MODULE "DÉCLARATION DES HISTORIQUES" - FORMULAIRES
# Un seul écran pour déclarer, par poste et par mois :
#   1) la Quittance ou Reçu de versement
#   2) l'Historique ou Extrait de compte
# Péage ET pesage (les 4 tables existantes sont réutilisées).
# ===================================================================

from decimal import Decimal  # Type décimal pour les montants
from datetime import date  # Pour contrôler les dates futures

from django import forms  # Outils de formulaires Django
from django.utils.translation import gettext_lazy as _  # Traduction FR/EN

from accounts.models import Poste  # Modèle des postes (péage + pesage)

# -------------------------------------------------------------------
# LIBELLÉS CENTRALISÉS (une seule source de vérité FR/EN)
# Ils sont réutilisés partout (formulaires, listes, PDF, CSP...).
# -------------------------------------------------------------------
LABEL_QUITTANCE = _("Quittance ou Reçu de versement")  # Titre du bloc quittance
LABEL_NUMERO_QUITTANCE = _("Numéro de quittance / Numéro de reçu de versement")  # N°
LABEL_DATE_QUITTANCEMENT = _("Date de quittancement ou Date de reversement")  # Date
LABEL_HISTORIQUE_ACCT = _("Historique ou Extrait de compte")  # Titre historique


class SelectionPosteMoisForm(forms.Form):
    """Étape 1 : choix du poste et du mois à déclarer (méthode GET)."""

    # Poste ou station concerné(e)
    poste = forms.ModelChoiceField(
        queryset=Poste.objects.none(),  # Rempli dans __init__ selon les droits
        label=_("Poste / Station"),  # Libellé affiché
    )
    # Mois concerné au format AAAA-MM (champ HTML <input type="month">)
    mois = forms.RegexField(
        regex=r'^\d{4}-(0[1-9]|1[0-2])$',  # Format strict AAAA-MM
        label=_("Mois"),  # Libellé affiché
        widget=forms.TextInput(attrs={'type': 'month', 'class': 'form-control'}),
    )

    def __init__(self, *args, postes_qs=None, **kwargs):
        """postes_qs : queryset des postes que l'utilisateur peut voir."""
        super().__init__(*args, **kwargs)  # Initialisation standard
        if postes_qs is not None:  # Si une liste de postes est fournie
            self.fields['poste'].queryset = postes_qs  # On la limite aux postes autorisés
        self.fields['poste'].widget.attrs['class'] = 'form-select'  # Style Bootstrap


class QuittanceRecuForm(forms.Form):
    """Bloc 1 : Quittance ou Reçu de versement (péage et pesage)."""

    # Choix du type de déclaration (identique au modèle Quittancement)
    TYPE_CHOICES = [
        ('journaliere', _("Journalière")),  # Une seule date de recette
        ('decade', _("Décade")),  # Une période début/fin
    ]

    numero_quittance = forms.CharField(
        max_length=50, label=LABEL_NUMERO_QUITTANCE,  # N° quittance / N° reçu
    )
    type_declaration = forms.ChoiceField(
        choices=TYPE_CHOICES, label=_("Type de déclaration"),
    )
    date_quittancement = forms.DateField(
        label=LABEL_DATE_QUITTANCEMENT,  # Date de quittancement ou de reversement
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    date_recette = forms.DateField(
        required=False, label=_("Date de recette"),  # Utilisée si journalière
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    date_debut_decade = forms.DateField(
        required=False, label=_("Début de la décade"),  # Utilisée si décade
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    date_fin_decade = forms.DateField(
        required=False, label=_("Fin de la décade"),  # Utilisée si décade
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    montant = forms.DecimalField(
        min_value=Decimal('0'), decimal_places=0, max_digits=15,
        label=_("Montant (FCFA)"),
    )
    image_quittance = forms.ImageField(
        required=False, label=_("Image de la quittance / du reçu"),
    )
    observations = forms.CharField(
        required=False, label=_("Observations"),
        widget=forms.Textarea(attrs={'rows': 2}),
    )

    def clean(self):
        """Contrôles croisés selon le type de déclaration."""
        data = super().clean()  # Données déjà validées champ par champ
        type_decl = data.get('type_declaration')  # Type choisi
        aujourdhui = date.today()  # Date du jour
        # Une date de quittancement/reversement ne peut pas être dans le futur
        dq = data.get('date_quittancement')
        if dq and dq > aujourdhui:
            self.add_error('date_quittancement', _("La date ne peut pas être dans le futur."))
        if type_decl == 'journaliere':  # Cas journalier
            if not data.get('date_recette'):
                self.add_error('date_recette', _("La date de recette est obligatoire."))
        elif type_decl == 'decade':  # Cas décade
            debut, fin = data.get('date_debut_decade'), data.get('date_fin_decade')
            if not debut or not fin:
                raise forms.ValidationError(_("Les dates de début et de fin de décade sont obligatoires."))
            if debut > fin:
                raise forms.ValidationError(_("Le début de la décade doit précéder sa fin."))
        return data  # Données nettoyées


class HistoriqueAcctForm(forms.Form):
    """Bloc 2 : Historique ou Extrait de compte (péage et pesage)."""

    # Seul le montant de l'extrait de compte est saisi (le montant global est supprimé de l'écran)
    montant_reel = forms.DecimalField(
        min_value=Decimal('0'), decimal_places=0, max_digits=15,
        label=_("Montant de l'extrait de compte (FCFA)"),  # Nouveau libellé
        help_text=_("Montant effectivement reversé (alimente le CSP)."),
    )
    image_historique = forms.ImageField(
        required=False, label=_("Document : historique ou extrait de compte"),
    )
    observations = forms.CharField(
        required=False, label=_("Observations"),
        widget=forms.Textarea(attrs={'rows': 2}),
    )

