# ===================================================================
# common/urls.py - URLs pour les dashboards et fonctions communes
# Chaque URL est commentée pour expliquer son rôle
# Structure bilingue prête pour FR/EN
# ===================================================================

from django.urls import path
from . import views

# Nom de l'application pour les namespaces URL
app_name = 'common'

urlpatterns = [
    # ===================================================================
    # DASHBOARDS SELON LES RÔLES
    # ===================================================================
    
    # Dashboard général - accessible à tous les utilisateurs connectés
    # Affiche les informations de base et redirige selon les permissions
    path('', views.GeneralDashboardView.as_view(), name='dashboard_general'),
    
    # Dashboard administrateur principal - accès complet au système
    # Statistiques globales, gestion utilisateurs, configuration système
    path('admin/', views.AdminDashboardView.as_view(), name='dashboard_admin'),
    
    # Dashboard chef de poste - gestion du poste assigné
    # Saisie recettes, consultation inventaires, statistiques du poste
    path('chef/', views.ChefDashboardView.as_view(), name='dashboard_chef'),
    
    # Dashboard agent inventaire - saisie quotidienne simplifiée
    # Interface épurée pour la saisie d'inventaire uniquement
    path('agent/', views.AgentDashboardView.as_view(), name='dashboard_agent'),
    
    # ===================================================================
    # GESTION DES JOURS (ADMIN UNIQUEMENT)
    # ===================================================================
    
    # Liste des configurations de jours - consultation historique
    # Permet de voir les jours ouverts/fermés/impertinents
    path('jours/', views.JourConfigurationListView.as_view(), name='jour_list'),
    
    # Ouverture d'un jour pour saisie - action administrative
    # Formulaire pour activer la saisie d'inventaire pour une date
    path('jours/ouvrir/', views.OuvrirJourView.as_view(), name='ouvrir_jour'),
    
    # Fermeture d'un jour - verrouillage des saisies
    # Empêche toute nouvelle saisie pour la date spécifiée
    path('jours/fermer/', views.FermerJourView.as_view(), name='fermer_jour'),
    
    # Marquage journée impertinente - cas particulier
    # Utilisé quand recette déclarée > recette potentielle
    path('jours/impertinent/', views.MarquerImpertinentView.as_view(), name='marquer_impertinent'),
    
    # ===================================================================
    # JOURNAL D'AUDIT (ADMIN UNIQUEMENT)
    # ===================================================================
    
    # Consultation du journal d'audit complet
    # Historique de toutes les actions utilisateur avec filtres
    path('audit/', views.AuditLogView.as_view(), name='audit_log'),
    
    # Détail d'une entrée d'audit spécifique
    # Affichage détaillé d'une action avec contexte complet
    path('audit/<int:pk>/', views.AuditDetailView.as_view(), name='audit_detail'),
    
    # Export du journal d'audit en CSV/Excel
    # Permet la sauvegarde externe des logs pour archivage
    path('audit/export/', views.AuditExportView.as_view(), name='audit_export'),
    
    # ===================================================================
    # NOTIFICATIONS SYSTÈME
    # ===================================================================
    
    # Liste des notifications de l'utilisateur connecté
    # Messages système, alertes, informations importantes
    path('notifications/', views.NotificationsView.as_view(), name='notifications'),
    
    # Marquage d'une notification comme lue
    # Action AJAX pour mettre à jour le statut de lecture
    path('notifications/<int:pk>/lue/', views.MarquerNotificationLue.as_view(), name='notification_lue'),
    
    # ===================================================================
    # API ENDPOINTS POUR AJAX
    # ===================================================================
    
    # API statistiques en temps réel pour les graphiques
    # Données JSON pour les tableaux de bord dynamiques
    path('api/stats/', views.StatsAPIView.as_view(), name='api_stats'),
    
    # API notifications non lues - compteur temps réel
    # Utilisé pour mettre à jour le badge de notifications
    path('api/notifications/', views.NotificationsAPIView.as_view(), name='api_notifications'),
    
    # API statut du système - vérification santé
    # Endpoint pour monitoring de l'état de l'application
    path('api/status/', views.SystemStatusAPIView.as_view(), name='api_status'),
    
    # API recherche globale - fonctionnalité de recherche
    # Recherche dans utilisateurs, postes, inventaires, etc.
    path('api/search/', views.GlobalSearchAPIView.as_view(), name='api_search'),
    
    # ===================================================================
    # UTILITAIRES SYSTÈME
    # ===================================================================
    
    # Changement de langue FR/EN
    # Bascule entre français et anglais avec redirection
    path('langue/<str:language_code>/', views.ChangeLanguageView.as_view(), name='change_language'),
    
    # Page d'aide contextuelle selon le rôle
    # Documentation spécifique à chaque type d'utilisateur
    path('aide/', views.HelpView.as_view(), name='help'),
    
    # Rapport de santé du système (admin uniquement)
    # Vérifications techniques, performance, état des services
    path('health/', views.SystemHealthView.as_view(), name='system_health'),
]