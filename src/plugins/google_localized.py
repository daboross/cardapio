import simplejson, urllib2, gio
from locale import getdefaultlocale
from glib import GError

class CardapioPlugin(CardapioPluginInterface):

	author             = 'Thiago Teixeira'
	name               = _('Google localized results')
	description        = _("Perform quick Google searches <b>limited to</b> the system's default language")

	url                = ''
	help_text          = ''
	version            = '1.2'

	plugin_api_version = 1.2

	search_delay_type  = 'remote search update delay'

	category_name      = _('Localized Web Results')
	category_icon      = 'system-search'
	category_tooltip  = _('Results found with Google in you system language')
	hide_from_sidebar  = True


	def __init__(self, settings, write_to_log, cardapio_result_handler, cardapio_error_handler):

		language, encoding = getdefaultlocale()
		google_results_language_format = language.split('_')[0]
		google_interface_language_format = language.replace('_', '-')

		# fix codes to match those at http://sites.google.com/site/tomihasa/google-language-codes

		if google_interface_language_format[:2] == 'en':
			google_interface_language_format = 'en'

		if google_interface_language_format == 'pt':
			google_interface_language_format = 'pt-PT'

		if google_interface_language_format == 'zh-HK':
			google_interface_language_format = 'zh-CN'

		if google_interface_language_format[:2] == 'zh':
			google_results_language_format = google_interface_language_format


		# The google search API only supports two sizes for the result list,
		# that is: small (4 results) or large (8 results). So this plugin
		# chooses the most appropriate given the 'search results limit' user
		# preference.

		if settings['search results limit'] >= 8:
			self.query_url = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz=large&lr=lang_%s&q=%%s' % google_results_language_format
		else:
			self.query_url = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz=small&lr=lang_%s&q=%%s' % google_results_language_format

		self.cardapio_result_handler = cardapio_result_handler
		self.cardapio_error_handler = cardapio_error_handler
		self.search_controller = gio.Cancellable()

		self.action_command = "xdg-open 'http://www.google.com/search?q=%%s&hl=%s&lr=lang_%s'" % (google_interface_language_format, google_results_language_format)
		self.action = {
			'name'      : _('Show additional results'),
			'tooltip'   : _('Show additional search results in your web browser'),
			'icon name' : 'system-search',
			'type'      : 'callback',
			'command'   : self.more_results_action,
			}

		self.loaded = True


	def search(self, text):

		# TODO: I'm sure this is not the best way of doing remote procedure
		# calls, but I can't seem to find anything that is this easy to use and
		# compatible with gtk. Argh :(

		# TODO: we should really check if there's an internet connection before
		# proceeding...

		text = urllib2.quote(text)

		query = self.query_url % text
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
			self.cardapio_error_handler(self, 'no response')
			return

		raw_results = simplejson.loads(response)

		parsed_results = [] 

		if 'Error' in raw_results:
			self.cardapio_error_handler(self, raw_results['Error'])
			return
		
		for raw_result in raw_results['responseData']['results']:

			item = {
				'name'      : raw_result['titleNoFormatting'],
				'tooltip'   : raw_result['url'],
				'icon name' : 'text-html',
				'type'      : 'xdg',
				'command'   : raw_result['url'],
				}
			parsed_results.append(item)

		if raw_results:
			parsed_results.append(self.action)

		self.cardapio_result_handler(self, parsed_results)


	def more_results_action(self, text):

		text = text.replace("'", r"\'")
		text = text.replace('"', r'\"')

		try:
			subprocess.Popen(self.action_command % text, shell = True)
		except OSError, e:
			write_to_log(self, 'Error launching plugin action.', is_error = True)
			write_to_log(self, e, is_error = True)


