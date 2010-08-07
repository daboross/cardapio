import json
import gio
import urllib

from glib import GError

# TODO: localize
class CardapioPlugin(CardapioPluginInterface):
	"""
	eBay search plugin based on it's Finding API documented at:
	http://developer.ebay.com/products/finding/

	Please note, that this API limits the number of calls to 5000 per IP
	and day.

	All of the plugin's web requests are asynchronous and cancellable.
	"""

	# Cardapio's variables
	author = 'Pawel Bara'
	name = _('eBay')
	description = _('Search for items on eBay')
	version = '0.9b'

	url = ''
	help_text = ''

	plugin_api_version = 1.37

	search_delay_type = 'remote search update delay'

	default_keyword = 'ebay'

	category_name = _('eBay Results')
	category_tooltip = _('Items found on eBay')

	category_icon = 'system-search'
	fallback_icon = ''

	hide_from_sidebar = True

	def __init__(self, cardapio_proxy):
		cardapio_proxy.write_to_log(self, 'initializing eBay plugin')

		self.cardapio = cardapio_proxy

		# take the maximum number of results into account
		self.results_limit = self.cardapio.settings['search results limit']
		self.long_results_limit = self.cardapio.settings['long search results limit']

		self.cancellable = gio.Cancellable()

		# eBay's API arguments (my API key, 'find' operation, JSON response format)
		self.api_base_args = {
			'SECURITY-APPNAME'     : 'Cardapio-9704-40b3-8e17-cfad62dd6c45',
			'OPERATION-NAME'       : 'findItemsByKeywords',
			'RESPONSE-DATA-FORMAT' : 'JSON'
		}

		# eBay's base search URL
		self.api_base_url = 'http://svcs.ebay.com/services/search/FindingService/v1?{0}'

		self.loaded = True

	def search(self, text, long_search = False):
		if len(text) == 0:
			return

		self.cardapio.write_to_log(self, 'searching for {0} on eBay'.format(text), is_debug = True)

		self.cancellable.reset()

		# prepare final API URL (items per page and search keyword)
		current_args = self.api_base_args.copy()
		current_args['paginationInput.entriesPerPage'] = self.long_results_limit if long_search else self.results_limit
		current_args['keywords'] = text

		final_url = self.api_base_url.format(urllib.urlencode(current_args))

		self.cardapio.write_to_log(self, 'final API URL: {0}'.format(final_url), is_debug = True)

		# asynchronous and cancellable IO call
		self.current_stream = gio.File(final_url)
		self.current_stream.load_contents_async(self.show_search_results,
			cancellable = self.cancellable,
			user_data = text)

	def show_search_results(self, gdaemonfile, result, text):
		"""
		Callback to asynchronous IO (eBay's API call).
		"""

		# watch out for connection problems
		try:
			json_body = self.current_stream.load_contents_finish(result)[0]

			# watch out for empty input
			if len(json_body) == 0:
				return

			response = json.loads(json_body)
		except (ValueError, GError) as ex:
			self.cardapio.handle_search_error(self, 'error while obtaining data: {0}'.format(str(ex)))
			return

		# decode the result
		try:
			items = []

			response_body = response['findItemsByKeywordsResponse'][0]

			# if we made a successful call...
			if response_body['ack'][0] == 'Success':
				search_result = response_body['searchResult'][0]

				# and we have any results...
				if int(search_result['@count']) > 0:

					# remember them all
					for ebay_item in search_result['item']:
						ebay_item_url = ebay_item['viewItemURL'][0]

						items.append({
							'name'         : ebay_item['title'][0],
							'tooltip'      : ebay_item_url,
							'icon name'    : 'text-html',
							'type'         : 'xdg',
							'command'      : ebay_item_url,
							'context menu' : None
							})

				# on a succesful call, add the 'Search more...' item (URL from the response)
				items.append({
					'name'	       : _('Show additional results'),
					'tooltip'      : _('Show additional search results in your web browser'),
					'icon name'    : 'system-search',
					'type'         : 'xdg',
					'command'      : response_body['itemSearchURL'][0],
					'context menu' : None
				})

			# pass the results to Cardapio
			self.cardapio.handle_search_result(self, items, text)

		except KeyError:
			self.cardapio.handle_search_error(self, "Incorrect eBay's JSON structure")

	def cancel(self):
		self.cardapio.write_to_log(self, 'cancelling a recent eBay search (if any)', is_debug = True)

		if not self.cancellable.is_cancelled():
			self.cancellable.cancel()
