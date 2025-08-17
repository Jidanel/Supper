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
from django.shortcuts import  redirect
from .models import *
import csv
from django.urls import path
from .widgets import InventaireMensuelForm
import json
from .widgets import CalendrierJoursWidget
from .forms import RecetteJournaliereAdminForm, ConfigurationJourForm

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
    # 🔧 AJOUTER le formulaire personnalisé
    form = ConfigurationJourForm
    
    list_display = [
        'date', 'poste_display', 'statut', 'permet_saisie_inventaire', 
        'permet_saisie_recette', 'get_config_summary', 'cree_par'
    ]
    
    list_filter = [
        'statut', 'permet_saisie_inventaire', 'permet_saisie_recette', 
        'poste__region', 'poste__type', 'date'
    ]
    
    search_fields = ['date', 'poste__nom', 'poste__code', 'commentaire']
    date_hierarchy = 'date'
    
    fieldsets = [
        ('Configuration de base', {
            'fields': ['date', 'poste', 'statut'],
            'description': 'Configuration principale du jour. Laisser le poste vide pour une configuration globale.'
        }),
        ('Permissions de saisie', {
            'fields': ['permet_saisie_inventaire', 'permet_saisie_recette'],
            'description': 'Contrôle quels types de saisie sont autorisés pour ce jour.'
        }),
        ('Informations complémentaires', {
            'fields': ['commentaire', 'cree_par'],
            'classes': ['collapse'],
            'description': 'Informations additionnelles et traçabilité.'
        })
    ]

    def poste_display(self, obj):
        """Affichage amélioré du poste"""
        if obj.poste:
            return format_html(
                '<strong>{}</strong><br><small style="color: #666;">{}</small>',
                obj.poste.nom,
                obj.poste.get_type_display()
            )
        return format_html('<em style="color: #007cba;">Configuration globale</em>')
    poste_display.short_description = 'Poste'
    
    def get_config_summary(self, obj):
        """Résumé de la configuration"""
        return obj.get_config_summary()
    get_config_summary.short_description = 'Résumé configuration'
    
    
    def get_form(self, request, obj=None, **kwargs):
        """Personnalise le formulaire"""
        form = super().get_form(request, obj, **kwargs)
        
        # 🔧 CORRECTION : Méthode plus simple pour passer l'utilisateur
        def form_wrapper(*args, **form_kwargs):
            form_kwargs['user'] = request.user
            return form(*args, **form_kwargs)
        
        return form_wrapper
    
    # Actions en lot améliorées
    actions = [
        'ouvrir_jours_selectionnes', 'fermer_jours_selectionnes', 
        'dupliquer_configuration', 'ouvrir_semaine_complete'
    ]
    
    def ouvrir_jours_selectionnes(self, request, queryset):
        """Ouvre les jours sélectionnés pour toutes les saisies"""
        updated = queryset.update(
            statut='ouvert',
            permet_saisie_inventaire=True,
            permet_saisie_recette=True
        )
        self.message_user(
            request, 
            f'{updated} jour(s) ouvert(s) avec succès pour inventaires et recettes.'
        )
    ouvrir_jours_selectionnes.short_description = "Ouvrir pour toutes les saisies"
    
    def fermer_jours_selectionnes(self, request, queryset):
        """Ferme les jours sélectionnés"""
        updated = queryset.update(
            statut='ferme',
            permet_saisie_inventaire=False,
            permet_saisie_recette=False
        )
        self.message_user(
            request,
            f'{updated} jour(s) fermé(s) avec succès.'
        )
    fermer_jours_selectionnes.short_description = "Fermer les jours sélectionnés"
    
    def dupliquer_configuration(self, request, queryset):
        """Duplique la configuration pour d'autres postes"""
        if queryset.count() != 1:
            self.message_user(
                request,
                "Sélectionnez exactement une configuration à dupliquer.",
                level='ERROR'
            )
            return
        
        config_originale = queryset.first()
        
        # Dupliquer pour tous les postes (configuration globale -> spécifique)
        if not config_originale.poste:
            from accounts.models import Poste
            postes = Poste.objects.filter(actif=True)
            created = 0
            
            for poste in postes:
                if not ConfigurationJour.objects.filter(
                    date=config_originale.date, poste=poste
                ).exists():
                    ConfigurationJour.objects.create(
                        date=config_originale.date,
                        poste=poste,
                        statut=config_originale.statut,
                        permet_saisie_inventaire=config_originale.permet_saisie_inventaire,
                        permet_saisie_recette=config_originale.permet_saisie_recette,
                        cree_par=request.user,
                        commentaire=f"Dupliqué depuis configuration globale"
                    )
                    created += 1
            
            self.message_user(
                request,
                f'Configuration dupliquée pour {created} poste(s).'
            )
    dupliquer_configuration.short_description = "Dupliquer la configuration"
    
    def ouvrir_semaine_complete(self, request, queryset):
        """Ouvre une semaine complète basée sur les jours sélectionnés"""
        from datetime import timedelta
        
        dates_selectionnees = queryset.values_list('date', flat=True)
        if not dates_selectionnees:
            return
        
        created = 0
        for date_base in dates_selectionnees:
            # Ouvrir 7 jours à partir de cette date
            for i in range(7):
                date_semaine = date_base + timedelta(days=i)
                
                config, created_config = ConfigurationJour.objects.get_or_create(
                    date=date_semaine,
                    poste=None,  # Configuration globale
                    defaults={
                        'statut': 'ouvert',
                        'permet_saisie_inventaire': True,
                        'permet_saisie_recette': True,
                        'cree_par': request.user,
                        'commentaire': f'Semaine ouverte automatiquement'
                    }
                )
                
                if created_config:
                    created += 1
        
        self.message_user(
            request,
            f'{created} jour(s) supplémentaire(s) ouvert(s) pour compléter les semaines.'
        )
    ouvrir_semaine_complete.short_description = "Ouvrir semaines complètes"


    
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
        if not change:  # Nouveau objet
            obj.cree_par = request.user
        super().save_model(request, obj, form, change)
    
    
    
    
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
    # 🔧 AJOUTER cette ligne pour utiliser le formulaire personnalisé
    form = RecetteJournaliereAdminForm
    
    list_display = [
        'poste', 'date', 'montant_declare_formatted', 'recette_potentielle_formatted', 
        'taux_deperdition_colored', 'get_couleur_alerte_display', 'chef_poste', 'verrouille'
    ]
    
    list_filter = [
        'poste__region', 'poste', 'date', 'verrouille', 'valide', 
        'chef_poste__habilitation'
    ]
    
    search_fields = [
        'poste__nom', 'poste__code', 'chef_poste__nom_complet', 
        'chef_poste__username'
    ]
    
    date_hierarchy = 'date'
    
    readonly_fields = [
        'recette_potentielle', 'ecart', 'taux_deperdition', 
        'date_saisie', 'date_modification', 'get_status_jour'
    ]
    
    fieldsets = [
        ('Informations principales', {
            'fields': [
                'poste', 'date', 'get_status_jour', 'chef_poste', 'montant_declare'
            ]
        }),
        ('Calculs automatiques', {
            'fields': [
                'inventaire_associe', 'recette_potentielle', 'ecart', 'taux_deperdition'
            ],
            'classes': ['collapse']
        }),
        ('État et validation', {
            'fields': [
                'verrouille', 'valide'
            ]
        }),
        ('Informations complémentaires', {
            'fields': [
                'observations', 'date_saisie', 'date_modification'
            ],
            'classes': ['collapse']
        })
    ]
    
    # 🔧 NOUVELLE MÉTHODE : Afficher le statut du jour
    def get_status_jour(self, obj):
        """Affiche le statut du jour pour cette recette"""
        if obj.date and obj.poste:
            from .models import ConfigurationJour
            
            inventaire_ouvert = ConfigurationJour.est_jour_ouvert_pour_inventaire(obj.date, obj.poste)
            recette_ouvert = ConfigurationJour.est_jour_ouvert_pour_recette(obj.date, obj.poste)
            
            status = []
            if inventaire_ouvert:
                status.append('<span style="color: green;">✓ Inventaire</span>')
            else:
                status.append('<span style="color: red;">✗ Inventaire</span>')
                
            if recette_ouvert:
                status.append('<span style="color: green;">✓ Recette</span>')
            else:
                status.append('<span style="color: red;">✗ Recette</span>')
            
            return format_html(' | '.join(status))
        return '-'
    get_status_jour.short_description = 'Statut du jour'
    
    def montant_declare_formatted(self, obj):
        """Affichage formaté du montant déclaré"""
        if obj.montant_declare is not None:
            try:
                # Conversion sécurisée en float puis formatage
                montant = float(obj.montant_declare)
                return format_html(
                    '<strong>{:,.0f} FCFA</strong>',
                    montant
                )
            except (ValueError, TypeError):
                return str(obj.montant_declare)
        return '-'
    montant_declare_formatted.short_description = 'Montant déclaré'
    montant_declare_formatted.admin_order_field = 'montant_declare'

    def recette_potentielle_formatted(self, obj):
        """Affichage formaté de la recette potentielle"""
        if obj.recette_potentielle is not None:
            try:
                montant = float(obj.recette_potentielle)
                return format_html(
                    '{:,.0f} FCFA',
                    montant
                )
            except (ValueError, TypeError):
                return str(obj.recette_potentielle)
        return '-'
    recette_potentielle_formatted.short_description = 'Recette potentielle'
    recette_potentielle_formatted.admin_order_field = 'recette_potentielle'
    
    def taux_deperdition_colored(self, obj):
        """Affichage formaté du taux de déperdition"""
        if obj.taux_deperdition is not None:
            try:
                taux = float(obj.taux_deperdition)
                couleur = obj.get_couleur_alerte()
                
                # Mapping couleurs bootstrap vers couleurs CSS
                color_map = {
                    'success': '#28a745',
                    'warning': '#ffc107', 
                    'danger': '#dc3545',
                    'secondary': '#6c757d'
                }
                
                return format_html(
                    '<span style="color: {}; font-weight: bold;">{:.2f}%</span>',
                    color_map.get(couleur, '#000000'),
                    taux
                )
            except (ValueError, TypeError):
                return str(obj.taux_deperdition)
        return '-'
    taux_deperdition_colored.short_description = 'Taux déperdition'
    taux_deperdition_colored.admin_order_field = 'taux_deperdition'
    
    def status_recette(self, obj):
        """Statut de la recette"""
        if obj.valide:
            return format_html('<span class="badge bg-success">✓ Validée</span>')
        elif obj.verrouille:
            return format_html('<span class="badge bg-warning">🔒 Verrouillée</span>')
        else:
            return format_html('<span class="badge bg-info">📝 En cours</span>')
    status_recette.short_description = 'Statut'

    def get_couleur_alerte_display(self, obj):
        """Affichage de l'alerte couleur"""
        couleur = obj.get_couleur_alerte()
        
        # Labels et couleurs
        labels = {
            'success': ('✓ Normal', '#28a745'),
            'warning': ('⚠ Attention', '#ffc107'),
            'danger': ('✗ Critique', '#dc3545'),
            'secondary': ('? Inconnu', '#6c757d')
        }
        
        label, color = labels.get(couleur, ('?', '#000000'))
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            label
        )
    get_couleur_alerte_display.short_description = 'Alerte'
    
    # Actions personnalisées
    actions = ['recalculer_indicateurs', 'verrouiller_recettes', 'exporter_csv']
    
    def get_queryset(self, request):
        """Optimiser les requêtes"""
        return super().get_queryset(request).select_related(
            'poste', 'chef_poste', 'inventaire_associe'
        )
    
    actions = ['recalculer_indicateurs', 'verrouiller_recettes', 'export_recettes']
    
    def recalculer_indicateurs(self, request, queryset):
        """Recalcule les indicateurs pour les recettes sélectionnées"""
        updated = 0
        for recette in queryset:
            recette.calculer_indicateurs()
            recette.save()
            updated += 1
        
        self.message_user(
            request, 
            f'{updated} recette(s) recalculée(s) avec succès.'
        )
    recalculer_indicateurs.short_description = "Recalculer les indicateurs"
    
    def verrouiller_recettes(self, request, queryset):
        """Verrouille les recettes sélectionnées"""
        updated = queryset.update(verrouille=True)
        self.message_user(
            request,
            f'{updated} recette(s) verrouillée(s) avec succès.'
        )
    verrouiller_recettes.short_description = "Verrouiller les recettes"
    
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

    def exporter_csv(self, request, queryset):
        """Exporte les recettes en CSV"""
        import csv
        from django.http import HttpResponse
        from django.utils import timezone
        
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="recettes_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        # BOM UTF-8 pour Excel
        response.write('\ufeff')
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Poste', 'Date', 'Montant déclaré', 'Recette potentielle', 
            'Écart', 'Taux déperdition', 'Chef de poste', 'Verrouillé'
        ])
        
        for recette in queryset:
            writer.writerow([
                recette.poste.nom,
                recette.date.strftime('%d/%m/%Y'),
                float(recette.montant_declare) if recette.montant_declare else 0,
                float(recette.recette_potentielle) if recette.recette_potentielle else 0,
                float(recette.ecart) if recette.ecart else 0,
                float(recette.taux_deperdition) if recette.taux_deperdition else 0,
                recette.chef_poste.nom_complet if recette.chef_poste else '',
                'Oui' if recette.verrouille else 'Non'
            ])
        
        return response
    exporter_csv.short_description = "Exporter en CSV"

    def get_form(self, request, obj=None, **kwargs):
        """Personnalise le formulaire selon l'utilisateur"""
        form = super().get_form(request, obj, **kwargs)
        
        # Limiter les postes selon les permissions de l'utilisateur
        if hasattr(request.user, 'get_postes_accessibles'):
            postes_accessibles = request.user.get_postes_accessibles()
            if 'poste' in form.base_fields:
                form.base_fields['poste'].queryset = postes_accessibles
        
        # Définir l'utilisateur connecté comme chef de poste par défaut
        if not obj and 'chef_poste' in form.base_fields:
            form.base_fields['chef_poste'].initial = request.user

        
        return form
    
    def save_model(self, request, obj, form, change):
        """Sauvegarde personnalisée avec gestion d'erreurs"""
        try:
            if not change:  # Nouvel objet
                if not obj.chef_poste:
                    obj.chef_poste = request.user
            
            # Calculer automatiquement les indicateurs
            obj.save()
            obj.calculer_indicateurs()
            obj.save()
            
            # Message de succès avec détails
            self.message_user(
                request,
                f'Recette sauvegardée avec succès. '
                f'Taux de déperdition: {obj.taux_deperdition:.2f}% '
                f'({obj.get_couleur_alerte().title()})'
            )
            
        except Exception as e:
            self.message_user(
                request,
                f'Erreur lors de la sauvegarde: {str(e)}',
                level='ERROR'
            )
            raise



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


