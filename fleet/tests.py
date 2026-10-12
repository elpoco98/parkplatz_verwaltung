from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, close_old_connections
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import Vehicle, Reservation, Usage, Audit
from . import services

class FleetTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user('admin', password='TestingPassword123!', is_staff=True, is_superuser=True)
        self.alice = User.objects.create_user('alice', password='TestingPassword123!')
        self.bob = User.objects.create_user('bob', password='TestingPassword123!')
        self.v = Vehicle.objects.create(plate='ZH 123', name='Golf', space='A-01', mileage=100)
        self.start = timezone.now() + timedelta(hours=1)
        self.end = self.start + timedelta(hours=2)
    def reserve(self, **kwargs):
        args = dict(actor=self.alice, vehicle_id=self.v.pk, person=self.alice, start=self.start, end=self.end)
        args.update(kwargs)
        return services.reserve(**args)
    def checkout(self, **kwargs):
        args = dict(actor=self.alice, vehicle_id=self.v.pk, person=self.alice, expected_return=timezone.now()+timedelta(minutes=30), mileage=100)
        args.update(kwargs)
        return services.checkout(**args)
    def test_reservation_overlap_rejected_and_adjacent_allowed(self):
        self.reserve()
        with self.assertRaises(ValidationError):
            self.reserve(start=self.start+timedelta(minutes=30))
        self.reserve(start=self.end, end=self.end+timedelta(hours=1))
        self.assertEqual(Reservation.objects.count(), 2)
    def test_invalid_intervals(self):
        for start, end in [(self.start, self.start), (self.end, self.start), (timezone.now()-timedelta(hours=1), self.end)]:
            with self.assertRaises(ValidationError):
                self.reserve(start=start, end=end)
    def test_cancel_releases_slot(self):
        r = self.reserve()
        services.cancel(self.alice, r.pk)
        self.reserve()
        self.assertEqual(Audit.objects.count(), 3)
    def test_other_person_is_denied(self):
        with self.assertRaises(PermissionDenied):
            self.reserve(person=self.bob)
        r = self.reserve()
        with self.assertRaises(PermissionDenied):
            services.cancel(self.bob, r.pk)
        self.assertEqual(Audit.objects.count(), 1)
    def test_staff_can_book_for_another_person(self):
        r = self.reserve(actor=self.admin, person=self.bob)
        self.assertEqual(r.user, self.bob)
    def test_double_checkout_rejected(self):
        self.checkout()
        with self.assertRaises(ValidationError):
            self.checkout()
        self.assertEqual(Usage.objects.count(), 1)
    def test_checkout_conflicts_with_reservation(self):
        self.reserve()
        with self.assertRaises(ValidationError):
            self.checkout(expected_return=self.end)
        self.assertEqual(Usage.objects.count(), 0)
    def test_reservation_consumed_only_once(self):
        r = Reservation.objects.create(vehicle=self.v, user=self.alice, created_by=self.alice, start=timezone.now()-timedelta(minutes=5), end=self.end)
        u = self.checkout(reservation_id=r.pk)
        r.refresh_from_db()
        self.assertEqual(r.status, 'used')
        self.assertEqual(u.reservation_id, r.pk)
        services.checkin(self.alice, u.pk, 110, 'A-02')
        with self.assertRaises(ValidationError):
            self.checkout(reservation_id=r.pk, mileage=110)
    def test_return_updates_vehicle_and_audit(self):
        u = self.checkout()
        services.checkin(self.alice, u.pk, 135, 'B-02', 'Kratzer links')
        self.v.refresh_from_db()
        u.refresh_from_db()
        self.assertEqual(self.v.mileage, 135)
        self.assertEqual(self.v.space, 'B-02')
        self.assertIsNotNone(u.returned_at)
        self.assertEqual(u.returned_by, self.alice)
        self.assertEqual(Audit.objects.count(), 2)
    def test_return_validation_does_not_mutate(self):
        u = self.checkout()
        with self.assertRaises(ValidationError):
            services.checkin(self.alice, u.pk, 99, 'B-02')
        u.refresh_from_db()
        self.assertIsNone(u.returned_at)
        self.assertEqual(Audit.objects.count(), 1)
    def test_double_return_and_other_person_return_denied(self):
        u = self.checkout()
        with self.assertRaises(PermissionDenied):
            services.checkin(self.bob, u.pk, 110, 'B-02')
        services.checkin(self.admin, u.pk, 110, 'B-02')
        with self.assertRaises(ValidationError):
            services.checkin(self.admin, u.pk, 110, 'B-02')
    def test_reservation_checks_open_and_overdue_usage(self):
        u = self.checkout(expected_return=self.start+timedelta(minutes=30))
        with self.assertRaises(ValidationError):
            self.reserve()
        self.reserve(start=self.end, end=self.end+timedelta(hours=1))
        Usage.objects.filter(pk=u.pk).update(expected_return=timezone.now()-timedelta(minutes=1))
        with self.assertRaises(ValidationError):
            self.reserve(start=self.end+timedelta(hours=2), end=self.end+timedelta(hours=3))
    def test_inactive_vehicle_denied(self):
        self.v.active = False
        self.v.save()
        with self.assertRaises(ValidationError):
            self.reserve()
        with self.assertRaises(ValidationError):
            self.checkout()
    def test_stale_vehicle_edit_denied(self):
        data = dict(plate=self.v.plate, name='Updated', mileage=100, space='A-02', notes='', active=True, version=1)
        services.save_vehicle(self.admin, data, self.v.pk)
        with self.assertRaises(ValidationError):
            services.save_vehicle(self.admin, data, self.v.pk)
        self.v.refresh_from_db()
        self.assertEqual(self.v.version, 2)
    def test_staff_edit_gates(self):
        data = dict(plate=self.v.plate, name='Updated', mileage=100, space='A-02', notes='', active=True, version=1)
        with self.assertRaises(PermissionDenied):
            services.save_vehicle(self.alice, data, self.v.pk)
        self.checkout()
        with self.assertRaises(ValidationError):
            services.save_vehicle(self.admin, data, self.v.pk)
    def test_cannot_deactivate_reserved_vehicle(self):
        self.reserve()
        with self.assertRaises(ValidationError):
            services.save_vehicle(self.admin, dict(plate=self.v.plate, name='Golf', mileage=100, space='A-01', notes='', active=False, version=1), self.v.pk)
    def test_login_required_and_no_get_mutations(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        self.client.force_login(self.alice)
        r = self.reserve()
        self.assertEqual(self.client.get(reverse('reservation_cancel', args=[r.pk])).status_code, 405)
        self.assertEqual(self.client.get('/vehicles/new/').status_code, 403)
        self.assertEqual(self.client.get('/audit/').status_code, 403)
    def test_csrf_protected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.alice)
        r = self.reserve()
        self.assertEqual(client.post(reverse('reservation_cancel', args=[r.pk])).status_code, 403)
    def test_all_pages_render(self):
        self.reserve()
        self.checkout()
        self.client.force_login(self.admin)
        for url in ['/', '/reservations/', '/reservations/?all=1', '/history/', '/history/export/', '/audit/', '/vehicles/new/', f'/vehicles/{self.v.pk}/edit/', f'/vehicles/{self.v.pk}/reserve/', f'/vehicles/{self.v.pk}/checkout/', '/usages/1/return/', '/password/', '/health/', '/admin/auth/user/']:
            with self.subTest(url=url):
                # Usage primary key is not guaranteed to start at 1 on PostgreSQL.
                if url == '/usages/1/return/':
                    url = reverse('checkin', args=[Usage.objects.first().pk])
                self.assertEqual(self.client.get(url).status_code, 200)
    def test_vehicle_creation_via_form(self):
        self.client.force_login(self.admin)
        response = self.client.post('/vehicles/new/', {'plate':'be 555', 'name':'Bus', 'space':'C-01', 'mileage':0, 'notes':'', 'active':'on'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Vehicle.objects.filter(plate='BE 555').exists())
    def test_export_escapes_spreadsheet_formulas(self):
        self.checkout(purpose='=1+1')
        self.client.force_login(self.alice)
        response = self.client.get('/history/export/')
        self.assertIn("'=1+1", response.content.decode())
    def test_health_and_login(self):
        self.assertEqual(self.client.get('/login/').status_code, 200)
        self.assertEqual(self.client.get('/health/').json(), {'status':'ok'})
    def test_pagination_retains_filters(self):
        for i in range(31):
            Reservation.objects.create(vehicle=self.v, user=self.alice, created_by=self.alice, start=self.start+timedelta(days=i), end=self.end+timedelta(days=i))
        self.client.force_login(self.alice)
        response = self.client.get('/reservations/?all=1&mine=1')
        self.assertContains(response, 'all=1&amp;mine=1&amp;page=2')

@skipUnless(connection.vendor == 'postgresql', 'Zeilensperren brauchen PostgreSQL; in Docker ausführen.')
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.person = get_user_model().objects.create_user('concurrent')
        self.v = Vehicle.objects.create(plate='TEST 1', name='Concurrency')
    def race(self, action):
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            person = get_user_model().objects.get(pk=self.person.pk)
            barrier.wait(timeout=10)
            try:
                action(person)
                return 'ok'
            except ValidationError:
                return 'conflict'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: worker(), range(2)))
        self.assertCountEqual(outcomes, ['ok', 'conflict'])
    def test_concurrent_reservations(self):
        start = timezone.now()+timedelta(hours=1)
        end = start+timedelta(hours=1)
        self.race(lambda person: services.reserve(person, self.v.pk, person, start, end))
        self.assertEqual(Reservation.objects.count(), 1)
    def test_concurrent_checkouts(self):
        end = timezone.now()+timedelta(hours=1)
        self.race(lambda person: services.checkout(person, self.v.pk, person, end, 0))
        self.assertEqual(Usage.objects.count(), 1)
    def test_concurrent_returns(self):
        u = services.checkout(self.person, self.v.pk, self.person, timezone.now()+timedelta(hours=1), 0)
        self.race(lambda person: services.checkin(person, u.pk, 10, 'A-01'))
        self.assertEqual(Audit.objects.filter(action='Fahrzeug zurückgegeben').count(), 1)

class BrowserFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('driver', password='TestingPassword123!')
        self.v = Vehicle.objects.create(plate='BE 999', name='Transporter', mileage=500, space='C-03')
        self.client.force_login(self.user)
    def local_input(self, value):
        return timezone.localtime(value).strftime('%Y-%m-%dT%H:%M')
    def test_issue_return_and_history_through_forms(self):
        response = self.client.post(reverse('checkout', args=[self.v.pk]), {'user':self.user.pk, 'expected_return':self.local_input(timezone.now()+timedelta(hours=1)), 'mileage':510, 'purpose':'Kundenbesuch'})
        self.assertRedirects(response, '/')
        u = Usage.objects.get()
        response = self.client.post(reverse('checkin', args=[u.pk]), {'mileage':540, 'space':'C-04', 'notes':'Alles gut'})
        self.assertRedirects(response, '/')
        self.assertContains(self.client.get('/history/'), 'Kundenbesuch')
        self.v.refresh_from_db()
        self.assertEqual(self.v.mileage, 540)
    def test_reserve_and_cancel_through_forms(self):
        response = self.client.post(reverse('reservation_create', args=[self.v.pk]), {'user':self.user.pk, 'start':self.local_input(timezone.now()+timedelta(hours=2)), 'end':self.local_input(timezone.now()+timedelta(hours=3)), 'purpose':'Termin'})
        self.assertRedirects(response, '/reservations/')
        r = Reservation.objects.get()
        self.assertRedirects(self.client.post(reverse('reservation_cancel', args=[r.pk])), '/reservations/')
        r.refresh_from_db()
        self.assertEqual(r.status, 'cancelled')
    def test_user_cannot_forge_another_driver(self):
        other = get_user_model().objects.create_user('other')
        response = self.client.post(reverse('checkout', args=[self.v.pk]), {'user':other.pk, 'expected_return':self.local_input(timezone.now()+timedelta(hours=1)), 'mileage':500})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Usage.objects.count(), 0)
    def test_admin_can_cancel_after_person_deactivated(self):
        r = services.reserve(self.user, self.v.pk, self.user, timezone.now()+timedelta(hours=1), timezone.now()+timedelta(hours=2))
        self.user.is_active = False
        self.user.save()
        admin = get_user_model().objects.create_user('staff', is_staff=True)
        services.cancel(admin, r.pk)
        r.refresh_from_db()
        self.assertEqual(r.status, 'cancelled')
    def test_staff_can_return_vehicle_for_deactivated_person(self):
        u = services.checkout(self.user, self.v.pk, self.user, timezone.now()+timedelta(hours=1), 500)
        self.user.is_active = False
        self.user.save()
        staff = get_user_model().objects.create_user('staff', is_staff=True)
        services.checkin(staff, u.pk, 520, 'C-03')
        u.refresh_from_db()
        self.assertIsNotNone(u.returned_at)

