from django.urls import path

from . import views

app_name = 'pharmacy'

urlpatterns = [
    path('list/', views.item_list, name='item_list'),
]
