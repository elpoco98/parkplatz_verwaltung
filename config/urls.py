from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
urlpatterns = [path('admin/', admin.site.urls), path('login/', auth_views.LoginView.as_view(), name='login'), path('logout/', auth_views.LogoutView.as_view(), name='logout'), path('password/', auth_views.PasswordChangeView.as_view(template_name='fleet/form.html', extra_context={'title': 'Passwort ändern'}, success_url='/password/done/'), name='password_change'), path('password/done/', auth_views.PasswordChangeDoneView.as_view(template_name='registration/password_change_done.html'), name='password_change_done'), path('', include('fleet.urls'))]
admin.site.site_header = 'ParkPilot · Administration'
admin.site.site_title = 'ParkPilot'
