from datetime import timedelta, datetime
from typing import TypeVar, Type, Union, Optional, List, Tuple
from unittest import mock

from django.contrib.admin import ModelAdmin, site
from django.contrib.admin.helpers import AdminForm
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.fields.files import FieldFile
from django.forms import MultiWidget
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import classproperty
from django.utils.translation import gettext_lazy as _

second = timedelta(seconds=1)

M = TypeVar('M', bound=models.Model)

# type definition for TestCase subclass mixed with TimeMixin
TimeDerived = Union["TimeMixin", TestCase]


class MockedDateTime(datetime):
    """
    Stub for DateTimeField auto_now/auto_now_add.

    Helps to override model_utils.TimeStampedModel.created.default
    """

    @classmethod
    def utcnow(cls):
        # noinspection PyUnresolvedReferences
        return timezone.utc.normalize(timezone.now())


class TimeMixin:
    """ Mixin to freeze time in django tests."""
    now: datetime

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self: TimeDerived):
        # noinspection PyUnresolvedReferences
        super().setUp()
        self.now = timezone.now()
        self.now_patcher = mock.patch('django.utils.timezone.now',
                                      side_effect=self.get_now)
        self.now_patcher.start()

        self.timezone_datetime_patcher = mock.patch(
            'django.utils.timezone.datetime',
            new_callable=mock.PropertyMock(return_value=MockedDateTime))
        self.timezone_datetime_patcher.start()

    # noinspection PyPep8Naming
    def tearDown(self: TimeDerived):
        # noinspection PyUnresolvedReferences
        super().tearDown()
        self.timezone_datetime_patcher.stop()
        self.now_patcher.stop()

    def get_now(self):
        return self.now


class BaseTestCaseMeta(type):
    """
    Collect and reset django models attributes initialized in SetUpTestData.
    """
    _created_objects: List[Tuple[int, models.Model]]

    def __setattr__(cls, key, value):
        if isinstance(value, models.Model):
            cls._created_objects.append((value.pk, value))
        return super().__setattr__(key, value)


class BaseTestCase(TimeMixin, TestCase, metaclass=BaseTestCaseMeta):
    """ Base class for django tests."""

    _created_objects = []

    @classmethod
    def refresh_objects(cls):
        """
        Reset in-memory changed for django models that are stored as
        class attributes.
        """
        for pk, obj in cls._created_objects:
            obj.pk = pk
            try:
                obj.refresh_from_db()
                # noinspection PyProtectedMember
                obj._state.fields_cache.clear()
            except models.ObjectDoesNotExist:
                pass

    @staticmethod
    def update_object(obj, *args, **kwargs):
        """ Update django model object in database only."""
        args_iter = iter(args)
        kwargs.update(dict(zip(args_iter, args_iter)))
        obj._meta.model.objects.filter(pk=obj.pk).update(**kwargs)

    @staticmethod
    def reload(obj: M) -> M:
        """ Fetch same object from database."""
        return obj._meta.model.objects.get(pk=obj.pk)

    def setUp(self):
        self.refresh_objects()
        super().setUp()

    def assert_object_fields(self, obj: models.Model, **kwargs):
        """ Obtains object from database and compares field values."""
        if obj.pk:
            obj = self.reload(obj)
        for k, v in kwargs.items():
            value = getattr(obj, k)
            self.assertEqual(value, v)


