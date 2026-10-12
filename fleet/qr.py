from urllib.parse import urlsplit
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.urls import reverse


def reservation_target(request, vehicle=None):
    path = reverse('reservation_create', args=[vehicle.pk]) if vehicle else reverse('availability')
    base = settings.PUBLIC_BASE_URL
    if not base:
        return request.build_absolute_uri(path)
    URLValidator(schemes=['http', 'https'])(base)
    parts = urlsplit(base)
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/'):
        raise ValidationError('PUBLIC_BASE_URL muss nur Protokoll, Host und optional Port enthalten, z. B. http://192.168.1.50:8080.')
    return base.rstrip('/') + path
