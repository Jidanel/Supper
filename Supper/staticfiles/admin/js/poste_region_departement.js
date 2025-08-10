/* 
===================================================================
Fichier : static/admin/js/poste_region_departement.js - CORRIGÉ
JavaScript pour sélection dynamique région/département + fonctionnalités admin
===================================================================
*/

// ===================================================================
// DONNÉES RÉGIONS/DÉPARTEMENTS DU CAMEROUN
// ===================================================================

const REGIONS_DEPARTEMENTS = {
    'Centre': [
        'Haute-Sanaga', 'Lekié', 'Mbam-et-Inoubou', 'Mbam-et-Kim',
        'Méfou-et-Afamba', 'Méfou-et-Akono', 'Mfoundi', 
        'Nyong-et-Kellé', 'Nyong-et-Mfoumou', 'Nyong-et-So\'o'
    ],
    'Littoral': [
        'Moungo', 'Nkam', 'Sanaga-Maritime', 'Wouri'
    ],
    'Nord': [
        'Bénoué', 'Faro', 'Mayo-Louti', 'Mayo-Rey'
    ],
    'Extrême-Nord': [
        'Diamaré', 'Logone-et-Chari', 'Mayo-Danay', 'Mayo-Kani',
        'Mayo-Sava', 'Mayo-Tsanaga'
    ],
    'Adamaoua': [
        'Djerem', 'Faro-et-Déo', 'Mayo-Banyo', 'Mbéré', 'Vina'
    ],
    'Ouest': [
        'Bamboutos', 'Haut-Nkam', 'Hauts-Plateaux', 'Koung-Khi',
        'Menoua', 'Mifi', 'Mino', 'Ndé'
    ],
    'Est': [
        'Boumba-et-Ngoko', 'Haut-Nyong', 'Haut-Ogooué', 'Kadey', 'Lom-et-Djerem'
    ],
    'Sud': [
        'Dja-et-Lobo', 'Mvila', 'Océan', 'Vallée-du-Ntem'
    ],
    'Nord-Ouest': [
        'Boyo', 'Bui', 'Donga-Mantung', 'Menchum', 'Mezam', 'Momo', 'Ngo-Ketunjia'
    ],
    'Sud-Ouest': [
        'Fako', 'Koupé-Manengouba', 'Lebialem', 'Manyu', 'Meme', 'Ndian'
    ]
};

// Axes routiers pour suggestions
const AXES_ROUTIERS = [
    'Yaoundé-Douala',
    'Douala-Bafoussam',
    'Bafoussam-Bamenda',
    'Yaoundé-Bertoua',
    'Bertoua-Garoua-Boulaï',
    'Ngaoundéré-Garoua',
    'Garoua-Maroua',
    'Maroua-Kousseri',
    'Douala-Kribi',
    'Yaoundé-Ebolowa',
    'Ebolowa-Ambam',
    'Bamenda-Mamfe',
    'Mamfe-Ekok',
    'Foumban-Ngaoundéré',
    'Douala-Buea',
    'Buea-Limbe'
];

// ===================================================================
// INITIALISATION AU CHARGEMENT DE LA PAGE
// ===================================================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Initialisation script région/département admin SUPPER...');
    
    // Initialiser la sélection dynamique région/département
    initRegionDepartementSelection();
    
    // Ajouter les suggestions d'axes routiers
    initAxesRoutiersDatalist();
    
    // Initialiser les fonctionnalités admin
    initAdminFunctions();
    
    // Restaurer les valeurs existantes si modification
    restoreExistingValues();
    
    console.log('✅ Script admin SUPPER initialisé avec succès');
});

// ===================================================================
// GESTION RÉGION/DÉPARTEMENT DYNAMIQUE
// ===================================================================

function initRegionDepartementSelection() {
    const regionSelect = document.getElementById('id_region');
    const departementSelect = document.getElementById('id_departement');
    
    if (!regionSelect || !departementSelect) {
        console.log('⚠️ Éléments région/département non trouvés');
        return;
    }
    
    // Écouter les changements de région
    regionSelect.addEventListener('change', function() {
        updateDepartements(this.value);
    });
    
    console.log('✅ Sélection région/département initialisée');
}

