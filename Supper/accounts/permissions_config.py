# ===================================================================
# accounts/permissions_config.py - Configuration des permissions par habilitation
# ===================================================================
# 
# Ce fichier centralise le mapping des permissions par habilitation.
# Il est utilisé à la fois côté serveur (Python) et côté client (JSON → JavaScript)
#
# IMPORTANT: Ce dictionnaire DOIT rester synchronisé avec les méthodes 
# _configurer_XXX du modèle UtilisateurSUPPER
# ===================================================================

from django.utils.translation import gettext_lazy as _

# ===================================================================
# LISTE COMPLÈTE DES 58 PERMISSIONS GRANULAIRES
# ===================================================================

TOUTES_PERMISSIONS = [
    # Inventaires (10)
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
    
    # Recettes Péage (6)
    'peut_saisir_recette_peage',
    'peut_voir_liste_recettes_peage',
    'peut_voir_stats_recettes_peage',
    'peut_importer_recettes_peage',
    'peut_voir_evolution_peage',
    'peut_voir_objectifs_peage',
    
    # Quittances Péage (3)
    'peut_saisir_quittance_peage',
    'peut_voir_liste_quittances_peage',
    'peut_comptabiliser_quittances_peage',
    
    # Pesage (12)
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
    
    # Stock Péage (9)
    'peut_charger_stock_peage',
    'peut_voir_liste_stocks_peage',
    'peut_voir_stock_date_peage',
    'peut_transferer_stock_peage',
    'peut_voir_tracabilite_tickets',
    'peut_voir_bordereaux_peage',
    'peut_voir_mon_stock_peage',
    'peut_voir_historique_stock_peage',
    'peut_simuler_commandes_peage',
    
    # Gestion (6)
    'peut_gerer_postes',
    'peut_ajouter_poste',
    'peut_creer_poste_masse',
    'peut_gerer_utilisateurs',
    'peut_creer_utilisateur',
    'peut_voir_journal_audit',
    
    # Rapports (7)
    'peut_voir_rapports_defaillants_peage',
    'peut_voir_rapports_defaillants_pesage',
    'peut_voir_rapport_inventaires',
    'peut_voir_classement_peage_rendement',
    'peut_voir_classement_station_pesage',
    'peut_voir_classement_peage_deperdition',
    'peut_voir_classement_agents_inventaire',
    
    # Autres (5)
    'peut_parametrage_global',
    'peut_voir_compte_emploi',
    'peut_voir_pv_confrontation',
    'peut_authentifier_document',
    'peut_voir_tous_postes',
]


# ===================================================================
# CATÉGORIES DE PERMISSIONS (pour l'accordéon dans l'interface)
# ===================================================================

CATEGORIES_PERMISSIONS = {
    'inventaires': {
        'label': _('Inventaires'),
        'icon': 'fas fa-clipboard-list',
        'permissions': [
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
        ]
    },
    'recettes_peage': {
        'label': _('Recettes Péage'),
        'icon': 'fas fa-cash-register',
        'permissions': [
            'peut_saisir_recette_peage',
            'peut_voir_liste_recettes_peage',
            'peut_voir_stats_recettes_peage',
            'peut_importer_recettes_peage',
            'peut_voir_evolution_peage',
            'peut_voir_objectifs_peage',
        ]
    },
    'quittances_peage': {
        'label': _('Quittances Péage'),
        'icon': 'fas fa-receipt',
        'permissions': [
            'peut_saisir_quittance_peage',
            'peut_voir_liste_quittances_peage',
            'peut_comptabiliser_quittances_peage',
        ]
    },
    'pesage': {
        'label': _('Pesage'),
        'icon': 'fas fa-weight',
        'permissions': [
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
        ]
    },
    'stock_peage': {
        'label': _('Stock Péage'),
        'icon': 'fas fa-boxes',
        'permissions': [
            'peut_charger_stock_peage',
            'peut_voir_liste_stocks_peage',
            'peut_voir_stock_date_peage',
            'peut_transferer_stock_peage',
            'peut_voir_tracabilite_tickets',
            'peut_voir_bordereaux_peage',
            'peut_voir_mon_stock_peage',
            'peut_voir_historique_stock_peage',
            'peut_simuler_commandes_peage',
        ]
    },
    'gestion': {
        'label': _('Gestion'),
        'icon': 'fas fa-cogs',
        'permissions': [
            'peut_gerer_postes',
            'peut_ajouter_poste',
            'peut_creer_poste_masse',
            'peut_gerer_utilisateurs',
            'peut_creer_utilisateur',
            'peut_voir_journal_audit',
        ]
    },
    'rapports': {
        'label': _('Rapports'),
        'icon': 'fas fa-chart-bar',
        'permissions': [
            'peut_voir_rapports_defaillants_peage',
            'peut_voir_rapports_defaillants_pesage',
            'peut_voir_rapport_inventaires',
            'peut_voir_classement_peage_rendement',
            'peut_voir_classement_station_pesage',
            'peut_voir_classement_peage_deperdition',
            'peut_voir_classement_agents_inventaire',
        ]
    },
    'autres': {
        'label': _('Autres'),
        'icon': 'fas fa-ellipsis-h',
        'permissions': [
            'peut_parametrage_global',
            'peut_voir_compte_emploi',
            'peut_voir_pv_confrontation',
            'peut_authentifier_document',
            'peut_voir_tous_postes',
        ]
    },
}


