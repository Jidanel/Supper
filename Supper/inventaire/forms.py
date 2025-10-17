# Supper/inventaire/forms.py
from django import forms
from django.utils import timezone
from .models import *
from zoneinfo import ZoneInfo  
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from datetime import date, datetime
from decimal import Decimal
from accounts.models import *

class InventaireJournalierForm(forms.ModelForm):
    """Formulaire personnalisé pour la saisie d'inventaire"""
        
    class Meta:
        model = InventaireJournalier
        fields = ['poste', 'date', 'observations', 'modifiable_par_agent']
        widgets = {
            'poste': forms.Select(attrs={
                'class': 'form-control select2',
                'data-placeholder': 'Sélectionnez un poste'
            }),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'max': date.today().isoformat()
            }),
            'observations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Notes ou observations particulières (optionnel)'
            }),
            'modifiable_par_agent': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
        labels = {
            'poste': _('Poste de péage/pesage'),
            'date': _('Date de l\'inventaire'),
            'observations': _('Observations'),
            'modifiable_par_agent': _('Modifiable par l\'agent')
        }
        
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filtrer les postes selon les permissions de l'utilisateur
        if self.user:
            if hasattr(self.user, 'get_postes_accessibles'):
                self.fields['poste'].queryset = self.user.get_postes_accessibles()
            else:
                self.fields['poste'].queryset = Poste.objects.filter(is_active=True)

        # Si c'est une modification, désactiver les champs poste et date
        if self.instance.pk:
            self.fields['poste'].disabled = True
            self.fields['date'].disabled = True
            
            # Cacher le champ modifiable_par_agent si l'utilisateur n'est pas admin
            if self.user and not self.user.is_superuser:
                self.fields['modifiable_par_agent'].widget = forms.HiddenInput()
                        
        # Si validation, définir automatiquement la date/heure du Cameroun
        if self.instance and self.instance.valide:
            # Utilisation de zoneinfo au lieu de pytz
            cameroon_tz = ZoneInfo('Africa/Douala')
            self.initial['date_validation'] = timezone.now().astimezone(cameroon_tz)

    def clean_date(self):
        """Vérifie que la date est valide"""
        date_inventaire = self.cleaned_data['date']
        
        # Vérifier que la date n'est pas dans le futur
        if date_inventaire > date.today():
            raise ValidationError(_("La date ne peut pas être dans le futur"))
        
        # Pas de vérification de jour ouvert/fermé - toujours autorisé
        
        return date_inventaire
    
    def clean(self):
        """Validation globale du formulaire"""
        cleaned_data = super().clean()
        poste = cleaned_data.get('poste')
        date_inventaire = cleaned_data.get('date')
        
        if poste and date_inventaire:
            # Vérifier qu'un inventaire n'existe pas déjà pour ce poste et cette date
            if not self.instance.pk:  # Seulement pour la création
                if InventaireJournalier.objects.filter(
                    poste=poste, 
                    date=date_inventaire
                ).exists():
                    raise ValidationError(
                        _("Un inventaire existe déjà pour ce poste à cette date")
                    )
        
        # Vérifier les permissions de modification
        if self.instance.pk and not self.instance.peut_etre_modifie_par(self.user):
            raise ValidationError(
                _("Vous n'avez pas les permissions pour modifier cet inventaire")
            )
        
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
                
        if commit:
            instance.save()
        return instance

