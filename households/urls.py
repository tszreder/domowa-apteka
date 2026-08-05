from django.urls import path

from . import views

app_name = 'households'

urlpatterns = [
    path('', views.landing, name='landing'),
]
