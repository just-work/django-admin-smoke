Django-admin-smoke
==================

Django-Admin-Smoke is a Django app providing smoke tests for django-admin.

![build](https://github.com/just-work/django-admin-smoke/workflows/build/badge.svg?branch=master)
[![codecov](https://codecov.io/gh/just-work/django-admin-smoke/branch/master/graph/badge.svg)](https://codecov.io/gh/just-work/django-admin-smoke)
[![PyPI version](https://badge.fury.io/py/django-admin-smoke.svg)](https://badge.fury.io/py/django-admin-smoke)

Installation
------------

```shell script
pip install django-admin-smoke
```

Usage
-----

Full example located at `testproject.testapp.tests`

```python

from admin_smoke.tests import AdminTests, AdminBaseTestCase
from testproject.testapp import admin, models


class ProjectAdminTestCase(AdminTests, AdminBaseTestCase):
    model_admin = admin.ProjectAdmin  # ModelAdmin to test
    model = models.Project  # Django model to test against
    object_name = 'project'  # self.project is an edited object in this testcase
    excluded_fields = ['client']  #  fields excluded from presence check

    def setUp(self):
        super().setUp()
        # We need existing object to test editing and deleting
        self.project = models.Project.objects.create(name='first')
        # All inlines for tested model admin should be non-empty, so we fill
        # all related models.
        self.task = models.Task.objects.create(name='first',
                                               project=self.project)

    def transform_to_new(self, data: dict) -> dict:
        # Creating a new object is tested with following algorithm:
        # 1. Open "edit" page for existing object
        # 2. Clear PK value in form data
        # 3. Clear PK values for all related objects in admin inlines
        # 4. Clear FK values pointing to existing object in admin inlines
        # 5. POST resulting data to "add" page
        # This algorithm need some help with unique fields and other constraints
        # and restrictions, so there is a hook for making newly created object
        # valid.

        data = data.copy()
        # Project.name is unique, making new value
        data['name'] += 'new'
        # Manually reset PK/FK values in admin inlines
        self.reset_inline_data(
            data,        # form data
            'task_set',  # name of inline prefix - it's FK's related_name 
            'project'    # name of edited object FK field (FK.name)
        )
        # Task.name is also unique, it should be changed properly
        data['task_set-0-name'] += '_new'
        return data

    def prepare_deletion(self):
        # To delete an object with FK's with models.PROTECT behavior we need
        # a hook to delete it manually before POST delete confirmation.
        self.task.delete()
```

Happy testing and non-smoky admins :)
