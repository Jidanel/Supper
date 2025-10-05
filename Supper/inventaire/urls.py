# inventaire/urls.py - URLs corrigées avec programmation inventaires

from django.urls import path
from . import views
from .views_stats import *
from .views_evolution import *
from . import views_evolution
from . import views_admin
from . import views_stocks
from . import views_import
app_name = 'inventaire'

urlpatterns = [
    # ================================================================
    # URLS PRINCIPALES INVENTAIRE
    # ================================================================
    path('', views.InventaireListView.as_view(), name='inventaire_list'),
    path('<int:pk>/', views.InventaireDetailView.as_view(), name='inventaire_detail'),
    #path('saisie/<int:poste_id>/', views.SaisieInventaireView.as_view(), name='saisie_inventaire_poste'),
    path('inventaire/supprimer/<int:pk>/', views.supprimer_inventaire, name='supprimer_inventaire_poste'),
    # Ajouter ces lignes dans inventaire/urls.py
    path('saisie/', views.selection_date_inventaire, name='saisie_inventaire'),  # Redirige vers sélection
    path('saisie/<int:poste_id>/', views.selection_date_inventaire, name='saisie_inventaire_poste'),  # Redirige vers sélection
    path('saisie/<int:poste_id>/<str:date_str>/', views.SaisieInventaireView.as_view(), name='saisie_inventaire_avec_date'),  # Saisie réelle
    path('check-inventaire-exists/', views.check_inventaire_exists, name='check_inventaire_exists'),
    path('jours-impertinents/', views.jours_impertinents_view, name='jours_impertinents'),
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
    #path('recettes/supprimer/<int:poste_id>/', views.supprimer_recette, name='supprimer_recette_poste'),
    path('recettes/<int:recette_id>/delete-admin/', views.redirect_to_delete_recette_admin, name='redirect_delete_recette_admin'),
    path('recettes/', views.RecetteListView.as_view(), name='liste_recettes'),
    path('recettes/<int:pk>/', views.RecetteDetailView.as_view(), name='recette_detail'),
    path('recettes/<int:pk>/modifier/', views.modifier_recette, name='modifier_recette'),
    #path('taux-evolution/', views_evolution.taux_evolution_view, name='taux_evolution'),
    # Dans la section des statistiques/évolution
    path('evolution/', views_evolution.taux_evolution_view, name='taux_evolution_avance'),
    #path('evolution/avance/', views_evolution.taux_evolution_avance_view, name='taux_evolution_avance'),

    
    # ================================================================
    # MODIFICATIONS ADMIN
    # ================================================================
    path('admin/<int:inventaire_id>/modifier/', views.modifier_inventaire, name='modifier_inventaire_admin'),
    path('recettes/admin/<int:recette_id>/modifier/', views.modifier_recette, name='modifier_recette_admin'),
    # Ajouter après les imports
     

     # Inventaire administratif
    path('admin-saisie/', views_admin.inventaire_administratif, name='inventaire_administratif'),
    path('admin-saisie/<int:poste_id>/<str:date_str>/', views_admin.inventaire_admin_saisie, name='inventaire_admin_saisie'),
    path('admin/liste/', views_admin.liste_inventaires_administratifs, name='liste_inventaires_administratifs'),
    
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
    path('stocks/', views_stocks.liste_postes_stocks, name='liste_postes_stocks'),
    path('stocks/charger/', views_stocks.charger_stock_selection, name='charger_stock_selection'),
    path('stocks/charger/<int:poste_id>/', views_stocks.charger_stock, name='charger_stock'),
    path('stocks/historique/<int:poste_id>/', views_stocks.historique_stock, name='historique_stock'),
    path('stocks/mon-stock/', views_stocks.mon_stock, name='mon_stock'),

    # Gestion des objectifs annuels
    path('objectifs-annuels/', 
         views.gestion_objectifs_annuels, 
         name='gestion_objectifs_annuels'),
    path('objectifs-annuels/dupliquer/', 
         views.dupliquer_objectifs_annee, 
         name='dupliquer_objectifs'),
     path('simulateur-commandes/', views.simulateur_commandes, name='simulateur_commandes'),
     path('objectifs-calculer/', views.calculer_objectifs_automatique, name='calculer_objectifs'),

     # IMPORT/EXPORT
     path('import/recettes/', views_import.import_recettes_excel, name='import_recettes'),
     path('import/modele/', views_import.telecharger_modele_excel, name='telecharger_modele_excel'),
     path('api/graphique-evolution/', views.api_graphique_evolution, name='api_graphique_evolution'),
     path('api/statistiques-postes/', views.api_statistiques_postes_ordonnes, name='api_statistiques_postes_ordonnes'),
     path('api/stats/', views.api_inventaire_stats, name='api_inventaire_stats'),
     ]
