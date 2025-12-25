/**
 * ===================================================================
 * SUPPER - Gestion automatique des permissions par habilitation
 * ===================================================================
 * 
 * Mapping basé sur le document officiel Habilitations.pdf
 * 
 * HABILITATIONS DÉFINIES (16 rôles):
 * - Services centraux (accès tous postes): admin_principal, coord_psrr, 
 *   serv_info, serv_emission, chef_ag, serv_controle, serv_ordre
 * - CISOP: cisop_peage, cisop_pesage
 * - Péage (accès poste affecté): chef_peage, agent_inventaire
 * - Pesage (accès poste affecté): chef_station_pesage, regisseur_pesage, 
 *   chef_equipe_pesage
 * - Externe: imprimerie
 * 
 * TOTAL: 58 permissions granulaires
 * ===================================================================
 */

const PERMISSIONS_PAR_HABILITATION = {
    
    // ═══════════════════════════════════════════════════════════════
    // SERVICES CENTRAUX - Accès complet à tous les postes
    // ═══════════════════════════════════════════════════════════════
    
    /**
     * ADMINISTRATEUR PRINCIPAL - Accès total système
     */
    'admin_principal': [
        // Inventaires (10)
        'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin', 'peut_programmer_inventaire',
        'peut_voir_programmation_active', 'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
        'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin', 'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        // Recettes Péage (6)
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_importer_recettes_peage', 'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        // Quittances Péage (3)
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        // Pesage (12)
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
        'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        // Stock Péage (9)
        'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage', 'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage', 'peut_simuler_commandes_peage',
        // Gestion (6)
        'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
        'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit',
        // Rapports (7)
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        // Autres (5)
        'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
        'peut_authentifier_document', 'peut_voir_tous_postes'
    ],

    /**
     * COORDONNATEUR PSRR - Accès complet système
     */
    'coord_psrr': [
        // Inventaires
        'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin', 'peut_programmer_inventaire',
        'peut_voir_programmation_active', 'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
        'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin', 'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        // Recettes Péage
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_importer_recettes_peage', 'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        // Quittances Péage
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        // Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
        'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        // Stock Péage
        'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage', 'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage', 'peut_simuler_commandes_peage',
        // Gestion
        'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
        'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit',
        // Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        // Autres
        'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
        'peut_authentifier_document', 'peut_voir_tous_postes'
    ],

    /**
     * SERVICE INFORMATIQUE - Accès complet système + maintenance
     */
    'serv_info': [
        // Inventaires
        'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin', 'peut_programmer_inventaire',
        'peut_voir_programmation_active', 'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
        'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin', 'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        // Recettes Péage
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_importer_recettes_peage', 'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        // Quittances Péage
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        // Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
        'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        // Stock Péage
        'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage', 'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage', 'peut_simuler_commandes_peage',
        // Gestion
        'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
        'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit',
        // Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        // Autres
        'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
        'peut_authentifier_document', 'peut_voir_tous_postes'
    ],

    /**
     * SERVICE ÉMISSIONS ET RECOUVREMENT - Gestion financière
     */
    'serv_emission': [
        // Inventaires
        'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin', 'peut_programmer_inventaire',
        'peut_voir_programmation_active', 'peut_voir_programmation_desactivee',
        'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin', 'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        // Recettes Péage
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        // Quittances Péage
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        // Pesage
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        // Stock Péage
        'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage', 'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage', 'peut_simuler_commandes_peage',
        // Rapports
        'peut_voir_classement_peage_rendement', 'peut_voir_classement_station_pesage',
        'peut_voir_classement_peage_deperdition', 'peut_voir_classement_agents_inventaire',
        // Autres
        'peut_voir_compte_emploi', 'peut_voir_pv_confrontation', 'peut_authentifier_document',
        'peut_voir_tous_postes'
    ],

    /**
     * SERVICE DES AFFAIRES GÉNÉRALES - Gestion RH et administrative
     */
    'chef_ag': [
        // Gestion
        'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
        'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit',
        // Autres
        'peut_parametrage_global', 'peut_voir_tous_postes'
    ],

    /**
     * SERVICE CONTRÔLE ET VALIDATION - Audit et validation
     */
    'serv_controle': [
        // Inventaires
        'peut_voir_liste_inventaires', 'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
        // Recettes Péage
        'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        // Quittances Péage
        'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        // Pesage
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        // Stock Péage
        'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage', 'peut_voir_historique_stock_peage',
        // Gestion
        'peut_voir_journal_audit',
        // Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        // Autres
        'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
        'peut_authentifier_document', 'peut_voir_tous_postes'
    ],

    /**
     * SERVICE ORDRE/SECRÉTARIAT - Archivage et documentation
     */
    'serv_ordre': [
        // Inventaires
        'peut_voir_stats_deperdition',
        // Recettes Péage
        'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        // Quittances Péage
        'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        // Pesage
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        // Stock Péage
        'peut_voir_liste_stocks_peage', 'peut_voir_tracabilite_tickets',
        'peut_voir_bordereaux_peage', 'peut_voir_historique_stock_peage',
        // Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
        // Autres
        'peut_voir_compte_emploi', 'peut_voir_pv_confrontation', 'peut_authentifier_document',
        'peut_voir_tous_postes'
    ],

    // ═══════════════════════════════════════════════════════════════
    // CISOP - Cellules d'Inspection et Suivi des Opérations
    // ═══════════════════════════════════════════════════════════════

    /**
     * CISOP PÉAGE - Inspection des postes de péage
     */
    'cisop_peage': [
        // Inventaires
        'peut_voir_liste_inventaires', 'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
        // Recettes Péage
        'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        // Quittances Péage
        'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        // Stock Péage
        'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage', 'peut_voir_historique_stock_peage',
        // Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapport_inventaires',
        'peut_voir_classement_peage_rendement', 'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        // Autres
        'peut_voir_compte_emploi', 'peut_voir_pv_confrontation', 'peut_authentifier_document',
        'peut_voir_tous_postes'
    ],

    /**
     * CISOP PESAGE - Inspection des stations de pesage
     */
    'cisop_pesage': [
        // Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_voir_liste_quittancements_pesage', 'peut_voir_historique_pesees',
        'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        // Rapports
        'peut_voir_rapports_defaillants_pesage', 'peut_voir_classement_station_pesage',
        // Autres
        'peut_voir_pv_confrontation', 'peut_authentifier_document', 'peut_voir_tous_postes'
    ],

    // ═══════════════════════════════════════════════════════════════
    // POSTES DE PÉAGE - Accès limité au poste d'affectation
    // ═══════════════════════════════════════════════════════════════

    /**
     * CHEF DE POSTE PÉAGE - Gestion complète du poste de péage
     */
    'chef_peage': [
        // Inventaires
        'peut_voir_liste_inventaires', 'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition','peut_voir_liste_inventaires_admin',
        // Recettes Péage
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        // Quittances Péage
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        // Stock Péage
        'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage',
        // Rapports
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_peage_deperdition', 'peut_voir_classement_agents_inventaire',
        // Autres
        'peut_voir_compte_emploi', 'peut_authentifier_document'
    ],

    /**
     * AGENT INVENTAIRE - Saisie des inventaires uniquement
     */
    'agent_inventaire': [
        // Inventaires - Saisie uniquement
        'peut_saisir_inventaire_normal'
    ],

    // ═══════════════════════════════════════════════════════════════
    // STATIONS DE PESAGE - Accès limité à la station d'affectation
    // ═══════════════════════════════════════════════════════════════

    /**
     * CHEF DE STATION PESAGE - Supervision de la station de pesage
     */
    'chef_station_pesage': [
        // Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende',
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        // Rapports
        'peut_voir_classement_station_pesage',
        // Autres
        'peut_voir_pv_confrontation', 'peut_authentifier_document'
    ],

    /**
     * RÉGISSEUR DE STATION PESAGE - Gestion financière de la station
     */
    'regisseur_pesage': [
        // Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
        'peut_saisir_quittance_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        // Rapports
        'peut_voir_classement_station_pesage','peut_voir_pv_confrontation', 'peut_authentifier_document'
    ],

    /**
     * CHEF D'ÉQUIPE STATION PESAGE - Opérations quotidiennes de pesage
     */
    'chef_equipe_pesage': [
        // Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_voir_historique_pesees', 'peut_voir_stats_pesage'
    ],

    // ═══════════════════════════════════════════════════════════════
    // EXTERNES
    // ═══════════════════════════════════════════════════════════════

    /**
     * IMPRIMERIE NATIONALE - Consultation historique uniquement
     */
    'imprimerie': [
        // Stock Péage - Historique uniquement
        'peut_voir_historique_stock_peage'
    ]
};


