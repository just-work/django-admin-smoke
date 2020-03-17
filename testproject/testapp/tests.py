from admin_smoke.tests import AdminTests, AdminBaseTestCase
from testproject.testapp import admin, models


class ProjectAdminTestCase(AdminTests, AdminBaseTestCase):
    model_admin = admin.ProjectAdmin
    model = models.Project
    object_name = 'project'

    def setUp(self):
        super().setUp()
        self.project = models.Project.objects.create(name='first')
        self.task = models.Task.objects.create(name='first',
                                               project=self.project)

    def transform_to_new(self, data: dict) -> dict:
        data = data.copy()
        del data['id']
        data['name'] = 'new'
        self.reset_inline_data(data, 'task_set', 'project')
        data['task_set-0-name'] += '_new'
        return data

    def prepare_deletion(self):
        self.task.delete()
