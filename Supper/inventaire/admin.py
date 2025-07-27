# ===================================================================
# Fichier : Supper/inventaire/admin.py
# Interface admin Django pour gestion complète des inventaires
# Accessible aux administrateurs et services autorisés
# ===================================================================

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.db.models import Count, Avg, Sum
from django.contrib.admin import SimpleListFilter
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib import messages
import datetime
import csv
from django.http import HttpResponse

from .models import (
    ConfigurationJour, InventaireJournalier, DetailInventairePeriode,
    RecetteJournaliere, StatistiquesPeriodiques
)


# ===================================================================
# FILTRES PERSONNALISÉS POUR INVENTAIRES
# ===================================================================

class PeriodeFilter(SimpleListFilter):
    """Filtre par période pour inventaires"""
    title = _('Période')
    parameter_name = 'periode'

    def lookups(self, request, model_admin):
        return [
            ('today', _('Aujourd\'hui')),
            ('week', _('Cette semaine')),
            ('month', _('Ce mois')),
            ('quarter', _('Ce trimestre')),
        ]

    def queryset(self, request, queryset):
        now = datetime.datetime.now()
        
        if self.value() == 'today':
            return queryset.filter(date=now.date())
        elif self.value() == 'week':
            start_week = now.date() - datetime.timedelta(days=now.weekday())
            return queryset.filter(date__gte=start_week)
        elif self.value() == 'month':
            return queryset.filter(date__year=now.year, date__month=now.month)
        elif self.value() == 'quarter':
            # Calcul du trimestre actuel
            quarter_start_month = ((now.month - 1) // 3) * 3 + 1
            quarter_start = datetime.date(now.year, quarter_start_month, 1)
            return queryset.filter(date__gte=quarter_start)
        return queryset


class PosteRegionFilter(SimpleListFilter):
    """Filtre par région des postes"""
    title = _('Région du poste')
    parameter_name = 'poste_region'

    def lookups(self, request, model_admin):
        from accounts.models import Poste
        regions = Poste.objects.values_list('region', flat=True).distinct()
        return [(region, region) for region in regions if region]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(poste__region=self.value())
        return queryset


class TauxDeperditionFilter(SimpleListFilter):
    """Filtre par niveau de taux de déperdition"""
    title = _('Niveau de déperdition')
    parameter_name = 'taux_deperdition'

    def lookups(self, request, model_admin):
        return [
            ('bon', _('Bon (0 à -10%)')),
            ('attention', _('Attention (-10% à -30%)')),
            ('critique', _('Critique (< -30%)')),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'bon':
            return queryset.filter(taux_deperdition__gt=-10)
        elif self.value() == 'attention':
            return queryset.filter(taux_deperdition__lte=-10, taux_deperdition__gte=-30)
        elif self.value() == 'critique':
            return queryset.filter(taux_deperdition__lt=-30)
        return queryset


# ===================================================================
# ACTIONS PERSONNALISÉES
# ===================================================================

def ouvrir_jours_selection(modeladmin, request, queryset):
    """Ouvre les jours sélectionnés pour saisie"""
    updated = queryset.update(statut='ouvert')
    messages.success(request, f'{updated} jour(s) ouvert(s) pour saisie.')

def fermer_jours_selection(modeladmin, request, queryset):
    """Ferme les jours sélectionnés"""
    updated = queryset.update(statut='ferme')
    messages.warning(request, f'{updated} jour(s) fermé(s) pour saisie.')

def verrouiller_inventaires(modeladmin, request, queryset):
    """Verrouille les inventaires sélectionnés"""
    updated = queryset.update(verrouille=True)
    messages.info(request, f'{updated} inventaire(s) verrouillé(s).')

def exporter_inventaires_csv(modeladmin, request, queryset):
    """Exporte les inventaires en CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventaires_supper.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Date', 'Poste', 'Agent', 'Total Véhicules', 'Périodes Saisies',
        'Moyenne Horaire', 'Estimation 24h', 'Recette Potentielle', 'Verrouillé'
    ])
    
    for inv in queryset:
        writer.writerow([
            inv.date.strftime('%d/%m/%Y'),
            inv.poste.nom,
            inv.agent_saisie.nom_complet if inv.agent_saisie else 'N/A',
            inv.total_vehicules,
            inv.nombre_periodes_saisies,
            inv.calculer_moyenne_horaire(),
            inv.estimer_total_24h(),
            inv.calculer_recette_potentielle(),
            'Oui' if inv.verrouille else 'Non'
        ])
    
    return response

# Configuration des actions
ouvrir_jours_selection.short_description = "🔓 Ouvrir jours sélectionnés"
fermer_jours_selection.short_description = "🔒 Fermer jours sélectionnés"
verrouiller_inventaires.short_description = "🔐 Verrouiller inventaires"
exporter_inventaires_csv.short_description = "📊 Exporter en CSV"


# ===================================================================
# ADMIN CONFIGURATION JOUR
# ===================================================================

@admin.register(ConfigurationJour)
class ConfigurationJourAdmin(admin.ModelAdmin):
    """
    Gestion des jours ouverts/fermés pour saisie
    Fonction critique pour contrôler les périodes de saisie
    """
    
    list_display = (
        'date',
        'get_jour_semaine',
        'get_statut_badge',
        'get_inventaires_count',
        'get_recettes_count',
        'cree_par',
        'get_actions_rapides'
    )
    
    list_filter = (
        'statut',  # Changé de 'ouvert' vers 'statut'
        PeriodeFilter,
        'cree_par__habilitation',
    )
    
    search_fields = (
        'date',
        'commentaire',  # Changé de 'description' vers 'commentaire'
        'cree_par__nom_complet',
    )
    
    date_hierarchy = 'date'
    ordering = ('-date',)
    list_per_page = 30
    
    actions = [ouvrir_jours_selection, fermer_jours_selection]
    
    fieldsets = (
        (_('Configuration du Jour'), {
            'fields': (
                'date',
                'statut',  # Changé de 'ouvert' vers 'statut'
                'commentaire',  # Changé de 'description' vers 'commentaire'
            )
        }),
        (_('Informations Système'), {
            'classes': ('collapse',),
            'fields': (
                'cree_par',
                'date_creation',
            )
        }),
    )
    
    readonly_fields = ('cree_par', 'date_creation')
    
    def get_jour_semaine(self, obj):
        """Affiche le jour de la semaine"""
        jours = {
            0: 'Lundi', 1: 'Mardi', 2: 'Mercredi', 3: 'Jeudi',
            4: 'Vendredi', 5: 'Samedi', 6: 'Dimanche'
        }
        return jours.get(obj.date.weekday(), '')
    
    get_jour_semaine.short_description = _('Jour')
    
    def get_statut_badge(self, obj):
        """Badge statut ouvert/fermé"""
        if obj.statut == 'ouvert':
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 4px 10px; '
                'border-radius: 12px; font-size: 11px; font-weight: bold;">'
                '<i class="fas fa-unlock"></i> Ouvert</span>'
            )
        elif obj.statut == 'ferme':
            return format_html(
                '<span style="background-color: #dc3545; color: white; padding: 4px 10px; '
                'border-radius: 12px; font-size: 11px; font-weight: bold;">'
                '<i class="fas fa-lock"></i> Fermé</span>'
            )
        else:  # impertinent
            return format_html(
                '<span style="background-color: #ffc107; color: #000; padding: 4px 10px; '
                'border-radius: 12px; font-size: 11px; font-weight: bold;">'
                '<i class="fas fa-exclamation-triangle"></i> Impertinent</span>'
            )
    
    get_statut_badge.short_description = _('Statut')
    get_statut_badge.admin_order_field = 'statut'
    
    def get_inventaires_count(self, obj):
        """Nombre d'inventaires pour ce jour"""
        count = InventaireJournalier.objects.filter(date=obj.date).count()
        color = '#198754' if count > 0 else '#6c757d'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, count
        )
    
    get_inventaires_count.short_description = _('Inventaires')
    
    def get_recettes_count(self, obj):
        """Nombre de recettes pour ce jour"""
        count = RecetteJournaliere.objects.filter(date=obj.date).count()
        color = '#0d6efd' if count > 0 else '#6c757d'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, count
        )
    
    get_recettes_count.short_description = _('Recettes')
    
    def get_actions_rapides(self, obj):
        """Actions rapides sur configuration jour"""
        actions = []
        
        # Bouton voir inventaires du jour
        inv_count = InventaireJournalier.objects.filter(date=obj.date).count()
        if inv_count > 0:
            actions.append(
                f'<a href="/admin/inventaire/inventairejournalier/?date__exact={obj.date}" '
                f'class="btn btn-sm btn-outline-success" title="Voir inventaires ({inv_count})">'
                f'<i class="fas fa-list"></i></a>'
            )
        
        # Bouton voir recettes du jour
        rec_count = RecetteJournaliere.objects.filter(date=obj.date).count()
        if rec_count > 0:
            actions.append(
                f'<a href="/admin/inventaire/recettejournaliere/?date__exact={obj.date}" '
                f'class="btn btn-sm btn-outline-primary" title="Voir recettes ({rec_count})">'
                f'<i class="fas fa-money-bill"></i></a>'
            )
        
        return format_html(' '.join(actions))
    
    get_actions_rapides.short_description = _('Actions')
    
    def save_model(self, request, obj, form, change):
        """Sauvegarde avec assignation du créateur"""
        if not change:
            obj.cree_par = request.user
        super().save_model(request, obj, form, change)


