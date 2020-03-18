from django.core.files.uploadedfile import SimpleUploadedFile

from admin_smoke.tests import AdminTests, AdminBaseTestCase
from testproject.testapp import admin, models


class ProjectAdminTestCase(AdminTests, AdminBaseTestCase):
    model_admin = admin.ProjectAdmin
    model = models.Project
    object_name = 'project'

    def setUp(self):
        super().setUp()
        self.project = models.Project.objects.create(name='project', pid=123)
        self.task = self.project.task_set.create(
            name='task', attachment=SimpleUploadedFile("txt.doc", b'text'))
        self.tag = self.project.tags.create(name='tag')

    def transform_to_new(self, data: dict) -> dict:
        data = data.copy()
        del data['pid']
        data['name'] = 'new'
        self.reset_inline_data(data, 'task_set', 'project')
        self.reset_inline_data(
            data, 'testapp-tag-content_type-object_id', None, pk='tid')
        data['task_set-0-name'] += '_new'
        data['task_set-0-attachment'] = SimpleUploadedFile("doc.txt", b'text')
        return data

    def prepare_deletion(self):
        self.task.delete()
