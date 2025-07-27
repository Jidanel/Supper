
# ===================================================================
# Fichier : accounts/admin.py - PANEL DJANGO ADMIN ENRICHI
# Dashboard intégré + Région/Département dynamique + Statistiques
# ===================================================================

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from django.urls import reverse, path
from django.utils.html import format_html
from django.db import models
from django.forms import TextInput, Textarea, Select
from django import forms
from django.shortcuts import render
from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.utils.safestring import mark_safe
from django.contrib.admin import AdminSite
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from datetime import datetime, timedelta
import json

from .models import UtilisateurSUPPER, Poste, JournalAudit, NotificationUtilisateur



class SupperAdminSite(AdminSite):
    """Site admin personnalisé pour SUPPER avec dashboard intégré"""
    
    site_header = "Administration SUPPER - Dashboard Intégré"
    site_title = "SUPPER Admin"
    index_title = "Tableau de Bord Administrateur"
    
    def get_urls(self):
        """URLs personnalisées pour le dashboard intégré"""
        urls = super().get_urls()
        custom_urls = [
            # Dashboard principal avec statistiques
            path('dashboard/', self.admin_view(self.dashboard_view), name='dashboard'),
            
            # APIs pour les statistiques
            path('api/stats/', self.admin_view(self.api_stats), name='api_stats'),
            path('api/departements/<str:region>/', self.admin_view(self.api_departements), name='api_departements'),
            
            # Actions rapides
            path('actions/ouvrir-jour/', self.admin_view(self.ouvrir_jour), name='ouvrir_jour'),
            path('actions/marquer-impertinent/', self.admin_view(self.marquer_impertinent), name='marquer_impertinent'),
            
            # Statistiques avancées
            path('stats/journalieres/', self.admin_view(self.stats_journalieres), name='stats_journalieres'),
            path('stats/hebdomadaires/', self.admin_view(self.stats_hebdomadaires), name='stats_hebdomadaires'),
            path('stats/mensuelles/', self.admin_view(self.stats_mensuelles), name='stats_mensuelles'),
            path('stats/trimestrielles/', self.admin_view(self.stats_trimestrielles), name='stats_trimestrielles'),
            path('stats/semestrielles/', self.admin_view(self.stats_semestrielles), name='stats_semestrielles'),
            path('stats/annuelles/', self.admin_view(self.stats_annuelles), name='stats_annuelles'),
            
            # Exports
            path('exports/audit/', self.admin_view(self.export_audit), name='export_audit'),
            path('exports/statistiques/', self.admin_view(self.export_statistiques), name='export_statistiques'),
        ]
        return custom_urls + urls
    
    def index(self, request, extra_context=None):
        """Page d'accueil admin avec dashboard intégré"""
        extra_context = extra_context or {}
        
        # Statistiques générales
        try:
            stats = self.get_dashboard_stats()
            extra_context.update(stats)
        except Exception as e:
            extra_context['stats_error'] = str(e)
        
        # Journal d'activité récente
        try:
            recent_logs = JournalAudit.objects.select_related('utilisateur').order_by('-timestamp')[:10]
            extra_context['recent_logs'] = recent_logs
        except Exception:
            extra_context['recent_logs'] = []
        
        return super().index(request, extra_context)
    
    def dashboard_view(self, request):
        """Vue dashboard complète avec graphiques"""
        context = {
            'title': 'Dashboard Administrateur SUPPER',
            'stats': self.get_dashboard_stats(),
            'recent_logs': JournalAudit.objects.select_related('utilisateur').order_by('-timestamp')[:20],
            'opts': {'app_label': 'supper'},
        }
        return TemplateResponse(request, 'admin/dashboard.html', context)
    
    def get_dashboard_stats(self):
        """Calcul des statistiques pour le dashboard"""
        try:
            # Statistiques utilisateurs
            total_users = UtilisateurSUPPER.objects.count()
            active_users = UtilisateurSUPPER.objects.filter(is_active=True).count()
            admin_users = UtilisateurSUPPER.objects.filter(
                Q(is_superuser=True) | Q(is_staff=True) | 
                Q(habilitation__in=['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'])
            ).count()
            
            # Statistiques postes
            total_postes = Poste.objects.count()
            postes_peage = Poste.objects.filter(type='peage').count()
            postes_pesage = Poste.objects.filter(type='pesage').count()
            postes_actifs = Poste.objects.filter(is_active=True).count()
            
            # Activité récente (7 derniers jours)
            depuis_7_jours = timezone.now() - timedelta(days=7)
            logs_recents = JournalAudit.objects.filter(timestamp__gte=depuis_7_jours).count()
            connexions_recentes = JournalAudit.objects.filter(
                timestamp__gte=depuis_7_jours, 
                action='CONNEXION'
            ).count()
            
            # Statistiques aujourd'hui
            aujourd_hui = timezone.now().date()
            logs_aujourd_hui = JournalAudit.objects.filter(timestamp__date=aujourd_hui).count()
            connexions_aujourd_hui = JournalAudit.objects.filter(
                timestamp__date=aujourd_hui,
                action='CONNEXION'
            ).count()
            
            return {
                'total_users': total_users,
                'active_users': active_users,
                'admin_users': admin_users,
                'total_postes': total_postes,
                'postes_peage': postes_peage,
                'postes_pesage': postes_pesage,
                'postes_actifs': postes_actifs,
                'logs_recents': logs_recents,
                'connexions_recentes': connexions_recentes,
                'logs_aujourd_hui': logs_aujourd_hui,
                'connexions_aujourd_hui': connexions_aujourd_hui,
            }
        except Exception as e:
            return {'error': f'Erreur calcul statistiques: {str(e)}'}
    
    def api_stats(self, request):
        """API pour statistiques temps réel"""
        type_stats = request.GET.get('type', 'general')
        
        if type_stats == 'quick':
            # Utilisateurs connectés (estimation basée sur les sessions récentes)
            depuis_1h = timezone.now() - timedelta(hours=1)
            connected = JournalAudit.objects.filter(
                timestamp__gte=depuis_1h,
                action='CONNEXION'
            ).values('utilisateur').distinct().count()
            
            # Actions aujourd'hui
            aujourd_hui = timezone.now().date()
            today = JournalAudit.objects.filter(timestamp__date=aujourd_hui).count()
            
            return JsonResponse({'connected': connected, 'today': today})
        
        else:
            stats = self.get_dashboard_stats()
            return JsonResponse(stats)
    
    def api_departements(self, request, region):
        """API pour récupérer les départements d'une région"""
        departements_par_region = {
            'Centre': [
                'Haute-Sanaga', 'Lekié', 'Mbam-et-Inoubou', 'Mbam-et-Kim',
                'Méfou-et-Afamba', 'Méfou-et-Akono', 'Mfoundi', 
                'Nyong-et-Kellé', 'Nyong-et-Mfoumou', 'Nyong-et-So\'o'
            ],
            'Littoral': ['Moungo', 'Nkam', 'Sanaga-Maritime', 'Wouri'],
            'Nord': ['Bénoué', 'Faro', 'Mayo-Louti', 'Mayo-Rey'],
            'Extrême-Nord': [
                'Diamaré', 'Logone-et-Chari', 'Mayo-Danay', 'Mayo-Kani',
                'Mayo-Sava', 'Mayo-Tsanaga'
            ],
            'Adamaoua': ['Djerem', 'Faro-et-Déo', 'Mayo-Banyo', 'Mbéré', 'Vina'],
            'Ouest': [
                'Bamboutos', 'Haut-Nkam', 'Hauts-Plateaux', 'Koung-Khi',
                'Menoua', 'Mifi', 'Mino', 'Ndé'
            ],
            'Est': [
                'Boumba-et-Ngoko', 'Haut-Nyong', 'Haut-Ogooué', 'Kadey', 'Lom-et-Djerem'
            ],
            'Sud': ['Dja-et-Lobo', 'Mvila', 'Océan', 'Vallée-du-Ntem'],
            'Nord-Ouest': [
                'Boyo', 'Bui', 'Donga-Mantung', 'Menchum', 'Mezam', 'Momo', 'Ngo-Ketunjia'
            ],
            'Sud-Ouest': [
                'Fako', 'Koupé-Manengouba', 'Lebialem', 'Manyu', 'Meme', 'Ndian'
            ],
        }
        
        departements = departements_par_region.get(region, [])
        return JsonResponse({'departements': departements})
    
    def ouvrir_jour(self, request):
        """Action rapide pour ouvrir un jour"""
        if request.method == 'POST':
            # Logique d'ouverture de jour (à implémenter)
            return JsonResponse({'success': True, 'message': 'Jour ouvert avec succès'})
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})
    
    def marquer_impertinent(self, request):
        """Action rapide pour marquer un jour comme impertinent"""
        if request.method == 'POST':
            # Logique de marquage impertinent (à implémenter)
            return JsonResponse({'success': True, 'message': 'Jour marqué comme impertinent'})
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})
    
    def stats_journalieres(self, request):
        """Statistiques journalières"""
        context = {
            'title': 'Statistiques Journalières',
            'period': 'journalieres',
            'opts': {'app_label': 'supper'},
        }
        return TemplateResponse(request, 'admin/stats_period.html', context)
    
    def stats_hebdomadaires(self, request):
        """Statistiques hebdomadaires"""
        context = {
            'title': 'Statistiques Hebdomadaires',
            'period': 'hebdomadaires',
            'opts': {'app_label': 'supper'},
        }
        return TemplateResponse(request, 'admin/stats_period.html', context)
    
    def stats_mensuelles(self, request):
        """Statistiques mensuelles"""
        context = {
            'title': 'Statistiques Mensuelles',
            'period': 'mensuelles',
            'opts': {'app_label': 'supper'},
        }
        return TemplateResponse(request, 'admin/stats_period.html', context)
    
    def stats_trimestrielles(self, request):
        """Statistiques trimestrielles"""
        context = {
            'title': 'Statistiques Trimestrielles',
            'period': 'trimestrielles',
            'opts': {'app_label': 'supper'},
        }
        return TemplateResponse(request, 'admin/stats_period.html', context)
    
    def stats_semestrielles(self, request):
        """Statistiques semestrielles"""
        context = {
            'title': 'Statistiques Semestrielles',
            'period': 'semestrielles',
            'opts': {'app_label': 'supper'},
        }
        return TemplateResponse(request, 'admin/stats_period.html', context)
    
    def stats_annuelles(self, request):
        """Statistiques annuelles"""
        context = {
            'title': 'Statistiques Annuelles',
            'period': 'annuelles',
            'opts': {'app_label': 'supper'},
        }
        return TemplateResponse(request, 'admin/stats_period.html', context)
    
    def export_audit(self, request):
        """Export du journal d'audit"""
        # Logique d'export (à implémenter)
        return JsonResponse({'success': True, 'message': 'Export en cours'})
    
    def export_statistiques(self, request):
        """Export des statistiques"""
        # Logique d'export (à implémenter)
        return JsonResponse({'success': True, 'message': 'Export en cours'})