# ===================================================================
# ADMIN INVENTAIRE JOURNALIER
# ===================================================================

@admin.register(InventaireJournalier)
class InventaireJournalierAdmin(admin.ModelAdmin):
    """
    Gestion complète des inventaires journaliers
    Interface principale pour les administrateurs
    """
    
    list_display = (
        'date',
        'poste',
        'get_agent_saisie',  # Changé de 'agent' vers méthode personnalisée
        'get_total_vehicules',
        'get_periodes_badge',
        'get_recette_potentielle',
        'get_verrouille_badge',
        'get_actions_rapides'
    )
    
    list_display_links = ('date', 'poste')
    
    list_filter = (
        PeriodeFilter,
        PosteRegionFilter,
        'poste__type',  # Supposé exister dans le modèle Poste
        'verrouille',
        'agent_saisie__habilitation',  # Changé de 'agent__habilitation'
    )
    
    search_fields = (
        'poste__nom',
        'poste__code',
        'agent_saisie__nom_complet',  # Changé de 'agent__nom_complet'
        'agent_saisie__username',     # Changé de 'agent__username'
        'observations',               # Changé de 'observations_generales'
    )
    
    date_hierarchy = 'date'
    ordering = ('-date', 'poste__nom')
    list_per_page = 25
    
    actions = [verrouiller_inventaires, exporter_inventaires_csv]
    
    fieldsets = (
        (_('Informations Principales'), {
            'fields': (
                'date',
                'poste',
                'agent_saisie',  # Changé de 'agent'
            )
        }),
        (_('Calculs Automatiques'), {
            'classes': ('collapse',),
            'fields': (
                ('total_vehicules', 'nombre_periodes_saisies'),  # Changé de 'periodes_saisies'
                ('get_moyenne_horaire', 'get_estimation_24h'),   # Méthodes du modèle
                'get_recette_potentielle_value',                # Méthode du modèle
            )
        }),
        (_('Statut et Observations'), {
            'fields': (
                'verrouille',
                'valide',
                'valide_par',
                'date_validation',
                'observations',  # Changé de 'observations_generales'
            )
        }),
        (_('Informations Système'), {
            'classes': ('collapse',),
            'fields': (
                'date_creation',
                'date_modification',
            )
        }),
    )
    
    readonly_fields = (
        'total_vehicules',
        'nombre_periodes_saisies',  # Changé de 'periodes_saisies'
        'get_moyenne_horaire',      # Méthodes du modèle
        'get_estimation_24h',
        'get_recette_potentielle_value',
        'date_creation',
        'date_modification',
    )
    
    # Inlines pour détails par période
    class DetailInventairePeriodeInline(admin.TabularInline):
        """Inline pour saisie des détails par période"""
        model = DetailInventairePeriode
        extra = 0
        max_num = 10  # 10 créneaux horaires maximum
        
        fields = (
            'periode',            # Changé de 'periode_debut' et 'periode_fin'
            'nombre_vehicules',
            'observations_periode', # Changé de 'observations'
        )
        
        readonly_fields = ()  # Pas de readonly car 'periode' remplace les deux champs
        
        def get_readonly_fields(self, request, obj=None):
            """Lecture seule si inventaire verrouillé"""
            if obj and obj.verrouille:
                return self.fields
            return self.readonly_fields
    
    inlines = [DetailInventairePeriodeInline]
    
    def get_agent_saisie(self, obj):
        """Affichage de l'agent de saisie"""
        if obj.agent_saisie:
            return obj.agent_saisie.nom_complet
        return "Non assigné"
    
    get_agent_saisie.short_description = _('Agent')
    get_agent_saisie.admin_order_field = 'agent_saisie'
    
    def get_moyenne_horaire(self, obj):
        """Affichage de la moyenne horaire"""
        return f"{obj.calculer_moyenne_horaire():.1f}"
    
    get_moyenne_horaire.short_description = _('Moyenne Horaire')
    
    def get_estimation_24h(self, obj):
        """Affichage de l'estimation 24h"""
        return f"{obj.estimer_total_24h():.0f}"
    
    get_estimation_24h.short_description = _('Estimation 24h')
    
    def get_recette_potentielle_value(self, obj):
        """Affichage de la recette potentielle"""
        return f"{obj.calculer_recette_potentielle():.0f} FCFA"
    
    get_recette_potentielle_value.short_description = _('Recette Potentielle')
    
    def get_total_vehicules(self, obj):
        """Affichage coloré du total véhicules"""
        total = obj.total_vehicules or 0
        color = '#198754' if total > 0 else '#6c757d'
        return format_html(
            '<span style="color: {}; font-weight: bold; font-size: 14px;">{}</span>',
            color, total
        )
    
    get_total_vehicules.short_description = _('Total Véhicules')
    get_total_vehicules.admin_order_field = 'total_vehicules'
    
    def get_periodes_badge(self, obj):
        """Badge du nombre de périodes saisies"""
        periodes = obj.nombre_periodes_saisies or 0
        # Couleur selon la complétude
        if periodes == 10:
            color = '#28a745'  # Vert - complet
        elif periodes >= 5:
            color = '#ffc107'  # Jaune - partiel
        else:
            color = '#dc3545'  # Rouge - insuffisant
        
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 10px; font-size: 11px; font-weight: bold;">{}/10</span>',
            color, periodes
        )
    
    get_periodes_badge.short_description = _('Périodes')
    get_periodes_badge.admin_order_field = 'nombre_periodes_saisies'
    
    def get_recette_potentielle(self, obj):
        """Affichage formaté de la recette potentielle (si autorisé)"""
        recette = obj.calculer_recette_potentielle()
        if recette:
            return format_html(
                '<span style="color: #0d6efd; font-weight: bold;">{:,.0f} FCFA</span>',
                recette
            )
        return format_html('<span style="color: #6c757d;">N/A</span>')
    
    get_recette_potentielle.short_description = _('Recette Potentielle')
    
    def get_verrouille_badge(self, obj):
        """Badge statut verrouillé/modifiable"""
        if obj.verrouille:
            return format_html(
                '<span style="background-color: #dc3545; color: white; padding: 3px 8px; '
                'border-radius: 8px; font-size: 11px;"><i class="fas fa-lock"></i> Verrouillé</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 3px 8px; '
                'border-radius: 8px; font-size: 11px;"><i class="fas fa-unlock"></i> Modifiable</span>'
            )
    
    get_verrouille_badge.short_description = _('Statut')
    get_verrouille_badge.admin_order_field = 'verrouille'
    
    def get_actions_rapides(self, obj):
        """Actions rapides sur inventaires"""
        actions = []
        
        # Bouton voir détails par période
        if obj.details_periodes.exists():
            actions.append(
                f'<a href="/admin/inventaire/detailinventaireperiode/?inventaire__id__exact={obj.pk}" '
                f'class="btn btn-sm btn-outline-info" title="Voir détails périodes">'
                f'<i class="fas fa-clock"></i></a>'
            )
        
        # Bouton voir recette associée
        try:
            recette = RecetteJournaliere.objects.get(date=obj.date, poste=obj.poste)
            actions.append(
                f'<a href="/admin/inventaire/recettejournaliere/{recette.pk}/change/" '
                f'class="btn btn-sm btn-outline-success" title="Voir recette">'
                f'<i class="fas fa-money-bill"></i></a>'
            )
        except RecetteJournaliere.DoesNotExist:
            actions.append(
                f'<span class="btn btn-sm btn-outline-secondary" title="Pas de recette">'
                f'<i class="fas fa-minus"></i></span>'
            )
        
        return format_html(' '.join(actions))
    
    get_actions_rapides.short_description = _('Actions')
    
    def get_readonly_fields(self, request, obj=None):
        """Champs lecture seule selon statut et permissions utilisateur"""
        readonly = list(self.readonly_fields)
        
        # Si inventaire verrouillé, tout en lecture seule sauf pour admin principal
        if obj and obj.verrouille and not request.user.habilitation == 'admin_principal':
            readonly.extend(['date', 'poste', 'agent_saisie', 'observations'])
        
        return readonly
    
    def has_delete_permission(self, request, obj=None):
        """Seuls les admins principaux peuvent supprimer"""
        return request.user.habilitation == 'admin_principal'


