from __future__ import absolute_import

import re
import django
import docker
try:
    from urllib.request import pathname2url
    from urllib.parse import urljoin
except ImportError:  # Python2
    from urllib import pathname2url
    from urlparse import urljoin

from tempfile import NamedTemporaryFile
from django.utils.encoding import smart_text
from django.conf import settings
from django.template import loader

from django.template.context import Context, RequestContext
from django.utils import six


NO_ARGUMENT_OPTIONS = ['--collate', '--no-collate', '-H', '--extended-help', '-g',
                       '--grayscale', '-h', '--help', '--htmldoc', '--license', '-l',
                       '--lowquality', '--manpage', '--no-pdf-compression', '-q',
                       '--quiet', '--read-args-from-stdin', '--readme',
                       '--use-xserver', '-V', '--version', '--dump-default-toc-xsl',
                       '--outline', '--no-outline', '--background', '--no-background',
                       '--custom-header-propagation', '--no-custom-header-propagation',
                       '--debug-javascript', '--no-debug-javascript', '--default-header',
                       '--disable-external-links', '--enable-external-links',
                       '--disable-forms', '--enable-forms', '--images', '--no-images',
                       '--disable-internal-links', '--enable-internal-links', '-n',
                       '--disable-javascript', '--enable-javascript', '--keep-relative-links',
                       '--load-error-handling', '--load-media-error-handling',
                       '--disable-local-file-access', '--enable-local-file-access',
                       '--exclude-from-outline', '--include-in-outline', '--disable-plugins',
                       '--enable-plugins', '--print-media-type', '--no-print-media-type',
                       '--resolve-relative-links', '--disable-smart-shrinking',
                       '--enable-smart-shrinking', '--stop-slow-scripts',
                       '--no-stop-slow-scripts', '--disable-toc-back-links',
                       '--enable-toc-back-links', '--footer-line', '--no-footer-line',
                       '--header-line', '--no-header-line', '--disable-dotted-lines',
                       '--disable-toc-links', '--verbose']


def htmltopdf(pages, output=None, **kwargs):
    """
    Converts html to PDF.
    example usage:
        wkhtmltopdf(pages=['/tmp/example.html'])
    """
    client = docker.from_env()
    vol = {'/tmp': {'bind': '/converted/', 'mode': 'rw'}}
    command = "athenapdf {convert} ./out.pdf".format(convert=pages[0].replace('/tmp/', './'))
    try:
        image = client.images.get('arachnysdocker/athenapdf')
    except docker.errors.ImageNotFound:

        image = client.images.pull('arachnysdocker/athenapdf')
    try:
        client.containers.get('athenahtmltopdf').remove()
    except docker.errors.NotFound:
        pass
    out = client.containers.run(image, command=command, volumes=vol, name="athenahtmltopdf")
    client.containers.get('athenahtmltopdf').remove()
    f = open('/tmp/out.pdf', 'rb')
    a = f.read()
    f.close()
    return a


def convert_to_pdf(filename, header_filename=None, footer_filename=None, cmd_options=None, cover_filename=None):
    # Clobber header_html and footer_html only if filenames are
    # provided. These keys may be in self.cmd_options as hardcoded
    # static files.
    cmd_options = cmd_options if cmd_options else {}
    if cover_filename:
        pages = [cover_filename, filename]
        cmd_options['has_cover'] = True
    else:
        pages = [filename]

    if header_filename is not None:
        cmd_options['header_html'] = header_filename
    if footer_filename is not None:
        cmd_options['footer_html'] = footer_filename
    return htmltopdf(pages=pages, **cmd_options)


class RenderedFile(object):
    """
    Create a temporary file resource of the rendered template with context.
    The filename will be used for later conversion to PDF.
    """
    temporary_file = None
    filename = ''

    def __init__(self, template, context, request=None):
        debug = getattr(settings, 'DEBUG', settings.DEBUG)

        self.temporary_file = render_to_temporary_file(
            template=template,
            context=context,
            request=request,
            prefix='htmltopdf', suffix='.html',
            delete=(not debug)
        )
        self.filename = self.temporary_file.name

    def __del__(self):
        # Always close the temporary_file on object destruction.
        if self.temporary_file is not None:
            self.temporary_file.close()


