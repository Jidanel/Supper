/**
 * Script pour la gestion dynamique des régions et départements du Cameroun
 * dans les formulaires d'administration SUPPER
 */

// Mapping des départements par région
const DEPARTEMENTS_PAR_REGION = {
    'adamaoua': ['Djerem', 'Faro-et-Déo', 'Mayo-Banyo', 'Mbéré', 'Vina'],
    'centre': ['Haute-Sanaga', 'Lekié', 'Mbam-et-Inoubou', 'Mbam-et-Kim', 'Méfou-et-Afamba', 'Méfou-et-Akono', 'Mfoundi', 'Nyong-et-Kéllé', 'Nyong-et-Mfoumou', 'Nyong-et-So\'o'],
    'est': ['Boumba-et-Ngoko', 'Haut-Nyong', 'Kadey', 'Lom-et-Djerem'],
    'extreme_nord': ['Diamaré', 'Logone-et-Chari', 'Mayo-Danay', 'Mayo-Kani', 'Mayo-Sava', 'Mayo-Tsanaga'],
    'littoral': ['Moungo', 'Nkam', 'Sanaga-Maritime', 'Wouri'],
    'nord': ['Bénoué', 'Faro', 'Mayo-Louti', 'Mayo-Rey'],
    'nord_ouest': ['Boyo', 'Bui', 'Donga-Mantung', 'Menchum', 'Mezam', 'Momo', 'Ngo-Ketunjia'],
    'ouest': ['Bamboutos', 'Haut-Nkam', 'Hauts-Plateaux', 'Koung-Khi', 'Menoua', 'Mifi', 'Mino', 'Ndé', 'Noun'],
    'sud': ['Dja-et-Lobo', 'Mvila', 'Océan', 'Vallée-du-Ntem'],
    'sud_ouest': ['Fako', 'Koupé-Manengouba', 'Lebialem', 'Manyu', 'Meme', 'Ndian']
};

// Mapping des arrondissements par département (échantillon)
const ARRONDISSEMENTS_PAR_DEPARTEMENT = {
    'Mfoundi': ['Yaoundé I', 'Yaoundé II', 'Yaoundé III', 'Yaoundé IV', 'Yaoundé V', 'Yaoundé VI', 'Yaoundé VII'],
    'Wouri': ['Douala I', 'Douala II', 'Douala III', 'Douala IV', 'Douala V', 'Douala VI'],
    'Bénoué': ['Garoua I', 'Garoua II', 'Garoua III', 'Dembo', 'Pitoa'],
    'Mifi': ['Bafoussam I', 'Bafoussam II', 'Bafoussam III'],
    'Diamaré': ['Maroua I', 'Maroua II', 'Maroua III', 'Bogo', 'Gazawa', 'Mindif', 'Moulvoudaye'],
    // Ajouter d'autres arrondissements selon les besoins
};

class RegionDepartementWidget {
    constructor() {
        this.regionSelect = null;
        this.departementInput = null;
        this.arrondissementInput = null;
        this.init();
    }

