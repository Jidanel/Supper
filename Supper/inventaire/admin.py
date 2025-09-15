# ===================================================================
# inventaire/admin.py - Interface admin pour les inventaires CORRIGÉE
# VERSION COMPLÈTE AVEC TOUTES LES CLASSES NÉCESSAIRES
# ===================================================================
from django.utils.translation import gettext_lazy as _
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.http import HttpResponse
from django import forms
from datetime import date
from django.utils.html import format_html
from django.shortcuts import  redirect
from .models import *
import csv
from django.urls import path
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from .widgets import InventaireMensuelForm
import json
from .widgets import CalendrierJoursWidget
from .forms import RecetteJournaliereAdminForm, ConfigurationJourForm
import logging
from django.contrib import messages

logger = logging.getLogger('supper')

# ===================================================================
# FORMULAIRES PERSONNALISÉS
# ===================================================================

class DetailInventairePeriodeInlineForm(forms.ModelForm):
    """Formulaire pour la saisie inline des périodes"""
    class Meta:
        model = DetailInventairePeriode
        extra = 1
        max_num = 10  # Maximum 10 périodes (8h-18h)
        fields = ['periode', 'nombre_vehicules', 'observations_periode']
        readonly_fields = ['heure_saisie', 'modifie_le']
        widgets = {
            'periode': forms.Select(attrs={
                'class': 'form-control',
                'style': 'width: 120px;'
            }),
            'nombre_vehicules': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '5000',
                'style': 'width: 100px;',
                'placeholder': '0'
            }),
            'observations_periode': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Observations (optionnel)',
                'style': 'width: 300px;'
            })
        }
    def get_readonly_fields(self, request, obj=None):
        """Rendre les champs readonly si l'inventaire n'est plus modifiable par l'agent"""
        if obj and not obj.modifiable_par_agent and not request.user.is_superuser:
            return self.fields + self.readonly_fields
        return self.readonly_fields
    
    def has_delete_permission(self, request, obj=None):
        """Empêcher la suppression si non modifiable par l'agent"""
        if obj and not obj.modifiable_par_agent and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

class InventaireJournalierForm(forms.ModelForm):
    """Formulaire principal pour l'inventaire"""
    class Meta:
        model = InventaireJournalier
        fields = '__all__'
        widgets = {
            'date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'observations': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Notes ou observations sur cet inventaire'
            }),
            'poste': forms.Select(attrs={
                'class': 'form-control'
            }),
            'agent_saisie': forms.Select(attrs={
                'class': 'form-control'
            })
        }

# ===================================================================
# INLINES
# ===================================================================

class DetailInventairePeriodeInline(admin.TabularInline):
    """Inline pour saisir les véhicules par période directement dans l'inventaire"""
    model = DetailInventairePeriode
    form = DetailInventairePeriodeInlineForm
    extra = 10  # Afficher 10 lignes vides (pour les 10 périodes)
    max_num = 10  # Maximum 10 périodes
    can_delete = True
    
    # Ordre d'affichage des périodes
    ordering = ['periode']
    
    # Personnalisation de l'affichage
    fields = ['periode', 'nombre_vehicules', 'observations_periode']
    readonly_fields = ('heure_saisie', 'modifie_le')
    
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        
        # Si c'est un nouvel inventaire, pré-remplir avec toutes les périodes
        if not obj:
            # Définir les choix de périodes dans l'ordre
            PERIODES = [
                ('08h-09h', '08h-09h'),
                ('09h-10h', '09h-10h'),
                ('10h-11h', '10h-11h'),
                ('11h-12h', '11h-12h'),
                ('12h-13h', '12h-13h'),
                ('13h-14h', '13h-14h'),
                ('14h-15h', '14h-15h'),
                ('15h-16h', '15h-16h'),
                ('16h-17h', '16h-17h'),
                ('17h-18h', '17h-18h'),
            ]
            
            # Configurer le formset avec les périodes prédéfinies
            formset.extra = len(PERIODES)
            
        return formset
    
    def get_queryset(self, request):
        return super().get_queryset(request).order_by('periode')

# ===================================================================
# ADMIN CLASSES
# ===================================================================

@admin.register(ConfigurationJour)
class ConfigurationJourAdmin(admin.ModelAdmin):
    # 🔧 AJOUTER le formulaire personnalisé
    form = ConfigurationJourForm
    
    list_display = [
        'date_formatee', 'poste_display', 'est_impertinent', 
        'commentaire_court', 'cree_par', 'date_creation'
    ]
    list_filter = ['statut', 'date', 'poste__region', 'cree_par']
    search_fields = ['commentaire', 'date', 'poste__nom', 'poste__code']
    date_hierarchy = 'date'
    ordering = ['-date']
    
    list_filter = ['statut', 'date', 'poste__region', 'cree_par']
    search_fields = ['commentaire', 'date', 'poste__nom', 'poste__code']
    date_hierarchy = 'date'
    ordering = ['-date']
    
    fieldsets = (
        (_('Jour à marquer'), {
            'fields': ('date', 'poste', 'statut', 'commentaire'),
            'description': _('Marquer un jour comme impertinent si nécessaire')
        }),
        (_('Informations système'), {
            'fields': ('cree_par', 'date_creation'),
            'classes': ('collapse',)
        }),
    )
    
    # Retirer les champs de permission de saisie
    exclude = ['permet_saisie_inventaire', 'permet_saisie_recette']
    readonly_fields = ['cree_par', 'date_creation']

    class Media:
        css = {
            'all': ('css/calendrier-widget.css',)
        }
        js = ('js/calendrier-widget.js',)
    
    def poste_display(self, obj):
        """Affiche le poste ou 'Tous'"""
        if obj.poste:
            return format_html(
                '<strong>{}</strong> ({})',
                obj.poste.nom,
                obj.poste.code
            )
        return format_html('<em>Tous les postes</em>')
    poste_display.short_description = _('Poste')
    
    def est_impertinent(self, obj):
        """Affiche si le jour est impertinent avec icône"""
        if obj.statut == 'impertinent':
            return format_html(
                '<span style="color: red; font-size: 18px;">⚠️ Impertinent</span>'
            )
        return format_html(
            '<span style="color: green;">✓ Normal</span>'
        )
    est_impertinent.short_description = _('Statut')
    est_impertinent.admin_order_field = 'statut'
    
    def commentaire_court(self, obj):
        """Affiche un extrait du commentaire"""
        if obj.commentaire:
            return obj.commentaire[:80] + '...' if len(obj.commentaire) > 80 else obj.commentaire
        return '-'
    commentaire_court.short_description = _('Raison')
    
    def save_model(self, request, obj, form, change):
        """Enregistre l'utilisateur qui crée la configuration"""
        if not change:
            obj.cree_par = request.user
        # Forcer les permissions à True (toujours autorisé sauf si impertinent)
        obj.permet_saisie_inventaire = True
        obj.permet_saisie_recette = True
        super().save_model(request, obj, form, change)
    
    actions = ['marquer_impertinent', 'marquer_normal']
    
    def marquer_impertinent(self, request, queryset):
        """Marque les jours sélectionnés comme impertinents"""
        count = queryset.update(statut='impertinent')
        self.message_user(request, f'{count} jour(s) marqué(s) comme impertinent(s).')
    marquer_impertinent.short_description = '⚠️ Marquer comme impertinent'
    
    def marquer_normal(self, request, queryset):
        """Marque les jours comme normaux"""
        count = queryset.update(statut='normal')
        self.message_user(request, f'{count} jour(s) marqué(s) comme normal(aux).')
    marquer_normal.short_description = '✓ Marquer comme normal'
    
    def statut_badge(self, obj):
        """Affichage coloré du statut"""
        colors = {
            'normal': 'success',
            'impertinent': 'warning'
        }
        color = colors.get(obj.statut, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.get_statut_display()
        )
    statut_badge.short_description = 'Statut'
    
    def date_formatee(self, obj):
        """Affiche la date formatée"""
        return obj.date.strftime('%d/%m/%Y')
    date_formatee.short_description = _('Date')
    date_formatee.admin_order_field = 'date'

    def permissions_display(self, obj):
        """Affichage des permissions"""
        permissions = []
        if obj.permet_saisie_inventaire:
            permissions.append('<span class="badge bg-success">✓ Inventaire</span>')
        if obj.permet_saisie_recette:
            permissions.append('<span class="badge bg-info">✓ Recette</span>')
        
        if not permissions:
            return format_html('<span class="badge bg-secondary">Aucune permission</span>')
        
        return format_html(' '.join(permissions))
    permissions_display.short_description = 'Permissions'
    