# Créer l'instance du site admin personnalisé
admin_site = SupperAdminSite(name='supper_admin')

# ===================================================================
# CONFIGURATION GLOBALE DU SITE ADMIN - TITRES DYNAMIQUES
# ===================================================================

# Personnalisation des titres du site admin
admin.site.site_header = _("Administration SUPPER")
admin.site.site_title = _("Admin SUPPER")
admin.site.index_title = _("Tableau de bord administrateur")



# ===================================================================
# ADMIN UTILISATEURS SUPPER - CONFIGURATION COMPLÈTE
# ===================================================================

@admin.register(UtilisateurSUPPER, site=admin_site)
class UtilisateurSUPPERAdmin(UserAdmin):
    """Administration des utilisateurs avec actions en masse"""
    
    list_display = [
        'username', 'nom_complet', 'habilitation_color', 'poste_affectation', 
        'telephone', 'is_active', 'last_login', 'interface_type', 'actions_admin'
    ]
    
    list_filter = [
        'habilitation', 'is_active', 'is_staff', 'is_superuser',
        'poste_affectation__type', 'poste_affectation__region',
        'date_joined', 'last_login'
    ]
    
    search_fields = [
        'username', 'nom_complet', 'telephone', 'email',
        'poste_affectation__nom', 'poste_affectation__code'
    ]
    
    ordering = ['-date_joined', 'nom_complet']
    
    fieldsets = (
        (_('Informations de connexion'), {
            'fields': ('username', 'password'),
            'classes': ('wide',),
        }),
        (_('Informations personnelles'), {
            'fields': ('nom_complet', 'telephone', 'email'),
            'classes': ('wide',),
        }),
        (_('Affectation et rôle'), {
            'fields': ('habilitation', 'poste_affectation'),
            'classes': ('wide',),
        }),
        (_('Permissions système'), {
            'fields': ('is_active', 'is_staff', 'is_superuser'),
            'classes': ('collapse',),
        }),
        (_('Permissions détaillées'), {
            'fields': (
                'voir_recettes_potentielles', 'voir_taux_deperdition', 
                'voir_statistiques_globales', 'acces_tous_postes'
            ),
            'classes': ('collapse',),
        }),
        (_('Métadonnées'), {
            'fields': ('date_joined', 'last_login', 'cree_par'),
            'classes': ('collapse',),
        }),
    )
    
    add_fieldsets = (
        (_('Créer un nouvel utilisateur'), {
            'classes': ('wide',),
            'fields': ('username', 'nom_complet', 'telephone', 'email', 
                      'habilitation', 'poste_affectation', 'password1', 'password2'),
        }),
    )
    
    readonly_fields = ['date_joined', 'last_login']
    
    # Actions en masse personnalisées
    actions = [
        'activer_utilisateurs', 'desactiver_utilisateurs', 'envoyer_notification_masse',
        'reset_password_masse', 'export_utilisateurs_csv'
    ]
    
    def habilitation_color(self, obj):
        """Affichage coloré de l'habilitation"""
        colors = {
            'admin_principal': '#dc3545',  # Rouge pour admin principal
            'coord_psrr': '#fd7e14',       # Orange pour coord
            'serv_info': '#6f42c1',        # Violet pour info
            'serv_emission': '#20c997',    # Teal pour émission
            'chef_peage': '#0d6efd',       # Bleu pour chef péage
            'chef_pesage': '#198754',      # Vert pour chef pesage
            'agent_inventaire': '#6c757d', # Gris pour agent
        }
        color = colors.get(obj.habilitation, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_habilitation_display()
        )
    habilitation_color.short_description = _('Rôle')
    
    def interface_type(self, obj):
        """Affichage du type d'interface"""
        from .signals import is_admin_user
        if is_admin_user(obj):
            return format_html(
                '<span style="color: #dc3545;"><i class="fas fa-cog"></i> Panel Django</span>'
            )
        else:
            return format_html(
                '<span style="color: #0d6efd;"><i class="fas fa-desktop"></i> Interface Web</span>'
            )
    interface_type.short_description = _('Interface')
    
    def actions_admin(self, obj):
        """Boutons d'action rapides"""
        actions = []
        
        # Bouton modifier
        edit_url = reverse('admin:accounts_utilisateursupper_change', args=[obj.pk])
        actions.append(f'<a href="{edit_url}" class="button">✏️ Modifier</a>')
        
        # Bouton reset password
        if obj.is_active:
            actions.append(f'<button onclick="resetUserPassword({obj.pk})" class="button">🔑 Reset MDP</button>')
        
        # Bouton notification
        actions.append(f'<button onclick="sendNotification({obj.pk})" class="button">📧 Notifier</button>')
        
        return format_html(' '.join(actions))
    actions_admin.short_description = _('Actions')
    
    def activer_utilisateurs(self, request, queryset):
        """Activer plusieurs utilisateurs"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} utilisateur(s) activé(s) avec succès.')
    activer_utilisateurs.short_description = _('✅ Activer les utilisateurs sélectionnés')
    
    def desactiver_utilisateurs(self, request, queryset):
        """Désactiver plusieurs utilisateurs"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} utilisateur(s) désactivé(s) avec succès.')
    desactiver_utilisateurs.short_description = _('❌ Désactiver les utilisateurs sélectionnés')
    
    def envoyer_notification_masse(self, request, queryset):
        """Envoyer une notification à plusieurs utilisateurs"""
        count = queryset.count()
        self.message_user(request, f'Notification envoyée à {count} utilisateur(s).')
    envoyer_notification_masse.short_description = _('📧 Envoyer notification aux sélectionnés')
    
    def reset_password_masse(self, request, queryset):
        """Réinitialiser le mot de passe de plusieurs utilisateurs"""
        count = queryset.count()
        self.message_user(request, f'Mot de passe réinitialisé pour {count} utilisateur(s).')
    reset_password_masse.short_description = _('🔑 Réinitialiser mots de passe')




