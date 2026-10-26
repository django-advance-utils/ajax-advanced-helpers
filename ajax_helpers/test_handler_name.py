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
    """``(name, kind)`` of the handler ``view`` dispatched ``request`` to, or None if it named none."""
    view.as_view()(request)
    if not hasattr(request, 'ajax_handler'):
        return None
    return request.ajax_handler, request.ajax_handler_kind


def upload_request(upload='drawing', index='0'):
    return RequestFactory().post(
        '/',
        data={
            'ajax_modal_file': SimpleUploadedFile('a.pdf', b'x'),
            'upload': upload,
            'index': index,
            'file_info': json.dumps([{'name': 'a.pdf', 'size': 1}]),
        },
        headers=AJAX,
    )


class SaveBothWays(PageView):
    """A method reached two ways: as the ``button`` command ``save`` and as an ``@ajax_method``."""

    @ajax_method
    def button_save(self, **kwargs):
        return JsonResponse([], safe=False)


class WrappedRequest:
    """Stands in for a wrapper of the request, as a REST framework ``Request`` is."""

    def __init__(self, request):
        self._request = request

    def __getattr__(self, name):
        return getattr(self._request, name)


class HandlerNameTests(SimpleTestCase):
    def test_a_command_is_named_by_its_prefix_and_name(self):
        self.assertEqual(handler_of(PageView, json_request({'button': 'approve'})), ('button_approve', 'button'))
        self.assertEqual(handler_of(PageView, json_request({'tooltip': 'help'})), ('tooltip_help', 'tooltip'))

    def test_a_prefix_a_view_adds_is_named_the_same_way(self):
        self.assertEqual(handler_of(PageView, json_request({'toggle': 'flag'})), ('toggle_flag', 'toggle'))

    def test_an_ajax_method_is_named_by_the_method(self):
        self.assertEqual(handler_of(PageView, json_request({'ajax_method': 'save'})), ('save', 'ajax_method'))

    def test_one_method_reached_two_ways_is_one_handler_and_the_kind_says_which_way(self):
        # The name is the method that ran, so coverage of it is the same either way; the kind keeps the routes apart.
        self.assertEqual(handler_of(SaveBothWays, json_request({'button': 'save'})), ('button_save', 'button'))
        self.assertEqual(
            handler_of(SaveBothWays, json_request({'ajax_method': 'button_save'})), ('button_save', 'ajax_method')
        )

    def test_a_form_is_named_by_its_form_id(self):
        request = RequestFactory().post('/', data={'form_id': 'contact'}, headers=AJAX)
        self.assertEqual(handler_of(FormView, request), ('form_contact', 'form'))

    def test_a_file_upload(self):
        request = RequestFactory().post('/', data={'ajax_file': SimpleUploadedFile('a.csv', b'x')}, headers=AJAX)
        self.assertEqual(handler_of(FileView, request), ('file_upload', 'file_upload'))

    def test_an_upload_is_named_by_its_upload(self):
        self.assertEqual(handler_of(UploadView, upload_request()), ('upload_drawing', 'upload'))

    def test_an_upload_whose_arguments_cannot_be_read_names_nothing(self):
        # An index past the files raises before the handler is called: it did not run.
        request = upload_request(index='5')
        with self.assertRaises(IndexError):
            UploadView.as_view()(request)
        self.assertFalse(hasattr(request, 'ajax_handler'))

    def test_the_name_goes_on_the_request_a_wrapper_wraps(self):
        # A middleware sees the HttpRequest, not the wrapper a view may have been handed.
        request = json_request({'button': 'approve'})
        view = PageView()
        view.setup(request)
        view.post(WrappedRequest(request))
        self.assertEqual((request.ajax_handler, request.ajax_handler_kind), ('button_approve', 'button'))

    def test_a_post_no_handler_answers_names_nothing(self):
        # A command the view has no method for falls through to the view's own post, as before.
        request = json_request({'button': 'missing'})
        response = PageView.as_view()(request)
        self.assertEqual(json.loads(response.content), {'fell_through': True})
        self.assertFalse(hasattr(request, 'ajax_handler'))

    def test_a_form_or_upload_with_no_such_handler_names_nothing(self):
        # The lookup fails as it always did; the name of a handler that does not exist is not recorded on the way.
        form = RequestFactory().post('/', data={'form_id': 'missing'}, headers=AJAX)
        with self.assertRaises(AttributeError):
            FormView.as_view()(form)
        self.assertFalse(hasattr(form, 'ajax_handler'))
        upload = upload_request(upload='missing')
        with self.assertRaises(AttributeError):
            UploadView.as_view()(upload)
        self.assertFalse(hasattr(upload, 'ajax_handler'))

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