@admin.register(InventaireJournalier)
class InventaireJournalierAdmin(admin.ModelAdmin):
    form = InventaireJournalierForm
    inlines = [DetailInventairePeriodeInline]  # Inline pour saisie des périodes
    
    # Configuration de la liste
    list_display = [
        'poste', 'date', 'agent_saisie', 'total_vehicules_badge',
        'nombre_periodes_badge', 'modifiable_badge', 'derniere_modification_par'
    ]
    
    list_filter = ['date', 'modifiable_par_agent', 'poste__region', 'poste__type']
    search_fields = ['poste__nom', 'poste__code', 'agent_saisie__nom_complet']
    date_hierarchy = 'date'
    
    # Organisation des champs
    fieldsets = (
        (_('Informations générales'), {
            'fields': ('poste', 'date', 'agent_saisie')
        }),
        (_('État de modification'), {
            'fields': ('modifiable_par_agent', 'derniere_modification_par'),
            'description': _('Contrôle qui peut modifier cet inventaire')
        }),
        (_('Totaux calculés'), {
            'fields': ('total_vehicules', 'nombre_periodes_saisies'),
            'classes': ('collapse',)
        }),
        (_('Observations'), {
            'fields': ('observations',),
            'classes': ('wide',)
        }),
    )
    
    readonly_fields = ['total_vehicules', 'nombre_periodes_saisies', 'derniere_modification_par']
    def total_vehicules_badge(self, obj):
        """Badge coloré pour le total de véhicules"""
        if obj.total_vehicules == 0:
            color = 'danger'
        elif obj.total_vehicules < 100:
            color = 'warning'
        else:
            color = 'success'
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.total_vehicules
        )
    total_vehicules_badge.short_description = 'Total véhicules'
    
    def nombre_periodes_badge(self, obj):
        """Badge coloré pour le nombre de périodes"""
        if obj.nombre_periodes_saisies == 0:
            color = 'danger'
            text = 'Aucune'
        elif obj.nombre_periodes_saisies < 5:
            color = 'warning'
            text = f'{obj.nombre_periodes_saisies}/10'
        else:
            color = 'success'
            text = f'{obj.nombre_periodes_saisies}/10'
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, text
        )
    nombre_periodes_badge.short_description = 'Périodes'
    
    # def nombre_periodes_colored(self, obj):
    #     """Affichage coloré du nombre de périodes saisies"""
    #     if obj.nombre_periodes_saisies == 0:
    #         color = 'danger'
    #         text = 'Aucune'
    #     elif obj.nombre_periodes_saisies < 5:
    #         color = 'warning'
    #         text = f'{obj.nombre_periodes_saisies}/10'
    #     else:
    #         color = 'success'
    #         text = f'{obj.nombre_periodes_saisies}/10'
    #     return format_html(
    #         '<span class="badge bg-{}">{}</span>',
    #         color, text
    #     )
    # nombre_periodes_colored.short_description = 'Périodes saisies'
    
    def modifiable_badge(self, obj):
        """Badge indiquant si modifiable"""
        if obj.modifiable_par_agent:
            return format_html('<span class="badge bg-success">✓ Modifiable</span>')
        return format_html('<span class="badge bg-warning">🔒 Soumis</span>')
    modifiable_badge.short_description = 'État'
    
    def save_model(self, request, obj, form, change):
        """Enregistre qui a modifié en dernier"""
        obj.derniere_modification_par = request.user
        super().save_model(request, obj, form, change)
    
    def save_formset(self, request, form, formset, change):
        """Sauvegarde des périodes et recalcul des totaux"""
        instances = formset.save(commit=False)
        for instance in instances:
            instance.save()
        formset.save_m2m()
        
        # Recalculer les totaux
        if form.instance:
            form.instance.recalculer_totaux()
    
    actions = ['soumettre_inventaires', 'export_csv', 'recalculer_totaux']
    def soumettre_inventaires(self, request, queryset):
        """Action pour soumettre les inventaires (non modifiables par agent)"""
        count = 0
        for inventaire in queryset:
            if inventaire.modifiable_par_agent:
                inventaire.soumettre()
                count += 1
        self.message_user(request, f'{count} inventaire(s) soumis.')
    soumettre_inventaires.short_description = "Soumettre les inventaires sélectionnés"
    
    def recalculer_totaux(self, request, queryset):
        """Recalcule les totaux"""
        for inventaire in queryset:
            inventaire.recalculer_totaux()
        self.message_user(request, f'{queryset.count()} inventaire(s) recalculé(s).')
    recalculer_totaux.short_description = 'Recalculer les totaux'
    
    def export_csv(self, request, queryset):
        """Export CSV des inventaires"""
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="inventaires.csv"'
        response.write('\ufeff')  # BOM UTF-8
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Date', 'Poste', 'Agent', 'Total Véhicules', 
            'Périodes', 'Modifiable', 'Observations'
        ])
        
        for inv in queryset:
            writer.writerow([
                inv.date.strftime('%d/%m/%Y'),
                inv.poste.nom,
                inv.agent_saisie.nom_complet if inv.agent_saisie else '',
                inv.total_vehicules,
                inv.nombre_periodes_saisies,
                'Oui' if inv.modifiable_par_agent else 'Non',
                inv.observations
            ])
        
        return response
    export_csv.short_description = 'Exporter en CSV'

   
    
    # def save_model(self, request, obj, form, change):
    #     """Gestion automatique de la validation"""
    #     if obj.valide and not obj.valide_par:
    #         obj.valide_par = request.user
    #         # Utiliser le timezone de Django
    #         obj.date_validation = timezone.now()
    #     super().save_model(request, obj, form, change)
    
    # def save_formset(self, request, form, formset, change):
    #     """Sauvegarde des périodes et recalcul automatique des totaux"""
    #     instances = formset.save(commit=False)
        
    #     for instance in instances:
    #         instance.save()
        
    #     formset.save_m2m()
        
    #     # Recalculer les totaux après sauvegarde des périodes
    #     if form.instance:
    #         form.instance.recalculer_totaux()
    
    # def get_queryset(self, request):
    #     """Optimiser les requêtes"""
    #     return super().get_queryset(request).select_related(
    #         'poste', 'agent_saisie', 'valide_par'
    #     ).prefetch_related('details_periodes')
    

    
    # def recalculer_totaux(self, request, queryset):
    #     """Action pour recalculer les totaux"""
    #     count = 0
    #     for inventaire in queryset:
    #         inventaire.recalculer_totaux()
    #         count += 1
    #     self.message_user(request, f'{count} inventaire(s) recalculé(s).')
    # recalculer_totaux.short_description = 'Recalculer les totaux'
    
    # def export_inventaires(self, request, queryset):
    #     """Export CSV des inventaires"""
    #     response = HttpResponse(content_type='text/csv; charset=utf-8')
    #     response['Content-Disposition'] = 'attachment; filename="inventaires_supper.csv"'
        
    #     # Ajouter le BOM UTF-8 pour Excel
    #     response.write('\ufeff')
        
    #     writer = csv.writer(response, delimiter=';')
    #     writer.writerow(['Date', 'Poste', 'Agent', 'Total Véhicules', 'Périodes Saisies', 
    #                     'Verrouillé', 'Validé', 'Recette Potentielle (FCFA)', 'Moyenne Horaire'])
        
    #     for inventaire in queryset:
    #         recette_potentielle = inventaire.calculer_recette_potentielle()
    #         moyenne_horaire = inventaire.calculer_moyenne_horaire()
            
    #         writer.writerow([
    #             inventaire.date.strftime('%d/%m/%Y'),
    #             inventaire.poste.nom,
    #             inventaire.agent_saisie.nom_complet if inventaire.agent_saisie else 'Non renseigné',
    #             inventaire.total_vehicules,
    #             inventaire.nombre_periodes_saisies,
    #             f"{recette_potentielle:,.0f}".replace(',', ' '),
    #             f"{moyenne_horaire:.1f}"
    #         ])
        
    #     return response
    # export_inventaires.short_description = 'Exporter en CSV'


