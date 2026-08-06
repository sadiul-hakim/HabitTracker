from django.urls import path, include
from . import views

app_name = 'routines'

urlpatterns = [
    path('', views.day_view, name='today'),
    path('day/<str:date_str>/', views.day_view, name='day'),
    path('toggle/<int:habit_id>/<str:date_str>/',
         views.toggle_habit, name='toggle'),
    path('stats/', views.stats_view, name='stats'),
    path('manage/', views.manage_habits, name='manage'),
    path('delete/<int:habit_id>/', views.delete_habit, name='delete'),
]
