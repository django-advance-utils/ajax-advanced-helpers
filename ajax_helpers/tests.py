from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.views.generic import TemplateView

from .mixins import AjaxHelpers
from .utils import is_ajax

INCLUDE = ("{% load ajax_helpers %}"
           "{% lib_include 'ajax_helpers' 'Bootstrap' module='ajax_helpers.includes' %}")


def render_includes():
    return Template(INCLUDE).render(Context({}))


class CssFrameworkIncludeTests(SimpleTestCase):

    def assert_bootstrap4(self, html):
        # jQuery + Popper bundled, Bootstrap 4 served from local static
        self.assertIn('jquery.min.js', html)
        self.assertIn('popper.min.js', html)
        self.assertIn('ajax_helpers.js', html)
        self.assertIn('/static/ajax_helpers/js/bootstrap.min.js', html)
        self.assertIn('/static/ajax_helpers/css/bootstrap.min.css', html)

    def test_default_is_bootstrap4(self):
        self.assert_bootstrap4(render_includes())

    @override_settings(CSS_FRAMEWORK='bootstrap4')
    def test_explicit_bootstrap4(self):
        self.assert_bootstrap4(render_includes())

    @override_settings(CSS_FRAMEWORK='bootstrap5')
    def test_bootstrap5_drops_jquery_and_serves_bs5_from_cdn(self):
        html = render_includes()
        self.assertIn('ajax_helpers.js', html)
        self.assertNotIn('jquery', html)
        self.assertNotIn('popper', html)
        self.assertIn('cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js', html)
        self.assertIn('cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css', html)

    @override_settings(CSS_FRAMEWORK='tailwind')
    def test_unsupported_framework_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            render_includes()


class RequestHeaderTests(SimpleTestCase):
    """is_ajax() routes a request on X-Requested-With, so the client has to send it.

    jQuery added the header to every request it made to its own origin. The client's own fetch and XMLHttpRequest
    calls do not, so without these lines every ajax POST to an AjaxHelpers view got no response. Like jQuery, the
    client leaves the header off a cross-origin request, where it would cost a CORS preflight.
    """

    @staticmethod
    def first_inside(guard, statement):
        """Whether statement is the first line of an `if (guard) {` block in the client's script."""
        js = (Path(__file__).parent / 'static' / 'ajax_helpers' / 'ajax_helpers.js').read_text(encoding='utf-8')
        lines = [line.strip() for line in js.splitlines()]
        return any(lines[i] == f'if ({guard}) {{' and lines[i + 1] == statement for i in range(len(lines) - 1))

    def test_fetch_requests_send_it_to_their_own_origin(self):
        self.assertTrue(self.first_inside('same_origin(config.url)', "headers['X-Requested-With'] = 'XMLHttpRequest';"))

    def test_xhr_requests_send_it_to_their_own_origin(self):
        self.assertTrue(
            self.first_inside('same_origin(url)', "xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');")
        )

    def test_is_ajax_reads_it(self):
        self.assertTrue(is_ajax(RequestFactory().post('/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')))
        self.assertFalse(is_ajax(RequestFactory().post('/')))


class Page(AjaxHelpers, TemplateView):
    """A view with no post of its own above AjaxHelpers, as every template modal is."""

    def button_save(self, **_kwargs):
        return self.command_response('reload')


class UnhandledPostTests(SimpleTestCase):
    """A post nothing on the view handles is answered, not dropped.

    post used to return None for it, and ensure_csrf_cookie (on AjaxHelpers.dispatch) then failed on
    response.set_cookie, so the request was a 500 rather than an answer.
    """

    @staticmethod
    def post(data, **headers):
        return Page.as_view()(RequestFactory().post('/page/', data, **headers))

    def test_a_handled_command_still_runs(self):
        response = self.post({'button': 'save'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'reload', response.content)

    def test_an_ajax_command_with_no_handler_is_a_bad_request(self):
        with self.assertLogs('ajax_helpers.mixins', 'WARNING') as logged:
            response = self.post(
                {'ajax': 'get_details', 'field_id': 'id_colour'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Page has no handler for the post {'ajax': 'get_details'} (/page/)", logged.output[0])

    def test_an_ajax_post_naming_no_command_is_a_bad_request(self):
        with self.assertLogs('ajax_helpers.mixins', 'WARNING'):
            response = self.post({}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)

    def test_a_plain_post_is_not_allowed(self):
        response = self.post({'name': 'x'})
        self.assertEqual(response.status_code, 405)
        self.assertNotIn('POST', response['Allow'])