@admin.register(DetailInventairePeriode)
class DetailInventairePeriodeAdmin(admin.ModelAdmin):
    """Admin pour voir toutes les périodes (lecture seule principalement)"""
    list_display = ['inventaire', 'periode', 'nombre_vehicules_colored', 'heure_saisie']
    list_filter = ['periode', 'inventaire__date', 'inventaire__poste__region']
    search_fields = ['inventaire__poste__nom']
    readonly_fields = ['heure_saisie', 'modifie_le']
    
    def nombre_vehicules_colored(self, obj):
        """Affichage coloré du nombre de véhicules"""
        if obj.nombre_vehicules == 0:
            color = 'secondary'
        elif obj.nombre_vehicules < 10:
            color = 'warning'
        else:
            color = 'success'
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.nombre_vehicules
        )
    nombre_vehicules_colored.short_description = 'Véhicules'


@admin.register(RecetteJournaliere)
class RecetteJournaliereAdmin(admin.ModelAdmin):
    # 🔧 AJOUTER cette ligne pour utiliser le formulaire personnalisé
    form = RecetteJournaliereAdminForm
    
    list_display = [
        'poste', 'date', 'montant_declare_formatted', 'chef_poste',  'modifiable_badge',
    ]
    
    list_filter = ['date', 'modifiable_par_chef', 'poste__region']
    search_fields = ['poste__nom', 'chef_poste__nom_complet']
    date_hierarchy = 'date'
    
    
    fieldsets = (
        (_('Informations principales'), {
            'fields': ('poste', 'date', 'chef_poste', 'montant_declare', 'stock_tickets_restant')
        }),
        (_('Calculs automatiques'), {
            'fields': ('inventaire_associe', 'recette_potentielle', 'ecart', 'taux_deperdition'),
            'classes': ('collapse',)
        }),
        (_('État'), {
            'fields': ('modifiable_par_chef', 'derniere_modification_par')
        }),
        (_('Observations'), {
            'fields': ('observations',),
            'classes': ('wide',)
        }),
    )
    
    readonly_fields = [
        'recette_potentielle', 'ecart', 'taux_deperdition',
        'derniere_modification_par', 'date_saisie', 'date_modification'
    ]
    
    # 🔧 NOUVELLE MÉTHODE : Afficher le statut du jour
    # def get_status_jour(self, obj):
    #     """Affiche le statut du jour pour cette recette"""
    #     if obj.date and obj.poste:
    #         from .models import ConfigurationJour
            
    #         inventaire_ouvert = ConfigurationJour.est_jour_ouvert_pour_inventaire(obj.date, obj.poste)
    #         recette_ouvert = ConfigurationJour.est_jour_ouvert_pour_recette(obj.date, obj.poste)
            
    #         status = []
    #         if inventaire_ouvert:
    #             status.append('<span style="color: green;">✓ Inventaire</span>')
    #         else:
    #             status.append('<span style="color: red;">✗ Inventaire</span>')
                
    #         if recette_ouvert:
    #             status.append('<span style="color: green;">✓ Recette</span>')
    #         else:
    #             status.append('<span style="color: red;">✗ Recette</span>')
            
    #         return format_html(' | '.join(status))
    #     return '-'
    # get_status_jour.short_description = 'Statut du jour'
    
    def montant_declare_formatted(self, obj):
        """Montant formaté"""
        return format_html(
            '<strong>{:,.0f} FCFA</strong>',
            float(obj.montant_declare) if obj.montant_declare else 0
        )
    montant_declare_formatted.short_description = 'Montant déclaré'
    
    def modifiable_badge(self, obj):
        """Badge modifiable"""
        if obj.modifiable_par_chef:
            return format_html('<span class="badge bg-success">✓ Modifiable</span>')
        return format_html('<span class="badge bg-warning">🔒 Soumise</span>')
    modifiable_badge.short_description = 'État'
    
    def save_model(self, request, obj, form, change):
        """Enregistre qui a modifié et vérifie si jour devient impertinent"""
        obj.derniere_modification_par = request.user
        super().save_model(request, obj, form, change)
        
        # Le calcul automatique dans le modèle marquera le jour comme impertinent si TD > -5%
    
    actions = ['soumettre_recettes', 'recalculer_indicateurs', 'lier_inventaires']
    
    def soumettre_recettes(self, request, queryset):
        """Soumet les recettes"""
        count = 0
        for recette in queryset:
            if recette.modifiable_par_chef:
                recette.modifiable_par_chef = False
                recette.save()
                count += 1
        self.message_user(request, f'{count} recette(s) soumise(s).')
    soumettre_recettes.short_description = "Soumettre les recettes"
    
    def recalculer_indicateurs(self, request, queryset):
        """Recalcule les indicateurs"""
        for recette in queryset:
            recette.calculer_indicateurs()
            recette.save()
        self.message_user(request, f'{queryset.count()} recette(s) recalculée(s).')
    recalculer_indicateurs.short_description = "Recalculer les indicateurs"
    
    def lier_inventaires(self, request, queryset):
        """Lie automatiquement aux inventaires"""
        count = 0
        for recette in queryset:
            try:
                inventaire = InventaireJournalier.objects.get(
                    poste=recette.poste,
                    date=recette.date
                )
                recette.inventaire_associe = inventaire
                recette.save()
                count += 1
            except InventaireJournalier.DoesNotExist:
                continue
        self.message_user(request, f'{count} recette(s) liée(s) à leur inventaire.')
    lier_inventaires.short_description = "Lier aux inventaires"

    # def taux_deperdition_colored(self, obj):
    #     """Taux de déperdition coloré"""
    #     if obj.taux_deperdition is None:
    #         return '-'
        
    #     couleur = obj.get_couleur_alerte()
    #     color_map = {
    #         'success': 'green',
    #         'warning': 'orange',
    #         'danger': 'red',
    #         'secondary': 'gray'
    #     }
        
    #     return format_html(
    #         '<span style="color: {}; font-weight: bold;">{:.2f}%</span>',
    #         color_map.get(couleur, 'black'),
    #         float(obj.taux_deperdition)
    #     )
    # taux_deperdition_colored.short_description = 'Taux déperdition'

    # def statut_colored(self, obj):
    #     """Statut de déperdition coloré"""
    #     statut = obj.get_statut_deperdition()
    #     color_map = {
    #         'Bon': 'success',
    #         'Acceptable': 'warning',
    #         'Mauvais': 'danger',
    #         'Impertinent': 'secondary'
    #     }
    #     color = color_map.get(statut, 'info')
        
    #     return format_html(
    #         '<span class="badge bg-{}">{}</span>',
    #         color, statut
    #     )
    # statut_colored.short_description = 'Statut'
    
    
    # def recette_potentielle_formatted(self, obj):
    #     """Affichage formaté de la recette potentielle"""
    #     if obj.recette_potentielle is not None:
    #         try:
    #             montant = float(obj.recette_potentielle)
    #             return format_html(
    #                 '{:,.0f} FCFA',
    #                 montant
    #             )
    #         except (ValueError, TypeError):
    #             return str(obj.recette_potentielle)
    #     return '-'
    # recette_potentielle_formatted.short_description = 'Recette potentielle'
    # recette_potentielle_formatted.admin_order_field = 'recette_potentielle'
    
    # def taux_deperdition_colored(self, obj):
    #     """Affichage formaté du taux de déperdition"""
    #     if obj.taux_deperdition is not None:
    #         try:
    #             taux = float(obj.taux_deperdition)
    #             couleur = obj.get_couleur_alerte()
                
    #             # Mapping couleurs bootstrap vers couleurs CSS
    #             color_map = {
    #                 'success': '#28a745',
    #                 'warning': '#ffc107', 
    #                 'danger': '#dc3545',
    #                 'secondary': '#6c757d'
    #             }
                
    #             return format_html(
    #                 '<span style="color: {}; font-weight: bold;">{:.2f}%</span>',
    #                 color_map.get(couleur, '#000000'),
    #                 taux
    #             )
    #         except (ValueError, TypeError):
    #             return str(obj.taux_deperdition)
    #     return '-'
    # taux_deperdition_colored.short_description = 'Taux déperdition'
    # taux_deperdition_colored.admin_order_field = 'taux_deperdition'

    # def inventaire_lie(self, obj):
    #     """Affiche si l'inventaire est lié"""
    #     if obj.inventaire_associe:
    #         return format_html(
    #             '<span style="color: green;">✓ Lié</span>'
    #         )
    #     else:
    #         return format_html(
    #             '<span style="color: red;">✗ Non lié</span>'
    #         )
    # inventaire_lie.short_description = 'Inventaire'
    
    # def debug_calculs(self, obj):
    #     """Affichage de debug pour comprendre les calculs"""
    #     if obj.inventaire_associe:
    #         stats = obj.inventaire_associe.get_statistiques_detaillees()
            
    #         if 'erreur' in stats:
    #             return format_html('<div style="color: red;">{}</div>', stats['erreur'])
            
    #         html = """
    #         <div style="font-family: monospace; font-size: 12px;">
    #             <strong>Détails du calcul :</strong><br>
    #             • Somme véhicules : {somme_vehicules}<br>
    #             • Nombre périodes : {nombre_periodes}<br>
    #             • Moyenne horaire : {moyenne_horaire}<br>
    #             • Estimation 24h : {estimation_24h}<br>
    #             • Véhicules effectifs (75%) : {vehicules_effectifs_75%}<br>
    #             • Recette potentielle : {recette_potentielle} FCFA<br>
    #             <br>
    #             <strong>Résultat :</strong><br>
    #             • Montant déclaré : {montant_declare} FCFA<br>
    #             • Écart : {ecart} FCFA<br>
    #             • Taux déperdition : {td}%
    #         </div>
    #         """.format(
    #             **stats,
    #             montant_declare=obj.montant_declare,
    #             ecart=obj.ecart or 'N/A',
    #             td=f"{obj.taux_deperdition:.2f}" if obj.taux_deperdition else 'N/A'
    #         )
            
    #         return format_html(html)
    #     else:
    #         return "Aucun inventaire associé"
    
    # debug_calculs.short_description = 'Debug calculs'
    
    # # Actions personnalisées
    # actions = ['recalculer_indicateurs', 'forcer_liaison_inventaire']
    
    # def recalculer_indicateurs(self, request, queryset):
    #     """Action pour recalculer les indicateurs"""
    #     count = 0
    #     for recette in queryset:
    #         recette.calculer_indicateurs()
    #         recette.save()
    #         count += 1
        
    #     self.message_user(
    #         request,
    #         f"{count} recette(s) recalculée(s) avec succès."
    #     )
    # recalculer_indicateurs.short_description = "Recalculer les indicateurs sélectionnés"
    
    # def forcer_liaison_inventaire(self, request, queryset):
    #     """Action pour forcer la liaison avec l'inventaire"""
    #     from .models import InventaireJournalier
    #     count = 0
        
    #     for recette in queryset:
    #         try:
    #             inventaire = InventaireJournalier.objects.get(
    #                 poste=recette.poste,
    #                 date=recette.date
    #             )
    #             recette.inventaire_associe = inventaire
    #             recette.save()
    #             count += 1
    #         except InventaireJournalier.DoesNotExist:
    #             continue
        
    #     self.message_user(
    #         request,
    #         f"{count} recette(s) liée(s) à leur inventaire."
    #     )
    # forcer_liaison_inventaire.short_description = "Forcer la liaison avec l'inventaire"
    

    # def get_couleur_alerte_display(self, obj):
    #     """Affichage de l'alerte couleur"""
    #     couleur = obj.get_couleur_alerte()
        
    #     # Labels et couleurs
    #     labels = {
    #         'success': ('✓ Normal', '#28a745'),
    #         'warning': ('⚠ Attention', '#ffc107'),
    #         'danger': ('✗ Critique', '#dc3545'),
    #         'secondary': ('? Inconnu', '#6c757d')
    #     }
        
    #     label, color = labels.get(couleur, ('?', '#000000'))
        
    #     return format_html(
    #         '<span style="color: {}; font-weight: bold;">{}</span>',
    #         color,
    #         label
    #     )
    # get_couleur_alerte_display.short_description = 'Alerte'
    
   
    
    # def get_queryset(self, request):
    #     """Optimiser les requêtes"""
    #     return super().get_queryset(request).select_related(
    #         'poste', 'chef_poste', 'inventaire_associe'
    #     )
    
  
    
    
    
    # def export_recettes(self, request, queryset):
    #     """Export CSV des recettes"""
    #     response = HttpResponse(content_type='text/csv; charset=utf-8')
    #     response['Content-Disposition'] = 'attachment; filename="recettes_supper.csv"'
        
    #     # Ajouter le BOM UTF-8 pour Excel
    #     response.write('\ufeff')
        
    #     writer = csv.writer(response, delimiter=';')
    #     writer.writerow(['Date', 'Poste', 'Chef', 'Montant Déclaré (FCFA)', 'Recette Potentielle (FCFA)',
    #                     'Écart (FCFA)', 'Taux Déperdition (%)', 'Couleur Alerte', 'Statut'])
        
    #     for recette in queryset:
    #         writer.writerow([
    #             recette.date.strftime('%d/%m/%Y'),
    #             recette.poste.nom,
    #             recette.chef_poste.nom_complet if recette.chef_poste else 'Non renseigné',
    #             f"{recette.montant_declare:,.0f}".replace(',', ' '),
    #             f"{recette.recette_potentielle:,.0f}".replace(',', ' ') if recette.recette_potentielle else 'N/A',
    #             f"{recette.ecart:,.0f}".replace(',', ' ') if recette.ecart else 'N/A',
    #             f"{recette.taux_deperdition:.2f}" if recette.taux_deperdition else 'N/A',
    #             recette.get_couleur_alerte() if recette.taux_deperdition else 'N/A',
    #           
    #         ])
        
    #     return response
    # export_recettes.short_description = 'Exporter en CSV'

    # def exporter_csv(self, request, queryset):
    #     """Exporte les recettes en CSV"""
    #     import csv
    #     from django.http import HttpResponse
    #     from django.utils import timezone
        
    #     response = HttpResponse(content_type='text/csv; charset=utf-8')
    #     response['Content-Disposition'] = f'attachment; filename="recettes_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
    #     # BOM UTF-8 pour Excel
    #     response.write('\ufeff')
        
    #     writer = csv.writer(response, delimiter=';')
    #     writer.writerow([
    #         'Poste', 'Date', 'Montant déclaré', 'Recette potentielle', 
    #         'Écart', 'Taux déperdition', 'Chef de poste', 'Verrouillé'
    #     ])
        
    #     for recette in queryset:
    #         writer.writerow([
    #             recette.poste.nom,
    #             recette.date.strftime('%d/%m/%Y'),
    #             float(recette.montant_declare) if recette.montant_declare else 0,
    #             float(recette.recette_potentielle) if recette.recette_potentielle else 0,
    #             float(recette.ecart) if recette.ecart else 0,
    #             float(recette.taux_deperdition) if recette.taux_deperdition else 0,
    #             recette.chef_poste.nom_complet if recette.chef_poste else '',
    #            
    #         ])
        
    #     return response
    # exporter_csv.short_description = "Exporter en CSV"

    # def get_form(self, request, obj=None, **kwargs):
    #     """Personnalise le formulaire selon l'utilisateur"""
    #     form = super().get_form(request, obj, **kwargs)
        
    #     # Limiter les postes selon les permissions de l'utilisateur
    #     if hasattr(request.user, 'get_postes_accessibles'):
    #         postes_accessibles = request.user.get_postes_accessibles()
    #         if 'poste' in form.base_fields:
    #             form.base_fields['poste'].queryset = postes_accessibles
        
    #     # Définir l'utilisateur connecté comme chef de poste par défaut
    #     if not obj and 'chef_poste' in form.base_fields:
    #         form.base_fields['chef_poste'].initial = request.user

        
    #     return form
    
    # def save_model(self, request, obj, form, change):
    #     """Sauvegarde avec journalisation et gestion sécurisée des valeurs None"""
        
    #     # Sauvegarder d'abord l'objet pour déclencher les calculs automatiques
    #     super().save_model(request, obj, form, change)
        
    #     # Construire le message de journalisation avec gestion des valeurs None
    #     try:
    #         if change:
    #             action = "Modification recette"
    #             details_parts = [
    #                 f"Recette modifiée: {obj.montant_declare} FCFA pour {obj.poste.nom} - {obj.date}"
    #             ]
    #         else:
    #             action = "Saisie recette"
    #             details_parts = [
    #                 f"Recette saisie: {obj.montant_declare} FCFA pour {obj.poste.nom} - {obj.date}"
    #             ]
            
    #         # Ajouter les indicateurs calculés seulement s'ils existent
    #         if obj.taux_deperdition is not None:
    #             details_parts.append(f"Taux de déperdition: {obj.taux_deperdition:.2f}%")
    #             details_parts.append(f"Couleur alerte: {obj.get_couleur_alerte()}")
    #         else:
    #             details_parts.append("Taux de déperdition: Non calculé (inventaire manquant)")
            
    #         if obj.recette_potentielle is not None:
    #             details_parts.append(f"Recette potentielle: {obj.recette_potentielle} FCFA")
            
    #         if obj.ecart is not None:
    #             details_parts.append(f"Écart: {obj.ecart} FCFA")
            
    #         details = " | ".join(details_parts)
            
    #         # Journaliser l'action
    #         from common.utils import log_user_action
    #         log_user_action(request.user, action, details, request)
            
    #     except Exception as e:
    #         # En cas d'erreur de journalisation, ne pas bloquer la sauvegarde
    #         logger.error(f"Erreur lors de la journalisation de recette: {str(e)}")
    #         # Journalisation minimale de fallback
    #         from common.utils import log_user_action
    #         log_user_action(
    #             request.user, 
    #             "Saisie recette" if not change else "Modification recette",
    #             f"Montant: {obj.montant_declare} FCFA - Poste: {obj.poste.nom}",
    #             request
    #         )