// ═══════════════════════════════════════════════════════════════════
// LISTE COMPLÈTE DES 58 PERMISSIONS
// ═══════════════════════════════════════════════════════════════════

const TOUTES_PERMISSIONS = [
    // ─────────────────────────────────────────────────────────────
    // INVENTAIRES (10 permissions)
    // ─────────────────────────────────────────────────────────────
    'peut_saisir_inventaire_normal',      // Saisie inventaire standard
    'peut_saisir_inventaire_admin',       // Saisie inventaire mode admin
    'peut_programmer_inventaire',          // Programmer les inventaires
    'peut_voir_programmation_active',      // Voir programmations actives
    'peut_desactiver_programmation',       // Désactiver programmations
    'peut_voir_programmation_desactivee',  // Voir programmations désactivées
    'peut_voir_liste_inventaires',         // Liste des inventaires
    'peut_voir_liste_inventaires_admin',   // Liste inventaires (vue admin)
    'peut_voir_jours_impertinents',        // Voir les jours impertinents
    'peut_voir_stats_deperdition',         // Statistiques de déperdition

    // ─────────────────────────────────────────────────────────────
    // RECETTES PÉAGE (6 permissions)
    // ─────────────────────────────────────────────────────────────
    'peut_saisir_recette_peage',          // Saisir une recette
    'peut_voir_liste_recettes_peage',     // Liste des recettes
    'peut_voir_stats_recettes_peage',     // Statistiques recettes
    'peut_importer_recettes_peage',       // Import de recettes
    'peut_voir_evolution_peage',          // Évolution des recettes
    'peut_voir_objectifs_peage',          // Objectifs de recettes

    // ─────────────────────────────────────────────────────────────
    // QUITTANCES PÉAGE (3 permissions)
    // ─────────────────────────────────────────────────────────────
    'peut_saisir_quittance_peage',        // Saisir quittance
    'peut_voir_liste_quittances_peage',   // Liste des quittances
    'peut_comptabiliser_quittances_peage', // Comptabiliser quittances

    // ─────────────────────────────────────────────────────────────
    // PESAGE (12 permissions)
    // ─────────────────────────────────────────────────────────────
    'peut_voir_historique_vehicule_pesage', // Historique véhicules
    'peut_saisir_amende',                   // Saisir une amende
    'peut_saisir_pesee_jour',               // Saisir pesée journalière
    'peut_voir_objectifs_pesage',           // Objectifs pesage
    'peut_valider_paiement_amende',         // Valider paiement amende
    'peut_lister_amendes',                  // Lister les amendes
    'peut_saisir_quittance_pesage',         // Saisir quittance pesage
    'peut_comptabiliser_quittances_pesage', // Comptabiliser quittances pesage
    'peut_voir_liste_quittancements_pesage', // Liste quittancements pesage
    'peut_voir_historique_pesees',          // Historique des pesées
    'peut_voir_recettes_pesage',            // Recettes pesage
    'peut_voir_stats_pesage',               // Statistiques pesage

    // ─────────────────────────────────────────────────────────────
    // STOCK PÉAGE (9 permissions)
    // ─────────────────────────────────────────────────────────────
    'peut_charger_stock_peage',           // Charger stock (imprimerie/régul)
    'peut_voir_liste_stocks_peage',       // Liste des stocks
    'peut_voir_stock_date_peage',         // Stock à une date
    'peut_transferer_stock_peage',        // Transférer stock entre postes
    'peut_voir_tracabilite_tickets',      // Traçabilité des tickets
    'peut_voir_bordereaux_peage',         // Bordereaux de livraison
    'peut_voir_mon_stock_peage',          // Mon stock (poste affecté)
    'peut_voir_historique_stock_peage',   // Historique des stocks
    'peut_simuler_commandes_peage',       // Simulation de commandes

    // ─────────────────────────────────────────────────────────────
    // GESTION (6 permissions)
    // ─────────────────────────────────────────────────────────────
    'peut_gerer_postes',                  // Gérer les postes
    'peut_ajouter_poste',                 // Ajouter un poste
    'peut_creer_poste_masse',             // Création en masse de postes
    'peut_gerer_utilisateurs',            // Gérer les utilisateurs
    'peut_creer_utilisateur',             // Créer un utilisateur
    'peut_voir_journal_audit',            // Journal d'audit

    // ─────────────────────────────────────────────────────────────
    // RAPPORTS (7 permissions)
    // ─────────────────────────────────────────────────────────────
    'peut_voir_rapports_defaillants_peage',    // Défaillants péage
    'peut_voir_rapports_defaillants_pesage',   // Défaillants pesage
    'peut_voir_rapport_inventaires',           // Rapport inventaires
    'peut_voir_classement_peage_rendement',    // Classement rendement péage
    'peut_voir_classement_station_pesage',     // Classement stations pesage
    'peut_voir_classement_peage_deperdition',  // Classement déperdition
    'peut_voir_classement_agents_inventaire',  // Classement agents inventaire

    // ─────────────────────────────────────────────────────────────
    // AUTRES (5 permissions)
    // ─────────────────────────────────────────────────────────────
    'peut_parametrage_global',            // Paramétrage système
    'peut_voir_compte_emploi',            // Compte d'emploi
    'peut_voir_pv_confrontation',         // PV de confrontation
    'peut_authentifier_document',         // Authentifier documents
    'peut_voir_tous_postes'               // Accès tous les postes
];


