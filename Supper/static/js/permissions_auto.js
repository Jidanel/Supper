/**
 * ===================================================================
 * SUPPER - Gestion automatique des permissions par habilitation
 * ===================================================================
 * Ce fichier contient le mapping complet entre chaque habilitation (rôle)
 * et ses permissions granulaires. Quand l'utilisateur sélectionne une
 * habilitation, les checkboxes correspondantes sont automatiquement cochées.
 * ===================================================================
 */

// ===================================================================
// DÉFINITION DES PERMISSIONS PAR CATÉGORIE
// ===================================================================

const TOUTES_PERMISSIONS = {
    // Permissions globales
    globales: [
        'acces_tous_postes',
        'peut_saisir_peage',
        'peut_saisir_pesage',
        'voir_recettes_potentielles',
        'voir_taux_deperdition',
        'voir_statistiques_globales',
        'peut_saisir_pour_autres_postes',
    ],
    
    // Anciennes permissions modules (rétrocompatibilité)
    modules: [
        'peut_gerer_peage',
        'peut_gerer_pesage',
        'peut_gerer_personnel',
        'peut_gerer_budget',
        'peut_gerer_inventaire',
        'peut_gerer_archives',
        'peut_gerer_stocks_psrr',
        'peut_gerer_stock_info',
    ],
    
    // Permissions Inventaires
    inventaires: [
        'peut_saisir_inventaire_normal',
        'peut_saisir_inventaire_admin',
        'peut_programmer_inventaire',
        'peut_voir_programmation_active',
        'peut_desactiver_programmation',
        'peut_voir_programmation_desactivee',
        'peut_voir_liste_inventaires',
        'peut_voir_liste_inventaires_admin',
        'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
    ],
    
    // Permissions Recettes Péage
    recettes_peage: [
        'peut_saisir_recette_peage',
        'peut_voir_liste_recettes_peage',
        'peut_voir_stats_recettes_peage',
        'peut_importer_recettes_peage',
        'peut_voir_evolution_peage',
        'peut_voir_objectifs_peage',
    ],
    
    // Permissions Quittances Péage
    quittances_peage: [
        'peut_saisir_quittance_peage',
        'peut_voir_liste_quittances_peage',
        'peut_comptabiliser_quittances_peage',
    ],
    
    // Permissions Pesage
    pesage: [
        'peut_voir_historique_vehicule_pesage',
        'peut_saisir_amende',
        'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage',
        'peut_valider_paiement_amende',
        'peut_lister_amendes',
        'peut_saisir_quittance_pesage',
        'peut_comptabiliser_quittances_pesage',
        'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees',
        'peut_voir_recettes_pesage',
        'peut_voir_stats_pesage',
    ],
    
    // Permissions Stock Péage
    stock_peage: [
        'peut_charger_stock_peage',
        'peut_voir_liste_stocks_peage',
        'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage',
        'peut_voir_tracabilite_tickets',
        'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage',
        'peut_voir_historique_stock_peage',
        'peut_simuler_commandes_peage',
    ],
    
    // Permissions Gestion
    gestion: [
        'peut_gerer_postes',
        'peut_ajouter_poste',
        'peut_creer_poste_masse',
        'peut_gerer_utilisateurs',
        'peut_creer_utilisateur',
        'peut_voir_journal_audit',
    ],
    
    // Permissions Rapports
    rapports: [
        'peut_voir_rapports_defaillants_peage',
        'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires',
        'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage',
        'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
    ],
    
    // Permissions Autres
    autres: [
        'peut_parametrage_global',
        'peut_voir_compte_emploi',
        'peut_voir_pv_confrontation',
        'peut_authentifier_document',
        'peut_voir_tous_postes',
    ],
};

// Fonction utilitaire pour obtenir toutes les permissions en une seule liste
function getToutesPermissions() {
    let toutes = [];
    for (let categorie in TOUTES_PERMISSIONS) {
        toutes = toutes.concat(TOUTES_PERMISSIONS[categorie]);
    }
    return toutes;
}

// ===================================================================
// MAPPING COMPLET DES PERMISSIONS PAR HABILITATION
// Basé sur les méthodes _configurer_* du modèle UtilisateurSUPPER
// ===================================================================

