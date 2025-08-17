// <!-- Créer le fichier : Supper/static/admin/js/region_departement.js -->
<script>
// Dictionnaire des départements par région du Cameroun
const DEPARTEMENTS_CAMEROUN = {
    'adamaoua': [
        'Djérem', 'Faro-et-Déo', 'Mayo-Banyo', 'Mbéré', 'Vina'
    ],
    'centre': [
        'Haute-Sanaga', 'Lekié', 'Mbam-et-Inoubou', 'Mbam-et-Kim',
        'Méfou-et-Afamba', 'Méfou-et-Akono', 'Mfoundi', 'Nyong-et-Kellé',
        'Nyong-et-Mfoumou', 'Nyong-et-So\'o'
    ],
    'est': [
        'Boumba-et-Ngoko', 'Haut-Nyong', 'Kadey', 'Lom-et-Djérem'
    ],
    'extreme_nord': [
        'Diamaré', 'Logone-et-Chari', 'Mayo-Danay', 'Mayo-Kani',
        'Mayo-Sava', 'Mayo-Tsanaga'
    ],
    'littoral': [
        'Moungo', 'Nkam', 'Sanaga-Maritime', 'Wouri'
    ],
    'nord': [
        'Bénoué', 'Faro', 'Mayo-Louti', 'Mayo-Rey'
    ],
    'nord_ouest': [
        'Boyo', 'Bui', 'Donga-Mantung', 'Menchum', 'Mezam',
        'Momo', 'Ngo-Ketunjia'
    ],
    'ouest': [
        'Bamboutos', 'Haut-Nkam', 'Hauts-Plateaux', 'Koung-Khi',
        'Menoua', 'Mifi', 'Ndé', 'Noun'
    ],
    'sud': [
        'Dja-et-Lobo', 'Mvila', 'Océan', 'Vallée-du-Ntem'
    ],
    'sud_ouest': [
        'Fako', 'Koupé-Manengouba', 'Lebialem', 'Manyu', 'Meme', 'Ndian'
    ]
};


function updateDepartements() {
    const regionSelect = document.getElementById('id_region');
    const departementSelect = document.getElementById('id_departement');
    
    if (!regionSelect || !departementSelect) return;
    
    const selectedRegion = regionSelect.value;
    const currentDepartement = departementSelect.value;
    
    // Vider la liste des départements
    departementSelect.innerHTML = '';
    
    // Ajouter l'option par défaut
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = '--- Sélectionner un département ---';
    departementSelect.appendChild(defaultOption);
    
    // Si une région est sélectionnée, ajouter ses départements
    if (selectedRegion && DEPARTEMENTS_CAMEROUN[selectedRegion]) {
        const departements = DEPARTEMENTS_CAMEROUN[selectedRegion];
        
        departements.forEach(dept => {
            const option = document.createElement('option');
            option.value = dept;
            option.textContent = dept;
            
            // Restaurer la sélection si c'était le département actuel
            if (dept === currentDepartement) {
                option.selected = true;
            }
            
            departementSelect.appendChild(option);
        });
    }
}

// Initialiser au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    const regionSelect = document.getElementById('id_region');
    
    if (regionSelect) {
        // Mettre à jour les départements au chargement
        updateDepartements();
        
        // Ajouter l'écouteur d'événement pour les changements
        regionSelect.addEventListener('change', updateDepartements);
    }
    
    // Pour Django Admin, utiliser django.jQuery si disponible
    if (typeof django !== 'undefined' && django.jQuery) {
        django.jQuery(document).ready(function() {
            updateDepartements();
            
            django.jQuery('#id_region').on('change', function() {
                updateDepartements();
            });
        });
    }
});

// Fonction pour initialiser les départements dans l'admin Django
if (typeof django !== 'undefined') {
    django.jQuery(document).ready(function($) {
        // Attendre que le DOM soit complètement chargé
        setTimeout(function() {
            const regionField = $('#id_region');
            const departementField = $('#id_departement');
            
            if (regionField.length && departementField.length) {
                // Sauvegarder la valeur actuelle du département
                const currentDept = departementField.val();
                
                // Mettre à jour immédiatement
                updateDepartements();
                
                // Restaurer la valeur si elle existe
                if (currentDept) {
                    departementField.val(currentDept);
                }
            }
        }, 100);
    });
}
</script>