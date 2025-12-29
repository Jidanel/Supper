# inventaire/urls.py - URLs corrigées avec programmation inventaires

from django.urls import path
from . import views
from .views_stats import *
from .views_evolution import *
from . import views_evolution
from . import views_admin
from . import views_stocks
from . import views_rapports
from . import views_import
from . import views_classement
from . import views_transferts
from . import views_transferts_tickets
from . import views_bordereaux_pdf
from .views_stock_event_sourcing import *
from . import views_rapport_defaillants
from . import views_rapport_inventaires
from . import views_pesage
from . import views_pv_confrontation
from . import views_historique_pesage
from . import views_classement_pesage
from . import views_rapports_defaillants_pesage

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
    path('recettes/saisie/', views.saisir_recette_avec_tickets, name='saisir_recette_avec_tickets'),
    path('recettes/saisie/<int:poste_id>/', views.saisir_recette_avec_tickets, name='saisir_recette_poste_avec_tickets'),
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
#     path('stocks/charger/', views_stocks.charger_stock_selection, name='charger_stock_selection'),
#     path('stocks/charger/<int:poste_id>/', views_stocks.charger_stock, name='charger_stock'),
    path('stocks/charger/', views_stocks.charger_stock_selection, name='charger_stock_selection'),
    path('stocks/charger/<int:poste_id>/', views_stocks.charger_stock_tickets, name='charger_stock_tickets'),
    path('stocks/historique/<int:poste_id>/', views_stocks.historique_stock, name='historique_stock'),
    path('stocks/mon-stock/', views_stocks.mon_stock, name='mon_stock'),
    path('stocks/historique/<int:historique_id>/detail/', 
     views_stocks.detail_historique_stock, 
     name='detail_historique_stock'),

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
     path('stocks/chargement/confirmation/', views_stocks.confirmation_chargement_stock_tickets, name='confirmation_chargement_stock_tickets'),
     path('recettes/vente/confirmation/', views.confirmation_recette_tickets, name='confirmation_recette_tickets'),
     path(
        'compte-emploi/selection/',
        views_rapports.selection_compte_emploi,
        name='selection_compte_emploi'
    ),
    
    path(
        'compte-emploi/<int:poste_id>/<str:date_debut>/<str:date_fin>/apercu/',
        views_rapports.apercu_compte_emploi,
        name='apercu_compte_emploi'
    ),
    
    path(
        'compte-emploi/<int:poste_id>/<str:date_debut>/<str:date_fin>/pdf/',
        views_rapports.generer_compte_emploi_pdf,
        name='generer_compte_emploi'
    ),
     path('parametrage-global/', views_rapports.parametrage_global, name='parametrage_global'),
     path('classement-rendement/', views_classement.classement_postes_rendement, name='classement_rendement'),
     path('stocks/transfert/selection/', 
         views_transferts.selection_transfert_stock, 
         name='selection_transfert_stock'),
    
    path('stocks/transfert/formulaire/<int:origine_id>/<int:destination_id>/', 
         views_transferts.formulaire_transfert_stock, 
         name='formulaire_transfert_stock'),
    
    path('stocks/transfert/confirmation/', 
         views_transferts.confirmation_transfert_stock, 
         name='confirmation_transfert_stock'),
    
    path('stocks/transfert/bordereaux/<str:numero_bordereau>/', 
         views_transferts.bordereaux_transfert, 
         name='bordereaux_transfert'),
    
    path('stocks/transfert/bordereau-pdf/<str:numero_bordereau>/<str:type_bordereau>/', 
         views_bordereaux_pdf.bordereau_transfert_pdf, 
         name='bordereau_pdf'),
     path('stocks/transfert/bordereaux/', views_transferts.liste_bordereaux, name='liste_bordereaux'),

     path('classement/postes/', 
         views_classement.classement_postes_performances, 
         name='classement_postes_performances'),
    
    path('classement/agents/', 
         views_classement.classement_agents_performances, 
         name='classement_agents_performances'),
    
    path('classement/poste/<int:poste_id>/', 
         views_classement.detail_performance_poste, 
         name='detail_performance_poste'),
    
#     path('classement/agent/<int:agent_id>/', 
#          views_classement.detail_performance_agent, 
#          name='detail_performance_agent'),
     path(
    'agent/<int:agent_id>/performance/',
    views_classement.detail_performance_agent,
    name='detail_performance_agent'
),
     
