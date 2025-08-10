/* 
===================================================================
Fichier : static/js/supper.js
JavaScript personnalisé pour l'application SUPPER
Fonctionnalités : AJAX, notifications, validation, UX
===================================================================
*/

// ===================================================================
// CONFIGURATION GLOBALE
// ===================================================================

// Configuration principale de l'application SUPPER
const SUPPER = {
    // URLs API pour les requêtes AJAX
    api: {
        notifications: '/dashboard/api/notifications/',
        stats: '/dashboard/api/stats/',
        search: '/dashboard/api/search/',
        status: '/dashboard/api/status/'
    },
    
    // Configuration des timeouts et intervalles
    config: {
        notificationRefresh: 30000, // 30 secondes
        autoSaveInterval: 60000,    // 1 minute
        toastDuration: 5000,        // 5 secondes
        fadeAnimationDuration: 300  // 300ms
    },
    
    // Cache des données
    cache: {
        notifications: null,
        lastNotificationCheck: null,
        currentUser: null
    }
};

// ===================================================================
// INITIALISATION DE L'APPLICATION
// ===================================================================

// Fonction d'initialisation appelée au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Initialisation SUPPER...');
    
    // Initialiser les composants principaux
    initializeNavigation();
    initializeNotifications();
    initializeForms();
    initializeTooltips();
    initializeModals();
    initializeCharts();
    
    // Afficher l'animation de fondu
    document.body.classList.add('fade-in');
    
    console.log('✅ SUPPER initialisé avec succès');
});

// ===================================================================
// GESTION DE LA NAVIGATION
// ===================================================================

// Initialise la navigation et les menus
function initializeNavigation() {
    // Marquer l'élément de menu actif
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
    
    navLinks.forEach(link => {
        // Comparer l'URL du lien avec l'URL actuelle
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });
    
    // Gérer la fermeture automatique des menus sur mobile
    const navbarToggler = document.querySelector('.navbar-toggler');
    const navbarCollapse = document.querySelector('.navbar-collapse');
    
    if (navbarToggler && navbarCollapse) {
        // Fermer le menu quand on clique sur un lien
        navLinks.forEach(link => {
            link.addEventListener('click', function() {
                if (navbarCollapse.classList.contains('show')) {
                    navbarToggler.click();
                }
            });
        });
    }
    
    console.log('📝 Navigation initialisée');
}

// ===================================================================
// GESTION DES NOTIFICATIONS
// ===================================================================

// Initialise le système de notifications
function initializeNotifications() {
    // Charger les notifications au démarrage
    loadNotifications();
    
    // Programmer l'actualisation périodique
    setInterval(loadNotifications, SUPPER.config.notificationRefresh);
    
    // Gérer le clic sur les notifications
    setupNotificationHandlers();
    
    console.log('🔔 Système de notifications initialisé');
}

// Charge les notifications via AJAX
function loadNotifications() {
    // Éviter les requêtes trop fréquentes
    const now = Date.now();
    if (SUPPER.cache.lastNotificationCheck && 
        (now - SUPPER.cache.lastNotificationCheck) < 5000) {
        return;
    }
    
    // Effectuer la requête AJAX
    fetch(SUPPER.api.notifications, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin'
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        updateNotificationUI(data);
        SUPPER.cache.notifications = data;
        SUPPER.cache.lastNotificationCheck = now;
    })
    .catch(error => {
        console.error('❌ Erreur chargement notifications:', error);
        // Ne pas afficher d'erreur à l'utilisateur pour les notifications
    });
}

