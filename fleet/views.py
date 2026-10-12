import csv
from urllib.parse import urlencode
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import connection, IntegrityError
from django.db.models import Q, Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import VehicleType, Vehicle, Reservation, Usage, Audit
from .forms import CalendarForm, AvailabilityForm, VehicleForm, ReservationForm, CheckoutForm, ReturnForm
from . import services

@login_required
def availability(request):
    initial_start = timezone.localtime() + timedelta(hours=1)
    submitted = 'start' in request.GET or 'end' in request.GET
    form = AvailabilityForm(request.GET if submitted else None, initial={
        'start': initial_start, 'end': initial_start + timedelta(hours=2),
    })
    vehicles = None
    reservation_query = ''
    if submitted and form.is_valid():
        try:
            vehicles = services.available_vehicles(form.cleaned_data['start'], form.cleaned_data['end'], form.cleaned_data['vehicle_type']).prefetch_related(
                Prefetch('usages', queryset=Usage.objects.filter(returned_at__isnull=True), to_attr='open_usages')
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            reservation_query = urlencode({key: timezone.localtime(form.cleaned_data[key]).strftime('%Y-%m-%dT%H:%M') for key in ('start', 'end')})
    return render(request, 'fleet/availability.html', {
        'form': form, 'vehicles': vehicles, 'reservation_query': reservation_query,
        'searched': vehicles is not None,
    })

@login_required
def dashboard(request):
    now = timezone.now()
    vehicles = Vehicle.objects.select_related('vehicle_type').prefetch_related(Prefetch('usages', queryset=Usage.objects.filter(returned_at__isnull=True).select_related('user'), to_attr='open_usages'), Prefetch('reservations', queryset=Reservation.objects.filter(status='active', end__gt=now).select_related('user').order_by('start'), to_attr='upcoming'))
    q = request.GET.get('q', '').strip()
    rows, counts = [], {'parked': 0, 'in_use': 0, 'reserved': 0, 'inactive': 0}
    for v in vehicles:
        usage = v.open_usages[0] if v.open_usages else None
        current = next((r for r in v.upcoming if r.start <= now), None)
        status = 'inactive' if not v.active else 'in_use' if usage else 'reserved' if current else 'parked'
        counts[status] += 1
        if q and q.casefold() not in f'{v.plate} {v.name} {v.vehicle_type or ""}'.casefold():
            continue
        if request.GET.get('vehicle_type') and str(v.vehicle_type_id) != request.GET['vehicle_type']:
            continue
        if request.GET.get('status') and status != request.GET['status']:
            continue
        rows.append({'vehicle': v, 'usage': usage, 'reservation': current, 'next': v.upcoming[0] if v.upcoming else None, 'status': status, 'overdue': bool(usage and usage.expected_return < now)})
    counts['on_site'] = counts['parked'] + counts['reserved'] + counts['inactive']
    return render(request, 'fleet/dashboard.html', {'rows': rows, 'counts': counts, 'q': q, 'now': now, 'vehicle_types': VehicleType.objects.all()})

@login_required
def vehicle_edit(request, pk=None):
    if not request.user.is_staff:
        raise PermissionDenied
    vehicle = get_object_or_404(Vehicle, pk=pk) if pk else None
    form = VehicleForm(request.POST or None, instance=vehicle, initial={'version': vehicle.version if vehicle else None})
    if request.method == 'POST' and form.is_valid():
        try:
            services.save_vehicle(request.user, form.cleaned_data, pk)
        except ValidationError as e:
            form.add_error(None, e)
        except IntegrityError:
            form.add_error(None, 'Dieses Kennzeichen wurde bereits von einem anderen Benutzer angelegt.')
        else:
            messages.success(request, 'Fahrzeug gespeichert.')
            return redirect('dashboard')
    return render(request, 'fleet/form.html', {'form': form, 'title': 'Fahrzeug bearbeiten' if pk else 'Fahrzeug anlegen', 'back': '/'})

@login_required
def reservation_create(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    now = timezone.localtime() + timedelta(hours=1)
    initial = {'start': now, 'end': now + timedelta(hours=2)}
    search = AvailabilityForm(request.GET)
    if search.is_valid():
        initial.update({key: search.cleaned_data[key] for key in ('start', 'end')})
    form = ReservationForm(request.POST or None, actor=request.user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            services.reserve(request.user, vehicle.pk, form.cleaned_data['user'], form.cleaned_data['start'], form.cleaned_data['end'], form.cleaned_data['purpose'])
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, 'Reservierung angelegt.')
            return redirect('reservations')
    return render(request, 'fleet/form.html', {'form': form, 'title': f'{vehicle.plate} reservieren', 'subtitle': vehicle.name, 'back': '/'})

@login_required
def checkout(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    rid = request.GET.get('reservation')
    reservation = get_object_or_404(Reservation, pk=rid, vehicle=vehicle) if rid else None
    if reservation:
        services.require_person(request.user, reservation.user)
    form = CheckoutForm(request.POST or None, actor=request.user, initial={'user': reservation.user_id if reservation else request.user.pk, 'expected_return': reservation.end if reservation else timezone.localtime() + timedelta(hours=2), 'mileage': vehicle.mileage, 'purpose': reservation.purpose if reservation else ''})
    if request.method == 'POST' and form.is_valid():
        try:
            services.checkout(request.user, vehicle.pk, form.cleaned_data['user'], form.cleaned_data['expected_return'], form.cleaned_data['mileage'], form.cleaned_data['purpose'], reservation.pk if reservation else None)
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, 'Fahrzeug ausgegeben.')
            return redirect('dashboard')
    return render(request, 'fleet/form.html', {'form': form, 'title': f'{vehicle.plate} ausgeben', 'subtitle': 'Reservierung übernehmen' if reservation else vehicle.name, 'back': '/'})

@login_required
def checkin(request, pk):
    usage = get_object_or_404(Usage.objects.select_related('vehicle', 'user'), pk=pk)
    services.require_person(request.user, usage.user, require_active=False)
    form = ReturnForm(request.POST or None, initial={'mileage': usage.vehicle.mileage})
    if request.method == 'POST' and form.is_valid():
        try:
            services.checkin(request.user, usage.pk, form.cleaned_data['mileage'], notes=form.cleaned_data['notes'])
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, 'Rückgabe erfasst. Das Fahrzeug ist wieder verfügbar.')
            return redirect('dashboard')
    return render(request, 'fleet/form.html', {'form': form, 'title': f'{usage.vehicle.plate} zurückgeben', 'subtitle': f'Genutzt von {usage.user.username}', 'back': '/'})

@login_required
def reservations(request):
    qs = Reservation.objects.select_related('vehicle', 'user', 'created_by')
    if request.GET.get('all') != '1':
        qs = qs.filter(status='active', end__gt=timezone.now()).order_by('start')
    if request.GET.get('mine') == '1':
        qs = qs.filter(user=request.user)
    page = Paginator(qs, 30).get_page(request.GET.get('page'))
    return render(request, 'fleet/reservations.html', {'page': page, 'now': timezone.now()})

@login_required
@require_POST
def reservation_cancel(request, pk):
    get_object_or_404(Reservation, pk=pk)
    try:
        services.cancel(request.user, pk)
    except ValidationError as e:
        messages.error(request, ' '.join(e.messages))
    else:
        messages.success(request, 'Reservierung storniert.')
    return redirect('reservations')

def history_query(request):
    qs = Usage.objects.select_related('vehicle', 'user', 'issued_by', 'returned_by')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(vehicle__plate__icontains=q) | Q(user__username__icontains=q) | Q(purpose__icontains=q))
    if request.GET.get('vehicle'):
        qs = qs.filter(vehicle_id=request.GET['vehicle']) if request.GET['vehicle'].isdigit() else qs.none()
    return qs

