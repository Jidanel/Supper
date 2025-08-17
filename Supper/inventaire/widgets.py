# ===================================================================
# SOLUTION COMPLÈTE : inventaire/widgets.py
# Widget avec JavaScript intégré - Aucun fichier externe requis
# ===================================================================

from django import forms
from django.utils.safestring import mark_safe
from django.utils.html import format_html
import calendar
import json


class CalendrierJoursWidget(forms.Textarea):
    """
    🔧 SOLUTION COMPLÈTE : Widget calendrier avec JavaScript intégré
    """
    
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'calendrier-jours-widget',
            'style': 'display: none;'  # Masquer le textarea
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)
    
    def format_value(self, value):
        """Formater la valeur pour Django admin"""
        if value is None:
            return '[]'
        
        if isinstance(value, list):
            return json.dumps(value)
        
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return value
                else:
                    return '[]'
            except (json.JSONDecodeError, ValueError):
                return '[]'
        
        return '[]'
    
    def render(self, name, value, attrs=None, renderer=None):
        """Génère le HTML du calendrier avec JavaScript intégré"""
        if attrs is None:
            attrs = {}
        
        value_formatted = self.format_value(value)
        widget_id = attrs.get('id', f'id_{name}')
        
        # Récupérer la liste des jours
        try:
            jours_list = json.loads(value_formatted) if value_formatted else []
        except:
            jours_list = []
        
        # Textarea Django standard
        textarea_html = super().render(name, value_formatted, attrs, renderer)
        
        # Interface calendrier avec JavaScript INTÉGRÉ
        calendrier_html = f'''
        <div class="calendrier-widget-container" style="margin-top: 10px;">
            <div class="calendrier-widget" id="{widget_id}_widget">
                
                <div class="calendrier-controls" style="margin-bottom: 15px;">
                    <button type="button" class="btn btn-sm btn-success" onclick="selectAllDays_{widget_id}()">
                        ✓ Tout sélectionner
                    </button>
                    <button type="button" class="btn btn-sm btn-secondary" onclick="clearAllDays_{widget_id}()">
                        ✗ Tout désélectionner
                    </button>
                    <button type="button" class="btn btn-sm btn-info" onclick="selectWeekdays_{widget_id}()">
                        📅 Jours ouvrables
                    </button>
                </div>
                
                <div class="calendrier-grid" id="{widget_id}_calendar">
                    <p style="text-align: center; color: #999; grid-column: 1 / -1; padding: 20px;">
                        Sélectionnez d'abord un mois et une année pour afficher le calendrier
                    </p>
                </div>
                
                <div class="calendrier-info" style="margin-top: 10px; font-size: 12px; color: #666;">
                    <span id="{widget_id}_count">{len(jours_list)}</span> jour(s) sélectionné(s)
                </div>
            </div>
        </div>
        
        <style>
            .calendrier-widget {{
                max-width: 600px;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 15px;
                background: #f9f9f9;
                margin-top: 10px;
            }}
            
            .calendrier-grid {{
                display: grid;
                grid-template-columns: repeat(7, 1fr);
                gap: 5px;
                margin: 15px 0;
                min-height: 200px;
            }}
            
            .calendrier-header {{
                display: contents;
            }}
            
            .calendrier-header-day {{
                text-align: center;
                font-weight: bold;
                padding: 8px;
                background: #6B46C1;
                color: white;
                border-radius: 4px;
                font-size: 12px;
            }}
            
            .calendrier-day {{
                width: 40px;
                height: 40px;
                border: 2px solid #ddd;
                border-radius: 6px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                background: white;
                transition: all 0.3s ease;
                user-select: none;
                justify-self: center;
            }}
            
            .calendrier-day:hover {{
                border-color: #6B46C1;
                transform: scale(1.05);
            }}
            
            .calendrier-day.selected {{
                background: #6B46C1;
                color: white;
                border-color: #553C9A;
            }}
            
            .calendrier-day.empty {{
                border: none;
                background: transparent;
                cursor: default;
            }}
            
            .calendrier-day.weekend {{
                background: #f0f0f0;
                color: #999;
            }}
            
            .calendrier-day.weekend.selected {{
                background: #F59E0B;
                color: white;
            }}
            
            .btn {{
                padding: 5px 10px;
                margin-right: 5px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
            }}
            
            .btn-success {{ background: #28a745; color: white; }}
            .btn-secondary {{ background: #6c757d; color: white; }}
            .btn-info {{ background: #17a2b8; color: white; }}
        </style>
        
        <script>
        (function() {{
            // Variables spécifiques à ce widget
            let selectedDays_{widget_id} = {json.dumps(jours_list)};
            const textarea_{widget_id} = document.getElementById('{widget_id}');
            const calendarContainer_{widget_id} = document.getElementById('{widget_id}_calendar');
            const countElement_{widget_id} = document.getElementById('{widget_id}_count');
            
            function generateCalendar_{widget_id}() {{
                const moisSelect = document.querySelector('select[name="mois"]');
                const anneeInput = document.querySelector('input[name="annee"]');
                
                if (!moisSelect || !anneeInput || !moisSelect.value || !anneeInput.value) {{
                    calendarContainer_{widget_id}.innerHTML = 
                        '<p style="text-align: center; color: #999; grid-column: 1 / -1; padding: 20px;">' +
                        'Sélectionnez d\\'abord un mois et une année pour afficher le calendrier</p>';
                    return;
                }}
                
                const month = parseInt(moisSelect.value);
                const year = parseInt(anneeInput.value);
                
                if (!month || !year || month < 1 || month > 12 || year < 1900 || year > 2100) {{
                    calendarContainer_{widget_id}.innerHTML = 
                        '<p style="text-align: center; color: #red; grid-column: 1 / -1; padding: 20px;">' +
                        'Mois ou année invalide</p>';
                    return;
                }}
                
                try {{
                    // En-tête jours de la semaine
                    const daysOfWeek = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
                    let html = '';
                    
                    daysOfWeek.forEach(day => {{
                        html += `<div class="calendrier-header-day">${{day}}</div>`;
                    }});
                    
                    // Calcul du calendrier
                    const firstDay = new Date(year, month - 1, 1);
                    const daysInMonth = new Date(year, month, 0).getDate();
                    let firstDayOfWeek = firstDay.getDay();
                    firstDayOfWeek = firstDayOfWeek === 0 ? 6 : firstDayOfWeek - 1;
                    
                    // Jours vides au début
                    for (let i = 0; i < firstDayOfWeek; i++) {{
                        html += '<div class="calendrier-day empty"></div>';
                    }}
                    
                    // Jours du mois
                    for (let day = 1; day <= daysInMonth; day++) {{
                        const dayDate = new Date(year, month - 1, day);
                        const dayOfWeek = dayDate.getDay();
                        const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
                        const isSelected = selectedDays_{widget_id}.includes(day);
                        
                        let classes = 'calendrier-day';
                        if (isWeekend) classes += ' weekend';
                        if (isSelected) classes += ' selected';
                        
                        html += `<div class="${{classes}}" onclick="toggleDay_{widget_id}(${{day}})">${{day}}</div>`;
                    }}
                    
                    calendarContainer_{widget_id}.innerHTML = html;
                    updateCount_{widget_id}();
                    
                }} catch (e) {{
                    console.error('Erreur génération calendrier:', e);
                    calendarContainer_{widget_id}.innerHTML = 
                        '<p style="color: red; grid-column: 1 / -1; text-align: center; padding: 20px;">' +
                        'Erreur lors de la génération du calendrier</p>';
                }}
            }}
            
            function updateCount_{widget_id}() {{
                if (countElement_{widget_id}) {{
                    countElement_{widget_id}.textContent = selectedDays_{widget_id}.length;
                }}
            }}
            
            function updateTextarea_{widget_id}() {{
                selectedDays_{widget_id} = selectedDays_{widget_id}
                    .filter(day => typeof day === 'number' && day >= 1 && day <= 31)
                    .sort((a, b) => a - b);
                
                if (textarea_{widget_id}) {{
                    textarea_{widget_id}.value = JSON.stringify(selectedDays_{widget_id});
                }}
                updateCount_{widget_id}();
            }}
            
            // Fonctions globales pour ce widget
            window.toggleDay_{widget_id} = function(day) {{
                const dayNum = parseInt(day);
                const index = selectedDays_{widget_id}.indexOf(dayNum);
                
                if (index > -1) {{
                    selectedDays_{widget_id}.splice(index, 1);
                }} else {{
                    selectedDays_{widget_id}.push(dayNum);
                }}
                
                updateTextarea_{widget_id}();
                generateCalendar_{widget_id}();
            }};
            
            window.selectAllDays_{widget_id} = function() {{
                const moisSelect = document.querySelector('select[name="mois"]');
                const anneeInput = document.querySelector('input[name="annee"]');
                
                if (!moisSelect || !anneeInput || !moisSelect.value || !anneeInput.value) {{
                    alert('Veuillez d\\'abord sélectionner un mois et une année');
                    return;
                }}
                
                const month = parseInt(moisSelect.value);
                const year = parseInt(anneeInput.value);
                
                selectedDays_{widget_id} = [];
                const daysInMonth = new Date(year, month, 0).getDate();
                for (let i = 1; i <= daysInMonth; i++) {{
                    selectedDays_{widget_id}.push(i);
                }}
                
                updateTextarea_{widget_id}();
                generateCalendar_{widget_id}();
            }};
            
            window.clearAllDays_{widget_id} = function() {{
                selectedDays_{widget_id} = [];
                updateTextarea_{widget_id}();
                generateCalendar_{widget_id}();
            }};
            
            window.selectWeekdays_{widget_id} = function() {{
                const moisSelect = document.querySelector('select[name="mois"]');
                const anneeInput = document.querySelector('input[name="annee"]');
                
                if (!moisSelect || !anneeInput || !moisSelect.value || !anneeInput.value) {{
                    alert('Veuillez d\\'abord sélectionner un mois et une année');
                    return;
                }}
                
                const month = parseInt(moisSelect.value);
                const year = parseInt(anneeInput.value);
                
                selectedDays_{widget_id} = [];
                const daysInMonth = new Date(year, month, 0).getDate();
                
                for (let day = 1; day <= daysInMonth; day++) {{
                    const dayDate = new Date(year, month - 1, day);
                    const dayOfWeek = dayDate.getDay();
                    if (dayOfWeek >= 1 && dayOfWeek <= 5) {{ // Lundi à vendredi
                        selectedDays_{widget_id}.push(day);
                    }}
                }}
                
                updateTextarea_{widget_id}();
                generateCalendar_{widget_id}();
            }};
            
            // Écouter les changements des champs mois/année
            function setupListeners_{widget_id}() {{
                const moisSelect = document.querySelector('select[name="mois"]');
                const anneeInput = document.querySelector('input[name="annee"]');
                
                if (moisSelect) {{
                    moisSelect.addEventListener('change', generateCalendar_{widget_id});
                }}
                
                if (anneeInput) {{
                    anneeInput.addEventListener('change', generateCalendar_{widget_id});
                    anneeInput.addEventListener('input', generateCalendar_{widget_id});
                }}
            }}
            
            // Initialisation
            document.addEventListener('DOMContentLoaded', function() {{
                setupListeners_{widget_id}();
                // Petit délai pour s'assurer que tous les champs sont chargés
                setTimeout(function() {{
                    generateCalendar_{widget_id}();
                }}, 500);
            }});
            
            // Si le DOM est déjà chargé
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', function() {{
                    setupListeners_{widget_id}();
                    setTimeout(generateCalendar_{widget_id}, 500);
                }});
            }} else {{
                setupListeners_{widget_id}();
                setTimeout(generateCalendar_{widget_id}, 500);
            }}
        }})();
        </script>
        '''
        
        return mark_safe(textarea_html + calendrier_html)


