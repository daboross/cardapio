import json
import gio
import urllib

import base64
import hashlib
import hmac
import time

from xml.etree import ElementTree

class CardapioPlugin(CardapioPluginInterface):

	"""
	Amazon plugin based on it's Product Advertising API. We provide
	results from all of the shop's categories.

	API's documentation can be found at:
	http://docs.amazonwebservices.com/AWSECommerceService/2009-11-01/DG/

	All of the plugin's web requests are asynchronous and cancellable.

	TODO: localize
	"""

	# Cardapio's variables
	author = 'Pawel Bara'
	name = _('Amazon')
	description = _('Search for results in Amazon')
	version = '0.9b'

	url = ''
	help_text = ''

	plugin_api_version = 1.35

	search_delay_type = 'remote search update delay'

	category_name = _('Amazon Results')
	category_tooltip = _('Results found in Amazon')

	category_icon = 'system-search'
	fallback_icon = ''

	hide_from_sidebar = True

	def __init__(self, cardapio_proxy):
		cardapio_proxy.write_to_log(self, 'initializing Amazon plugin')

		self.cardapio = cardapio_proxy

		self.cancellable = gio.Cancellable()

		# my API keys
		self.aws_access_key = 'AKIAIW35CYEJ653CJJHQ'
		self.aws_secret_access_key = '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'

		# basic API's arguments (search in all categories)
		self.api_base_args = {
			'Service'       : 'AWSECommerceService',
			'Version'       : '2009-11-01',
			'Operation'     : 'ItemSearch',
			'SearchIndex'   : 'All',
			'ResponseGroup' : 'Small',
 			'AWSAccessKeyId': self.aws_access_key
		}

		# remember the maximum number of results
		self.results_limit = self.cardapio.settings['search results limit']

		# Amazon's base URLs (search and search more variations)
		self.api_base_url = 'http://ecs.amazonaws.com/onca/xml?{0}'
		self.web_base_url = 'http://www.amazon.com/s?url=search-alias%3Daps&{0}'

		self.loaded = True

	def search(self, text):
		if len(text) == 0:
			return

		self.cardapio.write_to_log(self, 'searching for {0} using Amazon'.format(text), is_debug = True)

		self.cancellable.reset()

		# prepare final API URL
		final_url = self.api_base_url.format(self.prepare_amazon_rest_url(text))

		self.cardapio.write_to_log(self, 'final API URL: {0}'.format(final_url), is_debug = True)

		# asynchronous and cancellable IO call
		self.current_stream = gio.File(final_url)
		self.current_stream.load_contents_async(self.show_search_results,
			cancellable = self.cancellable,
			user_data = text)

	def prepare_amazon_rest_url(self, text):
		"""
		Prepares a RESTful URL according to Amazon's strict querying policies.
		Deals with the variable part of the URL only (the one after the '?').
		"""

		# additional required API arguments
		copy_args = self.api_base_args.copy()
		copy_args['Keywords'] = text
		copy_args['Timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

		# turn the argument map into a list of encoded request parameter strings
		query_list = map(
			lambda (k, v): (k + "=" + urllib.quote(v)),
			copy_args.items()
		)

		# sort the list (by parameter name)
		query_list.sort()

		# turn the list into a partial URL string
		query_string = "&".join(query_list)

		# prepare a string on which we will base the AWS signature
		string_to_sign = """GET
ecs.amazonaws.com
/onca/xml
{0}""".format(query_string)

		# create HMAC for the string (using SHA-256 and our secret API key)
		hm = hmac.new(key = self.aws_secret_access_key,
       		msg = string_to_sign,
         	digestmod = hashlib.sha256)
		# final step... convert the HMAC to base64, then encode it
		signature = urllib.quote(base64.b64encode(hm.digest()))

		return query_string + '&Signature=' + signature

	def show_search_results(self, gdaemonfile, result, text):
		"""
		Callback to asynchronous IO (Amazon's API call).
		"""

		# watch out for connection problems
		try:
			xml_body = self.current_stream.load_contents_finish(result)[0]

			# watch out for empty input
			if len(xml_body) == 0:
				return

			root = ElementTree.fromstring(xml_body)

			# strip the namespaces from all the parsed items
			for el in root.getiterator():
				ns_pos = el.tag.find('}')
				if ns_pos != -1:
					el.tag = el.tag[(ns_pos + 1):]
		except Exception as ex:
			self.cardapio.handle_search_error(self, 'error while obtaining data: {0}'.format(str(ex)))
			return

		# decode the result
		try:
			items = []

			is_valid = root.find('Items/Request/IsValid')
			total_results = root.find('Items/TotalResults')

			# if we have a valid response with any results...
			if (not is_valid is None) and is_valid != 'False' and (not total_results is None) and total_results != '0':
				# remember them all
				for i, item in enumerate(root.findall('Items/Item')):

					# the number of results cannot be limited using Amazon's API...
					if i == self.results_limit:
						break

					i_attributes = item.find('ItemAttributes')
					url = item.find('DetailPageURL').text

					items.append({
						'name'         : i_attributes.find('Title').text + ' [' + i_attributes.find('ProductGroup').text + ']',
						'tooltip'      : url,
						'icon name'    : 'text-html',
						'type'         : 'xdg',
						'command'      : url,
						'context menu' : None
					})

			# always add 'Search more...' item
			search_more_args = { 'field-keywords' : text }

			items.append({
				'name'         : _('Show additional results'),
				'tooltip'      : _('Show additional search results in your web browser'),
				'icon name'    : 'system-search',
				'type'         : 'xdg',
				# TODO: cardapio later unquotes this and then quotes it again;
				# it's screwing my quotation
				'command'      : self.web_base_url.format(urllib.urlencode(search_more_args)),
				'context menu' : None
			})

			# pass the results to Cardapio
			self.cardapio.handle_search_result(self, items, text)

		except KeyError:
			self.cardapio.handle_search_error(self, "Incorrect Amazon's JSON structure")

	def cancel(self):
		self.cardapio.write_to_log(self, 'cancelling a recent Amazon search (if any)', is_debug = True)

		if not self.cancellable.is_cancelled():
			self.cancellable.cancel()