# ===================================================================
# ADMIN DÉTAIL INVENTAIRE PÉRIODE
# ===================================================================

@admin.register(DetailInventairePeriode)
class DetailInventairePeriodeAdmin(admin.ModelAdmin):
    """
    Gestion des détails par période horaire
    Vue détaillée pour analyse fine
    """
    
    list_display = (
        'inventaire',
        'get_periode_complete',
        'nombre_vehicules',
        'get_observations_preview',
        'get_pourcentage_jour'
    )
    
    list_filter = (
        'periode',  # Changé de 'periode_debut'
        'inventaire__date',
        'inventaire__poste__region',
        'inventaire__poste__type',
    )
    
    search_fields = (
        'inventaire__poste__nom',
        'inventaire__agent_saisie__nom_complet',  # Changé de 'agent__nom_complet'
        'observations_periode',  # Changé de 'observations'
    )
    
    ordering = ('inventaire__date', 'periode')  # Changé de 'periode_debut'
    list_per_page = 50
    
    fieldsets = (
        (_('Inventaire et Période'), {
            'fields': (
                'inventaire',
                'periode',  # Un seul champ au lieu de deux
            )
        }),
        (_('Données Collectées'), {
            'fields': (
                'nombre_vehicules',
                'observations_periode',  # Changé de 'observations'
            )
        }),
    )
    
    def get_periode_complete(self, obj):
        """Affichage formaté de la période"""
        return obj.get_periode_display()  # Utilise le display du choix
    
    get_periode_complete.short_description = _('Période')
    get_periode_complete.admin_order_field = 'periode'
    
    def get_observations_preview(self, obj):
        """Aperçu des observations"""
        if obj.observations_periode:
            preview = obj.observations_periode[:50]
            if len(obj.observations_periode) > 50:
                preview += "..."
            return format_html('<span title="{}">{}</span>', obj.observations_periode, preview)
        return "-"
    
    get_observations_preview.short_description = _('Observations')
    
    def get_pourcentage_jour(self, obj):
        """Pourcentage par rapport au total de la journée"""
        if obj.inventaire.total_vehicules and obj.inventaire.total_vehicules > 0:
            pourcentage = (obj.nombre_vehicules / obj.inventaire.total_vehicules) * 100
            return format_html(
                '<span style="font-weight: bold; color: #0d6efd;">{:.1f}%</span>',
                pourcentage
            )
        return "0%"
    
    get_pourcentage_jour.short_description = _('% du jour')