@login_required
def history(request):
    return render(request, 'fleet/history.html', {'page': Paginator(history_query(request), 30).get_page(request.GET.get('page')), 'q': request.GET.get('q', '')})

def csv_safe(value):
    value = str(value if value is not None else '')
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value

@login_required
def export_history(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="nutzungshistorie.csv"'
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Kennzeichen', 'Benutzer', 'Ausgabe', 'Geplante Rückgabe', 'Rückgabe', 'KM Start', 'KM Ende', 'Zweck', 'Rückgabehinweis', 'Ausgegeben von', 'Zurückgenommen von'])
    def dt(value):
        return timezone.localtime(value).strftime('%d.%m.%Y %H:%M') if value else ''
    for u in history_query(request).iterator():
        writer.writerow([csv_safe(x) for x in [u.vehicle.plate, u.user.username, dt(u.started_at), dt(u.expected_return), dt(u.returned_at), u.start_mileage, u.end_mileage, u.purpose, u.return_notes, u.issued_by.username, u.returned_by.username if u.returned_by else '']])
    return response

@login_required
def audit_log(request):
    if not request.user.is_staff:
        raise PermissionDenied
    return render(request, 'fleet/audit.html', {'page': Paginator(Audit.objects.select_related('actor', 'vehicle'), 40).get_page(request.GET.get('page'))})

def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:
        return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})

