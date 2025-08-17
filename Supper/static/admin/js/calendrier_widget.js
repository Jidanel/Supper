// ===================================================================
// CRÉER LE FICHIER : static/admin/js/calendrier_widget.js
// JavaScript pour le widget calendrier interactif
// ===================================================================

function initCalendrier(widgetId) {
    const widget = document.getElementById(widgetId + '_widget');
    const hiddenInput = document.getElementById(widgetId);
    const calendarContainer = document.getElementById(widgetId + '_calendar');
    const countElement = document.getElementById(widgetId + '_count');
    
    if (!widget || !hiddenInput || !calendarContainer) {
        console.error('Éléments du calendrier non trouvés');
        return;
    }
    
    // Récupérer la date actuelle ou celle du formulaire
    const today = new Date();
    let currentMonth = today.getMonth() + 1; // JavaScript months are 0-based
    let currentYear = today.getFullYear();
    
    // Essayer de récupérer le mois/année depuis le formulaire
    const moisSelect = document.querySelector('select[name="mois"]');
    const anneeInput = document.querySelector('input[name="annee"]');
    
    if (moisSelect && moisSelect.value) {
        currentMonth = parseInt(moisSelect.value);
    }
    if (anneeInput && anneeInput.value) {
        currentYear = parseInt(anneeInput.value);
    }
    
    // Écouter les changements de mois/année
    if (moisSelect) {
        moisSelect.addEventListener('change', function() {
            currentMonth = parseInt(this.value);
            if (currentMonth && currentYear) {
                generateCalendar();
            }
        });
    }
    
    if (anneeInput) {
        anneeInput.addEventListener('change', function() {
            currentYear = parseInt(this.value);
            if (currentMonth && currentYear) {
                generateCalendar();
            }
        });
    }
    
    let selectedDays = [];
    
    // Charger les jours sélectionnés
    try {
        const value = hiddenInput.value;
        selectedDays = value ? JSON.parse(value) : [];
    } catch (e) {
        selectedDays = [];
    }
    
    function generateCalendar() {
        if (!currentMonth || !currentYear) {
            calendarContainer.innerHTML = '<p>Sélectionnez d\'abord un mois et une année</p>';
            return;
        }
        
        // Générer l'en-tête des jours de la semaine
        const daysOfWeek = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
        let calendarHTML = '<div class="calendrier-header">';
        daysOfWeek.forEach(day => {
            calendarHTML += `<div>${day}</div>`;
        });
        calendarHTML += '</div>';
        
        // Calculer le calendrier du mois
        const firstDay = new Date(currentYear, currentMonth - 1, 1);
        const lastDay = new Date(currentYear, currentMonth, 0);
        const daysInMonth = lastDay.getDate();
        
        // Le premier jour de la semaine (0 = dimanche, 1 = lundi, etc.)
        let firstDayOfWeek = firstDay.getDay();
        // Convertir pour que lundi = 0
        firstDayOfWeek = firstDayOfWeek === 0 ? 6 : firstDayOfWeek - 1;
        
        calendarHTML += '<div class="calendrier-grid">';
        
        // Ajouter les jours vides au début
        for (let i = 0; i < firstDayOfWeek; i++) {
            calendarHTML += '<div class="calendrier-day empty"></div>';
        }
        
        // Ajouter tous les jours du mois
        for (let day = 1; day <= daysInMonth; day++) {
            const dayDate = new Date(currentYear, currentMonth - 1, day);
            const dayOfWeek = dayDate.getDay();
            const isWeekend = dayOfWeek === 0 || dayOfWeek === 6; // Dimanche ou Samedi
            const isSelected = selectedDays.includes(day);
            
            let classes = 'calendrier-day';
            if (isWeekend) classes += ' weekend';
            if (isSelected) classes += ' selected';
            
            calendarHTML += `
                <div class="${classes}" 
                     data-day="${day}" 
                     onclick="toggleDay(${day}, '${widgetId}')">
                    ${day}
                </div>
            `;
        }
        
        calendarHTML += '</div>';
        calendarContainer.innerHTML = calendarHTML;
        updateCount();
    }
    
    function updateCount() {
        if (countElement) {
            countElement.textContent = selectedDays.length;
        }
    }
    
    function updateHiddenInput() {
        hiddenInput.value = JSON.stringify(selectedDays);
        updateCount();
    }
    
    // Fonctions globales pour les boutons
    window.toggleDay = function(day, wId) {
        if (wId !== widgetId) return;
        
        const index = selectedDays.indexOf(day);
        if (index > -1) {
            selectedDays.splice(index, 1);
        } else {
            selectedDays.push(day);
        }
        selectedDays.sort((a, b) => a - b);
        updateHiddenInput();
        generateCalendar();
    };
    
    window.selectAllDays = function(wId) {
        if (wId !== widgetId) return;
        
        selectedDays = [];
        const daysInMonth = new Date(currentYear, currentMonth, 0).getDate();
        for (let i = 1; i <= daysInMonth; i++) {
            selectedDays.push(i);
        }
        updateHiddenInput();
        generateCalendar();
    };
    
    window.clearAllDays = function(wId) {
        if (wId !== widgetId) return;
        
        selectedDays = [];
        updateHiddenInput();
        generateCalendar();
    };
    
    window.selectWeekdays = function(wId) {
        if (wId !== widgetId) return;
        
        selectedDays = [];
        const daysInMonth = new Date(currentYear, currentMonth, 0).getDate();
        
        for (let day = 1; day <= daysInMonth; day++) {
            const dayDate = new Date(currentYear, currentMonth - 1, day);
            const dayOfWeek = dayDate.getDay();
            // Lundi à Vendredi (1-5)
            if (dayOfWeek >= 1 && dayOfWeek <= 5) {
                selectedDays.push(day);
            }
        }
        updateHiddenInput();
        generateCalendar();
    };
    
    // Générer le calendrier initial
    generateCalendar();
}