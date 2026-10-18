# ===================================================================
# inventaire/forms_commandes.py - FORMULAIRES COMMANDES ET LIVRAISONS
# Application SUPPER - Gestion des commandes de tickets
# ===================================================================
"""
Ce fichier contient les formulaires pour le système de commandes:

- ParametresCommandeForm: Étape 1 - Sélection des paramètres
- SelectionPostesCommandeForm: Sélection des postes
- LivraisonCreationForm: Création d'une livraison
- SelectionRechargesForm: Sélection des recharges à associer

LOGIQUE MÉTIER:
- Gestion dynamique des champs période côté serveur (pas de JS)
- Sélection multiple des postes avec tout sélectionner/désélectionner
- Association des recharges imprimerie nationale aux livraisons
"""

from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

from accounts.models import Poste
from .models import HistoriqueStock, CouleurTicket
from .models_commandes import CommandeTickets, DetailCommandePoste, LivraisonTickets


class ParametresCommandeForm(forms.Form):
    """
    Formulaire Étape 1: Sélection des paramètres de la commande.
    La gestion dynamique des champs période est faite côté serveur.
    """
    
    # Sélection des postes (multiple)
    postes = forms.ModelMultipleChoiceField(
        queryset=Poste.objects.filter(is_active=True, type='peage'),
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input poste-checkbox'
        }),
        label=_("Postes de péage"),
        help_text=_("Sélectionnez les postes concernés par cette commande"),
        required=True
    )
    
    # Numéro de commande
    numero_commande = forms.ChoiceField(
        choices=[(i, f"{i}{'ère' if i == 1 else 'ème'} Commande") for i in range(1, 11)],
        label=_("Numéro de commande"),
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    # Exercice (année)
    exercice = forms.ChoiceField(
        label=_("Exercice (année)"),
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    # Type de période
    type_periode = forms.ChoiceField(
        choices=CommandeTickets.PERIODE_CHOICES,
        label=_("Type de période"),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_type_periode'
        })
    )
    
    # Champs conditionnels selon la période
    mois = forms.ChoiceField(
        choices=[('', '--- Sélectionnez un mois ---')] + list(CommandeTickets.MOIS_CHOICES),
        label=_("Mois"),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    trimestre = forms.ChoiceField(
        choices=[('', '--- Sélectionnez un trimestre ---')] + list(CommandeTickets.TRIMESTRE_CHOICES),
        label=_("Trimestre"),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    semestre = forms.ChoiceField(
        choices=[('', '--- Sélectionnez un semestre ---')] + list(CommandeTickets.SEMESTRE_CHOICES),
        label=_("Semestre"),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Observations ou commentaires (optionnel)'
        }),
        label=_("Description/Observations")
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Générer les choix d'exercice (année courante + 1 an avant et après)
        annee_courante = timezone.now().year
        self.fields['exercice'].choices = [
            (annee_courante - 1, str(annee_courante - 1)),
            (annee_courante, str(annee_courante)),
            (annee_courante + 1, str(annee_courante + 1)),
        ]
        self.fields['exercice'].initial = annee_courante
        
        # Ordonner les postes par région et nom
        self.fields['postes'].queryset = Poste.objects.filter(
            is_active=True, 
            type='peage'
        ).select_related('region').order_by('region__nom', 'nom')
    
    def clean(self):
        cleaned_data = super().clean()
        type_periode = cleaned_data.get('type_periode')
        mois = cleaned_data.get('mois')
        trimestre = cleaned_data.get('trimestre')
        semestre = cleaned_data.get('semestre')
        
        # Validation conditionnelle selon le type de période
        if type_periode == 'mensuelle':
            if not mois:
                self.add_error('mois', _("Veuillez sélectionner un mois"))
        elif type_periode == 'trimestrielle':
            if not trimestre:
                self.add_error('trimestre', _("Veuillez sélectionner un trimestre"))
        elif type_periode == 'semestrielle':
            if not semestre:
                self.add_error('semestre', _("Veuillez sélectionner un semestre"))
        
        return cleaned_data


class ConfirmationCommandeForm(forms.Form):
    """
    Formulaire de confirmation de la commande (Étape 2).
    Permet de valider ou modifier avant enregistrement.
    """
    
    confirmer = forms.BooleanField(
        required=True,
        label=_("Je confirme la création de cette commande"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    ecraser_existants = forms.BooleanField(
        required=False,
        label=_("Écraser les détails existants pour les postes déjà présents"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text=_("Si cochée, les postes déjà présents dans cette commande seront mis à jour")
    )


class LivraisonCreationForm(forms.Form):
    """
    Formulaire pour créer une livraison.
    Sélection de la commande, du poste et de la date.
    """
    
    commande = forms.ModelChoiceField(
        queryset=CommandeTickets.objects.filter(
            statut__in=['validee', 'en_cours']
        ).order_by('-exercice', '-numero_commande'),
        label=_("Commande"),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_commande'
        }),
        empty_label=_("--- Sélectionnez une commande ---")
    )
    
    poste = forms.ModelChoiceField(
        queryset=Poste.objects.none(),  # Sera rempli dynamiquement
        label=_("Poste de péage"),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_poste'
        }),
        empty_label=_("--- Sélectionnez d'abord une commande ---")
    )
    
    date_livraison = forms.DateField(
        label=_("Date de livraison"),
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    exercice_recharges = forms.ChoiceField(
        label=_("Exercice des recharges"),
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        help_text=_("Année des recharges à associer")
    )
    
    observations = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Observations (optionnel)'
        }),
        label=_("Observations")
    )
    
    def __init__(self, *args, **kwargs):
        commande_id = kwargs.pop('commande_id', None)
        super().__init__(*args, **kwargs)
        
        # Exercice pour les recharges
        annee_courante = timezone.now().year
        self.fields['exercice_recharges'].choices = [
            (annee_courante - 1, str(annee_courante - 1)),
            (annee_courante, str(annee_courante)),
        ]
        self.fields['exercice_recharges'].initial = annee_courante
        
        # Date par défaut = aujourd'hui
        self.fields['date_livraison'].initial = timezone.now().date()
        
        # Si une commande est pré-sélectionnée, filtrer les postes
        if commande_id:
            try:
                commande = CommandeTickets.objects.get(id=commande_id)
                postes_ids = commande.details.values_list('poste_id', flat=True)
                self.fields['poste'].queryset = Poste.objects.filter(
                    id__in=postes_ids
                ).select_related('region').order_by('nom')
                self.fields['commande'].initial = commande
            except CommandeTickets.DoesNotExist:
                pass
    
    def get_postes_pour_commande(self, commande_id):
        """Retourne les postes disponibles pour une commande donnée."""
        try:
            commande = CommandeTickets.objects.get(id=commande_id)
            postes_ids = commande.details.values_list('poste_id', flat=True)
            return Poste.objects.filter(
                id__in=postes_ids
            ).select_related('region').order_by('nom')
        except CommandeTickets.DoesNotExist:
            return Poste.objects.none()


