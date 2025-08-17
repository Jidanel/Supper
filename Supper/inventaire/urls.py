# ===================================================================
# inventaire/urls.py - URLs COMPLÈTES pour base_site.html
# SOLUTION PROBLÈME 1 : Toutes les URLs référencées dans base_site.html
# ===================================================================

from django.urls import path
from . import views

app_name = 'inventaire'

urlpatterns = [
    # ================================================================
    # URLS PRINCIPALES INVENTAIRE
    # ================================================================
    path('', views.InventaireListView.as_view(), name='inventaire_list'),
    path('<int:pk>/', views.InventaireDetailView.as_view(), name='inventaire_detail'),
    path('saisie/', views.SaisieInventaireView.as_view(), name='saisie_inventaire'),
    path('saisie/<int:poste_id>/<str:date>/', views.SaisieInventaireView.as_view(), name='saisie_inventaire_detail'),
    
    # ================================================================
    # URLS RÉFÉRENCÉES DANS BASE_SITE.HTML - MENU INVENTAIRES
    # ================================================================
    # URL : {% url 'admin:inventaire_inventairejournalier_add' %}
    path('admin/add/', views.redirect_to_add_inventaire_admin, name='add_inventaire_admin'),
    
    # URL : {% url 'admin:inventaire_inventairejournalier_changelist' %}
    path('admin/list/', views.redirect_to_inventaires_admin, name='inventaires_admin'),
    
    # URL : /admin/tools/saisie-inventaire/ (référencé dans base_site.html ligne 98)
    path('tools/saisie-inventaire/', views.SaisieInventaireView.as_view(), name='tools_saisie'),

    
    # ================================================================
    # URLS RÉFÉRENCÉES DANS BASE_SITE.HTML - MENU RECETTES
    # ================================================================
    # URL : {% url 'admin:inventaire_recettejournaliere_add' %}
    path('recettes/admin/add/', views.redirect_to_add_recette_admin, name='add_recette_admin'),
    
    # URL : {% url 'admin:inventaire_recettejournaliere_changelist' %}
    path('recettes/admin/list/', views.redirect_to_recettes_admin, name='recettes_admin'),
    
    # ================================================================
    # URLS RÉFÉRENCÉES DANS BASE_SITE.HTML - MENU PLANIFICATION
    # ================================================================
    # URL : {% url 'admin:inventaire_inventairemensuel_add' %} (ligne 113)
    path('mensuel/add/', views.redirect_to_add_inventaire_admin, name='add_inventaire_mensuel'),
    
    # URL : {% url 'admin:inventaire_inventairemensuel_changelist' %} (ligne 116)
    path('mensuel/list/', views.redirect_to_inventaires_admin, name='list_inventaire_mensuel'),
    
    # URL : {% url 'admin:inventaire_configurationjour_changelist' %} (ligne 124)
    path('config-jours/', views.redirect_to_config_jours_admin, name='config_jours'),
    
    # URL : {% url 'admin:inventaire_configurationjour_add' %} (ligne 127)
    path('config-jours/add/', views.redirect_to_add_config_jour_admin, name='add_config_jour'),
    
    # ================================================================
    # GESTION DES JOURS ET INVENTAIRES MENSUELS
    # ================================================================
    path('config-jours/list/', views.ConfigurationJourListView.as_view(), name='config_jour_list'),
    path('mensuel/<int:inventaire_id>/gerer-jours/', views.gerer_jours_inventaire, name='gerer_jours'),
    
    # ================================================================
    # ASSOCIATIONS POSTES-INVENTAIRES-AGENTS
    # ================================================================
    path('postes/', views.liste_postes_inventaires, name='liste_postes_inventaires'),
    path('postes/<int:poste_id>/', views.detail_poste_inventaires, name='detail_poste_inventaires'),
    path('postes/<int:poste_id>/changer-agent/', views.changer_agent_poste, name='changer_agent_poste'),
    
    # ================================================================
    # ACTIONS ET VERROUILLAGE
    # ================================================================
    path('<int:pk>/lock/', views.InventaireVerrouillerView.as_view(), name='lock_inventaire'),
    path('<int:pk>/validate/', views.InventaireValiderView.as_view(), name='validate_inventaire'),
    
    # ================================================================
    # API ENDPOINTS
    # ================================================================
    path('api/calcul-automatique/', views.CalculAutomatiqueAPIView.as_view(), name='api_calcul_automatique'),
    path('api/verification-jour/', views.VerificationJourAPIView.as_view(), name='api_verification_jour'),
    path('api/inventaire-stats/', views.inventaire_stats_api, name='api_inventaire_stats'),
    path('api/recette-stats/', views.recette_stats_api, name='api_recette_stats'),
    path('api/check-day-status/', views.check_day_status_api, name='api_check_day_status'),
    path('api/quick-action/', views.quick_action_api, name='api_quick_action'),
    
    # ================================================================
    # RAPPORTS ET EXPORTS
    # ================================================================
    path('rapports/', views.RapportInventaireView.as_view(), name='rapport_generation'),
    path('backup/', views.backup_inventaires_api, name='backup_inventaires'),
    path('diagnostic/', views.diagnostic_inventaires_view, name='diagnostic'),
    
    # ================================================================
    # DASHBOARD ET WIDGETS
    # ================================================================
    path('dashboard/widget/', views.inventaire_dashboard_widget, name='dashboard_widget'),
    path('admin/help/', views.inventaire_admin_help_view, name='admin_help'),
    
    # ================================================================
    # GESTION DES ERREURS
    # ================================================================
    path('error/<str:error_type>/', views.inventaire_redirect_error_handler, name='error_handler'),
]