// Met à jour l'interface des notifications
function updateNotificationUI(data) {
    const badge = document.getElementById('notificationsBadge');
    const container = document.getElementById('notificationsContainer');
    
    if (!badge || !container) return;
    
    // Mettre à jour le badge
    if (data.notifications && data.notifications.length > 0) {
        badge.textContent = data.notifications.length;
        badge.style.display = 'block';
        badge.classList.add('pulse'); // Animation d'attention
        
        // Construire le HTML des notifications
        let html = '';
        data.notifications.forEach(notif => {
            const typeIcon = getNotificationIcon(notif.type);
            html += `
                <div class="notification-item border-bottom pb-2 mb-2" data-id="${notif.id}">
                    <div class="d-flex align-items-start">
                        <div class="me-2">
                            <i class="${typeIcon} text-${getNotificationColor(notif.type)}"></i>
                        </div>
                        <div class="flex-grow-1">
                            <div class="fw-bold small">${escapeHtml(notif.titre)}</div>
                            <div class="text-muted small">${escapeHtml(notif.message)}</div>
                            <div class="text-muted x-small">${notif.date}</div>
                        </div>
                        <button class="btn btn-sm btn-outline-secondary mark-read-btn" 
                                onclick="markNotificationAsRead(${notif.id})">
                            <i class="fas fa-check"></i>
                        </button>
                    </div>
                </div>
            `;
        });
        container.innerHTML = html;
    } else {
        // Aucune notification
        badge.style.display = 'none';
        badge.classList.remove('pulse');
        
        container.innerHTML = `
            <div class="text-muted text-center py-3">
                <i class="fas fa-inbox me-2"></i>
                Aucune notification
            </div>
        `;
    }
}

// Retourne l'icône appropriée selon le type de notification
function getNotificationIcon(type) {
    const icons = {
        'info': 'fas fa-info-circle',
        'success': 'fas fa-check-circle',
        'warning': 'fas fa-exclamation-triangle',
        'error': 'fas fa-times-circle',
        'system': 'fas fa-cog'
    };
    return icons[type] || icons.info;
}

// Retourne la couleur appropriée selon le type de notification
function getNotificationColor(type) {
    const colors = {
        'info': 'info',
        'success': 'success',
        'warning': 'warning',
        'error': 'danger',
        'system': 'secondary'
    };
    return colors[type] || colors.info;
}

// Configure les gestionnaires d'événements pour les notifications
function setupNotificationHandlers() {
    // Marquer toutes les notifications comme lues quand le menu se ferme
    const notificationDropdown = document.querySelector('[data-bs-toggle="dropdown"]');
    if (notificationDropdown) {
        notificationDropdown.addEventListener('hidden.bs.dropdown', function() {
            // Optionnel : marquer comme lues après fermeture
        });
    }
}

// Marque une notification comme lue
function markNotificationAsRead(notificationId) {
    fetch(SUPPER.api.notifications, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken(),
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        body: JSON.stringify({
            'id': notificationId,
            'action': 'mark_read'
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Supprimer visuellement la notification
            const notifElement = document.querySelector(`[data-id="${notificationId}"]`);
            if (notifElement) {
                notifElement.style.opacity = '0.5';
                setTimeout(() => {
                    notifElement.remove();
                    loadNotifications(); // Recharger pour mettre à jour le badge
                }, 500);
            }
            
            showToast('Notification marquée comme lue', 'success');
        }
    })
    .catch(error => {
        console.error('❌ Erreur marquage notification:', error);
        showToast('Erreur lors du marquage', 'error');
    });
}

// ===================================================================
// GESTION DES FORMULAIRES
// ===================================================================

// Initialise les fonctionnalités des formulaires
function initializeForms() {
    // Validation automatique HTML5
    enableFormValidation();
    
    // Auto-sauvegarde pour les formulaires longs
    enableAutoSave();
    
    // Formatage automatique des champs
    enableFieldFormatting();
    
    // Confirmation avant soumission pour les actions critiques
    setupFormConfirmations();
    
    console.log('📋 Formulaires initialisés');
}

// Active la validation des formulaires
function enableFormValidation() {
    const forms = document.querySelectorAll('.needs-validation');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
                
                // Focaliser sur le premier champ invalide
                const firstInvalid = form.querySelector(':invalid');
                if (firstInvalid) {
                    firstInvalid.focus();
                }
            }
            
            form.classList.add('was-validated');
        });
    });
}

