# REMPLACER COMPLÈTEMENT le contenu de accounts/admin.py avec ce code corrigé

# ===================================================================
# accounts/admin.py - Panel administrateur enrichi SUPPER (CORRIGÉ)
# ===================================================================

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html, mark_safe
from django.urls import reverse, path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta, date
from django.http import JsonResponse, HttpResponse
from django.template.response import TemplateResponse
import json

from .models import UtilisateurSUPPER, Poste, JournalAudit, NotificationUtilisateur


class SupperAdminSite(admin.AdminSite):
    """Site d'administration personnalisé pour SUPPER"""
    
    site_header = "SUPPER - Administration"
    site_title = "SUPPER Admin"
    index_title = "Tableau de Bord SUPPER"
    
    def get_urls(self):
        """URLs personnalisées pour le dashboard enrichi"""
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_view(self.dashboard_view), name='dashboard'),
            path('api/stats/', self.admin_view(self.api_stats), name='api_stats'),
            path('api/activity/', self.admin_view(self.api_activity), name='api_activity'),
            path('api/deperdition/', self.admin_view(self.api_deperdition), name='api_deperdition'),
            path('actions/open-day/', self.admin_view(self.open_day_action), name='open_day'),
            path('actions/mark-impertinent/', self.admin_view(self.mark_impertinent_action), name='mark_impertinent'),
            path('export/audit/', self.admin_view(self.export_audit), name='export_audit'),
            path('saisie-inventaire/', self.admin_view(self.saisie_inventaire_view), name='saisie_inventaire'),
        ]
        return custom_urls + urls
    
    def index(self, request, extra_context=None):
        """Page d'accueil avec dashboard enrichi"""
        return self.dashboard_view(request)
    
    def dashboard_view(self, request):
        """Vue principale du dashboard administrateur"""
        context = {
            'title': 'Tableau de Bord SUPPER',
            'subtitle': f'Aperçu système - {timezone.now().strftime("%d/%m/%Y")}',
            'stats': self._get_dashboard_stats(),
            'recent_activity': self._get_recent_activity(),
            'alerts': self._get_system_alerts(),
            'days_status': self._get_days_status(),
            'has_permission': True,
        }
        
        return TemplateResponse(request, "admin/dashboard.html", context)
    
    def _get_dashboard_stats(self):
        """Calcule les statistiques du dashboard"""
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        # Import dynamique pour éviter les erreurs circulaires
        try:
            from inventaire.models import InventaireJournalier, RecetteJournaliere
            inventaires_today = InventaireJournalier.objects.filter(date=today).count()
            recettes_today = RecetteJournaliere.objects.filter(date=today).count()
            inventaires_week = InventaireJournalier.objects.filter(date__gte=week_ago).count()
        except ImportError:
            inventaires_today = 0
            recettes_today = 0
            inventaires_week = 0
        
        return {
            'total_users': UtilisateurSUPPER.objects.filter(is_active=True).count(),
            'total_postes': Poste.objects.filter(is_active=True).count(),
            'inventaires_today': inventaires_today,
            'recettes_today': recettes_today,
            'inventaires_week': inventaires_week,
            'users_online': self._get_active_users_count(),
        }
    
    def _get_active_users_count(self):
        """Compte les utilisateurs actifs (connectés dans les 30 dernières minutes)"""
        thirty_min_ago = timezone.now() - timedelta(minutes=30)
        return JournalAudit.objects.filter(
            timestamp__gte=thirty_min_ago,
            action__icontains='connexion'
        ).values('utilisateur').distinct().count()
    
    def _get_recent_activity(self):
        """Récupère l'activité récente"""
        return JournalAudit.objects.select_related('utilisateur').order_by('-timestamp')[:10]
    
    def _get_system_alerts(self):
        """Génère les alertes système"""
        alerts = []
        today = timezone.now().date()
        
        # Import dynamique
        try:
            from inventaire.models import ConfigurationJour, RecetteJournaliere
            
            # Vérifier les jours non configurés
            if not ConfigurationJour.objects.filter(date=today).exists():
                alerts.append({
                    'type': 'warning',
                    'message': f'Le jour {today.strftime("%d/%m/%Y")} n\'est pas configuré pour la saisie',
                    'action_url': '/admin/actions/open-day/',
                    'action_text': 'Ouvrir le jour'
                })
            
            # Vérifier les inventaires manquants
            postes_sans_inventaire = Poste.objects.filter(is_active=True).count()
            if postes_sans_inventaire > 0:
                alerts.append({
                    'type': 'info',
                    'message': f'{postes_sans_inventaire} poste(s) actif(s) dans le système',
                })
        except ImportError:
            pass
        
        return alerts
    
    def _get_days_status(self):
        """Statut des 7 derniers jours"""
        days = []
        
        try:
            from inventaire.models import ConfigurationJour
            
            for i in range(7):
                day = timezone.now().date() - timedelta(days=i)
                try:
                    config = ConfigurationJour.objects.get(date=day)
                    status = 'success' if config.statut == 'ouvert' else 'secondary'
                    if config.statut == 'impertinent':
                        status = 'warning'
                except ConfigurationJour.DoesNotExist:
                    status = 'secondary'
                
                days.append({
                    'date': day,
                    'status': status,
                    'label': day.strftime('%d/%m')
                })
        except ImportError:
            # Fallback si le module inventaire n'est pas disponible
            for i in range(7):
                day = timezone.now().date() - timedelta(days=i)
                days.append({
                    'date': day,
                    'status': 'secondary',
                    'label': day.strftime('%d/%m')
                })
        
        return days
    
    def api_stats(self, request):
        """API pour les statistiques temps réel"""
        stats = self._get_dashboard_stats()
        return JsonResponse(stats)
    
    def api_activity(self, request):
        """API pour l'activité horaire"""
        period = request.GET.get('period', '24h')
        
        if period == '24h':
            # Activité des 24 dernières heures
            start_time = timezone.now() - timedelta(hours=24)
            data = []
            for i in range(24):
                hour_start = start_time + timedelta(hours=i)
                hour_end = hour_start + timedelta(hours=1)
                count = JournalAudit.objects.filter(
                    timestamp__gte=hour_start,
                    timestamp__lt=hour_end
                ).count()
                data.append(count)
            
            return JsonResponse({
                'labels': [f'{i}h' for i in range(24)],
                'data': data,
                'title': 'Activité des 24 dernières heures'
            })
        
        return JsonResponse({'error': 'Période non supportée'})
    
    def api_deperdition(self, request):
        """API pour les taux de déperdition"""
        days = []
        data = []
        colors = []
        
        try:
            from inventaire.models import RecetteJournaliere
            
            for i in range(7):
                day = timezone.now().date() - timedelta(days=i)
                days.append(day.strftime('%d/%m'))
                
                # Calculer le taux moyen de déperdition du jour
                recettes = RecetteJournaliere.objects.filter(date=day)
                if recettes.exists():
                    taux_moyen = sum(r.taux_deperdition or 0 for r in recettes) / recettes.count()
                    data.append(float(taux_moyen))
                    
                    # Couleur selon le taux
                    if taux_moyen > -10:
                        colors.append('#28a745')  # Vert
                    elif taux_moyen >= -30:
                        colors.append('#ffc107')  # Orange
                    else:
                        colors.append('#dc3545')  # Rouge
                else:
                    data.append(0)
                    colors.append('#6c757d')  # Gris
        except ImportError:
            # Fallback si inventaire non disponible
            for i in range(7):
                day = timezone.now().date() - timedelta(days=i)
                days.append(day.strftime('%d/%m'))
                data.append(0)
                colors.append('#6c757d')
        
        return JsonResponse({
            'labels': days[::-1],  # Inverser pour avoir du plus ancien au plus récent
            'data': data[::-1],
            'colors': colors[::-1]
        })
    
    def open_day_action(self, request):
        """Action pour ouvrir le jour actuel"""
        if request.method == 'POST':
            try:
                from inventaire.models import ConfigurationJour
                today = timezone.now().date()
                
                config, created = ConfigurationJour.objects.get_or_create(
                    date=today,
                    defaults={
                        'statut': 'ouvert',
                        'cree_par': request.user,
                        'commentaire': 'Ouvert depuis le dashboard admin'
                    }
                )
                
                if created:
                    messages.success(request, f'Jour {today.strftime("%d/%m/%Y")} ouvert avec succès')
                else:
                    if config.statut != 'ouvert':
                        config.statut = 'ouvert'
                        config.save()
                        messages.success(request, f'Jour {today.strftime("%d/%m/%Y")} réouvert')
                    else:
                        messages.info(request, f'Jour {today.strftime("%d/%m/%Y")} déjà ouvert')
            except ImportError:
                messages.error(request, 'Module inventaire non disponible')
        
        return redirect('/admin/dashboard/')
    
    def mark_impertinent_action(self, request):
        """Action pour marquer un jour comme impertinent"""
        if request.method == 'POST':
            date_str = request.POST.get('date')
            if date_str:
                try:
                    from inventaire.models import ConfigurationJour
                    day = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
                    ConfigurationJour.marquer_impertinent(
                        day, 
                        request.user, 
                        "Marqué impertinent depuis le dashboard admin"
                    )
                    messages.success(request, f'Jour {day.strftime("%d/%m/%Y")} marqué comme impertinent')
                except (ValueError, ImportError) as e:
                    messages.error(request, f'Erreur: {str(e)}')
        
        return redirect('/admin/dashboard/')
    
    def export_audit(self, request):
        """Export du journal d'audit en CSV"""
        import csv
        from django.utils import timezone
        
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="audit_supper_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        # BOM UTF-8 pour Excel
        response.write('\ufeff')
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Date/Heure', 'Utilisateur', 'Action', 'Détails', 'IP', 'Succès'])
        
        for entry in JournalAudit.objects.select_related('utilisateur').order_by('-timestamp'):
            writer.writerow([
                entry.timestamp.strftime('%d/%m/%Y %H:%M:%S'),
                entry.utilisateur.nom_complet,
                entry.action,
                entry.details[:100] + '...' if len(entry.details) > 100 else entry.details,
                entry.adresse_ip or 'N/A',
                'Oui' if entry.succes else 'Non'
            ])
        
        return response
    
    def saisie_inventaire_view(self, request):
        """Interface de saisie d'inventaire pour les admins"""
        periodes_matin = ["08h-09h", "09h-10h", "10h-11h", "11h-12h", "12h-13h"]
        periodes_apresmidi = ["13h-14h", "14h-15h", "15h-16h", "16h-17h", "17h-18h"]
        if request.method == 'POST':
            # Traitement de la saisie d'inventaire
            poste_id = request.POST.get('poste')
            date_inventaire = request.POST.get('date')
           
            
            try:
                from inventaire.models import InventaireJournalier, DetailInventairePeriode
                
                poste = Poste.objects.get(id=poste_id)
                date_obj = timezone.datetime.strptime(date_inventaire, '%Y-%m-%d').date()
                
                # Créer ou récupérer l'inventaire
                inventaire, created = InventaireJournalier.objects.get_or_create(
                    poste=poste,
                    date=date_obj,
                    defaults={'agent_saisie': request.user}
                )
                
                if not inventaire.verrouille:
                    # Traiter les périodes
                    for periode in ['08h-09h', '09h-10h', '10h-11h', '11h-12h', 
                                  '12h-13h', '13h-14h', '14h-15h', '15h-16h', 
                                  '16h-17h', '17h-18h']:
                        nb_vehicules = request.POST.get(f'periode_{periode}')
                        if nb_vehicules:
                            DetailInventairePeriode.objects.update_or_create(
                                inventaire=inventaire,
                                periode=periode,
                                defaults={'nombre_vehicules': int(nb_vehicules)}
                            )
                    
                    inventaire.recalculer_totaux()
                    messages.success(request, f'Inventaire saisi pour {poste.nom} - {date_obj.strftime("%d/%m/%Y")}')
                else:
                    messages.error(request, 'Inventaire déjà verrouillé')
                    
            except Exception as e:
                messages.error(request, f'Erreur lors de la saisie: {str(e)}')
        
        # Afficher le formulaire
        context = {
            'title': 'Saisie Inventaire (Admin)',
            'postes': Poste.objects.filter(is_active=True).order_by('nom'),
            'date_today': timezone.now().date(),
            'periodes_matin': periodes_matin,
            'periodes_apresmidi': periodes_apresmidi,
        }
        
        return TemplateResponse(request, "admin/saisie_inventaire.html", context)


