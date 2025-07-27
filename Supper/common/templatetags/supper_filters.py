# ===================================================================
# Fichier : common/templatetags/supper_filters.py
# Filtres template personnalisés pour SUPPER
# ===================================================================

from django import template
from django.utils.safestring import mark_safe
import locale

register = template.Library()


@register.filter
def multiply(value, arg):
    """
    Multiplie une valeur par un argument
    Usage: {{ nombre|multiply:10 }}
    """
    try:
        return float(value or 0) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def percentage_10(value):
    """
    Calcule le pourcentage sur 10 périodes (max 100%)
    Usage: {{ nombre_periodes|percentage_10 }}
    """
    try:
        result = (float(value or 0) * 10)
        return min(result, 100)  # Maximum 100%
    except (ValueError, TypeError):
        return 0


@register.filter
def format_fcfa(value):
    """
    Formate un montant en FCFA avec séparateurs
    Usage: {{ montant|format_fcfa }}
    """
    try:
        if value is None or value == '':
            return "0 FCFA"
        
        # Convertir en entier pour éviter les décimales
        montant_int = int(float(value))
        
        # Formater avec séparateurs de milliers
        return f"{montant_int:,} FCFA".replace(',', ' ')
    except (ValueError, TypeError):
        return "0 FCFA"


@register.filter
def couleur_deperdition(taux):
    """
    Retourne la classe CSS selon le taux de déperdition
    Usage: {{ taux_deperdition|couleur_deperdition }}
    """
    try:
        taux_float = float(taux or 0)
        
        if taux_float > -10:
            return 'deperdition-vert'
        elif taux_float >= -30:
            return 'deperdition-orange'
        else:
            return 'deperdition-rouge'
    except (ValueError, TypeError):
        return 'deperdition-gris'


@register.filter
def status_badge(value):
    """
    Retourne la classe badge selon le statut
    Usage: {{ statut|status_badge }}
    """
    status_mapping = {
        'ouvert': 'jour-ouvert',
        'ferme': 'jour-ferme', 
        'impertinent': 'jour-impertinent',
        'actif': 'statut-actif',
        'inactif': 'statut-inactif',
        True: 'statut-actif',
        False: 'statut-inactif'
    }
    
    return status_mapping.get(value, 'badge-secondary')


@register.filter
def truncate_smart(value, length=50):
    """
    Tronque intelligemment un texte en gardant les mots entiers
    Usage: {{ texte|truncate_smart:30 }}
    """
    try:
        if not value or len(value) <= length:
            return value
        
        # Trouver le dernier espace avant la limite
        truncated = value[:length]
        last_space = truncated.rfind(' ')
        
        if last_space > 0:
            return truncated[:last_space] + '...'
        else:
            return truncated + '...'
    except:
        return value


@register.filter
def get_item(dictionary, key):
    """
    Récupère un élément d'un dictionnaire avec une clé dynamique
    Usage: {{ mon_dict|get_item:ma_cle }}
    """
    try:
        return dictionary.get(key, '')
    except:
        return ''


@register.filter
def phone_format(phone):
    """
    Formate un numéro de téléphone camerounais
    Usage: {{ telephone|phone_format }}
    """
    try:
        # Nettoyer le numéro
        clean_phone = ''.join(filter(str.isdigit, str(phone)))
        
        # Format camerounais
        if len(clean_phone) == 9:
            return f"+237 {clean_phone[:3]} {clean_phone[3:6]} {clean_phone[6:]}"
        elif len(clean_phone) == 12 and clean_phone.startswith('237'):
            num = clean_phone[3:]
            return f"+237 {num[:3]} {num[3:6]} {num[6:]}"
        else:
            return phone
    except:
        return phone


@register.filter
def duration_format(duration):
    """
    Formate une durée en format lisible
    Usage: {{ duree|duration_format }}
    """
    try:
        if not duration:
            return "N/A"
        
        total_seconds = duration.total_seconds()
        
        if total_seconds < 1:
            return f"{total_seconds*1000:.0f} ms"
        elif total_seconds < 60:
            return f"{total_seconds:.1f}s"
        else:
            minutes = int(total_seconds // 60)
            seconds = int(total_seconds % 60)
            return f"{minutes}m {seconds}s"
    except:
        return "N/A"


@register.simple_tag
def progress_bar(current, total, css_class="bg-primary"):
    """
    Génère une barre de progression HTML
    Usage: {% progress_bar 7 10 "bg-success" %}
    """
    try:
        if total == 0:
            percentage = 0
        else:
            percentage = min((current / total) * 100, 100)
        
        return mark_safe(f'''
            <div class="progress" style="height: 6px;">
                <div class="progress-bar {css_class}" 
                     style="width: {percentage}%" 
                     role="progressbar" 
                     aria-valuenow="{current}" 
                     aria-valuemin="0" 
                     aria-valuemax="{total}">
                </div>
            </div>
        ''')
    except:
        return ""


@register.simple_tag
def icon_status(status):
    """
    Retourne une icône selon le statut
    Usage: {% icon_status "success" %}
    """
    icons = {
        'success': '<i class="fas fa-check-circle text-success"></i>',
        'error': '<i class="fas fa-times-circle text-danger"></i>',
        'warning': '<i class="fas fa-exclamation-triangle text-warning"></i>',
        'info': '<i class="fas fa-info-circle text-info"></i>',
        'loading': '<i class="fas fa-spinner fa-spin text-primary"></i>',
        'ouvert': '<i class="fas fa-unlock text-success"></i>',
        'ferme': '<i class="fas fa-lock text-secondary"></i>',
        'impertinent': '<i class="fas fa-exclamation-triangle text-warning"></i>'
    }
    
    return mark_safe(icons.get(status, '<i class="fas fa-question-circle text-muted"></i>'))


@register.inclusion_tag('common/components/alert.html')
def alert_box(type, message, dismissible=True):
    """
    Génère une boîte d'alerte
    Usage: {% alert_box "success" "Message de succès" %}
    """
    return {
        'type': type,
        'message': message,
        'dismissible': dismissible
    }


@register.inclusion_tag('common/components/badge.html')
def status_badge_component(value, label=None):
    """
    Génère un badge de statut
    Usage: {% status_badge_component inventaire.verrouille "Verrouillé" %}
    """
    return {
        'value': value,
        'label': label or str(value),
        'css_class': status_badge(value)
    }


# ===================================================================
# FILTRES POUR LES DATES
# ===================================================================

@register.filter
def days_ago(date_value):
    """
    Calcule le nombre de jours depuis une date
    Usage: {{ ma_date|days_ago }}
    """
    try:
        from datetime import date
        if isinstance(date_value, date):
            delta = date.today() - date_value
            return delta.days
        return 0
    except:
        return 0


@register.filter
def is_recent(date_value, days=7):
    """
    Vérifie si une date est récente (moins de X jours)
    Usage: {{ ma_date|is_recent:3 }}
    """
    try:
        return days_ago(date_value) <= days
    except:
        return False


# ===================================================================
# FILTRES POUR LES PERMISSIONS
# ===================================================================

@register.filter
def has_permission(user, permission):
    """
    Vérifie si un utilisateur a une permission
    Usage: {{ user|has_permission:"peut_gerer_inventaire" }}
    """
    try:
        return hasattr(user, permission) and getattr(user, permission, False)
    except:
        return False


@register.filter
def can_access_poste(user, poste):
    """
    Vérifie si un utilisateur peut accéder à un poste
    Usage: {{ user|can_access_poste:poste }}
    """
    try:
        if hasattr(user, 'peut_acceder_poste'):
            return user.peut_acceder_poste(poste)
        return False
    except:
        return False