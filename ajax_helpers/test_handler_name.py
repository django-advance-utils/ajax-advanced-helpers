"""The handler a request was dispatched to, named on the request as ``request.ajax_handler``."""

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.views import View

from .mixins import AjaxFileHelpers, AjaxFileUploadMixin, AjaxHelpers, ReceiveForm, ajax_method

AJAX = {'x-requested-with': 'XMLHttpRequest'}
REFUSE_ALL = 'ajax_helpers.test_handler_name.refuse_all'


def refuse_all(request, kind, name, obj=None):
    return False


class FallThrough(View):
    """What a post no handler answers reaches: the view's own ``post``."""

    def post(self, request, *args, **kwargs):
        return JsonResponse({'fell_through': True})


class PageView(AjaxHelpers, FallThrough):
    ajax_commands = ['toggle']

    def button_approve(self, **kwargs):
        return JsonResponse([], safe=False)

    def tooltip_help(self, **kwargs):
        return JsonResponse([], safe=False)

    def toggle_flag(self, **kwargs):
        return JsonResponse([], safe=False)

    @ajax_method
    def save(self, **kwargs):
        return JsonResponse([], safe=False)


class FormView(ReceiveForm, View):
    def form_contact(self, **kwargs):
        return JsonResponse([], safe=False)


class FileView(AjaxFileHelpers, View):
    @staticmethod
    def file_upload(file):
        return JsonResponse({'file': 'ok'})


class UploadView(AjaxFileUploadMixin, AjaxHelpers, View):
    def upload_drawing(self, *args, **kwargs):
        pass

    def upload_completed(self):
        return JsonResponse([], safe=False)


def json_request(data):
    return RequestFactory().post('/', data=json.dumps(data), content_type='application/json', headers=AJAX)


def handler_of(view, request):
    view.as_view()(request)
    return getattr(request, 'ajax_handler', None)


class HandlerNameTests(SimpleTestCase):
    def test_a_command_is_named_by_its_prefix_and_name(self):
        self.assertEqual(handler_of(PageView, json_request({'button': 'approve'})), 'button_approve')
        self.assertEqual(handler_of(PageView, json_request({'tooltip': 'help'})), 'tooltip_help')

    def test_a_prefix_a_view_adds_is_named_the_same_way(self):
        self.assertEqual(handler_of(PageView, json_request({'toggle': 'flag'})), 'toggle_flag')

    def test_an_ajax_method_is_named_by_the_method(self):
        self.assertEqual(handler_of(PageView, json_request({'ajax_method': 'save'})), 'save')

    def test_a_form_is_named_by_its_form_id(self):
        request = RequestFactory().post('/', data={'form_id': 'contact'}, headers=AJAX)
        self.assertEqual(handler_of(FormView, request), 'form_contact')

    def test_a_file_upload(self):
        request = RequestFactory().post('/', data={'ajax_file': SimpleUploadedFile('a.csv', b'x')}, headers=AJAX)
        self.assertEqual(handler_of(FileView, request), 'file_upload')

    def test_an_upload_is_named_by_its_upload(self):
        request = RequestFactory().post(
            '/',
            data={
                'ajax_modal_file': SimpleUploadedFile('a.pdf', b'x'),
                'upload': 'drawing',
                'index': '0',
                'file_info': json.dumps([{'name': 'a.pdf', 'size': 1}]),
            },
            headers=AJAX,
        )
        self.assertEqual(handler_of(UploadView, request), 'upload_drawing')

    def test_a_post_no_handler_answers_names_nothing(self):
        # A command the view has no method for falls through to the view's own post, as before.
        request = json_request({'button': 'missing'})
        response = PageView.as_view()(request)
        self.assertEqual(json.loads(response.content), {'fell_through': True})
        self.assertFalse(hasattr(request, 'ajax_handler'))

    def test_a_get_names_nothing(self):
        request = RequestFactory().get('/', headers=AJAX)
        PageView.as_view()(request)
        self.assertFalse(hasattr(request, 'ajax_handler'))

    @override_settings(DJANGO_ADVANCED_PERMISSION_CHECK=REFUSE_ALL)
    def test_a_refused_handler_is_not_named(self):
        # It did not run, so nothing downstream should count it as having run.
        self.assertIsNone(handler_of(PageView, json_request({'button': 'approve'})))
        self.assertIsNone(handler_of(PageView, json_request({'ajax_method': 'save'})))
        self.assertIsNone(handler_of(FormView, RequestFactory().post('/', data={'form_id': 'contact'}, headers=AJAX)))
