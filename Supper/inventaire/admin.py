# ===================================================================
# inventaire/admin.py - Interface admin pour les inventaires CORRIGÉE
# CORRESPONDANCE EXACTE avec les modèles définis
# ===================================================================

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.http import HttpResponse
from accounts.admin import admin_site
from .models import (
    ConfigurationJour, InventaireJournalier, DetailInventairePeriode,
    RecetteJournaliere, StatistiquesPeriodiques
)
import csv


class DetailInventairePeriodeInline(admin.TabularInline):
    """Inline pour les détails d'inventaire par période"""
    model = DetailInventairePeriode
    extra = 0
    readonly_fields = ('heure_saisie', 'modifie_le')
    
    def get_queryset(self, request):
        return super().get_queryset(request).order_by('periode')


@admin.register(ConfigurationJour, site=admin_site)
class ConfigurationJourAdmin(admin.ModelAdmin):
    """Administration des configurations de jours"""
    
    list_display = ('date', 'statut_badge', 'cree_par', 'date_creation')
    list_filter = ('statut', 'date_creation')
    search_fields = ('commentaire',)
    ordering = ('-date',)
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Configuration', {
            'fields': ('date', 'statut', 'commentaire'),
            'classes': ('wide',),
        }),
        ('Métadonnées', {
            'fields': ('cree_par', 'date_creation'),
            'classes': ('collapse',),
        }),
    )
    
    readonly_fields = ('date_creation',)
    
    def statut_badge(self, obj):
        """Badge coloré pour le statut"""
        colors = {
            'ouvert': 'success',
            'ferme': 'danger',
            'impertinent': 'warning',
        }
        color = colors.get(obj.statut, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.get_statut_display()
        )
    statut_badge.short_description = 'Statut'
    
    def save_model(self, request, obj, form, change):
        """Logique personnalisée de sauvegarde"""
        if not change:  # Création
            obj.cree_par = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['ouvrir_jours', 'fermer_jours', 'marquer_impertinents']
    
    def ouvrir_jours(self, request, queryset):
        """Action pour ouvrir des jours"""
        count = queryset.update(statut='ouvert')
        self.message_user(request, f'{count} jours ouverts pour la saisie.')
    ouvrir_jours.short_description = 'Ouvrir pour saisie'
    
    def fermer_jours(self, request, queryset):
        """Action pour fermer des jours"""
        count = queryset.update(statut='ferme')
        self.message_user(request, f'{count} jours fermés pour la saisie.')
    fermer_jours.short_description = 'Fermer pour saisie'
    
    def marquer_impertinents(self, request, queryset):
        """Action pour marquer des jours comme impertinents"""
        count = queryset.update(statut='impertinent')
        self.message_user(request, f'{count} jours marqués comme impertinents.')
    marquer_impertinents.short_description = 'Marquer impertinents'