def render_pdf_from_template(input_template, header_template, footer_template, context, request=None, cmd_options=None,
                             cover_template=None):
    # For basic usage. Performs all the actions necessary to create a single
    # page PDF from a single template and context.
    cmd_options = cmd_options if cmd_options else {}

    header_filename = footer_filename = None

    # Main content.
    input_file = RenderedFile(
        template=input_template,
        context=context,
        request=request
    )

    # Optional. For header template argument.
    if header_template:
        header_file = RenderedFile(
            template=header_template,
            context=context,
            request=request
        )
        header_filename = header_file.filename

    # Optional. For footer template argument.
    if footer_template:
        footer_file = RenderedFile(
            template=footer_template,
            context=context,
            request=request
        )
        footer_filename = footer_file.filename
    cover = None
    if cover_template:
        cover = RenderedFile(
            template=cover_template,
            context=context,
            request=request
        )

    return convert_to_pdf(filename=input_file.filename,
                          header_filename=header_filename,
                          footer_filename=footer_filename,
                          cmd_options=cmd_options,
                          cover_filename=cover.filename if cover else None)


def content_disposition_filename(filename):
    """
    Sanitize a file name to be used in the Content-Disposition HTTP
    header.

    Even if the standard is quite permissive in terms of
    characters, there are a lot of edge cases that are not supported by
    different browsers.

    See http://greenbytes.de/tech/tc2231/#attmultinstances for more details.
    """
    filename = filename.replace(';', '').replace('"', '')
    return http_quote(filename)


def http_quote(string):
    """
    Given a unicode string, will do its dandiest to give you back a
    valid ascii charset string you can use in, say, http headers and the
    like.
    """
    if isinstance(string, six.text_type):
        try:
            import unidecode
        except ImportError:
            pass
        else:
            string = unidecode.unidecode(string)
        string = string.encode('ascii', 'replace')
    # Wrap in double-quotes for ; , and the like
    string = string.replace(b'\\', b'\\\\').replace(b'"', b'\\"')
    return '"{0!s}"'.format(string.decode())


def pathname2fileurl(pathname):
    """Returns a file:// URL for pathname. Handles OS-specific conversions."""
    return urljoin('file:', pathname2url(pathname))


def make_absolute_paths(content):
    """Convert all MEDIA files into a file://URL paths in order to
    correctly get it displayed in PDFs."""
    overrides = [
        {
            'root': settings.MEDIA_ROOT,
            'url': settings.MEDIA_URL,
        },
        {
            'root': settings.STATIC_ROOT,
            'url': settings.STATIC_URL,
        }
    ]
    has_scheme = re.compile(r'^[^:/]+://')

    for x in overrides:
        if not x['url'] or has_scheme.match(x['url']):
            continue

        if not x['root'].endswith('/'):
            x['root'] += '/'

        occur_pattern = '''["|']({0}.*?)["|']'''
        occurences = re.findall(occur_pattern.format(x['url']), content)
        occurences = list(set(occurences))  # Remove dups
        for occur in occurences:
            content = content.replace(occur,
                                      pathname2fileurl(x['root']) +
                                      occur[len(x['url']):])
    return content


def render_to_temporary_file(template, context, request=None, mode='w+b',
                             bufsize=-1, suffix='.html', prefix='tmp',
                             dir=None, delete=True):
    try:
        if django.VERSION < (1, 8):
            # If using a version of Django prior to 1.8, ensure ``context`` is an
            # instance of ``Context``
            if not isinstance(context, Context):
                if request:
                    context = RequestContext(request, context)
                else:
                    context = Context(context)
            # Handle error when ``request`` is None
            content = template.render(context)
        else:
            content = template.render(context, request)
    except AttributeError:
        content = loader.render_to_string(template, context)
    content = smart_text(content)
    content = make_absolute_paths(content)

    try:
        # Python3 has 'buffering' arg instead of 'bufsize'
        tempfile = NamedTemporaryFile(mode=mode, buffering=bufsize,
                                      suffix=suffix, prefix=prefix,
                                      dir=dir, delete=delete)
    except TypeError:
        tempfile = NamedTemporaryFile(mode=mode, bufsize=bufsize,
                                      suffix=suffix, prefix=prefix,
                                      dir=dir, delete=delete)

    try:
        tempfile.write(content.encode('utf-8'))
        tempfile.flush()
        return tempfile
    except:
        # Clean-up tempfile if an Exception is raised.
        tempfile.close()
        raise