# @admin.register(StatistiquesPeriodiques)
# class StatistiquesPeriodiquesAdmin(admin.ModelAdmin):
#     list_display = [
#         'poste', 'type_periode', 'date_debut', 
#         'date_fin', 'taux_deperdition_moyen_badge'
#     ]
#     list_filter = ['type_periode', 'poste__region']
#     search_fields = ['poste__nom']
#     date_hierarchy = 'date_debut'
    
#     readonly_fields = [
#         'total_recettes_declarees', 'total_recettes_potentielles',
#         'taux_deperdition_moyen', 'nombre_jours_impertinents', 'date_calcul'
#     ]
    
#     fieldsets = (
#         ('Période', {
#             'fields': ('poste', 'type_periode', 'date_debut', 'date_fin')
#         }),
#         ('Statistiques calculées', {
#             'fields': (
#                 'nombre_jours_actifs', 'total_recettes_declarees',
#                 'total_recettes_potentielles', 'taux_deperdition_moyen',
#                 'nombre_jours_impertinents'
#             )
#         }),
#         ('Métadonnées', {
#             'fields': ('date_calcul',),
#             'classes': ('collapse',)
#         }),
#     )
    
#     def taux_deperdition_moyen_badge(self, obj):
#         """Badge pour le taux moyen"""
#         if obj.taux_deperdition_moyen is not None:
#             if obj.taux_deperdition_moyen > -10:
#                 color = 'success'
#             elif obj.taux_deperdition_moyen >= -30:
#                 color = 'warning'
#             else:
#                 color = 'danger'
            