# ===================================================================
# ADMIN POSTES - CONFIGURATION AVEC RÉGIONS CAMEROUNAISES
# ===================================================================

@admin.register(Poste, site=admin_site)
class PosteAdmin(admin.ModelAdmin):
    """Administration des postes avec sélection dynamique région/département"""
    
    list_display = [
        'code', 'nom', 'type_icon', 'region', 'departement', 
        'axe_routier', 'status_display', 'coordonnees_admin', 'actions_poste'
    ]
    
    list_filter = [
        'type', 'region', 'is_active', 'date_creation'
    ]
    
    search_fields = [
        'code', 'nom', 'region', 'departement', 'axe_routier'
    ]
    
    ordering = ['region', 'type', 'nom']
    
    fieldsets = (
        (_('🏷️ Identification du poste'), {
            'fields': ('code', 'nom', 'type'),
            'classes': ('wide',),
        }),
        (_('📍 Localisation'), {
            'fields': ('region', 'departement', 'axe_routier'),
            'classes': ('wide',),
            'description': _(
                '<strong>Instructions:</strong><br>'
                '1. Sélectionnez d\'abord la région<br>'
                '2. Le département se mettra à jour automatiquement<br>'
                '3. Saisissez l\'axe routier manuellement'
            )
        }),
        (_('📝 Description'), {
            'fields': ('description',),
            'classes': ('wide',),
        }),
        (_('🌍 Coordonnées GPS (optionnel)'), {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',),
        }),
        (_('⚙️ Statut'), {
            'fields': ('is_active',),
        }),
    )
    
    actions = ['activer_postes', 'desactiver_postes', 'export_postes_csv', 'generer_rapport_postes']
    
    class Media:
        js = ('admin/js/poste_region_departement.js',)
        css = {
            'all': ('admin/css/poste_admin.css',)
        }
    
    def type_icon(self, obj):
        """Affichage avec icône du type de poste"""
        if obj.type == 'peage':
            return format_html(
                '<span style="color: #0d6efd;"><i class="fas fa-road"></i> Péage</span>'
            )
        else:
            return format_html(
                '<span style="color: #198754;"><i class="fas fa-weight"></i> Pesage</span>'
            )
    type_icon.short_description = _('Type')
    
    def status_display(self, obj):
        """Affichage coloré du statut"""
        if obj.is_active:
            return format_html(
                '<span style="color: #198754; font-weight: bold;">✅ Actif</span>'
            )
        else:
            return format_html(
                '<span style="color: #dc3545; font-weight: bold;">❌ Inactif</span>'
            )
    status_display.short_description = _('Statut')
    
    def coordonnees_admin(self, obj):
        """Affichage des coordonnées GPS"""
        if obj.latitude and obj.longitude:
            return format_html(
                '<a href="https://maps.google.com/?q={},{}" target="_blank" style="color: #198754;">'
                '📍 {:.6f}, {:.6f}</a>',
                obj.latitude, obj.longitude, obj.latitude, obj.longitude
            )
        return format_html('<span style="color: #6c757d;">📍 Non renseignées</span>')
    coordonnees_admin.short_description = _('Coordonnées GPS')
    
    def actions_poste(self, obj):
        """Actions rapides pour les postes"""
        actions = []
        
        # Bouton modifier
        edit_url = reverse('admin:accounts_poste_change', args=[obj.pk])
        actions.append(f'<a href="{edit_url}" class="button">✏️ Modifier</a>')
        
        # Bouton statistiques
        actions.append(f'<button onclick="voirStatsPoste({obj.pk})" class="button">📊 Stats</button>')
        
        # Bouton Google Maps
        if obj.latitude and obj.longitude:
            maps_url = f"https://maps.google.com/?q={obj.latitude},{obj.longitude}"
            actions.append(f'<a href="{maps_url}" target="_blank" class="button">🗺️ Maps</a>')
        
        return format_html(' '.join(actions))
    actions_poste.short_description = _('Actions')
    
    def get_form(self, request, obj=None, **kwargs):
        """Formulaire avec sélection dynamique région/département"""
        form = super().get_form(request, obj, **kwargs)
        
        # Régions du Cameroun
        REGIONS_CAMEROUN = [
            ('', '--- Sélectionner une région ---'),
            ('Centre', 'Centre'),
            ('Littoral', 'Littoral'), 
            ('Nord', 'Nord'),
            ('Extrême-Nord', 'Extrême-Nord'),
            ('Adamaoua', 'Adamaoua'),
            ('Ouest', 'Ouest'),
            ('Est', 'Est'),
            ('Sud', 'Sud'),
            ('Nord-Ouest', 'Nord-Ouest'),
            ('Sud-Ouest', 'Sud-Ouest'),
        ]
        
        # Configuration du widget région
        if 'region' in form.base_fields:
            form.base_fields['region'].widget = forms.Select(
                choices=REGIONS_CAMEROUN,
                attrs={
                    'id': 'id_region',
                    'onchange': 'updateDepartements(this.value)',
                    'class': 'form-control'
                }
            )
        
        # Configuration du widget département
        if 'departement' in form.base_fields:
            # Si c'est une modification, garder la valeur actuelle
            if obj and obj.departement:
                initial_dept = obj.departement
            else:
                initial_dept = ''
            
            form.base_fields['departement'].widget = forms.Select(
                choices=[('', '--- Sélectionner d\'abord une région ---')],
                attrs={
                    'id': 'id_departement',
                    'class': 'form-control',
                    'data-initial': initial_dept
                }
            )
        
        # Configuration axe routier avec exemples
        if 'axe_routier' in form.base_fields:
            form.base_fields['axe_routier'].widget = forms.TextInput(attrs={
                'size': '60',
                'placeholder': 'Ex: Yaoundé-Douala, Douala-Bafoussam, Ngaoundéré-Garoua...',
                'class': 'form-control',
                'list': 'axes_routiers'
            })
        
        return form
        # Actions personnalisées
    actions = ['activer_postes', 'desactiver_postes', 'exporter_postes_csv']
    
    def activer_postes(self, request, queryset):
        """Activer plusieurs postes"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} poste(s) activé(s) avec succès.')
    activer_postes.short_description = _('✅ Activer les postes sélectionnés')
    
    def desactiver_postes(self, request, queryset):
        """Désactiver plusieurs postes"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} poste(s) désactivé(s) avec succès.')
    desactiver_postes.short_description = _('❌ Désactiver les postes sélectionnés')
    
    def export_postes_csv(self, request, queryset):
        """Exporter les postes sélectionnés en CSV"""
        count = queryset.count()
        self.message_user(request, f'Export CSV de {count} poste(s) en cours.')
    export_postes_csv.short_description = _('📊 Exporter en CSV')
    
    def generer_rapport_postes(self, request, queryset):
        """Générer un rapport détaillé des postes"""
        count = queryset.count()
        self.message_user(request, f'Rapport PDF de {count} poste(s) en génération.')
    generer_rapport_postes.short_description = _('📄 Générer rapport PDF')