# ===================================================================
# LABELS DES PERMISSIONS (pour affichage en français)
# ===================================================================

LABELS_PERMISSIONS = {
    # Inventaires
    'peut_saisir_inventaire_normal': _("Saisir inventaire normal"),
    'peut_saisir_inventaire_admin': _("Saisir inventaire administratif"),
    'peut_programmer_inventaire': _("Programmer inventaire"),
    'peut_voir_programmation_active': _("Voir programmation active"),
    'peut_desactiver_programmation': _("Désactiver programmation"),
    'peut_voir_programmation_desactivee': _("Voir programmations désactivées"),
    'peut_voir_liste_inventaires': _("Liste inventaires normaux"),
    'peut_voir_liste_inventaires_admin': _("Liste inventaires administratifs"),
    'peut_voir_jours_impertinents': _("Jours impertinents"),
    'peut_voir_stats_deperdition': _("Statistiques taux de déperdition"),
    
    # Recettes Péage
    'peut_saisir_recette_peage': _("Saisir recette péage"),
    'peut_voir_liste_recettes_peage': _("Liste des recettes péage"),
    'peut_voir_stats_recettes_peage': _("Statistiques recettes péage"),
    'peut_importer_recettes_peage': _("Importer recettes péage"),
    'peut_voir_evolution_peage': _("Taux d'évolution et estimations"),
    'peut_voir_objectifs_peage': _("Objectifs annuels péage"),
    
    # Quittances Péage
    'peut_saisir_quittance_peage': _("Saisir quittance péage"),
    'peut_voir_liste_quittances_peage': _("Liste quittances péage"),
    'peut_comptabiliser_quittances_peage': _("Comptabilisation quittances péage"),
    
    # Pesage
    'peut_voir_historique_vehicule_pesage': _("Historique véhicule pesage"),
    'peut_saisir_amende': _("Saisir amende"),
    'peut_saisir_pesee_jour': _("Saisir pesée du jour"),
    'peut_voir_objectifs_pesage': _("Objectifs annuels pesage"),
    'peut_valider_paiement_amende': _("Valider paiement amende"),
    'peut_lister_amendes': _("Lister amendes"),
    'peut_saisir_quittance_pesage': _("Saisir quittance pesage"),
    'peut_comptabiliser_quittances_pesage': _("Comptabilisation quittances pesage"),
    'peut_voir_liste_quittancements_pesage': _("Liste quittancements pesage"),
    'peut_voir_historique_pesees': _("Historique des pesées"),
    'peut_voir_recettes_pesage': _("Recettes pesage"),
    'peut_voir_stats_pesage': _("Statistiques pesage"),
    
    # Stock Péage
    'peut_charger_stock_peage': _("Charger/régulariser stock"),
    'peut_voir_liste_stocks_peage': _("Liste des stocks péage"),
    'peut_voir_stock_date_peage': _("Stock à une date"),
    'peut_transferer_stock_peage': _("Transférer stock péage"),
    'peut_voir_tracabilite_tickets': _("Traçabilité tickets"),
    'peut_voir_bordereaux_peage': _("Liste des bordereaux péage"),
    'peut_voir_mon_stock_peage': _("Mon stock péage"),
    'peut_voir_historique_stock_peage': _("Historique de stock péage"),
    'peut_simuler_commandes_peage': _("Simulateur de commandes"),
    
    # Gestion
    'peut_gerer_postes': _("Gestion des postes"),
    'peut_ajouter_poste': _("Ajouter un poste"),
    'peut_creer_poste_masse': _("Créer poste en masse"),
    'peut_gerer_utilisateurs': _("Gestion utilisateurs"),
    'peut_creer_utilisateur': _("Nouvel utilisateur"),
    'peut_voir_journal_audit': _("Journal audit"),
    
    # Rapports
    'peut_voir_rapports_defaillants_peage': _("Rapports défaillants péage"),
    'peut_voir_rapports_defaillants_pesage': _("Rapports défaillants pesage"),
    'peut_voir_rapport_inventaires': _("Rapport des inventaires"),
    'peut_voir_classement_peage_rendement': _("Classement péage rendement"),
    'peut_voir_classement_station_pesage': _("Classement station pesage"),
    'peut_voir_classement_peage_deperdition': _("Classement péage déperdition"),
    'peut_voir_classement_agents_inventaire': _("Classement agents inventaire"),
    
    # Autres
    'peut_parametrage_global': _("Paramétrage global"),
    'peut_voir_compte_emploi': _("Compte d'emploi"),
    'peut_voir_pv_confrontation': _("PV Confrontation"),
    'peut_authentifier_document': _("Authentifier un document"),
    'peut_voir_tous_postes': _("Voir tous les postes"),
}