class AvailabilityTests(TestCase):
    def setUp(self):
        self.person = get_user_model().objects.create_user('searcher')
        self.client.force_login(self.person)
        self.start = (timezone.now()+timedelta(hours=3)).replace(second=0, microsecond=0)
        self.end = self.start+timedelta(hours=2)
        self.v = Vehicle.objects.create(plate='ZH FREE', name='Available', mileage=0)
    def params(self, **overrides):
        params = {key: timezone.localtime(value).strftime('%Y-%m-%dT%H:%M') for key, value in {'start':self.start,'end':self.end}.items()}
        params.update(overrides)
        return params
    def reservation(self, start, end, status='active'):
        return Reservation.objects.create(vehicle=self.v, user=self.person, created_by=self.person, start=start, end=end, status=status)
    def test_entire_interval_conflicts_are_excluded(self):
        for start, end in [(self.start-timedelta(hours=1), self.end+timedelta(hours=1)), (self.start+timedelta(minutes=20), self.end-timedelta(minutes=20)), (self.start-timedelta(hours=1), self.start+timedelta(minutes=1)), (self.end-timedelta(minutes=1), self.end+timedelta(hours=1))]:
            with self.subTest(start=start, end=end):
                r = self.reservation(start,end)
                self.assertFalse(services.available_vehicles(self.start,self.end).exists())
                r.delete()
    def test_adjacent_cancelled_and_consumed_reservations_do_not_block(self):
        self.reservation(self.start-timedelta(hours=1), self.start)
        self.reservation(self.end, self.end+timedelta(hours=1))
        self.reservation(self.start, self.end, status='cancelled')
        self.reservation(self.start, self.end, status='used')
        self.assertQuerySetEqual(services.available_vehicles(self.start,self.end), [self.v])
    def test_current_usage_before_window_and_overdue_return(self):
        u = services.checkout(self.person, self.v.pk, self.person, self.start, 0)
        self.assertTrue(services.available_vehicles(self.start,self.end).exists())
        Usage.objects.filter(pk=u.pk).update(expected_return=self.start+timedelta(minutes=1))
        self.assertFalse(services.available_vehicles(self.start,self.end).exists())
        Usage.objects.filter(pk=u.pk).update(expected_return=timezone.now()-timedelta(minutes=1))
        self.assertFalse(services.available_vehicles(self.start,self.end).exists())
        services.checkin(self.person,u.pk,0,'A-01')
        self.assertTrue(services.available_vehicles(self.start,self.end).exists())
    def test_inactive_vehicle_not_shown(self):
        self.v.active=False
        self.v.save()
        self.assertFalse(services.available_vehicles(self.start,self.end).exists())
    def test_empty_page_and_login_required(self):
        response=self.client.get('/availability/')
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.context['searched'])
        self.client.logout()
        self.assertEqual(self.client.get('/availability/').status_code,302)
    def test_invalid_or_incomplete_dates_show_errors_without_results(self):
        for params in [self.params(end=self.params()['start']), self.params(start='nonsense'), {'start':self.params()['start']}, self.params(start=timezone.localtime(timezone.now()-timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'))]:
            with self.subTest(params=params):
                response=self.client.get('/availability/',params)
                self.assertEqual(response.status_code,200)
                self.assertTrue(response.context['form'].errors)
                self.assertFalse(response.context['searched'])
    def test_results_and_reservation_prefill_and_booking(self):
        from urllib.parse import urlencode
        response=self.client.get('/availability/',self.params())
        self.assertContains(response,'ZH FREE')
        self.assertTrue(response.context['searched'])
        url=reverse('reservation_create',args=[self.v.pk])+'?'+urlencode(self.params())
        response=self.client.get(url)
        self.assertEqual(response.context['form'].initial['start'],self.start)
        self.assertEqual(response.context['form'].initial['end'],self.end)
        self.assertRedirects(self.client.post(url,{**self.params(),'user':self.person.pk,'purpose':'Suchergebnis'}),'/reservations/')
        r=Reservation.objects.get()
        self.assertEqual(r.start,self.start)
        self.assertEqual(r.end,self.end)
    def test_no_results_message(self):
        self.reservation(self.start,self.end)
        response=self.client.get('/availability/',self.params())
        self.assertContains(response,'kein Fahrzeug verfügbar')
        self.assertNotContains(response,'Für diesen Zeitraum reservieren')
    def test_booking_rechecks_availability_after_search(self):
        response=self.client.get('/availability/',self.params())
        self.assertContains(response,'ZH FREE')
        self.reservation(self.start,self.end)
        response=self.client.post(reverse('reservation_create',args=[self.v.pk]),{**self.params(),'user':self.person.pk})
        self.assertContains(response,'bereits eine Reservierung')
        self.assertEqual(Reservation.objects.count(),1)

class TypeCalendarQrTests(TestCase):
    def setUp(self):
        from .models import VehicleType
        self.admin = get_user_model().objects.create_user('featureadmin', is_staff=True, is_superuser=True)
        self.person = get_user_model().objects.create_user('featureuser')
        self.car_type = VehicleType.objects.create(name='Personenwagen')
        self.van_type = VehicleType.objects.create(name='Lieferwagen')
        self.car = Vehicle.objects.create(plate='ZH TYP1', name='Golf', vehicle_type=self.car_type, space='LEGACY-NUMMER', mileage=100)
        self.van = Vehicle.objects.create(plate='ZH TYP2', name='Van', vehicle_type=self.van_type)
        self.client.force_login(self.admin)
    def reservation(self, start, end, vehicle=None, status='active'):
        return Reservation.objects.create(vehicle=vehicle or self.car,user=self.person,created_by=self.admin,start=start,end=end,status=status)
    def aware(self, value):
        from datetime import datetime
        return timezone.make_aware(datetime.fromisoformat(value))
    def events_on(self, result, value):
        from datetime import date
        return next(day['events'] for week in result['weeks'] for day in week if day['date']==date.fromisoformat(value))
    def test_type_create_and_rename_in_admin(self):
        from .models import VehicleType
        response=self.client.post('/admin/fleet/vehicletype/add/',{'name':'Geländewagen','description':'4x4','_save':'Speichern'})
        self.assertEqual(response.status_code,302)
        kind=VehicleType.objects.get(name='Geländewagen')
        response=self.client.post(f'/admin/fleet/vehicletype/{kind.pk}/change/',{'name':'Offroad','description':'4x4','_save':'Speichern'})
        self.assertEqual(response.status_code,302)
        kind.refresh_from_db()
        self.assertEqual(kind.name,'Offroad')
    def test_referenced_type_cannot_be_deleted(self):
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError):
            self.car_type.delete()
    def test_vehicle_type_assignment_without_space_field(self):
        response=self.client.post(reverse('vehicle_edit',args=[self.car.pk]),{'plate':self.car.plate,'name':self.car.name,'mileage':100,'vehicle_type':self.van_type.pk,'notes':'','active':'on','version':1})
        self.assertEqual(response.status_code,302)
        self.car.refresh_from_db()
        self.assertEqual(self.car.vehicle_type,self.van_type)
        response=self.client.get(reverse('vehicle_edit',args=[self.car.pk]))
        self.assertNotContains(response,'name="space"')
        self.assertNotContains(self.client.get('/'),'LEGACY-NUMMER')
    def test_dashboard_and_availability_type_filters(self):
        response=self.client.get('/',{'vehicle_type':self.van_type.pk})
        self.assertContains(response,'ZH TYP2')
        self.assertNotContains(response,'ZH TYP1')
        start=timezone.localtime()+timedelta(hours=1)
        response=self.client.get('/availability/',{'start':start.strftime('%Y-%m-%dT%H:%M'),'end':(start+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),'vehicle_type':self.car_type.pk})
        self.assertContains(response,'ZH TYP1')
        self.assertNotContains(response,'ZH TYP2')
    def test_return_form_works_without_park_number(self):
        u=services.checkout(self.admin,self.car.pk,self.person,timezone.now()+timedelta(hours=1),100)
        response=self.client.get(reverse('checkin',args=[u.pk]))
        self.assertNotContains(response,'name="space"')
        self.assertRedirects(self.client.post(reverse('checkin',args=[u.pk]),{'mileage':120,'notes':'OK'}),'/')
        self.car.refresh_from_db()
        self.assertEqual(self.car.space,'LEGACY-NUMMER')
    def test_normal_user_cannot_manage_types(self):
        self.client.force_login(self.person)
        self.assertEqual(self.client.get('/admin/fleet/vehicletype/add/').status_code,302)
    def test_calendar_multiday_and_midnight_exclusive_end(self):
        from .calendar import build_calendar
        from datetime import date
        self.reservation(self.aware('2028-10-02T23:30'),self.aware('2028-10-04T00:00'))
        result=build_calendar(date(2028,10,1))
        self.assertEqual(len(self.events_on(result,'2028-10-02')),1)
        self.assertEqual(len(self.events_on(result,'2028-10-03')),1)
        self.assertEqual(len(self.events_on(result,'2028-10-04')),0)
    def test_calendar_omits_cancelled_and_filters_type_and_vehicle(self):
        self.reservation(self.aware('2028-10-02T10:00'),self.aware('2028-10-02T12:00'))
        self.reservation(self.aware('2028-10-02T10:00'),self.aware('2028-10-02T12:00'),self.van)
        self.reservation(self.aware('2028-10-02T13:00'),self.aware('2028-10-02T14:00'),self.van,status='cancelled')
        response=self.client.get('/calendar/',{'month':'2028-10','vehicle_type':self.van_type.pk,'vehicle':self.van.pk})
        events=self.events_on(response.context['calendar'],'2028-10-02')
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['vehicle'],self.van)
        self.assertIn(f'vehicle_type={self.van_type.pk}',response.context['following_url'])
        self.assertIn('month=2028-11',response.context['following_url'])
    def test_calendar_usage_instead_of_duplicate_consumed_reservation(self):
        from .calendar import build_calendar
        from datetime import date
        start=self.aware('2028-10-02T10:00')
        end=self.aware('2028-10-02T12:00')
        r=self.reservation(start,end,status='used')
        u=Usage.objects.create(vehicle=self.car,user=self.person,issued_by=self.admin,reservation=r,expected_return=end,returned_at=end,start_mileage=100,end_mileage=110)
        Usage.objects.filter(pk=u.pk).update(started_at=start)
        events=self.events_on(build_calendar(date(2028,10,1)),'2028-10-02')
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['kind'],'usage')
    def test_calendar_daylight_saving_time(self):
        from .calendar import build_calendar
        from datetime import date
        self.reservation(self.aware('2028-10-28T23:00'),self.aware('2028-10-30T00:00'))
        result=build_calendar(date(2028,10,1))
        self.assertEqual(len(self.events_on(result,'2028-10-28')),1)
        self.assertEqual(len(self.events_on(result,'2028-10-29')),1)
        self.assertEqual(len(self.events_on(result,'2028-10-30')),0)
    def test_calendar_invalid_filters_and_default_render(self):
        self.assertEqual(self.client.get('/calendar/').status_code,200)
        for params in [{'month':'bogus'},{'month':'2028-99'},{'month':'0001-01'},{'month':'2028-10','vehicle':'999999'}]:
            response=self.client.get('/calendar/',params)
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.context['form'].errors)
            self.assertIsNone(response.context['calendar'])
    def test_overdue_usage_calendar_explains_unknown_return(self):
        from .calendar import build_calendar
        u=Usage.objects.create(vehicle=self.car,user=self.person,issued_by=self.admin,expected_return=timezone.now()-timedelta(hours=1),start_mileage=100)
        Usage.objects.filter(pk=u.pk).update(started_at=timezone.now()-timedelta(hours=2))
        result=build_calendar(timezone.localdate().replace(day=1))
        events=self.events_on(result,timezone.localdate().isoformat())
        self.assertEqual(events[0]['kind'],'overdue')
        self.assertIsNone(events[0]['end'])
    def test_qr_configured_target_and_vehicle_link(self):
        from django.test import override_settings
        with override_settings(PUBLIC_BASE_URL='http://192.168.1.50:8080'):
            response=self.client.get('/qr/')
            self.assertEqual(response.context['target'],'http://192.168.1.50:8080/availability/')
            self.assertFalse(response.context['local_only'])
            response=self.client.get('/qr/',{'vehicle':self.car.pk})
            self.assertEqual(response.context['target'],f'http://192.168.1.50:8080/vehicles/{self.car.pk}/reserve/')
    def test_qr_svg_is_generated_and_downloadable(self):
        import xml.etree.ElementTree as ET
        from django.test import override_settings
        with override_settings(PUBLIC_BASE_URL='http://192.168.1.50:8080'):
            response=self.client.get('/qr/image.svg',{'vehicle':self.car.pk,'download':'1'})
            self.assertEqual(response.status_code,200)
            root=ET.fromstring(response.content)
            self.assertEqual(root.tag,'{http://www.w3.org/2000/svg}svg')
            self.assertTrue(root.findall('.//{http://www.w3.org/2000/svg}path'))
            self.assertIn('attachment',response['Content-Disposition'])
    def test_qr_localhost_guidance_and_invalid_config(self):
        from django.test import override_settings
        with override_settings(PUBLIC_BASE_URL=''):
            response=self.client.get('/qr/',HTTP_HOST='localhost')
            self.assertTrue(response.context['local_only'])
            self.assertContains(response,'PUBLIC_BASE_URL')
        for base in ['javascript:alert(1)','http://user:pass@example.com','http://example.com/wrong-path']:
            with override_settings(PUBLIC_BASE_URL=base):
                self.assertEqual(self.client.get('/qr/image.svg').status_code,400)
    def test_qr_invalid_vehicle(self):
        for value in ['bad','999999']:
            self.assertEqual(self.client.get('/qr/',{'vehicle':value}).status_code,404)
    def test_new_pages_require_authentication_and_login_preserves_target(self):
        self.client.logout()
        for path in ['/calendar/','/qr/','/qr/image.svg',f'/vehicles/{self.car.pk}/reserve/']:
            response=self.client.get(path)
            self.assertEqual(response.status_code,302)
            self.assertIn('/login/?next=',response.url)
    def test_existing_vehicle_can_remain_untyped(self):
        self.car.vehicle_type=None
        self.car.save()
        self.assertContains(self.client.get('/'),'Ohne Typ')