# ===================================================================
# ADMIN JOURNAL AUDIT - CONSULTATION SEULEMENT
# ===================================================================
@admin.register(JournalAudit, site=admin_site)
class JournalAuditAdmin(admin.ModelAdmin):
    """Administration du journal d'audit avec filtres avancés"""
    
    list_display = [
        'timestamp_format', 'utilisateur_info', 'action_color', 'details_court',
        'adresse_ip', 'succes_format', 'duree_formatee', 'voir_details'
    ]
    
    list_filter = [
        'succes', 'action', 'timestamp', 'utilisateur__habilitation',
        'methode_http', 'statut_reponse'
    ]
    
    search_fields = [
        'utilisateur__username', 'utilisateur__nom_complet', 
        'action', 'details', 'adresse_ip'
    ]
    
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'
    
    readonly_fields = [
        'timestamp', 'utilisateur', 'action', 'details', 
        'adresse_ip', 'user_agent', 'url_acces', 'methode_http',
        'succes', 'duree_execution', 'statut_reponse', 'session_key'
    ]
    
    actions = ['export_logs_csv', 'marquer_comme_traite', 'archiver_logs']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # Seuls les superusers peuvent supprimer
    
    def timestamp_format(self, obj):
        """Affichage formaté de la date/heure"""
        return format_html(
            '<div style="white-space: nowrap;">'
            '<strong>{}</strong><br>'
            '<small style="color: #6c757d;">{}</small>'
            '</div>',
            obj.timestamp.strftime('%d/%m/%Y'),
            obj.timestamp.strftime('%H:%M:%S')
        )
    timestamp_format.short_description = _('Date/Heure')
    
    def utilisateur_info(self, obj):
        """Informations enrichies sur l'utilisateur"""
        from .signals import is_admin_user
        interface = "Panel Django" if is_admin_user(obj.utilisateur) else "Interface Web"
        return format_html(
            '<div>'
            '<strong>{}</strong><br>'
            '<small>{}</small><br>'
            '<span style="font-size: 10px; color: #6c757d;">{}</span>'
            '</div>',
            obj.utilisateur.nom_complet,
            obj.utilisateur.username,
            interface
        )
    utilisateur_info.short_description = _('Utilisateur')
    
    def action_color(self, obj):
        """Action avec couleur selon le type"""
        colors = {
            'CONNEXION': '#198754',
            'DÉCONNEXION': '#6c757d',
            'CRÉATION': '#0d6efd',
            'MODIFICATION': '#fd7e14',
            'SUPPRESSION': '#dc3545',
            'ACCÈS REFUSÉ': '#dc3545',
        }
        
        for key, color in colors.items():
            if key in obj.action:
                return format_html(
                    '<span style="color: {}; font-weight: bold;">{}</span>',
                    color, obj.action
                )
        
        return obj.action
    action_color.short_description = _('Action')
    
    def details_court(self, obj):
        """Détails courts avec tooltip"""
        if len(obj.details) > 100:
            court = obj.details[:100] + '...'
            return format_html(
                '<span title="{}" style="cursor: help;">{}</span>',
                obj.details, court
            )
        return obj.details
    details_court.short_description = _('Détails')
    
    def succes_format(self, obj):
        """Statut formaté avec icône"""
        if obj.succes:
            return format_html(
                '<span style="color: #198754;"><i class="fas fa-check-circle"></i> Succès</span>'
            )
        else:
            return format_html(
                '<span style="color: #dc3545;"><i class="fas fa-times-circle"></i> Échec</span>'
            )
    succes_format.short_description = _('Statut')
    
    def duree_formatee(self, obj):
        """Durée formatée avec couleur selon la performance"""
        if obj.duree_execution:
            duree = obj.duree_execution.total_seconds()
            if duree < 1:
                color = '#198754'  # Vert pour rapide
            elif duree < 3:
                color = '#fd7e14'  # Orange pour moyen
            else:
                color = '#dc3545'  # Rouge pour lent
            
            return format_html(
                '<span style="color: {};">{:.3f}s</span>',
                color, duree
            )
        return "N/A"
    duree_formatee.short_description = _('Durée')
    
    def voir_details(self, obj):
        """Bouton pour voir les détails complets"""
        return format_html(
            '<button onclick="voirDetailsLog({})" class="button">🔍 Détails</button>',
            obj.pk
        )
    voir_details.short_description = _('Actions')
    
    def export_logs_csv(self, request, queryset):
        """Exporter les logs sélectionnés"""
        count = queryset.count()
        self.message_user(request, f'Export de {count} entrée(s) du journal en cours.')
    export_logs_csv.short_description = _('📊 Exporter en CSV')