@admin.register(InventaireJournalier, site=admin_site)
class InventaireJournalierAdmin(admin.ModelAdmin):
    """Administration des inventaires journaliers"""
    
    list_display = ('__str__', 'agent_saisie', 'total_vehicules', 'nombre_periodes_saisies',
                   'verrouille_badge', 'valide_badge', 'date_creation')
    list_filter = ('verrouille', 'valide', 'poste__type', 'poste__region', 'date')
    search_fields = ('poste__nom', 'poste__code', 'agent_saisie__username', 'agent_saisie__nom_complet')
    ordering = ('-date', 'poste__nom')
    date_hierarchy = 'date'
    
    inlines = [DetailInventairePeriodeInline]
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('poste', 'date', 'agent_saisie'),
            'classes': ('wide',),
        }),
        ('Totaux calculés', {
            'fields': ('total_vehicules', 'nombre_periodes_saisies'),
            'classes': ('wide',),
        }),
        ('Statut', {
            'fields': ('verrouille', 'valide', 'valide_par', 'date_validation'),
            'classes': ('wide',),
        }),
        ('Observations', {
            'fields': ('observations',),
            'classes': ('collapse',),
        }),
        ('Métadonnées', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',),
        }),
    )
    
    readonly_fields = ('date_creation', 'date_modification', 'total_vehicules', 'nombre_periodes_saisies')
    
    def verrouille_badge(self, obj):
        """Badge pour le statut verrouillé"""
        if obj.verrouille:
            return format_html('<span class="badge bg-warning">Verrouillé</span>')
        return format_html('<span class="badge bg-success">Modifiable</span>')
    verrouille_badge.short_description = 'Verrouillage'
    
    def valide_badge(self, obj):
        """Badge pour le statut validé"""
        if obj.valide:
            return format_html('<span class="badge bg-success">Validé</span>')
        return format_html('<span class="badge bg-secondary">En attente</span>')
    valide_badge.short_description = 'Validation'
    
    def get_queryset(self, request):
        """Optimiser les requêtes"""
        return super().get_queryset(request).select_related(
            'poste', 'agent_saisie', 'valide_par'
        ).prefetch_related('details_periodes')
    
    actions = ['verrouiller_inventaires', 'valider_inventaires', 'export_inventaires', 'recalculer_totaux']
    
    def verrouiller_inventaires(self, request, queryset):
        """Action pour verrouiller des inventaires"""
        count = 0
        for inventaire in queryset.filter(verrouille=False):
            inventaire.verrouiller(request.user)
            count += 1
        self.message_user(request, f'{count} inventaires verrouillés.')
    verrouiller_inventaires.short_description = 'Verrouiller les inventaires'
    
    def valider_inventaires(self, request, queryset):
        """Action pour valider des inventaires"""
        count = queryset.filter(valide=False).update(
            valide=True,
            valide_par=request.user,
            date_validation=timezone.now()
        )
        self.message_user(request, f'{count} inventaires validés.')
    valider_inventaires.short_description = 'Valider les inventaires'
    
    def recalculer_totaux(self, request, queryset):
        """Action pour recalculer les totaux"""
        count = 0
        for inventaire in queryset:
            inventaire.recalculer_totaux()
            count += 1
        self.message_user(request, f'{count} inventaires recalculés.')
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


@admin.register(RecetteJournaliere, site=admin_site)
class RecetteJournaliereAdmin(admin.ModelAdmin):
    """Administration des recettes journalières"""
    
    list_display = ('__str__', 'chef_poste', 'recette_potentielle_formatted', 
                   'ecart_formatted', 'taux_deperdition_badge', 'verrouille_badge')
    list_filter = ('verrouille', 'valide', 'poste__type', 'poste__region', 'date')
    search_fields = ('poste__nom', 'chef_poste__username', 'chef_poste__nom_complet')
    ordering = ('-date', 'poste__nom')
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('poste', 'date', 'chef_poste'),
            'classes': ('wide',),
        }),
        ('Recettes', {
            'fields': ('montant_declare', 'inventaire_associe'),
            'classes': ('wide',),
        }),
        ('Calculs automatiques', {
            'fields': ('recette_potentielle', 'ecart', 'taux_deperdition'),
            'classes': ('wide',),
        }),
        ('Statut', {
            'fields': ('verrouille', 'valide'),
            'classes': ('wide',),
        }),
        ('Observations', {
            'fields': ('observations',),
            'classes': ('collapse',),
        }),
        ('Métadonnées', {
            'fields': ('date_saisie', 'date_modification'),
            'classes': ('collapse',),
        }),
    )
    
    readonly_fields = ('date_saisie', 'date_modification', 'recette_potentielle', 'ecart', 'taux_deperdition')
    
    def recette_potentielle_formatted(self, obj):
        """Recette potentielle formatée"""
        if obj.recette_potentielle:
            return f"{obj.recette_potentielle:,.0f} FCFA".replace(',', ' ')
        return "Non calculée"
    recette_potentielle_formatted.short_description = 'Recette potentielle'
    
    def ecart_formatted(self, obj):
        """Écart formaté avec couleur"""
        if obj.ecart is not None:
            ecart_str = f"{obj.ecart:,.0f} FCFA".replace(',', ' ')
            if obj.ecart >= 0:
                return format_html('<span class="text-success">+{}</span>', ecart_str)
            else:
                return format_html('<span class="text-danger">{}</span>', ecart_str)
        return "Non calculé"
    ecart_formatted.short_description = 'Écart'
    
    def taux_deperdition_badge(self, obj):
        """Badge pour le taux de déperdition"""
        if obj.taux_deperdition is not None:
            couleur = obj.get_couleur_alerte()
            colors = {
                'success': 'success',
                'warning': 'warning', 
                'danger': 'danger',
                'secondary': 'secondary',
            }
            color_class = colors.get(couleur, 'secondary')
            return format_html(
                '<span class="badge bg-{}">{:.2f}%</span>',
                color_class, obj.taux_deperdition
            )
        return format_html('<span class="badge bg-secondary">N/A</span>')
    taux_deperdition_badge.short_description = 'Taux déperdition'
    
    def verrouille_badge(self, obj):
        """Badge pour le statut verrouillé"""
        if obj.verrouille:
            return format_html('<span class="badge bg-warning">Verrouillé</span>')
        return format_html('<span class="badge bg-success">Modifiable</span>')
    verrouille_badge.short_description = 'Statut'
    
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
        self.message_user(request, f'{count} recettes recalculées.')
    recalculer_indicateurs.short_description = 'Recalculer les indicateurs'
    
    def verrouiller_recettes(self, request, queryset):
        """Action pour verrouiller des recettes"""
        count = queryset.filter(verrouille=False).update(verrouille=True)
        self.message_user(request, f'{count} recettes verrouillées.')
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