class DetailInventairePeriodeForm(forms.ModelForm):
    """
    Formulaire pour la saisie d'une période d'inventaire
    """
    
    class Meta:
        model = DetailInventairePeriode
        fields = ['periode', 'nombre_vehicules', 'observations_periode']
        widgets = {
            'periode': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'nombre_vehicules': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 5000,
                'placeholder': 'Nombre de véhicules'
            }),
            'observations_periode': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Observations (optionnel)',
                'maxlength': 200
            })
        }
        labels = {
            'periode': _('Période horaire'),
            'nombre_vehicules': _('Nombre de véhicules'),
            'observations_periode': _('Observations')
        }
    
    def __init__(self, *args, **kwargs):
        self.inventaire = kwargs.pop('inventaire', None)
        super().__init__(*args, **kwargs)
        
        # Filtrer les périodes déjà saisies
        if self.inventaire and not self.instance.pk:
            periodes_existantes = self.inventaire.details_periodes.values_list(
                'periode', flat=True
            )
            # Créer les choix en excluant les périodes déjà saisies
            choix_periodes = [
                (choice[0], choice[1]) 
                for choice in PeriodeHoraire.choices 
                if choice[0] not in periodes_existantes
            ]
            self.fields['periode'].choices = choix_periodes
    
    def clean_nombre_vehicules(self):
        """Validation du nombre de véhicules"""
        nombre = self.cleaned_data['nombre_vehicules']
        
        if nombre < 0:
            raise ValidationError(_("Le nombre de véhicules ne peut pas être négatif"))
        
        if nombre > 5000:
            raise ValidationError(
                _("Le nombre de véhicules semble trop élevé (max: 5000)."
                  "Vérifiez votre saisie.")
            )
        
        return nombre
DetailInventairePeriodeFormSet = forms.inlineformset_factory(
    InventaireJournalier,
    DetailInventairePeriode,
    form=DetailInventairePeriodeForm,
    extra=0,  # Pas de formulaires vides supplémentaires
    can_delete=False,
    min_num=10,  # 10 périodes minimum (8h-18h)
    max_num=10,
    validate_min=True,
    validate_max=True
)
class SaisieRapideInventaireForm(forms.Form):
    """
    Formulaire pour la saisie rapide de toutes les périodes d'un inventaire
    """
    
    poste = forms.ModelChoiceField(
        queryset=Poste.objects.filter(is_active=True),
        label=_('Poste'),
        widget=forms.Select(attrs={
            'class': 'form-control select2',
            'data-placeholder': 'Sélectionnez un poste'
        })
    )
    
    date = forms.DateField(
        label=_('Date'),
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'max': date.today().isoformat()
        })
    )
    
    # Génération dynamique des champs pour chaque période
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filtrer les postes
        if self.user and hasattr(self.user, 'get_postes_accessibles'):
            self.fields['poste'].queryset = self.user.get_postes_accessibles()
        
        # Créer un champ pour chaque période
        for periode_code, periode_label in PeriodeHoraire.choices:
            field_name = f'periode_{periode_code}'
            self.fields[field_name] = forms.IntegerField(
                required=False,
                label=periode_label,
                min_value=0,
                max_value=5000,
                widget=forms.NumberInput(attrs={
                    'class': 'form-control periode-input',
                    'placeholder': '0',
                    'data-periode': periode_code
                })
            )
        
        # Champ observations global
        self.fields['observations'] = forms.CharField(
            required=False,
            label=_('Observations'),
            widget=forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observations générales (optionnel)'
            })
        )
    
    def clean(self):
        """Validation du formulaire"""
        cleaned_data = super().clean()
        poste = cleaned_data.get('poste')
        date_inventaire = cleaned_data.get('date')
        
        if poste and date_inventaire:
            # Vérifier qu'un inventaire n'existe pas déjà
            if InventaireJournalier.objects.filter(
                poste=poste, 
                date=date_inventaire
            ).exists():
                raise ValidationError(
                    _("Un inventaire existe déjà pour ce poste à cette date")
                )
        
        # Vérifier qu'au moins une période a été saisie
        periodes_saisies = False
        for field_name, value in cleaned_data.items():
            if field_name.startswith('periode_') and value is not None and value > 0:
                periodes_saisies = True
                break
        
        if not periodes_saisies:
            raise ValidationError(
                _("Veuillez saisir au moins une période")
            )
        
        return cleaned_data
    
    def save(self):
        """Créer l'inventaire et ses détails"""
        # Créer l'inventaire principal
        inventaire = InventaireJournalier.objects.create(
            poste=self.cleaned_data['poste'],
            date=self.cleaned_data['date'],
            agent_saisie=self.user,
            observations=self.cleaned_data.get('observations', '')
        )
        
        # Créer les détails par période
        for field_name, value in self.cleaned_data.items():
            if field_name.startswith('periode_') and value is not None and value > 0:
                periode_code = field_name.replace('periode_', '')
                DetailInventairePeriode.objects.create(
                    inventaire=inventaire,
                    periode=periode_code,
                    nombre_vehicules=value
                )
        
        # Recalculer les totaux
        inventaire.recalculer_totaux()
        
        return inventaire


