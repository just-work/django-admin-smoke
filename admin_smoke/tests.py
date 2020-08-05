from datetime import timedelta
from typing import (Any, TypeVar, Type, Union, Optional, Iterable,
                    cast, Dict, List, TYPE_CHECKING, ClassVar)

from django.contrib.admin import ModelAdmin, site
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import AutoField
from django.db.models.fields.files import FieldFile
from django.db.models.options import Options
from django.forms import MultiWidget
from django.forms.models import ModelForm
from django.forms.utils import ErrorList
from django.http.response import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_testing_utils.mixins import BaseTestCase  # type: ignore

try:
    from django.utils.decorators import classproperty
except ImportError:
    # Django-3.1+
    from django.utils.functional import classproperty  # type: ignore

second = timedelta(seconds=1)

M = TypeVar('M', bound=models.Model)


class AdminBaseTestCase(BaseTestCase):
    """ Base class for django admin smoke tests."""
    model_admin: ClassVar[Type[ModelAdmin]]
    model: ClassVar[Type[models.Model]]
    object_name: ClassVar[str]
    excluded_fields: ClassVar[List[str]] = []
    # model fields omitted in model admin

    changelist_url: str
    add_url: str
    admin: ModelAdmin

    @classproperty
    def opts(self) -> Options:
        return self.model._meta

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.superuser = get_user_model().objects.create_superuser(
            username='admin', email='admin@gmail.com', password='admin_admin')
        cls.admin = cls.model_admin(cls.model, site)
        cls.changelist_url = reverse(
            f'admin:{cls.opts.app_label}_{cls.opts.model_name}_changelist')
        cls.add_url = reverse(
            f'admin:{cls.opts.app_label}_{cls.opts.model_name}_add')

    def setUp(self) -> None:
        super().setUp()
        self.client.login(username='admin', password='admin_admin')

    @staticmethod
    def reset_inline_data(data: dict, prefix: str, related: Optional[str],
                          pk: str = 'id') -> None:
        """ Transforms saved records in formsets to new ones.

        :param data: form data dictionary
        :param prefix: inline formset prefix
        :param related: name of inline model ForeignKey field pointing to
            edited object (None for GenericInlineModelAdmin)
        :param pk: name of inline model primary key field
        """
        i = 0
        try:
            while True:
                del data[f'{prefix}-{i}-{pk}']
                if related is not None:
                    del data[f'{prefix}-{i}-{related}']
                i += 1
        except KeyError:
            pass
        data[f'{prefix}-INITIAL_FORMS'] = 0

    @property
    def change_url(self) -> str:
        """ Admin object edit page url."""
        return reverse(
            f'admin:{self.opts.app_label}_{self.opts.model_name}_change',
            kwargs={'object_id': self.get_object().pk})

    @property
    def delete_url(self) -> str:
        """ Admin delete confirmation page url."""
        return reverse(
            f'admin:{self.opts.app_label}_{self.opts.model_name}_delete',
            kwargs={'object_id': self.get_object().pk})

    def get_object(self) -> models.Model:
        """ Get tested object."""
        return getattr(self, self.object_name)

    def transform_to_new(self, data: dict) -> dict:
        """
        Method modifies admin form data to look like a valid new object.
        """
        raise NotImplementedError()

    def prepare_deletion(self) -> None:
        """
        Prepares an object for deletion to exclude errors caused by
        on_delete=PROTECT.
        """
        pass

    @staticmethod
    def get_form_data(form: ModelForm) -> Dict[str, Any]:
        """ Get initial request data from form."""
        initial = form.initial.copy()
        data = {}
        if hasattr(form, 'instance') and form.instance:
            model = form._meta.model  # type: ignore
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
                _meta = form._meta.model._meta  # type: ignore
                model_field: AutoField = _meta.get_field(k)
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

    def get_form_data_from_response(self, r: HttpResponse) -> Dict[str, Any]:
        """ Get form data from response context."""
        data = {'_continue': 'save and continue'}
        cd = getattr(r, 'context_data')
        form: ModelForm = cd['adminform'].form
        data.update(self.get_form_data(form))
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
    def get_errors_from_response(r: HttpResponse) -> Dict[str, ErrorList]:
        """ Get error list from response context."""
        data: Dict[str, ErrorList] = {}
        if r.status_code == 302:
            return data
        cd = getattr(r, 'context_data')
        form: ModelForm = cd['adminform'].form
        data.update(form.errors)
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


if TYPE_CHECKING:  # pragma: no cover
    CommonAdminTestsTarget = AdminBaseTestCase
else:
    CommonAdminTestsTarget = object