# ===================================================================
# ADMIN RECETTE JOURNALIÈRE
# ===================================================================

@admin.register(RecetteJournaliere)
class RecetteJournaliereAdmin(admin.ModelAdmin):
    """
    Gestion des recettes journalières avec calculs de déperdition
    Interface critique pour les chefs de poste et administrateurs
    """
    
    list_display = (
        'date',
        'poste',
        'get_chef_poste',  # Changé de 'chef_saisie'
        'get_montant_formate',
        'get_taux_deperdition',
        'get_validation_badge',  # Changé de 'journee_badge'
        'get_actions_rapides'
    )
    
    list_display_links = ('date', 'poste')
    
    list_filter = (
        PeriodeFilter,
        PosteRegionFilter,
        TauxDeperditionFilter,
        'valide',  # Changé de 'journee_impertinente'
        'chef_poste__habilitation',  # Changé de 'chef_saisie__habilitation'
    )
    
    search_fields = (
        'poste__nom',
        'poste__code',
        'chef_poste__nom_complet',  # Changé de 'chef_saisie__nom_complet'
        'observations',
    )
    
    date_hierarchy = 'date'
    ordering = ('-date', 'poste__nom')
    list_per_page = 25
    
    fieldsets = (
        (_('Informations Principales'), {
            'fields': (
                'date',
                'poste',
                'chef_poste',        # Changé de 'chef_saisie'
                'montant_declare',   # Changé de 'montant'
            )
        }),
        (_('Calculs de Déperdition'), {
            'classes': ('collapse',),
            'fields': (
                ('recette_potentielle', 'ecart'),  # Changé de 'ecart_montant'
                'taux_deperdition',
                'inventaire_associe',  # Ajouté car c'est un champ du modèle
            )
        }),
        (_('Statut et Observations'), {
            'fields': (
                'verrouille',
                'valide',
                'observations',
            )
        }),
        (_('Informations Système'), {
            'classes': ('collapse',),
            'fields': (
                'date_saisie',      # Changé de 'date_creation'
                'date_modification',
            )
        }),
    )
    
    readonly_fields = (
        'recette_potentielle',
        'ecart',           # Changé de 'ecart_montant'
        'taux_deperdition',
        'date_saisie',     # Changé de 'date_creation'
        'date_modification',
    )
    
    def get_chef_poste(self, obj):
        """Affichage du chef de poste"""
        if obj.chef_poste:
            return obj.chef_poste.nom_complet
        return "Non assigné"
    
    get_chef_poste.short_description = _('Chef de Poste')
    get_chef_poste.admin_order_field = 'chef_poste'
    
    def get_montant_formate(self, obj):
        """Affichage formaté du montant"""
        return format_html(
            '<span style="color: #198754; font-weight: bold; font-size: 14px;">{:,.0f} FCFA</span>',
            obj.montant_declare
        )
    
    get_montant_formate.short_description = _('Montant Déclaré')
    get_montant_formate.admin_order_field = 'montant_declare'
    
    def get_taux_deperdition(self, obj):
        """Affichage coloré du taux de déperdition"""
        if obj.taux_deperdition is not None:
            # Couleur selon le niveau
            if obj.taux_deperdition >= 0 or obj.taux_deperdition > -10:
                color = '#28a745'  # Vert - bon
            elif obj.taux_deperdition <= -10 and obj.taux_deperdition >= -30:
                color = '#fd7e14'  # Orange - attention
            else:
                color = '#dc3545'  # Rouge - critique
            
            return format_html(
                '<span style="color: {}; font-weight: bold; font-size: 14px;">{:.1f}%</span>',
                color, obj.taux_deperdition
            )
        return format_html('<span style="color: #6c757d;">N/A</span>')
    
    get_taux_deperdition.short_description = _('Taux Déperdition')
    get_taux_deperdition.admin_order_field = 'taux_deperdition'
    
    def get_validation_badge(self, obj):
        """Badge pour statut de validation"""
        if obj.valide:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 3px 8px; '
                'border-radius: 8px; font-size: 11px; font-weight: bold;">'
                '<i class="fas fa-check"></i> Validé</span>'
            )
        elif obj.verrouille:
            return format_html(
                '<span style="background-color: #6c757d; color: white; padding: 3px 8px; '
                'border-radius: 8px; font-size: 11px;">'
                '<i class="fas fa-lock"></i> Verrouillé</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #ffc107; color: #000; padding: 3px 8px; '
                'border-radius: 8px; font-size: 11px;">'
                '<i class="fas fa-edit"></i> En cours</span>'
            )
    
    get_validation_badge.short_description = _('Statut')
    get_validation_badge.admin_order_field = 'valide'
    
    def get_actions_rapides(self, obj):
        """Actions rapides sur recettes"""
        actions = []
        
        # Bouton voir inventaire associé
        if obj.inventaire_associe:
            actions.append(
                f'<a href="/admin/inventaire/inventairejournalier/{obj.inventaire_associe.pk}/change/" '
                f'class="btn btn-sm btn-outline-primary" title="Voir inventaire">'
                f'<i class="fas fa-list"></i></a>'
            )
        else:
            # Chercher un inventaire pour la même date et poste
            try:
                inventaire = InventaireJournalier.objects.get(date=obj.date, poste=obj.poste)
                actions.append(
                    f'<a href="/admin/inventaire/inventairejournalier/{inventaire.pk}/change/" '
                    f'class="btn btn-sm btn-outline-primary" title="Voir inventaire">'
                    f'<i class="fas fa-list"></i></a>'
                )
            except InventaireJournalier.DoesNotExist:
                actions.append(
                    f'<span class="btn btn-sm btn-outline-secondary" title="Pas d\'inventaire">'
                    f'<i class="fas fa-minus"></i></span>'
                )
        
        # Indicateur niveau déperdition
        if obj.taux_deperdition is not None:
            if obj.taux_deperdition < -30:
                actions.append(
                    f'<span class="btn btn-sm btn-outline-danger" title="Déperdition critique">'
                    f'<i class="fas fa-exclamation-triangle"></i></span>'
                )
        
        return format_html(' '.join(actions))
    
    get_actions_rapides.short_description = _('Actions')