# Quittancements - URLs CORRIGÉES
path('quittancements/saisie/', views.saisie_quittancement, name='saisie_quittancement'),
path('quittancements/', views.liste_quittancements, name='liste_quittancements'),
path('quittancements/comptabilisation/', views.comptabilisation_quittancements, name='comptabilisation_quittancements'),

# CORRECTION : Changer le nom de la route pour correspondre à la vue
path('quittancements/detail/<int:poste_id>/<str:date_debut>/<str:date_fin>/', 
     views.detail_quittancements_periode,  # ← Nom de vue corrigé
     name='detail_quittancements_periode'),  # ← Nom de route cohérent

# CORRECTION : URL justifier_ecart avec paramètres corrects
path('quittancements/justifier/<int:poste_id>/<str:date_debut>/<str:date_fin>/', 
     views.justifier_ecart_periode,  # ← Renommé pour cohérence
     name='justifier_ecart_periode'),

# Authentification documents
path('authentifier-document/', views.authentifier_document, name='authentifier_document'),

# Export
path('quittancements/export/', views.export_quittancements, name='export_quittancements'),
path(
    'quittancements/<int:quittancement_id>/ajouter-image/',
    views.ajouter_image_quittancement,
    name='ajouter_image_quittancement'
),

# Traçabilité des tickets (admin)
    path('admin/tracabilite-tickets/', 
         views_admin.recherche_tracabilite_ticket, 
         name='recherche_tracabilite_ticket'),
    
    path('api/verifier-unicite-ticket/', 
         views_admin.verifier_unicite_ticket_annee, 
         name='api_verifier_unicite_ticket'),
     
     path('transfert-tickets/selection-postes/', 
         views_transferts_tickets.selection_postes_transfert_tickets,
         name='selection_postes_transfert_tickets'),
     path('transfert/bordereau/<str:numero_bordereau>/',
     views_transferts_tickets.detail_bordereau_transfert,
     name='detail_bordereau_transfert'),
    
    path('transfert-tickets/saisie/', 
         views_transferts_tickets.saisie_tickets_transfert,
         name='saisie_tickets_transfert'),
    
    path('transfert-tickets/confirmation/', 
         views_transferts_tickets.confirmation_transfert_tickets,
         name='confirmation_transfert_tickets'),

    path('stocks/transfert/succes/<str:numero_bordereau>/', 
     views_transferts.detail_transfert_succes, 
     name='detail_transfert_succes'),
    
    # ===== RAPPORT DES INVENTAIRES =====
    path(
        'rapports/inventaires/selection/',
        views_rapport_inventaires.selection_rapport_inventaires,
        name='selection_rapport_inventaires'
    ),
    path(
        'rapports/inventaires/',
        views_rapport_inventaires.rapport_inventaires,
        name='rapport_inventaires'
    ),

    path(
        'ajax/series-par-couleur/', 
        views_transferts_tickets.ajax_series_par_couleur,
        name='ajax_series_par_couleur'
    ),

    
    
    
    
    # ===================================================================
    # API ENDPOINTS (JSON)
    # ===================================================================
    path(
        'pesage/api/stats/<str:date_str>/',
        views_pesage.api_stats_jour,
        name='api_stats_jour'
    ),
    path(
        'pesage/api/recherche/',
        views_pesage.api_recherche_amende,
        name='api_recherche_amende'
    ),



]

event_sourcing_patterns = [
    # Vue de sélection (nouvelle)
    path(
        'stock/selection-date/',
        stock_selection_date,
        name='stock_selection_date'
    ),
    
    # Visualisation du stock à une date avec poste_id optionnel
    path(
        'stock/historique/',
        stock_historique_date,
        name='stock_historique_date_sans_poste'
    ),
    
    # Visualisation du stock à une date avec poste spécifique
    path(
        'stock/<int:poste_id>/historique/',
        stock_historique_date,
        name='stock_historique_date'
    ),
    
    # API pour timeline graphique
    path(
        'api/stock/<int:poste_id>/timeline/',
        api_stock_timeline,
        name='api_stock_timeline'
    ),
    
    # Comparaison entre dates
    path(
        'stock/comparer-dates/',
        comparer_stocks_dates,
        name='comparer_stocks_dates'
    ),
    
    # Export CSV
    path(
        'stock/<int:poste_id>/export-csv/',
        export_stock_history_csv,
        name='export_stock_history_csv'
    ),
    
    # Reconstruction (admin only)
    path(
        'stock/<int:poste_id>/rebuild/',
        rebuild_stock_events,
        name='rebuild_stock_events'
    ),
    # Rapport des défaillants
    path('rapports/defaillants/', views_rapport_defaillants.selection_rapport_defaillants, name='selection_rapport_defaillants'),

    path('rapports/defaillants/generer/', views_rapport_defaillants.rapport_defaillants_peage, name='rapport_defaillants_peage'),
]
urlpatterns += event_sourcing_patterns

