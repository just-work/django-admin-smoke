from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline

from testproject.testapp import models


@admin.register(models.Task)
class TaskAdmin(admin.ModelAdmin):
    pass


class TaskInline(admin.TabularInline):
    model = models.Task


class TagInline(GenericTabularInline):
    model = models.Tag


@admin.register(models.Project)
class ProjectAdmin(admin.ModelAdmin):
    inlines = (TaskInline, TagInline)