const PERMISSIONS_PAR_HABILITATION = {
    
    // ===================================================================
    // ADMINISTRATEUR PRINCIPAL - Toutes les permissions
    // ===================================================================
    'admin_principal': getToutesPermissions(),
    
    // ===================================================================
    // COORDONNATEUR PSRR - Toutes les permissions
    // ===================================================================
    'coord_psrr': getToutesPermissions(),
    
    // ===================================================================
    // SERVICE INFORMATIQUE - Toutes les permissions
    // ===================================================================
    'serv_info': getToutesPermissions(),
    
    // ===================================================================
    // SERVICE ÉMISSION ET RECOUVREMENT
    // ===================================================================
    'serv_emission': [
        // Globales
        'acces_tous_postes',
        'peut_saisir_peage',
        'voir_recettes_potentielles',
        'voir_taux_deperdition',
        'voir_statistiques_globales',
        'peut_saisir_pour_autres_postes',
        
        // Modules
        'peut_gerer_peage',
        'peut_gerer_inventaire',
        'peut_gerer_stocks_psrr',
        
        // Inventaires
        'peut_voir_programmation_active',
        'peut_voir_liste_inventaires',
        'peut_voir_liste_inventaires_admin',
        'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        
        // Recettes Péage
        'peut_saisir_recette_peage',
        'peut_voir_liste_recettes_peage',
        'peut_voir_stats_recettes_peage',
        'peut_importer_recettes_peage',
        'peut_voir_evolution_peage',
        'peut_voir_objectifs_peage',
        
        // Quittances Péage
        'peut_saisir_quittance_peage',
        'peut_voir_liste_quittances_peage',
        'peut_comptabiliser_quittances_peage',
        
        // Stock Péage
        'peut_charger_stock_peage',
        'peut_voir_liste_stocks_peage',
        'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage',
        'peut_voir_tracabilite_tickets',
        'peut_voir_bordereaux_peage',
        'peut_voir_historique_stock_peage',
        'peut_simuler_commandes_peage',
        
        // Rapports
        'peut_voir_rapports_defaillants_peage',
        'peut_voir_rapport_inventaires',
        'peut_voir_classement_peage_rendement',
        'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        
        // Autres
        'peut_authentifier_document',
        'peut_voir_tous_postes',
    ],
    
    // ===================================================================
    // CHEF SERVICE AFFAIRES GÉNÉRALES
    // ===================================================================
    'chef_ag': [
        // Globales
        'acces_tous_postes',
        'voir_statistiques_globales',
        
        // Modules
        'peut_gerer_personnel',
        'peut_gerer_archives',
        
        // Gestion
        'peut_gerer_utilisateurs',
        'peut_creer_utilisateur',
        'peut_voir_journal_audit',
        
        // Rapports
        'peut_voir_rapports_defaillants_peage',
        'peut_voir_rapports_defaillants_pesage',
        'peut_voir_classement_agents_inventaire',
        
        // Autres
        'peut_voir_compte_emploi',
        'peut_voir_pv_confrontation',
        'peut_authentifier_document',
        'peut_voir_tous_postes',
    ],
    
    // ===================================================================
    // SERVICE CONTRÔLE ET VALIDATION
    // ===================================================================
    'serv_controle': [
        // Globales
        'acces_tous_postes',
        'voir_recettes_potentielles',
        'voir_taux_deperdition',
        'voir_statistiques_globales',
        
        // Modules
        'peut_gerer_archives',
        
        // Inventaires
        'peut_voir_programmation_active',
        'peut_voir_liste_inventaires',
        'peut_voir_liste_inventaires_admin',
        'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        
        // Recettes Péage
        'peut_voir_liste_recettes_peage',
        'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage',
        
        // Quittances Péage
        'peut_voir_liste_quittances_peage',
        
        // Pesage
        'peut_voir_historique_pesees',
        'peut_voir_recettes_pesage',
        'peut_voir_stats_pesage',
        'peut_lister_amendes',
        'peut_voir_liste_quittancements_pesage',
        
        // Stock Péage
        'peut_voir_liste_stocks_peage',
        'peut_voir_tracabilite_tickets',
        'peut_voir_bordereaux_peage',
        
        // Rapports
        'peut_voir_rapports_defaillants_peage',
        'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires',
        'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage',
        'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        
        // Autres
        'peut_voir_pv_confrontation',
        'peut_authentifier_document',
        'peut_voir_tous_postes',
    ],
    
    // ===================================================================
    // SERVICE ORDRE / SECRÉTARIAT
    // ===================================================================
    'serv_ordre': [
        // Globales
        'acces_tous_postes',
        'voir_statistiques_globales',
        
        // Modules
        'peut_gerer_archives',
        
        // Inventaires
        'peut_voir_liste_inventaires',
        
        // Recettes Péage
        'peut_voir_liste_recettes_peage',
        
        // Quittances Péage
        'peut_voir_liste_quittances_peage',
        
        // Pesage
        'peut_voir_recettes_pesage',
        'peut_lister_amendes',
        'peut_voir_liste_quittancements_pesage',
        
        // Rapports
        'peut_voir_rapport_inventaires',
        
        // Autres
        'peut_authentifier_document',
        'peut_voir_tous_postes',
    ],
    
    // ===================================================================
    // IMPRIMERIE NATIONALE
    // ===================================================================
    'imprimerie': [
        // Globales
        'acces_tous_postes',
        
        // Modules
        'peut_gerer_stocks_psrr',
        
        // Stock Péage
        'peut_charger_stock_peage',
        'peut_voir_liste_stocks_peage',
        'peut_voir_stock_date_peage',
        'peut_voir_tracabilite_tickets',
        'peut_voir_bordereaux_peage',
        'peut_voir_historique_stock_peage',
        'peut_simuler_commandes_peage',
        
        // Autres
        'peut_voir_tous_postes',
    ],
    
    // ===================================================================
    // CISOP PÉAGE
    // ===================================================================
    'cisop_peage': [
        // Globales
        'acces_tous_postes',
        'peut_saisir_peage',
        'voir_recettes_potentielles',
        'voir_taux_deperdition',
        'voir_statistiques_globales',
        'peut_saisir_pour_autres_postes',
        
        // Modules
        'peut_gerer_peage',
        'peut_gerer_inventaire',
        
        // Inventaires
        'peut_saisir_inventaire_admin',
        'peut_programmer_inventaire',
        'peut_voir_programmation_active',
        'peut_desactiver_programmation',
        'peut_voir_programmation_desactivee',
        'peut_voir_liste_inventaires',
        'peut_voir_liste_inventaires_admin',
        'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        
        // Recettes Péage
        'peut_saisir_recette_peage',
        'peut_voir_liste_recettes_peage',
        'peut_voir_stats_recettes_peage',
        'peut_importer_recettes_peage',
        'peut_voir_evolution_peage',
        'peut_voir_objectifs_peage',
        
        // Quittances Péage
        'peut_saisir_quittance_peage',
        'peut_voir_liste_quittances_peage',
        'peut_comptabiliser_quittances_peage',
        
        // Stock Péage
        'peut_charger_stock_peage',
        'peut_voir_liste_stocks_peage',
        'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage',
        'peut_voir_tracabilite_tickets',
        'peut_voir_bordereaux_peage',
        'peut_voir_historique_stock_peage',
        
        // Rapports
        'peut_voir_rapports_defaillants_peage',
        'peut_voir_rapport_inventaires',
        'peut_voir_classement_peage_rendement',
        'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        
        // Autres
        'peut_voir_tous_postes',
    ],
    
    // ===================================================================
    // CISOP PESAGE
    // ===================================================================
    'cisop_pesage': [
        // Globales
        'acces_tous_postes',
        'peut_saisir_pesage',
        'voir_statistiques_globales',
        'peut_saisir_pour_autres_postes',
        
        // Modules
        'peut_gerer_pesage',
        
        // Pesage
        'peut_voir_historique_vehicule_pesage',
        'peut_saisir_amende',
        'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage',
        'peut_valider_paiement_amende',
        'peut_lister_amendes',
        'peut_saisir_quittance_pesage',
        'peut_comptabiliser_quittances_pesage',
        'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees',
        'peut_voir_recettes_pesage',
        'peut_voir_stats_pesage',
        
        // Rapports
        'peut_voir_rapports_defaillants_pesage',
        'peut_voir_classement_station_pesage',
        
        // Autres
        'peut_voir_tous_postes',
    ],
    
    // ===================================================================
    // POINT FOCAL RÉGIONAL
    // ===================================================================
    'focal_regional': [
        // Globales
        'acces_tous_postes',
        'peut_saisir_peage',
        'peut_saisir_pesage',
        'voir_recettes_potentielles',
        'voir_taux_deperdition',
        'voir_statistiques_globales',
        
        // Modules
        'peut_gerer_inventaire',
        
        // Inventaires
        'peut_voir_programmation_active',
        'peut_voir_liste_inventaires',
        'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        
        // Recettes Péage
        'peut_voir_liste_recettes_peage',
        'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage',
        
        // Quittances Péage
        'peut_voir_liste_quittances_peage',
        
        // Pesage
        'peut_voir_historique_pesees',
        'peut_voir_recettes_pesage',
        'peut_voir_stats_pesage',
        'peut_lister_amendes',
        'peut_voir_liste_quittancements_pesage',
        
        // Stock Péage
        'peut_voir_liste_stocks_peage',
        
        // Rapports
        'peut_voir_rapports_defaillants_peage',
        'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires',
        'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage',
        'peut_voir_classement_peage_deperdition',
        
        // Autres
        'peut_voir_tous_postes',
    ],
    
    // ===================================================================
    // CHEF DE SERVICE
    // ===================================================================
    'chef_service': [
        // Globales
        'acces_tous_postes',
        'voir_statistiques_globales',
        
        // Inventaires
        'peut_voir_programmation_active',
        'peut_voir_liste_inventaires',
        'peut_voir_stats_deperdition',
        
        // Recettes Péage
        'peut_voir_liste_recettes_peage',
        'peut_voir_stats_recettes_peage',
        
        // Quittances Péage
        'peut_voir_liste_quittances_peage',
        
        // Pesage
        'peut_voir_recettes_pesage',
        'peut_voir_stats_pesage',
        'peut_lister_amendes',
        'peut_voir_liste_quittancements_pesage',
        
        // Rapports
        'peut_voir_rapport_inventaires',
        
        // Autres
        'peut_voir_tous_postes',
    ],
    
    // ===================================================================
    // RÉGISSEUR CENTRAL
    // ===================================================================
    'regisseur': [
        // Globales
        'acces_tous_postes',
        'voir_recettes_potentielles',
        'voir_taux_deperdition',
        'voir_statistiques_globales',
        
        // Modules
        'peut_gerer_budget',
        
        // Recettes Péage
        'peut_voir_liste_recettes_peage',
        'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage',
        'peut_voir_objectifs_peage',
        
        // Quittances Péage
        'peut_voir_liste_quittances_peage',
        'peut_comptabiliser_quittances_peage',
        
        // Pesage
        'peut_voir_recettes_pesage',
        'peut_voir_stats_pesage',
        'peut_lister_amendes',
        'peut_comptabiliser_quittances_pesage',
        'peut_voir_liste_quittancements_pesage',
        
        // Rapports
        'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage',
        
        // Autres
        'peut_voir_compte_emploi',
        'peut_voir_tous_postes',
    ],
    
    // ===================================================================
    // COMPTABLE MATIÈRES
    // ===================================================================
    'comptable_mat': [
        // Globales
        'acces_tous_postes',
        
        // Modules
        'peut_gerer_archives',
        'peut_gerer_stocks_psrr',
        
        // Stock Péage
        'peut_voir_liste_stocks_peage',
        'peut_voir_stock_date_peage',
        'peut_voir_tracabilite_tickets',
        'peut_voir_bordereaux_peage',
        'peut_voir_historique_stock_peage',
        
        // Autres
        'peut_voir_compte_emploi',
        'peut_voir_tous_postes',
    ],
    
    // ===================================================================
    // CHEF DE POSTE PÉAGE
    // ===================================================================
    'chef_peage': [
        // Globales
        'peut_saisir_peage',
        'voir_recettes_potentielles',
        'voir_taux_deperdition',
        
        // Modules
        'peut_gerer_peage',
        'peut_gerer_inventaire',
        
        // Inventaires
        'peut_saisir_inventaire_normal',
        'peut_voir_programmation_active',
        'peut_voir_liste_inventaires',
        'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        
        // Recettes Péage
        'peut_saisir_recette_peage',
        'peut_voir_liste_recettes_peage',
        'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage',
        
        // Quittances Péage
        'peut_saisir_quittance_peage',
        'peut_voir_liste_quittances_peage',
        
        // Stock Péage
        'peut_voir_liste_stocks_peage',
        'peut_voir_mon_stock_peage',
        'peut_voir_historique_stock_peage',
        
        // Rapports
        'peut_voir_rapport_inventaires',
    ],
    
    // ===================================================================
    // AGENT INVENTAIRE
    // ===================================================================
    'agent_inventaire': [
        // Modules
        'peut_gerer_inventaire',
        
        // Inventaires
        'peut_saisir_inventaire_normal',
        'peut_voir_programmation_active',
        'peut_voir_liste_inventaires',
    ],
    
    // ===================================================================
    // CHEF DE STATION PESAGE
    // ===================================================================
    'chef_station_pesage': [
        // Globales
        'peut_saisir_pesage',
        
        // Modules
        'peut_gerer_pesage',
        
        // Pesage
        'peut_voir_historique_vehicule_pesage',
        'peut_saisir_amende',
        'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage',
        'peut_valider_paiement_amende',
        'peut_lister_amendes',
        'peut_saisir_quittance_pesage',
        'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees',
        'peut_voir_recettes_pesage',
        'peut_voir_stats_pesage',
    ],
    
    // Alias pour compatibilité
    'chef_pesage': [], // Sera copié depuis chef_station_pesage
    
    // ===================================================================
    // RÉGISSEUR DE STATION PESAGE
    // ===================================================================
    'regisseur_pesage': [
        // Globales
        'peut_saisir_pesage',
        
        // Modules
        'peut_gerer_pesage',
        'peut_gerer_budget',
        
        // Pesage
        'peut_voir_historique_vehicule_pesage',
        'peut_saisir_amende',
        'peut_voir_objectifs_pesage',
        'peut_valider_paiement_amende',
        'peut_lister_amendes',
        'peut_saisir_quittance_pesage',
        'peut_comptabiliser_quittances_pesage',
        'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees',
        'peut_voir_recettes_pesage',
        'peut_voir_stats_pesage',
        
        // Autres
        'peut_voir_compte_emploi',
    ],
    
    // ===================================================================
    // CHEF D'ÉQUIPE PESAGE
    // ===================================================================
    'chef_equipe_pesage': [
        // Globales
        'peut_saisir_pesage',
        
        // Pesage
        'peut_voir_historique_vehicule_pesage',
        'peut_saisir_amende',
        'peut_saisir_pesee_jour',
        'peut_lister_amendes',
        'peut_voir_historique_pesees',
    ],
    
    // ===================================================================
    // CAISSIER
    // ===================================================================
    'caissier': [
        // Quittances Péage
        'peut_saisir_quittance_peage',
        'peut_voir_liste_quittances_peage',
        
        // Stock Péage
        'peut_voir_mon_stock_peage',
    ],
};