pesage_patterns = [
    # Liste et recherche des amendes
    path('pesage/amendes/', views_pesage.liste_amendes, name='liste_amendes'),
    path('pesage/amendes/<int:pk>/', views_pesage.detail_amende, name='detail_amende'),
    
    # Saisie (Chef d'équipe)
    path('pesage/amendes/saisir/', views_pesage.saisir_amende, name='saisir_amende'),
    path('pesage/pesees/saisir/', views_pesage.saisir_pesees, name='saisir_pesees'),
    path('pesage/pesees/', views_pesage.historique_pesees, name='historique_pesees'),
    
    # Validation (Régisseur)
    path('pesage/amendes/a-valider/', views_pesage.liste_amendes_a_valider, name='liste_amendes_a_valider'),
    path('pesage/amendes/<int:pk>/valider/', views_pesage.valider_paiement, name='valider_paiement'),
    path('pesage/amendes/valider-masse/', views_pesage.valider_paiements_masse, name='valider_paiements_masse'),
    
    # Quittancements
    # Saisie de quittancement pesage (3 étapes)
    path(
        'pesage/quittancements/saisie/', 
        views_pesage.saisie_quittancement_pesage, 
        name='saisie_quittancement_pesage'
    ),
    
    # Liste des quittancements pesage
    path(
        'pesage/quittancements/', 
        views_pesage.liste_quittancements_pesage, 
        name='liste_quittancements_pesage'
    ),
    
    # Comptabilisation des quittancements pesage
    path(
        'pesage/quittancements/comptabilisation/', 
        views_pesage.comptabilisation_quittancements_pesage, 
        name='comptabilisation_quittancements_pesage'
    ),
    
    # Justification d'écart pesage
    path(
        'pesage/quittancements/justifier/<int:station_id>/<str:date_debut>/<str:date_fin>/',
        views_pesage.justifier_ecart_pesage,
        name='justifier_ecart_pesage'
    ),
    
    # Détails quittancements période pesage
    path(
        'pesage/quittancements/detail/<int:station_id>/<str:date_debut>/<str:date_fin>/',
        views_pesage.detail_quittancements_periode_pesage,
        name='detail_quittancements_periode_pesage'
    ),
    
    # Export Excel quittancements pesage
    path(
        'quittancements/export/',
        views_pesage.export_quittancements_pesage,
        name='export_quittancements_pesage'
    ),
    # Recettes avec recherche et filtres
    path('pesage/recettes/', views_pesage.recettes_pesage, name='recettes_pesage'),
    path('pesage/recettes/imprimer/', views_pesage.imprimer_recette_jour, name='imprimer_recette_jour'),
    path('recettes/imprimer/<str:date_str>/',views_pesage.imprimer_recette_jour,name='imprimer_recette_jour'),
    
    # Statistiques et rapports
    path('pesage/statistiques/', views_pesage.statistiques_pesage, name='statistiques_pesage'),
    
    # API JSON
    path('pesage/api/paiements-jour/', views_pesage.api_paiements_jour, name='api_paiements_jour'),

    path(
        'selectionner-station/',
        views_pesage.selectionner_station,
        name='selectionner_station'
    ),
    # PV de Confrontation Pesage
    path('pesage/pv-confrontation/', 
         views_pv_confrontation.selection_pv_confrontation, 
         name='selection_pv_confrontation'),
    path('pesage/pv-confrontation/apercu/<int:station_id>/<str:date_debut>/<str:date_fin>/', 
         views_pv_confrontation.apercu_pv_confrontation, 
         name='apercu_pv_confrontation'),
    path('pesage/pv-confrontation/pdf/<int:station_id>/<str:date_debut>/<str:date_fin>/', 
         views_pv_confrontation.generer_pv_confrontation_pdf, 
         name='generer_pv_confrontation_pdf'),
     path('pesage/amendes/<int:pk>/consulter/', 
          views_pesage.consulter_amendes_anterieures, 
          name='consulter_amendes_anterieures'),
    
     # ===================================================================
    # RECHERCHE HISTORIQUE VÉHICULE
    # ===================================================================
    
    # Page de recherche d'historique (accessible à tous les rôles pesage)
    path('pesage/recherche-historique/', 
         views_historique_pesage.recherche_historique_vehicule, 
         name='recherche_historique_vehicule'),
    
    # Détail historique d'un véhicule spécifique
    path('pesage/historique-vehicule/<str:immatriculation>/', 
         views_historique_pesage.detail_historique_vehicule, 
         name='detail_historique_vehicule'),
    
    # ===================================================================
    # VÉRIFICATION AVANT VALIDATION DE PAIEMENT
    # ===================================================================
    
    # Vérifier les amendes impayées avant validation
    path('pesage/verifier-avant-validation/<int:pk>/', 
         views_historique_pesage.verifier_avant_validation, 
         name='verifier_avant_validation'),
    
    # Validation directe (après vérification OK ou avec confirmations)
    path('pesage/valider-paiement-direct/<int:pk>/', 
         views_historique_pesage.valider_paiement_direct, 
         name='valider_paiement_direct'),
     path('api/pesage/amendes-vehicule/<str:immatriculation>/', 
      views_pesage.api_amendes_vehicule_autres_stations, 
      name='api_amendes_vehicule_autres_stations'),
    
    # ===================================================================
    # DEMANDES DE CONFIRMATION INTER-STATIONS
#     # ===================================================================
    
#     # Créer une demande de confirmation
#     path('pesage/creer-demande-confirmation/<int:amende_pk>/<int:amende_bloquante_pk>/', 
#          views_historique_pesage.creer_demande_confirmation, 
#          name='creer_demande_confirmation'),
    
#     # Liste des demandes envoyées par ma station
#     path('pesage/mes-demandes-confirmation/', 
#          views_historique_pesage.mes_demandes_confirmation, 
#          name='mes_demandes_confirmation'),
    
#     # Liste des demandes à traiter (reçues)
#     path('pesage/demandes-confirmation-a-traiter/', 
#          views_historique_pesage.demandes_confirmation_a_traiter, 
#          name='demandes_confirmation_a_traiter'),
    
    # Détail d'une demande
#     path('pesage/demande-confirmation/<int:pk>/', 
#          views_historique_pesage.detail_demande_confirmation, 
#          name='detail_demande_confirmation'),
    
    # Traiter une demande (confirmer/refuser)
#     #path('pesage/traiter-demande-confirmation/<int:pk>/', 
#          views_historique_pesage.traiter_demande_confirmation, 
#          name='traiter_demande_confirmation'),
    #path('pesage/validation-bloquee/<int:pk>/', views_historique_pesage.validation_bloquee, name='validation_bloquee'),

    path('pesage/classement-rendement/', views_classement_pesage.classement_stations_pesage_rendement, name='classement_stations_pesage_rendement'),

     path('pesage/selection-rapport-defaillants/', 
         views_rapports_defaillants_pesage.selection_rapport_defaillants_pesage, 
         name='selection_rapport_defaillants_pesage'),
    
    path('pesage/rapport-defaillants/', 
         views_rapports_defaillants_pesage.rapport_defaillants_pesage, 
         name='rapport_defaillants_pesage'),
    
    # =====================================================
    # OBJECTIFS ANNUELS PESAGE
    # =====================================================
    path('objectifs-pesage/', 
         views_rapports_defaillants_pesage.gestion_objectifs_annuels_pesage, 
         name='gestion_objectifs_pesage'),
    
    path('objectifs-pesage/dupliquer/', 
         views_rapports_defaillants_pesage.dupliquer_objectifs_annee_pesage, 
         name='dupliquer_objectifs_pesage'),
    
    path('objectifs-pesage/calculer/', 
         views_rapports_defaillants_pesage.calculer_objectifs_pesage_automatique, 
         name='calculer_objectifs_pesage'),

    
    # ===================================================================
    # API ENDPOINTS
    # ===================================================================
    
    # API recherche historique
    path('api/pesage/recherche-historique/', 
         views_historique_pesage.api_recherche_historique, 
         name='api_recherche_historique'),
    
    # API vérifier amendes impayées autres stations
    path('api/pesage/verifier-impaye/', 
         views_historique_pesage.api_verifier_impaye_autres_stations, 
         name='api_verifier_impaye_autres_stations'),
    
]
urlpatterns += pesage_patterns