class SelectionRechargesForm(forms.Form):
    """
    Formulaire pour sélectionner les recharges à associer à une livraison.
    Affiche les recharges imprimerie nationale disponibles pour le poste.
    """
    
    recharges = forms.ModelMultipleChoiceField(
        queryset=HistoriqueStock.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input recharge-checkbox'
        }),
        label=_("Recharges imprimerie nationale"),
        help_text=_("Sélectionnez les recharges à associer à cette livraison"),
        required=True
    )
    
    def __init__(self, *args, **kwargs):
        poste_id = kwargs.pop('poste_id', None)
        exercice = kwargs.pop('exercice', None)
        exclure_livrees = kwargs.pop('exclure_livrees', True)
        super().__init__(*args, **kwargs)
        
        if poste_id and exercice:
            # Filtrer les recharges imprimerie nationale pour ce poste et exercice
            queryset = HistoriqueStock.objects.filter(
                poste_id=poste_id,
                type_mouvement='CREDIT',
                type_stock='imprimerie_nationale',
                date_mouvement__year=exercice
            ).order_by('-date_mouvement')
            
            # Exclure les recharges déjà associées à des livraisons
            if exclure_livrees:
                livrees_ids = LivraisonTickets.objects.filter(
                    poste_id=poste_id
                ).values_list('historiques_associes__id', flat=True)
                queryset = queryset.exclude(id__in=livrees_ids)
            
            self.fields['recharges'].queryset = queryset


