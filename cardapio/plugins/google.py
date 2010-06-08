import simplejson, urllib2, gio

if '_' not in locals():
	_ = lambda x: x

class CardapioPlugin(CardapioPluginInterface):

	author             = 'Thiago Teixeira'
	name               = 'Google plugin'
	description        = 'Perform quick Google searches'
	version            = '1.0'

	plugin_api_version = 1.0

	search_delay_type  = 'remote search update delay'

	category_name      = _('Web Results')
	category_icon      = 'system-search'
	hide_from_sidebar  = True


	def __init__(self, settings, cardapio_result_handler, cardapio_error_handler):

		self.query_url = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz=large&q=%s'
		self.timeout = settings['remote search update delay'] * 2
		self.search_results_limit = settings['search results limit']
		self.cardapio_result_handler = cardapio_result_handler
		self.cardapio_error_handler = cardapio_error_handler
		self.search_controller = gio.Cancellable()


	def search(self, text):

		text = urllib2.quote(text)
		self.search_controller.reset()

		self.stream = gio.File(self.query_url % text)
		self.stream.load_contents_async(self.handle_search_result, cancellable = self.search_controller)


	def cancel(self):

		if not self.search_controller.is_cancelled():
			self.search_controller.cancel()

	
	def handle_search_result(self, gdaemonfile = None, response = None):

		response = self.stream.load_contents_finish(response)[0]
		raw_results = simplejson.loads(response)

		parsed_results = [] 

		if 'Error' in raw_results:
			self.cardapio_error_handler(self, raw_results['Error'])
			return
		
		for raw_result in raw_results['responseData']['results']:

			item = {}
			item['name']      = raw_result['titleNoFormatting']
			item['tooltip']   = raw_result['url']
			item['xdg uri']   = raw_result['url']
			item['icon name'] = 'text-html'
			parsed_results.append(item)

		self.cardapio_result_handler(self, parsed_results)

