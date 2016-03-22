# Copyright 2016 Splunk, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"): you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

'''
This module contains a http request wrapper.
'''

import ssl
import urllib
import urllib2
import logging

from splunksolutionlib.credentials import CredentialManager
from splunksolutionlib.credentials import CredNotExistException
from splunksolutionlib.common.codecs import GzipHandler, ZipHandler

__all__ = ['HTTPRequest']


class HTTPRequest(object):
    '''A wrapper of http request.

    This class provides an easy interface to set http authentication
    and http proxy for http request (should be noticed that the http
    authentication and proxy credential need to be fetched from splunk
    password storage, need to provide the user names of http authentication
    and proxy).

    :param session_key: Splunk access token.
    :type session_key: ``string``
    :param app: App name of namespace.
    :type app: ``string``
    :param owner: (optional) Owner of namespace.
    :type owner: ``string``
    :param scheme: (optional) The access scheme, default is `https`.
    :type scheme: ``string``
    :param host: (optional) The host name, default is `localhost`.
    :type host: ``string``
    :param port: (optional) The port number, default is 8089.
    :type port: ``integer``
    :param realm: (optional) Realm for `api_user` and `proxy_user` if
        credentials stored in splunk with realm.
    :type realm: ``string``
    :param api_user: (optional) User for http authentication, make sure
        the password has been stored in splunk password storage.
    :type api_user: ``string``
    :param proxy_server: (optional) Proxy server ip.
    :type proxy_server: ``string``
    :param proxy_port: (optional) Proxy server port.
    :type proxy_port: ``integer``
    :param proxy_user: (optional) User for http proxy authentication.
    :type proxy_user: ``string``
    :param timeout: (optional) Http request timeout.
    :type timeout: ``integer``

    Usage::

       >>> from splunksolutionlib import http_request
       >>> hq = http_request.HTTPRequest(session_key, 'Splunk_TA_test',
                                         realm='realm_test', api_user='admin',
                                         proxy_server='192.168.1.120',
                                         proxy_port=8000, proxy_user='user1',
                                         timeout=20)
       >>> content = hq.open('http://host:port/namespace/endpoint',
                             body={'key1': kv1},
                             headers={'h1': hv1})
    '''

    DEFAULT_TIMEOUT = 30

    def __init__(self, session_key, app, owner='nobody',
                 scheme='https', host='localhost', port=8089, **options):
        # Splunk credential realm
        realm = options.get('realm')

        cred_manager = CredentialManager(session_key, app, owner, realm,
                                         scheme, host, port)

        # Http authentication args
        self._api_user = options.get('api_user')
        if self._api_user:
            try:
                self._api_password = cred_manager.get_password(self._api_user)
            except CredNotExistException:
                logging.error('API user: %s credential could not be found.' %
                              self._api_user)
                raise
        else:
            self._api_password = None

        # Http proxy handler
        proxy_server = options.get('proxy_server')
        proxy_port = options.get('proxy_port')
        proxy_user = options.get('proxy_user')
        if proxy_user:
            try:
                proxy_password = cred_manager.get_password(proxy_user)
            except CredNotExistException:
                logging.error('Proxy user: %s credential could not be found.' %
                              proxy_user)
                raise
        else:
            proxy_password = None
        self._proxy_handler = self._get_proxy_handler(
            proxy_server, proxy_port, proxy_user, proxy_password)

        # Https handlers
        self._https_handler = urllib2.HTTPSHandler(
            context=ssl._create_unverified_context())

        # Http request timeout
        self._timeout = options.get('timeout', self.DEFAULT_TIMEOUT)

    def _get_proxy_handler(self, proxy_server, proxy_port, proxy_user,
                           proxy_password):
        proxy_setting = None
        if proxy_server and proxy_port and proxy_user and proxy_password:
            proxy_setting = 'http://{user}:{password}@{server}:{port}'.format(
                user=proxy_user, password=proxy_password,
                server=proxy_server, port=proxy_port)
        elif proxy_server is not None and proxy_port is not None:
            proxy_server = 'http://{server}:{port}'.format(
                server=proxy_server, port=proxy_port)
        elif proxy_server or proxy_port or proxy_user or proxy_password:
            logging.error('Invalid proxy settings.')

        if proxy_setting:
            return urllib2.ProxyHandler({'http': proxy_server,
                                         'https': proxy_server})
        return None

    def _build_opener(self, url):
        http_handlers = []

        # HTTPS connection handling
        http_handlers.append(self._https_handler)

        # Proxy handling
        if self._proxy_handler:
            http_handlers.append(self._proxy_handler)

        # HTTP auth handling
        if self._api_user and self._api_password:
            http_pwd_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
            http_pwd_mgr.add_password(None, url, self._api_user, self._api_password)
            http_basicauth_handler = urllib2.HTTPBasicAuthHandler(http_pwd_mgr)
            http_digestauth_handler = urllib2.HTTPDigestAuthHandler(http_pwd_mgr)
            http_handlers.extend([http_basicauth_handler, http_digestauth_handler])

        return urllib2.build_opener(*http_handlers)

    def _format_output(self, output):
        if GzipHandler.check_format(output):
            return GzipHandler.decompress(output)
        elif ZipHandler.check_format(output):
            return ZipHandler.decompress(output)
        else:
            return output

    def send(self, url, body=None, headers=None):
        '''Send a http request, if body is None will select GET
        method else select POST method.

        :param url: Http request url.
        :type url: ``string``
        :param body: (optional) Http post body.
        :type body: ``(dict, string)``
        :param headers: (optional) Http request headers
        :type headers: ``dict``
        :returns: Http request response body.
        :rtype: ``(bytes, string)``
        '''

        if isinstance(body, dict):
            body = urllib.urlencode(body)

        args = {}
        if body:
            args['data'] = body
        if headers:
            headers['headers'] = headers
        opener = self._build_opener(url)
        request = urllib2.Request(url, **args)
        response = opener.open(request, timeout=self._timeout)
        content = response.read()
        return self._format_output(content)
