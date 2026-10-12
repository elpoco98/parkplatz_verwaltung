from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from .models import Vehicle, Reservation, Usage, Audit

def require_person(actor, person, require_active=True):
    if require_active and not person.is_active:
        raise ValidationError('Der Benutzer ist nicht aktiv.')
    if person.pk != actor.pk and not actor.is_staff:
        raise PermissionDenied('Diese Aktion ist nur für eigene Buchungen erlaubt.')

def audit(actor, vehicle, action, detail):
    Audit.objects.create(actor=actor, vehicle=vehicle, action=action, detail=detail)

def overlaps(vehicle, start, end, exclude=None):
    qs = Reservation.objects.filter(vehicle=vehicle, status=Reservation.Status.ACTIVE, start__lt=end, end__gt=start)
    if exclude:
        qs = qs.exclude(pk=exclude)
    return qs.exists()

def available_vehicles(start, end, vehicle_type=None):
    """Verfügbarkeit für das gesamte Intervall, nach denselben Regeln wie reserve()."""
    now = timezone.now()
    if start < now or end <= start:
        raise ValidationError('Bitte einen gültigen zukünftigen Zeitraum wählen.')
    reservations = Reservation.objects.filter(
        vehicle_id=OuterRef('pk'), status=Reservation.Status.ACTIVE,
        start__lt=end, end__gt=start,
    )
    usages = Usage.objects.filter(vehicle_id=OuterRef('pk'), returned_at__isnull=True).filter(
        Q(expected_return__gt=start) | Q(expected_return__lte=now)
    )
    vehicles = Vehicle.objects.filter(active=True).select_related('vehicle_type')
    if vehicle_type:
        vehicles = vehicles.filter(vehicle_type=vehicle_type)
    return vehicles.annotate(
        reservation_conflict=Exists(reservations), usage_conflict=Exists(usages),
    ).filter(reservation_conflict=False, usage_conflict=False)

@transaction.atomic
def reserve(actor, vehicle_id, person, start, end, purpose=''):
    require_person(actor, person)
    v = Vehicle.objects.select_for_update().get(pk=vehicle_id)
    now = timezone.now()
    if not v.active:
        raise ValidationError('Das Fahrzeug ist deaktiviert.')
    if start < now or end <= start:
        raise ValidationError('Die Reservierung muss in der Zukunft liegen und ein gültiges Ende haben.')
    if overlaps(v, start, end):
        raise ValidationError('Für diesen Zeitraum besteht bereits eine Reservierung.')
    opened = Usage.objects.filter(vehicle=v, returned_at__isnull=True).first()
    if opened and (opened.expected_return > start or opened.expected_return <= now):
        raise ValidationError('Das Fahrzeug ist in Betrieb oder seine Rückgabe ist überfällig.')
    r = Reservation.objects.create(vehicle=v, user=person, start=start, end=end, purpose=purpose, created_by=actor)
    audit(actor, v, 'Reservierung erstellt', f'#{r.pk}, {person.username}, {start.isoformat()} – {end.isoformat()}, {purpose}')
    return r

@transaction.atomic
def cancel(actor, reservation_id):
    original = Reservation.objects.get(pk=reservation_id)
    v = Vehicle.objects.select_for_update().get(pk=original.vehicle_id)
    r = Reservation.objects.get(pk=reservation_id)
    require_person(actor, r.user, require_active=False)
    if r.status != Reservation.Status.ACTIVE:
        raise ValidationError('Die Reservierung ist bereits abgeschlossen.')
    r.status = Reservation.Status.CANCELLED
    r.save(update_fields=['status'])
    audit(actor, v, 'Reservierung storniert', f'#{r.pk}, {r.user.username}')

