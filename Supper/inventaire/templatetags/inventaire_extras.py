# ===================================================================
# inventaire/templatetags/inventaire_extras.py
# Template tags et filtres personnalisés pour SUPPER - VERSION COMPLÈTE
# ===================================================================

from django import template
from django.contrib.humanize.templatetags.humanize import intcomma
from decimal import Decimal, InvalidOperation
import locale

register = template.Library()

# ===================================================================
# FILTRES HUMANIZE (Réexportés et améliorés)
# ===================================================================
@register.filter(name='abs')
def absolute_value(value):
    """
    Retourne la valeur absolue d'un nombre
    Usage: {{ my_number|abs }}
    """
    try:
        return abs(int(value))
    except (ValueError, TypeError):
        return 0

@register.filter(name='intcomma')
def intcomma_filter(value):
    """
    Formate un nombre avec des espaces comme séparateurs de milliers
    Exemple: 1000000 -> 1 000 000
    """
    try:
        # Convertir en entier si c'est un Decimal
        if isinstance(value, Decimal):
            value = int(value)
        elif isinstance(value, float):
            value = int(value)
        
        # Formater avec des espaces
        return "{:,}".format(int(value)).replace(',', ' ')
    except (ValueError, TypeError):
        return value


@register.filter(name='floatformat')
def floatformat_filter(value, arg=2):
    """
    Formate un nombre décimal avec un nombre de décimales spécifié
    Exemple: 123.456789 avec arg=2 -> 123.46
    """
    try:
        if value is None:
            return ''
        
        # Convertir en float
        value = float(value)
        
        # Appliquer le format
        if arg == 0:
            return "{:.0f}".format(value)
        else:
            return "{:.{}f}".format(value, int(arg))
    except (ValueError, TypeError):
        return value

@register.filter(name='format_motif')
def format_motif(value):
    """
    Formate l'affichage des motifs
    Usage: {{ motif|format_motif }}
    """
    motifs_dict = {
        'taux_deperdition': 'Taux de déperdition élevé',
        'grand_stock': 'Risque de grand stock',
        'risque_baisse': 'Risque de baisse annuel',
        'presence_admin': 'Présence administrative'
    }
    return motifs_dict.get(value, value)

@register.filter(name='format_milliers')
def format_milliers(value):
    """
    Formate un nombre avec séparateurs de milliers (espaces)
    Exemple: 1500000 -> 1 500 000
    """
    try:
        value = float(value)
        return f"{value:,.0f}".replace(",", " ")
    except (ValueError, TypeError):
        return value


# ===================================================================
# FILTRES PERSONNALISÉS SUPPER - FORMATAGE
# ===================================================================

@register.filter(name='format_fcfa')
def format_fcfa(value):
    """
    Formate un montant en FCFA avec séparateurs de milliers
    Exemple: 1500000 -> 1 500 000 FCFA
    """
    try:
        if value is None:
            return "0 FCFA"
        
        # Convertir en entier
        montant = int(float(value))
        
        # Formater avec espaces
        formatted = "{:,}".format(montant).replace(',', ' ')
        
        return f"{formatted} FCFA"
    except (ValueError, TypeError):
        return "0 FCFA"


@register.filter(name='format_percentage')
def format_percentage(value, decimals=2):
    """
    Formate un nombre en pourcentage
    Exemple: -15.5678 -> -15.57%
    """
    try:
        if value is None:
            return "0.00%"
        
        value = float(value)
        
        return "{:.{}f}%".format(value, decimals)
    except (ValueError, TypeError):
        return "0.00%"


@register.filter(name='format_date_fr')
def format_date_fr(date_obj):
    """
    Formate une date au format français
    Exemple: 2025-01-15 -> 15/01/2025
    """
    try:
        if not date_obj:
            return ''
        
        return date_obj.strftime('%d/%m/%Y')
    except:
        return str(date_obj)


@register.filter(name='format_datetime_fr')
def format_datetime_fr(datetime_obj):
    """
    Formate une date-heure au format français
    Exemple: 2025-01-15 14:30:00 -> 15/01/2025 14:30
    """
    try:
        if not datetime_obj:
            return ''
        
        return datetime_obj.strftime('%d/%m/%Y %H:%M')
    except:
        return str(datetime_obj)


# ===================================================================
# FILTRES DE SÉCURITÉ - CONVERSIONS SÛRES
# ===================================================================

