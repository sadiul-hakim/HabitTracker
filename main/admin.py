from django.contrib import admin
from .models import Habit, HabitLog


@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'order', 'is_active',
                    'created_at', 'archived_at')
    list_editable = ('order', 'is_active')
    search_fields = ('name',)
    readonly_fields = ('archived_at',)
    list_per_page = 25


@admin.register(HabitLog)
class HabitLogAdmin(admin.ModelAdmin):
    list_display = ('habit', 'date', 'completed')
    list_filter = ('habit', 'completed', 'date')
    date_hierarchy = 'date'
    list_per_page = 25