#             return format_html(
#                 '<span class="badge bg-{}">{:.2f}%</span>',
#                 color, obj.taux_deperdition_moyen
#             )
#         return format_html('<span class="badge bg-secondary">N/A</span>')
#     taux_deperdition_moyen_badge.short_description = 'Taux moyen'
    
#     def get_queryset(self, request):
#         """Optimiser les requêtes"""
#         return super().get_queryset(request).select_related('poste')
    
#     actions = ['export_statistiques', 'recalculer_statistiques']
    
#     def recalculer_statistiques(self, request, queryset):
#         """Action pour recalculer les statistiques"""
#         count = 0
#         for stat in queryset:
#             # Recalculer les statistiques en appelant la méthode du modèle
#             stat_recalculee = StatistiquesPeriodiques.calculer_statistiques_periode(
#                 stat.poste, stat.type_periode, stat.date_debut, stat.date_fin
#             )
#             if stat_recalculee:
#                 count += 1
        
#         self.message_user(request, f'{count} statistique(s) recalculée(s).')
#     recalculer_statistiques.short_description = 'Recalculer les statistiques'
    
#     def export_statistiques(self, request, queryset):
#         """Export CSV des statistiques"""
#         response = HttpResponse(content_type='text/csv; charset=utf-8')
#         response['Content-Disposition'] = 'attachment; filename="statistiques_supper.csv"'
        