// Active l'auto-sauvegarde des formulaires
function enableAutoSave() {
    const autosaveForms = document.querySelectorAll('[data-autosave]');
    
    autosaveForms.forEach(form => {
        let saveTimeout;
        
        // Sauvegarder les données dans le localStorage
        const inputs = form.querySelectorAll('input, textarea, select');
        inputs.forEach(input => {
            input.addEventListener('input', function() {
                clearTimeout(saveTimeout);
                saveTimeout = setTimeout(() => {
                    saveFormData(form);
                }, 1000); // Attendre 1 seconde après la dernière modification
            });
        });
        
        // Restaurer les données au chargement
        restoreFormData(form);
    });
}

// Sauvegarde les données du formulaire localement
function saveFormData(form) {
    if (!form.id) return;
    
    const formData = new FormData(form);
    const data = {};
    
    for (let [key, value] of formData.entries()) {
        data[key] = value;
    }
    
    try {
        localStorage.setItem(`supper_form_${form.id}`, JSON.stringify(data));
        showToast('Données sauvegardées automatiquement', 'info', 2000);
    } catch (error) {
        console.warn('⚠️ Impossible de sauvegarder les données du formulaire');
    }
}

// Restaure les données du formulaire depuis le localStorage
function restoreFormData(form) {
    if (!form.id) return;
    
    try {
        const savedData = localStorage.getItem(`supper_form_${form.id}`);
        if (savedData) {
            const data = JSON.parse(savedData);
            
            Object.keys(data).forEach(key => {
                const field = form.querySelector(`[name="${key}"]`);
                if (field && field.type !== 'password') {
                    field.value = data[key];
                }
            });
            
            showToast('Données restaurées', 'info', 2000);
        }
    } catch (error) {
        console.warn('⚠️ Impossible de restaurer les données du formulaire');
    }
}

// Active le formatage automatique des champs
function enableFieldFormatting() {
    // Formatage des numéros de téléphone
    const phoneFields = document.querySelectorAll('input[type="tel"], input[name*="telephone"]');
    phoneFields.forEach(field => {
        field.addEventListener('input', function() {
            formatPhoneNumber(this);
        });
    });
    
    // Formatage des montants
    const amountFields = document.querySelectorAll('input[name*="montant"], input[data-format="currency"]');
    amountFields.forEach(field => {
        field.addEventListener('input', function() {
            formatCurrency(this);
        });
        field.addEventListener('blur', function() {
            formatCurrencyFinal(this);
        });
    });
    
    // Conversion automatique en majuscules pour les matricules
    const matriculeFields = document.querySelectorAll('input[name*="username"], input[name*="matricule"]');
    matriculeFields.forEach(field => {
        field.addEventListener('input', function() {
            this.value = this.value.toUpperCase();
        });
    });
}

// Formate un numéro de téléphone camerounais
function formatPhoneNumber(field) {
    let value = field.value.replace(/\D/g, ''); // Supprimer tout sauf les chiffres
    
    // Ajouter le préfixe +237 si nécessaire
    if (value.length > 0 && !value.startsWith('237')) {
        if (value.length === 9) {
            value = '237' + value;
        }
    }
    
    // Formater avec des espaces
    if (value.length >= 3) {
        value = '+' + value.substring(0, 3) + ' ' + value.substring(3);
    }
    
    field.value = value;
}

// Formate un montant en devise
function formatCurrency(field) {
    let value = field.value.replace(/[^\d]/g, ''); // Garder seulement les chiffres
    if (value) {
        // Ajouter des espaces comme séparateurs de milliers
        value = parseInt(value).toLocaleString('fr-FR');
        field.value = value;
    }
}

// Finalise le formatage d'un montant
function formatCurrencyFinal(field) {
    if (field.value) {
        field.value += ' FCFA';
    }
}