class RecetteJournaliereForm(forms.ModelForm):
    """
    Formulaire personnalisé pour RecetteJournaliere avec widget calendrier
    """
    
    # Champ pour lier automatiquement à un inventaire existant
    lier_inventaire = forms.BooleanField(
        required=False,
        label=_("Lier à l'inventaire du jour"),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'checked': True
        }),
        help_text=_("Cochez pour lier automatiquement à l'inventaire existant")
    )

    class Meta:
        model = RecetteJournaliere
        fields = ['poste', 'date', 'montant_declare', 'observations']
        
        widgets = {
            'poste': forms.Select(attrs={
                'class': 'form-control select2',
                'data-placeholder': 'Sélectionnez un poste'
            }),

            'date': forms.DateInput(
                attrs={
                    'type': 'date',  # Widget calendrier HTML5
                    'class': 'form-control',
                    'placeholder': 'Sélectionner une date',
                    'style': 'max-width: 200px;',
                    'max': date.today().isoformat()
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
            'observations': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Observations sur cette recette (optionnel)'
                }
            )
        }
        
        labels = {
            'poste': 'Poste *',
            'date': 'Date de la recette *',
            'montant_declare': 'Montant déclaré (FCFA) *',
            'observations': 'Observations',
        }
        
        help_texts = {
            'date': 'Cliquez pour ouvrir le calendrier et sélectionner la date',
            'montant_declare': 'Recette déclarée par le chef de poste en FCFA',
            'observations': 'Commentaires optionnels sur cette recette',
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filtrer les postes selon les permissions
        if self.user:
            if hasattr(self.user, 'get_postes_accessibles'):
                self.fields['poste'].queryset = self.user.get_postes_accessibles()
            else:
                self.fields['poste'].queryset = Poste.objects.filter(is_active=True)
        
        # Si modification, désactiver poste et date
        if self.instance.pk:
            self.fields['poste'].disabled = True
            self.fields['date'].disabled = True
            self.fields.pop('lier_inventaire')
        
        # Définir la date d'aujourd'hui par défaut
        if not self.instance.pk:
            self.fields['date'].initial = timezone.now().date()
    
    def clean_date(self):
        """Validation de la date"""
        date_recette = self.cleaned_data['date']
        
        if date_recette > date.today():
            raise ValidationError(_("La date ne peut pas être dans le futur"))
        
        return date_recette
    
    def clean_montant_declare(self):
        """Validation du montant déclaré"""
        montant = self.cleaned_data['montant_declare']
        
        if montant < 0:
            raise ValidationError(_("Le montant ne peut pas être négatif"))
        
        # Alerte si montant très élevé (à ajuster selon contexte)
        if montant > Decimal('100000000'):  # 100 millions FCFA
            raise ValidationError(
                _("Le montant semble trop élevé. Vérifiez votre saisie ou contactez l'administrateur")
            )
        
        return montant
    
    def clean(self):
        """Validation globale"""
        cleaned_data = super().clean()
        poste = cleaned_data.get('poste')
        date_recette = cleaned_data.get('date')
        
        if poste and date_recette:
            # Vérifier qu'une recette n'existe pas déjà
            if not self.instance.pk:
                if RecetteJournaliere.objects.filter(
                    poste=poste, 
                    date=date_recette
                ).exists():
                    raise ValidationError(
                        _("Une recette existe déjà pour ce poste à cette date")
                    )
        
        return cleaned_data
    
    def save(self, commit=True):
        """Sauvegarde avec liaison automatique à l'inventaire"""
        instance = super().save(commit=False)
        
        # Lier l'inventaire si demandé et si création
        if not self.instance.pk and self.cleaned_data.get('lier_inventaire'):
            try:
                inventaire = InventaireJournalier.objects.get(
                    poste=instance.poste,
                    date=instance.date
                )
                instance.inventaire_associe = inventaire
            except InventaireJournalier.DoesNotExist:
                pass
        
        # Définir le chef de poste
        if self.user:
            instance.chef_poste = self.user
        
        if commit:
            instance.save()
        
        return instance


class ConfigurationJourForm(forms.ModelForm):
    """
    Formulaire pour ConfigurationJour avec widget calendrier et validation robuste
    """
    
    class Meta:
        model = ConfigurationJour
        fields = ['date', 'statut', 'commentaire']
        
        widgets = {
            'date': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control calendrier-widget',
                    'style': 'max-width: 200px;'
                }
            ),
            'statut': forms.Select(
                attrs={
                    'class': 'form-control',
                    'style': 'max-width: 200px;'
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
            'date': _('Date'),
            'statut': _('Statut du jour'),
            'commentaire': _('Commentaire')
        }
    

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

class ConfigurationMultiJoursForm(forms.Form):
    """
    Formulaire pour configurer plusieurs jours en une fois
    """
    
    date_debut = forms.DateField(
        label=_('Date de début'),
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    date_fin = forms.DateField(
        label=_('Date de fin'),
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    statut = forms.ChoiceField(
        choices=StatutJour.choices,
        label=_('Statut à appliquer'),
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    exclure_weekends = forms.BooleanField(
        required=False,
        label=_('Exclure les weekends'),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    commentaire = forms.CharField(
        required=False,
        label=_('Commentaire'),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3
        })
    )
    
    def clean(self):
        """Validation du formulaire"""
        cleaned_data = super().clean()
        date_debut = cleaned_data.get('date_debut')
        date_fin = cleaned_data.get('date_fin')
        
        if date_debut and date_fin:
            if date_debut > date_fin:
                raise ValidationError(
                    _("La date de début doit être avant la date de fin")
                )
            
            # Limiter à 365 jours maximum
            delta = (date_fin - date_debut).days
            if delta > 365:
                raise ValidationError(
                    _("La période ne peut pas dépasser 365 jours")
                )
        
        return cleaned_data


# ===================================================================
# FORMULAIRES PROGRAMMATION
# ===================================================================

class ProgrammationInventaireForm(forms.Form):
    """
    Formulaire pour programmer des inventaires mensuels
    """
    
    mois = forms.DateField(
        label="Mois à programmer",
        widget=forms.DateInput(attrs={
            'type': 'month',
            'class': 'form-control',
            'required': True
        }),
        help_text="Sélectionnez le mois pour la programmation"
    )
    
    motif = forms.ChoiceField(
        label="Motif de l'inventaire",
        choices=MotifInventaire.choices,
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'motif-select',
            'required': True
        })
    )
    
    # Ce champ sera rempli dynamiquement via JavaScript
    postes = forms.MultipleChoiceField(
        label="Postes à programmer",
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'poste-checkbox'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Charger dynamiquement les postes actifs
        self.fields['postes'].choices = [
            (poste.id, f"{poste.nom} ({poste.code})")
            for poste in Poste.objects.filter(is_active=True).order_by('nom')
        ]
    
    def clean_mois(self):
        """Valide le mois sélectionné"""
        mois = self.cleaned_data['mois']
        
        # S'assurer que c'est le premier jour du mois
        if mois.day != 1:
            mois = mois.replace(day=1)
        
        # Vérifier que le mois n'est pas trop dans le passé
        today = date.today()
        if mois < today.replace(day=1):
            # Autoriser seulement le mois précédent
            mois_precedent = today.replace(day=1)
            if mois.month == 12:
                mois_precedent = mois_precedent.replace(year=mois_precedent.year-1, month=1)
            else:
                mois_precedent = mois_precedent.replace(month=mois_precedent.month-1)
            
            if mois < mois_precedent:
                raise ValidationError("Vous ne pouvez pas programmer pour un mois si ancien")
        
        return mois
    
    def clean_postes(self):
        """Valide les postes sélectionnés"""
        postes_ids = self.cleaned_data.get('postes', [])
        
        if not postes_ids:
            raise ValidationError("Veuillez sélectionner au moins un poste")
        
        # Vérifier que les postes existent et sont actifs
        postes_valides = Poste.objects.filter(
            id__in=postes_ids,
            is_active=True
        ).values_list('id', flat=True)
        
        postes_invalides = set(postes_ids) - set(str(p) for p in postes_valides)
        if postes_invalides:
            raise ValidationError(f"Postes invalides: {postes_invalides}")
        
        return postes_ids
    
    def clean(self):
        """Validation globale du formulaire"""
        cleaned_data = super().clean()
        mois = cleaned_data.get('mois')
        motif = cleaned_data.get('motif')
        postes_ids = cleaned_data.get('postes', [])
        
        if mois and motif and postes_ids:
            # Vérifier les doublons
            programmations_existantes = ProgrammationInventaire.objects.filter(
                poste_id__in=postes_ids,
                mois=mois,
                motif=motif,
                actif=True
            ).values_list('poste__nom', flat=True)
            
            if programmations_existantes:
                raise ValidationError(
                    f"Des programmations existent déjà pour: {', '.join(programmations_existantes)}"
                )
        
        return cleaned_data
    
    def save(self, user):
        """
        Crée les programmations pour tous les postes sélectionnés
        Retourne la liste des programmations créées
        """
        mois = self.cleaned_data['mois']
        motif = self.cleaned_data['motif']
        postes_ids = self.cleaned_data['postes']
        
        programmations_creees = []
        
        for poste_id in postes_ids:
            try:
                poste = Poste.objects.get(id=poste_id)
                
                # Créer la programmation
                prog = ProgrammationInventaire(
                    poste=poste,
                    mois=mois,
                    motif=motif,
                    cree_par=user,
                    actif=True
                )
                
                # Ajouter les données spécifiques selon le motif
                if motif == MotifInventaire.TAUX_DEPERDITION:
                    # Récupérer le taux depuis la requête si disponible
                    taux_key = f'taux_{poste_id}'
                    if taux_key in self.data:
                        try:
                            prog.taux_deperdition_precedent = Decimal(self.data[taux_key])
                        except:
                            pass
                
                elif motif == MotifInventaire.GRAND_STOCK:
                    # Récupérer le stock depuis la requête si disponible
                    stock_key = f'stock_{poste_id}'
                    if stock_key in self.data:
                        try:
                            prog.stock_restant = int(self.data[stock_key])
                        except:
                            pass
                
                # Sauvegarder (les calculs automatiques se font dans save())
                prog.save()
                programmations_creees.append(prog)
                
            except Poste.DoesNotExist:
                continue
            except Exception as e:
                # Logger l'erreur mais continuer avec les autres postes
                import logging
                logger = logging.getLogger('supper')
                logger.error(f"Erreur création programmation pour poste {poste_id}: {str(e)}")
        
        return programmations_creees
# ===================================================================
# FORMULAIRES INVENTAIRE MENSUEL
# ===================================================================

class InventaireMensuelForm(forms.ModelForm):
    """
    Formulaire pour la gestion des inventaires mensuels
    """
    
    class Meta:
        model = InventaireMensuel
        fields = [
            'poste', 'programmation', 'motif', 'taux_deperdition_precedent',
            'risque_baisse_annuel', 'date_epuisement_stock', 'mois', 'annee', 
            'description', 'nombre_jours_saisis', 'actif'
        ]
        widgets = {
            'poste': forms.Select(attrs={
                'class': 'form-control select2'
            }),
            'programmation': forms.Select(attrs={
                'class': 'form-control select2'
            }),
            'motif': forms.Select(attrs={
                'class': 'form-control'
            }),
            'taux_deperdition_precedent': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': 0
            }),
            'risque_baisse_annuel': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'date_epuisement_stock': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'mois': forms.Select(attrs={
                'class': 'form-control'
            }),
            'annee': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 2020,
                'max': 2099
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4
            }),
            'nombre_jours_saisis': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'actif': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }


# class QuittancementForm(forms.ModelForm):
#     """
#     Formulaire pour saisir un quittancement
#     Gère les champs conditionnels selon le type de déclaration
#     """
    
#     class Meta:
#         model = Quittancement
#         fields = [
#             'numero_quittance',
#             'date_quittancement',
#             'poste',
#             'montant',
#             'date_recette',           # Pour type JOUR
#             'date_debut_decade',      # Pour type DÉCADE
#             'date_fin_decade',        # Pour type DÉCADE
#             'image_quittance',
#         ]
#         widgets = {
#             'numero_quittance': forms.TextInput(attrs={
#                 'class': 'form-control',
#                 'placeholder': 'Ex: Q-2025-001',
#             }),
#             'date_quittancement': forms.DateInput(attrs={
#                 'class': 'form-control',
#                 'type': 'date',
#             }),
#             'poste': forms.Select(attrs={
#                 'class': 'form-select',
#             }),
#             'montant': forms.NumberInput(attrs={
#                 'class': 'form-control',
#                 'step': '1',
#                 'min': '0',
#                 'placeholder': '0',
#             }),
#             'date_recette': forms.DateInput(attrs={
#                 'class': 'form-control date-recette-field',
#                 'type': 'date',
#             }),
#             'date_debut_decade': forms.DateInput(attrs={
#                 'class': 'form-control date-decade-field',
#                 'type': 'date',
#             }),
#             'date_fin_decade': forms.DateInput(attrs={
#                 'class': 'form-control date-decade-field',
#                 'type': 'date',
#             }),
#             'observations': forms.Textarea(attrs={
#                 'class': 'form-control',
#                 'rows': 3,
#                 'placeholder': 'Observations (optionnel)',
#             }),
#             'fichier_quittance': forms.FileInput(attrs={
#                 'class': 'form-control',
#             }),
#         }
    