# Instance personnalisée du site admin
admin_site = SupperAdminSite(name='supper_admin')


@admin.register(UtilisateurSUPPER, site=admin_site)
class UtilisateurSupperAdmin(UserAdmin):
    """Administration des utilisateurs SUPPER"""
    
    list_display = (
        'username', 'nom_complet', 'get_habilitation_display', 
        'poste_affectation', 'is_active', 'get_permissions_count',
        'date_creation'
    )
    
    list_filter = (
        'habilitation', 'is_active', 'acces_tous_postes'
    )
    
    search_fields = ('username', 'nom_complet', 'telephone', 'email')
    
    readonly_fields = ('date_creation', 'date_modification', 'last_login')
    
    fieldsets = (
        ('Informations de Base', {
            'fields': ('username', 'nom_complet', 'telephone', 'email')
        }),
        ('Affectation', {
            'fields': ('poste_affectation', 'habilitation')
        }),
        ('Permissions Système', {
            'fields': (
                'is_active', 'is_staff', 'is_superuser',
                'acces_tous_postes'
            )
        }),
        ('Permissions Métier', {
            'fields': (
                'peut_saisir_peage', 'peut_saisir_pesage',
                'peut_gerer_peage', 'peut_gerer_pesage',
                'peut_gerer_personnel', 'peut_gerer_budget',
                'peut_gerer_inventaire', 'peut_gerer_archives',
                'peut_gerer_stocks_psrr', 'peut_gerer_stock_info'
            ),
            'classes': ('collapse',)
        }),
        ('Métadonnées', {
            'fields': ('cree_par', 'date_creation', 'date_modification', 'last_login'),
            'classes': ('collapse',)
        })
    )
    
    def get_habilitation_display(self, obj):
        return obj.get_habilitation_display()
    get_habilitation_display.short_description = 'Rôle'
    
    def get_permissions_count(self, obj):
        count = len(obj.get_permissions_list())
        color = 'green' if count > 3 else 'orange' if count > 0 else 'red'
        return format_html(
            '<span style="color: {};">{} permissions</span>',
            color, count
        )
    get_permissions_count.short_description = 'Permissions'
    
    actions = ['reset_password_action', 'send_notification_action']
    
    def reset_password_action(self, request, queryset):
        """Action pour réinitialiser les mots de passe"""
        count = 0
        for user in queryset:
            user.set_password('1234')  # Mot de passe par défaut
            user.save()
            count += 1
        
        self.message_user(
            request, 
            f'{count} mot(s) de passe réinitialisé(s) à "1234"'
        )
    reset_password_action.short_description = "Réinitialiser mots de passe"
    
    def send_notification_action(self, request, queryset):
        """Action pour envoyer une notification"""
        self.message_user(request, "Fonctionnalité de notification à développer")
    send_notification_action.short_description = "Envoyer notification"


