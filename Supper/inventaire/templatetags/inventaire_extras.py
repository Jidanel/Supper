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

from django import template

register = template.Library()

@register.filter
def sum_attribute(queryset, attribute):
    """Somme un attribut d'une liste d'objets"""
    return sum(getattr(item, attribute, 0) for item in queryset)

@register.filter
def average_attribute(queryset, attribute):
    """Moyenne d'un attribut d'une liste d'objets"""
    values = [getattr(item, attribute, 0) for item in queryset if getattr(item, attribute, None) is not None]
    return sum(values) / len(values) if values else 0

@register.filter
def div(value, divisor):
    """Division sécurisée"""
    try:
        return float(value) / float(divisor)
    except (ValueError, ZeroDivisionError):
        return 0

@register.filter
def sub(value, arg):
    """Soustraction"""
    return float(value) - float(arg)

@register.filter
def mul(value, arg):
    """Multiplication"""
    return float(value) * float(arg)

@register.filter
def get_item(lst, index):
    """Récupère un élément de liste par index"""
    try:
        return lst[index]
    except (IndexError, TypeError):
        return None