// Copier les permissions de chef_station_pesage vers chef_pesage (alias)
PERMISSIONS_PAR_HABILITATION['chef_pesage'] = PERMISSIONS_PAR_HABILITATION['chef_station_pesage'];

// Alias pour serv_ordre et serv_controle (anciens noms)
PERMISSIONS_PAR_HABILITATION['chef_ordre'] = PERMISSIONS_PAR_HABILITATION['serv_ordre'];
PERMISSIONS_PAR_HABILITATION['chef_controle'] = PERMISSIONS_PAR_HABILITATION['serv_controle'];


// ===================================================================
// FONCTIONS DE GESTION DES CHECKBOXES
// ===================================================================

/**
 * Décoche toutes les permissions
 */
function decocherToutesPermissions() {
    const toutesPermissions = getToutesPermissions();
    toutesPermissions.forEach(permission => {
        const checkbox = document.getElementById('id_' + permission);
        if (checkbox) {
            checkbox.checked = false;
        }
    });
}

/**
 * Coche les permissions pour une habilitation donnée
 * @param {string} habilitation - Le code de l'habilitation
 */
function cocherPermissionsPourHabilitation(habilitation) {
    // D'abord décocher toutes les permissions
    decocherToutesPermissions();
    
    // Si aucune habilitation sélectionnée, ne rien faire de plus
    if (!habilitation || habilitation === '') {
        return;
    }
    
    // Récupérer les permissions pour cette habilitation
    const permissions = PERMISSIONS_PAR_HABILITATION[habilitation];
    
    if (!permissions) {
        console.warn('Habilitation non reconnue:', habilitation);
        return;
    }
    
    // Cocher chaque permission
    permissions.forEach(permission => {
        const checkbox = document.getElementById('id_' + permission);
        if (checkbox) {
            checkbox.checked = true;
        } else {
            // Essayer avec un préfixe différent au cas où
            const altCheckbox = document.querySelector(`input[name="${permission}"]`);
            if (altCheckbox) {
                altCheckbox.checked = true;
            }
        }
    });
    
    // Mettre à jour l'aperçu des permissions si la fonction existe
    if (typeof updatePermissionsPreview === 'function') {
        updatePermissionsPreview();
    }
    
    // Log pour debug
    console.log(`Permissions cochées pour ${habilitation}:`, permissions.length);
}