@admin.register(InventaireMensuel)
class InventaireMensuelAdmin(admin.ModelAdmin):
    """
    Administration des inventaires mensuels avec widget calendrier
    """
    
    # 🔧 CORRECTION : Pas de form personnalisé pour éviter les conflits
    # form = InventaireMensuelForm  # COMMENTÉ TEMPORAIREMENT
    
    list_display = [
        'titre', 'mois_annee', 'nombre_jours_actifs', 
        'actif', 'actions_admin', 'date_creation'
    ]
    
    list_filter = ['actif', 'annee', 'mois', 'date_creation']
    search_fields = ['titre', 'description']
    readonly_fields = ['date_creation', 'date_modification', 'cree_par']
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('titre', 'mois', 'annee', 'description')
        }),
        ('Configuration des Jours', {
            'fields': ('jours_actifs',),
            'description': 'Sélectionnez les jours du mois où la saisie d\'inventaire sera autorisée'
        }),
        ('État', {
            'fields': ('actif',)
        }),
        ('Métadonnées', {
            'fields': ('cree_par', 'date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )
    
    # 🔧 CORRECTION : Supprimer get_form pour utiliser le form par défaut
    # def get_form(self, request, obj=None, **kwargs):
    #     return super().get_form(request, obj, **kwargs)
    
    def mois_annee(self, obj):
        """Affiche mois et année formatés"""
        try:
            return f"{obj.get_mois_display()} {obj.annee}"
        except Exception as e:
            return f"Erreur: {str(e)}"
    mois_annee.short_description = "Période"
    
    def nombre_jours_actifs(self, obj):
        """Affiche le nombre de jours actifs avec style"""
        try:
            if obj.jours_actifs and isinstance(obj.jours_actifs, list):
                count = len(obj.jours_actifs)
            else:
                count = 0
                
            if count > 0:
                return format_html(
                    '<span style="color: green; font-weight: bold; background: #d4edda; '
                    'padding: 3px 8px; border-radius: 12px;">{} jours</span>',
                    count
                )
            return format_html(
                '<span style="color: red; background: #f8d7da; '
                'padding: 3px 8px; border-radius: 12px;">Aucun jour</span>'
            )
        except Exception as e:
            return format_html(
                '<span style="color: orange; background: #fff3cd; '
                'padding: 3px 8px; border-radius: 12px;">Erreur: {}</span>',
                str(e)
            )
    nombre_jours_actifs.short_description = "Jours actifs"
    
    def actions_admin(self, obj):
        """Boutons d'actions rapides"""
        if obj.pk:
            buttons = []
            
            # Bouton générer configurations
            buttons.append(format_html(
                '<a href="{}" class="button" style="background: #28a745; color: white; '
                'padding: 5px 10px; text-decoration: none; border-radius: 3px; margin-right: 5px;">'
                '🔧 Générer Configs</a>',
                reverse('admin:inventaire_inventairemensuel_generer_config', args=[obj.pk])
            ))
            
            return format_html(''.join(buttons))
        return "Sauvegardez d'abord"
    actions_admin.short_description = "Actions"
    
    def save_model(self, request, obj, form, change):
        """Surcharge avec gestion d'erreurs simplifiée"""
        try:
            if not change:  # Création
                obj.cree_par = request.user
            
            # 🔧 CORRECTION : Validation simple des jours_actifs
            if hasattr(obj, 'jours_actifs') and obj.jours_actifs:
                if isinstance(obj.jours_actifs, str):
                    try:
                        import json
                        obj.jours_actifs = json.loads(obj.jours_actifs)
                    except (json.JSONDecodeError, ValueError):
                        obj.jours_actifs = []
                
                # S'assurer que c'est une liste
                if not isinstance(obj.jours_actifs, list):
                    obj.jours_actifs = []
            else:
                obj.jours_actifs = []
            
            # Validation de l'unicité
            existing = InventaireMensuel.objects.filter(
                mois=obj.mois, 
                annee=obj.annee
            ).exclude(pk=obj.pk if obj.pk else 0)
            
            if existing.exists():
                self.message_user(
                    request,
                    f"Un inventaire existe déjà pour {obj.get_mois_display()} {obj.annee}",
                    level='ERROR'
                )
                return
            
            super().save_model(request, obj, form, change)
            
            # Message de succès
            jours_count = len(obj.jours_actifs) if obj.jours_actifs else 0
            self.message_user(
                request,
                f"Inventaire '{obj.titre}' sauvegardé avec succès ! "
                f"({jours_count} jours sélectionnés)",
                level='SUCCESS'
            )
            
        except Exception as e:
            self.message_user(
                request,
                f"Erreur lors de la sauvegarde: {str(e)}",
                level='ERROR'
            )
            # Déboguer l'erreur
            import traceback
            print(f"ERREUR SAUVEGARDE: {traceback.format_exc()}")
    
    def get_urls(self):
        """Ajouter des URLs personnalisées"""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:object_id>/generer_config/',
                self.admin_site.admin_view(self.generer_config_view),
                name='inventaire_inventairemensuel_generer_config'
            ),
        ]
        return custom_urls + urls
    
    def generer_config_view(self, request, object_id):
        """Action pour générer automatiquement les configurations de jours"""
        try:
            inventaire = InventaireMensuel.objects.get(pk=object_id)
            configs_creees = inventaire.generer_configurations_jours()
            
            self.message_user(
                request,
                f"Configuration automatique réussie ! "
                f"{len(configs_creees)} jours configurés pour {inventaire.titre}",
                level='SUCCESS'
            )
            
        except InventaireMensuel.DoesNotExist:
            self.message_user(request, "Inventaire mensuel introuvable", level='ERROR')
        except Exception as e:
            self.message_user(request, f"Erreur: {str(e)}", level='ERROR')
        
        return redirect('admin:inventaire_inventairemensuel_change', object_id)
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Personnaliser les widgets des champs"""
        if db_field.name == 'jours_actifs':
            kwargs['widget'] = CalendrierJoursWidget()
        return super().formfield_for_dbfield(db_field, request, **kwargs)