@admin.register(StatistiquesPeriodiques, site=admin_site)
class StatistiquesPeriodiqueAdmin(admin.ModelAdmin):
    """Administration des statistiques périodiques"""
    
    list_display = ('__str__', 'nombre_jours_actifs', 'total_recettes_declarees_formatted',
                   'taux_deperdition_moyen_badge', 'nombre_jours_impertinents', 'date_calcul')
    list_filter = ('type_periode', 'poste__type', 'poste__region', 'date_debut')
    search_fields = ('poste__nom',)
    ordering = ('-date_debut', 'poste__nom')
    date_hierarchy = 'date_debut'
    
    fieldsets = (
        ('Période', {
            'fields': ('poste', 'type_periode', 'date_debut', 'date_fin'),
            'classes': ('wide',),
        }),
        ('Données consolidées', {
            'fields': ('nombre_jours_actifs', 'total_recettes_declarees', 
                      'total_recettes_potentielles', 'taux_deperdition_moyen'),
            'classes': ('wide',),
        }),
        ('Anomalies', {
            'fields': ('nombre_jours_impertinents',),
            'classes': ('wide',),
        }),
        ('Métadonnées', {
            'fields': ('date_calcul',),
            'classes': ('collapse',),
        }),
    )
    
    readonly_fields = ('date_calcul',)
    
    def total_recettes_declarees_formatted(self, obj):
        """Total recettes formaté"""
        return f"{obj.total_recettes_declarees:,.0f} FCFA".replace(',', ' ')
    total_recettes_declarees_formatted.short_description = 'Total déclaré'
    
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
        
        self.message_user(request, f'{count} statistiques recalculées.')
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


# AJOUT : Admin pour DetailInventairePeriode (pour gestion directe si nécessaire)
@admin.register(DetailInventairePeriode, site=admin_site)
class DetailInventairePeriodeAdmin(admin.ModelAdmin):
    """Administration des détails d'inventaire par période"""
    
    list_display = ('inventaire', 'periode', 'nombre_vehicules', 'heure_saisie', 'observations_periode')
    list_filter = ('periode', 'inventaire__date', 'inventaire__poste')
    search_fields = ('inventaire__poste__nom', 'observations_periode')
    ordering = ('-inventaire__date', 'inventaire__poste__nom', 'periode')
    
    fieldsets = (
        ('Inventaire', {
            'fields': ('inventaire', 'periode'),
            'classes': ('wide',),
        }),
        ('Données', {
            'fields': ('nombre_vehicules', 'observations_periode'),
            'classes': ('wide',),
        }),
        ('Métadonnées', {
            'fields': ('heure_saisie', 'modifie_le'),
            'classes': ('collapse',),
        }),
    )
    
    readonly_fields = ('heure_saisie', 'modifie_le')
    
    def get_queryset(self, request):
        """Optimiser les requêtes"""
        return super().get_queryset(request).select_related(
            'inventaire', 'inventaire__poste', 'inventaire__agent_saisie'
        )