/**
 * Initialise les event listeners pour la gestion automatique des permissions
 */
function initPermissionsAutoCheck() {
    const habilitationSelect = document.getElementById('id_habilitation');
    
    if (!habilitationSelect) {
        console.warn('Select habilitation non trouvé');
        return;
    }
    
    // Écouter les changements d'habilitation
    habilitationSelect.addEventListener('change', function(e) {
        const habilitation = e.target.value;
        cocherPermissionsPourHabilitation(habilitation);
    });
    
    // Appliquer les permissions pour l'habilitation actuellement sélectionnée
    // (utile si le formulaire est pré-rempli)
    if (habilitationSelect.value) {
        // Vérifier si c'est un formulaire de création (pas de modification)
        const isCreation = document.querySelector('form[action*="creer"]') || 
                          !document.querySelector('input[name="is_active"]')?.checked;
        
        // En création, toujours appliquer les permissions par défaut
        // En modification, ne pas écraser les permissions existantes automatiquement
        if (isCreation) {
            cocherPermissionsPourHabilitation(habilitationSelect.value);
        }
    }
    
    console.log('Système de permissions automatiques initialisé');
}

/**
 * Coche/décoche toutes les permissions d'une catégorie
 * @param {string} categorie - Le nom de la catégorie
 * @param {boolean} cocher - True pour cocher, false pour décocher
 */
