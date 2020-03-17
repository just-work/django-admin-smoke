from django.contrib import admin

from testproject.testapp import models


@admin.register(models.Task)
class TaskAdmin(admin.ModelAdmin):
    pass


class TaskInline(admin.TabularInline):
    model = models.Task


@admin.register(models.Project)
class ProjectAdmin(admin.ModelAdmin):
    inlines = (TaskInline,)