#     def __init__(self, *args, **kwargs):
#         user = kwargs.pop('user', None)
#         type_declaration = kwargs.pop('type_declaration', None)  # NOUVEAU PARAMÈTRE
#         super().__init__(*args, **kwargs)
        
#         # Stocker le type pour validation
#         self.type_declaration = type_declaration
        
#         # Gestion des postes selon permissions
#         if user:
#             if user.is_admin:
#                 self.fields['poste'].queryset = Poste.objects.filter(is_active=True)
#             elif user.poste_affectation:
#                 self.fields['poste'].queryset = Poste.objects.filter(
#                     id=user.poste_affectation.id
#                 )
#                 self.fields['poste'].initial = user.poste_affectation
#                 self.fields['poste'].widget = forms.HiddenInput()
#             else:
#                 self.fields['poste'].queryset = Poste.objects.none()
        
#         # LOGIQUE CONDITIONNELLE SELON TYPE DE DÉCLARATION
#         if type_declaration == 'journaliere':
#             # Type JOUR : date_recette obligatoire, décades désactivées
#             self.fields['date_recette'].required = True
#             self.fields['date_debut_decade'].required = False
#             self.fields['date_fin_decade'].required = False
            
#             # Masquer visuellement les champs décade
#             self.fields['date_debut_decade'].widget.attrs['style'] = 'display:none;'
#             self.fields['date_fin_decade'].widget.attrs['style'] = 'display:none;'
            