// ═══════════════════════════════════════════════════════════════════
// CATÉGORIES DE PERMISSIONS (pour l'accordéon dans l'interface)
// ═══════════════════════════════════════════════════════════════════

const CATEGORIES_PERMISSIONS = {
    'inventaires': {
        label: 'Inventaires',
        icon: 'fas fa-clipboard-list',
        permissions: [
            'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin', 'peut_programmer_inventaire',
            'peut_voir_programmation_active', 'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
            'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin', 'peut_voir_jours_impertinents',
            'peut_voir_stats_deperdition'
        ]
    },
    'recettes-peage': {
        label: 'Recettes Péage',
        icon: 'fas fa-coins',
        permissions: [
            'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
            'peut_importer_recettes_peage', 'peut_voir_evolution_peage', 'peut_voir_objectifs_peage'
        ]
    },
    'quittances-peage': {
        label: 'Quittances Péage',
        icon: 'fas fa-receipt',
        permissions: [
            'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage'
        ]
    },
    'pesage': {
        label: 'Pesage',
        icon: 'fas fa-weight',
        permissions: [
            'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
            'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
            'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
            'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage'
        ]
    },
    'stock-peage': {
        label: 'Stock Péage',
        icon: 'fas fa-boxes',
        permissions: [
            'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
            'peut_transferer_stock_peage', 'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
            'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage', 'peut_simuler_commandes_peage'
        ]
    },
    'gestion': {
        label: 'Gestion',
        icon: 'fas fa-cogs',
        permissions: [
            'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
            'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit'
        ]
    },
    'rapports': {
        label: 'Rapports',
        icon: 'fas fa-chart-bar',
        permissions: [
            'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
            'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
            'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
            'peut_voir_classement_agents_inventaire'
        ]
    },
    'autres': {
        label: 'Autres',
        icon: 'fas fa-ellipsis-h',
        permissions: [
            'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
            'peut_authentifier_document', 'peut_voir_tous_postes'
        ]
    }
};