class AdminBaseTestCase(BaseTestCase):
    """ Base class for django admin smoke tests."""
    model_admin: Type[ModelAdmin]
    model: Type[models.Model]
    object_name: str

    @classproperty
    def opts(self):
        # noinspection PyUnresolvedReferences
        return self.model._meta

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.superuser = get_user_model().objects.create_superuser(
            username='admin', email='admin@gmail.com', password='admin_admin')
        cls.admin = cls.model_admin(cls.model, site)
        cls.changelist_url = reverse(
            f'admin:{cls.opts.app_label}_{cls.opts.model_name}_changelist')
        cls.add_url = reverse(
            f'admin:{cls.opts.app_label}_{cls.opts.model_name}_add')

    def setUp(self):
        super().setUp()
        self.client.login(username='admin', password='admin_admin')

    @staticmethod
    def reset_inline_data(data: dict, prefix: str, related: Optional[str],
                          pk: str = 'id'):
        """ Transforms saved records in formsets to new ones.

        :param data: form data dictionary
        :param prefix: inline formset prefix
        :param related: name of inline model ForeignKey field pointing to
            edited object (None for GenericInlineModelAdmin)
        :param pk: name of inline model primary key field
        """
        del data[f'{prefix}-0-{pk}']
        if related is not None:
            del data[f'{prefix}-0-{related}']
        data[f'{prefix}-INITIAL_FORMS'] = 0

    @property
    def change_url(self):
        """ Admin object edit page url."""
        return reverse(
            f'admin:{self.opts.app_label}_{self.opts.model_name}_change',
            kwargs={'object_id': self.get_object().pk})

    @property
    def delete_url(self):
        """ Admin delete confirmation page url."""
        return reverse(
            f'admin:{self.opts.app_label}_{self.opts.model_name}_delete',
            kwargs={'object_id': self.get_object().pk})

    def get_object(self):
        """ Get tested object."""
        return getattr(self, self.object_name)

    def transform_to_new(self, data: dict) -> dict:
        """
        Method modifies admin form data to look like a valid new object.
        """
        raise NotImplementedError()

    def prepare_deletion(self):
        """
        Prepares object for deletion to exclude errors caused by
        on_delete=PROTECT.
        """
        pass

    @staticmethod
    def get_form_data(form):
        """ Get initial request data from form."""
        initial = form.initial.copy()
        data = {}
        if hasattr(form, 'instance') and form.instance:
            model = form._meta.model
            while model._meta.proxy:
                model = model._meta.proxy_for_model

            for f in model._meta.local_fields:
                if f.name in form.fields or f.primary_key and form.instance.pk:
                    initial[f.name] = getattr(form.instance, f.attname)

        for k, v in initial.items():
            try:
                field = form.fields[k]
                v = field.prepare_value(v)
            except KeyError:
                model_field = form._meta.model._meta.get_field(k)
                if model_field.primary_key:
                    data[k] = v
                continue

            key = f'{form.prefix}-{k}' if form.prefix else k
            if isinstance(field.widget, MultiWidget):
                for i, w in enumerate(field.widget.widgets):
                    value = w.format_value(v)
                    if value is None:
                        continue
                    data[f'{key}_{i}'] = value
                continue
            if isinstance(v, FieldFile):
                v = ''
            if v is None:
                continue
            data[key] = v
        return data

    def get_form_data_from_response(self, r: HttpResponse):
        """ Get form data from response context."""
        data = {'_continue': 'save and continue'}
        cd = getattr(r, 'context_data')
        admin_form: AdminForm = cd['adminform']
        data.update(self.get_form_data(admin_form.form))
        formsets = cd['inline_admin_formsets']
        for inline_formset in formsets:
            formset = inline_formset.formset
            forms_count = len(inline_formset.forms)
            extra_count = inline_formset.opts.extra
            # for proper test coverage inlines must not be empty
            self.assertGreater(forms_count, extra_count,
                               f"Empty AdminInline {formset.prefix}")
            for form in formset.forms:
                data.update(self.get_form_data(form))
            data.update(self.get_form_data(formset.management_form))
        return data

    @staticmethod
    def get_errors_from_response(r: HttpResponse):
        """ Get error list from response context."""
        data = {}
        if r.status_code == 302:
            return data
        cd = getattr(r, 'context_data')
        admin_form: AdminForm = cd['adminform']
        data.update(admin_form.form.errors)
        formsets = cd['inline_admin_formsets']
        for inline_formset in formsets:
            formset = inline_formset.formset
            for form in formset.forms:
                data.update(form.errors)
            data.update(formset.management_form.errors)
            errors = formset.non_form_errors()
            if errors:
                data['non_form_errors'] = errors
        return data


# type definition for subclasses with CommonAdminTests mixin
AdminTestsDerived = Union["CommonAdminTests", AdminBaseTestCase]


