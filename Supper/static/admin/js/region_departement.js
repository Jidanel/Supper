/* ===================================================================
   static/admin/js/region_departement.js - Widget dynamique régions
   ===================================================================
   📄 NOUVEAU fichier à créer dans static/admin/js/region_departement.js */

/**
 * Données des régions et départements du Cameroun
 * Source: Découpage administratif officiel
 */
const REGIONS_DEPARTEMENTS = {
    'adamaoua': {
        'nom': 'Adamaoua',
        'departements': [
            'Djerem',
            'Faro-et-Déo',
            'Mayo-Banyo',
            'Mbéré',
            'Vina'
        ]
    },
    'centre': {
        'nom': 'Centre',
        'departements': [
            'Haute-Sanaga',
            'Lekié',
            'Mbam-et-Inoubou',
            'Mbam-et-Kim',
            'Méfou-et-Afamba',
            'Méfou-et-Akono',
            'Mfoundi',
            'Nyong-et-Kéllé',
            'Nyong-et-Mfoumou',
            'Nyong-et-So\'o'
        ]
    },
    'est': {
        'nom': 'Est',
        'departements': [
            'Boumba-et-Ngoko',
            'Haut-Nyong',
            'Kadey',
            'Lom-et-Djerem'
        ]
    },
    'extreme_nord': {
        'nom': 'Extrême-Nord',
        'departements': [
            'Diamaré',
            'Logone-et-Chari',
            'Mayo-Danay',
            'Mayo-Kani',
            'Mayo-Sava',
            'Mayo-Tsanaga'
        ]
    },
    'littoral': {
        'nom': 'Littoral',
        'departements': [
            'Moungo',
            'Nkam',
            'Sanaga-Maritime',
            'Wouri'
        ]
    },
    'nord': {
        'nom': 'Nord',
        'departements': [
            'Bénoué',
            'Faro',
            'Mayo-Louti',
            'Mayo-Rey'
        ]
    },
    'nord_ouest': {
        'nom': 'Nord-Ouest',
        'departements': [
            'Boyo',
            'Bui',
            'Donga-Mantung',
            'Menchum',
            'Mezam',
            'Momo',
            'Ngo-Ketunjia'
        ]
    },
    'ouest': {
        'nom': 'Ouest',
        'departements': [
            'Bamboutos',
            'Haut-Nkam',
            'Hauts-Plateaux',
            'Koung-Khi',
            'Menoua',
            'Mifi',
            'Ndé',
            'Noun'
        ]
    },
    'sud': {
        'nom': 'Sud',
        'departements': [
            'Dja-et-Lobo',
            'Mvila',
            'Océan',
            'Vallée-du-Ntem'
        ]
    },
    'sud_ouest': {
        'nom': 'Sud-Ouest',
        'departements': [
            'Fako',
            'Koupé-Manengouba',
            'Lebialem',
            'Manyu',
            'Meme',
            'Ndian'
        ]
    }
};

/**
 * Classe pour gérer le widget région/département
 */
class RegionDepartementWidget {
    constructor(regionSelectId, departementSelectId) {
        this.regionSelect = document.getElementById(regionSelectId);
        this.departementSelect = document.getElementById(departementSelectId);
        
        if (!this.regionSelect || !this.departementSelect) {
            console.warn('RegionDepartementWidget: Éléments select non trouvés');
            return;
        }
        
        this.init();
    }
    
    /**
     * Initialise le widget
     */
    init() {
        // Événement sur changement de région
        this.regionSelect.addEventListener('change', (e) => {
            this.updateDepartements(e.target.value);
        });
        
        // Charger les départements si une région est déjà sélectionnée
        if (this.regionSelect.value) {
            this.updateDepartements(this.regionSelect.value);
        }
        
        // Ajouter des styles visuels
        this.addVisualEnhancements();
    }
    
    /**
     * Met à jour la liste des départements selon la région sélectionnée
     */
    updateDepartements(regionValue) {
        // Vider la liste des départements
        this.departementSelect.innerHTML = '<option value="">Sélectionner un département...</option>';
        
        if (!regionValue || !REGIONS_DEPARTEMENTS[regionValue]) {
            this.departementSelect.disabled = true;
            this.updateSelectStatus(this.departementSelect, 'disabled');
            return;
        }
        
        const region = REGIONS_DEPARTEMENTS[regionValue];
        
        // Ajouter les départements de la région
        region.departements.forEach(departement => {
            const option = document.createElement('option');
            option.value = departement;
            option.textContent = departement;
            this.departementSelect.appendChild(option);
        });
        
        // Réactiver le select des départements
        this.departementSelect.disabled = false;
        this.updateSelectStatus(this.departementSelect, 'enabled');
        
        // Animation de mise à jour
        this.animateUpdate(this.departementSelect);
    }
    
    /**
     * Ajoute des améliorations visuelles
     */
    addVisualEnhancements() {
        // Ajouter des icônes
        this.addIconToSelect(this.regionSelect, 'fas fa-map-marker-alt');
        this.addIconToSelect(this.departementSelect, 'fas fa-building');
        
        // Classes CSS personnalisées
        this.regionSelect.classList.add('region-select', 'enhanced-select');
        this.departementSelect.classList.add('departement-select', 'enhanced-select');
        
        // État initial
        if (!this.regionSelect.value) {
            this.departementSelect.disabled = true;
            this.updateSelectStatus(this.departementSelect, 'disabled');
        }
    }
    
