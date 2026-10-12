from django.conf import settings
from django.db import models
from django.db.models import Q, F

class VehicleType(models.Model):
    name = models.CharField('Bezeichnung', max_length=100, unique=True)
    description = models.TextField('Beschreibung', blank=True, max_length=1000)

    class Meta:
        ordering = ['name']
        verbose_name = 'Fahrzeugtyp'
        verbose_name_plural = 'Fahrzeugtypen'

    def __str__(self):
        return self.name

class Vehicle(models.Model):
    plate = models.CharField('Kennzeichen', max_length=30, unique=True)
    name = models.CharField('Fahrzeug / Modell', max_length=100)
    space = models.CharField('Parkplatz', max_length=40, blank=True)
    vehicle_type = models.ForeignKey(VehicleType, verbose_name='Fahrzeugtyp', on_delete=models.PROTECT, null=True, blank=True, related_name='vehicles')
    mileage = models.PositiveIntegerField('Kilometerstand', default=0)
    notes = models.TextField('Bemerkungen', blank=True, max_length=3000)
    active = models.BooleanField('Aktiv', default=True)
    version = models.PositiveIntegerField(default=1)
    class Meta:
        ordering = ['plate']
    def __str__(self):
        return f'{self.plate} · {self.name}'

class Reservation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Reserviert'
        CANCELLED = 'cancelled', 'Storniert'
        USED = 'used', 'Übernommen'
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='reservations')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='reservations')
    start = models.DateTimeField('Von')
    end = models.DateTimeField('Bis')
    purpose = models.CharField('Zweck', max_length=300, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_reservations')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-start']
        constraints = [models.CheckConstraint(condition=Q(end__gt=F('start')), name='reservation_positive_interval')]

class Usage(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='usages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='usages')
    reservation = models.OneToOneField(Reservation, on_delete=models.PROTECT, null=True, blank=True)
    started_at = models.DateTimeField('Ausgabe', auto_now_add=True)
    expected_return = models.DateTimeField('Geplante Rückgabe')
    returned_at = models.DateTimeField('Rückgabe', null=True, blank=True)
    start_mileage = models.PositiveIntegerField('Kilometerstand bei Ausgabe')
    end_mileage = models.PositiveIntegerField('Kilometerstand bei Rückgabe', null=True, blank=True)
    purpose = models.CharField('Zweck', max_length=300, blank=True)
    return_notes = models.TextField('Rückgabe / Schäden', max_length=3000, blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='issued_usages')
    returned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='returned_usages', null=True, blank=True)
    class Meta:
        ordering = ['-started_at']
        constraints = [models.UniqueConstraint(fields=['vehicle'], condition=Q(returned_at__isnull=True), name='one_open_usage_per_vehicle'), models.CheckConstraint(condition=Q(end_mileage__isnull=True) | Q(end_mileage__gte=F('start_mileage')), name='non_decreasing_mileage')]

class Audit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT)
    action = models.CharField(max_length=60)
    detail = models.TextField()
    at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-at']
