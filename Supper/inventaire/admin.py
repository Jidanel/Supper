# ===================================================================
# inventaire/admin.py - Interface admin pour les inventaires CORRIGÉE
# VERSION COMPLÈTE AVEC TOUTES LES CLASSES NÉCESSAIRES
# ===================================================================

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.http import HttpResponse
from django import forms
from datetime import date
from django.utils.html import format_html
from .models import (
    ConfigurationJour, InventaireJournalier, DetailInventairePeriode,
    RecetteJournaliere, StatistiquesPeriodiques
)
import csv

# ===================================================================
# FORMULAIRES PERSONNALISÉS
# ===================================================================

class DetailInventairePeriodeInlineForm(forms.ModelForm):
    """Formulaire pour la saisie inline des périodes"""
    class Meta:
        model = DetailInventairePeriode
        fields = ['periode', 'nombre_vehicules', 'observations_periode']
        widgets = {
            'periode': forms.Select(attrs={
                'class': 'form-control',
                'style': 'width: 120px;'
            }),
            'nombre_vehicules': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '1000',
                'style': 'width: 100px;',
                'placeholder': '0'
            }),
            'observations_periode': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Observations (optionnel)',
                'style': 'width: 300px;'
            })
        }

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
    list_display = ['date', 'statut_colored', 'cree_par', 'date_creation']
    list_filter = ['statut', 'date_creation']
    search_fields = ['commentaire']
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('date', 'statut')
        }),
        ('Détails', {
            'fields': ('commentaire', 'cree_par', 'date_creation'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('cree_par', 'date_creation')
    
    def statut_colored(self, obj):
        """Affichage coloré du statut"""
        colors = {
            'ouvert': 'success',
            'ferme': 'danger',
            'impertinent': 'warning'
        }
        color = colors.get(obj.statut, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.get_statut_display()
        )
    statut_colored.short_description = 'Statut'
    
    def save_model(self, request, obj, form, change):
        """Logique personnalisée de sauvegarde"""
        if not change:  # Création
            obj.cree_par = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['ouvrir_jours', 'fermer_jours', 'marquer_impertinents']
    
    def ouvrir_jours(self, request, queryset):
        """Action pour ouvrir des jours"""
        count = queryset.update(statut='ouvert')
        self.message_user(request, f'{count} jour(s) ouvert(s) pour la saisie.')
    ouvrir_jours.short_description = 'Ouvrir pour saisie'
    
    def fermer_jours(self, request, queryset):
        """Action pour fermer des jours"""
        count = queryset.update(statut='ferme')
        self.message_user(request, f'{count} jour(s) fermé(s) pour la saisie.')
    fermer_jours.short_description = 'Fermer pour saisie'
    
    def marquer_impertinents(self, request, queryset):
        """Action pour marquer des jours comme impertinents"""
        count = queryset.update(statut='impertinent')
        self.message_user(request, f'{count} jour(s) marqué(s) comme impertinent(s).')
    marquer_impertinents.short_description = 'Marquer impertinents'


@admin.register(InventaireJournalier)
class InventaireJournalierAdmin(admin.ModelAdmin):
    form = InventaireJournalierForm
    inlines = [DetailInventairePeriodeInline]  # Inline pour saisie des périodes
    
    # Configuration de la liste
    list_display = [
        'poste', 'date', 'agent_saisie', 
        'total_vehicules_colored', 'nombre_periodes_colored',
        'status_inventaire'
    ]
    list_filter = ['date', 'verrouille', 'valide', 'poste__region', 'poste__type']
    search_fields = ['poste__nom', 'poste__code', 'agent_saisie__nom_complet']
    date_hierarchy = 'date'
    
    # Organisation des champs
    fieldsets = (
        ('Informations générales', {
            'fields': ('poste', 'date', 'agent_saisie'),
            'description': 'Informations de base de l\'inventaire'
        }),
        ('État', {
            'fields': ('verrouille', 'valide', 'valide_par', 'date_validation'),
            'description': 'État de validation de l\'inventaire'
        }),
        ('Totaux calculés', {
            'fields': ('total_vehicules', 'nombre_periodes_saisies'),
            'description': 'Ces valeurs sont calculées automatiquement',
            'classes': ('collapse',)
        }),
        ('Observations', {
            'fields': ('observations',),
            'classes': ('wide',)
        }),
    )
    
    # Champs en lecture seule
    readonly_fields = [
        'total_vehicules', 'nombre_periodes_saisies',
        'valide_par', 'date_validation'
    ]
    
    def total_vehicules_colored(self, obj):
        """Affichage coloré du total de véhicules"""
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
    total_vehicules_colored.short_description = 'Total véhicules'
    
    def nombre_periodes_colored(self, obj):
        """Affichage coloré du nombre de périodes saisies"""
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
    nombre_periodes_colored.short_description = 'Périodes saisies'
    
    def status_inventaire(self, obj):
        """Affichage du statut de l'inventaire"""
        if obj.valide:
            return format_html(
                '<span class="badge bg-success">✓ Validé</span>'
            )
        elif obj.verrouille:
            return format_html(
                '<span class="badge bg-warning">🔒 Verrouillé</span>'
            )
        else:
            return format_html(
                '<span class="badge bg-info">📝 En cours</span>'
            )
    status_inventaire.short_description = 'Statut'
    
    def save_model(self, request, obj, form, change):
        """Gestion automatique de la validation"""
        if obj.valide and not obj.valide_par:
            obj.valide_par = request.user
            # Utiliser le timezone de Django
            obj.date_validation = timezone.now()
        super().save_model(request, obj, form, change)
    
    def save_formset(self, request, form, formset, change):
        """Sauvegarde des périodes et recalcul automatique des totaux"""
        instances = formset.save(commit=False)
        
        for instance in instances:
            instance.save()
        
        formset.save_m2m()
        
        # Recalculer les totaux après sauvegarde des périodes
        if form.instance:
            form.instance.recalculer_totaux()
    
    def get_queryset(self, request):
        """Optimiser les requêtes"""
        return super().get_queryset(request).select_related(
            'poste', 'agent_saisie', 'valide_par'
        ).prefetch_related('details_periodes')
    
    actions = ['verrouiller_inventaires', 'valider_inventaires', 'export_inventaires', 'recalculer_totaux']
    
    def verrouiller_inventaires(self, request, queryset):
        """Action pour verrouiller plusieurs inventaires"""
        count = 0
        for inventaire in queryset:
            if not inventaire.verrouille:
                inventaire.verrouiller(request.user)
                count += 1
        self.message_user(request, f'{count} inventaire(s) verrouillé(s)')
    verrouiller_inventaires.short_description = "Verrouiller les inventaires sélectionnés"
    def changelist_view(self, request, extra_context=None):
        """Ajouter un bouton pour gérer les jours du mois"""
        extra_context = extra_context or {}
        
        # Ajouter l'URL de gestion des jours
        today = date.today()
        gerer_jours_url = reverse('inventaire:gerer_jours', args=[1])
        
        extra_context['custom_buttons'] = format_html(
            '<a class="btn btn-primary" href="{}">📅 Gérer les jours du mois</a>',
            gerer_jours_url
        )
        
        return super().changelist_view(request, extra_context)
    def valider_inventaires(self, request, queryset):
        """Action pour valider plusieurs inventaires"""
        count = 0
        for inventaire in queryset:
            if not inventaire.valide:
                inventaire.valide = True
                inventaire.valide_par = request.user
                inventaire.date_validation = timezone.now()
                inventaire.save()
                count += 1
        self.message_user(request, f'{count} inventaire(s) validé(s)')
    valider_inventaires.short_description = "Valider les inventaires sélectionnés"
    
    def recalculer_totaux(self, request, queryset):
        """Action pour recalculer les totaux"""
        count = 0
        for inventaire in queryset:
            inventaire.recalculer_totaux()
            count += 1
        self.message_user(request, f'{count} inventaire(s) recalculé(s).')
    recalculer_totaux.short_description = 'Recalculer les totaux'
    
    def export_inventaires(self, request, queryset):
        """Export CSV des inventaires"""
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="inventaires_supper.csv"'
        
        # Ajouter le BOM UTF-8 pour Excel
        response.write('\ufeff')
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Date', 'Poste', 'Agent', 'Total Véhicules', 'Périodes Saisies', 
                        'Verrouillé', 'Validé', 'Recette Potentielle (FCFA)', 'Moyenne Horaire'])
        
        for inventaire in queryset:
            recette_potentielle = inventaire.calculer_recette_potentielle()
            moyenne_horaire = inventaire.calculer_moyenne_horaire()
            
            writer.writerow([
                inventaire.date.strftime('%d/%m/%Y'),
                inventaire.poste.nom,
                inventaire.agent_saisie.nom_complet if inventaire.agent_saisie else 'Non renseigné',
                inventaire.total_vehicules,
                inventaire.nombre_periodes_saisies,
                'Oui' if inventaire.verrouille else 'Non',
                'Oui' if inventaire.valide else 'Non',
                f"{recette_potentielle:,.0f}".replace(',', ' '),
                f"{moyenne_horaire:.1f}"
            ])
        
        return response
    export_inventaires.short_description = 'Exporter en CSV'


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
    list_display = [
        'poste', 'date', 'montant_declare_formatted', 
        'taux_deperdition_colored', 'status_recette'
    ]
    list_filter = ['date', 'poste__region', 'verrouille', 'valide']
    search_fields = ['poste__nom', 'chef_poste__nom_complet']
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('poste', 'date', 'chef_poste', 'montant_declare')
        }),
        ('Calculs automatiques', {
            'fields': (
                'inventaire_associe', 'recette_potentielle', 
                'ecart', 'taux_deperdition'
            ),
            'classes': ('collapse',)
        }),
        ('État', {
            'fields': ('verrouille', 'valide')
        }),
        ('Observations', {
            'fields': ('observations',)
        }),
    )
    
    readonly_fields = [
        'recette_potentielle', 'ecart', 'taux_deperdition'
    ]
    
    def montant_declare_formatted(self, obj):
        """Format monétaire du montant"""
        return format_html(
            '<strong>{:,.0f} FCFA</strong>',
            obj.montant_declare
        )
    montant_declare_formatted.short_description = 'Montant déclaré'
    
    def taux_deperdition_colored(self, obj):
        """Affichage coloré du taux de déperdition"""
        if obj.taux_deperdition is None:
            return '-'
        
        couleur = obj.get_couleur_alerte()
        return format_html(
            '<span class="badge bg-{}">{:.1f}%</span>',
            couleur, obj.taux_deperdition
        )
    taux_deperdition_colored.short_description = 'Taux déperdition'
    
    def status_recette(self, obj):
        """Statut de la recette"""
        if obj.valide:
            return format_html('<span class="badge bg-success">✓ Validée</span>')
        elif obj.verrouille:
            return format_html('<span class="badge bg-warning">🔒 Verrouillée</span>')
        else:
            return format_html('<span class="badge bg-info">📝 En cours</span>')
    status_recette.short_description = 'Statut'
    
    def get_queryset(self, request):
        """Optimiser les requêtes"""
        return super().get_queryset(request).select_related(
            'poste', 'chef_poste', 'inventaire_associe'
        )
    
    actions = ['recalculer_indicateurs', 'verrouiller_recettes', 'export_recettes']
    
    def recalculer_indicateurs(self, request, queryset):
        """Action pour recalculer les indicateurs"""
        count = 0
        for recette in queryset:
            recette.calculer_indicateurs()
            recette.save()
            count += 1
        self.message_user(request, f'{count} recette(s) recalculée(s).')
    recalculer_indicateurs.short_description = 'Recalculer les indicateurs'
    
    def verrouiller_recettes(self, request, queryset):
        """Action pour verrouiller des recettes"""
        count = queryset.filter(verrouille=False).update(verrouille=True)
        self.message_user(request, f'{count} recette(s) verrouillée(s).')
    verrouiller_recettes.short_description = 'Verrouiller les recettes'
    
    def export_recettes(self, request, queryset):
        """Export CSV des recettes"""
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="recettes_supper.csv"'
        
        # Ajouter le BOM UTF-8 pour Excel
        response.write('\ufeff')
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Date', 'Poste', 'Chef', 'Montant Déclaré (FCFA)', 'Recette Potentielle (FCFA)',
                        'Écart (FCFA)', 'Taux Déperdition (%)', 'Couleur Alerte', 'Statut'])
        
        for recette in queryset:
            writer.writerow([
                recette.date.strftime('%d/%m/%Y'),
                recette.poste.nom,
                recette.chef_poste.nom_complet if recette.chef_poste else 'Non renseigné',
                f"{recette.montant_declare:,.0f}".replace(',', ' '),
                f"{recette.recette_potentielle:,.0f}".replace(',', ' ') if recette.recette_potentielle else 'N/A',
                f"{recette.ecart:,.0f}".replace(',', ' ') if recette.ecart else 'N/A',
                f"{recette.taux_deperdition:.2f}" if recette.taux_deperdition else 'N/A',
                recette.get_couleur_alerte() if recette.taux_deperdition else 'N/A',
                'Verrouillé' if recette.verrouille else 'Modifiable'
            ])
        
        return response
    export_recettes.short_description = 'Exporter en CSV'