    /**
     * Ajoute une icône à un élément select
     */
    addIconToSelect(selectElement, iconClass) {
        const wrapper = document.createElement('div');
        wrapper.className = 'select-wrapper position-relative';
        
        const icon = document.createElement('i');
        icon.className = iconClass + ' select-icon';
        icon.style.cssText = `
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: #6c757d;
            pointer-events: none;
            z-index: 1;
        `;
        
        // Modifier le padding du select pour faire place à l'icône
        selectElement.style.paddingLeft = '40px';
        
        // Insérer le wrapper
        selectElement.parentNode.insertBefore(wrapper, selectElement);
        wrapper.appendChild(icon);
        wrapper.appendChild(selectElement);
    }
    
    /**
     * Met à jour le statut visuel d'un select
     */
    updateSelectStatus(selectElement, status) {
        selectElement.classList.remove('select-enabled', 'select-disabled');
        selectElement.classList.add(`select-${status}`);
        
        // Mettre à jour l'icône si présente
        const icon = selectElement.parentNode.querySelector('.select-icon');
        if (icon) {
            if (status === 'enabled') {
                icon.style.color = '#007bff';
                icon.classList.add('text-primary');
            } else {
                icon.style.color = '#6c757d';
                icon.classList.remove('text-primary');
            }
        }
    }
    
    /**
     * Animation de mise à jour
     */
    animateUpdate(element) {
        element.style.transform = 'scale(1.02)';
        element.style.transition = 'transform 0.2s ease';
        
        setTimeout(() => {
            element.style.transform = 'scale(1)';
        }, 200);
    }
    
    /**
     * Obtient tous les départements d'une région
     */
    static getDepartementsForRegion(regionValue) {
        return REGIONS_DEPARTEMENTS[regionValue]?.departements || [];
    }
    
    /**
     * Obtient le nom complet d'une région
     */
    static getRegionName(regionValue) {
        return REGIONS_DEPARTEMENTS[regionValue]?.nom || regionValue;
    }
    
    /**
     * Valide qu'un département appartient bien à une région
     */
    static validateDepartementInRegion(regionValue, departementValue) {
        const region = REGIONS_DEPARTEMENTS[regionValue];
        if (!region) return false;
        return region.departements.includes(departementValue);
    }
    
    /**
     * Recherche une région par département
     */
    static findRegionByDepartement(departementValue) {
        for (const [regionKey, regionData] of Object.entries(REGIONS_DEPARTEMENTS)) {
            if (regionData.departements.includes(departementValue)) {
                return {
                    key: regionKey,
                    nom: regionData.nom
                };
            }
        }
        return null;
    }
}

/**
 * Fonction d'initialisation automatique
 */
function initRegionDepartementWidgets() {
    // Rechercher automatiquement les paires région/département
    const regionSelects = document.querySelectorAll('select[name*="region"]');
    
    regionSelects.forEach(regionSelect => {
        // Essayer de trouver le select département correspondant
        let departementSelect = null;
        
        // Stratégies de recherche
        const strategies = [
            () => document.querySelector('select[name*="departement"]'),
            () => document.getElementById(regionSelect.id.replace('region', 'departement')),
            () => regionSelect.parentNode.nextElementSibling?.querySelector('select'),
            () => regionSelect.closest('form')?.querySelector('select[name*="departement"]')
        ];
        
        for (const strategy of strategies) {
            departementSelect = strategy();
            if (departementSelect) break;
        }
        
        if (departementSelect) {
            new RegionDepartementWidget(regionSelect.id, departementSelect.id);
        }
    });
}

/**
 * Utilitaire pour créer dynamiquement un widget
 */
function createRegionDepartementWidget(container, options = {}) {
    const defaults = {
        regionName: 'region',
        departementName: 'departement',
        regionLabel: 'Région',
        departementLabel: 'Département',
        required: false,
        cssClasses: 'form-select mb-3'
    };
    
    const config = { ...defaults, ...options };
    
    // Créer le HTML
    const html = `
        <div class="row">
            <div class="col-md-6">
                <label for="${config.regionName}" class="form-label">
                    <i class="fas fa-map-marker-alt me-2"></i>${config.regionLabel}
                </label>
                <select name="${config.regionName}" id="${config.regionName}" 
                        class="${config.cssClasses}" ${config.required ? 'required' : ''}>
                    <option value="">Sélectionner une région...</option>
                    ${Object.entries(REGIONS_DEPARTEMENTS).map(([key, region]) => 
                        `<option value="${key}">${region.nom}</option>`
                    ).join('')}
                </select>
            </div>
            <div class="col-md-6">
                <label for="${config.departementName}" class="form-label">
                    <i class="fas fa-building me-2"></i>${config.departementLabel}
                </label>
                <select name="${config.departementName}" id="${config.departementName}" 
                        class="${config.cssClasses}" disabled ${config.required ? 'required' : ''}>
                    <option value="">Sélectionner un département...</option>
                </select>
            </div>
        </div>
    `;

    // Insérer le HTML dans le container passé en paramètre
    if (container && container instanceof HTMLElement) {
        container.innerHTML = html;

        // Initialiser le widget sur les selects créés dynamiquement
        new RegionDepartementWidget(config.regionName, config.departementName);
    }

    // Retourne le HTML au cas où on voudrait l'utiliser autrement
    return html;
}