from django import template

register = template.Library()

@register.filter
def mul(value, arg):
    """Multiplie la valeur par l'argument."""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0