# ===================================================================
# DICTIONNAIRE DES PERMISSIONS PAR HABILITATION
# Synchronisé avec les méthodes _configurer_XXX du modèle
# ===================================================================

PERMISSIONS_PAR_HABILITATION = {
    
    # ═══════════════════════════════════════════════════════════════
    # SERVICES CENTRAUX - Accès complet à tous les postes
    # ═══════════════════════════════════════════════════════════════
    
    'admin_principal': TOUTES_PERMISSIONS.copy(),
    
    'coord_psrr': TOUTES_PERMISSIONS.copy(),
    
    'serv_info': TOUTES_PERMISSIONS.copy(),
    
    'serv_emission': [
        # Inventaires
        'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin', 'peut_programmer_inventaire',
        'peut_voir_programmation_active', 'peut_voir_programmation_desactivee',
        'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin', 'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        # Recettes Péage
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Pesage
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Stock Péage
        'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage', 'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage', 'peut_simuler_commandes_peage',
        # Rapports
        'peut_voir_classement_peage_rendement', 'peut_voir_classement_station_pesage',
        'peut_voir_classement_peage_deperdition', 'peut_voir_classement_agents_inventaire',
        # Autres
        'peut_voir_compte_emploi', 'peut_voir_pv_confrontation', 'peut_authentifier_document',
        'peut_voir_tous_postes',
    ],
    
    'chef_ag': [
        # Gestion uniquement
        'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
        'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit',
        # Autres
        'peut_parametrage_global', 'peut_voir_tous_postes',
    ],
    
    'serv_controle': [
        # Inventaires
        'peut_voir_liste_inventaires', 'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
        # Recettes Péage
        'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage
        'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Pesage
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Stock Péage
        'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage', 'peut_voir_historique_stock_peage',
        # Gestion
        'peut_voir_journal_audit',
        # Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        # Autres
        'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
        'peut_authentifier_document', 'peut_voir_tous_postes',
    ],
    
    'serv_ordre': [
        # Inventaires
        'peut_voir_stats_deperdition',
        # Recettes Péage
        'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage
        'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Pesage
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Stock Péage
        'peut_voir_liste_stocks_peage', 'peut_voir_tracabilite_tickets',
        'peut_voir_bordereaux_peage', 'peut_voir_historique_stock_peage',
        # Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
        # Autres
        'peut_voir_compte_emploi', 'peut_voir_pv_confrontation', 'peut_authentifier_document',
        'peut_voir_tous_postes',
    ],
    
    # ═══════════════════════════════════════════════════════════════
    # CISOP - Cellules d'Inspection et Suivi des Opérations
    # ═══════════════════════════════════════════════════════════════
    
    'cisop_peage': [
      
        # Recettes Péage
        'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage
        'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Stock Péage
        'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage', 'peut_voir_historique_stock_peage',
        # Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapport_inventaires',
        'peut_voir_classement_peage_rendement', 'peut_voir_classement_peage_deperdition',
        # Autres
        'peut_voir_compte_emploi', 'peut_voir_pv_confrontation', 'peut_authentifier_document',
        'peut_voir_tous_postes',
    ],
    
    'cisop_pesage': [
        # Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_voir_liste_quittancements_pesage', 'peut_voir_historique_pesees',
        'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Rapports
        'peut_voir_rapports_defaillants_pesage', 'peut_voir_classement_station_pesage',
        # Autres
        'peut_voir_pv_confrontation', 'peut_authentifier_document', 'peut_voir_tous_postes',
    ],
    
    # ═══════════════════════════════════════════════════════════════
    # POSTES DE PÉAGE - Accès limité au poste d'affectation
    # ═══════════════════════════════════════════════════════════════
    
    'chef_peage': [
        # Inventaires
        'peut_voir_liste_inventaires', 'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
        # Recettes Péage
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Stock Péage
        'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage','peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage',
        # Rapports
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_peage_deperdition', 'peut_voir_classement_agents_inventaire',
        # Autres
        'peut_voir_compte_emploi', 'peut_authentifier_document',
    ],
    
    'agent_inventaire': [
        # Inventaires - Saisie uniquement
        'peut_saisir_inventaire_normal',
        'peut_voir_liste_inventaires',
        'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
    ],
    
    # ═══════════════════════════════════════════════════════════════
    # STATIONS DE PESAGE - Accès limité à la station d'affectation
    # ═══════════════════════════════════════════════════════════════
    
    'chef_station_pesage': [
        # Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_lister_amendes', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Rapports
        'peut_voir_classement_station_pesage',
        # Autres
        'peut_voir_pv_confrontation', 'peut_authentifier_document',
    ],
    
    'regisseur_pesage': [
        # Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
        'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage', 
        'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Rapports
        'peut_voir_classement_station_pesage', 'peut_voir_pv_confrontation',
    ],
    
    'chef_equipe_pesage': [
        # Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
    ],
    
    # ═══════════════════════════════════════════════════════════════
    # EXTERNES
    # ═══════════════════════════════════════════════════════════════
    
    'imprimerie': [
        # Stock Péage - Historique uniquement
        'peut_voir_historique_stock_peage',
        'peut_voir_tous_postes',
    ],
    
    # Comptable matières
    'comptable_mat': [
        'peut_voir_tous_postes',
    ],
}