function toggleCategoriePermissions(categorie, cocher) {
    const permissions = TOUTES_PERMISSIONS[categorie];
    if (!permissions) {
        console.warn('Catégorie non reconnue:', categorie);
        return;
    }
    
    permissions.forEach(permission => {
        const checkbox = document.getElementById('id_' + permission);
        if (checkbox) {
            checkbox.checked = cocher;
        }
    });
}

/**
 * Obtient le nombre de permissions cochées pour une catégorie
 * @param {string} categorie - Le nom de la catégorie
 * @returns {number} Le nombre de permissions cochées
 */
function getPermissionsCocheesCategorie(categorie) {
    const permissions = TOUTES_PERMISSIONS[categorie];
    if (!permissions) return 0;
    
    let count = 0;
    permissions.forEach(permission => {
        const checkbox = document.getElementById('id_' + permission);
        if (checkbox && checkbox.checked) {
            count++;
        }
    });
    
    return count;
}

/**
 * Met à jour l'indicateur de progression des permissions
 */
function updatePermissionsIndicateur() {
    const total = getToutesPermissions().length;
    let cochees = 0;
    
    getToutesPermissions().forEach(permission => {
        const checkbox = document.getElementById('id_' + permission);
        if (checkbox && checkbox.checked) {
            cochees++;
        }
    });
    
    const indicateur = document.getElementById('permissions-count');
    if (indicateur) {
        indicateur.textContent = `${cochees} / ${total} permissions`;
    }
    
    const progressBar = document.getElementById('permissions-progress');
    if (progressBar) {
        const percentage = (cochees / total) * 100;
        progressBar.style.width = `${percentage}%`;
        progressBar.setAttribute('aria-valuenow', percentage);
    }
}