function updateDepartements(regionValue) {
    const departementSelect = document.getElementById('id_departement');
    
    if (!departementSelect) {
        console.error('❌ Élément département non trouvé');
        return;
    }
    
    // Vider les options existantes
    departementSelect.innerHTML = '';
    
    if (!regionValue || regionValue === '') {
        // Aucune région sélectionnée
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = '--- Sélectionner d\'abord une région ---';
        departementSelect.appendChild(defaultOption);
        departementSelect.disabled = true;
        return;
    }
    
    // Activer le select département
    departementSelect.disabled = false;
    
    // Ajouter l'option par défaut
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = '--- Sélectionner un département ---';
    departementSelect.appendChild(defaultOption);
    
    // Récupérer les départements de la région sélectionnée
    const departements = REGIONS_DEPARTEMENTS[regionValue] || [];
    
    // Ajouter les départements
    departements.forEach(function(dept) {
        const option = document.createElement('option');
        option.value = dept;
        option.textContent = dept;
        departementSelect.appendChild(option);
    });
    
    console.log('✅ Départements mis à jour pour la région: ' + regionValue + ' (' + departements.length + ' départements)');
    
    // Animation visuelle
    departementSelect.style.backgroundColor = '#e8f5e8';
    setTimeout(function() {
        departementSelect.style.backgroundColor = '';
    }, 500);
}

function restoreExistingValues() {
    const regionSelect = document.getElementById('id_region');
    const departementSelect = document.getElementById('id_departement');
    
    if (!regionSelect || !departementSelect) {
        return;
    }
    
    // Récupérer la valeur initiale du département (si modification d'un poste existant)
    const initialDepartement = departementSelect.getAttribute('data-initial');
    
    if (regionSelect.value && initialDepartement) {
        // Il y a une région et un département sélectionnés (modification)
        updateDepartements(regionSelect.value);
        
        // Attendre que les options soient créées, puis sélectionner le département
        setTimeout(function() {
            departementSelect.value = initialDepartement;
            console.log('✅ Valeurs restaurées: ' + regionSelect.value + ' / ' + initialDepartement);
        }, 100);
    }
}

// ===================================================================
// SUGGESTIONS AXES ROUTIERS
// ===================================================================

function initAxesRoutiersDatalist() {
    // Créer ou mettre à jour le datalist pour les axes routiers
    let datalist = document.getElementById('axes_routiers');
    
    if (!datalist) {
        datalist = document.createElement('datalist');
        datalist.id = 'axes_routiers';
        document.body.appendChild(datalist);
    }
    
    // Vider le datalist existant
    datalist.innerHTML = '';
    
    // Ajouter les options
    AXES_ROUTIERS.forEach(function(axe) {
        const option = document.createElement('option');
        option.value = axe;
        datalist.appendChild(option);
    });
    
    console.log('✅ ' + AXES_ROUTIERS.length + ' suggestions d\'axes routiers ajoutées');
}

// ===================================================================
// FONCTIONNALITÉS ADMIN AVANCÉES
// ===================================================================

function initAdminFunctions() {
    // Améliorer les tableaux d'administration
    enhanceAdminTables();
    
    // Ajouter des raccourcis clavier
    addKeyboardShortcuts();
}

function enhanceAdminTables() {
    const tables = document.querySelectorAll('.results');
    
    tables.forEach(function(table) {
        // Ajouter des classes Bootstrap pour un meilleur style
        table.classList.add('table', 'table-hover');
        
        // Ajouter une fonctionnalité de recherche rapide
        addQuickSearch(table);
        
        // Améliorer les liens et boutons
        const buttons = table.querySelectorAll('.button');
        buttons.forEach(function(btn) {
            btn.classList.add('btn', 'btn-sm', 'btn-outline-primary');
        });
    });
}

function addQuickSearch(table) {
    // Créer un champ de recherche rapide au-dessus du tableau
    const searchContainer = document.createElement('div');
    searchContainer.className = 'quick-search-container mb-3';
    searchContainer.innerHTML = 
        '<div class="input-group" style="max-width: 300px;">' +
            '<span class="input-group-text">🔍</span>' +
            '<input type="text" class="form-control" placeholder="Recherche rapide..." ' +
                   'onkeyup="quickSearch(this, \'' + (table.id || 'table') + '\')">' +
        '</div>';
    
    // Insérer avant le tableau
    table.parentNode.insertBefore(searchContainer, table);
}

function quickSearch(input, tableId) {
    const query = input.value.toLowerCase();
    const table = document.getElementById(tableId) || input.closest('table') || document.querySelector('.results');
    
    if (!table) return;
    
    const rows = table.querySelectorAll('tbody tr');
    
    rows.forEach(function(row) {
        const text = row.textContent.toLowerCase();
        if (text.includes(query)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

function addKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + S pour sauvegarder
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            const saveButton = document.querySelector('input[type="submit"][name="_save"]');
            if (saveButton) {
                e.preventDefault();
                saveButton.click();
                showNotification('💾 Sauvegarde en cours...', 'info');
            }
        }
        
        // Escape pour annuler/retour
        if (e.key === 'Escape') {
            const cancelButton = document.querySelector('a.cancel-link') || 
                               document.querySelector('a[href*="changelist"]');
            if (cancelButton) {
                window.location.href = cancelButton.href;
            }
        }
    });
}

