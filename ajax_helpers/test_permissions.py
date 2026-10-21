"""Ajax handlers put to the project's permission check (``ajax_helpers.permissions``)."""

import json

from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.views import View

from django.core.files.uploadedfile import SimpleUploadedFile

from .mixins import AjaxFileHelpers, AjaxFileUploadMixin, AjaxHelpers, ReceiveForm, ajax_method

CHECK = 'ajax_helpers.test_permissions.check'

ASKED = []
REFUSED = set()
RAN = []


def check(request, kind, name, obj=None):
    ASKED.append((kind, name))
    return (kind, name) not in REFUSED


class PageView(AjaxHelpers, View):
    def button_approve(self, **kwargs):
        RAN.append('approve')
        return JsonResponse([], safe=False)

    @ajax_method
    def save(self, **kwargs):
        RAN.append('save')
        return JsonResponse([], safe=False)


    def tooltip_help(self, **kwargs):
        RAN.append('help')
        return HttpResponse('<b>help</b>')


class FileView(AjaxFileHelpers, View):
    @staticmethod
    def file_upload(file):
        RAN.append('file_upload')
        return JsonResponse({'file': 'ok'})


class UploadView(AjaxFileUploadMixin, AjaxHelpers, View):
    def upload_drawing(self, *args, **kwargs):
        RAN.append('drawing')

    def upload_completed(self):
        return JsonResponse([], safe=False)


class DecidesItselfView(PageView):
    def check_ajax_permission(self, kind, name):
        return False

    def refuse_ajax(self, kind, name):
        return JsonResponse({'refused': [kind, name]})


class FormView(ReceiveForm, View):
    def form_contact(self, **kwargs):
        RAN.append('contact')
        return JsonResponse([], safe=False)


def post_json(view, data):
    request = RequestFactory().post(
        '/', data=json.dumps(data), content_type='application/json', headers={'x-requested-with': 'XMLHttpRequest'}
    )
    return view.as_view()(request)


class PermissionCheckTestBase(SimpleTestCase):
    def setUp(self):
        ASKED.clear()
        REFUSED.clear()
        RAN.clear()


class WithNoCheckSetTests(PermissionCheckTestBase):
    def test_a_button_runs_as_before_and_nothing_is_asked(self):
        post_json(PageView, {'button': 'approve'})

        self.assertEqual(RAN, ['approve'])
        self.assertEqual(ASKED, [])

    def test_the_hooks_are_not_ajax_handlers(self):
        with self.assertRaises(AttributeError):
            post_json(PageView, {'ajax': 'permission_denied', 'kind': 'button', 'name': 'approve'})


@override_settings(DJANGO_ADVANCED_PERMISSION_CHECK=CHECK)
class WithACheckSetTests(PermissionCheckTestBase):
    def test_an_allowed_button_runs(self):
        post_json(PageView, {'button': 'approve'})

        self.assertEqual(RAN, ['approve'])
        self.assertIn(('button', 'approve'), ASKED)

    def test_a_refused_button_does_not_run_and_says_why(self):
        REFUSED.add(('button', 'approve'))

        response = post_json(PageView, {'button': 'approve'})

        self.assertEqual(RAN, [])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)[0]['function'], 'message')

    def test_a_refused_ajax_method_does_not_run(self):
        REFUSED.add(('ajax_method', 'save'))

        post_json(PageView, {'ajax_method': 'save'})

        self.assertEqual(RAN, [])

    def test_a_refused_form_post_does_not_run(self):
        REFUSED.add(('form', 'contact'))
        request = RequestFactory().post('/', data={'form_id': 'contact'}, headers={'x-requested-with': 'XMLHttpRequest'})

        response = FormView.as_view()(request)

        self.assertEqual(RAN, [])
        self.assertEqual(json.loads(response.content)[0]['function'], 'message')

    def test_a_refused_tooltip_shows_the_message_as_text(self):
        REFUSED.add(('tooltip', 'help'))

        response = post_json(PageView, {'tooltip': 'help'})

        self.assertEqual(RAN, [])
        self.assertEqual(response.content.decode(), 'You do not have permission to do this.')

    def test_a_refused_file_upload_does_not_run(self):
        REFUSED.add(('file_upload', 'ajax_file'))
        request = RequestFactory().post(
            '/', data={'ajax_file': SimpleUploadedFile('a.csv', b'x')}, headers={'x-requested-with': 'XMLHttpRequest'}
        )

        response = FileView.as_view()(request)

        self.assertEqual(RAN, [])
        self.assertEqual(response.status_code, 200)

    def test_a_refused_upload_does_not_run(self):
        REFUSED.add(('upload', 'drawing'))
        request = RequestFactory().post(
            '/',
            data={
                'ajax_modal_file': SimpleUploadedFile('a.pdf', b'x'),
                'upload': 'drawing',
                'index': '0',
                'file_info': json.dumps([{'name': 'a.pdf', 'size': 1}]),
            },
            headers={'x-requested-with': 'XMLHttpRequest'},
        )

        UploadView.as_view()(request)

        self.assertEqual(RAN, [])

    def test_the_check_is_asked_with_the_command_kind_and_handler_name(self):
        post_json(PageView, {'button': 'approve'})

        self.assertEqual(ASKED, [('button', 'approve')])


class AViewThatDecidesItselfTests(PermissionCheckTestBase):
    def test_its_own_check_and_refusal_are_used(self):
        response = post_json(DecidesItselfView, {'button': 'approve'})

        self.assertEqual(RAN, [])
        self.assertEqual(json.loads(response.content), {'refused': ['button', 'approve']})