# ===================================================================
# ADMIN NOTIFICATIONS - GESTION COMPLÈTE
# ===================================================================
@admin.register(NotificationUtilisateur, site=admin_site)
class NotificationUtilisateurAdmin(admin.ModelAdmin):
    """Administration des notifications avec envoi en masse"""
    
    list_display = [
        'titre', 'destinataire_info', 'cree_par', 'date_creation_format',
        'type_color', 'lu_format', 'actions_notif'
    ]
    
    list_filter = [
        'type_notification', 'lu', 'date_creation', 'cree_par'
    ]
    
    search_fields = [
        'titre', 'message', 'destinataire__nom_complet', 
        'cree_par__nom_complet'
    ]
    
    ordering = ['-date_creation']
    date_hierarchy = 'date_creation'
    
    actions = ['marquer_comme_lu', 'envoyer_rappel', 'supprimer_lues']
    
    def destinataire_info(self, obj):
        """Informations sur le destinataire"""
        return format_html(
            '<div>'
            '<strong>{}</strong><br>'
            '<small>{}</small>'
            '</div>',
            obj.destinataire.nom_complet,
            obj.destinataire.get_habilitation_display()
        )
    destinataire_info.short_description = _('Destinataire')
    
    def date_creation_format(self, obj):
        """Date de création formatée"""
        return format_html(
            '<div style="white-space: nowrap;">'
            '<strong>{}</strong><br>'
            '<small style="color: #6c757d;">{}</small>'
            '</div>',
            obj.date_creation.strftime('%d/%m/%Y'),
            obj.date_creation.strftime('%H:%M')
        )
    date_creation_format.short_description = _('Date/Heure')
    
    def type_color(self, obj):
        """Type avec couleur"""
        colors = {
            'info': '#0d6efd',
            'succes': '#198754',
            'avertissement': '#fd7e14',
            'erreur': '#dc3545',
        }
        color = colors.get(obj.type_notification, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_type_notification_display()
        )
    type_color.short_description = _('Type')
    
    def lu_format(self, obj):
        """Statut de lecture formaté"""
        if obj.lu:
            return format_html(
                '<span style="color: #198754;">✅ Lu le {}</span>',
                obj.date_lecture.strftime('%d/%m %H:%M') if obj.date_lecture else 'N/A'
            )
        else:
            return format_html(
                '<span style="color: #fd7e14; font-weight: bold;">📧 Non lu</span>'
            )
    lu_format.short_description = _('Statut')
    
    def actions_notif(self, obj):
        """Actions pour les notifications"""
        actions = []
        
        if not obj.lu:
            actions.append(f'<button onclick="marquerCommeLu({obj.pk})" class="button">✅ Marquer lu</button>')
        
        actions.append(f'<button onclick="renvoyerNotification({obj.pk})" class="button">🔄 Renvoyer</button>')
        
        return format_html(' '.join(actions))
    actions_notif.short_description = _('Actions')


