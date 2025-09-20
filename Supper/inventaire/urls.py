# inventaire/urls.py - URLs corrigées avec programmation inventaires

from django.urls import path
from . import views
from .views_stats import *

app_name = 'inventaire'

urlpatterns = [
    # ================================================================
    # URLS PRINCIPALES INVENTAIRE
    # ================================================================
    path('', views.InventaireListView.as_view(), name='inventaire_list'),
    path('<int:pk>/', views.InventaireDetailView.as_view(), name='inventaire_detail'),
    #path('saisie/<int:poste_id>/', views.SaisieInventaireView.as_view(), name='saisie_inventaire_poste'),
    path('inventaire/supprimer/<int:poste_id>/', views.supprimer_inventaire, name='supprimer_inventaire_poste'),
    # Ajouter ces lignes dans inventaire/urls.py
    path('saisie/', views.selection_date_inventaire, name='saisie_inventaire'),  # Redirige vers sélection
    path('saisie/<int:poste_id>/', views.selection_date_inventaire, name='saisie_inventaire_poste'),  # Redirige vers sélection
    path('saisie/<int:poste_id>/<str:date_str>/', views.SaisieInventaireView.as_view(), name='saisie_inventaire_avec_date'),  # Saisie réelle
    
    # ================================================================
    # PROGRAMMATION INVENTAIRES (NOUVELLES)
    # ================================================================
    path('programmer/', views.programmer_inventaire, name='programmer_inventaire'),
    path('programmations/', views.liste_programmations, name='liste_programmations'),
    path('programmation/<int:poste_id>/<str:mois>/', views.detail_programmation, name='detail_programmation'),
    # API pour les postes par motif
    path('api/postes-par-motif/', 
         views.api_get_postes_par_motif, 
         name='api_get_postes_par_motif'),
    
    # Actions sur les programmations
    path('programmation/<int:poste_id>/<str:mois>/<str:motif>/desactiver/', 
         views.desactiver_programmation, 
         name='desactiver_programmation'),
    
    path('programmation/<int:poste_id>/<str:mois>/<str:motif>/supprimer/', 
         views.supprimer_programmation, 
         name='supprimer_programmation'),
     path('programmations/desactivees/', views.programmations_desactivees, name='programmations_desactivees'),

    # ================================================================
    # SAISIE RECETTES
    # ================================================================
    path('recettes/saisie/', views.saisir_recette, name='saisie_recette'),
    path('recettes/saisie/<int:poste_id>/', views.saisir_recette, name='saisie_recette_poste'),
    path('recettes/supprimer/<int:poste_id>/', views.supprimer_recette, name='supprimer_recette_poste'),
    path('recettes/', views.RecetteListView.as_view(), name='liste_recettes'),
    path('recettes/<int:pk>/', views.RecetteDetailView.as_view(), name='recette_detail'),
    path('recettes/<int:pk>/modifier/', views.modifier_recette, name='modifier_recette'),

    
    # ================================================================
    # MODIFICATIONS ADMIN
    # ================================================================
    path('admin/<int:inventaire_id>/modifier/', views.modifier_inventaire, name='modifier_inventaire_admin'),
    path('recettes/admin/<int:recette_id>/modifier/', views.modifier_recette, name='modifier_recette_admin'),
    
    # ================================================================
    # CONSOLIDATION MENSUELLE
    # ================================================================
     path('mensuel/', views.liste_inventaires_mensuels, name='liste_inventaires_mensuels'),
     path('mensuel/<int:pk>/', views.detail_inventaire_mensuel, name='detail_inventaire_mensuel'),
     path('mensuel/consolider/', views.consolider_inventaire_mensuel, name='consolider_inventaire_mensuel'),
     path('statistiques/taux/', statistiques_taux_deperdition, name='statistiques_taux'),
     path('statistiques/recettes/', statistiques_recettes, name='statistiques_recettes'),
    
    # ================================================================
    # API ENDPOINTS
    # ================================================================
    path('api/calcul-automatique/', views.CalculAutomatiqueAPIView.as_view(), name='api_calcul_automatique'),
    path('api/inventaire-stats/', views.inventaire_stats_api, name='api_inventaire_stats'),
    path('api/recette-stats/', views.recette_stats_api, name='api_recette_stats'),
    path('api/check-day-status/', views.check_day_status_api, name='api_check_day_status'),
    path('api/quick-action/', views.quick_action_api, name='api_quick_action'),
   # path('api/notifications/', views.api_notifications, name='api_notifications'),
    path('api/month-data/', views.api_month_data, name='api_month_data'),
    
    # ================================================================
    # RAPPORTS ET EXPORTS
    # ================================================================
    path('rapports/', views.RapportInventaireView.as_view(), name='rapport_generation'),
    path('backup/', views.backup_inventaires_api, name='backup_inventaires'),
    
    # ================================================================
    # DASHBOARD ET WIDGETS
    # ================================================================
    path('dashboard/widget/', views.inventaire_dashboard_widget, name='dashboard_widget'),
    
    # ================================================================
    # REDIRECTIONS ADMIN DJANGO
    # ================================================================
    path('admin/inventaires/', views.redirect_to_inventaires_admin, name='inventaires_admin'),
    path('admin/recettes/', views.redirect_to_recettes_admin, name='recettes_admin'),
    path('admin/statistiques/', views.redirect_to_statistiques_admin, name='statistiques_admin'),
]
# # ===================================================================
# # inventaire/urls.py - URLs COMPLÈTES pour base_site.html
# # SOLUTION PROBLÈME 1 : Toutes les URLs référencées dans base_site.html
# # ===================================================================