// ===================================================================
// FONCTIONS POUR LES ACTIONS ADMIN
// ===================================================================

function resetUserPassword(userId) {
    if (confirm('Êtes-vous sûr de vouloir réinitialiser le mot de passe de cet utilisateur ?')) {
        fetch('/admin/actions/reset-password/' + userId + '/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'Content-Type': 'application/json',
            },
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            if (data.success) {
                showNotification('🔑 Mot de passe réinitialisé avec succès', 'success');
            } else {
                showNotification('❌ Erreur lors de la réinitialisation', 'error');
            }
        })
        .catch(function(error) {
            console.error('Erreur:', error);
            showNotification('❌ Erreur de connexion', 'error');
        });
    }
}

function sendNotification(userId) {
    const message = prompt('Message à envoyer à cet utilisateur :');
    if (message && message.trim()) {
        fetch('/admin/actions/send-notification/' + userId + '/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message.trim(),
                type: 'info'
            })
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            if (data.success) {
                showNotification('📧 Notification envoyée avec succès', 'success');
            } else {
                showNotification('❌ Erreur lors de l\'envoi', 'error');
            }
        })
        .catch(function(error) {
            console.error('Erreur:', error);
            showNotification('❌ Erreur de connexion', 'error');
        });
    }
}

function voirStatsPoste(posteId) {
    // Ouvrir les statistiques du poste dans une nouvelle fenêtre/modal
    const url = '/admin/stats/poste/' + posteId + '/';
    window.open(url, '_blank', 'width=1200,height=800');
}

function voirDetailsLog(logId) {
    // Afficher les détails complets d'une entrée de log
    fetch('/admin/api/log-details/' + logId + '/')
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            if (data.success) {
                showLogDetails(data.log);
            } else {
                showNotification('❌ Impossible de charger les détails', 'error');
            }
        })
        .catch(function(error) {
            console.error('Erreur:', error);
            showNotification('❌ Erreur de connexion', 'error');
        });
}

function showLogDetails(log) {
    // Créer une modal pour afficher les détails du log
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.innerHTML = 
        '<div class="modal-dialog modal-lg">' +
            '<div class="modal-content">' +
                '<div class="modal-header">' +
                    '<h5 class="modal-title">📋 Détails du Journal</h5>' +
                    '<button type="button" class="btn-close" data-bs-dismiss="modal"></button>' +
                '</div>' +
                '<div class="modal-body">' +
                    '<table class="table table-bordered">' +
                        '<tr><th>Utilisateur</th><td>' + log.utilisateur + '</td></tr>' +
                        '<tr><th>Action</th><td>' + log.action + '</td></tr>' +
                        '<tr><th>Date/Heure</th><td>' + log.timestamp + '</td></tr>' +
                        '<tr><th>Adresse IP</th><td>' + log.adresse_ip + '</td></tr>' +
                        '<tr><th>User Agent</th><td>' + log.user_agent + '</td></tr>' +
                        '<tr><th>URL</th><td>' + log.url_acces + '</td></tr>' +
                        '<tr><th>Méthode</th><td>' + log.methode_http + '</td></tr>' +
                        '<tr><th>Statut</th><td>' + log.statut_reponse + '</td></tr>' +
                        '<tr><th>Durée</th><td>' + log.duree_execution + '</td></tr>' +
                        '<tr><th>Succès</th><td>' + (log.succes ? '✅ Oui' : '❌ Non') + '</td></tr>' +
                        '<tr><th>Détails</th><td style="max-width: 400px; word-wrap: break-word;">' + log.details + '</td></tr>' +
                    '</table>' +
                '</div>' +
                '<div class="modal-footer">' +
                    '<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Fermer</button>' +
                '</div>' +
            '</div>' +
        '</div>';
    
    document.body.appendChild(modal);
    
    if (typeof bootstrap !== 'undefined') {
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
        
        // Supprimer la modal après fermeture
        modal.addEventListener('hidden.bs.modal', function() {
            document.body.removeChild(modal);
        });
    }
}