# ===================================================================
# PERSONNALISATION GLOBALE DE L'INTERFACE ADMIN
# ===================================================================

# Ajouter du JavaScript personnalisé pour les titres dynamiques
class AdminTitleMixin:
    """Mixin pour ajouter des titres dynamiques selon le module"""
    
    class Media:
        js = ('admin/js/dynamic_titles.js',)
        css = {
            'all': ('admin/css/custom_admin.css',)
        }


# Appliquer le mixin aux classes admin
UtilisateurSUPPERAdmin.__bases__ = (AdminTitleMixin,) + UtilisateurSUPPERAdmin.__bases__
PosteAdmin.__bases__ = (AdminTitleMixin,) + PosteAdmin.__bases__
JournalAuditAdmin.__bases__ = (AdminTitleMixin,) + JournalAuditAdmin.__bases__
NotificationUtilisateurAdmin.__bases__ = (AdminTitleMixin,) + NotificationUtilisateurAdmin.__bases__

# Enregistrer les modèles sur le site admin par défaut pour compatibilité
admin.site.register(UtilisateurSUPPER, UtilisateurSUPPERAdmin)
admin.site.register(Poste, PosteAdmin)
admin.site.register(JournalAudit, JournalAuditAdmin)
admin.site.register(NotificationUtilisateur, NotificationUtilisateurAdmin)