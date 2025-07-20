# ===================================================================
# common/views.py - Vues des dashboards
# ===================================================================

from django.shortcuts import render, redirect
from django.views.generic import TemplateView, ListView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils import timezone
from datetime import date, timedelta
from django.db.models import Sum, Count, Q, Avg
from .mixins import AdminRequiredMixin, AuditMixin
from accounts.models import UtilisateurSUPPER, JournalAudit, Poste
from inventaire.models import (
    InventaireJournalier, RecetteJournaliere, 
    ConfigurationJour, StatutJour
)


class GeneralDashboardView(LoginRequiredMixin, AuditMixin, TemplateView):
    """Dashboard général - accessible à tous les utilisateurs connectés"""
    
    template_name = 'common/dashboard_general.html'
    audit_action = "Accès dashboard général"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context.update({
            'user': user,
            'permissions': user.get_permissions_list(),
            'poste_affectation': user.poste_affectation,
            'notifications_non_lues': self.get_notifications_count(user),
        })
        
        return context
    
    def get_notifications_count(self, user):
        """Compte les notifications non lues"""
        try:
            from accounts.models import NotificationUtilisateur
            return NotificationUtilisateur.objects.filter(
                destinataire=user,
                lue=False
            ).count()
        except:
            return 0


class AdminDashboardView(LoginRequiredMixin, AdminRequiredMixin, AuditMixin, TemplateView):
    """Dashboard administrateur avec statistiques complètes"""
    
    template_name = 'common/dashboard_admin.html'
    audit_action = "Accès dashboard administrateur"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Statistiques générales
        stats = self.get_general_stats()
        context.update(stats)
        
        # Activité récente
        context['recent_logs'] = self.get_recent_activity()
        
        # Jours ouverts/fermés
        context['jours_ouverts'] = self.get_jours_status()
        
        # Alertes
        context['alertes'] = self.get_alertes()
        
        return context
    
    def get_general_stats(self):
        """Statistiques générales du système"""
        today = date.today()
        week_ago = today - timedelta(days=7)
        
        return {
            'total_users': UtilisateurSUPPER.objects.count(),
            'active_users': UtilisateurSUPPER.objects.filter(is_active=True).count(),
            'total_postes': Poste.objects.count(),
            'active_postes': Poste.objects.filter(actif=True).count(),
            'inventaires_today': InventaireJournalier.objects.filter(date=today).count(),
            'inventaires_week': InventaireJournalier.objects.filter(date__gte=week_ago).count(),
            'recettes_today': RecetteJournaliere.objects.filter(date=today).count(),
        }
    
    def get_recent_activity(self):
        """Activité récente du système"""
        return JournalAudit.objects.select_related('utilisateur').order_by('-timestamp')[:10]
    
    def get_jours_status(self):
        """Statut des jours récents"""
        today = date.today()
        days = []
        
        for i in range(7):  # 7 derniers jours
            day = today - timedelta(days=i)
            try:
                config = ConfigurationJour.objects.get(date=day)
                status = config.get_statut_display()
                css_class = {
                    'ouvert': 'success',
                    'ferme': 'secondary',
                    'impertinent': 'warning'
                }.get(config.statut, 'secondary')
            except ConfigurationJour.DoesNotExist:
                status = 'Non configuré'
                css_class = 'secondary'
            
            days.append({
                'date': day,
                'status': status,
                'css_class': css_class
            })
        
        return days
    
    def get_alertes(self):
        """Alertes système importantes"""
        alertes = []
        
        # Vérifier les recettes avec déperdition élevée (derniers 7 jours)
        week_ago = date.today() - timedelta(days=7)
        recettes_alertes = RecetteJournaliere.objects.filter(
            date__gte=week_ago,
            taux_deperdition__lt=-30  # Seuil rouge
        ).count()
        
        if recettes_alertes > 0:
            alertes.append({
                'type': 'danger',
                'message': f"{recettes_alertes} recette(s) avec déperdition critique cette semaine"
            })
        
        # Vérifier les inventaires non verrouillés (plus de 2 jours)
        old_date = date.today() - timedelta(days=2)
        inventaires_ouverts = InventaireJournalier.objects.filter(
            date__lt=old_date,
            verrouille=False
        ).count()
        
        if inventaires_ouverts > 0:
            alertes.append({
                'type': 'warning',
                'message': f"{inventaires_ouverts} inventaire(s) ancien(s) non verrouillé(s)"
            })
        
        return alertes


class ChefDashboardView(LoginRequiredMixin, AuditMixin, TemplateView):
    """Dashboard pour les chefs de poste"""
    
    template_name = 'common/dashboard_chef.html'
    audit_action = "Accès dashboard chef de poste"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Statistiques du poste de l'utilisateur
        if user.poste_affectation:
            context.update(self.get_poste_stats(user.poste_affectation))
        
        context['can_saisir_recette'] = user.peut_saisir_peage or user.peut_saisir_pesage
        
        return context
    
    def get_poste_stats(self, poste):
        """Statistiques du poste"""
        today = date.today()
        month_start = today.replace(day=1)
        
        # Inventaires du mois
        inventaires_mois = InventaireJournalier.objects.filter(
            poste=poste,
            date__gte=month_start
        )
        
        # Recettes du mois
        recettes_mois = RecetteJournaliere.objects.filter(
            poste=poste,
            date__gte=month_start
        )
        
        return {
            'poste': poste,
            'inventaires_mois': inventaires_mois.count(),
            'recettes_mois': recettes_mois.count(),
            'total_recettes_mois': recettes_mois.aggregate(
                total=Sum('montant_declare')
            )['total'] or 0,
            'inventaire_today': inventaires_mois.filter(date=today).first(),
            'recette_today': recettes_mois.filter(date=today).first(),
        }


