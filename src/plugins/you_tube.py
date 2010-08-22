import json
import gio
import urllib

from glib import GError

class CardapioPlugin(CardapioPluginInterface):
	"""
	YouTube video searching plugin based on it's Data API.
	Searching using the API is described here:
	http://code.google.com/apis/youtube/2.0/developers_guide_protocol.html#Searching_for_Videos

	All web requests are done in asynchronous and cancellable manner.
	"""

	# Cardapio's variables
	author = 'Pawel Bara'
	name = _('YouTube')
	description = _('Search for results in YouTube')
	version = '0.93b'

	url = ''
	help_text = ''

	plugin_api_version = 1.39

	search_delay_type = 'remote'

	default_keyword = 'youtube'

	category_name = _('YouTube Results')
	category_tooltip = _('Results found in YouTube')

	category_icon = 'system-search'
	fallback_icon = ''

	hide_from_sidebar = True

	def __init__(self, cardapio_proxy):

		self.cardapio = cardapio_proxy

		self.cancellable = gio.Cancellable()

		# YouTube's API arguments (format and maximum result count)
		self.api_base_args = {
			'alt'        : 'json'
		}

		# YouTube's base URLs (search and search more variations)
		self.api_base_url = 'http://gdata.youtube.com/feeds/api/videos?{0}'
		self.web_base_url = 'http://www.youtube.com/results?{0}'

		self.loaded = True

	def search(self, text, result_limit):

		if len(text) == 0:
			return

		self.cardapio.write_to_log(self, 'searching for {0} using YouTube'.format(text), is_debug = True)

		self.cancellable.reset()

		# prepare final API URL
		current_args = self.api_base_args.copy()
		current_args['max-results'] = result_limit
		current_args['q'] = text
		
		final_url = self.api_base_url.format(urllib.urlencode(current_args))

		self.cardapio.write_to_log(self, 'final API URL: {0}'.format(final_url), is_debug = True)

		# asynchronous and cancellable IO call
		self.current_stream = gio.File(final_url)
		self.current_stream.load_contents_async(self.show_search_results,
			cancellable = self.cancellable,
			user_data = text)

	def show_search_results(self, gdaemonfile, result, text):
		"""
		Callback to asynchronous IO (YouTube's API call).
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

			if response['feed']['openSearch$totalResults']['$t'] > 0:

				response_body = response['feed']['entry']

				for item in response_body:

					# we need to find the correct URL type (text/html) among
					# all that we are getting
					href = ""
					for link in item['link']:
						if link['type'] == 'text/html':
							href = link['href']
							break

					# ignore entries without the needed URL
					if len(href) == 0:
						continue

					items.append({
						'name'         : item['title']['$t'],
						'tooltip'      : href,
						'icon name'    : 'text-html',
						'type'         : 'xdg',
						'command'      : href,
						'context menu' : None
					})

			# always add 'Search more...' item
			items.append({
				'name'         : _('Show additional results'),
				'tooltip'      : _('Show additional search results in your web browser'),
				'icon name'    : 'system-search',
				'type'         : 'xdg',
				# TODO: cardapio later unquotes this and then quotes it again;
				# it's screwing my quotation
				'command'      : self.web_base_url.format(urllib.urlencode({'search_query' : text})),
				'context menu' : None
			})

			# pass the results to Cardapio
			self.cardapio.handle_search_result(self, items, text)

		except KeyError:
			self.cardapio.handle_search_error(self, "Incorrect YouTube's JSON structure")

	def cancel(self):
		self.cardapio.write_to_log(self, 'cancelling a recent YouTube search (if any)', is_debug = True)

		if not self.cancellable.is_cancelled():
			self.cancellable.cancel()