// ===================================================================
// INITIALISATION AU CHARGEMENT DE LA PAGE
// ===================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Initialiser la gestion automatique des permissions
    initPermissionsAutoCheck();
    
    // Ajouter des listeners pour mettre à jour l'indicateur
    getToutesPermissions().forEach(permission => {
        const checkbox = document.getElementById('id_' + permission);
        if (checkbox) {
            checkbox.addEventListener('change', updatePermissionsIndicateur);
        }
    });
    
    // Mise à jour initiale de l'indicateur
    updatePermissionsIndicateur();
});


// ===================================================================
// EXPORT POUR UTILISATION EXTERNE
// ===================================================================

// Exposer les fonctions globalement pour utilisation dans les templates
window.SUPPER_PERMISSIONS = {
    TOUTES_PERMISSIONS: TOUTES_PERMISSIONS,
    PERMISSIONS_PAR_HABILITATION: PERMISSIONS_PAR_HABILITATION,
    getToutesPermissions: getToutesPermissions,
    cocherPermissionsPourHabilitation: cocherPermissionsPourHabilitation,
    decocherToutesPermissions: decocherToutesPermissions,
    toggleCategoriePermissions: toggleCategoriePermissions,
    getPermissionsCocheesCategorie: getPermissionsCocheesCategorie,
    updatePermissionsIndicateur: updatePermissionsIndicateur,
};