// ═══════════════════════════════════════════════════════════════════
// FONCTIONS UTILITAIRES
// ═══════════════════════════════════════════════════════════════════

/**
 * Décoche toutes les permissions
 */
function resetAllPermissions() {
    TOUTES_PERMISSIONS.forEach(perm => {
        const checkbox = document.getElementById('id_' + perm);
        if (checkbox) {
            checkbox.checked = false;
        }
    });
    updatePermissionsIndicator();
}

/**
 * Coche toutes les permissions
 */
function checkAllPermissions() {
    TOUTES_PERMISSIONS.forEach(perm => {
        const checkbox = document.getElementById('id_' + perm);
        if (checkbox) {
            checkbox.checked = true;
        }
    });
    updatePermissionsIndicator();
}

/**
 * Applique les permissions par défaut pour une habilitation donnée
 * @param {string} habilitation - Le code de l'habilitation
 */
function applyPermissionsForHabilitation(habilitation) {
    // D'abord, décocher toutes les permissions
    resetAllPermissions();
    
    // Ensuite, cocher les permissions de l'habilitation
    const permissions = PERMISSIONS_PAR_HABILITATION[habilitation];
    if (permissions) {
        permissions.forEach(perm => {
            const checkbox = document.getElementById('id_' + perm);
            if (checkbox) {
                checkbox.checked = true;
            }
        });
    }
    
    updatePermissionsIndicator();
}

