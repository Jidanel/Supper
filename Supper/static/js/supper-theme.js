/* =====================================================================
   SUPPER - Aide d'affichage mobile
   Pour les tableaux marqués "table-stack" : copie le titre de chaque colonne
   dans un attribut data-label de chaque cellule. Le CSS (supper-theme.css)
   s'en sert pour afficher chaque ligne comme une carte sur téléphone.
   ===================================================================== */
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('table.table-stack').forEach(function (table) {          // Pour chaque tableau concerné
        var titres = Array.prototype.map.call(                                         // Titres des colonnes (ligne d'en-tête)
            table.querySelectorAll('thead th'), function (th) { return th.textContent.trim(); });
        table.querySelectorAll('tbody tr').forEach(function (tr) {                     // Pour chaque ligne de données
            var index = 0;                                                             // Position de la colonne courante
            Array.prototype.forEach.call(tr.children, function (td) {
                if (td.tagName !== 'TD') { return; }                                   // Ignore ce qui n'est pas une cellule
                var span = td.colSpan || 1;                                            // Cellule fusionnée ?
                if (span === 1) {
                    td.setAttribute('data-label', titres[index] || '');                // Étiquette = titre de la colonne
                    var val = document.createElement('span');                          // Conteneur unique pour la valeur
                    val.className = 'td-val';
                    while (td.firstChild) { val.appendChild(td.firstChild); }          // Déplace le contenu (garde les événements)
                    td.appendChild(val);
                }
                else { td.classList.add('td-full'); }                                  // Cellule fusionnée = pleine largeur
                index += span;                                                         // Avance de span colonnes
            });
        });
    });
});