# ===================================================================
# ADMIN STATISTIQUES PÉRIODIQUES
# ===================================================================

@admin.register(StatistiquesPeriodiques)
class StatistiquesPeriodiquesAdmin(admin.ModelAdmin):
    """
    Consultation des statistiques consolidées
    Interface pour analyses et rapports
    """
    
    list_display = (
        'date_debut',
        'date_fin',
        'get_type_badge',
        'poste',
        'get_total_recettes',
        'get_taux_moyen',
        'get_jours_actifs'
    )
    
    list_filter = (
        'type_periode',
        'poste__region',
        'poste__type',
        'date_debut',
    )
    
    search_fields = (
        'poste__nom',
        'poste__code',
    )
    
    ordering = ('-date_debut', 'poste__nom')  # Changé de 'periode_debut'
    list_per_page = 30
    
    # Interface en lecture seule
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.habilitation == 'admin_principal'
    
    fieldsets = (
        (_('Période et Poste'), {
            'fields': (
                ('date_debut', 'date_fin'),  # Changé de 'periode_debut' et 'periode_fin'
                'type_periode',
                'poste',
            )
        }),
        (_('Statistiques Financières'), {
            'fields': (
                ('total_recettes_declarees', 'total_recettes_potentielles'),
                'taux_deperdition_moyen',  # Retiré 'ecart_total' car pas dans le modèle
            )
        }),
        (_('Statistiques d\'Activité'), {
            'fields': (
                'nombre_jours_actifs',     # Changé de 'jours_avec_donnees'
                'nombre_jours_impertinents',  # Nouveau champ ajouté
            )
        }),
        (_('Informations Système'), {
            'classes': ('collapse',),
            'fields': (
                'date_calcul',
            )
        }),
    )
    
    readonly_fields = (
        'date_debut', 'date_fin', 'type_periode', 'poste',
        'total_recettes_declarees', 'total_recettes_potentielles',
        'taux_deperdition_moyen', 'nombre_jours_actifs',
        'nombre_jours_impertinents', 'date_calcul'
    )
    
    def get_type_badge(self, obj):
        """Badge coloré pour le type de période"""
        color_map = {
            'hebdomadaire': '#17a2b8',
            'mensuelle': '#6f42c1',
            'trimestrielle': '#fd7e14',
            'annuelle': '#dc3545',
        }
        
        color = color_map.get(obj.type_periode, '#6c757d')
        
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 8px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_type_periode_display()
        )
    
    get_type_badge.short_description = _('Type')
    get_type_badge.admin_order_field = 'type_periode'
    
    def get_total_recettes(self, obj):
        """Affichage formaté du total des recettes"""
        return format_html(
            '<span style="color: #198754; font-weight: bold;">{:,.0f} FCFA</span>',
            obj.total_recettes_declarees or 0
        )
    
    get_total_recettes.short_description = _('Total Recettes')
    get_total_recettes.admin_order_field = 'total_recettes_declarees'
    
    def get_taux_moyen(self, obj):
        """Affichage coloré du taux moyen"""
        if obj.taux_deperdition_moyen is not None:
            # Couleur selon le niveau
            if obj.taux_deperdition_moyen >= -10:
                color = '#28a745'
            elif obj.taux_deperdition_moyen >= -30:
                color = '#fd7e14'
            else:
                color = '#dc3545'
            
            return format_html(
                '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
                color, obj.taux_deperdition_moyen
            )
        return "N/A"
    
    get_taux_moyen.short_description = _('Taux Moyen')
    get_taux_moyen.admin_order_field = 'taux_deperdition_moyen'
    
    def get_jours_actifs(self, obj):
        """Nombre de jours avec données"""
        return format_html(
            '<span style="color: #0d6efd; font-weight: bold;">{}</span>',
            obj.nombre_jours_actifs or 0
        )
    
    get_jours_actifs.short_description = _('Jours Actifs')
    get_jours_actifs.admin_order_field = 'nombre_jours_actifs'


# ===================================================================
# PERSONNALISATION INTERFACE ADMIN INVENTAIRE
# ===================================================================

# Messages personnalisés
admin.site.site_header = "Administration SUPPER - Module Inventaire"
admin.site.index_title = "Gestion des Inventaires et Recettes"