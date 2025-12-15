/**
 * SUPPER - Gestion automatique des permissions par habilitation
 * Mapping basé sur le document officiel Habilitations.pdf
 */

const PERMISSIONS_PAR_HABILITATION = {
    // ADMINISTRATEUR PRINCIPAL - Accès complet
    'admin_principal': [
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

    // COORDONNATEUR PSRR - Accès complet
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

    // SERVICE INFORMATIQUE - Accès complet
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

    // SERVICE EMISSIONS ET RECOUVREMENT
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

    // SERVICE DES AFFAIRES GENERALES (Chef AG)
    'chef_ag': [
        // Gestion
        'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
        'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit',
        // Autres
        'peut_parametrage_global'
    ],

    // SERVICE CONTROLE ET VALIDATION
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

    // SERVICE ORDRE/SECRETARIAT
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

    // IMPRIMERIE NATIONALE
    'imprimerie': [
        // Stock Péage - Historique uniquement
        'peut_voir_historique_stock_peage'
    ],

    // CISOP PEAGE
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

    // CISOP PESAGE
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

    // CHEF DE POSTE (Péage)
    'chef_poste': [
        // Inventaires
        'peut_saisir_inventaire_normal', 'peut_voir_liste_inventaires',
        'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
        // Recettes Péage
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        // Quittances Péage
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        // Stock Péage
        'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage', 'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage',
        // Rapports
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_peage_deperdition', 'peut_voir_classement_agents_inventaire',
        // Autres
        'peut_voir_compte_emploi', 'peut_voir_pv_confrontation', 'peut_authentifier_document'
    ],

    // CHEF DE STATION (Pesage)
    'chef_station_pesage': [
        // Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
        'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        // Rapports
        'peut_voir_classement_station_pesage',
        // Autres
        'peut_voir_pv_confrontation', 'peut_authentifier_document'
    ],

    // REGISSEUR DE STATION (Pesage)
    'regisseur_pesage': [
        // Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
        'peut_saisir_quittance_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        // Rapports
        'peut_voir_classement_station_pesage'
    ],

    // CHEF D'EQUIPE STATION (Pesage)
    'chef_equipe_pesage': [
        // Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_voir_liste_quittancements_pesage', 'peut_voir_historique_pesees', 'peut_voir_stats_pesage'
    ],

    // AGENT INVENTAIRE
    'agent_inventaire': [
        // Inventaires - Saisie uniquement
        'peut_saisir_inventaire_normal'
    ]
};

// Liste complète des 58 permissions (selon le PDF)
const TOUTES_PERMISSIONS = [
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
];

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
    const categories = {
        'inventaires': ['peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin', 'peut_programmer_inventaire',
            'peut_voir_programmation_active', 'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
            'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin', 'peut_voir_jours_impertinents',
            'peut_voir_stats_deperdition'],
        'recettes-peage': ['peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
            'peut_importer_recettes_peage', 'peut_voir_evolution_peage', 'peut_voir_objectifs_peage'],
        'quittances-peage': ['peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage'],
        'pesage': ['peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
            'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
            'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
            'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage'],
        'stock-peage': ['peut_charger_stock_peage', 'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
            'peut_transferer_stock_peage', 'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
            'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage', 'peut_simuler_commandes_peage'],
        'gestion': ['peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
            'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit'],
        'rapports': ['peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
            'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
            'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
            'peut_voir_classement_agents_inventaire'],
        'autres': ['peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
            'peut_authentifier_document', 'peut_voir_tous_postes']
    };
    
    Object.keys(categories).forEach(cat => {
        const badge = document.getElementById('count-' + cat);
        if (badge) {
            let count = 0;
            categories[cat].forEach(perm => {
                const checkbox = document.getElementById('id_' + perm);
                if (checkbox && checkbox.checked) count++;
            });
            badge.textContent = `${count}/${categories[cat].length}`;
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
    const container = document.getElementById(categoryId);
    if (container) {
        container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.checked = true;
        });
        updatePermissionsIndicator();
    }
}

/**
 * Décoche toutes les permissions d'une catégorie
 * @param {string} categoryId - L'ID de la catégorie
 */
function uncheckAllInCategory(categoryId) {
    const container = document.getElementById(categoryId);
    if (container) {
        container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
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
        if (confirm(`Voulez-vous appliquer les permissions par défaut du rôle "${select.options[select.selectedIndex].text}" ?\n\nCela remplacera les ${currentCount} permission(s) actuellement cochée(s).`)) {
            applyPermissionsForHabilitation(habilitation);
        }
    } else if (habilitation) {
        applyPermissionsForHabilitation(habilitation);
    } else {
        resetAllPermissions();
    }
}

/**
 * Initialisation au chargement de la page
 */
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
});