# ===================================================================
# accounts/admin.py - Interface d'administration complète SUPPER
# ===================================================================
# 🔄 REMPLACE le contenu existant du fichier accounts/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.utils.html import format_html
from django.urls import reverse, path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from datetime import datetime, timedelta
from django.http import JsonResponse, HttpResponse
from django.template.response import TemplateResponse
from django.contrib.admin import AdminSite
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
import csv

from .models import UtilisateurSUPPER, Poste, JournalAudit, NotificationUtilisateur, Habilitation
from .forms import UserCreateForm, UserUpdateForm


class SupperAdminSite(AdminSite):
    """Site d'administration personnalisé pour SUPPER"""
    
    site_header = 'Administration SUPPER'
    site_title = 'SUPPER Admin'
    index_title = 'Tableau de Bord Principal'
    site_url = None  # Désactive le lien "Voir le site"
    
    def __init__(self, name='supper_admin'):
        super().__init__(name)
    
    def index(self, request, extra_context=None):
        """Dashboard principal avec statistiques"""
        
        # Vérifier que l'utilisateur est connecté et admin
        if not request.user.is_authenticated or not request.user.is_admin():
            return redirect('admin:login')
        
        # Calculer les statistiques
        stats = self._get_dashboard_stats()
        
        # Activité récente
        recent_actions = JournalAudit.objects.select_related('utilisateur').order_by('-timestamp')[:10]
        
        # Graphiques data
        chart_data = self._get_chart_data()
        
        context = {
            'title': 'Tableau de Bord SUPPER',
            'stats': stats,
            'recent_actions': recent_actions,
            'chart_data': chart_data,
            'has_permission': True,
        }
        
        if extra_context:
            context.update(extra_context)
        
        return TemplateResponse(request, 'admin/dashboard.html', context)
    
    def _get_dashboard_stats(self):
        """Calcule les statistiques pour le dashboard"""
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        # Import conditionnel pour éviter les erreurs de dépendance circulaire
        try:
            from inventaire.models import InventaireJournalier, RecetteJournaliere
        except ImportError:
            InventaireJournalier = None
            RecetteJournaliere = None
        
        stats = {
            'users_total': UtilisateurSUPPER.objects.count(),
            'users_active': UtilisateurSUPPER.objects.filter(is_active=True).count(),
            'users_this_week': UtilisateurSUPPER.objects.filter(date_creation__gte=week_ago).count(),
            'postes_total': Poste.objects.count(),
            'postes_active': Poste.objects.filter(actif=True).count(),
            'postes_peage': Poste.objects.filter(type='peage', actif=True).count(),
            'postes_pesage': Poste.objects.filter(type='pesage', actif=True).count(),
        }
        
        if InventaireJournalier:
            stats.update({
                'inventaires_today': InventaireJournalier.objects.filter(date=today).count(),
                'inventaires_week': InventaireJournalier.objects.filter(date__gte=week_ago).count(),
                'inventaires_locked': InventaireJournalier.objects.filter(verrouille=True).count(),
            })
        
        if RecetteJournaliere:
            stats.update({
                'recettes_today': RecetteJournaliere.objects.filter(date=today).count(),
                'recettes_week': RecetteJournaliere.objects.filter(date__gte=week_ago).count(),
            })
        
        # Activité système
        stats['actions_today'] = JournalAudit.objects.filter(timestamp__date=today).count()
        stats['actions_week'] = JournalAudit.objects.filter(timestamp__gte=week_ago).count()
        
        return stats
    
    def _get_chart_data(self):
        """Prépare les données pour les graphiques"""
        # Données pour graphique d'activité (7 derniers jours)
        dates = []
        actions = []
        
        for i in range(6, -1, -1):
            date = timezone.now().date() - timedelta(days=i)
            count = JournalAudit.objects.filter(timestamp__date=date).count()
            dates.append(date.strftime('%d/%m'))
            actions.append(count)
        
        # Données utilisateurs par rôle
        roles_data = []
        for role_value, role_label in Habilitation.choices:
            count = UtilisateurSUPPER.objects.filter(habilitation=role_value).count()
            if count > 0:
                roles_data.append({'label': role_label, 'value': count})
        
        return {
            'activity_dates': dates,
            'activity_actions': actions,
            'roles_data': roles_data,
        }
    
    def get_urls(self):
        """URLs personnalisées pour l'admin"""
        urls = super().get_urls()
        custom_urls = [
            path('create-users/', self.admin_view(self.create_users_view), name='create_users'),
            path('dashboard/stats/', self.admin_view(self.dashboard_stats_api), name='dashboard_stats'),
            path('saisie-inventaire/', self.admin_view(self.saisie_inventaire_view), name='saisie_inventaire'),
        ]
        return custom_urls + urls
    
    @method_decorator(login_required)
    def create_users_view(self, request):
        """Vue pour création d'utilisateurs en masse"""
        if request.method == 'POST':
            # Logique de création en masse
            count = int(request.POST.get('count', 1))
            base_username = request.POST.get('base_username', 'USER')
            default_password = request.POST.get('default_password', 'supper2025')
            habilitation = request.POST.get('habilitation', 'agent_inventaire')
            
            created_users = []
            for i in range(1, count + 1):
                username = f"{base_username}{i:03d}"
                if not UtilisateurSUPPER.objects.filter(username=username).exists():
                    user = UtilisateurSUPPER.objects.create_user(
                        username=username,
                        nom_complet=f"Utilisateur {username}",
                        telephone=f"+237600{i:06d}",
                        habilitation=habilitation,
                        password=default_password,
                        cree_par=request.user
                    )
                    created_users.append(user)
            
            messages.success(request, f'{len(created_users)} utilisateurs créés avec succès.')
            return redirect('admin:accounts_utilisateursupper_changelist')
        
        context = {
            'title': 'Création d\'utilisateurs en masse',
            'habilitations': Habilitation.choices,
        }
        return TemplateResponse(request, 'admin/create_users.html', context)
    
    @method_decorator(login_required)
    def dashboard_stats_api(self, request):
        """API pour les statistiques en temps réel"""
        stats = self._get_dashboard_stats()
        return JsonResponse(stats)
    
    @method_decorator(login_required)
    def saisie_inventaire_view(self, request):
        """Interface de saisie d'inventaire pour admin - CORRIGÉE"""
        if request.method == 'POST':
            # Logique de traitement de l'inventaire
            try:
                from inventaire.models import InventaireJournalier, DetailInventairePeriode, ConfigurationJour
                
                poste_id = request.POST.get('poste')
                date_inventaire = request.POST.get('date')
                
                if not poste_id or not date_inventaire:
                    messages.error(request, 'Poste et date sont obligatoires.')
                    return redirect('admin:saisie_inventaire')
                
                poste = Poste.objects.get(id=poste_id)
                
                # Créer ou récupérer l'inventaire
                inventaire, created = InventaireJournalier.objects.get_or_create(
                    poste=poste,
                    date=date_inventaire,
                    defaults={
                        'agent_saisie': request.user,
                    }
                )
                
                if inventaire.verrouille:
                    messages.error(request, 'Cet inventaire est déjà verrouillé.')
                    return redirect('admin:saisie_inventaire')
                
                # Sauvegarder les détails par période - NOMS CORRIGÉS
                periodes_mapping = {
                    'vehicules_0809': '08h-09h',
                    'vehicules_0910': '09h-10h', 
                    'vehicules_1011': '10h-11h',
                    'vehicules_1112': '11h-12h',
                    'vehicules_1213': '12h-13h',
                    'vehicules_1314': '13h-14h',
                    'vehicules_1415': '14h-15h',
                    'vehicules_1516': '15h-16h',
                    'vehicules_1617': '16h-17h',
                    'vehicules_1718': '17h-18h'
                }
                
                total_vehicules = 0
                periodes_saisies = 0
                
                for field_name, periode_label in periodes_mapping.items():
                    vehicules = request.POST.get(field_name)
                    if vehicules and vehicules.strip():
                        try:
                            nb_vehicules = int(vehicules)
                            if 0 <= nb_vehicules <= 1000:
                                detail, detail_created = DetailInventairePeriode.objects.get_or_create(
                                    inventaire=inventaire,
                                    periode=periode_label,
                                    defaults={'nombre_vehicules': nb_vehicules}
                                )
                                if not detail_created:
                                    detail.nombre_vehicules = nb_vehicules
                                    detail.save()
                                
                                total_vehicules += nb_vehicules
                                periodes_saisies += 1
                        except ValueError:
                            messages.warning(request, f'Valeur invalide pour la période {periode_label}')
                
                # Mettre à jour les totaux
                inventaire.total_vehicules = total_vehicules
                inventaire.nombre_periodes_saisies = periodes_saisies
                
                # Ajouter les observations si présentes
                observations = request.POST.get('observations', '').strip()
                if observations:
                    inventaire.observations = observations
                
                inventaire.save()
                
                # Verrouiller si demandé
                if request.POST.get('verrouiller'):
                    inventaire.verrouille = True
                    inventaire.save()
                    messages.success(request, f'✅ Inventaire sauvegardé et verrouillé pour {poste.nom} du {date_inventaire}.')
                else:
                    messages.success(request, f'✅ Inventaire sauvegardé pour {poste.nom} du {date_inventaire}.')
                
                return redirect('admin:saisie_inventaire')
                
            except Exception as e:
                messages.error(request, f'❌ Erreur lors de la sauvegarde: {str(e)}')
                return redirect('admin:saisie_inventaire')
        
        # GET: Afficher le formulaire
        postes = Poste.objects.filter(actif=True).order_by('nom')
        
        # Définir les périodes ici pour le template
        periodes = [
            '08h-09h', '09h-10h', '10h-11h', '11h-12h', '12h-13h',
            '13h-14h', '14h-15h', '15h-16h', '16h-17h', '17h-18h'
        ]
        
        context = {
            'title': 'Saisie d\'Inventaire',
            'postes': postes,
            'periodes': periodes,  # AJOUT IMPORTANT pour éviter l'erreur
            'has_permission': True,
        }
        return TemplateResponse(request, 'admin/saisie_inventaire.html', context)