class CommonAdminTests:
    """ Common smoke tests for django admin."""

    def test_changelist(self: AdminTestsDerived):
        """ Object list ist rendered correctly."""
        url = self.changelist_url
        count = self.model.objects.count()
        self.assert_row_count(url, count)

    def assert_row_count(self: AdminTestsDerived, url, count):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        text = r.content.decode('utf-8')
        if count == 1:
            n = self.opts.verbose_name
        else:
            n = self.opts.verbose_name_plural
        if self.admin.list_editable:
            save = (' <input type="submit" name="_save" '
                    'class="default" value="%s">' % _("Save"))
        else:
            save = ''
        marker = f'<p class="paginator">{count} {n}{save}</p>'
        self.assertInHTML(marker, text)
        return text

    def post_changeform(self: AdminTestsDerived, create=False,
                        erase_data=False):
        r = self.client.get(self.change_url)
        data = self.get_form_data_from_response(r)
        if create:
            url = self.add_url
            data = self.transform_to_new(data)
        else:
            url = self.change_url
        # clear form fields, preserving only django formset management form
        if erase_data:
            data = {k: data[k] for k in data if '_FORMS' in k}
        return self.client.post(url, data=data)

    def test_changeform_view(self: AdminTestsDerived):
        """ Add object page opens correctly."""
        r = self.client.get(self.add_url)
        self.assertEqual(r.status_code, 200)

    def test_changeform_save(self: AdminTestsDerived):
        """ Save same existing object works."""
        self.now += second
        r = self.post_changeform()
        self.assertFalse(self.get_errors_from_response(r))
        self.assertEqual(r.status_code, 302)

        obj = self.get_object()
        if hasattr(obj, 'modified'):
            # check whether TimeStampedModel.modified timestamp has changed
            self.assert_object_fields(obj, modified=self.now)

    def test_changeform_create(self: AdminTestsDerived):
        """ New object created correctly."""
        c = self.model.objects.count()
        self.now += second

        r = self.post_changeform(create=True)
        self.assertFalse(self.get_errors_from_response(r))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.model.objects.count(), c + 1)
        obj = self.model.objects.order_by(self.opts.pk.name).last()
        if hasattr(obj, 'created'):
            # checks TimeStampModel.created timestamp
            self.assertEqual(obj.created, self.now)

    def test_delete(self: AdminTestsDerived):
        """
        Deleting object works correctly.
        """
        self.prepare_deletion()
        r = self.client.post(self.delete_url, {'post': 'yes'})
        cd = getattr(r, 'context_data', {})
        self.assertFalse(cd.get('protected'))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(self.get_errors_from_response(r))
        self.assertFalse(self.model.objects.filter(
            pk=self.get_object().pk).exists())


class AdminTests(CommonAdminTests):
    """ smoke tests for full-functional django admin."""

    def test_changeform_create_without_data(self: AdminTestsDerived):
        """
        Creating new object without required fields returns proper response
        with error list.
        """
        r = self.post_changeform(create=True, erase_data=True)
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(self.get_errors_from_response(r))


class ReadOnlyAdminTests(CommonAdminTests):
    """ smoke tests for readonly django admin."""

    def test_changeform_view(self: AdminTestsDerived):
        """
        New object admin page returns access denied.
        """
        r = self.client.get(self.add_url)
        self.assertEqual(r.status_code, 403)

    def test_changeform_create(self: AdminTestsDerived):
        """
        POST to create admin view is denied.
        """
        r = self.client.get(self.change_url)
        data = self.get_form_data_from_response(r)
        data = self.transform_to_new(data)

        r = self.client.post(self.add_url, data=data)

        self.assertEqual(r.status_code, 403)

    def test_changeform_save(self: AdminTestsDerived):
        """
        Object changing is denied.
        """
        r = self.client.get(self.change_url)
        data = self.get_form_data_from_response(r)

        r = self.client.post(self.change_url, data=data)

        self.assertEqual(r.status_code, 403)

    def test_delete(self: AdminTestsDerived):
        """
        Object deletion is denied.
        """
        self.prepare_deletion()
        r = self.client.post(self.delete_url, {'post': 'yes'})
        self.assertEqual(r.status_code, 403)
