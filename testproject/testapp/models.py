from django.contrib.auth import get_user_model
from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=10, unique=True)
    members = models.ManyToManyField(get_user_model(), blank=True)


class Task(models.Model):
    project = models.ForeignKey(Project, models.PROTECT)
    name = models.CharField(max_length=10, unique=True)
