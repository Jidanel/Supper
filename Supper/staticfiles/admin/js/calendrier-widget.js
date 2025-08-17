// ===================================================================
// static/js/calendrier-widget.js
// JavaScript pour améliorer l'UX du widget calendrier
// ===================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Initialiser les fonctionnalités du widget calendrier
    initCalendrierWidgets();
    
    // Initialiser les tooltips Bootstrap si disponible
    if (typeof bootstrap !== 'undefined') {
        initTooltips();
    }
    
    // Vérifier le statut des jours sélectionnés
    initStatusJourVerification();
    
    // Initialiser les améliorations d'accessibilité
    setTimeout(enhanceAccessibility, 100);
});

function initCalendrierWidgets() {
    const widgets = document.querySelectorAll('.calendrier-widget, input[type="date"]');
    
    widgets.forEach(function(input) {
        // Ajouter la classe si pas déjà présente
        if (!input.classList.contains('calendrier-widget')) {
            input.classList.add('calendrier-widget');
        }
        
        // Animation lors du changement
        input.addEventListener('change', function() {
            this.classList.add('changed');
            
            // Vérifier le statut du jour si possible
            verifierStatutJour(this);
            
            setTimeout(() => {
                this.classList.remove('changed');
            }, 1000);
        });
        
        // Validation en temps réel
        input.addEventListener('input', function() {
            validateDate(this);
        });
        
        // Améliorer l'accessibilité
        if (!input.getAttribute('aria-label')) {
            input.setAttribute('aria-label', 'Sélectionner une date');
        }
        
        // Définir les limites de date si pas déjà fait
        if (!input.min) {
            // Limiter à 1 an dans le passé
            const pastLimit = new Date();
            pastLimit.setFullYear(pastLimit.getFullYear() - 1);
            input.min = pastLimit.toISOString().split('T')[0];
        }
        
        if (!input.max) {
            // Limiter à aujourd'hui (pas de dates futures)
            const today = new Date();
            input.max = today.toISOString().split('T')[0];
        }
    });
}

