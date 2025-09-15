document.addEventListener('DOMContentLoaded', function() {
    const regionSelect = document.getElementById('id_region');
    const departementSelect = document.getElementById('id_departement');
    
    if (!regionSelect || !departementSelect) return;
    
    function updateDepartements() {
        const regionId = regionSelect.value;
        
        if (!regionId) {
            departementSelect.innerHTML = '<option value="">---------</option>';
            departementSelect.disabled = true;
            return;
        }
        
        // Faire une requête AJAX pour obtenir les départements
        fetch(`/api/departements/?region=${regionId}`)
            .then(response => response.json())
            .then(data => {
                departementSelect.innerHTML = '<option value="">---------</option>';
                data.departements.forEach(dept => {
                    const option = document.createElement('option');
                    option.value = dept.id;
                    option.textContent = dept.nom;
                    departementSelect.appendChild(option);
                });
                departementSelect.disabled = false;
            })
            .catch(error => {
                console.error('Erreur lors du chargement des départements:', error);
                departementSelect.disabled = true;
            });
    }
    
    regionSelect.addEventListener('change', updateDepartements);
    
    // Charger les départements initiaux si une région est déjà sélectionnée
    if (regionSelect.value) {
        updateDepartements();
    }
});