class ModificationCommandeForm(forms.ModelForm):
    """
    Formulaire de modification d'une commande existante.
    Limité aux champs modifiables après création.
    """
    
    class Meta:
        model = CommandeTickets
        fields = ['description', 'statut']
        widgets = {
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'statut': forms.Select(attrs={
                'class': 'form-select'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Limiter les statuts modifiables selon l'état actuel
        instance = kwargs.get('instance')
        if instance:
            if instance.statut == 'brouillon':
                self.fields['statut'].choices = [
                    ('brouillon', _('Brouillon')),
                    ('validee', _('Validée')),
                    ('annulee', _('Annulée')),
                ]
            elif instance.statut == 'validee':
                self.fields['statut'].choices = [
                    ('validee', _('Validée')),
                    ('annulee', _('Annulée')),
                ]
            elif instance.statut in ['en_cours', 'completee']:
                # Ne peut plus modifier le statut
                self.fields['statut'].disabled = True


class ModificationLivraisonForm(forms.ModelForm):
    """
    Formulaire de modification d'une livraison existante.
    """
    
    class Meta:
        model = LivraisonTickets
        fields = ['date_livraison', 'observations', 'statut']
        widgets = {
            'date_livraison': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'observations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
            'statut': forms.Select(attrs={
                'class': 'form-select'
            })
        }


class FiltreCommandesForm(forms.Form):
    """
    Formulaire de filtrage pour la liste des commandes.
    """
    
    exercice = forms.ChoiceField(
        required=False,
        label=_("Exercice"),
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm'
        })
    )
    
    numero_commande = forms.ChoiceField(
        choices=[('', 'Toutes')] + [(i, f"Commande {i}") for i in range(1, 11)],
        required=False,
        label=_("Numéro"),
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm'
        })
    )
    
    statut = forms.ChoiceField(
        choices=[('', 'Tous')] + list(CommandeTickets.STATUT_CHOICES),
        required=False,
        label=_("Statut"),
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm'
        })
    )
    
    type_periode = forms.ChoiceField(
        choices=[('', 'Toutes')] + list(CommandeTickets.PERIODE_CHOICES),
        required=False,
        label=_("Période"),
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Exercices disponibles
        annee_courante = timezone.now().year
        self.fields['exercice'].choices = [
            ('', 'Tous'),
            (annee_courante - 2, str(annee_courante - 2)),
            (annee_courante - 1, str(annee_courante - 1)),
            (annee_courante, str(annee_courante)),
            (annee_courante + 1, str(annee_courante + 1)),
        ]


class FiltreLivraisonsForm(forms.Form):
    """
    Formulaire de filtrage pour la liste des livraisons.
    """
    
    commande = forms.ModelChoiceField(
        queryset=CommandeTickets.objects.all().order_by('-exercice', '-numero_commande'),
        required=False,
        label=_("Commande"),
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm'
        }),
        empty_label=_("Toutes les commandes")
    )
    
    poste = forms.ModelChoiceField(
        queryset=Poste.objects.filter(is_active=True, type='peage').order_by('nom'),
        required=False,
        label=_("Poste"),
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm'
        }),
        empty_label=_("Tous les postes")
    )
    
    statut = forms.ChoiceField(
        choices=[('', 'Tous')] + list(LivraisonTickets.STATUT_CHOICES),
        required=False,
        label=_("Statut"),
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm'
        })
    )
    
    date_debut = forms.DateField(
        required=False,
        label=_("Date début"),
        widget=forms.DateInput(attrs={
            'class': 'form-control form-control-sm',
            'type': 'date'
        })
    )
    
    date_fin = forms.DateField(
        required=False,
        label=_("Date fin"),
        widget=forms.DateInput(attrs={
            'class': 'form-control form-control-sm',
            'type': 'date'
        })
    )