class AgentDashboardView(LoginRequiredMixin, AuditMixin, TemplateView):
    """Dashboard pour les agents d'inventaire"""
    
    template_name = 'common/dashboard_agent.html'
    audit_action = "Accès dashboard agent inventaire"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Vérifier si le jour actuel est ouvert pour saisie
        today = date.today()
        jour_ouvert = ConfigurationJour.est_jour_ouvert(today)
        
        context.update({
            'jour_ouvert': jour_ouvert,
            'date_today': today,
            'poste_affectation': user.poste_affectation,
        })
        
        # Mes inventaires récents
        if user.poste_affectation:
            context['mes_inventaires'] = InventaireJournalier.objects.filter(
                poste=user.poste_affectation,
                agent_saisie=user
            ).order_by('-date')[:5]
        
        return context


class JourConfigurationListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """Liste des configurations de jours"""
    
    model = ConfigurationJour
    template_name = 'common/jour_list.html'
    context_object_name = 'jours'
    paginate_by = 30
    
    def get_queryset(self):
        return ConfigurationJour.objects.order_by('-date')


class AuditLogView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """Journal d'audit pour les administrateurs"""
    
    model = JournalAudit
    template_name = 'common/audit_log.html'
    context_object_name = 'logs'
    paginate_by = 50
    
    def get_queryset(self):
        return JournalAudit.objects.select_related('utilisateur').order_by('-timestamp')


# ===================================================================
# API Views pour AJAX
# ===================================================================

class StatsAPIView(LoginRequiredMixin, AdminRequiredMixin, View):
    """API pour les statistiques en temps réel"""
    
    def get(self, request):
        stats_type = request.GET.get('type', 'general')
        
        if stats_type == 'activite':
            # Activité des 24 dernières heures
            yesterday = timezone.now() - timedelta(hours=24)
            activite = JournalAudit.objects.filter(
                timestamp__gte=yesterday
            ).extra(
                select={'hour': 'EXTRACT(hour FROM timestamp)'}
            ).values('hour').annotate(
                count=Count('id')
            ).order_by('hour')
            
            return JsonResponse({
                'labels': [f"{item['hour']}h" for item in activite],
                'data': [item['count'] for item in activite]
            })
        
        elif stats_type == 'deperdition':
            # Taux de déperdition des 7 derniers jours
            week_ago = date.today() - timedelta(days=7)
            recettes = RecetteJournaliere.objects.filter(
                date__gte=week_ago
            ).values('date').annotate(
                taux_moyen=Avg('taux_deperdition')
            ).order_by('date')
            
            return JsonResponse({
                'labels': [item['date'].strftime('%d/%m') for item in recettes],
                'data': [float(item['taux_moyen'] or 0) for item in recettes]
            })
        
        return JsonResponse({'error': 'Type de statistiques non reconnu'}, status=400)


class NotificationsAPIView(LoginRequiredMixin, View):
    """API pour les notifications utilisateur"""
    
    def get(self, request):
        try:
            from accounts.models import NotificationUtilisateur
            notifications = NotificationUtilisateur.objects.filter(
                destinataire=request.user,
                lue=False
            ).order_by('-date_creation')[:5]
            
            data = [{
                'id': notif.id,
                'titre': notif.titre,
                'message': notif.message,
                'type': notif.type_notification,
                'date': notif.date_creation.strftime('%d/%m/%Y %H:%M')
            } for notif in notifications]
            
            return JsonResponse({'notifications': data})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def post(self, request):
        # Marquer une notification comme lue
        try:
            from accounts.models import NotificationUtilisateur
            notif_id = request.POST.get('id')
            notification = NotificationUtilisateur.objects.get(
                id=notif_id,
                destinataire=request.user
            )
            notification.marquer_comme_lue()
            
            return JsonResponse({'success': True})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
# AJOUTER à la fin de votre common/views.py existant :

class OuvrirJourView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Vue pour ouvrir un jour pour saisie"""
    template_name = 'common/ouvrir_jour.html'

class FermerJourView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Vue pour fermer un jour"""
    template_name = 'common/fermer_jour.html'

class MarquerImpertinentView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Vue pour marquer une journée comme impertinente"""
    template_name = 'common/marquer_impertinent.html'

class AuditDetailView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Détail d'une entrée d'audit"""
    template_name = 'common/audit_detail.html'

class AuditExportView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Export du journal d'audit"""
    template_name = 'common/audit_export.html'

class NotificationsView(LoginRequiredMixin, TemplateView):
    """Liste des notifications utilisateur"""
    template_name = 'common/notifications.html'

class MarquerNotificationLue(LoginRequiredMixin, View):
    """Marquer une notification comme lue"""
    def post(self, request, pk):
        # Implementation à venir
        return JsonResponse({'success': True})

class SystemStatusAPIView(LoginRequiredMixin, AdminRequiredMixin, View):
    """API statut système"""
    def get(self, request):
        return JsonResponse({'status': 'ok'})

class GlobalSearchAPIView(LoginRequiredMixin, View):
    """API recherche globale"""
    def get(self, request):
        return JsonResponse({'results': []})

class ChangeLanguageView(LoginRequiredMixin, View):
    """Changement de langue"""
    def get(self, request, language_code):
        # Implementation à venir
        return redirect('common:dashboard_general')

class HelpView(LoginRequiredMixin, TemplateView):
    """Page d'aide"""
    template_name = 'common/help.html'

class SystemHealthView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Santé du système"""
    template_name = 'common/system_health.html'