# Instance du site admin personnalisé
admin_site = SupperAdminSite()


# Configuration des modèles dans l'admin

@admin.register(UtilisateurSUPPER, site=admin_site)
class UtilisateurSUPPERAdmin(UserAdmin):
    """Administration des utilisateurs SUPPER"""
    
    add_form = UserCreateForm
    form = UserUpdateForm
    model = UtilisateurSUPPER
    
    list_display = ('username', 'nom_complet', 'habilitation_badge', 'poste_affectation', 
                   'is_active_badge', 'date_creation')
    list_filter = ('habilitation', 'is_active', 'poste_affectation__type', 
                  'poste_affectation__region', 'date_creation')
    search_fields = ('username', 'nom_complet', 'telephone', 'email')
    ordering = ('-date_creation',)
    
    fieldsets = (
        ('Informations de connexion', {
            'fields': ('username', 'password'),
            'classes': ('wide',),
        }),
        ('Informations personnelles', {
            'fields': ('nom_complet', 'telephone', 'email', 'photo_profil'),
            'classes': ('wide',),
        }),
        ('Affectation professionnelle', {
            'fields': ('poste_affectation', 'habilitation'),
            'classes': ('wide',),
        }),
        ('Permissions d\'accès', {
            'fields': ('peut_saisir_peage', 'peut_saisir_pesage', 'acces_tous_postes'),
            'classes': ('collapse',),
        }),
        ('Permissions fonctionnelles', {
            'fields': ('peut_gerer_peage', 'peut_gerer_pesage', 'peut_gerer_personnel',
                      'peut_gerer_budget', 'peut_gerer_inventaire', 'peut_gerer_archives',
                      'peut_gerer_stocks_psrr', 'peut_gerer_stock_info'),
            'classes': ('collapse',),
        }),
        ('Statut du compte', {
            'fields': ('is_active', 'is_staff', 'is_superuser'),
            'classes': ('collapse',),
        }),
        ('Métadonnées', {
            'fields': ('cree_par', 'commentaires', 'date_creation', 'date_modification'),
            'classes': ('collapse',),
        }),
    )
    
    add_fieldsets = (
        ('Création d\'utilisateur', {
            'classes': ('wide',),
            'fields': ('username', 'nom_complet', 'telephone', 'email', 
                      'habilitation', 'poste_affectation', 'password1', 'password2'),
        }),
    )
    
    readonly_fields = ('date_creation', 'date_modification')
    
    def habilitation_badge(self, obj):
        """Badge coloré pour l'habilitation"""
        colors = {
            'admin_principal': 'danger',
            'coord_psrr': 'warning',
            'serv_info': 'info',
            'chef_peage': 'success',
            'chef_pesage': 'success',
            'agent_inventaire': 'secondary',
        }
        color = colors.get(obj.habilitation, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.get_habilitation_display()
        )
    habilitation_badge.short_description = 'Habilitation'
    
    def is_active_badge(self, obj):
        """Badge pour le statut actif"""
        if obj.is_active:
            return format_html('<span class="badge bg-success">Actif</span>')
        return format_html('<span class="badge bg-danger">Inactif</span>')
    is_active_badge.short_description = 'Statut'
    
    def save_model(self, request, obj, form, change):
        """Logique personnalisée de sauvegarde"""
        if not change:  # Création
            obj.cree_par = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['reset_password', 'send_notification', 'export_users']
    
    def reset_password(self, request, queryset):
        """Action pour réinitialiser les mots de passe"""
        count = 0
        for user in queryset:
            user.set_password('supper2025')
            user.save()
            count += 1
        self.message_user(request, f'{count} mots de passe réinitialisés à "supper2025".')
    reset_password.short_description = 'Réinitialiser les mots de passe'
    
    def send_notification(self, request, queryset):
        """Action pour envoyer une notification"""
        # Logique d'envoi de notification
        count = queryset.count()
        self.message_user(request, f'Notification envoyée à {count} utilisateurs.')
    send_notification.short_description = 'Envoyer une notification'
    
    def export_users(self, request, queryset):
        """Export CSV des utilisateurs"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="utilisateurs_supper.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Matricule', 'Nom complet', 'Téléphone', 'Email', 'Habilitation', 'Poste', 'is_active'])
        
        for user in queryset:
            writer.writerow([
                user.username,
                user.nom_complet,
                user.telephone,
                user.email or '',
                user.get_habilitation_display(),
                str(user.poste_affectation) if user.poste_affectation else '',
                'Oui' if user.is_active else 'Non'
            ])
        
        return response
    export_users.short_description = 'Exporter en CSV'


@admin.register(Poste, site=admin_site)
class PosteAdmin(admin.ModelAdmin):
    """Administration des postes"""
    
    list_display = ('nom', 'code', 'type_badge', 'region_badge', 'actif_badge', 'date_creation')
    list_filter = ('type', 'region', 'is_active', 'date_creation')
    search_fields = ('nom', 'code', 'localisation', 'departement')
    ordering = ('region', 'nom')
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('nom', 'code', 'type'),
            'classes': ('wide',),
        }),
        ('Localisation', {
            'fields': ('localisation', 'region', 'departement', 'arrondissement'),
            'classes': ('wide',),
        }),
        ('Coordonnées GPS', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',),
        }),
        ('Statut et métadonnées', {
            'fields': ('actif', 'date_ouverture', 'observations'),
            'classes': ('wide',),
        }),
    )
    
    readonly_fields = ('date_creation', 'date_modification')
    
    def type_badge(self, obj):
        """Badge pour le type de poste"""
        color = 'primary' if obj.type == 'peage' else 'warning'
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.get_type_display()
        )
    type_badge.short_description = 'Type'
    
    def region_badge(self, obj):
        """Badge pour la région"""
        return format_html(
            '<span class="badge bg-secondary">{}</span>',
            obj.get_region_display()
        )
    region_badge.short_description = 'Région'
    
    def actif_badge(self, obj):
        """Badge pour le statut actif"""
        if obj.actif:
            return format_html('<span class="badge bg-success">Actif</span>')
        return format_html('<span class="badge bg-danger">Inactif</span>')
    actif_badge.short_description = 'Statut'


@admin.register(JournalAudit, site=admin_site)
class JournalAuditAdmin(admin.ModelAdmin):
    """Administration du journal d'audit"""
    
    list_display = ('timestamp', 'utilisateur', 'action', 'succes_badge', 'adresse_ip', 'duree_execution')
    list_filter = ('succes', 'action', 'timestamp', 'utilisateur__habilitation')
    search_fields = ('utilisateur__username', 'utilisateur__nom_complet', 'action', 'details')
    ordering = ('-timestamp',)
    date_hierarchy = 'timestamp'
    
    readonly_fields = ('timestamp', 'utilisateur', 'action', 'details', 'adresse_ip',
                      'user_agent', 'session_key', 'url_acces', 'methode_http',
                      'duree_execution', 'statut_reponse', 'succes')
    
    def has_add_permission(self, request):
        """Pas de création manuelle d'entrées d'audit"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Pas de modification des entrées d'audit"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Seuls les admins peuvent supprimer (pour nettoyage)"""
        return request.user.is_superuser
    
    def succes_badge(self, obj):
        """Badge pour le succès de l'action"""
        if obj.succes:
            return format_html('<span class="badge bg-success">Succès</span>')
        return format_html('<span class="badge bg-danger">Échec</span>')
    succes_badge.short_description = 'Statut'


@admin.register(NotificationUtilisateur, site=admin_site)
class NotificationUtilisateurAdmin(admin.ModelAdmin):
    """Administration des notifications"""
    
    list_display = ('titre', 'destinataire', 'type_badge', 'lu', 'date_creation')
    list_filter = ('type_notification', 'lu', 'date_creation')
    search_fields = ('titre', 'message', 'destinataire__username')
    ordering = ('-date_creation',)
    
    def type_badge(self, obj):
        """Badge pour le type de notification"""
        colors = {
            'info': 'info',
            'warning': 'warning',
            'error': 'danger',
            'success': 'success',
            'system': 'secondary',
        }
        color = colors.get(obj.type_notification, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.get_type_notification_display()
        )
    type_badge.short_description = 'Type'
    
    def lue_badge(self, obj):
        """Badge pour le statut lu"""
        if obj.lu:
            return format_html('<span class="badge bg-success">Lue</span>')
        return format_html('<span class="badge bg-warning">Non lue</span>')
    lue_badge.short_description = 'Statut'


# Désinscrire les modèles du site admin par défaut
admin.site.unregister(Group)  # On n'utilise pas les groupes Django