@login_required
def booking_calendar(request):
    from .calendar import build_calendar
    current = timezone.localdate().replace(day=1)
    form = CalendarForm(request.GET if request.GET else None, initial={'month': current})
    result = None
    query = {}
    if not request.GET:
        result = build_calendar(current)
    elif form.is_valid():
        result = build_calendar(form.cleaned_data['month'], form.cleaned_data['vehicle'], form.cleaned_data['vehicle_type'])
        for key in ('vehicle', 'vehicle_type'):
            value = form.cleaned_data[key]
            if value:
                query[key] = value.pk
    previous_url = following_url = ''
    if result:
        if result['previous']:
            previous_url = '?' + urlencode({**query, 'month': result['previous'].strftime('%Y-%m')})
        if result['following']:
            following_url = '?' + urlencode({**query, 'month': result['following'].strftime('%Y-%m')})
    return render(request, 'fleet/calendar.html', {'form': form, 'calendar': result, 'previous_url': previous_url, 'following_url': following_url})


def qr_vehicle(request):
    value = request.GET.get('vehicle')
    if value is None:
        return None
    if not value.isdecimal():
        from django.http import Http404
        raise Http404
    return get_object_or_404(Vehicle, pk=value)

@login_required
def reservation_qr(request):
    from urllib.parse import urlsplit
    from .qr import reservation_target
    vehicle = qr_vehicle(request)
    target = ''
    error = ''
    try:
        target = reservation_target(request, vehicle)
    except ValidationError as e:
        error = ' '.join(e.messages)
    local_only = bool(target and urlsplit(target).hostname in ('localhost', '127.0.0.1', '::1'))
    return render(request, 'fleet/qr.html', {'vehicle': vehicle, 'target': target, 'error': error, 'local_only': local_only})

@login_required
def reservation_qr_image(request):
    import qrcode
    from qrcode.image.svg import SvgPathImage
    from .qr import reservation_target
    vehicle = qr_vehicle(request)
    try:
        target = reservation_target(request, vehicle)
    except ValidationError as e:
        return HttpResponse(' '.join(e.messages), status=400, content_type='text/plain; charset=utf-8')
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4, image_factory=SvgPathImage)
    qr.add_data(target)
    qr.make(fit=True)
    response = HttpResponse(qr.make_image().to_string(), content_type='image/svg+xml')
    response['Cache-Control'] = 'private, no-store'
    if request.GET.get('download') == '1':
        response['Content-Disposition'] = f'attachment; filename="parkpilot-reservierung{f"-{vehicle.pk}" if vehicle else ""}.svg"'
    return response