@admin.register(StatistiquesPeriodiques)
class StatistiquesPeriodiquesAdmin(admin.ModelAdmin):
    list_display = [
        'poste', 'type_periode', 'date_debut', 
        'date_fin', 'taux_deperdition_moyen_badge'
    ]
    list_filter = ['type_periode', 'poste__region']
    search_fields = ['poste__nom']
    date_hierarchy = 'date_debut'
    
    readonly_fields = [
        'total_recettes_declarees', 'total_recettes_potentielles',
        'taux_deperdition_moyen', 'nombre_jours_impertinents', 'date_calcul'
    ]
    
    fieldsets = (
        ('Période', {
            'fields': ('poste', 'type_periode', 'date_debut', 'date_fin')
        }),
        ('Statistiques calculées', {
            'fields': (
                'nombre_jours_actifs', 'total_recettes_declarees',
                'total_recettes_potentielles', 'taux_deperdition_moyen',
                'nombre_jours_impertinents'
            )
        }),
        ('Métadonnées', {
            'fields': ('date_calcul',),
            'classes': ('collapse',)
        }),
    )
    
    def taux_deperdition_moyen_badge(self, obj):
        """Badge pour le taux moyen"""
        if obj.taux_deperdition_moyen is not None:
            if obj.taux_deperdition_moyen > -10:
                color = 'success'
            elif obj.taux_deperdition_moyen >= -30:
                color = 'warning'
            else:
                color = 'danger'
            
            return format_html(
                '<span class="badge bg-{}">{:.2f}%</span>',
                color, obj.taux_deperdition_moyen
            )
        return format_html('<span class="badge bg-secondary">N/A</span>')
    taux_deperdition_moyen_badge.short_description = 'Taux moyen'
    
    def get_queryset(self, request):
        """Optimiser les requêtes"""
        return super().get_queryset(request).select_related('poste')
    
    actions = ['export_statistiques', 'recalculer_statistiques']
    
    def recalculer_statistiques(self, request, queryset):
        """Action pour recalculer les statistiques"""
        count = 0
        for stat in queryset:
            # Recalculer les statistiques en appelant la méthode du modèle
            stat_recalculee = StatistiquesPeriodiques.calculer_statistiques_periode(
                stat.poste, stat.type_periode, stat.date_debut, stat.date_fin
            )
            if stat_recalculee:
                count += 1
        
        self.message_user(request, f'{count} statistique(s) recalculée(s).')
    recalculer_statistiques.short_description = 'Recalculer les statistiques'
    
    def export_statistiques(self, request, queryset):
        """Export CSV des statistiques"""
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="statistiques_supper.csv"'
        
        # Ajouter le BOM UTF-8 pour Excel
        response.write('\ufeff')
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Poste', 'Type Période', 'Début', 'Fin', 'Jours Actifs',
                        'Total Déclaré (FCFA)', 'Total Potentiel (FCFA)', 'Taux Moyen (%)', 
                        'Jours Impertinents', 'Date Calcul'])
        
        for stat in queryset:
            writer.writerow([
                stat.poste.nom,
                stat.get_type_periode_display(),
                stat.date_debut.strftime('%d/%m/%Y'),
                stat.date_fin.strftime('%d/%m/%Y'),
                stat.nombre_jours_actifs,
                f"{stat.total_recettes_declarees:,.0f}".replace(',', ' '),
                f"{stat.total_recettes_potentielles:,.0f}".replace(',', ' '),
                f"{stat.taux_deperdition_moyen:.2f}" if stat.taux_deperdition_moyen else 'N/A',
                stat.nombre_jours_impertinents,
                stat.date_calcul.strftime('%d/%m/%Y %H:%M')
            ])
        
        return response
    export_statistiques.short_description = 'Exporter en CSV'