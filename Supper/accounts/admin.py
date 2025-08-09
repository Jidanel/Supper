# Fichier : Supper/accounts/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.utils.html import format_html
from django.urls import reverse, path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from datetime import datetime, timedelta, date
from django.http import JsonResponse, HttpResponse
from django.template.response import TemplateResponse
from django.contrib.admin import AdminSite
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
import csv
import logging
logger = logging.getLogger('supper')

from .models import UtilisateurSUPPER, Poste, JournalAudit, NotificationUtilisateur, Habilitation


class SupperAdminSite(AdminSite):
    """Site d'administration personnalisé pour SUPPER"""
    
    site_header = 'Administration SUPPER'
    site_title = 'SUPPER Admin'
    index_title = 'Tableau de Bord Principal'
    site_url = None  # Désactive le lien "Voir le site"
    
    def __init__(self, name='admin'):
        super().__init__(name)
    
    def index(self, request, extra_context=None):
        """Dashboard principal avec vraies données - VERSION FINALE"""
        
        # Vérifier authentification
        if not request.user.is_authenticated:
            return redirect('admin:login')
        
        # Vérifier permissions admin
        if not (request.user.is_superuser or 
                hasattr(request.user, 'habilitation') and
                request.user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info']):
            messages.error(request, 'Accès non autorisé au panel d\'administration.')
            return redirect('admin:login')
        
        # Calculer les vraies statistiques
        stats = self._get_dashboard_stats()
        
        # Activité récente (vraies données)
        recent_actions = JournalAudit.objects.select_related('utilisateur').order_by('-timestamp')[:10]
        
        # Données pour graphiques
        chart_data = self._get_chart_data()
        
        context = {
            'title': 'Tableau de Bord SUPPER',
            'subtitle': 'Administration - Suivi des Péages et Pesages Routiers',
            'stats': stats,
            'recent_actions': recent_actions,
            'chart_data': chart_data,
            'has_permission': True,
        }
        
        if extra_context:
            context.update(extra_context)
        
        return TemplateResponse(request, 'admin/dashboard.html', context)

    def dashboard_view(self, request):
        """Vue du tableau de bord principal"""
        return redirect('http://127.0.0.1:8000/')
        
    def _get_dashboard_stats(self):
        """Calcule les vraies statistiques pour le dashboard"""
        from django.db import connection
        
        # CORRIGÉ: Import explicite et utilisation correcte
        today = date.today()
        week_ago = today - timedelta(days=7)
        
        # Import conditionnel pour éviter les erreurs
        try:
            from inventaire.models import InventaireJournalier, RecetteJournaliere
            inventaire_model = InventaireJournalier
            recette_model = RecetteJournaliere
        except ImportError:
            inventaire_model = None
            recette_model = None
        
        # Stats utilisateurs
        users_total = UtilisateurSUPPER.objects.count()
        users_active = UtilisateurSUPPER.objects.filter(is_active=True).count()
        users_inactive = users_total - users_active
        users_this_week = UtilisateurSUPPER.objects.filter(date_creation__gte=week_ago).count()
        
        # Utilisateurs en ligne (sessions actives des 30 dernières minutes)
        try:
            from django.contrib.sessions.models import Session
            active_sessions = Session.objects.filter(
                expire_date__gte=timezone.now() - timedelta(minutes=30)
            ).count()
        except Exception:
            active_sessions = 0
        
        # Stats postes - GARDÉ: is_active et type
        postes_total = Poste.objects.count()
        postes_active = Poste.objects.filter(is_active=True).count()
        postes_inactive = postes_total - postes_active
        postes_peage = Poste.objects.filter(type='peage', is_active=True).count()
        postes_pesage = Poste.objects.filter(type='pesage', is_active=True).count()
        
        # Stats inventaires
        inventaires_today = 0
        inventaires_week = 0
        inventaires_locked = 0
        if inventaire_model:
            try:
                inventaires_today = inventaire_model.objects.filter(date=today).count()
                inventaires_week = inventaire_model.objects.filter(date__gte=week_ago).count()
                inventaires_locked = inventaire_model.objects.filter(verrouille=True, valide=False).count()
            except Exception:
                pass
        
        # Stats recettes
        recettes_today = 0
        recettes_week = 0
        if recette_model:
            try:
                recettes_today = recette_model.objects.filter(date=today).count()
                recettes_week = recette_model.objects.filter(date__gte=week_ago).count()
            except Exception:
                pass
        
        # Stats activité/audit
        actions_today = JournalAudit.objects.filter(timestamp__date=today).count()
        actions_week = JournalAudit.objects.filter(timestamp__gte=week_ago).count()
        total_logs = JournalAudit.objects.count()
        
        # Stats base de données
        db_tables = 0
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
                result = cursor.fetchone()
                if result:
                    db_tables = result[0]
        except Exception:
            db_tables = 0
        
        return {
            # Utilisateurs
            'users_total': users_total,
            'users_active': users_active,
            'users_inactive': users_inactive,
            'users_this_week': users_this_week,
            'users_online': active_sessions,
            
            # Postes
            'postes_total': postes_total,
            'postes_active': postes_active,
            'postes_inactive': postes_inactive,
            'postes_peage': postes_peage,
            'postes_pesage': postes_pesage,
            
            # Inventaires
            'inventaires_today': inventaires_today,
            'inventaires_week': inventaires_week,
            'inventaires_locked': inventaires_locked,
            
            # Recettes
            'recettes_today': recettes_today,
            'recettes_week': recettes_week,
            
            # Activité
            'actions_today': actions_today,
            'actions_week': actions_week,
            'total_logs': total_logs,
            
            # Système
            'db_tables': db_tables,
        }

    def _get_chart_data(self):
        """Prépare les vraies données pour les graphiques"""
        from django.db.models import Count, Q
        
        # Données d'activité (7 derniers jours)
        activity_dates = []
        activity_counts = []
        
        for i in range(6, -1, -1):
            target_date = date.today() - timedelta(days=i)
            count = JournalAudit.objects.filter(timestamp__date=target_date).count()
            activity_dates.append(target_date.strftime('%d/%m'))
            activity_counts.append(count)
        
        # Données utilisateurs par rôle
        users_by_role = UtilisateurSUPPER.objects.values('habilitation').annotate(
            count=Count('id')
        ).order_by('-count')
        
        users_labels = []
        users_data = []
        for item in users_by_role:
            # Convertir le code en libellé lisible
            role_display = dict(Habilitation.choices).get(item['habilitation'], item['habilitation'])
            users_labels.append(role_display)
            users_data.append(item['count'])
        
        # Données de déperdition (derniers postes avec recettes)
        deperdition_data = []
        try:
            from inventaire.models import RecetteJournaliere
            
            # Prendre les 5 dernières recettes avec taux de déperdition
            recent_recettes = RecetteJournaliere.objects.filter(
                taux_deperdition__isnull=False
            ).select_related('poste').order_by('-date')[:5]
            
            deperdition_labels = []
            deperdition_values = []
            deperdition_colors = []
            
            for recette in recent_recettes:
                deperdition_labels.append(recette.poste.nom[:15] + '...' if len(recette.poste.nom) > 15 else recette.poste.nom)
                deperdition_values.append(float(recette.taux_deperdition))
                
                # Couleur selon le taux
                if recette.taux_deperdition > -10:
                    deperdition_colors.append('#28a745')  # Vert
                elif recette.taux_deperdition >= -30:
                    deperdition_colors.append('#ffc107')  # Orange
                else:
                    deperdition_colors.append('#dc3545')  # Rouge
            
            deperdition_data = {
                'labels': deperdition_labels,
                'data': deperdition_values,
                'colors': deperdition_colors
            }
        except ImportError:
            deperdition_data = {
                'labels': ['Aucune donnée'],
                'data': [0],
                'colors': ['#6c757d']
            }
        
        return {
            'activity_data': {
                'labels': activity_dates,
                'data': activity_counts
            },
            'users_by_role': {
                'labels': users_labels,
                'data': users_data
            },
            'deperdition_data': deperdition_data
        }
    
    def get_urls(self):
        """URLs complètes avec toutes les API"""
        urls = super().get_urls()
        custom_urls = [

            path('dashboard/', self.admin_view(self.dashboard_view), name='dashboard'),
            # API Dashboard
            path('api/stats/', self.admin_view(self.api_stats_view), name='api_stats'),
            path('api/activity/', self.admin_view(self.api_activity_view), name='api_activity'),
            path('api/deperdition/', self.admin_view(self.api_deperdition_view), name='api_deperdition'),
            path('api/notifications/count/', self.admin_view(self.notification_count_view), name='notification_count'),
            
            # Actions rapides
            path('actions/open-day/', self.admin_view(self.open_day_view), name='open_day'),
            path('actions/mark-impertinent/', self.admin_view(self.mark_impertinent_view), name='mark_impertinent'),
            
            # Exports
            path('export/audit/', self.admin_view(self.export_audit_view), name='export_audit'),
            
            # Autres vues
            path('tools/create-users/', self.admin_view(self.create_users_view), name='create_users'),
            path('tools/saisie-inventaire/', self.admin_view(self.saisie_inventaire_view), name='saisie_inventaire'),
            
            # Monitoring
            path('monitoring/ping/', self.admin_view(self.ping_view), name='ping'),
        ]
        return custom_urls + urls
    
    @method_decorator(login_required)
    def ping_view(self, request):
        """Vue simple pour vérifier la connexion"""
        return JsonResponse({'status': 'ok', 'timestamp': timezone.now().isoformat()})
    
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
    
    def saisie_inventaire_view(self, request):
        """Vue de saisie d'inventaire"""
        from inventaire.views import SaisieInventaireView
        return SaisieInventaireView.as_view()(request)

    @method_decorator(login_required)
    def api_stats_view(self, request):
        """API pour les statistiques temps réel avec vraies données"""
        stats = self._get_dashboard_stats()
        return JsonResponse(stats)

    @method_decorator(login_required)
    def api_activity_view(self, request):
        """API pour l'activité système avec vraies données"""
        period = request.GET.get('period', '7d')
        
        if period == '24h':
            # Données par heure des dernières 24h
            now = timezone.now()
            labels = []
            data = []
            
            for i in range(23, -1, -1):
                hour_start = now - timedelta(hours=i)
                hour_end = hour_start + timedelta(hours=1)
                count = JournalAudit.objects.filter(
                    timestamp__gte=hour_start,
                    timestamp__lt=hour_end
                ).count()
                labels.append(hour_start.strftime('%H:00'))
                data.append(count)
            
            result = {
                'title': 'Activité 24 heures',
                'labels': labels,
                'data': data
            }
        
        elif period == '7d':
            # Données par jour des 7 derniers jours
            labels = []
            data = []
            
            for i in range(6, -1, -1):
                target_date = date.today() - timedelta(days=i)
                count = JournalAudit.objects.filter(timestamp__date=target_date).count()
                labels.append(target_date.strftime('%d/%m'))
                data.append(count)
            
            result = {
                'title': 'Activité 7 jours',
                'labels': labels,
                'data': data
            }
        
        else:  # 30d
            # Données par semaine des 4 dernières semaines
            labels = []
            data = []
            
            for i in range(3, -1, -1):
                week_start = date.today() - timedelta(days=i*7)
                week_end = week_start + timedelta(days=6)
                count = JournalAudit.objects.filter(
                    timestamp__date__gte=week_start,
                    timestamp__date__lte=week_end
                ).count()
                labels.append(f'Sem {4-i}')
                data.append(count)
            
            result = {
                'title': 'Activité 30 jours',
                'labels': labels,
                'data': data
            }
        
        return JsonResponse(result)

    @method_decorator(login_required)
    def api_deperdition_view(self, request):
        """API pour les taux de déperdition avec vraies données"""
        try:
            from inventaire.models import RecetteJournaliere
            
            # Prendre les 8 dernières recettes avec taux calculé
            recettes = RecetteJournaliere.objects.filter(
                taux_deperdition__isnull=False
            ).select_related('poste').order_by('-date')[:8]
            
            labels = []
            data = []
            colors = []
            
            for recette in recettes:
                # Nom du poste (raccourci si trop long)
                nom_poste = recette.poste.nom
                if len(nom_poste) > 12:
                    nom_poste = nom_poste[:12] + '...'
                labels.append(nom_poste)
                
                # Valeur du taux
                taux = float(recette.taux_deperdition)
                data.append(taux)
                
                # Couleur selon les seuils SUPPER
                if taux > -10:
                    colors.append('#28a745')  # Vert - Bon
                elif taux >= -30:
                    colors.append('#ffc107')  # Orange - Attention
                else:
                    colors.append('#dc3545')  # Rouge - Critique
            
            result = {
                'labels': labels,
                'data': data,
                'colors': colors
            }
        
        except ImportError:
            # Fallback si le modèle n'existe pas
            result = {
                'labels': ['Aucune donnée'],
                'data': [0],
                'colors': ['#6c757d']
            }
        
        return JsonResponse(result)

    @method_decorator(login_required)
    def notification_count_view(self, request):
        """API pour le compteur de notifications"""
        if request.user.is_superuser or request.user.habilitation == 'admin_principal':
            count = NotificationUtilisateur.objects.filter(
                destinataire=request.user,
                lu=False
            ).count()
        else:
            count = 0
        
        return JsonResponse({'count': count})

    @method_decorator(login_required)
    def open_day_view(self, request):
        """Vue pour ouvrir un jour avec vraies données"""
        if request.method == 'POST':
            try:
                from inventaire.models import ConfigurationJour
                
                today = date.today()
                config, created = ConfigurationJour.objects.get_or_create(
                    date=today,
                    defaults={
                        'statut': 'ouvert',
                        'cree_par': request.user,
                        'commentaire': f'Ouvert via dashboard par {request.user.nom_complet} le {timezone.now().strftime("%d/%m/%Y à %H:%M")}'
                    }
                )
                
                if not created:
                    config.statut = 'ouvert'
                    config.commentaire = f'Réouvert via dashboard par {request.user.nom_complet} le {timezone.now().strftime("%d/%m/%Y à %H:%M")}'
                    config.save()
                
                # Journaliser l'action
                JournalAudit.objects.create(
                    utilisateur=request.user,
                    action="Ouverture jour saisie",
                    details=f"Jour {today.strftime('%d/%m/%Y')} ouvert pour la saisie",
                    adresse_ip=request.META.get('REMOTE_ADDR'),
                    url_acces=request.path,
                    methode_http=request.method,
                    succes=True
                )
                
                messages.success(request, f'✅ Jour {today.strftime("%d/%m/%Y")} ouvert pour la saisie.')
                
            except Exception as e:
                logger.error(f'Erreur ouverture jour: {str(e)}')
                messages.error(request, f'❌ Erreur lors de l\'ouverture du jour: {str(e)}')
        
        return JsonResponse({'success': True})

    @method_decorator(login_required)
    def mark_impertinent_view(self, request):
        """Vue pour marquer un jour comme impertinent"""
        if request.method == 'POST':
            try:
                from inventaire.models import ConfigurationJour
                
                date_str = request.POST.get('date')
                if not date_str:
                    return JsonResponse({'error': 'Date requise'}, status=400)
                
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                
                config, created = ConfigurationJour.objects.get_or_create(
                    date=target_date,
                    defaults={
                        'statut': 'impertinent',
                        'cree_par': request.user,
                        'commentaire': f'Marqué impertinent via dashboard par {request.user.nom_complet} le {timezone.now().strftime("%d/%m/%Y à %H:%M")}'
                    }
                )
                
                if not created:
                    config.statut = 'impertinent'
                    config.commentaire = f'Marqué impertinent via dashboard par {request.user.nom_complet} le {timezone.now().strftime("%d/%m/%Y à %H:%M")}'
                    config.save()
                
                # Journaliser l'action
                JournalAudit.objects.create(
                    utilisateur=request.user,
                    action="Marquage jour impertinent",
                    details=f"Jour {target_date.strftime('%d/%m/%Y')} marqué comme impertinent",
                    adresse_ip=request.META.get('REMOTE_ADDR'),
                    url_acces=request.path,
                    methode_http=request.method,
                    succes=True
                )
                
                messages.warning(request, f'⚠️ Jour {target_date.strftime("%d/%m/%Y")} marqué comme impertinent.')
                
            except Exception as e:
                logger.error(f'Erreur marquage impertinent: {str(e)}')
                return JsonResponse({'error': str(e)}, status=500)
        
        return JsonResponse({'success': True})

    @method_decorator(login_required)
    def export_audit_view(self, request):
        """Export complet du journal d'audit"""
        try:
            import csv
            
            # Export des 30 derniers jours par défaut
            days = int(request.GET.get('days', 30))
            start_date = date.today() - timedelta(days=days)
            
            logs = JournalAudit.objects.filter(
                timestamp__date__gte=start_date
            ).select_related('utilisateur').order_by('-timestamp')
            
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            filename = f"audit_supper_{date.today().strftime('%Y%m%d')}_{logs.count()}entries.csv"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            # BOM UTF-8 pour Excel
            response.write('\ufeff')
            
            writer = csv.writer(response, delimiter=';')
            writer.writerow([
                'Date/Heure', 'Utilisateur', 'Nom Complet', 'Habilitation', 'Poste',
                'Action', 'Détails', 'IP', 'User Agent', 'URL', 'Méthode',
                'Statut HTTP', 'Succès', 'Durée', 'Session'
            ])
            
            for log in logs:
                writer.writerow([
                    log.timestamp.strftime('%d/%m/%Y %H:%M:%S'),
                    log.utilisateur.username,
                    log.utilisateur.nom_complet,
                    log.utilisateur.get_habilitation_display(),
                    log.utilisateur.poste_affectation.nom if log.utilisateur.poste_affectation else 'Non affecté',
                    log.action,
                    log.details[:200] + '...' if len(log.details or '') > 200 else log.details or '',
                    log.adresse_ip or '',
                    log.user_agent[:100] + '...' if len(log.user_agent or '') > 100 else log.user_agent or '',
                    log.url_acces or '',
                    log.methode_http or '',
                    log.statut_reponse or '',
                    'Oui' if log.succes else 'Non',
                    log.duree_formatee if hasattr(log, 'duree_formatee') else '',
                    log.session_key[:10] + '...' if log.session_key else ''
                ])
            
            # Journaliser l'export
            JournalAudit.objects.create(
                utilisateur=request.user,
                action="Export journal audit",
                details=f"Export de {logs.count()} entrées sur {days} jours",
                adresse_ip=request.META.get('REMOTE_ADDR'),
                url_acces=request.path,
                methode_http=request.method,
                succes=True
            )
            
            messages.success(request, f'✅ Export généré: {logs.count()} entrées sur {days} jours.')
            return response
            
        except Exception as e:
            logger.error(f'Erreur export audit: {str(e)}')
            messages.error(request, f'❌ Erreur lors de l\'export: {str(e)}')
            return redirect('admin:index')

    @method_decorator(login_required)
    def ping_view(self, request):
        """Vue de monitoring pour vérifier la santé du système"""
        try:
            # Test basique de la base de données
            UtilisateurSUPPER.objects.count()
            
            return JsonResponse({
                'status': 'ok',
                'timestamp': timezone.now().isoformat(),
                'version': '2.0',
                'database': 'connected'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'error': str(e),
                'timestamp': timezone.now().isoformat()
            }, status=500)


# Création de l'instance du site admin personnalisé
admin_site = SupperAdminSite(name='supper_admin')


@admin.register(UtilisateurSUPPER, site=admin_site)
class UtilisateurSUPPERAdmin(UserAdmin):
    """Administration des utilisateurs SUPPER - CORRIGÉE"""
    
    model = UtilisateurSUPPER
    
    # CORRIGÉ: Utilisation des bons noms de champs du modèle
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
            'fields': ('nom_complet', 'telephone', 'email'),
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
        ('Contrôle d\'affichage', {
            'fields': ('voir_recettes_potentielles', 'voir_taux_deperdition', 
                      'voir_statistiques_globales', 'peut_saisir_pour_autres_postes'),
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
            'fields': ('cree_par', 'date_creation', 'date_modification'),
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
        count = queryset.count()
        self.message_user(request, f'Notification envoyée à {count} utilisateurs.')
    send_notification.short_description = 'Envoyer une notification'
    
    def export_users(self, request, queryset):
        """Export CSV des utilisateurs"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="utilisateurs_supper.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Matricule', 'Nom complet', 'Téléphone', 'Email', 'Habilitation', 'Poste', 'Actif'])
        
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
    """Administration des postes - GARDÉ is_active et type"""
    
    list_display = ('nom', 'code', 'type_badge', 'region_badge', 'is_active_badge', 'date_creation')
    list_filter = ('type', 'region', 'is_active', 'date_creation')
    search_fields = ('nom', 'code', 'region', 'departement')
    ordering = ('region', 'nom')
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('nom', 'code', 'type'),
            'classes': ('wide',),
        }),
        ('Localisation', {
            'fields': ('region', 'departement', 'axe_routier'),
            'classes': ('wide',),
        }),
        ('Coordonnées GPS', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',),
        }),
        ('Informations complémentaires', {
            'fields': ('description', 'is_active'),
            'classes': ('wide',),
        }),
        ('Métadonnées', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',),
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
            obj.region
        )
    region_badge.short_description = 'Région'
    
    def is_active_badge(self, obj):
        """Badge pour le statut actif"""
        if obj.is_active:
            return format_html('<span class="badge bg-success">Actif</span>')
        return format_html('<span class="badge bg-danger">Inactif</span>')
    is_active_badge.short_description = 'Statut'


@admin.register(JournalAudit, site=admin_site)
class JournalAuditAdmin(admin.ModelAdmin):
    """Administration du journal d'audit - CORRIGÉE"""
    
    list_display = ('timestamp', 'utilisateur', 'action', 'succes_badge', 'adresse_ip', 'duree_formatee_display')
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
    
    def duree_formatee_display(self, obj):
        """Affichage de la durée formatée"""
        return obj.duree_formatee if hasattr(obj, 'duree_formatee') else ''
    duree_formatee_display.short_description = 'Durée'


@admin.register(NotificationUtilisateur, site=admin_site)
class NotificationUtilisateurAdmin(admin.ModelAdmin):
    """Administration des notifications - CORRIGÉE"""
    
    list_display = ('titre', 'destinataire', 'type_badge', 'lu_badge', 'date_creation')
    list_filter = ('type_notification', 'lu', 'date_creation')
    search_fields = ('titre', 'message', 'destinataire__username')
    ordering = ('-date_creation',)
    
    def type_badge(self, obj):
        """Badge pour le type de notification"""
        colors = {
            'info': 'info',
            'succes': 'success',
            'avertissement': 'warning',
            'erreur': 'danger',
        }
        color = colors.get(obj.type_notification, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.get_type_notification_display()
        )
    type_badge.short_description = 'Type'
    
    def lu_badge(self, obj):
        """Badge pour le statut lu"""
        if obj.lu:
            return format_html('<span class="badge bg-success">Lue</span>')
        return format_html('<span class="badge bg-warning">Non lue</span>')
    lu_badge.short_description = 'Statut'


# CORRECTION FINALE: Gestion sécurisée de la désinscription du modèle Group
try:
    # Essayer de désinscrire Group seulement s'il est enregistré
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    # Si Group n'est pas enregistré, ignorer l'erreur
    pass

# Utiliser notre site admin personnalisé comme site par défaut
admin.site = admin_site

# AJOUT: Export pour l'import depuis d'autres fichiers
__all__ = ['admin_site', 'SupperAdminSite']