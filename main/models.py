from django.db import models
from django.utils import timezone


class Habit(models.Model):
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=10, blank=True,
                            help_text="Optional emoji, e.g. 📖")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Automatically stamp archived_at when a habit is deactivated,
        # and clear it if it's reactivated. This lets Stats know exactly
        # which days a habit was actually "in play" for.
        if self.pk:
            old = Habit.objects.filter(pk=self.pk).values('is_active').first()
            if old:
                if old['is_active'] and not self.is_active:
                    self.archived_at = timezone.now()
                elif not old['is_active'] and self.is_active:
                    self.archived_at = None
        super().save(*args, **kwargs)


class HabitLog(models.Model):
    habit = models.ForeignKey(
        Habit, on_delete=models.CASCADE, related_name='logs')
    date = models.DateField()
    completed = models.BooleanField(default=True)

    class Meta:
        unique_together = ('habit', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.habit.name} - {self.date} ({'done' if self.completed else 'missed'})"
