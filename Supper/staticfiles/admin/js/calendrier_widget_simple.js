// ===================================================================
// FICHIER : static/admin/js/calendrier_widget_simple.js
// JavaScript simplifié pour éviter les erreurs JSON
// ===================================================================

function initCalendrierSimple(widgetId, initialDays) {
    const textarea = document.getElementById(widgetId);
    const calendarContainer = document.getElementById(widgetId + '_calendar');
    const countElement = document.getElementById(widgetId + '_count');
    
    if (!textarea || !calendarContainer) {
        console.error('Éléments du calendrier non trouvés pour:', widgetId);
        return;
    }
    
    // Variables globales pour ce widget
    let selectedDays = Array.isArray(initialDays) ? initialDays : [];
    let currentMonth = null;
    let currentYear = null;
    
    // Récupérer le mois/année depuis le formulaire
    function updateDateFromForm() {
        const moisSelect = document.querySelector('select[name="mois"]');
        const anneeInput = document.querySelector('input[name="annee"]');
        
        if (moisSelect && moisSelect.value) {
            currentMonth = parseInt(moisSelect.value);
        }
        if (anneeInput && anneeInput.value) {
            currentYear = parseInt(anneeInput.value);
        }
        
        // Si pas de date dans le form, utiliser la date actuelle
        if (!currentMonth || !currentYear) {
            const today = new Date();
            currentMonth = currentMonth || (today.getMonth() + 1);
            currentYear = currentYear || today.getFullYear();
        }
    }
    
    // Écouter les changements
    function setupEventListeners() {
        const moisSelect = document.querySelector('select[name="mois"]');
        const anneeInput = document.querySelector('input[name="annee"]');
        
        if (moisSelect) {
            moisSelect.addEventListener('change', function() {
                currentMonth = parseInt(this.value);
                generateCalendar();
            });
        }
        
        if (anneeInput) {
            anneeInput.addEventListener('change', function() {
                currentYear = parseInt(this.value);
                generateCalendar();
            });
        }
    }
    
    function generateCalendar() {
        if (!currentMonth || !currentYear) {
            calendarContainer.innerHTML = '<p style="text-align: center; color: #999;">Sélectionnez un mois et une année</p>';
            return;
        }
        
        try {
            // En-tête
            const daysOfWeek = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
            let html = '<div class="calendrier-header">';
            daysOfWeek.forEach(day => {
                html += `<div>${day}</div>`;
            });
            html += '</div>';
            
            // Calcul du calendrier
            const firstDay = new Date(currentYear, currentMonth - 1, 1);
            const lastDay = new Date(currentYear, currentMonth, 0);
            const daysInMonth = lastDay.getDate();
            
            let firstDayOfWeek = firstDay.getDay();
            firstDayOfWeek = firstDayOfWeek === 0 ? 6 : firstDayOfWeek - 1;
            
            html += '<div class="calendrier-grid">';
            
            // Jours vides
            for (let i = 0; i < firstDayOfWeek; i++) {
                html += '<div class="calendrier-day empty"></div>';
            }
            
            // Jours du mois
            for (let day = 1; day <= daysInMonth; day++) {
                const dayDate = new Date(currentYear, currentMonth - 1, day);
                const dayOfWeek = dayDate.getDay();
                const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
                const isSelected = selectedDays.includes(day);
                
                let classes = 'calendrier-day';
                if (isWeekend) classes += ' weekend';
                if (isSelected) classes += ' selected';
                
                html += `<div class="${classes}" data-day="${day}" onclick="toggleDaySimple(${day}, '${widgetId}')">${day}</div>`;
            }
            
            html += '</div>';
            calendarContainer.innerHTML = html;
            updateCount();
            
        } catch (e) {
            console.error('Erreur génération calendrier:', e);
            calendarContainer.innerHTML = '<p style="color: red;">Erreur génération calendrier</p>';
        }
    }
    
    function updateCount() {
        if (countElement) {
            countElement.textContent = selectedDays.length;
        }
    }
    
    function updateTextarea() {
        try {
            selectedDays = selectedDays
                .filter(day => typeof day === 'number' && day >= 1 && day <= 31)
                .sort((a, b) => a - b);
            
            textarea.value = JSON.stringify(selectedDays);
            updateCount();
        } catch (e) {
            console.error('Erreur mise à jour textarea:', e);
        }
    }
    
    // Fonctions globales
    window.toggleDaySimple = function(day, wId) {
        if (wId !== widgetId) return;
        
        try {
            const dayNum = parseInt(day);
            const index = selectedDays.indexOf(dayNum);
            
            if (index > -1) {
                selectedDays.splice(index, 1);
            } else {
                selectedDays.push(dayNum);
            }
            
            updateTextarea();
            generateCalendar();
        } catch (e) {
            console.error('Erreur toggle day:', e);
        }
    };
    
    window.selectAllDays = function(wId) {
        if (wId !== widgetId) return;
        
        try {
            if (!currentMonth || !currentYear) return;
            
            selectedDays = [];
            const daysInMonth = new Date(currentYear, currentMonth, 0).getDate();
            for (let i = 1; i <= daysInMonth; i++) {
                selectedDays.push(i);
            }
            updateTextarea();
            generateCalendar();
        } catch (e) {
            console.error('Erreur select all:', e);
        }
    };
    
    window.clearAllDays = function(wId) {
        if (wId !== widgetId) return;
        
        try {
            selectedDays = [];
            updateTextarea();
            generateCalendar();
        } catch (e) {
            console.error('Erreur clear all:', e);
        }
    };
    
    window.selectWeekdays = function(wId) {
        if (wId !== widgetId) return;
        
        try {
            if (!currentMonth || !currentYear) return;
            
            selectedDays = [];
            const daysInMonth = new Date(currentYear, currentMonth, 0).getDate();
            
            for (let day = 1; day <= daysInMonth; day++) {
                const dayDate = new Date(currentYear, currentMonth - 1, day);
                const dayOfWeek = dayDate.getDay();
                if (dayOfWeek >= 1 && dayOfWeek <= 5) {
                    selectedDays.push(day);
                }
            }
            updateTextarea();
            generateCalendar();
        } catch (e) {
            console.error('Erreur select weekdays:', e);
        }
    };
    
    // Initialisation
    updateDateFromForm();
    setupEventListeners();
    generateCalendar();
}