function marquerCommeLu(notificationId) {
    fetch('/admin/actions/mark-notification-read/' + notificationId + '/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCSRFToken(),
            'Content-Type': 'application/json',
        },
    })
    .then(function(response) {
        return response.json();
    })
    .then(function(data) {
        if (data.success) {
            showNotification('✅ Notification marquée comme lue', 'success');
            location.reload(); // Recharger pour mettre à jour l'affichage
        } else {
            showNotification('❌ Erreur lors de la mise à jour', 'error');
        }
    })
    .catch(function(error) {
        console.error('Erreur:', error);
        showNotification('❌ Erreur de connexion', 'error');
    });
}

function renvoyerNotification(notificationId) {
    if (confirm('Voulez-vous renvoyer cette notification ?')) {
        fetch('/admin/actions/resend-notification/' + notificationId + '/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'Content-Type': 'application/json',
            },
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            if (data.success) {
                showNotification('📧 Notification renvoyée avec succès', 'success');
            } else {
                showNotification('❌ Erreur lors du renvoi', 'error');
            }
        })
        .catch(function(error) {
            console.error('Erreur:', error);
            showNotification('❌ Erreur de connexion', 'error');
        });
    }
}

// ===================================================================
// FONCTIONS UTILITAIRES
// ===================================================================

function getCSRFToken() {
    const token = document.querySelector('[name=csrfmiddlewaretoken]');
    return token ? token.value : (document.querySelector('meta[name=csrf-token]') ? document.querySelector('meta[name=csrf-token]').getAttribute('content') : '');
}

function showNotification(message, type, duration) {
    type = type || 'info';
    duration = duration || 4000;
    
    // Créer le conteneur de notifications s'il n'existe pas
    let container = document.getElementById('notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        container.style.cssText = 
            'position: fixed;' +
            'top: 20px;' +
            'right: 20px;' +
            'z-index: 9999;' +
            'max-width: 400px;';
        document.body.appendChild(container);
    }
    
    // Créer la notification
    const notification = document.createElement('div');
    notification.className = 'notification notification-' + type;
    notification.style.cssText = 
        'background: ' + getNotificationColor(type) + ';' +
        'color: white;' +
        'padding: 15px 20px;' +
        'margin-bottom: 10px;' +
        'border-radius: 6px;' +
        'box-shadow: 0 4px 12px rgba(0,0,0,0.2);' +
        'animation: slideInRight 0.3s ease-out;' +
        'cursor: pointer;';
    notification.textContent = message;
    
    // Ajouter l'animation CSS si pas déjà présente
    addNotificationCSS();
    
    // Ajouter la notification
    container.appendChild(notification);
    
    // Permettre de fermer en cliquant
    notification.addEventListener('click', function() {
        removeNotification(notification);
    });
    
    // Supprimer automatiquement
    setTimeout(function() {
        removeNotification(notification);
    }, duration);
}

function getNotificationColor(type) {
    const colors = {
        'success': '#198754',
        'error': '#dc3545',
        'warning': '#fd7e14',
        'info': '#0d6efd'
    };
    return colors[type] || colors['info'];
}

function removeNotification(notification) {
    if (notification.parentNode) {
        notification.style.animation = 'slideOutRight 0.3s ease-in';
        setTimeout(function() {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }
}

function addNotificationCSS() {
    if (document.getElementById('notification-styles')) {
        return; // Déjà ajouté
    }
    
    const style = document.createElement('style');
    style.id = 'notification-styles';
    style.textContent = 
        '@keyframes slideInRight {' +
            'from {' +
                'transform: translateX(100%);' +
                'opacity: 0;' +
            '}' +
            'to {' +
                'transform: translateX(0);' +
                'opacity: 1;' +
            '}' +
        '}' +
        
        '@keyframes slideOutRight {' +
            'from {' +
                'transform: translateX(0);' +
                'opacity: 1;' +
            '}' +
            'to {' +
                'transform: translateX(100%);' +
                'opacity: 0;' +
            '}' +
        '}' +
        
        '.notification:hover {' +
            'opacity: 0.9;' +
            'transform: scale(1.02);' +
            'transition: all 0.2s ease;' +
        '}';
    document.head.appendChild(style);
}

// ===================================================================
// FONCTIONS GLOBALES POUR COMPATIBILITÉ
// ===================================================================

// Rendre les fonctions accessibles globalement pour les onclick dans le HTML
window.updateDepartements = updateDepartements;
window.resetUserPassword = resetUserPassword;
window.sendNotification = sendNotification;
window.voirStatsPoste = voirStatsPoste;
window.voirDetailsLog = voirDetailsLog;
window.marquerCommeLu = marquerCommeLu;
window.renvoyerNotification = renvoyerNotification;
window.quickSearch = quickSearch;