    init() {
        // Attendre que le DOM soit chargé
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setupWidget());
        } else {
            this.setupWidget();
        }
    }

    setupWidget() {
        // Rechercher les champs dans le formulaire
        this.findFields();
        
        if (this.regionSelect) {
            this.setupRegionHandler();
            this.setupDepartementHandler();
            
            // Traiter la valeur initiale si elle existe
            this.handleInitialValues();
        }
    }

    findFields() {
        // Chercher les champs de région, département et arrondissement
        this.regionSelect = document.getElementById('id_region') || 
                           document.querySelector('select[name="region"]');
        
        this.departementInput = document.getElementById('id_departement') || 
                               document.querySelector('input[name="departement"], select[name="departement"]');
        
        this.arrondissementInput = document.getElementById('id_arrondissement') || 
                                  document.querySelector('input[name="arrondissement"], select[name="arrondissement"]');
    }

    setupRegionHandler() {
        this.regionSelect.addEventListener('change', (e) => {
            const selectedRegion = e.target.value;
            this.updateDepartementOptions(selectedRegion);
            this.clearArrondissement();
        });
    }

    setupDepartementHandler() {
        if (this.departementInput) {
            this.departementInput.addEventListener('change', (e) => {
                const selectedDepartement = e.target.value;
                this.updateArrondissementOptions(selectedDepartement);
            });
        }
    }

    updateDepartementOptions(region) {
        if (!this.departementInput || !region) {
            return;
        }

        const departements = DEPARTEMENTS_PAR_REGION[region] || [];

        if (this.departementInput.tagName === 'SELECT') {
            // Si c'est un select, mettre à jour les options
            this.clearSelect(this.departementInput);
            
            // Ajouter l'option vide
            const emptyOption = document.createElement('option');
            emptyOption.value = '';
            emptyOption.textContent = '-- Sélectionner un département --';
            this.departementInput.appendChild(emptyOption);

            // Ajouter les départements
            departements.forEach(dept => {
                const option = document.createElement('option');
                option.value = dept;
                option.textContent = dept;
                this.departementInput.appendChild(option);
            });
        } else if (this.departementInput.tagName === 'INPUT') {
            // Si c'est un input, créer une datalist pour l'autocomplétion
            this.setupDatalist(this.departementInput, departements, 'departements');
        }
    }

    updateArrondissementOptions(departement) {
        if (!this.arrondissementInput || !departement) {
            return;
        }

        const arrondissements = ARRONDISSEMENTS_PAR_DEPARTEMENT[departement] || [];

        if (this.arrondissementInput.tagName === 'SELECT') {
            this.clearSelect(this.arrondissementInput);
            
            const emptyOption = document.createElement('option');
            emptyOption.value = '';
            emptyOption.textContent = '-- Sélectionner un arrondissement --';
            this.arrondissementInput.appendChild(emptyOption);

            arrondissements.forEach(arr => {
                const option = document.createElement('option');
                option.value = arr;
                option.textContent = arr;
                this.arrondissementInput.appendChild(option);
            });
        } else if (this.arrondissementInput.tagName === 'INPUT') {
            this.setupDatalist(this.arrondissementInput, arrondissements, 'arrondissements');
        }
    }

    setupDatalist(input, options, listId) {
        // Supprimer l'ancienne datalist si elle existe
        const oldDatalist = document.getElementById(listId);
        if (oldDatalist) {
            oldDatalist.remove();
        }

        // Créer une nouvelle datalist
        const datalist = document.createElement('datalist');
        datalist.id = listId;

        options.forEach(option => {
            const optionElement = document.createElement('option');
            optionElement.value = option;
            datalist.appendChild(optionElement);
        });

        // Ajouter la datalist au document
        document.body.appendChild(datalist);
        
        // Lier l'input à la datalist
        input.setAttribute('list', listId);
        
        // Ajouter un placeholder informatif
        input.placeholder = `Tapez ou sélectionnez dans la liste...`;
    }

    clearSelect(selectElement) {
        while (selectElement.firstChild) {
            selectElement.removeChild(selectElement.firstChild);
        }
    }

    clearArrondissement() {
        if (this.arrondissementInput) {
            if (this.arrondissementInput.tagName === 'SELECT') {
                this.clearSelect(this.arrondissementInput);
                const emptyOption = document.createElement('option');
                emptyOption.value = '';
                emptyOption.textContent = '-- Sélectionner d\'abord un département --';
                this.arrondissementInput.appendChild(emptyOption);
            } else {
                this.arrondissementInput.value = '';
                this.arrondissementInput.removeAttribute('list');
            }
        }
    }

    handleInitialValues() {
        // Si une région est déjà sélectionnée, mettre à jour les départements
        if (this.regionSelect.value) {
            this.updateDepartementOptions(this.regionSelect.value);
            
            // Attendre un moment puis restaurer la valeur du département
            setTimeout(() => {
                const currentDepartement = this.departementInput.value;
                if (currentDepartement) {
                    this.updateArrondissementOptions(currentDepartement);
                }
            }, 100);
        }
    }

    // Méthode statique pour initialiser le widget
    static init() {
        new RegionDepartementWidget();
    }
}

// Auto-initialisation quand le script est chargé
RegionDepartementWidget.init();

// Export pour utilisation dans d'autres scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = RegionDepartementWidget;
}

// Fonction utilitaire pour valider une région/département
function validateRegionDepartement(region, departement) {
    if (!region || !departement) {
        return { valid: false, message: 'Région et département sont requis' };
    }

    const departements = DEPARTEMENTS_PAR_REGION[region];
    if (!departements) {
        return { valid: false, message: 'Région non valide' };
    }

    if (!departements.includes(departement)) {
        return { 
            valid: false, 
            message: `Le département "${departement}" n'existe pas dans la région "${region}"` 
        };
    }

    return { valid: true, message: 'Validation réussie' };
}

// Fonction pour obtenir tous les départements d'une région
function getDepartementsForRegion(region) {
    return DEPARTEMENTS_PAR_REGION[region] || [];
}

// Fonction pour obtenir tous les arrondissements d'un département
function getArrondissementsForDepartement(departement) {
    return ARRONDISSEMENTS_PAR_DEPARTEMENT[departement] || [];
}

// Exposer les fonctions utilitaires globalement
window.SUPPER = window.SUPPER || {};
window.SUPPER.RegionDepartementWidget = RegionDepartementWidget;
window.SUPPER.validateRegionDepartement = validateRegionDepartement;
window.SUPPER.getDepartementsForRegion = getDepartementsForRegion;
window.SUPPER.getArrondissementsForDepartement = getArrondissementsForDepartement;