function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.forEach(function (tooltipTriggerEl) {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

function validateDate(input) {
    const value = input.value;
    const today = new Date().toISOString().split('T')[0];
    
    // Supprimer les classes de validation précédentes
    input.classList.remove('is-valid', 'is-invalid');
    
    if (!value) {
        return; // Pas de validation si vide
    }
    
    // Vérifier si la date est dans le futur
    if (value > today) {
        input.classList.add('is-invalid');
        showDateError(input, 'La date ne peut pas être dans le futur');
        return false;
    }
    
    // Vérifier si la date est trop ancienne (plus d'un an)
    const pastLimit = new Date();
    pastLimit.setFullYear(pastLimit.getFullYear() - 1);
    const pastLimitStr = pastLimit.toISOString().split('T')[0];
    
    if (value < pastLimitStr) {
        input.classList.add('is-invalid');
        showDateError(input, 'Date trop ancienne (plus d\'un an)');
        return false;
    }
    
    // Date valide
    input.classList.add('is-valid');
    clearDateError(input);
    return true;
}

function showDateError(input, message) {
    // Supprimer l'erreur existante
    clearDateError(input);
    
    // Créer le message d'erreur
    const errorDiv = document.createElement('div');
    errorDiv.className = 'date-error-message';
    errorDiv.style.cssText = `
        color: #dc3545;
        font-size: 12px;
        margin-top: 4px;
        padding: 4px 8px;
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-radius: 4px;
    `;
    errorDiv.textContent = message;
    
    // Insérer après le champ
    input.parentNode.insertBefore(errorDiv, input.nextSibling);
}

function clearDateError(input) {
    const existingError = input.parentNode.querySelector('.date-error-message');
    if (existingError) {
        existingError.remove();
    }
}

function verifierStatutJour(dateInput) {
    const date = dateInput.value;
    if (!date) return;
    
    // Chercher le champ poste associé
    const form = dateInput.closest('form');
    if (!form) return;
    
    const posteField = form.querySelector('select[name="poste"], input[name="poste"]');
    const posteId = posteField ? posteField.value : null;
    
    // Appel API pour vérifier le statut
    checkDayStatusAPI(date, posteId)
        .then(data => {
            afficherStatutJour(dateInput, data);
        })
        .catch(error => {
            console.warn('Impossible de vérifier le statut du jour:', error);
        });
}

function afficherStatutJour(dateInput, statusData) {
    // Supprimer l'affichage de statut existant
    const existingStatus = dateInput.parentNode.querySelector('.status-jour-display');
    if (existingStatus) {
        existingStatus.remove();
    }
    
    if (!statusData) return;
    
    // Créer l'affichage du statut
    const statusDiv = document.createElement('div');
    statusDiv.className = 'status-jour-display';
    statusDiv.style.cssText = `
        margin-top: 8px;
        padding: 6px 10px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 6px;
    `;
    
    // Déterminer le style selon le statut
    let statusClass = '';
    let statusText = '';
    let statusIcon = '';
    
    if (statusData.inventaire_ouvert && statusData.recette_ouvert) {
        statusClass = 'ouvert';
        statusText = 'Jour ouvert pour inventaires et recettes';
        statusIcon = '✓';
        statusDiv.style.background = '#dcfce7';
        statusDiv.style.color = '#166534';
        statusDiv.style.border = '1px solid #bbf7d0';
    } else if (statusData.recette_ouvert) {
        statusClass = 'partiellement-ouvert';
        statusText = 'Jour ouvert pour recettes uniquement';
        statusIcon = '⚠';
        statusDiv.style.background = '#fef3c7';
        statusDiv.style.color = '#92400e';
        statusDiv.style.border = '1px solid #fde68a';
    } else if (statusData.inventaire_ouvert) {
        statusClass = 'partiellement-ouvert';
        statusText = 'Jour ouvert pour inventaires uniquement';
        statusIcon = '⚠';
        statusDiv.style.background = '#fef3c7';
        statusDiv.style.color = '#92400e';
        statusDiv.style.border = '1px solid #fde68a';
    } else {
        statusClass = 'ferme';
        statusText = 'Jour fermé pour toutes les saisies';
        statusIcon = '✗';
        statusDiv.style.background = '#fef2f2';
        statusDiv.style.color = '#991b1b';
        statusDiv.style.border = '1px solid #fecaca';
    }
    
    statusDiv.innerHTML = `
        <span style="font-weight: bold;">${statusIcon}</span>
        <span>${statusText}</span>
    `;
    
    statusDiv.className += ` ${statusClass}`;
    
    // Insérer après le champ de date
    dateInput.parentNode.insertBefore(statusDiv, dateInput.nextSibling);
}

function initStatusJourVerification() {
    // Vérifier automatiquement le statut au chargement de la page
    const dateInputs = document.querySelectorAll('input[type="date"], .calendrier-widget');
    
    dateInputs.forEach(input => {
        if (input.value) {
            setTimeout(() => verifierStatutJour(input), 500);
        }
    });
}

// API pour vérifier le statut d'un jour (si disponible)
function checkDayStatusAPI(date, posteId = null) {
    const url = '/inventaire/api/check-day-status/';
    const params = new URLSearchParams({ date });
    
    if (posteId) {
        params.append('poste_id', posteId);
    }
    
    return fetch(`${url}?${params}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Erreur réseau');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                return data.data;
            } else {
                throw new Error(data.error || 'Erreur inconnue');
            }
        })
        .catch(error => {
            // Retourner des données par défaut en cas d'erreur
            console.warn('API non disponible, mode dégradé activé:', error);
            return {
                inventaire_ouvert: true,
                recette_ouvert: true,
                mode_degrade: true
            };
        });
}

// Fonction utilitaire pour formater les dates
function formatDateFr(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('fr-FR', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

// Amélioration de l'accessibilité
function enhanceAccessibility() {
    document.querySelectorAll('.calendrier-widget').forEach(input => {
        // Ajouter des instructions pour les lecteurs d'écran
        if (!input.getAttribute('aria-describedby')) {
            const helpText = document.createElement('div');
            helpText.id = `help-${input.id || Math.random().toString(36).substr(2, 9)}`;
            helpText.className = 'sr-only';
            helpText.textContent = 'Utilisez les flèches pour naviguer dans le calendrier, Entrée pour sélectionner';
            helpText.style.cssText = `
                position: absolute !important;
                width: 1px !important;
                height: 1px !important;
                padding: 0 !important;
                margin: -1px !important;
                overflow: hidden !important;
                clip: rect(0, 0, 0, 0) !important;
                white-space: nowrap !important;
                border: 0 !important;
            `;
            
            input.parentNode.appendChild(helpText);
            input.setAttribute('aria-describedby', helpText.id);
        }
    });
}

// Gestion des raccourcis clavier
document.addEventListener('keydown', function(e) {
    const activeElement = document.activeElement;
    
    if (activeElement && activeElement.classList.contains('calendrier-widget')) {
        // Raccourcis utiles pour la navigation
        switch(e.key) {
            case 'T':
            case 't':
                if (e.ctrlKey || e.metaKey) {
                    e.preventDefault();
                    // Définir la date d'aujourd'hui
                    const today = new Date().toISOString().split('T')[0];
                    activeElement.value = today;
                    activeElement.dispatchEvent(new Event('change', { bubbles: true }));
                    
                    // Afficher un feedback visuel
                    activeElement.style.backgroundColor = '#e7f3ff';
                    setTimeout(() => {
                        activeElement.style.backgroundColor = '';
                    }, 500);
                }
                break;
                
            case 'Escape':
                activeElement.blur();
                break;
                
            case 'Enter':
                // Valider et passer au champ suivant
                if (validateDate(activeElement)) {
                    const nextField = findNextFormField(activeElement);
                    if (nextField) {
                        nextField.focus();
                    }
                }
                break;
        }
    }
});

// Fonction pour trouver le prochain champ du formulaire
function findNextFormField(currentField) {
    const form = currentField.closest('form');
    if (!form) return null;
    
    const formFields = form.querySelectorAll('input, select, textarea');
    const currentIndex = Array.from(formFields).indexOf(currentField);
    
    for (let i = currentIndex + 1; i < formFields.length; i++) {
        const field = formFields[i];
        if (!field.disabled && !field.hidden && field.type !== 'hidden') {
            return field;
        }
    }
    
    return null;
}

// Fonction pour ajouter un feedback visuel lors de la validation
function addValidationFeedback(input, isValid, message = '') {
    // Supprimer le feedback existant
    const existingFeedback = input.parentNode.querySelector('.validation-feedback');
    if (existingFeedback) {
        existingFeedback.remove();
    }
    
    if (message) {
        const feedback = document.createElement('div');
        feedback.className = 'validation-feedback';
        feedback.style.cssText = `
            font-size: 12px;
            margin-top: 4px;
            color: ${isValid ? '#28a745' : '#dc3545'};
        `;
        feedback.textContent = message;
        
        input.parentNode.insertBefore(feedback, input.nextSibling);
    }
}

// Fonction pour gérer les événements de focus/blur
function initFocusHandlers() {
    document.querySelectorAll('.calendrier-widget').forEach(input => {
        input.addEventListener('focus', function() {
            this.style.transform = 'scale(1.02)';
            this.style.transition = 'transform 0.2s ease';
        });
        
        input.addEventListener('blur', function() {
            this.style.transform = '';
            validateDate(this);
        });
    });
}

// Initialiser les gestionnaires de focus au chargement
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(initFocusHandlers, 200);
});

// Fonction pour détecter les changements de poste et revalider
function initPosteChangeHandler() {
    document.querySelectorAll('select[name="poste"]').forEach(select => {
        select.addEventListener('change', function() {
            // Revalider toutes les dates du formulaire
            const form = this.closest('form');
            if (form) {
                const dateInputs = form.querySelectorAll('.calendrier-widget');
                dateInputs.forEach(input => {
                    if (input.value) {
                        setTimeout(() => verifierStatutJour(input), 100);
                    }
                });
            }
        });
    });
}

// Initialiser le gestionnaire de changement de poste
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(initPosteChangeHandler, 300);
});

// Export des fonctions pour usage externe
window.CalendrierWidget = {
    init: initCalendrierWidgets,
    validate: validateDate,
    checkStatus: verifierStatutJour,
    formatDate: formatDateFr,
    showError: showDateError,
    clearError: clearDateError
};

// Log de démarrage pour le debug
console.log('CalendrierWidget initialisé - Version 1.0');

// Gestionnaire d'erreurs global pour le widget
window.addEventListener('error', function(e) {
    if (e.filename && e.filename.includes('calendrier-widget.js')) {
        console.error('Erreur dans CalendrierWidget:', e.error);
    }
});

// Nettoyage automatique des erreurs après un délai
setInterval(function() {
    document.querySelectorAll('.date-error-message').forEach(error => {
        if (error.dataset.timestamp) {
            const age = Date.now() - parseInt(error.dataset.timestamp);
            if (age > 10000) { // 10 secondes
                error.remove();
            }
        } else {
            // Marquer avec timestamp si pas déjà fait
            error.dataset.timestamp = Date.now().toString();
        }
    });
}, 5000);