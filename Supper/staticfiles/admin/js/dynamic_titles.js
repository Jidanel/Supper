/* 
===================================================================
Fichier : static/admin/js/dynamic_titles.js
JavaScript pour gérer les titres dynamiques dans le panel admin
===================================================================
*/

document.addEventListener('DOMContentLoaded', function() {
    
    // ===================================================================
    // CONFIGURATION DES TITRES PAR MODULE
    // ===================================================================
    
    const MODULE_TITLES = {
        // Module Utilisateurs
        'utilisateursupper': {
            title: 'Administration SUPPER - Gestion des Comptes Utilisateurs',
            icon: '👥',
            className: 'module-users'
        },
        
        // Module Postes
        'poste': {
            title: 'Administration SUPPER - Gestion des Postes de Péage et Pesage',
            icon: '🏢',
            className: 'module-postes'
        },
        
        // Module Journal d'Audit
        'journalaudit': {
            title: 'Administration SUPPER - Journal d\'Audit et Sécurité',
            icon: '📋',
            className: 'module-audit'
        },
        
        // Module Notifications
        'notificationutilisateur': {
            title: 'Administration SUPPER - Gestion des Notifications',
            icon: '📧',
            className: 'module-notifications'
        },
        
        // Module Inventaire
        'inventairejournalier': {
            title: 'Administration SUPPER - Module Inventaire',
            icon: '📊',
            className: 'module-inventaire'
        },
        
        // Module Recettes
        'recettejournaliere': {
            title: 'Administration SUPPER - Module Recettes',
            icon: '💰',
            className: 'module-recettes'
        },
        
        // Module Statistiques
        'statistiquesperi': {
            title: 'Administration SUPPER - Module Statistiques',
            icon: '📈',
            className: 'module-stats'
        }
    };
    
    // ===================================================================
    // DÉTECTION DU MODULE ACTUEL
    // ===================================================================
    
    function detectCurrentModule() {
        const currentPath = window.location.pathname;
        const pathParts = currentPath.split('/');
        
        // Chercher dans l'URL des indices du module
        for (let i = 0; i < pathParts.length; i++) {
            const part = pathParts[i].toLowerCase();
            
            // Vérifier si cette partie correspond à un module connu
            for (const moduleKey in MODULE_TITLES) {
                if (part.includes(moduleKey) || part.includes(moduleKey.replace('supper', ''))) {
                    return moduleKey;
                }
            }
        }
        
        // Vérification par classes CSS de la page
        const bodyClasses = document.body.className;
        for (const moduleKey in MODULE_TITLES) {
            if (bodyClasses.includes(moduleKey)) {
                return moduleKey;
            }
        }
        
        // Vérification par titre de la page existant
        const pageTitle = document.title.toLowerCase();
        for (const moduleKey in MODULE_TITLES) {
            if (pageTitle.includes(moduleKey.replace('supper', '')) || 
                pageTitle.includes(MODULE_TITLES[moduleKey].title.toLowerCase())) {
                return moduleKey;
            }
        }
        
        // Par défaut, retourner 'dashboard' pour la page principale
        if (currentPath.includes('/admin/') && pathParts.length <= 3) {
            return 'dashboard';
        }
        
        return null;
    }
    
    // ===================================================================
    // MISE À JOUR DU TITRE DE LA PAGE
    // ===================================================================
    
    function updatePageTitle(moduleKey) {
        if (!moduleKey || !MODULE_TITLES[moduleKey]) {
            return;
        }
        
        const moduleInfo = MODULE_TITLES[moduleKey];
        
        // Mettre à jour le titre de l'onglet du navigateur
        document.title = moduleInfo.title;
        
        // Mettre à jour le titre principal dans l'interface admin
        const siteNameElement = document.querySelector('#site-name a');
        if (siteNameElement) {
            siteNameElement.textContent = moduleInfo.title;
        }
        
        // Ajouter une classe CSS au body pour le styling spécifique
        document.body.classList.add(moduleInfo.className);
    }
    
    // ===================================================================
    // CRÉATION D'UN BREADCRUMB DYNAMIQUE
    // ===================================================================
    
    function createDynamicBreadcrumb(moduleKey) {
        if (!moduleKey || !MODULE_TITLES[moduleKey]) {
            return;
        }
        
        const moduleInfo = MODULE_TITLES[moduleKey];
        const breadcrumbContainer = document.querySelector('.breadcrumbs');
        
        if (breadcrumbContainer) {
            // Créer le breadcrumb avec icône
            const breadcrumbHTML = `
                <div class="admin-title-dynamic">
                    ${moduleInfo.icon} ${moduleInfo.title}
                </div>
            `;
            
            // Insérer le titre dynamique au début du conteneur
            breadcrumbContainer.insertAdjacentHTML('afterbegin', breadcrumbHTML);
        }
    }
    
    // ===================================================================
    // AMÉLIORATION DE LA NAVIGATION
    // ===================================================================
    
    function enhanceNavigation() {
        // Ajouter des icônes aux liens de navigation
        const navLinks = document.querySelectorAll('#nav-sidebar a');
        
        navLinks.forEach(link => {
            const linkText = link.textContent.toLowerCase();
            let icon = '';
            
            // Associer des icônes selon le contenu
            if (linkText.includes('utilisateur') || linkText.includes('user')) {
                icon = '👥 ';
            } else if (linkText.includes('poste')) {
                icon = '🏢 ';
            } else if (linkText.includes('journal') || linkText.includes('audit')) {
                icon = '📋 ';
            } else if (linkText.includes('notification')) {
                icon = '📧 ';
            } else if (linkText.includes('inventaire')) {
                icon = '📊 ';
            } else if (linkText.includes('recette')) {
                icon = '💰 ';
            } else if (linkText.includes('statistique')) {
                icon = '📈 ';
            }
            
            if (icon) {
                link.innerHTML = icon + link.innerHTML;
            }
        });
    }
    
    // ===================================================================
    // AMÉLIORATION DES FORMULAIRES
    // ===================================================================
    
    function enhanceForms() {
        // Ajouter une validation en temps réel
        const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"]');
        
        inputs.forEach(input => {
            // Validation du matricule
            if (input.name === 'username' || input.id === 'id_username') {
                input.addEventListener('input', function() {
                    const value = this.value.toUpperCase();
                    const matriculePattern = /^[A-Z]{2,4}[0-9]{3,4}$/;
                    
                    if (value && !matriculePattern.test(value)) {
                        this.style.borderColor = '#e74c3c';
                        showFieldError(this, 'Format: 2-4 lettres + 3-4 chiffres (ex: INV001)');
                    } else {
                        this.style.borderColor = '#27ae60';
                        hideFieldError(this);
                    }
                    
                    this.value = value; // Forcer en majuscules
                });
            }
            
            // Validation du téléphone camerounais
            if (input.name === 'telephone' || input.id === 'id_telephone') {
                input.addEventListener('input', function() {
                    const value = this.value;
                    const phonePattern = /^(\+237)?[67][0-9]{8}$/;
                    
                    if (value && !phonePattern.test(value)) {
                        this.style.borderColor = '#e74c3c';
                        showFieldError(this, 'Format: +237XXXXXXXXX ou 6XXXXXXXX/7XXXXXXXX');
                    } else {
                        this.style.borderColor = '#27ae60';
                        hideFieldError(this);
                    }
                });
            }
        });
    }
    
    // ===================================================================
    // FONCTIONS UTILITAIRES POUR LES MESSAGES D'ERREUR
    // ===================================================================
    
    function showFieldError(field, message) {
        // Supprimer l'ancien message d'erreur s'il existe
        hideFieldError(field);
        
        // Créer un nouveau message d'erreur
        const errorDiv = document.createElement('div');
        errorDiv.className = 'field-error';
        errorDiv.style.color = '#e74c3c';
        errorDiv.style.fontSize = '12px';
        errorDiv.style.marginTop = '5px';
        errorDiv.textContent = message;
        
        // Insérer après le champ
        field.parentNode.insertBefore(errorDiv, field.nextSibling);
    }
    
    function hideFieldError(field) {
        const existingError = field.parentNode.querySelector('.field-error');
        if (existingError) {
            existingError.remove();
        }
    }
    
    // ===================================================================
    // AMÉLIORATION DES TABLEAUX
    // ===================================================================
    
    function enhanceTables() {
        const tables = document.querySelectorAll('#result_list');
        
        tables.forEach(table => {
            // Ajouter une fonctionnalité de tri visuel
            const headers = table.querySelectorAll('thead th');
            
            headers.forEach(header => {
                if (header.querySelector('a')) {
                    header.style.cursor = 'pointer';
                    header.addEventListener('mouseenter', function() {
                        this.style.backgroundColor = '#2c3e50';
                    });
                    header.addEventListener('mouseleave', function() {
                        this.style.backgroundColor = '#34495e';
                    });
                }
            });
            
            // Ajouter des numéros de ligne
            const rows = table.querySelectorAll('tbody tr');
            rows.forEach((row, index) => {
                const firstCell = row.querySelector('td');
                if (firstCell && !firstCell.querySelector('input[type="checkbox"]')) {
                    const lineNumber = document.createElement('span');
                    lineNumber.textContent = `${index + 1}. `;
                    lineNumber.style.color = '#7f8c8d';
                    lineNumber.style.fontWeight = 'bold';
                    firstCell.insertBefore(lineNumber, firstCell.firstChild);
                }
            });
        });
    }
    
    // ===================================================================
    // FONCTIONNALITÉS DE RECHERCHE AMÉLIORÉE
    // ===================================================================
    
    function enhanceSearch() {
        const searchInput = document.querySelector('#searchbar');
        
        if (searchInput) {
            // Ajouter un placeholder dynamique
            const moduleKey = detectCurrentModule();
            if (moduleKey && MODULE_TITLES[moduleKey]) {
                const moduleName = MODULE_TITLES[moduleKey].title.split(' - ')[1] || 'éléments';
                searchInput.placeholder = `Rechercher dans ${moduleName}...`;
            }
            
            // Ajouter une fonction de recherche en temps réel (optionnel)
            let searchTimeout;
            searchInput.addEventListener('input', function() {
                clearTimeout(searchTimeout);
                const query = this.value;
                
                if (query.length > 2) {
                    searchTimeout = setTimeout(() => {
                        // Ici on pourrait ajouter une recherche AJAX en temps réel
                        console.log('Recherche:', query);
                    }, 500);
                }
            });
        }
    }
    
    // ===================================================================
    // FONCTIONNALITÉS D'EXPORT ET ACTIONS
    // ===================================================================
    
    function addExportFunctionality() {
        // Ajouter un bouton d'export rapide si pas déjà présent
        const actionsBar = document.querySelector('.actions');
        
        if (actionsBar && !document.querySelector('#export-button')) {
            const exportButton = document.createElement('button');
            exportButton.id = 'export-button';
            exportButton.className = 'button';
            exportButton.innerHTML = '📊 Exporter CSV';
            exportButton.style.marginLeft = '10px';
            
            exportButton.addEventListener('click', function() {
                // Fonction d'export (à implémenter selon les besoins)
                alert('Fonctionnalité d\'export en cours de développement');
            });
            
            actionsBar.appendChild(exportButton);
        }
    }
    
    // ===================================================================
    // GESTION DES NOTIFICATIONS TEMPS RÉEL
    // ===================================================================
    
    function initNotifications() {
        // Créer un conteneur pour les notifications
        if (!document.querySelector('#notification-container')) {
            const notifContainer = document.createElement('div');
            notifContainer.id = 'notification-container';
            notifContainer.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 9999;
                max-width: 400px;
            `;
            document.body.appendChild(notifContainer);
        }
    }
    
    function showNotification(message, type = 'info', duration = 5000) {
        const container = document.querySelector('#notification-container');
        if (!container) return;
        
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.style.cssText = `
            background: ${type === 'success' ? '#27ae60' : type === 'error' ? '#e74c3c' : '#3498db'};
            color: white;
            padding: 15px 20px;
            margin-bottom: 10px;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            animation: slideInRight 0.3s ease-out;
        `;
        notification.textContent = message;
        
        container.appendChild(notification);
        
        // Supprimer automatiquement après la durée spécifiée
        setTimeout(() => {
            notification.style.animation = 'slideOutRight 0.3s ease-in';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, duration);
    }
    
    // ===================================================================
    // INITIALISATION PRINCIPALE
    // ===================================================================
    
    function initDynamicAdmin() {
        console.log('🚀 Initialisation du panel admin SUPPER dynamique...');
        
        // Détecter le module actuel
        const currentModule = detectCurrentModule();
        console.log('📍 Module détecté:', currentModule);
        
        // Appliquer les améliorations
        if (currentModule) {
            updatePageTitle(currentModule);
            createDynamicBreadcrumb(currentModule);
        }
        
        enhanceNavigation();
        enhanceForms();
        enhanceTables();
        enhanceSearch();
        addExportFunctionality();
        initNotifications();
        
        // Afficher une notification de bienvenue
        setTimeout(() => {
            showNotification('Interface d\'administration SUPPER initialisée avec succès', 'success', 3000);
        }, 1000);
        
        console.log('✅ Panel admin SUPPER prêt !');
    }
    
    // ===================================================================
    // STYLES CSS DYNAMIQUES
    // ===================================================================
    
    // Ajouter les styles CSS pour les animations
    const dynamicStyles = document.createElement('style');
    dynamicStyles.textContent = `
        @keyframes slideInRight {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        
        @keyframes slideOutRight {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(100%);
                opacity: 0;
            }
        }
        
        .admin-title-dynamic {
            animation: fadeInDown 0.5s ease-out;
        }
        
        @keyframes fadeInDown {
            from {
                transform: translateY(-20px);
                opacity: 0;
            }
            to {
                transform: translateY(0);
                opacity: 1;
            }
        }
    `;
    document.head.appendChild(dynamicStyles);
    
    // ===================================================================
    // LANCEMENT DE L'INITIALISATION
    // ===================================================================
    
    // Délai court pour s'assurer que le DOM est complètement chargé
    setTimeout(initDynamicAdmin, 100);
    
});

// ===================================================================
// FONCTIONS GLOBALES POUR INTERACTIONS ADMIN
// ===================================================================

// Fonction pour réinitialiser le mot de passe d'un utilisateur
function resetPassword(userId) {
    if (confirm('Êtes-vous sûr de vouloir réinitialiser le mot de passe de cet utilisateur ?')) {
        // Ici, implémenter l'appel AJAX pour réinitialiser le mot de passe
        fetch(`/admin/accounts/utilisateursupper/${userId}/reset-password/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                'Content-Type': 'application/json',
            },
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification('Mot de passe réinitialisé avec succès', 'success');
            } else {
                showNotification('Erreur lors de la réinitialisation', 'error');
            }
        })
        .catch(error => {
            console.error('Erreur:', error);
            showNotification('Erreur de connexion', 'error');
        });
    }
}

// Fonction pour marquer une notification comme lue
function markAsRead(notificationId) {
    fetch(`/admin/accounts/notificationutilisateur/${notificationId}/mark-read/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            'Content-Type': 'application/json',
        },
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Notification marquée comme lue', 'success');
            location.reload(); // Recharger pour mettre à jour l'affichage
        }
    })
    .catch(error => {
        console.error('Erreur:', error);
        showNotification('Erreur lors de la mise à jour', 'error');
    });
}