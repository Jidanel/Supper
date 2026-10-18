# ===================================================================
# inventaire/forms_incident.py - Formulaires pour la gestion des incidents SUPPER
# VERSION SIMPLIFIÉE
# À AJOUTER dans le dossier inventaire/
# ===================================================================
"""
Formulaires pour la création et le traitement des incidents.

2 formulaires seulement:
    - IncidentCreationForm: Pour créer un incident (tous utilisateurs)
    - IncidentReponseForm: Pour la réponse admin (traiter/rejeter/complément)
"""

from django import forms
from django.utils.translation import gettext_lazy as _
from .models_incident import Incident, PrioriteIncident, CategorieIncident

import logging
logger = logging.getLogger('supper')


class IncidentCreationForm(forms.ModelForm):
    """
    Formulaire de création d'un nouvel incident.
    Accessible à tous les utilisateurs authentifiés.
    """
    
    class Meta:
        model = Incident
        fields = ['sujet', 'description', 'categorie', 'priorite']
        widgets = {
            'sujet': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Ex: Impossible de saisir une recette'),
                'maxlength': '200',
                'required': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': _('Décrivez en détail le problème rencontré, les étapes pour le reproduire, les messages d\'erreur éventuels...'),
                'required': True,
            }),
            'categorie': forms.Select(attrs={
                'class': 'form-select',
            }),
            'priorite': forms.Select(attrs={
                'class': 'form-select',
            }),
        }
        labels = {
            'sujet': _('Sujet de l\'incident'),
            'description': _('Description détaillée'),
            'categorie': _('Catégorie'),
            'priorite': _('Priorité'),
        }
        help_texts = {
            'sujet': _('Résumez le problème en une phrase concise'),
            'description': _('Plus vous donnez de détails, plus le traitement sera rapide'),
            'categorie': _('Sélectionnez la catégorie la plus appropriée'),
            'priorite': _('Utilisez "Critique" uniquement pour les blocages majeurs'),
        }
    
    def clean_sujet(self):
        """Validation du sujet"""
        sujet = self.cleaned_data.get('sujet', '').strip()
        if len(sujet) < 10:
            raise forms.ValidationError(
                _("Le sujet doit contenir au moins 10 caractères.")
            )
        return sujet
    
    def clean_description(self):
        """Validation de la description"""
        description = self.cleaned_data.get('description', '').strip()
        if len(description) < 20:
            raise forms.ValidationError(
                _("La description doit contenir au moins 20 caractères.")
            )
        return description


class IncidentReponseForm(forms.Form):
    """
    Formulaire simple pour la réponse de l'administrateur.
    Utilisé pour: Traiter, Rejeter, Demander complément.
    """
    
    reponse = forms.CharField(
        label=_("Réponse / Commentaire"),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('Votre réponse ou commentaire...'),
            'required': True,
        }),
        min_length=10,
        help_text=_("Minimum 10 caractères requis.")
    )
    
    def clean_reponse(self):
        """Validation de la réponse"""
        reponse = self.cleaned_data.get('reponse', '').strip()
        if len(reponse) < 10:
            raise forms.ValidationError(
                _("La réponse doit contenir au moins 10 caractères.")
            )
        return reponse