#         elif type_declaration == 'decade':
#             # Type DÉCADE : décades obligatoires, date_recette désactivée
#             self.fields['date_recette'].required = False
#             self.fields['date_debut_decade'].required = True
#             self.fields['date_fin_decade'].required = True
            
#             # Masquer visuellement le champ date_recette
#             self.fields['date_recette'].widget.attrs['style'] = 'display:none;'
        
#         else:
#             # Par défaut : tous optionnels
#             self.fields['date_recette'].required = False
#             self.fields['date_debut_decade'].required = False
#             self.fields['date_fin_decade'].required = False
    
#     def clean(self):
#         cleaned_data = super().clean()
        
#         # Validation selon type de déclaration
#         if self.type_declaration == 'journaliere':
#             # Vérifier que date_recette est fournie
#             if not cleaned_data.get('date_recette'):
#                 raise forms.ValidationError(
#                     "La date de recette est obligatoire pour une déclaration journalière"
#                 )
            
#             # Nettoyer les champs décade
#             cleaned_data['date_debut_decade'] = None
#             cleaned_data['date_fin_decade'] = None
        
#         elif self.type_declaration == 'decade':
#             # Vérifier que les dates de décade sont fournies
#             date_debut = cleaned_data.get('date_debut_decade')
#             date_fin = cleaned_data.get('date_fin_decade')
            