// Configure les confirmations de formulaires
function setupFormConfirmations() {
    const dangerousForms = document.querySelectorAll('[data-confirm]');
    
    dangerousForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            const message = this.dataset.confirm || 'Êtes-vous sûr de vouloir continuer ?';
            
            if (!confirm(message)) {
                event.preventDefault();
                return false;
            }
        });
    });
}

// ===================================================================
// GESTION DES GRAPHIQUES
// ===================================================================

// Initialise les graphiques et visualisations
function initializeCharts() {
    // Vérifier si Chart.js est disponible
    if (typeof Chart === 'undefined') {
        console.warn('⚠️ Chart.js non disponible');
        return;
    }
    
    // Initialiser les graphiques existants
    const chartContainers = document.querySelectorAll('.chart-container');
    chartContainers.forEach(container => {
        const canvas = container.querySelector('canvas');
        if (canvas) {
            initializeChart(canvas);
        }
    });
    
    console.log('📊 Graphiques initialisés');
}

// Initialise un graphique spécifique
function initializeChart(canvas) {
    const type = canvas.dataset.chartType || 'line';
    const apiUrl = canvas.dataset.chartData;
    
    if (apiUrl) {
        // Charger les données via AJAX
        fetch(apiUrl)
            .then(response => response.json())
            .then(data => {
                createChart(canvas, type, data);
            })
            .catch(error => {
                console.error('❌ Erreur chargement données graphique:', error);
                showChartError(canvas);
            });
    }
}

// Crée un graphique avec Chart.js
function createChart(canvas, type, data) {
    const ctx = canvas.getContext('2d');
    
    const config = {
        type: type,
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                },
                title: {
                    display: true,
                    text: canvas.dataset.chartTitle || ''
                }
            },
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    };
    
    new Chart(ctx, config);
}

// Affiche une erreur dans un conteneur de graphique
function showChartError(canvas) {
    const container = canvas.parentElement;
    container.innerHTML = `
        <div class="alert alert-warning d-flex align-items-center justify-content-center h-100">
            <div class="text-center">
                <i class="fas fa-exclamation-triangle fa-2x mb-2"></i>
                <div>Impossible de charger le graphique</div>
            </div>
        </div>
    `;
}

// ===================================================================
// UTILITAIRES
// ===================================================================

// Initialise les tooltips Bootstrap
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Initialise les modales Bootstrap
function initializeModals() {
    const modalTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="modal"]'));
    modalTriggerList.map(function (modalTriggerEl) {
        return new bootstrap.Modal(modalTriggerEl);
    });
}

// Récupère le token CSRF pour les requêtes AJAX
function getCSRFToken() {
    const token = document.querySelector('[name=csrfmiddlewaretoken]');
    return token ? token.value : '';
}

