from django.core.files.uploadedfile import SimpleUploadedFile

from admin_smoke.tests import AdminTests, AdminBaseTestCase, BaseTestCase
from testproject.testapp import admin, models


class ProjectAdminTestCase(AdminTests, AdminBaseTestCase):
    model_admin = admin.ProjectAdmin
    model = models.Project
    object_name = 'project'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.project = models.Project.objects.create(name='project', pid=123)
        cls.task = cls.project.task_set.create(
            name='task', attachment=SimpleUploadedFile("txt.doc", b'text'))
        cls.tag = cls.project.tags.create(name='tag')

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


class BaseTestCaseMetaTestCase(BaseTestCase):
    """ Tests for base testcase metaclass."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.project = models.Project.objects.create(name='project')
        cls.project2 = models.Project.objects.create(name='project2')
        cls.forget_object(cls.project2)
        cls.project2.delete()

    def test_1_first(self):
        """ Modify something in memory."""
        self.project.name = 'modified'
        self.project.save()

        self.project2.name = 'modified2'

    def test_2_second(self):
        """ class attributes are reset correctly."""
        # This test fill pass only if running whole test case
        self.assertEqual(self.project.name, "project")
        # forgotten object is in modified state
        self.assertEqual(self.project2.name, "modified2")