@register.filter(name='safe_decimal')
def safe_decimal(value, default=0):
    """
    Convertit une valeur en nombre sûr pour l'affichage
    Exemple: safe_decimal(None, 0) -> 0
    """
    if value is None:
        return default
    
    try:
        if isinstance(value, Decimal):
            return float(str(value))
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return default


@register.filter(name='safe_int')
def safe_int(value, default=0):
    """
    Convertit une valeur en entier sûr pour l'affichage
    Exemple: safe_int("abc", 0) -> 0
    """
    if value is None:
        return default
    
    try:
        if isinstance(value, Decimal):
            return int(float(str(value)))
        return int(value)
    except (TypeError, ValueError, InvalidOperation):
        return default


# ===================================================================
# FILTRES MATHÉMATIQUES - OPÉRATIONS DE BASE
# ===================================================================

@register.filter(name='abs')
def absolute_value(value):
    """
    Retourne la valeur absolue d'un nombre
    Exemple: abs(-15) -> 15
    """
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return 0


@register.filter(name='multiply')
@register.filter(name='mul')
def multiply(value, arg):
    """
    Multiplie une valeur par un argument
    Exemple: {{ 5|multiply:3 }} -> 15
    Alias: mul
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter(name='divide')
@register.filter(name='div')
@register.filter(name='dividedby')
def div(value, arg):
    """
    Divise une valeur par un argument
    Exemple: {{ 10|divide:2 }} -> 5.0
    Alias: div, dividedby
    """
    try:
        divisor = float(arg)
        if divisor == 0:
            return 0
        return float(value) / divisor
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


@register.filter(name='sub')
@register.filter(name='subtract')
def subtract(value, arg):
    """
    Soustrait arg de value
    Exemple: {{ 10|sub:3 }} -> 7
    """
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter(name='add')
def add_filter(value, arg):
    """
    Additionne value et arg
    Exemple: {{ 5|add:3 }} -> 8
    """
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return 0


# ===================================================================
# FILTRES DE COLLECTION - LISTES ET DICTIONNAIRES
# ===================================================================

@register.filter(name='get_item')
def get_item(container, key):
    """
    Récupère un élément d'un dictionnaire ou d'une liste
    Exemple dict: {{ my_dict|get_item:"key" }}
    Exemple list: {{ my_list|get_item:0 }}
    """
    if container is None:
        return None
    
    try:
        # Si c'est un dictionnaire
        if isinstance(container, dict):
            return container.get(key)
        # Si c'est une liste ou tuple
        elif isinstance(container, (list, tuple)):
            return container[int(key)]
        else:
            return None
    except (KeyError, IndexError, TypeError, ValueError):
        return None


@register.filter(name='sum_attribute')
def sum_attribute(queryset, attribute):
    """
    Somme un attribut d'une liste d'objets
    Exemple: {{ inventaires|sum_attribute:"total_vehicules" }}
    """
    try:
        return sum(getattr(item, attribute, 0) for item in queryset)
    except (TypeError, AttributeError):
        return 0


@register.filter(name='average_attribute')
def average_attribute(queryset, attribute):
    """
    Moyenne d'un attribut d'une liste d'objets
    Exemple: {{ recettes|average_attribute:"taux_deperdition" }}
    """
    try:
        values = [
            getattr(item, attribute, 0) 
            for item in queryset 
            if getattr(item, attribute, None) is not None
        ]
        return sum(values) / len(values) if values else 0
    except (TypeError, AttributeError, ZeroDivisionError):
        return 0


# ===================================================================
# FILTRES DE COMPARAISON
# ===================================================================

@register.filter(name='gt')
def greater_than(value, arg):
    """
    Vérifie si value > arg
    Exemple: {% if taux|gt:-10 %}Bon{% endif %}
    """
    try:
        return float(value) > float(arg)
    except (ValueError, TypeError):
        return False


@register.filter(name='gte')
def greater_than_equal(value, arg):
    """
    Vérifie si value >= arg
    """
    try:
        return float(value) >= float(arg)
    except (ValueError, TypeError):
        return False


@register.filter(name='lt')
def less_than(value, arg):
    """
    Vérifie si value < arg
    """
    try:
        return float(value) < float(arg)
    except (ValueError, TypeError):
        return False


@register.filter(name='lte')
def less_than_equal(value, arg):
    """
    Vérifie si value <= arg
    """
    try:
        return float(value) <= float(arg)
    except (ValueError, TypeError):
        return False


# ===================================================================
# FILTRES MÉTIER SUPPER - STYLES ET CLASSES CSS
# ===================================================================

@register.filter(name='couleur_taux')
def couleur_taux(taux):
    """
    Retourne la classe CSS Bootstrap selon le taux de déperdition
    Vert: > -10%, Orange: -10% à -30%, Rouge: < -30%
    """
    try:
        if taux is None:
            return 'secondary'
        
        taux = float(taux)
        
        if taux > -10:
            return 'success'  # Vert
        elif taux >= -30:
            return 'warning'  # Orange
        else:
            return 'danger'   # Rouge
    except (ValueError, TypeError):
        return 'secondary'

@register.filter(name='couleur_note')
def couleur_note(note):
    """
    Retourne la classe CSS selon la note /20
    Usage: {{ note|couleur_note }}
    """
    try:
        note = float(note)
        if note >= 15:
            return 'note-excellente'
        elif note >= 12:
            return 'note-bonne'
        elif note >= 10:
            return 'note-moyenne'
        else:
            return 'note-faible'
    except (ValueError, TypeError):
        return 'text-muted'

@register.filter(name='badge_statut')
def badge_statut(statut):
    """
    Retourne la classe CSS Bootstrap pour les badges de statut
    Exemple: {{ jour.statut|badge_statut }} -> 'success'
    """
    badges = {
        'ouvert': 'success',
        'ferme': 'danger',
        'impertinent': 'warning',
        'actif': 'success',
        'inactif': 'secondary',
        'valide': 'success',
        'en_attente': 'warning',
        'verrouille': 'info',
    }
    
    statut_lower = str(statut).lower() if statut else ''
    return badges.get(statut_lower, 'secondary')


@register.filter(name='icon_habilitation')
def icon_habilitation(habilitation):
    """
    Retourne l'icône Font Awesome selon l'habilitation
    Exemple: {{ user.habilitation|icon_habilitation }} -> 'fa-user-shield'
    """
    icons = {
        'admin_principal': 'fa-user-shield',
        'chef_peage': 'fa-user-tie',
        'chef_pesage': 'fa-user-tie',
        'focal_regional': 'fa-map-marked-alt',
        'agent_inventaire': 'fa-clipboard-list',
        'caissier': 'fa-cash-register',
        'coord_psrr': 'fa-project-diagram',
        'serv_info': 'fa-laptop-code',
        'serv_emission': 'fa-file-invoice-dollar',
        'chef_service': 'fa-user-cog',
        'regisseur': 'fa-coins',
        'comptable_mat': 'fa-archive',
        'chef_ordre': 'fa-tasks',
        'chef_controle': 'fa-check-double',
        'imprimerie': 'fa-print',
    }
    
    return icons.get(habilitation, 'fa-user')


@register.filter(name='icon_type_poste')
def icon_type_poste(type_poste):
    """
    Retourne l'icône Font Awesome selon le type de poste
    Exemple: {{ poste.type|icon_type_poste }} -> 'fa-road'
    """
    icons = {
        'peage': 'fa-road',
        'pesage': 'fa-weight',
    }
    
    return icons.get(type_poste, 'fa-map-marker-alt')


# ===================================================================
# FILTRES DE TEXTE
# ===================================================================

@register.filter(name='truncate_words')
def truncate_words(value, length=3):
    """
    Tronque un texte à un nombre de mots spécifié
    Exemple: "Péage de Yaoundé Nord" avec length=3 -> "Péage de Yaoundé..."
    """
    try:
        if not value:
            return ''
        
        words = str(value).split()
        
        if len(words) <= length:
            return value
        
        return ' '.join(words[:int(length)]) + '...'
    except:
        return value


# ===================================================================
# TEMPLATE TAGS (fonctions appelables dans les templates)
# ===================================================================

@register.simple_tag
def get_setting(name, default=''):
    """
    Récupère une valeur de configuration Django settings
    Exemple: {% get_setting 'DEBUG' %}
    """
    from django.conf import settings
    return getattr(settings, name, default)


@register.simple_tag
def query_transform(request, **kwargs):
    """
    Transforme les paramètres de requête pour la pagination
    Exemple: <a href="?{% query_transform page=2 %}">Page 2</a>
    """
    updated = request.GET.copy()
    for key, value in kwargs.items():
        if value is not None:
            updated[key] = value
        else:
            updated.pop(key, None)
    
    return updated.urlencode()


@register.inclusion_tag('partials/badge_taux.html', takes_context=False)
def badge_taux_deperdition(taux):
    """
    Affiche un badge coloré selon le taux de déperdition
    Usage: {% badge_taux_deperdition recette.taux_deperdition %}
    
    Note: Nécessite le template partials/badge_taux.html
    """
    if taux is None:
        classe = 'secondary'
        texte = 'N/A'
    else:
        try:
            taux_float = float(taux)
            if taux_float > -10:
                classe = 'success'
                texte = f"{taux_float:.2f}%"
            elif taux_float >= -30:
                classe = 'warning'
                texte = f"{taux_float:.2f}%"
            else:
                classe = 'danger'
                texte = f"{taux_float:.2f}%"
        except (ValueError, TypeError):
            classe = 'secondary'
            texte = 'N/A'
    
    return {
        'classe': classe,
        'texte': texte,
        'taux': taux
    }


@register.simple_tag
def calculate_percentage(value, total):
    """
    Calcule le pourcentage de value par rapport à total
    Exemple: {% calculate_percentage 25 100 %} -> 25.00
    """
    try:
        value = float(value)
        total = float(total)
        
        if total == 0:
            return 0
        
        return (value / total) * 100
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


@register.simple_tag
def get_month_name(month_number):
    """
    Retourne le nom du mois en français
    Exemple: {% get_month_name 1 %} -> Janvier
    """
    months = {
        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
        5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
        9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
    }
    
    try:
        return months.get(int(month_number), '')
    except (ValueError, TypeError):
        return ''


# ===================================================================
# FILTRES SPÉCIAUX POUR DEBUG
# ===================================================================

@register.filter(name='type')
def get_type(value):
    """
    Retourne le type d'une variable (utile pour le debug)
    Exemple: {{ my_var|type }}
    """
    return type(value).__name__


@register.filter(name='dir')
def get_dir(value):
    """
    Retourne les attributs d'un objet (utile pour le debug)
    Exemple: {{ my_object|dir }}
    """
    return dir(value)


@register.filter(name='pprint')
def pretty_print(value):
    """
    Affichage formaté pour le debug
    """
    import pprint
    return pprint.pformat(value)

@register.filter
def range_filter(start, end=None):
    """
    Retourne un range pour utiliser dans les templates
    Usage: 
    - {{ 5|range_filter }} -> range(5) = [0,1,2,3,4]
    - {{ start|range_filter:end }} -> range(start, end)
    """
    try:
        if end is None:
            # Si un seul argument, créer range(start)
            return range(int(start))
        else:
            # Si deux arguments, créer range(start, end)
            return range(int(start), int(end))
    except (ValueError, TypeError):
        return []
    
@register.filter
def subtract(value, arg):
    """
    Soustraction de deux valeurs
    """
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def add_years(value, arg):
    """
    Ajoute des années à une valeur
    """
    try:
        return int(value) + int(arg)
    except (ValueError, TypeError):
        return value

@register.simple_tag
def year_range(start_year, end_year):
    """
    Génère une liste d'années entre start et end
    """
    try:
        return list(range(int(start_year), int(end_year) + 1))
    except (ValueError, TypeError):
        return []

@register.filter(name='div')
@register.filter(name='divide')
@register.filter(name='dividedby')
def safe_divide(value, arg):
    """
    Divise value par arg de manière sécurisée
    Retourne 0 si division par zéro ou erreur
    
    Usage: {{ 100|div:50 }} -> 2.0
           {{ ecart|div:total_declare|mul:100 }} -> pourcentage
    """
    try:
        # Convertir en float
        numerator = float(value) if value is not None else 0
        denominator = float(arg) if arg is not None else 0
        
        # Éviter division par zéro
        if denominator == 0:
            return 0
        
        return numerator / denominator
    except (ValueError, TypeError, ZeroDivisionError, InvalidOperation):
        return 0


@register.filter(name='mul')
@register.filter(name='multiply')
@register.filter(name='times')
def safe_multiply(value, arg):
    """
    Multiplie value par arg de manière sécurisée
    
    Usage: {{ 0.15|mul:100 }} -> 15.0
    """
    try:
        val1 = float(value) if value is not None else 0
        val2 = float(arg) if arg is not None else 0
        return val1 * val2
    except (ValueError, TypeError, InvalidOperation):
        return 0


@register.filter(name='sub')
@register.filter(name='subtract')
def safe_subtract(value, arg):
    """
    Soustrait arg de value de manière sécurisée
    
    Usage: {{ montant1|sub:montant2 }}
    """
    try:
        val1 = float(value) if value is not None else 0
        val2 = float(arg) if arg is not None else 0
        return val1 - val2
    except (ValueError, TypeError, InvalidOperation):
        return 0


# ===================================================================
# CORRECTION 2 : Filtre pour calcul de pourcentage direct
# ===================================================================

@register.filter(name='percentage_of')
def percentage_of(value, total):
    """
    Calcule le pourcentage de value par rapport à total
    Usage directe : {{ ecart|percentage_of:total_declare }}
    
    Alternative simplifiée à |div:total|mul:100
    """
    try:
        if total is None or float(total) == 0:
            return 0
        
        val = float(value) if value is not None else 0
        tot = float(total)
        
        return (val / tot) * 100
    except (ValueError, TypeError, ZeroDivisionError, InvalidOperation):
        return 0


# ===================================================================
# CORRECTION 3 : Filtre abs (valeur absolue) - sécurisé
# ===================================================================

@register.filter(name='abs')
@register.filter(name='absolute')
def safe_absolute(value):
    """
    Retourne la valeur absolue de manière sécurisée
    Usage: {{ -15.5|abs }} -> 15.5
    """
    try:
        if value is None:
            return 0
        return abs(float(value))
    except (ValueError, TypeError, InvalidOperation):
        return 0


# ===================================================================
# CORRECTION 4 : Filtre pour détecter si une valeur existe et n'est pas None
# ===================================================================

@register.filter(name='is_not_none')
def is_not_none(value):
    """
    Vérifie si une valeur n'est pas None
    Usage: {% if image_quittance|is_not_none %}...{% endif %}
    """
    return value is not None


@register.filter(name='has_value')
def has_value(value):
    """
    Vérifie si une valeur existe et n'est pas vide
    Usage: {% if quittancement.image_quittance|has_value %}...{% endif %}
    """
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == '':
        return False
    return True

@register.filter(name='type_mouvement_badge_class')
def type_mouvement_badge_class(type_mouvement):
    """
    Retourne la classe CSS Bootstrap pour le badge selon le type de mouvement
    
    Usage dans le template :
    {{ h.type_mouvement|type_mouvement_badge_class }}
    """
    if not type_mouvement:
        return 'secondary'
    
    type_lower = str(type_mouvement).lower()
    
    if type_lower == 'credit':
        return 'success'
    elif type_lower == 'debit':
        return 'danger'
    else:
        return 'secondary'


@register.filter(name='is_credit')
def is_credit(type_mouvement):
    """
    Vérifie si le type de mouvement est un crédit
    
    Usage dans le template :
    {% if h.type_mouvement|is_credit %}...{% endif %}
    """
    if not type_mouvement:
        return False
    return str(type_mouvement).lower() == 'credit'


@register.filter(name='is_debit')
def is_debit(type_mouvement):
    """
    Vérifie si le type de mouvement est un débit
    
    Usage dans le template :
    {% if h.type_mouvement|is_debit %}...{% endif %}
    """
    if not type_mouvement:
        return False
    return str(type_mouvement).lower() == 'debit'


@register.filter(name='mouvement_sign')
def mouvement_sign(type_mouvement):
    """
    Retourne le signe + ou - selon le type de mouvement
    
    Usage dans le template :
    {{ h.type_mouvement|mouvement_sign }}
    """
    if not type_mouvement:
        return ''
    
    type_lower = str(type_mouvement).lower()
    return '+' if type_lower == 'credit' else '-'


@register.filter(name='text_color_by_mouvement')
def text_color_by_mouvement(type_mouvement):
    """
    Retourne la classe de couleur de texte selon le type de mouvement
    
    Usage dans le template :
    <span class="text-{{ h.type_mouvement|text_color_by_mouvement }}">...</span>
    """
    if not type_mouvement:
        return 'secondary'
    
    type_lower = str(type_mouvement).lower()
    return 'success' if type_lower == 'credit' else 'danger'


# ===================================================================
# FILTRES UTILITAIRES SUPPLÉMENTAIRES
# ===================================================================

@register.filter(name='default_if_none_or_empty')
def default_if_none_or_empty(value, default='N/A'):
    """
    Retourne une valeur par défaut si la valeur est None ou vide
    
    Usage dans le template :
    {{ h.nombre_tickets|default_if_none_or_empty:'Aucun' }}
    """
    if value is None or value == '':
        return default
    return value
