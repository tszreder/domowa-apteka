from django.urls import path

from . import views

app_name = 'pharmacy'

urlpatterns = [
    path('list/', views.item_list, name='item_list'),
    path('list/add/', views.item_add, name='item_add'),
    path('list/<int:pk>/delete/', views.item_delete, name='item_delete'),
    path('suggestions/', views.product_suggestions, name='product_suggestions'),
]
