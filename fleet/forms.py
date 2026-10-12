from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Vehicle, VehicleType

class DateTimeInput(forms.DateTimeInput):
    input_type = 'datetime-local'
    def __init__(self, **kwargs):
        super().__init__(format='%Y-%m-%dT%H:%M', **kwargs)

def datefield(label):
    return forms.DateTimeField(label=label, widget=DateTimeInput(), input_formats=['%Y-%m-%dT%H:%M'])

class AvailabilityForm(forms.Form):
    start = datefield('Von (Schweizer Zeit)')
    end = datefield('Bis (Schweizer Zeit)')
    vehicle_type = forms.ModelChoiceField(label='Fahrzeugtyp', queryset=VehicleType.objects.all(), required=False, empty_label='Alle Fahrzeugtypen')

    def clean(self):
        data = super().clean()
        start, end = data.get('start'), data.get('end')
        if start and start < timezone.now():
            self.add_error('start', 'Bitte einen zukünftigen Zeitpunkt wählen.')
        if start and end and end <= start:
            self.add_error('end', 'Das Ende muss nach dem Beginn liegen.')
        return data

class VehicleForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput, required=False)
    class Meta:
        model = Vehicle
        fields = ['plate', 'name', 'vehicle_type', 'mileage', 'notes', 'active']
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}
    def clean_plate(self):
        return self.cleaned_data['plate'].strip().upper()

class PersonForm(forms.Form):
    user = forms.ModelChoiceField(label='Benutzer', queryset=get_user_model().objects.none())
    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        users = get_user_model().objects.filter(is_active=True).order_by('username')
        self.fields['user'].queryset = users if actor.is_staff else users.filter(pk=actor.pk)
        self.fields['user'].initial = actor.pk

class ReservationForm(PersonForm):
    start = datefield('Von (Schweizer Zeit)')
    end = datefield('Bis (Schweizer Zeit)')
    purpose = forms.CharField(label='Zweck', max_length=300, required=False)

class CheckoutForm(PersonForm):
    expected_return = datefield('Geplante Rückgabe (Schweizer Zeit)')
    mileage = forms.IntegerField(label='Aktueller Kilometerstand', min_value=0)
    purpose = forms.CharField(label='Zweck', max_length=300, required=False)

class ReturnForm(forms.Form):
    mileage = forms.IntegerField(label='Kilometerstand bei Rückgabe', min_value=0)
    notes = forms.CharField(label='Bemerkungen / Schäden', max_length=3000, required=False, widget=forms.Textarea(attrs={'rows': 4}))

class CalendarForm(forms.Form):
    month = forms.DateField(label='Monat', input_formats=['%Y-%m'], widget=forms.DateInput(format='%Y-%m', attrs={'type': 'month'}))
    vehicle_type = forms.ModelChoiceField(label='Fahrzeugtyp', queryset=VehicleType.objects.all(), required=False, empty_label='Alle Fahrzeugtypen')
    vehicle = forms.ModelChoiceField(label='Fahrzeug', queryset=Vehicle.objects.select_related('vehicle_type'), required=False, empty_label='Alle Fahrzeuge')

    def clean_month(self):
        value = self.cleaned_data['month']
        if not 1900 <= value.year <= 2100:
            raise forms.ValidationError('Bitte einen Monat zwischen 1900 und 2100 wählen.')
        return value