# ===================================================================
# FONCTIONS UTILITAIRES
# ===================================================================

def get_permissions_pour_habilitation(habilitation):
    """
    Retourne la liste des permissions pour une habilitation donnée.
    
    Args:
        habilitation: Code de l'habilitation (str)
    
    Returns:
        list: Liste des noms de permissions
    """
    return PERMISSIONS_PAR_HABILITATION.get(habilitation, [])


def get_permissions_dict_pour_habilitation(habilitation):
    """
    Retourne un dictionnaire {permission: True/False} pour une habilitation.
    
    Args:
        habilitation: Code de l'habilitation (str)
    
    Returns:
        dict: Dictionnaire avec toutes les permissions et leur état
    """
    permissions_actives = PERMISSIONS_PAR_HABILITATION.get(habilitation, [])
    return {perm: perm in permissions_actives for perm in TOUTES_PERMISSIONS}


def get_permissions_context_pour_template(user=None, habilitation=None):
    """
    Génère le contexte des permissions organisé par catégorie pour le template.
    
    Args:
        user: Instance de UtilisateurSUPPER (pour modification)
        habilitation: Code de l'habilitation (pour création avec présélection)
    
    Returns:
        dict: Structure hiérarchique des permissions pour l'accordéon
    """
    # Déterminer les permissions actives
    if user:
        # Mode modification: utiliser les permissions actuelles de l'utilisateur
        permissions_actives = {
            perm: getattr(user, perm, False) for perm in TOUTES_PERMISSIONS
        }
    elif habilitation:
        # Mode création avec habilitation présélectionnée
        permissions_actives = get_permissions_dict_pour_habilitation(habilitation)
    else:
        # Mode création sans présélection: tout à False
        permissions_actives = {perm: False for perm in TOUTES_PERMISSIONS}
    
    # Construire la structure par catégorie
    context = {}
    for cat_id, cat_info in CATEGORIES_PERMISSIONS.items():
        perms_list = []
        count_actives = 0
        
        for perm in cat_info['permissions']:
            is_active = permissions_actives.get(perm, False)
            if is_active:
                count_actives += 1
            
            perms_list.append({
                'name': perm,
                'label': str(LABELS_PERMISSIONS.get(perm, perm)),
                'checked': is_active,
            })
        
        context[cat_id] = {
            'label': str(cat_info['label']),
            'icon': cat_info['icon'],
            'permissions': perms_list,
            'count_actives': count_actives,
            'count_total': len(cat_info['permissions']),
        }
    
    return context


def get_permissions_json_pour_js():
    """
    Génère le dictionnaire PERMISSIONS_PAR_HABILITATION en format JSON
    pour utilisation dans le JavaScript.
    
    Returns:
        str: JSON string du dictionnaire des permissions
    """
    import json
    return json.dumps(PERMISSIONS_PAR_HABILITATION)


def compter_permissions_utilisateur(user):
    """
    Compte le nombre de permissions actives pour un utilisateur.
    
    Args:
        user: Instance de UtilisateurSUPPER
    
    Returns:
        tuple: (count_actives, count_total)
    """
    count = sum(1 for perm in TOUTES_PERMISSIONS if getattr(user, perm, False))
    return count, len(TOUTES_PERMISSIONS)