#         # Ajouter le BOM UTF-8 pour Excel
#         response.write('\ufeff')
        
#         writer = csv.writer(response, delimiter=';')
#         writer.writerow(['Poste', 'Type Période', 'Début', 'Fin', 'Jours Actifs',
#                         'Total Déclaré (FCFA)', 'Total Potentiel (FCFA)', 'Taux Moyen (%)', 
#                         'Jours Impertinents', 'Date Calcul'])
        
#         for stat in queryset:
#             writer.writerow([
#                 stat.poste.nom,
#                 stat.get_type_periode_display(),
#                 stat.date_debut.strftime('%d/%m/%Y'),
#                 stat.date_fin.strftime('%d/%m/%Y'),
#                 stat.nombre_jours_actifs,
#                 f"{stat.total_recettes_declarees:,.0f}".replace(',', ' '),
#                 f"{stat.total_recettes_potentielles:,.0f}".replace(',', ' '),
#                 f"{stat.taux_deperdition_moyen:.2f}" if stat.taux_deperdition_moyen else 'N/A',
#                 stat.nombre_jours_impertinents,
#                 stat.date_calcul.strftime('%d/%m/%Y %H:%M')
#             ])
        
#         return response
#     export_statistiques.short_description = 'Exporter en CSV'


# @admin.register(InventaireMensuel)
# class InventaireMensuelAdmin(admin.ModelAdmin):
#     """
#     Administration des inventaires mensuels avec widget calendrier
#     """
    
#     # 🔧 CORRECTION : Pas de form personnalisé pour éviter les conflits
#     # form = InventaireMensuelForm  # COMMENTÉ TEMPORAIREMENT
    
#     list_display = [
#         'titre', 'mois_annee', 'nombre_jours_actifs', 
#         'actif', 'actions_admin', 'date_creation'
#     ]
    
#     list_filter = ['actif', 'annee', 'mois', 'date_creation']
#     search_fields = ['titre', 'description']
#     readonly_fields = ['date_creation', 'date_modification', 'cree_par']
    
#     fieldsets = (
#         ('Informations principales', {
#             'fields': ('titre', 'mois', 'annee', 'description')
#         }),
#         ('Configuration des Jours', {
#             'fields': ('jours_actifs',),
#             'description': 'Sélectionnez les jours du mois où la saisie d\'inventaire sera autorisée'
#         }),
#         ('État', {
#             'fields': ('actif',)
#         }),
#         ('Métadonnées', {
#             'fields': ('cree_par', 'date_creation', 'date_modification'),
#             'classes': ('collapse',)
#         }),
#     )
    