// Échappe les caractères HTML pour éviter XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Affiche un toast de notification
function showToast(message, type = 'info', duration = null) {
    const toastContainer = getOrCreateToastContainer();
    const toastId = 'toast_' + Date.now();
    
    const typeClass = {
        'success': 'text-bg-success',
        'error': 'text-bg-danger',
        'warning': 'text-bg-warning',
        'info': 'text-bg-info'
    }[type] || 'text-bg-info';
    
    const toastHtml = `
        <div id="${toastId}" class="toast ${typeClass}" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header">
                <i class="${getNotificationIcon(type)} me-2"></i>
                <strong class="me-auto">SUPPER</strong>
                <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                ${escapeHtml(message)}
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, {
        delay: duration || SUPPER.config.toastDuration
    });
    
    toast.show();
    
    // Supprimer le toast après fermeture
    toastElement.addEventListener('hidden.bs.toast', function() {
        this.remove();
    });
}

// Crée ou récupère le conteneur de toasts
function getOrCreateToastContainer() {
    let container = document.getElementById('toast-container');
    
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '1055';
        document.body.appendChild(container);
    }
    
    return container;
}

// Affiche un indicateur de chargement
function showLoading(element, text = 'Chargement...') {
    const loadingHtml = `
        <div class="loading-overlay d-flex align-items-center justify-content-center">
            <div class="text-center">
                <div class="spinner-border text-primary mb-2" role="status">
                    <span class="visually-hidden">Chargement...</span>
                </div>
                <div class="small text-muted">${escapeHtml(text)}</div>
            </div>
        </div>
    `;
    
    element.style.position = 'relative';
    element.insertAdjacentHTML('beforeend', loadingHtml);
}

// Masque l'indicateur de chargement
function hideLoading(element) {
    const overlay = element.querySelector('.loading-overlay');
    if (overlay) {
        overlay.remove();
    }
}

// Confirme une action avec une modal
function confirmAction(title, message, confirmCallback, cancelCallback = null) {
    const modalId = 'confirmModal_' + Date.now();
    
    const modalHtml = `
        <div class="modal fade" id="${modalId}" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="fas fa-question-circle text-warning me-2"></i>
                            ${escapeHtml(title)}
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        ${escapeHtml(message)}
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            <i class="fas fa-times me-2"></i>
                            Annuler
                        </button>
                        <button type="button" class="btn btn-primary confirm-btn">
                            <i class="fas fa-check me-2"></i>
                            Confirmer
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modal = new bootstrap.Modal(document.getElementById(modalId));
    
    // Gérer les événements
    const confirmBtn = document.querySelector(`#${modalId} .confirm-btn`);
    confirmBtn.addEventListener('click', function() {
        modal.hide();
        if (confirmCallback) confirmCallback();
    });
    
    // Nettoyer après fermeture
    document.getElementById(modalId).addEventListener('hidden.bs.modal', function() {
        this.remove();
        if (cancelCallback) cancelCallback();
    });
    
    modal.show();
    return modal;
}

// ===================================================================
// FONCTIONS SPÉCIFIQUES SUPPER
// ===================================================================

// Calcule et affiche le taux de déperdition
function calculateDeperditionRate(recetteDeclare, recettePotentielle) {
    if (!recettePotentielle || recettePotentielle === 0) {
        return { taux: 0, couleur: 'secondary', classe: 'deperdition-gris' };
    }
    
    const ecart = recetteDeclare - recettePotentielle;
    const taux = (ecart / recettePotentielle) * 100;
    
    let couleur, classe;
    if (taux > -10) {
        couleur = 'success';
        classe = 'deperdition-vert';
    } else if (taux >= -30) {
        couleur = 'warning';
        classe = 'deperdition-orange';
    } else {
        couleur = 'danger';
        classe = 'deperdition-rouge';
    }
    
    return { taux: taux.toFixed(2), couleur, classe };
}

// Formate un montant en FCFA
function formatMontantFCFA(montant) {
    if (!montant && montant !== 0) return '0 FCFA';
    
    const montantInt = parseInt(montant);
    return montantInt.toLocaleString('fr-FR') + ' FCFA';
}

// Valide un numéro de téléphone camerounais
function validateCameroonPhone(phone) {
    const patterns = [
        /^\+237[6-9]\d{8}$/,  // Format international
        /^[6-9]\d{8}$/,       // Format national
        /^237[6-9]\d{8}$/     // Avec préfixe sans +
    ];
    
    return patterns.some(pattern => pattern.test(phone));
}

// Valide un matricule SUPPER
function validateMatricule(matricule) {
    // Format: 3+ lettres suivies de 3+ chiffres (ex: INV001, CHEF123)
    const pattern = /^[A-Z]{3,}[0-9]{3,}$/;
    return pattern.test(matricule.toUpperCase());
}