#             if not date_debut:
#                 raise forms.ValidationError(
#                     "La date de début de décade est obligatoire"
#                 )
            
#             if not date_fin:
#                 raise forms.ValidationError(
#                     "La date de fin de décade est obligatoire"
#                 )
            
#             # Vérifier cohérence des dates
#             if date_debut and date_fin and date_debut > date_fin:
#                 raise forms.ValidationError(
#                     "La date de début doit être antérieure à la date de fin"
#                 )
            
#             # Nettoyer le champ date_recette
#             cleaned_data['date_recette'] = None
        
#         return cleaned_data

# Dans inventaire/forms.py - Formulaire complet pour Quittancement

class QuittancementForm(forms.ModelForm):
    """
    Formulaire pour saisir un quittancement
    Gère les champs conditionnels selon le type de déclaration
    """
    
    class Meta:
        model = Quittancement
        fields = [
            'numero_quittance',
            'date_quittancement', 
            'poste',
            'montant',
            'date_recette',           # Pour type JOURNALIERE
            'date_debut_decade',      # Pour type DÉCADE
            'date_fin_decade',        # Pour type DÉCADE
            'observations',           # AJOUT du champ observations
            'image_quittance',
        ]
        widgets = {
            'numero_quittance': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: H12345678',
            }),
            'date_quittancement': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'max': '9999-12-31',  # Pour éviter les problèmes de validation
            }),
            'poste': forms.Select(attrs={
                'class': 'form-select',
            }),
            'montant': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '1',
                'min': '0',
                'placeholder': '0',
            }),
            'date_recette': forms.DateInput(attrs={
                'class': 'form-control date-recette-field',
                'type': 'date',
            }),
            'date_debut_decade': forms.DateInput(attrs={
                'class': 'form-control date-decade-field',
                'type': 'date',
            }),
            'date_fin_decade': forms.DateInput(attrs={
                'class': 'form-control date-decade-field',
                'type': 'date',
            }),
            'observations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observations (optionnel)',
            }),
            'image_quittance': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*,.pdf',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        type_declaration = kwargs.pop('type_declaration', None)
        super().__init__(*args, **kwargs)
        
        # Stocker le type pour validation
        self.type_declaration = type_declaration
        
        # Gestion des postes selon permissions
        if user:
            if user.is_admin:
                self.fields['poste'].queryset = Poste.objects.filter(is_active=True)
            elif user.poste_affectation:
                self.fields['poste'].queryset = Poste.objects.filter(
                    id=user.poste_affectation.id
                )
                self.fields['poste'].initial = user.poste_affectation
            else:
                self.fields['poste'].queryset = Poste.objects.none()
        
        # LOGIQUE CONDITIONNELLE SELON TYPE DE DÉCLARATION
        if type_declaration == 'journaliere':
            # Type JOUR : date_recette obligatoire, décades désactivées
            self.fields['date_recette'].required = True
            self.fields['date_debut_decade'].required = False
            self.fields['date_fin_decade'].required = False
            
        elif type_declaration == 'decade':
            # Type DÉCADE : décades obligatoires, date_recette désactivée
            self.fields['date_recette'].required = False
            self.fields['date_debut_decade'].required = True
            self.fields['date_fin_decade'].required = True
        
        else:
            # Par défaut : tous optionnels
            self.fields['date_recette'].required = False
            self.fields['date_debut_decade'].required = False
            self.fields['date_fin_decade'].required = False
        
        # Le champ observations est toujours optionnel
        self.fields['observations'].required = False
        
        # L'image est optionnelle
        self.fields['image_quittance'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        from django.utils import timezone
        
        today = timezone.now().date()
        
        # Vérifier les dates futures
        date_quittancement = cleaned_data.get('date_quittancement')
        if date_quittancement and date_quittancement > today:
            self.add_error('date_quittancement', "La date de quittancement ne peut pas être dans le futur.")
        
        # Validation selon type de déclaration
        if self.type_declaration == 'journaliere':
            date_recette = cleaned_data.get('date_recette')
            
            if not date_recette:
                self.add_error('date_recette', "La date de recette est obligatoire pour une déclaration journalière.")
            elif date_recette > today:
                self.add_error('date_recette', "La date de recette ne peut pas être dans le futur.")
            
            # Vérifier l'unicité pour ce jour et ce poste
            if date_recette and cleaned_data.get('poste'):
                existing = Quittancement.objects.filter(
                    poste=cleaned_data['poste'],
                    type_declaration='journaliere',
                    date_recette=date_recette
                ).exclude(pk=self.instance.pk if self.instance.pk else None)
                
                if existing.exists():
                    self.add_error('date_recette', 
                        f"Un quittancement existe déjà pour le {date_recette.strftime('%d/%m/%Y')} sur ce poste.")
            
            # Nettoyer les champs décade
            cleaned_data['date_debut_decade'] = None
            cleaned_data['date_fin_decade'] = None
        
        elif self.type_declaration == 'decade':
            date_debut = cleaned_data.get('date_debut_decade')
            date_fin = cleaned_data.get('date_fin_decade')
            
            if not date_debut:
                self.add_error('date_debut_decade', "La date de début de décade est obligatoire.")
            elif date_debut > today:
                self.add_error('date_debut_decade', "La date de début ne peut pas être dans le futur.")
            
            if not date_fin:
                self.add_error('date_fin_decade', "La date de fin de décade est obligatoire.")
            elif date_fin > today:
                self.add_error('date_fin_decade', "La date de fin ne peut pas être dans le futur.")
            
            # Vérifier cohérence des dates
            if date_debut and date_fin and date_debut > date_fin:
                self.add_error('date_fin_decade', "La date de fin doit être après la date de début.")
            
            # Vérifier les chevauchements pour ce poste
            if date_debut and date_fin and cleaned_data.get('poste'):
                chevauchements = Quittancement.objects.filter(
                    poste=cleaned_data['poste'],
                    type_declaration='decade'
                ).exclude(pk=self.instance.pk if self.instance.pk else None)
                
                for q in chevauchements:
                    if (date_debut <= q.date_fin_decade and date_fin >= q.date_debut_decade):
                        self.add_error('date_debut_decade',
                            f"Cette période chevauche avec le quittancement {q.numero_quittance} "
                            f"({q.date_debut_decade.strftime('%d/%m/%Y')} au "
                            f"{q.date_fin_decade.strftime('%d/%m/%Y')})")
                        break
            
            # Nettoyer le champ date_recette
            cleaned_data['date_recette'] = None
        
        return cleaned_data
    
class JustificationEcartForm(forms.ModelForm):
    """Formulaire pour justifier un écart"""
    
    class Meta:
        model = JustificationEcart
        fields = ['justification']
        widgets = {
            'justification': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Expliquez en détail les raisons de l\'écart constaté...'
            })
        }
