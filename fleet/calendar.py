import calendar as month_calendar
from datetime import datetime, time, timedelta
from django.db.models import Q
from django.utils import timezone
from .models import Reservation, Usage

MONTHS = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

def month_days(month):
    return month_calendar.Calendar(firstweekday=0).monthdatescalendar(month.year, month.month)

def build_calendar(month, vehicle=None, vehicle_type=None):
    weeks = month_days(month)
    range_start = timezone.make_aware(datetime.combine(weeks[0][0], time.min))
    range_end = timezone.make_aware(datetime.combine(weeks[-1][-1] + timedelta(days=1), time.min))
    now = timezone.now()
    reservations = Reservation.objects.filter(status='active', start__lt=range_end, end__gt=range_start).select_related('vehicle__vehicle_type', 'user')
    usages = Usage.objects.filter(started_at__lt=range_end).filter(Q(returned_at__gt=range_start) | Q(returned_at__isnull=True)).select_related('vehicle__vehicle_type', 'user')
    if vehicle:
        reservations = reservations.filter(vehicle=vehicle)
        usages = usages.filter(vehicle=vehicle)
    if vehicle_type:
        reservations = reservations.filter(vehicle__vehicle_type=vehicle_type)
        usages = usages.filter(vehicle__vehicle_type=vehicle_type)
    events = []
    for r in reservations:
        events.append({'kind': 'reservation', 'label': 'Reserviert', 'vehicle': r.vehicle, 'user': r.user, 'start': r.start, 'end': r.end, 'paint_end': r.end, 'purpose': r.purpose})
    for u in usages:
        overdue = not u.returned_at and u.expected_return <= now
        end = u.returned_at or u.expected_return
        if overdue:
            end = None
        events.append({'kind': 'overdue' if overdue else 'usage', 'label': 'Rückgabe offen' if overdue else 'Nutzung', 'vehicle': u.vehicle, 'user': u.user, 'start': u.started_at, 'end': end, 'paint_end': range_end if overdue else end, 'purpose': u.purpose})
    events.sort(key=lambda e: (e['start'], e['vehicle'].plate))
    output = []
    today = timezone.localdate()
    for week in weeks:
        cells = []
        for day in week:
            start = timezone.make_aware(datetime.combine(day, time.min))
            end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
            day_events = []
            for event in events:
                if event['start'] < end and event['paint_end'] > start:
                    day_events.append({**event, 'time_label': timezone.localtime(event['start']).strftime('%H:%M') if event['start'] >= start else 'Fortsetzung'})
            cells.append({'date': day, 'in_month': day.month == month.month, 'today': day == today, 'events': day_events})
        output.append(cells)
    previous = (month-timedelta(days=1)).replace(day=1)
    following = (month.replace(day=28)+timedelta(days=4)).replace(day=1)
    return {'weeks': output, 'title': f'{MONTHS[month.month-1]} {month.year}', 'previous': previous if previous.year >= 1900 else None, 'following': following if following.year <= 2100 else None}