// Gère la saisie d'inventaire par périodes
function setupInventaireSaisie() {
    const periodeInputs = document.querySelectorAll('.periode-input');
    let totalVehicules = 0;
    
    periodeInputs.forEach(input => {
        input.addEventListener('input', function() {
            // Valider la saisie (0-1000 véhicules)
            let value = parseInt(this.value) || 0;
            if (value < 0) value = 0;
            if (value > 1000) value = 1000;
            this.value = value;
            
            // Recalculer le total
            updateInventaireTotal();
            
            // Calculer la recette potentielle en temps réel
            updateRecettePotentielle();
        });
    });
}

// Met à jour le total de l'inventaire
function updateInventaireTotal() {
    const inputs = document.querySelectorAll('.periode-input');
    let total = 0;
    let nbPeriodes = 0;
    
    inputs.forEach(input => {
        const value = parseInt(input.value) || 0;
        if (value > 0) {
            total += value;
            nbPeriodes++;
        }
    });
    
    // Afficher le total
    const totalElement = document.getElementById('totalVehicules');
    if (totalElement) {
        totalElement.textContent = total;
    }
    
    // Afficher la moyenne
    const moyenneElement = document.getElementById('moyenneHoraire');
    if (moyenneElement && nbPeriodes > 0) {
        const moyenne = (total / nbPeriodes).toFixed(1);
        moyenneElement.textContent = moyenne;
    }
    
    return { total, nbPeriodes, moyenne: nbPeriodes > 0 ? total / nbPeriodes : 0 };
}

// Met à jour la recette potentielle calculée
function updateRecettePotentielle() {
    const stats = updateInventaireTotal();
    
    if (stats.moyenne > 0) {
        // Estimation 24h
        const estimation24h = stats.moyenne * 24;
        
        // Recette potentielle (formule SUPPER)
        const recettePotentielle = (estimation24h * 75 * 500) / 100;
        
        // Afficher les résultats
        const estimationElement = document.getElementById('estimation24h');
        if (estimationElement) {
            estimationElement.textContent = Math.round(estimation24h);
        }
        
        const recetteElement = document.getElementById('recettePotentielle');
        if (recetteElement) {
            recetteElement.textContent = formatMontantFCFA(recettePotentielle);
        }
        
        return recettePotentielle;
    }
    
    return 0;
}

// Gère la saisie de recette avec calcul automatique
function setupRecetteSaisie() {
    const recetteInput = document.getElementById('montantDeclare');
    const recettePotentielleElement = document.getElementById('recettePotentielleValue');
    
    if (recetteInput && recettePotentielleElement) {
        recetteInput.addEventListener('input', function() {
            const montantDeclare = parseFloat(this.value.replace(/[^\d]/g, '')) || 0;
            const recettePotentielle = parseFloat(recettePotentielleElement.dataset.value) || 0;
            
            // Calculer le taux de déperdition
            const result = calculateDeperditionRate(montantDeclare, recettePotentielle);
            
            // Afficher le résultat
            const tauxElement = document.getElementById('tauxDeperdition');
            if (tauxElement) {
                tauxElement.className = `badge ${result.classe}`;
                tauxElement.textContent = `${result.taux}%`;
            }
            
            // Colorer le champ selon le résultat
            this.className = `form-control border-${result.couleur}`;
        });
    }
}

// Charge les statistiques via AJAX
function loadStats(type = 'general', container = null) {
    const url = `${SUPPER.api.stats}?type=${type}`;
    
    if (container) {
        showLoading(container, 'Chargement des statistiques...');
    }
    
    fetch(url, {
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (container) {
            hideLoading(container);
            updateStatsDisplay(container, data);
        }
        return data;
    })
    .catch(error => {
        console.error('❌ Erreur chargement statistiques:', error);
        if (container) {
            hideLoading(container);
            showStatsError(container);
        }
        showToast('Erreur lors du chargement des statistiques', 'error');
    });
}

// Met à jour l'affichage des statistiques
function updateStatsDisplay(container, data) {
    // Cette fonction sera adaptée selon les données reçues
    console.log('📊 Statistiques reçues:', data);
}

