import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from fleet.models import Vehicle, VehicleType

class Command(BaseCommand):
    help = 'Legt den initialen Administrator und optional Testfahrzeuge an; verändert vorhandene Benutzer nicht.'
    @transaction.atomic
    def handle(self, *args, **options):
        username = os.environ.get('ADMIN_USERNAME', 'admin')
        password = os.environ.get('ADMIN_PASSWORD')
        User = get_user_model()
        if not User.objects.filter(username=username).exists():
            if not password or len(password) < 12:
                raise CommandError('ADMIN_PASSWORD muss beim ersten Start mindestens 12 Zeichen haben.')
            User.objects.create_superuser(username=username, password=password, email=os.environ.get('ADMIN_EMAIL', ''))
            self.stdout.write('Administrator angelegt.')
        if os.environ.get('SEED_DEMO', '0') == '1':
            for plate, name, space, mileage in [('ZH 123456', 'VW Golf · Weiss', 'A-01', 42350), ('ZH 234567', 'Skoda Octavia · Blau', 'A-02', 78100), ('ZH 345678', 'Mercedes Sprinter · Silber', 'B-01', 113240)]:
                if not Vehicle.objects.filter(plate=plate).exists():
                    vehicle_type, _ = VehicleType.objects.get_or_create(name='Transporter' if 'Sprinter' in name else 'Personenwagen')
                    Vehicle.objects.create(plate=plate, name=name, mileage=mileage, vehicle_type=vehicle_type)
        self.stdout.write(self.style.SUCCESS('Initialisierung abgeschlossen.'))