#     # 🔧 CORRECTION : Supprimer get_form pour utiliser le form par défaut
#     # def get_form(self, request, obj=None, **kwargs):
#     #     return super().get_form(request, obj, **kwargs)
    
#     def mois_annee(self, obj):
#         """Affiche mois et année formatés"""
#         try:
#             return f"{obj.get_mois_display()} {obj.annee}"
#         except Exception as e:
#             return f"Erreur: {str(e)}"
#     mois_annee.short_description = "Période"
    
#     def nombre_jours_actifs(self, obj):
#         """Affiche le nombre de jours actifs avec style"""
#         try:
#             if obj.jours_actifs and isinstance(obj.jours_actifs, list):
#                 count = len(obj.jours_actifs)
#             else:
#                 count = 0
                
#             if count > 0:
#                 return format_html(
#                     '<span style="color: green; font-weight: bold; background: #d4edda; '
#                     'padding: 3px 8px; border-radius: 12px;">{} jours</span>',
#                     count
#                 )
#             return format_html(
#                 '<span style="color: red; background: #f8d7da; '
#                 'padding: 3px 8px; border-radius: 12px;">Aucun jour</span>'
#             )
#         except Exception as e:
#             return format_html(
#                 '<span style="color: orange; background: #fff3cd; '
#                 'padding: 3px 8px; border-radius: 12px;">Erreur: {}</span>',
#                 str(e)
#             )
#     nombre_jours_actifs.short_description = "Jours actifs"
    
#     def actions_admin(self, obj):
#         """Boutons d'actions rapides"""
#         if obj.pk:
#             buttons = []
            
#             # Bouton générer configurations
#             buttons.append(format_html(
#                 '<a href="{}" class="button" style="background: #28a745; color: white; '
#                 'padding: 5px 10px; text-decoration: none; border-radius: 3px; margin-right: 5px;">'
#                 '🔧 Générer Configs</a>',
#                 reverse('admin:inventaire_inventairemensuel_generer_config', args=[obj.pk])
#             ))
            
#             return format_html(''.join(buttons))
#         return "Sauvegardez d'abord"
#     actions_admin.short_description = "Actions"
    
#     def save_model(self, request, obj, form, change):
#         """Surcharge avec gestion d'erreurs simplifiée"""
#         try:
#             if not change:  # Création
#                 obj.cree_par = request.user
            
#             # 🔧 CORRECTION : Validation simple des jours_actifs
#             if hasattr(obj, 'jours_actifs') and obj.jours_actifs:
#                 if isinstance(obj.jours_actifs, str):
#                     try:
#                         import json
#                         obj.jours_actifs = json.loads(obj.jours_actifs)
#                     except (json.JSONDecodeError, ValueError):
#                         obj.jours_actifs = []
                
#                 # S'assurer que c'est une liste
#                 if not isinstance(obj.jours_actifs, list):
#                     obj.jours_actifs = []
#             else:
#                 obj.jours_actifs = []
            
#             # Validation de l'unicité
#             existing = InventaireMensuel.objects.filter(
#                 mois=obj.mois, 
#                 annee=obj.annee
#             ).exclude(pk=obj.pk if obj.pk else 0)
            
#             if existing.exists():
#                 self.message_user(
#                     request,
#                     f"Un inventaire existe déjà pour {obj.get_mois_display()} {obj.annee}",
#                     level='ERROR'
#                 )
#                 return
            
#             super().save_model(request, obj, form, change)
            
#             # Message de succès
#             jours_count = len(obj.jours_actifs) if obj.jours_actifs else 0
#             self.message_user(
#                 request,
#                 f"Inventaire '{obj.titre}' sauvegardé avec succès ! "
#                 f"({jours_count} jours sélectionnés)",
#                 level='SUCCESS'
#             )
            
#         except Exception as e:
#             self.message_user(
#                 request,
#                 f"Erreur lors de la sauvegarde: {str(e)}",
#                 level='ERROR'
#             )
#             # Déboguer l'erreur
#             import traceback
#             print(f"ERREUR SAUVEGARDE: {traceback.format_exc()}")
    
#     def get_urls(self):
#         """Ajouter des URLs personnalisées"""
#         urls = super().get_urls()
#         custom_urls = [
#             path(
#                 '<int:object_id>/generer_config/',
#                 self.admin_site.admin_view(self.generer_config_view),
#                 name='inventaire_inventairemensuel_generer_config'
#             ),
#         ]
#         return custom_urls + urls
    
#     def generer_config_view(self, request, object_id):
#         """Action pour générer automatiquement les configurations de jours"""
#         try:
#             inventaire = InventaireMensuel.objects.get(pk=object_id)
#             configs_creees = inventaire.generer_configurations_jours()
            
#             self.message_user(
#                 request,
#                 f"Configuration automatique réussie ! "
#                 f"{len(configs_creees)} jours configurés pour {inventaire.titre}",
#                 level='SUCCESS'
#             )
            
#         except InventaireMensuel.DoesNotExist:
#             self.message_user(request, "Inventaire mensuel introuvable", level='ERROR')
#         except Exception as e:
#             self.message_user(request, f"Erreur: {str(e)}", level='ERROR')
        
#         return redirect('admin:inventaire_inventairemensuel_change', object_id)
    
#     def formfield_for_dbfield(self, db_field, request, **kwargs):
#         """Personnaliser les widgets des champs"""
#         if db_field.name == 'jours_actifs':
#             kwargs['widget'] = CalendrierJoursWidget()
#         return super().formfield_for_dbfield(db_field, request, **kwargs)

