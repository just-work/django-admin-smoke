from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline

from testproject.testapp import models


@admin.register(models.Task)
class TaskAdmin(admin.ModelAdmin):

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class TaskInline(admin.TabularInline):
    model = models.Task


class TagInline(GenericTabularInline):
    model = models.Tag


@admin.register(models.Project)
class ProjectAdmin(admin.ModelAdmin):
    inlines = (TaskInline, TagInline)
    list_display = ('pid', 'name',)
    list_editable = ('name',)
    exclude = ('client',)


@admin.register(models.InnerProject)
class InnerProjectAdmin(admin.ModelAdmin):
    inlines = (TaskInline, TagInline)
    list_display = ('pid', 'name',)
    list_editable = ('name',)
    fields = ('name', )
