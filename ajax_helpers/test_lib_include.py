from django.template import Context, Engine
from django.test import SimpleTestCase

from .templatetags.ajax_helpers import lib_include

LOAD = '{% load ajax_helpers %}'
AJAX_HELPERS = "{% lib_include 'ajax_helpers' module='ajax_helpers.includes' %}"
JQUERY = "{% lib_include 'Jquery' module='ajax_helpers.includes' %}"
JQUERY_CDN = "{% lib_include 'Jquery' module='ajax_helpers.includes' cdn=True %}"

TEMPLATES = {
    # The shape of a project's base template: what every page loads, then whatever the view adds.
    'base.html': (
        LOAD + AJAX_HELPERS
        + '{% for extra_include in extra_includes %}'
        + '{% lib_include extra_include.0 module=extra_include.1 %}{% endfor %}'
        + '{% block head %}{% endblock %}'
    ),
    'page.html': "{% extends 'base.html' %}" + LOAD + '{% block head %}' + JQUERY + '{% endblock %}',
    'jquery.html': LOAD + JQUERY,
    'includes.html': "{% include 'jquery.html' %}{% include 'jquery.html' only %}",
}

ENGINE = Engine(
    loaders=[('django.template.loaders.locmem.Loader', TEMPLATES)],
    libraries={'ajax_helpers': 'ajax_helpers.templatetags.ajax_helpers'},
)


def render(name, **context):
    return ENGINE.get_template(name).render(Context(context))


def render_string(source, **context):
    return ENGINE.from_string(LOAD + source).render(Context(context))


def jquery_count(html):
    return html.count('jquery.min.js')


class LibIncludeOncePerRenderTests(SimpleTestCase):

    def test_a_library_asked_for_twice_is_written_once(self):
        self.assertEqual(jquery_count(render_string(JQUERY + JQUERY)), 1)

    def test_a_library_two_packages_share_is_written_once(self):
        """The ajax_helpers package brings Jquery with it. The rest of the package is still written."""
        html = render_string(JQUERY + AJAX_HELPERS)
        self.assertEqual(jquery_count(html), 1)
        self.assertIn('popper.min.js', html)
        self.assertIn('ajax_helpers.js', html)

    def test_a_views_extra_includes_repeating_the_base(self):
        """A base template includes a library on every page, and a view lists the same one in the extra_includes
        the base loops over."""
        html = render('base.html', extra_includes=[('ajax_helpers', 'ajax_helpers.includes')])
        self.assertEqual(jquery_count(html), 1)

    def test_an_extending_template_shares_the_render_with_its_base(self):
        self.assertEqual(jquery_count(render('page.html')), 1)

    def test_included_templates_share_the_render(self):
        """Including with only as well, which gives the included template a new context but not a new render."""
        self.assertEqual(jquery_count(render_string(JQUERY + "{% include 'includes.html' %}")), 1)

    def test_the_first_request_decides_the_cdn(self):
        html = render_string(JQUERY_CDN + JQUERY)
        self.assertEqual(jquery_count(html), 1)
        self.assertIn('https://ajax.googleapis.com/', html)

    def test_the_first_request_decides_the_version(self):
        html = render_string("{% lib_include 'Jquery' module='ajax_helpers.includes' version='1' %}"
                             "{% lib_include 'Jquery' module='ajax_helpers.includes' version='2' %}")
        self.assertEqual(jquery_count(html), 1)
        self.assertIn('jquery.min.js?v=1', html)
        self.assertNotIn('?v=2', html)

    def test_each_render_writes_its_own_libraries(self):
        """A modal body or an ajax response is a separate render, and the page it goes into may not have them."""
        self.assertEqual(jquery_count(render('jquery.html')), 1)
        self.assertEqual(jquery_count(render('jquery.html')), 1)

    def test_a_dict_context_writes_every_request(self):
        """Called from Python with a dict rather than a template's context, there is no render to record anything
        on, so nothing is left out."""
        html = lib_include({}, 'Jquery', module='ajax_helpers.includes')
        html += lib_include({}, 'Jquery', module='ajax_helpers.includes')
        self.assertEqual(jquery_count(html), 2)