/**
 * Retourne l'état actuel de toutes les permissions
 * @returns {Object} - Objet avec les permissions actives
 */
function getCurrentPermissions() {
    const current = {};
    TOUTES_PERMISSIONS.forEach(perm => {
        const checkbox = document.getElementById('id_' + perm);
        if (checkbox) {
            current[perm] = checkbox.checked;
        }
    });
    return current;
}

/**
 * Compte le nombre de permissions actives
 * @returns {number} - Nombre de permissions cochées
 */
function countActivePermissions() {
    let count = 0;
    TOUTES_PERMISSIONS.forEach(perm => {
        const checkbox = document.getElementById('id_' + perm);
        if (checkbox && checkbox.checked) {
            count++;
        }
    });
    return count;
}

/**
 * Met à jour l'indicateur visuel du nombre de permissions
 */
function updatePermissionsIndicator() {
    const indicator = document.getElementById('permissions-count');
    if (indicator) {
        const count = countActivePermissions();
        const total = TOUTES_PERMISSIONS.length;
        indicator.textContent = `${count}/${total} permissions actives`;
        
        // Couleur selon le pourcentage
        if (count === 0) {
            indicator.className = 'badge bg-secondary';
        } else if (count < total * 0.3) {
            indicator.className = 'badge bg-warning';
        } else if (count < total * 0.7) {
            indicator.className = 'badge bg-info';
        } else {
            indicator.className = 'badge bg-success';
        }
    }
    
    // Mettre à jour les compteurs par catégorie
    updateCategoryCounters();
}

/**
 * Met à jour les compteurs par catégorie dans l'accordéon
 */
function updateCategoryCounters() {
    Object.keys(CATEGORIES_PERMISSIONS).forEach(catId => {
        const badge = document.getElementById('count-' + catId);
        if (badge) {
            let count = 0;
            CATEGORIES_PERMISSIONS[catId].permissions.forEach(perm => {
                const checkbox = document.getElementById('id_' + perm);
                if (checkbox && checkbox.checked) count++;
            });
            badge.textContent = `${count}/${CATEGORIES_PERMISSIONS[catId].permissions.length}`;
        }
    });
}

/**
 * Développe tous les accordéons de permissions
 */
function expandAllPermissionAccordions() {
    document.querySelectorAll('.accordion-collapse').forEach(el => {
        el.classList.add('show');
    });
    document.querySelectorAll('.accordion-button').forEach(btn => {
        btn.classList.remove('collapsed');
        btn.setAttribute('aria-expanded', 'true');
    });
}

/**
 * Replie tous les accordéons de permissions
 */
function collapseAllPermissionAccordions() {
    document.querySelectorAll('.accordion-collapse').forEach(el => {
        el.classList.remove('show');
    });
    document.querySelectorAll('.accordion-button').forEach(btn => {
        btn.classList.add('collapsed');
        btn.setAttribute('aria-expanded', 'false');
    });
}

/**
 * Coche toutes les permissions d'une catégorie
 * @param {string} categoryId - L'ID de la catégorie
 */
function checkAllInCategory(categoryId) {
    const category = CATEGORIES_PERMISSIONS[categoryId];
    if (category) {
        category.permissions.forEach(perm => {
            const checkbox = document.getElementById('id_' + perm);
            if (checkbox) checkbox.checked = true;
        });
        updatePermissionsIndicator();
    }
}

