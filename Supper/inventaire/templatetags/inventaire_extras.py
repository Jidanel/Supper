from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Récupère un élément d'un dictionnaire dans un template"""
    if dictionary:
        return dictionary.get(key)
    return None

@register.filter
def mul(value, arg):
    """Multiplie la valeur par l'argument."""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0

from django import template
from decimal import Decimal, InvalidOperation


@register.filter
def safe_decimal(value, default=0):
    """Convertit une valeur en nombre sûr pour l'affichage"""
    if value is None:
        return default
    
    try:
        if isinstance(value, Decimal):
            return float(str(value))
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return default

@register.filter
def safe_int(value, default=0):
    """Convertit une valeur en entier sûr pour l'affichage"""
    if value is None:
        return default
    
    try:
        if isinstance(value, Decimal):
            return int(float(str(value)))
        return int(value)
    except (TypeError, ValueError, InvalidOperation):
        return default