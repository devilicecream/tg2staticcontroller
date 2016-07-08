# -*- coding: utf-8 -*-
"""
IN NO EVENT SHALL THE AUTHOR BE LIABLE TO ANY PARTY FOR DIRECT, INDIRECT, SPECIAL, INCIDENTAL,
OR CONSEQUENTIAL DAMAGES, INCLUDING LOST PROFITS, ARISING OUT OF THE USE OF THIS SOFTWARE AND ITS
DOCUMENTATION, EVEN IF REGENTS HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

THE AUTHOR SPECIFICALLY DISCLAIMS ANY WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
THE SOFTWARE AND ACCOMPANYING DOCUMENTATION, IF ANY, PROVIDED HERE UNDER IS PROVIDED "AS IS".
"""
from tg import expose, request, response, redirect, config, TGController
from tg.support.statics import _FileIter, _BLOCK_SIZE, INVALID_PATH_PARTS
from os.path import normcase, normpath, join, isfile, dirname, getmtime, getsize
from webob.exc import HTTPNotFound, HTTPForbidden, HTTPBadRequest, HTTPNotModified
from datetime import datetime
from time import gmtime, time
from email.utils import parsedate_tz, mktime_tz
import mimetypes

mimetypes.init()


class StaticController(TGController):
    """
    A Controller used to serve static files.
    This is more flexible then the TurboGears2 standard way to serve static files,
    because it can be plugged at any given path, and can even be used
    with the authentication and validation systems.
    """
    def _adapt_path(self, path):
        """
        OS independent path normalization
        """
        return normcase(normpath(path))

    def __init__(self, static_path, cache_max_age=3600):
        """
        :param static_path: The path of the static files to serve.
                            Must be relative to the application root module path.
        :param cache_max_age: The max-age value for caching in seconds. Default 3600 (1 hour).
        """
        self.cache_max_age = cache_max_age

        # Get the application path from tg.config
        application_path = self._adapt_path(dirname(config.package.__file__))
        # Use <application_path>/<static_path> as path to serve
        self.static_path = self._adapt_path(join(application_path, static_path))

    @staticmethod
    def make_date(d):
        """
        Makes a ISO Datetime string from a `datetime` or an `int` (representing a timestamp)
        :param d: The `datetime` or `int` timestamp
        :return: The ISO Datetime string
        """
        if isinstance(d, datetime):
            d = d.utctimetuple()
        else:
            d = gmtime(d)

        return '%s, %02d%s%s%s%s %02d:%02d:%02d GMT' % (
            ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[d.tm_wday],
            d.tm_mday, ' ',
            ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
             'Oct', 'Nov', 'Dec')[d.tm_mon - 1],
            ' ', str(d.tm_year), d.tm_hour, d.tm_min, d.tm_sec)

    @staticmethod
    def generate_etag(last_modified, content_length):
        """
        Generates an Etag from the last modified date and the content length of a resource
        :param last_modified: The last modified ISO Datetime string
        :param content_length: The content length of the resource
        :return: The Etag string
        """
        return '"%s-%s"' % (last_modified, content_length)

    @staticmethod
    def parse_date(value):
        """
        Used to parse the HTTP_IF_MODIFIED_SINCE date.
        Raises HTTPBadRequest leading to a 400 page if it fails.
        """
        try:
            return mktime_tz(parsedate_tz(value))
        except (TypeError, OverflowError):
            raise HTTPBadRequest("Received an ill-formed timestamp.\r\n")

    def has_been_modified(self, environ, etag, last_modified):
        """
        Decides wether or not actually serve the file from the filesystem,
        or to send a 304 Unmodified instead.
        :param environ: The TG environ object.
        :param etag: The generated Etag
        :param last_modified: The resource last modified date
        :return: A boolean (True/False)
        """
        if environ['REQUEST_METHOD'] not in ('GET', 'HEAD'):
            return False

        unmodified = False

        modified_since = environ.get('HTTP_IF_MODIFIED_SINCE')
        if modified_since:
            modified_since = self.parse_date(modified_since)
            if last_modified and last_modified <= modified_since:
                unmodified = True

        if_none_match = environ.get('HTTP_IF_NONE_MATCH')
        if if_none_match and etag == if_none_match:
            unmodified = True

        return not unmodified

    @expose()
    def _default(self, *args, **kw):
        """
        Using the _default method to serve the static files.
        :param args: This will be a list of the path parts.
                     The extension of the resource will not be included.
        """
        # Empty path redirects to /index.html
        if not args:
            return redirect(request.environ["PATH_INFO"] + "index.html")
        # Adding security check on path (importing INVALID_PATH_PARTS from tg.support.static)
        if INVALID_PATH_PARTS(args):
            return HTTPNotFound('Out of bounds: %s' % request.environ['PATH_INFO'])
        # Using *args to get the file path
        filepath = self._adapt_path(join(self.static_path, *args))
        # But we don't receive the extension this way, so we get it from the environ["PATH_INFO"]
        extension = request.environ["PATH_INFO"].split(".")
        if len(extension) > 1:
            extension = extension[len(extension)-1]
            filepath += ".%s" % extension

        try:
            last_modified = getmtime(filepath)
            content_length = getsize(filepath)
        except (IOError, OSError):
            return HTTPNotFound()

        if isfile(filepath):
            etag = self.generate_etag(last_modified, content_length)
            headers = [('Etag', '%s' % etag),
                       ('Cache-Control', 'max-age=%d, public' % self.cache_max_age)]
            if not self.has_been_modified(request.environ, etag, last_modified):
                return HTTPNotModified(headers=headers)

            try:
                fp = open(filepath, 'rb')
            except (IOError, OSError, TypeError) as e:
                return HTTPForbidden('You are not permitted to view this file (%s)' % e)

            content_type, content_encoding = mimetypes.guess_type(filepath, strict=False)
            if content_type is None:
                content_type = 'application/octet-stream'

            headers.extend((
                ('Expires', self.make_date(time() + self.cache_max_age)),
                ('Content-Type', content_type),
                ('Content-Length', str(content_length)),
                ('Last-Modified', self.make_date(last_modified)),
                ('Etag', '%s' % etag),
                ('Cache-Control', 'max-age=%d, public' % self.cache_max_age)
            ))
            response.headers.extend(headers)
            return request.environ.get('wsgi.file_wrapper', _FileIter)(fp, _BLOCK_SIZE)
        return HTTPNotFound()
