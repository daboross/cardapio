#  
#  Copyright (C) 2010 Cardapio Team (tvst@hotmail.com)
# 
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
# 
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
# 
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

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
	version = '0.95'

	url = ''
	help_text = ''

	plugin_api_version = 1.40

	search_delay_type = 'remote'

	default_keyword = 'wikipedia'

	category_name = _('Wikipedia Results')
	category_tooltip = _('Results found in Wikipedia')

	category_icon = 'system-search'
	icon          = 'system-search'
	fallback_icon = ''

	hide_from_sidebar = True

	def __init__(self, cardapio_proxy, category):

		self.cardapio = cardapio_proxy

		try:
			import json
			import gio
			import urllib
			from glib import GError

		except Exception, exception:
			self.cardapio.write_to_log(self, 'Could not import certain modules', is_error = True)
			self.cardapio.write_to_log(self, exception, is_error = True)
			self.loaded = False
			return
		
		self.json   = json
		self.gio    = gio
		self.urllib = urllib
		self.GError = GError

		self.cancellable = self.gio.Cancellable()

		# Wikipedia's unofficial API arguments (search truncated to
		# maximum four results, formatted as json)
		self.api_base_args = {
			'action': 'opensearch',
			'format': 'json'
		}

		# Wikipedia's base URLs (search and show details variations)
		self.api_base_url = 'http://en.wikipedia.org/w/api.php?{0}'
		self.web_base_url = 'http://en.wikipedia.org/wiki/{0}'

		self.loaded = True

	def search(self, text, result_limit):
		if len(text) == 0:
			return

		self.cardapio.write_to_log(self, 'searching for {0} in Wikipedia'.format(text), is_debug = True)

		self.cancellable.reset()

		# prepare final API URL
		current_args = self.api_base_args.copy()
		current_args['limit'] = result_limit
		current_args['search'] = text

		final_url = self.api_base_url.format(self.urllib.urlencode(current_args))

		self.cardapio.write_to_log(self, 'final API URL: {0}'.format(final_url), is_debug = True)

		# asynchronous and cancellable IO call
		self.current_stream = self.gio.File(final_url)
		self.current_stream.load_contents_async(self.show_search_results,
			cancellable = self.cancellable,
			user_data = text)

	def show_search_results(self, gdaemonfile, result, text):
		"""
		Callback to asynchronous IO (Wikipedia's API call).
		"""

		# watch out for connection problems
		try:
			json_body = self.current_stream.load_contents_finish(result)[0]

			# watch out for empty input
			if len(json_body) == 0:
				return

			response = self.json.loads(json_body)
		except (ValueError, self.GError) as ex:
			self.cardapio.handle_search_error(self, 'error while obtaining data: {0}'.format(str(ex)))
			return

		# decode the result
		try:
			items = []

			# response[1] because the response looks like: [text, [result_list]]
			# append results (if any)
			for item in response[1]:
				# TODO: wikipedia sometimes returns item names encoded in unicode (try
				# searching for 'aaaaaaaaaaaaa' for example); we use those names as part
				# of a URL so we need to encode the special characters; unfortunately,
				# Python's 2.* urllib.quote throws an exception when it's given unicode
				# argument - what now?
				item_url = self.web_base_url.format(self.urllib.quote(str(item)))
				items.append({
					'name'         : item,
					'tooltip'      : item_url,
					'icon name'    : 'text-html',
					'type'         : 'xdg',
					'command'      : item_url,
					'context menu' : None
				})

			# pass the results to Cardapio
			self.cardapio.handle_search_result(self, items, text)

		except KeyError:
			self.cardapio.handle_search_error(self, "Incorrect Wikipedia's JSON structure")

	def cancel(self):
		self.cardapio.write_to_log(self, 'cancelling a recent Wikipedia search (if any)', is_debug = True)

		if not self.cancellable.is_cancelled():
			self.cancellable.cancel()