@admin.register(ProgrammationInventaire)
class ProgrammationInventaireAdmin(admin.ModelAdmin):
    """Administration des programmations d'inventaires"""
    
    list_display = [
        'poste_display', 'mois_formatted', 'motif_badge', 
        'indicateurs_display', 'actif_badge', 'cree_par', 'date_creation'
    ]
    
    list_filter = [
        'motif', 'actif', 'mois', 
        'poste__region', 'poste__type'
    ]
    
    search_fields = ['poste__nom', 'poste__code']
    date_hierarchy = 'mois'
    
    readonly_fields = [
        'cree_par', 'date_creation', 'recettes_periode_actuelle',
        'recettes_periode_precedente', 'pourcentage_baisse',
        'date_epuisement_prevu', 'risque_grand_stock'
    ]
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('poste', 'mois', 'motif', 'actif')
        }),
        ('Données Taux de déperdition', {
            'fields': ('taux_deperdition_precedent',),
            'classes': ('collapse',),
        }),
        ('Données Risque de baisse', {
            'fields': (
                'risque_baisse_annuel', 'recettes_periode_actuelle',
                'recettes_periode_precedente', 'pourcentage_baisse'
            ),
            'classes': ('collapse',),
        }),
        ('Données Grand stock', {
            'fields': (
                'stock_restant', 'date_epuisement_prevu', 'risque_grand_stock'
            ),
            'classes': ('collapse',),
        }),
        ('Métadonnées', {
            'fields': ('cree_par', 'date_creation'),
            'classes': ('collapse',),
        })
    )

    def poste_display(self, obj):
        """Affichage enrichi du poste"""
        return format_html(
            '<strong>{}</strong><br><small>{} - {}</small>',
            obj.poste.nom,
            obj.poste.code,
            obj.poste.get_region_display()
        )
    poste_display.short_description = 'Poste'

    
    def mois_formatted(self, obj):
        """Mois formaté avec indicateur"""
        mois_actuel = date.today().replace(day=1)
        is_current = obj.mois.year == mois_actuel.year and obj.mois.month == mois_actuel.month
        
        if is_current:
            return format_html(
                '<span class="badge bg-success">{}</span>',
                obj.mois.strftime('%B %Y')
            )
        return obj.mois.strftime('%B %Y')
    mois_formatted.short_description = 'Mois'

    def motif_badge(self, obj):
        """Badge coloré pour le motif"""
        colors = {
            MotifInventaire.TAUX_DEPERDITION: 'danger',
            MotifInventaire.RISQUE_BAISSE: 'warning',
            MotifInventaire.GRAND_STOCK: 'info'
        }
        color = colors.get(obj.motif, 'secondary')
        
        icon = ''
        if obj.motif == MotifInventaire.TAUX_DEPERDITION:
            icon = '📊'
        elif obj.motif == MotifInventaire.RISQUE_BAISSE:
            icon = '📉'
        elif obj.motif == MotifInventaire.GRAND_STOCK:
            icon = '📦'
        
        return format_html(
            '<span class="badge bg-{}">{} {}</span>',
            color, icon, obj.get_motif_display()
        )
    motif_badge.short_description = 'Motif'
    
    
    def indicateurs_display(self, obj):
        """Affichage des indicateurs selon le motif"""
        if obj.motif == MotifInventaire.TAUX_DEPERDITION and obj.taux_deperdition_precedent:
            taux = float(obj.taux_deperdition_precedent)
            color = 'danger' if taux < -30 else 'warning' if taux < -10 else 'success'
            return format_html(
                '<span class="badge bg-{}">Taux: {:.1f}%</span>',
                color, taux
            )
        
        elif obj.motif == MotifInventaire.RISQUE_BAISSE and obj.pourcentage_baisse:
            return format_html(
                '<span class="badge bg-warning">Baisse: -{:.1f}%</span>',
                float(obj.pourcentage_baisse)
            )
        
        elif obj.motif == MotifInventaire.GRAND_STOCK and obj.date_epuisement_prevu:
            return format_html(
                '<span class="badge bg-info">Épuisement: {}</span>',
                obj.date_epuisement_prevu.strftime('%d/%m/%Y')
            )
        
        return '-'
    indicateurs_display.short_description = 'Indicateurs'

    def actif_badge(self, obj):
        """Badge pour le statut actif"""
        if obj.actif:
            return format_html('<span class="badge bg-success">✓ Actif</span>')
        return format_html('<span class="badge bg-secondary">Inactif</span>')
    actif_badge.short_description = 'Statut'
    
    def save_model(self, request, obj, form, change):
        """Enregistre le créateur et fait les calculs automatiques"""
        if not change:
            obj.cree_par = request.user
        
        # Forcer les calculs selon le motif
        if obj.motif == MotifInventaire.RISQUE_BAISSE:
            obj.calculer_risque_baisse_annuel()
        elif obj.motif == MotifInventaire.GRAND_STOCK:
            obj.calculer_date_epuisement_stock()
        
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        """Optimise les requêtes"""
        qs = super().get_queryset(request)
        return qs.select_related('poste', 'cree_par')
    
    actions = ['activer_programmations', 'desactiver_programmations', 'recalculer_indicateurs']
    
    def activer_programmations(self, request, queryset):
        """Action pour activer les programmations sélectionnées"""
        count = queryset.update(actif=True)
        self.message_user(request, f"{count} programmation(s) activée(s)")
    activer_programmations.short_description = "Activer les programmations sélectionnées"
    
    def desactiver_programmations(self, request, queryset):
        """Action pour désactiver les programmations sélectionnées"""
        count = queryset.update(actif=False)
        self.message_user(request, f"{count} programmation(s) désactivée(s)")
    desactiver_programmations.short_description = "Désactiver les programmations sélectionnées"
    
    def recalculer_indicateurs(self, request, queryset):
        """Recalcule les indicateurs pour les programmations sélectionnées"""
        count = 0
        for prog in queryset:
            if prog.motif == MotifInventaire.RISQUE_BAISSE:
                prog.calculer_risque_baisse_annuel()
            elif prog.motif == MotifInventaire.GRAND_STOCK:
                prog.calculer_date_epuisement_stock()
            prog.save()
            count += 1
        self.message_user(request, f"Indicateurs recalculés pour {count} programmation(s)")
    recalculer_indicateurs.short_description = "Recalculer les indicateurs"


class ProgrammationInline(admin.TabularInline):
    """Inline pour voir les programmations d'un poste"""
    model = ProgrammationInventaire
    extra = 0
    fields = ['mois', 'motif', 'actif']
    readonly_fields = ['mois', 'motif']
    can_delete = False


@admin.register(StatistiquesPeriodiques)
class StatistiquesPeriodiquesAdmin(admin.ModelAdmin):
    """Administration des statistiques périodiques"""
    
    list_display = [
        'poste', 'type_periode', 'periode_formatted',
        'taux_moyen_badge', 'nombre_jours_actifs'
    ]
    
    list_filter = ['type_periode', 'poste__region']
    search_fields = ['poste__nom']
    date_hierarchy = 'date_debut'
    
    readonly_fields = [
        'nombre_jours_actifs', 'total_recettes_declarees',
        'total_recettes_potentielles', 'taux_deperdition_moyen',
        'nombre_jours_impertinents', 'date_calcul'
    ]
    
    def periode_formatted(self, obj):
        """Période formatée"""
        return f"{obj.date_debut.strftime('%d/%m')} - {obj.date_fin.strftime('%d/%m/%Y')}"
    periode_formatted.short_description = 'Période'
    
    def taux_moyen_badge(self, obj):
        """Badge du taux moyen"""
        if obj.taux_deperdition_moyen is None:
            return '-'
        
        taux = float(obj.taux_deperdition_moyen)
        if taux > -10:
            color = 'success'
        elif taux >= -30:
            color = 'warning'
        else:
            color = 'danger'
        
        return format_html(
            '<span class="badge bg-{}">{:.1f}%</span>',
            color, taux
        )
    taux_moyen_badge.short_description = 'Taux moyen'