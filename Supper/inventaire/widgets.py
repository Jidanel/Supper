# ===================================================================
# CRÉER LE FICHIER : inventaire/widgets.py
# Widget calendrier personnalisé pour les jours actifs
# ===================================================================

from django import forms
from django.utils.safestring import mark_safe
from django.utils.html import format_html
import calendar
import json


class CalendrierJoursWidget(forms.Widget):
    """
    Widget personnalisé pour afficher un calendrier interactif
    permettant de sélectionner les jours actifs
    """
    
    template_name = 'admin/widgets/calendrier_jours.html'
    
    def __init__(self, attrs=None):
        default_attrs = {'class': 'calendrier-jours-widget'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)
    
    def format_value(self, value):
        """Formatte la valeur pour l'affichage"""
        if value is None:
            return []
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return []
        return value if isinstance(value, list) else []
    
    def render(self, name, value, attrs=None, renderer=None):
        """Génère le HTML du calendrier"""
        if attrs is None:
            attrs = {}
        
        # Récupérer les jours sélectionnés
        jours_selectionnes = self.format_value(value)
        
        # Générer l'ID unique pour ce widget
        widget_id = attrs.get('id', f'id_{name}')
        
        # HTML du calendrier
        html = f'''
        <div class="calendrier-widget" id="{widget_id}_widget">
            <input type="hidden" name="{name}" id="{widget_id}" value="{json.dumps(jours_selectionnes)}">
            
            <div class="calendrier-controls" style="margin-bottom: 15px;">
                <button type="button" class="btn btn-sm btn-success" onclick="selectAllDays('{widget_id}')">
                    ✓ Tout sélectionner
                </button>
                <button type="button" class="btn btn-sm btn-secondary" onclick="clearAllDays('{widget_id}')">
                    ✗ Tout désélectionner
                </button>
                <button type="button" class="btn btn-sm btn-info" onclick="selectWeekdays('{widget_id}')">
                    📅 Jours ouvrables
                </button>
            </div>
            
            <div class="calendrier-grid" id="{widget_id}_calendar">
                <!-- Le calendrier sera généré par JavaScript -->
            </div>
            
            <div class="calendrier-info" style="margin-top: 10px; font-size: 12px; color: #666;">
                <span id="{widget_id}_count">0</span> jour(s) sélectionné(s)
            </div>
        </div>
        
        <style>
            .calendrier-widget {{
                max-width: 600px;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 15px;
                background: #f9f9f9;
            }}
            
            .calendrier-grid {{
                display: grid;
                grid-template-columns: repeat(7, 1fr);
                gap: 5px;
                margin: 15px 0;
            }}
            
            .calendrier-header {{
                display: grid;
                grid-template-columns: repeat(7, 1fr);
                gap: 5px;
                margin-bottom: 10px;
            }}
            
            .calendrier-header div {{
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
            document.addEventListener('DOMContentLoaded', function() {{
                initCalendrier('{widget_id}');
            }});
        </script>
        '''
        
        return mark_safe(html)
    
    def value_from_datadict(self, data, files, name):
        """Récupère la valeur depuis les données du formulaire"""
        value = data.get(name, '[]')
        try:
            return json.loads(value) if value else []
        except (json.JSONDecodeError, ValueError):
            return []
    
    class Media:
        js = ('admin/js/calendrier_widget.js',)


# ===================================================================
# FORM PERSONNALISÉ pour InventaireMensuel
# ===================================================================

class InventaireMensuelForm(forms.ModelForm):
    """Form personnalisé avec widget calendrier"""
    
    class Meta:
        model = None  # Sera défini dans l'admin
        fields = '__all__'
        widgets = {
            'jours_actifs': CalendrierJoursWidget(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Améliorer les autres champs
        if 'titre' in self.fields:
            self.fields['titre'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Ex: Inventaire Septembre 2025 - Région Centre'
            })
        
        if 'description' in self.fields:
            self.fields['description'].widget.attrs.update({
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Description détaillée de cet inventaire mensuel...'
            })