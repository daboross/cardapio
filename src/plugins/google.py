import simplejson, urllib2, gio
from locale import getdefaultlocale
from glib import GError

class CardapioPlugin(CardapioPluginInterface):

	author             = _('Cardapio Team')
	name               = _('Google')
	description        = _('Perform quick Google searches in <b>all</b> languages')

	url                = ''
	help_text          = ''
	version            = '1.37'

	plugin_api_version = 1.38

	search_delay_type  = 'remote search update delay'

	default_keyword    = 'google'

	category_name      = _('Web Results')
	category_icon      = 'system-search'
	category_tooltip   = _('Results found with Google')
	hide_from_sidebar  = True


	def __init__(self, cardapio_proxy):

		self.c = cardapio_proxy
		
		language, encoding = getdefaultlocale()
		google_interface_language_format = language.replace('_', '-')

		# fix codes to match those at http://sites.google.com/site/tomihasa/google-language-codes

		if google_interface_language_format[:2] == 'en':
			google_interface_language_format = 'en'

		if google_interface_language_format == 'pt':
			google_interface_language_format = 'pt-PT'

		if google_interface_language_format == 'zh-HK':
			google_interface_language_format = 'zh-CN'

		self.query_url = r'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz={0}&q={1}'

		self.search_controller = gio.Cancellable()

		self.action_command = "xdg-open 'http://www.google.com/search?q=%%s&hl=%s'" % google_interface_language_format
		self.action = {
			'name'         : _('Show additional results'),
			'tooltip'      : _('Show additional search results in your web browser'),
			'icon name'    : 'system-search',
			'type'         : 'callback',
			'command'      : self.more_results_action,
			'context menu' : None,
			}

		self.loaded = True


	def search(self, text, result_limit):

		# TODO: I'm sure this is not the best way of doing remote procedure
		# calls, but I can't seem to find anything that is this easy to use and
		# compatible with gtk. Argh :(

		# TODO: we should really check if there's an internet connection before
		# proceeding...

		self.current_query = text
		text = urllib2.quote(text)

		# The google search API only supports two sizes for the result list,
		# that is: small (4 results) or large (8 results). So this plugin
		# chooses the most appropriate given the 'search results limit' user
		# preference.

		query = self.query_url.format('large' if result_limit >= 8 else 'small', text)

		self.stream = gio.File(query)

		self.search_controller.reset()
		self.stream.load_contents_async(self.handle_search_result, cancellable = self.search_controller)


	def cancel(self):

		if not self.search_controller.is_cancelled():
			self.search_controller.cancel()

	
	def handle_search_result(self, gdaemonfile = None, response = None):

		try:
			response = self.stream.load_contents_finish(response)[0]

		except GError, e:
			# no need to worry if there's no response: maybe there's no internet
			# connection...
			self.c.handle_search_error(self, 'no response')
			return

		raw_results = simplejson.loads(response)

		parsed_results = [] 

		if 'Error' in raw_results:
			self.c.handle_search_error(self, raw_results['Error'])
			return
		
		for raw_result in raw_results['responseData']['results']:

			item = {
				'name'         : raw_result['titleNoFormatting'],
				'tooltip'      : raw_result['url'],
				'icon name'    : 'text-html',
				'type'         : 'xdg',
				'command'      : raw_result['url'],
				'context menu' : None,
				}
			parsed_results.append(item)

		if parsed_results:
			parsed_results.append(self.action)

		self.c.handle_search_result(self, parsed_results, self.current_query)


	def more_results_action(self, text):

		text = text.replace("'", r"\'")
		text = text.replace('"', r'\"')

		try:
			subprocess.Popen(self.action_command % text, shell = True)
		except OSError, e:
			self.c.write_to_log(self, 'Error launching plugin action.', is_error = True)
			self.c.write_to_log(self, e, is_error = True)


