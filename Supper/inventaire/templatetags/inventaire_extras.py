from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Récupère un élément d'un dictionnaire dans un template"""
    if dictionary:
        return dictionary.get(key)
    return None