@admin.register(Poste, site=admin_site)
class PosteAdmin(admin.ModelAdmin):
    """Administration des postes"""
    
    list_display = (
        'nom', 'code', 'type', 'region',
        'departement', 'is_active', 'get_agents_count'
    )
    
    list_filter = ('region',)
    search_fields = ('nom', 'code', 'localisation', 'departement')
    
    fieldsets = (
        ('Informations Générales', {
            'fields': ('nom', 'code', 'type', 'is_active')
        }),
        ('Localisation', {
            'fields': ('axe_routier', 'region', 'departement')
        }),
        ('Coordonnées GPS', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',)
        }),
        ('Informations Complémentaires', {
            'fields': ( 'description',),
            'classes': ('collapse',)
        })
    )
    
    def get_type_display(self, obj):
        return obj.get_type_display()
    get_type_display.short_description = 'Type'
    
    def get_region_display(self, obj):
        return obj.get_region_display()
    get_region_display.short_description = 'Région'
    
    def get_actif_display(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Actif</span>')
        else:
            return format_html('<span style="color: red;">✗ Inactif</span>')
    get_actif_display.short_description = 'Statut'
    
    def get_agents_count(self, obj):
        count = obj.agents_affectes.filter(is_active=True).count()
        return format_html(
            '<span class="badge badge-{}">{}</span>',
            'success' if count > 0 else 'secondary',
            count
        )
    get_agents_count.short_description = 'Agents'


@admin.register(JournalAudit, site=admin_site)
class JournalAuditAdmin(admin.ModelAdmin):
    """Administration du journal d'audit"""
    
    list_display = (
        'timestamp', 'get_user_display', 'action', 
        'get_success_display', 'adresse_ip', 'get_duration_display'
    )
    
    list_filter = (
        'succes', 'action', 'utilisateur__habilitation',
        ('timestamp', admin.DateFieldListFilter)
    )
    
    search_fields = ('utilisateur__username', 'utilisateur__nom_complet', 'action', 'details')
    
    readonly_fields = (
        'timestamp', 'utilisateur', 'action', 'details',
        'adresse_ip', 'user_agent', 'session_key', 'url_acces',
        'methode_http', 'statut_reponse', 'succes', 'duree_execution'
    )
    
    date_hierarchy = 'timestamp'
    
    def get_user_display(self, obj):
        return format_html(
            '<strong>{}</strong><br><small>{}</small>',
            obj.utilisateur.nom_complet,
            obj.utilisateur.username
        )
    get_user_display.short_description = 'Utilisateur'
    
    def get_success_display(self, obj):
        if obj.succes:
            return format_html('<span style="color: green;">✓ Succès</span>')
        else:
            return format_html('<span style="color: red;">✗ Échec</span>')
    get_success_display.short_description = 'Statut'
    
    def get_duration_display(self, obj):
        if obj.duree_execution:
            return obj.duree_execution
        return '-'
    get_duration_display.short_description = 'Durée'
    
    def has_add_permission(self, request):
        return False  # Pas de création manuelle
    
    def has_change_permission(self, request, obj=None):
        return False  # Lecture seule


@admin.register(NotificationUtilisateur, site=admin_site)
class NotificationAdmin(admin.ModelAdmin):
    """Administration des notifications"""
    
    list_display = ('titre', 'destinataire', 'type_notification', 'get_lue_display', 'date_creation')
    list_filter = ('type_notification', 'date_creation')
    search_fields = ('titre', 'message', 'destinataire__nom_complet')
    
    readonly_fields = ('date_creation', 'date_lecture')
    
    def get_lue_display(self, obj):
        if obj.lue:
            return format_html('<span style="color: green;">✓ Lue</span>')
        else:
            return format_html('<span style="color: orange;">Non lue</span>')
    get_lue_display.short_description = 'Statut'


# Enregistrer les modèles de l'inventaire dans le site admin personnalisé
# Import conditionnel pour éviter les erreurs si l'app n'est pas encore migrée
try:
    from inventaire.models import (
        ConfigurationJour, InventaireJournalier, 
        DetailInventairePeriode, RecetteJournaliere, StatistiquesPeriodiques
    )

    @admin.register(ConfigurationJour, site=admin_site)
    class ConfigurationJourAdmin(admin.ModelAdmin):
        list_display = ('date', 'statut', 'cree_par', 'date_creation')
        list_filter = ('statut', 'date_creation')
        date_hierarchy = 'date'

    @admin.register(InventaireJournalier, site=admin_site)
    class InventaireJournalierAdmin(admin.ModelAdmin):
        list_display = ('poste', 'date', 'agent_saisie', 'total_vehicules', 'verrouille', 'valide')
        list_filter = ('verrouille', 'valide', 'date')
        search_fields = ('poste__nom', 'agent_saisie__nom_complet')
        date_hierarchy = 'date'

    @admin.register(RecetteJournaliere, site=admin_site)
    class RecetteJournaliereAdmin(admin.ModelAdmin):
        list_display = ('poste', 'date', 'montant_declare', 'taux_deperdition', 'get_alerte_display')
        list_filter = ('verrouille', 'valide', 'date')
        search_fields = ('poste__nom', 'chef_poste__nom_complet')
        
        def get_alerte_display(self, obj):
            couleur = obj.get_couleur_alerte()
            colors = {'success': 'green', 'warning': 'orange', 'danger': 'red', 'secondary': 'gray'}
            return format_html(
                '<span style="color: {};">●</span>',
                colors.get(couleur, 'gray')
            )
        get_alerte_display.short_description = 'Alerte'

except ImportError:
    # Les modèles inventaire ne sont pas encore disponibles
    pass