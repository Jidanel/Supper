# ===================================================================
# Fichier : common/urls.py - URLs module commun COMPLET
# Chemin : Supper/common/urls.py
# Routes dashboards, gestion jours, audit, notifications
# ===================================================================

from django.urls import path
from . import views

# Nom de l'application pour les namespaces URL
app_name = 'common'

urlpatterns = [
    # ===================================================================
    # DASHBOARDS SELON LES RÔLES
    # ===================================================================
    
    # Dashboard général - point d'entrée principal
    path('', views.DashboardGeneralView.as_view(), name='dashboard_general'),
    
    # Dashboard administrateur principal avec toutes les statistiques
    path('admin/', views.DashboardAdminView.as_view(), name='dashboard_admin'),
    
    # Dashboard chef de poste pour la gestion du poste assigné
    path('chef/', views.DashboardChefView.as_view(), name='dashboard_chef'),
    
    # Dashboard agent inventaire pour la saisie simplifiée
    path('agent/', views.DashboardAgentView.as_view(), name='dashboard_agent'),
    
    # ===================================================================
    # GESTION DES JOURS (ADMIN UNIQUEMENT)
    # ===================================================================
    
    # Liste des configurations de jours avec historique et filtres
    #path('jours/', views.JourConfigurationListView.as_view(), name='jour_list'),
    
    # Ouverture d'un jour pour saisie d'inventaire
    #path('jours/ouvrir/', views.OuvrirJourView.as_view(), name='ouvrir_jour'),
    
    # Fermeture d'un jour - verrouillage des saisies
   # path('jours/fermer/', views.FermerJourView.as_view(), name='fermer_jour'),
    
    # Marquage d'une journée comme impertinente
    #path('jours/impertinent/', views.MarquerImpertinentView.as_view(), name='marquer_impertinent'),
    
    # ===================================================================
    # JOURNAL D'AUDIT (ADMIN UNIQUEMENT)
    # ===================================================================
    
    # Consultation du journal d'audit complet avec filtres avancés
    #path('audit/', views.AuditLogView.as_view(), name='audit_log'),
    
    # Détail d'une entrée d'audit spécifique avec contexte
    #path('audit/<int:pk>/', views.AuditDetailView.as_view(), name='audit_detail'),
    
    # Export du journal d'audit en CSV/Excel
    #path('audit/export/', views.AuditExportView.as_view(), name='audit_export'),
    
    # ===================================================================
    # NOTIFICATIONS SYSTÈME
    # ===================================================================
    
    # Liste des notifications de l'utilisateur connecté
    #path('notifications/', views.NotificationsView.as_view(), name='notifications'),
    
    # Marquage d'une notification comme lue (support AJAX)
    #path('notifications/<int:pk>/lue/', views.MarquerNotificationLue.as_view(), name='notification_lue'),
    
    # ===================================================================
    # GESTION INVENTAIRES (ADMIN) - NOUVELLES ROUTES
    # ===================================================================
    
    # Liste admin de TOUS les inventaires (tous agents, tous postes)
    #path('admin/inventaires/', views.AdminInventaireListView.as_view(), name='admin_inventaire_list'),
    
    # Liste admin de TOUTES les recettes avec calculs complets
   # path('admin/recettes/', views.AdminRecetteListView.as_view(), name='admin_recette_list'),
    
    # Saisie inventaire par admin (tous postes)
    #path('admin/inventaires/saisie/', views.AdminInventaireSaisieView.as_view(), name='admin_inventaire_saisie'),
    
    # Saisie recette par admin (tous postes)
    #path('admin/recettes/saisie/', views.AdminRecetteSaisieView.as_view(), name='admin_recette_saisie'),
    
    # ===================================================================
    # API ENDPOINTS POUR AJAX ET TEMPS RÉEL
    # ===================================================================
    
    # API statistiques pour les graphiques dynamiques
    #path('api/stats/', views.StatsAPIView.as_view(), name='api_stats'),
    
    # API notifications en temps réel pour le badge de notification
   # path('api/notifications/', views.NotificationsAPIView.as_view(), name='api_notifications'),
    
    # API statut du système pour monitoring et healthcheck
   # path('api/status/', views.SystemStatusAPIView.as_view(), name='api_status'),
    
    # API recherche globale dans l'application
   # path('api/search/', views.GlobalSearchAPIView.as_view(), name='api_search'),
    
    # API graphiques déperdition pour admin (NOUVELLE)
   # path('api/deperdition/', views.DeperditionChartAPIView.as_view(), name='api_deperdition'),
    
    # ===================================================================
    # UTILITAIRES SYSTÈME
    # ===================================================================
    
    # Changement de langue FR/EN avec redirection intelligente
    #path('langue/<str:language_code>/', views.ChangeLanguageView.as_view(), name='change_language'),
    
    # Page d'aide contextuelle selon le rôle utilisateur
   # path('aide/', views.HelpView.as_view(), name='help'),
    
    # Rapport de santé du système (admin uniquement)
   # path('health/', views.SystemHealthView.as_view(), name='system_health'),
    
    # Vue de maintenance système (futures fonctionnalités)
   # path('maintenance/', views.MaintenanceView.as_view(), name='maintenance'),
    # Actions admin
    #path('ouvrir-jour/', views.ouvrir_jour_saisie, name='ouvrir_jour'),
    #path('rapport-hebdomadaire/', views.generer_rapport_hebdomadaire, name='rapport_hebdo'),

    # APIs Graphiques Admin
    path('api/graphique-hebdomadaire/', views.api_graphique_hebdomadaire, name='api_graphique_hebdo'),
    path('api/graphique-mensuel/', views.api_graphique_mensuel, name='api_graphique_mensuel'),
    path('api/statistiques-postes/', views.api_statistiques_postes_ordonnes, name='api_stats_postes'),
    # ===================================================================
]