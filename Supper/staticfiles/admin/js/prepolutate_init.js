// ===================================================================
// static/admin/js/prepopulate_init.js
// ===================================================================

// Vérifier que django est défini avant utilisation
if (typeof django !== 'undefined') {
    django.jQuery(document).ready(function($) {
        // Code de prépopulation Django standard
        console.log('Prepopulate init SUPPER loaded');
    });
} else {
    // Fallback si django n'est pas disponible
    document.addEventListener('DOMContentLoaded', function() {
        console.log('Prepopulate init SUPPER loaded (fallback)');
    });
}