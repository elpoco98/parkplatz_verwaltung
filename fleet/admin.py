from django.contrib import admin
from .models import VehicleType, Vehicle, Reservation, Usage, Audit

@admin.register(VehicleType)
class VehicleTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']

class ReadOnlyAdmin(admin.ModelAdmin):
    exclude = ['space']
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
for model in (Vehicle, Reservation, Usage, Audit):
    admin.site.register(model, ReadOnlyAdmin)
