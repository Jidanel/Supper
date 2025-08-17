// ===================================================================
// CRÉER LE FICHIER : static/admin/js/calendrier_widget.js
// JavaScript pour le widget calendrier interactif CORRIGÉ
// ===================================================================

function initCalendrier(widgetId) {
    const widget = document.getElementById(widgetId + '_widget');
    const hiddenInput = document.getElementById(widgetId);
    const calendarContainer = document.getElementById(widgetId + '_calendar');
    const countElement = document.getElementById(widgetId + '_count');
    
    if (!widget || !hiddenInput || !calendarContainer) {
        console.error('Éléments du calendrier non trouvés pour:', widgetId);
        return;
    }
    
    // 🔧 CORRECTION : Gestion robuste de la date
    const today = new Date();
    let currentMonth = today.getMonth() + 1;
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
            const newMonth = parseInt(this.value);
            if (newMonth && !isNaN(newMonth)) {
                currentMonth = newMonth;
                generateCalendar();
            }
        });
    }
    
    if (anneeInput) {
        anneeInput.addEventListener('change', function() {
            const newYear = parseInt(this.value);
            if (newYear && !isNaN(newYear) && newYear > 1900 && newYear < 3000) {
                currentYear = newYear;
                generateCalendar();
            }
        });
    }
    
    let selectedDays = [];
    
    // 🔧 CORRECTION : Charger les jours sélectionnés de façon robuste
    function loadSelectedDays() {
        try {
            const value = hiddenInput.value;
            if (!value || value === '') {
                selectedDays = [];
                return;
            }
            
            const parsed = JSON.parse(value);
            selectedDays = Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            console.warn('Erreur parsing jours sélectionnés:', e);
            selectedDays = [];
        }
    }
    
    function generateCalendar() {
        if (!currentMonth || !currentYear || isNaN(currentMonth) || isNaN(currentYear)) {
            calendarContainer.innerHTML = '<p style="text-align: center; color: #999;">Sélectionnez d\'abord un mois et une année</p>';
            return;
        }
        
        try {
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
            
        } catch (e) {
            console.error('Erreur génération calendrier:', e);
            calendarContainer.innerHTML = '<p style="color: red;">Erreur lors de la génération du calendrier</p>';
        }
    }
    
    function updateCount() {
        if (countElement) {
            countElement.textContent = selectedDays.length;
        }
    }
    
    function updateHiddenInput() {
        try {
            // 🔧 CORRECTION : Trier et nettoyer les jours avant sérialisation
            selectedDays = selectedDays
                .filter(day => typeof day === 'number' && day >= 1 && day <= 31)
                .sort((a, b) => a - b);
            
            hiddenInput.value = JSON.stringify(selectedDays);
            updateCount();
        } catch (e) {
            console.error('Erreur mise à jour input:', e);
        }
    }
    
    // 🔧 CORRECTION : Fonctions globales avec vérification d'ID
    window.toggleDay = function(day, wId) {
        if (wId !== widgetId) return;
        
        try {
            const dayNum = parseInt(day);
            if (isNaN(dayNum) || dayNum < 1 || dayNum > 31) return;
            
            const index = selectedDays.indexOf(dayNum);
            if (index > -1) {
                selectedDays.splice(index, 1);
            } else {
                selectedDays.push(dayNum);
            }
            
            updateHiddenInput();
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
            updateHiddenInput();
            generateCalendar();
        } catch (e) {
            console.error('Erreur select all:', e);
        }
    };
    
    window.clearAllDays = function(wId) {
        if (wId !== widgetId) return;
        
        try {
            selectedDays = [];
            updateHiddenInput();
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
                // Lundi à Vendredi (1-5)
                if (dayOfWeek >= 1 && dayOfWeek <= 5) {
                    selectedDays.push(day);
                }
            }
            updateHiddenInput();
            generateCalendar();
        } catch (e) {
            console.error('Erreur select weekdays:', e);
        }
    };
    
    // Initialisation
    loadSelectedDays();
    generateCalendar();
}