from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views
from .forms import EmailAuthenticationForm

app_name = 'households'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('signup/', views.signup, name='signup'),
    path(
        'login/',
        LoginView.as_view(
            template_name='households/login.html',
            authentication_form=EmailAuthenticationForm,
        ),
        name='login',
    ),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('list/', views.item_list, name='item_list'),
    path('join/<str:token>/', views.join, name='join'),
    path('household/', views.household_detail, name='household_detail'),
    path('household/create/', views.household_create, name='household_create'),
    path('household/invite/regenerate/', views.regenerate_invite, name='regenerate_invite'),
]
