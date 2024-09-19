from django.contrib.auth.models import User
from django.contrib.contenttypes import fields
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Tag(models.Model):
    tid = models.AutoField(primary_key=True)
    name = models.CharField(max_length=32, blank=True)
    content_type = models.ForeignKey(ContentType, models.CASCADE)
    object_id = models.IntegerField()
    related = fields.GenericForeignKey()


class Client(models.Model):
    name = models.CharField(max_length=10, unique=True)


class Project(models.Model):
    pid = models.AutoField(primary_key=True)
    name = models.CharField(max_length=10, unique=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True,
                               blank=True)
    members = models.ManyToManyField(User, blank=True)
    tags = fields.GenericRelation(Tag)
    created = models.DateTimeField(auto_now_add=True, editable=False)
    modified = models.DateTimeField(auto_now=True, editable=False)


class Task(models.Model):
    project = models.ForeignKey(Project, models.PROTECT)
    name = models.CharField(max_length=10, unique=True)
    attachment = models.FileField()
    visible = models.BooleanField(default=True)


class InnerProject(Project):
    class Meta:
        proxy = True
