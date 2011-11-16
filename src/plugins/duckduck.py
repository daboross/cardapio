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


## Duck Duck Go search plugin by Clifton Mulkey
## Adapted from the Google Search plugin
class CardapioPlugin(CardapioPluginInterface):

	author             = _('Cardapio Team')
	name               = _('DuckDuckGo')
	description        = _('Perform quick DuckDuckGo searches')

	url                = ''
	help_text          = ''
	version            = '1.0'

	plugin_api_version = 1.40

	search_delay_type  = 'remote'

	default_keyword    = 'duck'

	category_name      = _('DuckDuckGo Results')
	category_icon      = 'system-search'
	icon               = 'system-search'
	category_tooltip   = _('Results found with DuckDuckGo')
	hide_from_sidebar  = True


	def __init__(self, cardapio_proxy, category):

		self.c = cardapio_proxy
		
		try:
			from gio import File, Cancellable
			from urllib2 import quote
			from simplejson import loads
			from locale import getdefaultlocale
			from glib import GError

		except Exception, exception:
			self.c.write_to_log(self, 'Could not import certain modules', is_error = True)
			self.c.write_to_log(self, exception, is_error = True)
			self.loaded = False
			return
		
		self.File             = File
		self.Cancellable      = Cancellable
		self.quote            = quote
		self.loads            = loads
		self.getdefaultlocale = getdefaultlocale
		self.GError           = GError

		self.query_url = r'http://www.duckduckgo.com/?q={0}&o=json'

		self.search_controller = self.Cancellable()

		self.action_command = "xdg-open 'http://duckduckgo.com/?q=%s'"
		self.action = {
			'name'         : _('Show additional results'),
			'tooltip'      : _('Show additional search results in your web browser'),
			'icon name'    : 'system-search',
			'type'         : 'callback',
			'command'      : self.more_results_action,
			'context menu' : None,
			}
		
		

		self.loaded = True


	def search(self, text, result_limit):

		# TODO: I'm sure this is not the best way of doing remote procedure
		# calls, but I can't seem to find anything that is this easy to use and
		# compatible with gtk. Argh :(

		# TODO: we should really check if there's an internet connection before
		# proceeding...

		self.current_query = text
		text = self.quote(str(text))
		
		# Is there a way to get the result_limit in the init method
		# so we don't have to assign it everytime search is called?
		self.result_limit = result_limit

		query = self.query_url.format(text)

		self.stream = self.File(query)

		self.search_controller.reset()
		self.stream.load_contents_async(self.handle_search_result, cancellable = self.search_controller)


	def cancel(self):

		if not self.search_controller.is_cancelled():
			self.search_controller.cancel()

	
	def handle_search_result(self, gdaemonfile = None, response = None):
		# This function parses the results from the query
		# The results returned from DDG are a little convoluted
		# so we have to check for many different types of results here
		
		result_count = 0;

		try:
			response = self.stream.load_contents_finish(response)[0]

		except self.GError, e:
			# no need to worry if there's no response: maybe there's no internet
			# connection...
			self.c.handle_search_error(self, 'no response')
			return

		raw_results = self.loads(response)
		
		# print raw_results
		parsed_results = [] 

		if 'Error' in raw_results:
			self.c.handle_search_error(self, raw_results['Error'])
			return
		
		# check for an abstract section
		try:
			if raw_results['Abstract']:
				item = {
					'name'         : raw_results['Heading'],
					'tooltip'      : '(%s) %s' % (raw_results['AbstractSource'], raw_results['AbstractText']),
					'icon name'    : 'text-html',
					'type'         : 'xdg',
					'command'      : raw_results['AbstractURL'],
					'context menu' : None,
					}
				parsed_results.append(item)
				result_count += 1
		except KeyError:
			pass
			
		# check for a definition section
		try:
			if raw_results['Definition']:
				item = {
					'name'         : '%s (Definition)' % raw_results['Heading'],
					'tooltip'      : '(%s) %s' % (raw_results['DefinitionSource'], raw_results['Definition']),
					'icon name'    : 'text-html',
					'type'         : 'xdg',
					'command'      : raw_results['DefinitionURL'],
					'context menu' : None,
					}
				parsed_results.append(item)
				result_count += 1
		except KeyError:
			pass
		
		# check for a related topics section
		try:
			if raw_results['RelatedTopics']:
				for raw_result in raw_results['RelatedTopics']:
					if result_count >= self.result_limit: break
						
					#some related topics have a 'Topics' sub list
					try: 
						for result in raw_result['Topics']:
								if result_count >= self.result_limit: break
									
								item = {
									'name'         : result['Text'],
									'tooltip'      : result['FirstURL'],
									'icon name'    : 'text-html',
									'type'         : 'xdg',
									'command'      : result['FirstURL'],
									'context menu' : None,
									}
								parsed_results.append(item)
								result_count += 1
					except KeyError:		
					#otherwise the RelatedTopic is a single entry
						item = {
						'name'         : raw_result['Text'],
						'tooltip'      : raw_result['FirstURL'],
						'icon name'    : 'text-html',
						'type'         : 'xdg',
						'command'      : raw_result['FirstURL'],
						'context menu' : None,
						}
						parsed_results.append(item)
						result_count += 1
		except KeyError:
			pass
		
		# check for external results section
		try:
			if raw_results['Results']:
				for raw_result in raw_results['Results']:
					if result_count >= self.result_limit: break
			
					item = {
					'name'         : raw_result['Text'],
					'tooltip'      : raw_result['FirstURL'],
					'icon name'    : 'text-html',
					'type'         : 'xdg',
					'command'      : raw_result['FirstURL'],
					'context menu' : None,
					}
					parsed_results.append(item)
					result_count += 1
				
		except KeyError:
			pass
		
		

		if parsed_results:
			parsed_results.append(self.action)

		self.c.handle_search_result(self, parsed_results, self.current_query)


	def more_results_action(self, text):

		text = text.replace("'", r"\'")
		text = text.replace('"', r'\"')

		try:
			subprocess.Popen(self.action_command % text, shell = True)
		except OSError, e:
			self.c.write_to_log(self, 'Error launching plugin action.', is_error = True)
			self.c.write_to_log(self, e, is_error = True)