@transaction.atomic
def checkout(actor, vehicle_id, person, expected_return, mileage, purpose='', reservation_id=None):
    require_person(actor, person)
    v = Vehicle.objects.select_for_update().get(pk=vehicle_id)
    now = timezone.now()
    if not v.active or Usage.objects.filter(vehicle=v, returned_at__isnull=True).exists():
        raise ValidationError('Das Fahrzeug ist deaktiviert oder bereits in Betrieb.')
    if expected_return <= now or mileage < v.mileage:
        raise ValidationError('Rückgabe muss in der Zukunft liegen; der Kilometerstand darf nicht sinken.')
    r = None
    if reservation_id:
        r = Reservation.objects.get(pk=reservation_id)
        if r.vehicle_id != v.pk or r.user_id != person.pk or r.status != Reservation.Status.ACTIVE:
            raise ValidationError('Diese Reservierung passt nicht zur Ausgabe.')
        if not r.start <= now < r.end:
            raise ValidationError('Die Ausgabe ist nur innerhalb des reservierten Zeitraums möglich.')
        if expected_return > r.end:
            raise ValidationError('Die Rückgabe darf das Ende der Reservierung nicht überschreiten.')
    if overlaps(v, now, expected_return, reservation_id):
        raise ValidationError('Die Nutzung überschneidet sich mit einer Reservierung. Eigene Reservierung bitte über „Übernehmen“ öffnen.')
    u = Usage.objects.create(vehicle=v, user=person, expected_return=expected_return, start_mileage=mileage, purpose=purpose, issued_by=actor, reservation=r)
    v.mileage = mileage
    v.version += 1
    v.save(update_fields=['mileage', 'version'])
    if r:
        r.status = Reservation.Status.USED
        r.save(update_fields=['status'])
    audit(actor, v, 'Fahrzeug ausgegeben', f'Nutzung #{u.pk}, {person.username}, {mileage} km, Rückgabe {expected_return.isoformat()}, {purpose}')
    return u

@transaction.atomic
def checkin(actor, usage_id, mileage, space=None, notes=''):
    original = Usage.objects.get(pk=usage_id)
    v = Vehicle.objects.select_for_update().get(pk=original.vehicle_id)
    u = Usage.objects.get(pk=usage_id)
    require_person(actor, u.user, require_active=False)
    if u.returned_at:
        raise ValidationError('Das Fahrzeug wurde bereits zurückgegeben.')
    if mileage < u.start_mileage or mileage < v.mileage:
        raise ValidationError('Der Kilometerstand darf nicht sinken.')
    u.returned_at = timezone.now()
    u.end_mileage = mileage
    u.return_notes = notes
    u.returned_by = actor
    u.save()
    v.mileage = mileage
    if space is not None:
        v.space = space
    v.version += 1
    v.save(update_fields=['mileage', 'space', 'version'])
    audit(actor, v, 'Fahrzeug zurückgegeben', f'Nutzung #{u.pk}, {mileage} km, {notes}')
    return u

@transaction.atomic
def save_vehicle(actor, data, vehicle_id=None):
    if not actor.is_staff:
        raise PermissionDenied
    payload = dict(data)
    version = payload.pop('version', None)
    if vehicle_id:
        v = Vehicle.objects.select_for_update().get(pk=vehicle_id)
        if version != v.version:
            raise ValidationError('Ein anderer Benutzer hat dieses Fahrzeug geändert. Bitte die Seite neu laden.')
        if payload['mileage'] < v.mileage:
            raise ValidationError('Der Kilometerstand darf nicht sinken.')
        if Usage.objects.filter(vehicle=v, returned_at__isnull=True).exists():
            raise ValidationError('Ein Fahrzeug in Betrieb kann erst nach der Rückgabe bearbeitet werden.')
        if not payload['active'] and Reservation.objects.filter(vehicle=v, status='active', end__gt=timezone.now()).exists():
            raise ValidationError('Bitte zuerst zukünftige Reservierungen stornieren.')
        before = {k: getattr(v, k) for k in payload}
        for key, value in payload.items():
            setattr(v, key, value)
        v.version += 1
        v.full_clean()
        v.save()
        audit(actor, v, 'Fahrzeug geändert', f'Vorher: {before}; Nachher: {payload}')
    else:
        v = Vehicle(**payload)
        v.full_clean()
        v.save()
        audit(actor, v, 'Fahrzeug angelegt', str(payload))
    return v