# ===================================================================
# FORM POUR InventaireMensuel
# ===================================================================

class InventaireMensuelForm(forms.ModelForm):
    """Form avec widget calendrier intégré"""
    
    class Meta:
        model = None
        fields = '__all__'
        widgets = {
            'jours_actifs': CalendrierJoursWidget(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if 'titre' in self.fields:
            self.fields['titre'].widget.attrs.update({
                'class': 'vTextField',
                'placeholder': 'Ex: Inventaire Septembre 2025 - Région Centre'
            })
        
        if 'description' in self.fields:
            self.fields['description'].widget.attrs.update({
                'class': 'vLargeTextField',
                'rows': 4,
                'placeholder': 'Description détaillée de cet inventaire mensuel...'
            })
    
    def clean_jours_actifs(self):
        """Validation des jours actifs"""
        jours_actifs = self.cleaned_data.get('jours_actifs')
        
        if isinstance(jours_actifs, str):
            try:
                jours_list = json.loads(jours_actifs)
                if isinstance(jours_list, list):
                    jours_valides = []
                    for jour in jours_list:
                        try:
                            jour_int = int(jour)
                            if 1 <= jour_int <= 31:
                                jours_valides.append(jour_int)
                        except (ValueError, TypeError):
                            continue
                    return jours_valides
                else:
                    return []
            except (json.JSONDecodeError, ValueError):
                return []
        
        elif isinstance(jours_actifs, list):
            jours_valides = []
            for jour in jours_actifs:
                try:
                    jour_int = int(jour)
                    if 1 <= jour_int <= 31:
                        jours_valides.append(jour_int)
                except (ValueError, TypeError):
                    continue
            return jours_valides
        
        return []