// Affiche une erreur de chargement des statistiques
function showStatsError(container) {
    container.innerHTML = `
        <div class="alert alert-danger d-flex align-items-center">
            <i class="fas fa-exclamation-triangle me-2"></i>
            <div>Impossible de charger les statistiques</div>
        </div>
    `;
}

// ===================================================================
// RECHERCHE GLOBALE
// ===================================================================

// Initialise la recherche globale
function initializeGlobalSearch() {
    const searchInput = document.getElementById('globalSearch');
    if (!searchInput) return;
    
    let searchTimeout;
    
    searchInput.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        const query = this.value.trim();
        
        if (query.length >= 2) {
            searchTimeout = setTimeout(() => {
                performGlobalSearch(query);
            }, 500);
        } else {
            hideSearchResults();
        }
    });
    
    // Fermer les résultats quand on clique ailleurs
    document.addEventListener('click', function(event) {
        if (!event.target.closest('.search-container')) {
            hideSearchResults();
        }
    });
}

// Effectue une recherche globale
function performGlobalSearch(query) {
    fetch(`${SUPPER.api.search}?q=${encodeURIComponent(query)}`, {
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        displaySearchResults(data.results || []);
    })
    .catch(error => {
        console.error('❌ Erreur recherche:', error);
        hideSearchResults();
    });
}

// Affiche les résultats de recherche
function displaySearchResults(results) {
    const container = document.getElementById('searchResults');
    if (!container) return;
    
    if (results.length === 0) {
        container.innerHTML = `
            <div class="search-no-results p-3">
                <i class="fas fa-search me-2"></i>
                Aucun résultat trouvé
            </div>
        `;
    } else {
        let html = '';
        results.forEach(result => {
            html += `
                <a href="${result.url}" class="search-result-item d-block p-3 text-decoration-none">
                    <div class="fw-bold">${escapeHtml(result.title)}</div>
                    <div class="text-muted small">${escapeHtml(result.description)}</div>
                    <div class="text-primary small">${escapeHtml(result.type)}</div>
                </a>
            `;
        });
        container.innerHTML = html;
    }
    
    container.style.display = 'block';
}

// Masque les résultats de recherche
function hideSearchResults() {
    const container = document.getElementById('searchResults');
    if (container) {
        container.style.display = 'none';
    }
}

// ===================================================================
// GESTION DES ERREURS GLOBALES
// ===================================================================

// Gère les erreurs JavaScript globales
window.addEventListener('error', function(event) {
    console.error('❌ Erreur JavaScript:', event.error);
    
    // Ne pas afficher d'erreur à l'utilisateur pour les erreurs mineures
    if (!event.error.message.includes('ResizeObserver') && 
        !event.error.message.includes('Non-Error promise')) {
        showToast('Une erreur inattendue s\'est produite', 'error');
    }
});

// Gère les promesses rejetées
window.addEventListener('unhandledrejection', function(event) {
    console.error('❌ Promesse rejetée:', event.reason);
    event.preventDefault(); // Empêcher l'affichage dans la console
});

// ===================================================================
// FONCTIONS D'EXPORT GLOBAL
// ===================================================================

// Expose les fonctions principales pour utilisation dans les templates
window.SUPPER = window.SUPPER || {};
Object.assign(window.SUPPER, {
    // Utilitaires
    showToast,
    showLoading,
    hideLoading,
    confirmAction,
    
    // Formatage
    formatMontantFCFA,
    calculateDeperditionRate,
    
    // Validation
    validateCameroonPhone,
    validateMatricule,
    
    // Inventaire
    setupInventaireSaisie,
    updateInventaireTotal,
    updateRecettePotentielle,
    
    // Recettes
    setupRecetteSaisie,
    
    // Statistiques
    loadStats,
    
    // Recherche
    initializeGlobalSearch,
    
    // Notifications
    loadNotifications,
    markNotificationAsRead
});

console.log('✅ SUPPER JavaScript initialisé et prêt');