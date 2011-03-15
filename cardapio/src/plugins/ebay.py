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

class CardapioPlugin(CardapioPluginInterface):
	"""
	eBay search plugin based on it's Finding API documented at:
	http://developer.ebay.com/products/finding/

	Please note, that this API limits the number of calls to 5000 per IP
	and day.

	All calls are localized, meaning that they are using eBay version local
	to the user. The specific version being used is derived from the user's
	computer locale.

	For a list of locale supported by eBay check:
	http://developer.ebay.com/DevZone/finding/Concepts/SiteIDToGlobalID.html
	The listing there means that the plugin is localized for more than 20
	countries. :) Nevertheless, we must have a fallback strategy and we use
	the US version in this role.

	All of the plugin's web requests are asynchronous and cancellable.
	"""

	# Cardapio's variables
	author = 'Pawel Bara'
	name = _('eBay')
	description = _('Search for items on eBay')
	version = '0.93'

	url = ''
	help_text = ''

	plugin_api_version = 1.40

	search_delay_type = 'remote'

	default_keyword = 'ebay'

	category_name = _('eBay Results')
	category_tooltip = _('Items found on eBay')

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
			from locale import getdefaultlocale

		except Exception, exception:
			self.cardapio.write_to_log(self, 'Could not import certain modules', is_error = True)
			self.cardapio.write_to_log(self, exception, is_error = True)
			self.loaded = False
			return

		self.json             = json
		self.gio              = gio
		self.urllib           = urllib
		self.GError           = GError
		self.getdefaultlocale = getdefaultlocale
		
		self.cancellable = self.gio.Cancellable()

		# eBay's API arguments (my API key, 'find' operation, JSON response format,
		# and locale information)
		self.api_base_args = {
			'SECURITY-APPNAME'     : 'Cardapio-9704-40b3-8e17-cfad62dd6c45',
			'OPERATION-NAME'       : 'findItemsByKeywords',
			'RESPONSE-DATA-FORMAT' : 'JSON',
			'GLOBAL-ID'            : self.get_global_id()
		}

		# eBay's base URLs (search and a fallback search more variations)
		self.api_base_url = 'http://svcs.ebay.com/services/search/FindingService/v1?{0}'
		self.web_base_url = 'http://shop.ebay.com/?{0}'

		self.loaded = True

	def get_global_id(self):
		"""
		Tries to get a locale specific GLOBAL-ID argument for eBay's API.
		For more information check those two websites:
		http://developer.ebay.com/DevZone/finding/Concepts/SiteIDToGlobalID.html
		http://developer.ebay.com/DevZone/finding/CallRef/Enums/GlobalIdList.html

		We use 'EBAY-US' as a fallback strategy.
		"""

		default = 'EBAY-US'

		# get and parse the language code
		lang_code = self.getdefaultlocale()[0]

		if lang_code is None:
			return default

		lang = lang_code[:2].lower()
		dialect = lang_code[3:].lower()

		# try to find a mapping...
		result = None
		if lang == 'en':
			if dialect == 'gb':
				result = 'EBAY-GB'
			elif dialect == 'ca':
				result = 'EBAY-ENCA'
			elif dialect == 'ie':
				result = 'EBAY-IE'
			elif dialect == 'in':
				result = 'EBAY-IN'
			elif dialect == 'my':
				result = 'EBAY-MY'
			elif dialect == 'ph':
				result = 'EBAY-PH'
			elif dialect == 'sg':
				result = 'EBAY-SG'
			elif dialect == 'au':
				result = 'EBAY-AU'
		elif lang == 'fr':
			if dialect == 'be':
				result = 'EBAY-FRBE'
			elif dialect == 'ca':
				result = 'EBAY-FRCA'
			else:
				result = 'EBAY-FR'
		elif lang == 'de':
			if dialect == 'at':
				result = 'EBAY-AT'
			elif dialect == 'ch':
				result = 'EBAY-CH'
			else:
				result = 'EBAY-DE'
		elif lang == 'it':
			result = 'EBAY-IT'
		elif lang == 'pl':
			result = 'EBAY-PL'
		elif lang == 'es':
			result = 'EBAY-ES'
		elif lang == 'nl':
			if dialect == 'be':
				result = 'EBAY-NLBE'
			else:
				result = 'EBAY-NL'
		elif lang == 'zh':
			result = 'EBAY-HK'
		elif lang == 'sv':
			result = 'EBAY-SE'

		return default if result is None else result

	def search(self, text, result_limit):
		if len(text) == 0:
			return

		self.cardapio.write_to_log(self, 'searching for {0} on eBay'.format(text), is_debug = True)

		self.cancellable.reset()

		# prepare final API URL (items per page and search keyword)
		current_args = self.api_base_args.copy()
		current_args['paginationInput.entriesPerPage'] = result_limit
		current_args['keywords'] = text

		final_url = self.api_base_url.format(self.urllib.urlencode(current_args))

		self.cardapio.write_to_log(self, 'final API URL: {0}'.format(final_url), is_debug = True)

		# asynchronous and cancellable IO call
		self.current_stream = self.gio.File(final_url)
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

			response = self.json.loads(json_body)
		except (ValueError, self.GError) as ex:
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

			# if the API call failed, add the generic 'search more' item
			if len(items) == 0:
				search_more_args = {
					'_nkw'   : text,
					'_sacat' : 'See-All-Categories'
				}

				items.append({
					'name'	       : _('Show additional results'),
					'tooltip'      : _('Show additional search results in your web browser'),
					'icon name'    : 'system-search',
					'type'         : 'xdg',
					# TODO: cardapio later unquotes this and then quotes it again;
					# it's screwing my quotation
					'command'      : self.web_base_url.format(self.urllib.urlencode(search_more_args)),
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
