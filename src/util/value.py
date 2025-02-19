import cgi
import urllib.request
import urllib.parse
import urllib.error
import xml.sax.saxutils


def map_not_None(value, function):
	if value is not None:
		return function(value)
	else:
		return None


def select_not_None(*args):
	for arg in args:
		if arg is not None:
			return arg
	return None


def html_input_escape(value):
	return cgi.escape(value, True)


def html_attribute(value):
	return xml.sax.saxutils.quoteattr(value)


def build_url(scheme='', netloc='', path='', query='', fragment=''):
	if not scheme and netloc:
		scheme = 'http'
	try:
		query_str = urllib.parse.urlencode(query)
	except TypeError:
		query_str = urllib.parse.quote(query)
	return urllib.parse.urlunsplit(urllib.parse.SplitResult(scheme=scheme, netloc=netloc, path=path, query=query_str, fragment=fragment))
