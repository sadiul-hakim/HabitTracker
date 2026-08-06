from datetime import timedelta, datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Habit, HabitLog


def _parse_date(date_str):
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        raise Http404("Invalid date")


@login_required
def day_view(request, date_str=None):
    today = timezone.localdate()
    target_date = _parse_date(date_str) if date_str else today

    if target_date > today:
        target_date = today

    habits = Habit.objects.filter(is_active=True)

    completed_ids = set(
        HabitLog.objects.filter(date=target_date, completed=True).values_list(
            'habit_id', flat=True)
    )

    habit_data = [{'habit': h, 'done': h.id in completed_ids} for h in habits]

    total = habits.count()
    completed_count = len(completed_ids)
    percent = int((completed_count / total) * 100) if total else 0

    context = {
        'habit_data': habit_data,
        'target_date': target_date,
        'today': today,
        'is_today': target_date == today,
        'prev_date': target_date - timedelta(days=1),
        'next_date': target_date + timedelta(days=1) if target_date < today else None,
        'completed_count': completed_count,
        'total': total,
        'percent': percent,
    }
    return render(request, 'routines/today.html', context)


@login_required
@require_POST
def toggle_habit(request, habit_id, date_str):
    habit = get_object_or_404(Habit, id=habit_id)
    target_date = _parse_date(date_str)
    today = timezone.localdate()

    if target_date > today:
        return redirect('routines:today')

    log, created = HabitLog.objects.get_or_create(
        habit=habit, date=target_date, defaults={'completed': True}
    )
    if not created:
        log.completed = not log.completed
        log.save()

    if target_date == today:
        return redirect('routines:today')
    return redirect('routines:day', date_str=date_str)


@login_required
def stats_view(request):
    period = request.GET.get('period', 'week')
    days = 30 if period == 'month' else 7

    today = timezone.localdate()
    start_date = today - timedelta(days=days - 1)
    date_list = [start_date + timedelta(days=i) for i in range(days)]

    habits = Habit.objects.filter(
        Q(is_active=True)
        | Q(archived_at__date__gte=start_date)
        | Q(logs__date__range=(start_date, today))
    ).distinct()

    logs = HabitLog.objects.filter(
        date__gte=start_date, date__lte=today, completed=True)
    log_set = {(log.habit_id, log.date) for log in logs}

    habit_stats = []
    total_possible = 0
    total_completed = 0
    active_on = {h.id: set() for h in habits}

    for h in habits:
        habit_start = start_date
        habit_end = today if not h.archived_at else min(
            today, h.archived_at.date())

        if habit_end < habit_start:
            habit_stats.append({
                'habit': h, 'completed': 0, 'missed': 0, 'percent': None, 'tracked_days': 0,
            })
            continue

        tracked_days = (habit_end - habit_start).days + 1
        completed_days = sum(
            1 for d in date_list
            if habit_start <= d <= habit_end and (h.id, d) in log_set
        )
        missed_days = tracked_days - completed_days
        percent = int((completed_days / tracked_days)
                      * 100) if tracked_days else None

        for d in date_list:
            if habit_start <= d <= habit_end:
                active_on[h.id].add(d)

        habit_stats.append({
            'habit': h,
            'completed': completed_days,
            'missed': missed_days,
            'percent': percent,
            'tracked_days': tracked_days,
        })
        total_possible += tracked_days
        total_completed += completed_days

    overall_percent = int((total_completed / total_possible)
                          * 100) if total_possible else 0

    grid = []
    for d in date_list:
        row = {'date': d, 'is_today': d == today, 'cells': []}
        for h in habits:
            if d not in active_on[h.id]:
                row['cells'].append('na')
            elif (h.id, d) in log_set:
                row['cells'].append('on')
            else:
                row['cells'].append('off')
        grid.append(row)

    context = {
        'period': period,
        'days': days,
        'habit_stats': habit_stats,
        'overall_percent': overall_percent,
        'total_completed': total_completed,
        'total_possible': total_possible,
        'total_missed': total_possible - total_completed,
        'habits': habits,
        'grid': grid,
        'start_date': start_date,
        'today': today,
    }
    return render(request, 'routines/stats.html', context)


@login_required
def manage_habits(request):
    active_habits = Habit.objects.filter(
        is_active=True).order_by('order', 'name')
    archived_habits = Habit.objects.filter(
        is_active=False).order_by('-archived_at')
    return render(request, 'routines/manage.html', {
        'active_habits': active_habits,
        'archived_habits': archived_habits,
    })


@login_required
def delete_habit(request, habit_id):
    habit = get_object_or_404(Habit, id=habit_id)

    if habit.is_active:
        return redirect('routines:manage')

    log_count = habit.logs.count()

    if request.method == 'POST':
        confirm_name = request.POST.get('confirm_name', '').strip()
        if confirm_name == habit.name:
            habit.delete()
            return redirect('routines:manage')
        return render(request, 'routines/delete_confirm.html', {
            'habit': habit, 'log_count': log_count, 'error': True,
        })

    return render(request, 'routines/delete_confirm.html', {
        'habit': habit, 'log_count': log_count,
    })