# from django.urls import path
# from . import views

# app_name = 'inventaire'

# urlpatterns = [
#     # ================================================================
#     # URLS PRINCIPALES INVENTAIRE
#     # ================================================================
#     path('', views.InventaireListView.as_view(), name='inventaire_list'),
#     path('<int:pk>/', views.InventaireDetailView.as_view(), name='inventaire_detail'),
#     path('saisie/', views.SaisieInventaireView.as_view(), name='saisie_inventaire'),
#     path('saisie/<int:poste_id>/<str:date>/', views.SaisieInventaireView.as_view(), name='saisie_inventaire_detail'),
    
#     # ================================================================
#     # URLS RÉFÉRENCÉES DANS BASE_SITE.HTML - MENU INVENTAIRES
#     # ================================================================
#     # URL : {% url 'admin:inventaire_inventairejournalier_add' %}
#     path('admin/add/', views.redirect_to_add_inventaire_admin, name='add_inventaire_admin'),
    
#     # URL : {% url 'admin:inventaire_inventairejournalier_changelist' %}
#     path('admin/list/', views.redirect_to_inventaires_admin, name='inventaires_admin'),
    
#     # URL : /admin/tools/saisie-inventaire/ (référencé dans base_site.html ligne 98)
#     path('tools/saisie-inventaire/', views.SaisieInventaireView.as_view(), name='tools_saisie'),

    
#     # ================================================================
#     # URLS RÉFÉRENCÉES DANS BASE_SITE.HTML - MENU RECETTES
#     # ================================================================
#     # URL : {% url 'admin:inventaire_recettejournaliere_add' %}
#     path('recettes/admin/add/', views.redirect_to_add_recette_admin, name='add_recette_admin'),
    
#     # URL : {% url 'admin:inventaire_recettejournaliere_changelist' %}
#     path('recettes/admin/list/', views.redirect_to_recettes_admin, name='recettes_admin'),
    
#     # ================================================================
#     # URLS RÉFÉRENCÉES DANS BASE_SITE.HTML - MENU PLANIFICATION
#     # ================================================================
#     # URL : {% url 'admin:inventaire_inventairemensuel_add' %} (ligne 113)
#     path('mensuel/add/', views.redirect_to_add_inventaire_admin, name='add_inventaire_mensuel'),
    
#     # URL : {% url 'admin:inventaire_inventairemensuel_changelist' %} (ligne 116)
#     path('mensuel/list/', views.redirect_to_inventaires_admin, name='list_inventaire_mensuel'),
    
#     # URL : {% url 'admin:inventaire_configurationjour_changelist' %} (ligne 124)
#     path('config-jours/', views.redirect_to_config_jours_admin, name='config_jours'),
    
#     # URL : {% url 'admin:inventaire_configurationjour_add' %} (ligne 127)
#     path('config-jours/add/', views.redirect_to_add_config_jour_admin, name='add_config_jour'),
    
#     # ================================================================
#     # GESTION DES JOURS ET INVENTAIRES MENSUELS
#     # ================================================================
#     path('config-jours/list/', views.ConfigurationJourListView.as_view(), name='config_jour_list'),
#     path('mensuel/<int:inventaire_id>/gerer-jours/', views.gerer_jours_inventaire, name='gerer_jours'),
    
#     # ================================================================
#     # ASSOCIATIONS POSTES-INVENTAIRES-AGENTS
#     # ================================================================
#     path('postes/', views.liste_postes_inventaires, name='liste_postes_inventaires'),
#     path('postes/<int:poste_id>/', views.detail_poste_inventaires, name='detail_poste_inventaires'),
#     path('postes/<int:poste_id>/changer-agent/', views.changer_agent_poste, name='changer_agent_poste'),
    
#     # ================================================================
#     # ACTIONS ET VERROUILLAGE
#     # ================================================================
#     path('<int:pk>/lock/', views.InventaireVerrouillerView.as_view(), name='lock_inventaire'),
#     path('<int:pk>/validate/', views.InventaireValiderView.as_view(), name='validate_inventaire'),
    
#     # ================================================================
#     # API ENDPOINTS
#     # ================================================================
#     path('api/calcul-automatique/', views.CalculAutomatiqueAPIView.as_view(), name='api_calcul_automatique'),
#     path('api/verification-jour/', views.VerificationJourAPIView.as_view(), name='api_verification_jour'),
#     path('api/inventaire-stats/', views.inventaire_stats_api, name='api_inventaire_stats'),
#     path('api/recette-stats/', views.recette_stats_api, name='api_recette_stats'),
#     path('api/check-day-status/', views.check_day_status_api, name='api_check_day_status'),
#     path('api/quick-action/', views.quick_action_api, name='api_quick_action'),
    
#     # ================================================================
#     # RAPPORTS ET EXPORTS
#     # ================================================================
#     path('rapports/', views.RapportInventaireView.as_view(), name='rapport_generation'),
#     path('backup/', views.backup_inventaires_api, name='backup_inventaires'),
#     path('diagnostic/', views.diagnostic_inventaires_view, name='diagnostic'),
    
#     # ================================================================
#     # DASHBOARD ET WIDGETS
#     # ================================================================
#     path('dashboard/widget/', views.inventaire_dashboard_widget, name='dashboard_widget'),
#     path('admin/help/', views.inventaire_admin_help_view, name='admin_help'),
    
#     # ================================================================
#     # GESTION DES ERREURS
#     # ================================================================
#     path('error/<str:error_type>/', views.inventaire_redirect_error_handler, name='error_handler'),
#     path('api/notifications/', views.api_notifications, name='api_notifications'),
# ]