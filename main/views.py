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


def _compute_streaks(habit_ids, reference_date):
    """
    Computes current streak (consecutive completed days ending today or yesterday)
    and best streak (all-time longest consecutive completed days) for given habit IDs.
    """
    if not habit_ids:
        return {}

    logs = HabitLog.objects.filter(
        habit_id__in=habit_ids, completed=True
    ).values_list('habit_id', 'date')

    habit_dates = {}
    for hid, d in logs:
        habit_dates.setdefault(hid, set()).add(d)

    streaks = {}
    for hid in habit_ids:
        dates_set = habit_dates.get(hid, set())

        # Current streak
        current = 0
        if reference_date in dates_set:
            check_d = reference_date
            while check_d in dates_set:
                current += 1
                check_d -= timedelta(days=1)
        else:
            check_d = reference_date - timedelta(days=1)
            while check_d in dates_set:
                current += 1
                check_d -= timedelta(days=1)

        # Best streak (all time)
        best = 0
        if dates_set:
            sorted_dates = sorted(dates_set)
            running = 0
            prev_d = None
            for d in sorted_dates:
                if prev_d is not None and d == prev_d + timedelta(days=1):
                    running += 1
                else:
                    running = 1
                if running > best:
                    best = running
                prev_d = d

        streaks[hid] = {
            'current': current,
            'best': max(best, current)
        }

    return streaks


@login_required
def day_view(request, date_str=None):
    today = timezone.localdate()
    target_date = _parse_date(date_str) if date_str else today

    if target_date > today:
        target_date = today

    habits = Habit.objects.filter(is_active=True)
    habit_ids = [h.id for h in habits]

    completed_ids = set(
        HabitLog.objects.filter(date=target_date, completed=True).values_list(
            'habit_id', flat=True)
    )

    streaks = _compute_streaks(habit_ids, today)

    habit_data = [
        {
            'habit': h,
            'done': h.id in completed_ids,
            'current_streak': streaks.get(h.id, {}).get('current', 0),
            'best_streak': streaks.get(h.id, {}).get('best', 0),
        }
        for h in habits
    ]

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

    habit_ids = [h.id for h in habits]
    streaks = _compute_streaks(habit_ids, today)

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

        h_streak = streaks.get(h.id, {'current': 0, 'best': 0})

        if habit_end < habit_start:
            habit_stats.append({
                'habit': h,
                'completed': 0,
                'missed': 0,
                'percent': None,
                'tracked_days': 0,
                'current_streak': h_streak['current'],
                'best_streak': h_streak['best'],
                'recent_dots': [],
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

        recent_dots = []
        for d in date_list[-7:]:  # last 7 days mini strip for each habit
            if d not in active_on[h.id]:
                recent_dots.append({'status': 'na', 'date': d, 'day': d.strftime('%a')[0]})
            elif (h.id, d) in log_set:
                recent_dots.append({'status': 'on', 'date': d, 'day': d.strftime('%a')[0]})
            else:
                recent_dots.append({'status': 'off', 'date': d, 'day': d.strftime('%a')[0]})

        habit_stats.append({
            'habit': h,
            'completed': completed_days,
            'missed': missed_days,
            'percent': percent,
            'tracked_days': tracked_days,
            'current_streak': h_streak['current'],
            'best_streak': h_streak['best'],
            'recent_dots': recent_dots,
        })
        total_possible += tracked_days
        total_completed += completed_days

    overall_percent = int((total_completed / total_possible)
                          * 100) if total_possible else 0

    # Build Calendar Weeks (Monday to Sunday grid)
    padding_before = start_date.weekday()  # Monday = 0
    padded_start = start_date - timedelta(days=padding_before)

    padding_after = (6 - today.weekday())  # Sunday = 6
    padded_end = today + timedelta(days=padding_after)

    total_cal_days = (padded_end - padded_start).days + 1
    calendar_weeks = []
    current_week = []

    for i in range(total_cal_days):
        d = padded_start + timedelta(days=i)
        is_in_range = start_date <= d <= today

        if is_in_range:
            active_count = sum(1 for h in habits if d in active_on[h.id])
            done_count = sum(1 for h in habits if d in active_on[h.id] and (h.id, d) in log_set)
            if active_count > 0:
                pct = int((done_count / active_count) * 100)
                if done_count == 0:
                    level = 0
                elif pct == 100:
                    level = 3
                elif pct >= 50:
                    level = 2
                else:
                    level = 1
            else:
                pct = 0
                level = 0
        else:
            active_count = 0
            done_count = 0
            pct = 0
            level = 'out'

        day_cell = {
            'date': d,
            'day_num': d.day,
            'month_short': d.strftime('%b'),
            'weekday_short': d.strftime('%a'),
            'is_today': d == today,
            'is_in_range': is_in_range,
            'is_future': d > today,
            'active_count': active_count,
            'done_count': done_count,
            'percent': pct,
            'level': level,
        }
        current_week.append(day_cell)
        if len(current_week) == 7:
            calendar_weeks.append(current_week)
            current_week = []

    # 7-day strip
    days_7 = []
    for d in date_list[-7:]:
        active_count = sum(1 for h in habits if d in active_on[h.id])
        done_count = sum(1 for h in habits if d in active_on[h.id] and (h.id, d) in log_set)
        pct = int((done_count / active_count) * 100) if active_count > 0 else 0
        level = 3 if pct == 100 else (2 if pct >= 50 else (1 if done_count > 0 else 0))
        days_7.append({
            'date': d,
            'day_num': d.day,
            'weekday_short': d.strftime('%a'),
            'is_today': d == today,
            'active_count': active_count,
            'done_count': done_count,
            'percent': pct,
            'level': level if active_count > 0 else 'na',
        })

    context = {
        'period': period,
        'days': days,
        'habit_stats': habit_stats,
        'overall_percent': overall_percent,
        'total_completed': total_completed,
        'total_possible': total_possible,
        'total_missed': total_possible - total_completed,
        'habits': habits,
        'calendar_weeks': calendar_weeks,
        'days_7': days_7,
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
