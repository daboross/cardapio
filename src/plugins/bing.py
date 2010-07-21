import json
import gio
import urllib

class CardapioPlugin(CardapioPluginInterface):

	# Cardapio's variables
	author = 'Pawel Bara'
	name = _('Bing')
	description = _('Perform a search using Microsoft\'s Bing')
	version = '0.9b'

	url = ''
	help_text = ''

	plugin_api_version = 1.3

	search_delay_type = 'remote search update delay'

	category_name = _('Bing Results')
	category_tooltip = _('Results found with Bing')

	category_icon = 'system-search'
	fallback_icon = ''

	hide_from_sidebar = True

	def __init__(self, cardapio_proxy):
		cardapio_proxy.write_to_log(self, 'initializing Bing')

		self.cardapio = cardapio_proxy

		self.cancellable = gio.Cancellable()

		# Bing API's arguments
		self.api_base_args = {
			'Appid': '237CBC82BB8C3F7F5F19F6A77B0D38A59E8F8C2C',
			'sources'  : 'web',
			'web.count': 4
		}
		self.api_base_url = 'http://api.search.live.net/json.aspx?{0}'

		# Bing's web base URL (for purposes of 'search more' option)
		self.web_base_url = 'http://www.bing.com/search?q={0}'

		self.loaded = True

	def search(self, text):
		if len(text) == 0:
			return

		self.cardapio.write_to_log(self, 'searching for {0} using Bing'.format(text))

		self.cancellable.reset()

		# prepare final API URL
		current_args = self.api_base_args.copy()
		current_args['query'] = text
		final_url = self.api_base_url.format(urllib.urlencode(current_args))

		self.cardapio.write_to_log(self, 'search URL: {0}'.format(final_url))

		# asynchronous and cancellable IO call
		self.current_stream = gio.File(final_url)
		self.current_stream.load_contents_async(self.show_search_results,
												cancellable = self.cancellable,
												user_data = text)

	def show_search_results(self, gdaemonfile, result, text):
		"""
        Callback to asynchronous IO (Bing API's call).
		"""

		json_body = self.current_stream.load_contents_finish(result)[0]
		response = json.loads(json_body)

		try:
			items = []

			response_body = response['SearchResponse']['Web']

			# if we have any results...
			if response_body['Total'] != 0:
				# remember them all
				for item in response_body['Results']:
					items.append({
									'name'         : item['Title'],
									'tooltip'      : item['Url'],
									'icon name'    : 'text-html',
									'type'         : 'xdg',
									'command'      : item['Url'],
									'context menu' : None
								})

			# always add 'Search more...' item
			items.append({
							'name'         : _('Show additional results'),
							'tooltip'      : _('Show additional search results in your web browser'),
							'icon name'    : 'system-search',
							'type'         : 'xdg',
							'command'      : self.web_base_url.format(text),
							'context menu' : None
						})

			# pass the results to Cardapio
			self.cardapio.handle_search_result(self, items)

		except KeyError:
			self.cardapio.handle_search_error(self, 'Incorrect Bing\'s JSON structure')

	def cancel(self):
		self.cardapio.write_to_log(self, 'cancelling a recent Bing search (if any)')

		if not self.cancellable.is_cancelled():
			self.cancellable.cancel()
