import simplejson, urllib2, gio
from glib import GError

class CardapioPlugin(CardapioPluginInterface):

	author             = 'Thiago Teixeira'
	name               = _('Google plugin')
	description        = _('Perform quick Google searches')

	url                = ''
	help_text          = ''
	version            = '1.2'

	plugin_api_version = 1.2

	search_delay_type  = 'remote search update delay'

	category_name      = _('Web Results')
	category_icon      = 'system-search'
	category_position  = 'end'
	hide_from_sidebar  = True


	def __init__(self, settings, write_to_log, cardapio_result_handler, cardapio_error_handler):

		# The google search API only supports two sizes for the result list,
		# that is: small (4 results) or large (8 results). So this plugin
		# chooses the most appropriate given the 'search results limit' user
		# preference.

		if settings['search results limit'] >= 8:
			self.query_url = r'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz=large&q=%s'
		else:
			self.query_url = r'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz=small&q=%s'

		self.cardapio_result_handler = cardapio_result_handler
		self.cardapio_error_handler = cardapio_error_handler
		self.search_controller = gio.Cancellable()

		self.action_command = r"xdg-open 'http://www.google.com/search?q=%s'"
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
			write_to_log(self, 'Error launching plugin action.')
			write_to_log(self, e)			


