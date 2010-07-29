import json
import gio
import urllib

from glib import GError

# TODO: it would be nice to localize this but it's hard; the Wikipedia's API
# has no locale parameter and the only way to look for results in other
# language is to change the URL from http://en.wikipedia.org/ to
# for example http://pl.wikipedia.org/; because we cannot be sure about
# existence of local Wikipedia versions we should look for them at runtime
# and use English only as fallback strategy; this is really hard considering
# asynchronous web requests and the lifecycle of plugin so I'm leaving this
# unimplemented and waiting for somebody brave enough ;)
class CardapioPlugin(CardapioPluginInterface):
	"""
	Wikipedia plugin based on it's "unofficial" API. Documentation can
	be found at: http://en.wikipedia.org/w/api.php.

	All web requests are done in asynchronous and cancellable manner.
	"""

	# Cardapio's variables
	author = 'Pawel Bara'
	name = _('Wikipedia')
	description = _('Search for results in Wikipedia')
	version = '0.91b'

	url = ''
	help_text = ''

	plugin_api_version = 1.35

	search_delay_type = 'remote search update delay'

	category_name = _('Wikipedia Results')
	category_tooltip = _('Results found in Wikipedia')

	category_icon = 'system-search'
	fallback_icon = ''

	hide_from_sidebar = True

	def __init__(self, cardapio_proxy):
		cardapio_proxy.write_to_log(self, 'initializing Wikipedia plugin')

		self.cardapio = cardapio_proxy

		self.cancellable = gio.Cancellable()

		# Wikipedia's unofficial API arguments (search truncated to
		# maximum four results, formatted as json)
		self.api_base_args = {
			'action': 'opensearch',
			'format': 'json',
			'limit' : str(self.cardapio.settings['search results limit']),
		}

		# Wikipedia's base URLs (search and show details variations)
		self.api_base_url = 'http://en.wikipedia.org/w/api.php?{0}'
		self.web_base_url = 'http://en.wikipedia.org/wiki/{0}'

		self.loaded = True

	def search(self, text):
		if len(text) == 0:
			return

		self.current_query = text

		self.cardapio.write_to_log(self, 'searching for {0} in Wikipedia'.format(text))

		self.cancellable.reset()

		# prepare final API URL
		current_args = self.api_base_args.copy()
		current_args['search'] = text
		final_url = self.api_base_url.format(urllib.urlencode(current_args))

		self.cardapio.write_to_log(self, 'final API URL: {0}'.format(final_url))

		# asynchronous and cancellable IO call
		self.current_stream = gio.File(final_url)
		self.current_stream.load_contents_async(self.show_search_results,
			cancellable = self.cancellable)

	def show_search_results(self, gdaemonfile, result):
		"""
		Callback to asynchronous IO (Wikipedia's API call).
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

			# response[1] because the response looks like: [text, [result_list]]
			# append results (if any)
			for item in response[1]:
				item_url = self.web_base_url.format(urllib.quote(item))
				items.append({
					'name'         : item,
					'tooltip'      : item_url,
					'icon name'    : 'text-html',
					'type'         : 'xdg',
					'command'      : item_url,
					'context menu' : None
				})

			# pass the results to Cardapio
			self.cardapio.handle_search_result(self, items, self.current_query)

		except KeyError:
			self.cardapio.handle_search_error(self, "Incorrect Wikipedia's JSON structure")

	def cancel(self):
		self.cardapio.write_to_log(self, 'cancelling a recent Wikipedia search (if any)')

		if not self.cancellable.is_cancelled():
			self.cancellable.cancel()