/**
 * Décoche toutes les permissions d'une catégorie
 * @param {string} categoryId - L'ID de la catégorie
 */
function uncheckAllInCategory(categoryId) {
    const category = CATEGORIES_PERMISSIONS[categoryId];
    if (category) {
        category.permissions.forEach(perm => {
            const checkbox = document.getElementById('id_' + perm);
            if (checkbox) checkbox.checked = false;
        });
        updatePermissionsIndicator();
    }
}

/**
 * Gestionnaire de changement d'habilitation
 */
function handleHabilitationChange() {
    const select = document.getElementById('id_habilitation');
    if (!select) return;
    
    const habilitation = select.value;
    
    // Vérifier si des permissions sont déjà cochées
    const currentCount = countActivePermissions();
    
    if (currentCount > 0 && habilitation) {
        // Demander confirmation avant d'écraser
        const habLabel = select.options[select.selectedIndex].text;
        if (confirm(`Voulez-vous appliquer les permissions par défaut du rôle "${habLabel}" ?\n\nCela remplacera les ${currentCount} permission(s) actuellement cochée(s).`)) {
            applyPermissionsForHabilitation(habilitation);
        }
    } else if (habilitation) {
        applyPermissionsForHabilitation(habilitation);
    } else {
        resetAllPermissions();
    }
}

/**
 * Vérifie si une habilitation a une permission spécifique
 * @param {string} habilitation - Le code de l'habilitation
 * @param {string} permission - Le code de la permission
 * @returns {boolean}
 */
function habilitationHasPermission(habilitation, permission) {
    const permissions = PERMISSIONS_PAR_HABILITATION[habilitation];
    return permissions ? permissions.includes(permission) : false;
}

/**
 * Retourne la liste des habilitations ayant une permission donnée
 * @param {string} permission - Le code de la permission
 * @returns {Array} - Liste des habilitations
 */
function getHabilitationsWithPermission(permission) {
    const result = [];
    Object.keys(PERMISSIONS_PAR_HABILITATION).forEach(hab => {
        if (PERMISSIONS_PAR_HABILITATION[hab].includes(permission)) {
            result.push(hab);
        }
    });
    return result;
}

/**
 * Retourne le nombre de permissions pour une habilitation
 * @param {string} habilitation - Le code de l'habilitation
 * @returns {number}
 */
function countPermissionsForHabilitation(habilitation) {
    const permissions = PERMISSIONS_PAR_HABILITATION[habilitation];
    return permissions ? permissions.length : 0;
}


// ═══════════════════════════════════════════════════════════════════
// INITIALISATION
// ═══════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', function() {
    // Ajouter l'écouteur sur le changement d'habilitation
    const habSelect = document.getElementById('id_habilitation');
    if (habSelect) {
        // Pour la création: appliquer automatiquement au changement
        if (document.getElementById('form-creer-utilisateur')) {
            habSelect.addEventListener('change', handleHabilitationChange);
        }
        // Pour la modification: ne pas appliquer automatiquement (garder les valeurs existantes)
    }
    
    // Ajouter l'écouteur sur tous les checkboxes de permissions
    TOUTES_PERMISSIONS.forEach(perm => {
        const checkbox = document.getElementById('id_' + perm);
        if (checkbox) {
            checkbox.addEventListener('change', updatePermissionsIndicator);
        }
    });
    
    // Mettre à jour l'indicateur initial
    updatePermissionsIndicator();
    
    // Log pour debug
    console.log('SUPPER Permissions Manager chargé');
    console.log(`Total habilitations: ${Object.keys(PERMISSIONS_PAR_HABILITATION).length}`);
    console.log(`Total permissions: ${TOUTES_PERMISSIONS.length}`);
});


// ═══════════════════════════════════════════════════════════════════
// EXPORT (si utilisé comme module)
// ═══════════════════════════════════════════════════════════════════

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        PERMISSIONS_PAR_HABILITATION,
        TOUTES_PERMISSIONS,
        CATEGORIES_PERMISSIONS,
        applyPermissionsForHabilitation,
        resetAllPermissions,
        checkAllPermissions,
        countActivePermissions,
        habilitationHasPermission,
        getHabilitationsWithPermission,
        countPermissionsForHabilitation
    };
}