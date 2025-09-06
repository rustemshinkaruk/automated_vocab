import pprint
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter(name='pprint')
def pprint_filter(value):
    """
    Pretty print complex objects in templates.
    
    Usage:
    {{ my_complex_object|pprint }}
    """
    formatted = pprint.pformat(value, indent=2, width=120)
    # Mark as safe to prevent HTML escaping
    return mark_safe(formatted) 


@register.filter(name='dict_get')
def dict_get(mapping, key):
    """Safe dictionary getter for templates: {{ mydict|dict_get:key }}.

    Returns None if mapping is not a dict-like or key not present.
    """
    try:
        return mapping.get(key)
    except Exception:
        return None