# noinspection PyAbstractClass
class CommonAdminTests(CommonAdminTestsTarget):
    """ Common smoke tests for django admin."""

    def test_changelist(self) -> None:
        """ Object list ist rendered correctly."""
        url = self.changelist_url
        count = self.model.objects.count()
        self.assert_row_count(url, count)

    def assert_row_count(self, url: str,
                         count: int) -> None:
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        text = r.content.decode('utf-8')
        if count == 1:
            n = self.opts.verbose_name
        else:
            n = self.opts.verbose_name_plural
        if self.admin.list_editable and count:
            save = (' <input type="submit" name="_save" '
                    'class="default" value="%s">' % _("Save"))
        else:
            save = ''
        marker = f'<p class="paginator">{count} {n}{save}</p>'
        self.assertInHTML(marker, text)
        return text

    def post_changeform(self, create: bool = False,
                        erase: Union[None, str, Iterable[str]] = None,
                        fields: Optional[Dict[str, Any]] = None
                        ) -> Union[HttpResponseRedirect, HttpResponse]:
        """
        Fetches form data from change view and performs POST request.

        :param create: New object creation flag. Transforms existing form data
            to valid data for a new object, makes POST request to "add" url.
        :param erase: Erase form data from request. Accepts '__all__' or a list
            of form field names.
        :param fields: New fields values.
        :return: POST response.
        """
        r = self.client.get(self.change_url)
        data = self.get_form_data_from_response(r)
        if create:
            url = self.add_url
            data = self.transform_to_new(data)
        else:
            url = self.change_url
        # clear form fields, preserving only django formset management form
        if erase:
            for k in list(data):
                if '_FORMS' in k:
                    # skip management fields
                    continue
                if k in erase or erase == '__all__':
                    data.pop(k)
        # set new fields values
        if fields:
            data.update(fields)
        return self.client.post(url, data=data)

    def test_changeform_view(self) -> None:
        """ Add object page opens correctly."""
        r = self.client.get(self.add_url)
        self.assertEqual(r.status_code, 200)

    def test_changeform_save(self) -> None:
        """ Save same existing object works."""
        self.now += second
        r = self.post_changeform()
        self.assertFalse(self.get_errors_from_response(r))
        self.assertEqual(r.status_code, 302)

        obj = self.get_object()
        if hasattr(obj, 'modified'):
            # check whether TimeStampedModel.modified timestamp has changed
            self.assert_object_fields(obj, modified=self.now)

    def test_changeform_create(self) -> None:
        """ New object created correctly."""
        c = self.model.objects.count()
        self.now += second

        r = self.post_changeform(create=True)
        self.assertFalse(self.get_errors_from_response(r))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.model.objects.count(), c + 1)
        obj = cast(models.Model,
                   self.model.objects.order_by(self.opts.pk.name).last())
        if hasattr(obj, 'created'):
            # checks TimeStampModel.created timestamp
            self.assertEqual(obj.created, self.now)  # type: ignore

    def test_all_fields_present(self) -> None:
        """ All not excluded fields are present on the form. """
        r = self.client.get(self.change_url)
        cd = getattr(r, 'context_data')
        form: ModelForm = cd['adminform'].form
        model_fields = {f.name for f in self.opts.fields
                        if f.name not in self.excluded_fields
                        and not f.primary_key and f.editable}
        form_fields = set(form.Meta.fields)
        absent_fields = model_fields - form_fields
        self.assertFalse(absent_fields,
                         f'fields {list(absent_fields)} are absent on form.')

    def test_delete(self) -> None:
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

    def test_empty_changelist(self) -> None:
        """
        Empty object list rendered correctly.
        """
        self.prepare_deletion()
        self.model.objects.all().delete()
        url = self.changelist_url
        count = 0
        self.assert_row_count(url, count)


# noinspection PyAbstractClass
class AdminTests(CommonAdminTests):
    """ smoke tests for full-functional django admin."""

    def test_changeform_create_without_data(self) -> None:
        """
        Creating new object without required fields returns proper response
        with error list.
        """
        r = self.post_changeform(create=True, erase='__all__')
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(self.get_errors_from_response(r))


# noinspection PyAbstractClass
class ReadOnlyAdminTests(CommonAdminTests):
    """ smoke tests for readonly django admin."""

    def test_changeform_view(self) -> None:
        """
        New object admin page returns access denied.
        """
        r = self.client.get(self.add_url)
        self.assertEqual(r.status_code, 403)

    def test_changeform_create(self) -> None:
        """
        POST to create admin view is denied.
        """
        r = self.client.get(self.change_url)
        data = self.get_form_data_from_response(r)
        data = self.transform_to_new(data)

        r = self.client.post(self.add_url, data=data)

        self.assertEqual(r.status_code, 403)

    def test_changeform_save(self) -> None:
        """
        Object changing is denied.
        """
        r = self.client.get(self.change_url)
        data = self.get_form_data_from_response(r)

        r = self.client.post(self.change_url, data=data)

        self.assertEqual(r.status_code, 403)

    def test_delete(self) -> None:
        """
        Object deletion is denied.
        """
        self.prepare_deletion()
        r = self.client.post(self.delete_url, {'post': 'yes'})
        self.assertEqual(r.status_code, 403)
