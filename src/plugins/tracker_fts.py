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

	author             = _('Cardapio Team')
	name               = _('Full-text file search')
	description        = _('Search <b>inside</b> local files and folders indexed with Tracker')

	url                = ''
	help_text          = ''
	version            = '1.43'

	plugin_api_version = 1.40

	search_delay_type  = 'local'

	default_keyword    = 'ftstracker'

	category_name      = _('Results within files')
	category_icon      = 'system-search'
	icon               = 'system-search'
	category_tooltip   = _('Results found inside the files in your computer')
	hide_from_sidebar  = True


	def __init__(self, cardapio_proxy, category):

		self.c = cardapio_proxy

		try:
			from os.path import split
			from urllib2 import quote, splittype

		except Exception, exception:
			self.c.write_to_log(self, 'Could not import certain modules', is_error = True)
			self.c.write_to_log(self, exception, is_error = True)
			self.loaded = False
			return
		
		self.split     = split
		self.quote     = quote
		self.splittype = splittype
		
		self.tracker = None
		bus = dbus.SessionBus()

		if bus.request_name('org.freedesktop.Tracker1') == dbus.bus.REQUEST_NAME_REPLY_IN_QUEUE:
			tracker_object = bus.get_object('org.freedesktop.Tracker1', '/org/freedesktop/Tracker1/Resources')
			self.tracker = dbus.Interface(tracker_object, 'org.freedesktop.Tracker1.Resources')
		else:
			self.c.write_to_log(self, 'Could not connect to Tracker', is_error = True)
			self.loaded = False
			bus.release_name('org.freedesktop.Tracker1')
			return

		if (which("tracker-needle") is not None):
			self.action_command = r"tracker-needle '%s'"
		else:
			self.action_command = r"tracker-search-tool '%s'"

		self.action = {
			'name'         : _('Show additional results'),
			'tooltip'      : _('Show additional search results in the Tracker search tool'),
			'icon name'    : 'system-search',
			'type'         : 'callback',
			'command'      : self.more_results_action,
			'context menu' : None,
			}

		self.loaded = True


	def search(self, text, result_limit):

		self.current_query = text
		text = self.quote(text).lower()

		self.tracker.SparqlQuery(
			"""
				SELECT ?uri ?mime
				WHERE {
					?item a nie:InformationElement;
						fts:match "%s";
						nie:url ?uri;
						nie:mimeType ?mime;
						tracker:available true.
					}
				LIMIT %d
			"""
			% (text, result_limit),
			dbus_interface='org.freedesktop.Tracker1.Resources',
			reply_handler=self.prepare_and_handle_search_result,
			error_handler=self.handle_search_error
			)

		# not using: ORDER BY DESC(fts:rank(?item))


	def handle_search_error(self, error):

		self.c.handle_search_error(self, error)


	def prepare_and_handle_search_result(self, results):

		formatted_results = []

		for result in results:

			dummy, canonical_path = self.splittype(result[0])
			parent_name, child_name = self.split(canonical_path)
			icon_name = result[1]

			formatted_result = {
				'name'         : child_name,
				'icon name'    : icon_name,
				'tooltip'      : result[0],
				'command'      : canonical_path,
				'type'         : 'xdg',
				'context menu' : None,
				}

			formatted_results.append(formatted_result)

		if results:
			formatted_results.append(self.action)

		self.c.handle_search_result(self, formatted_results, self.current_query)


	def more_results_action(self, text):

		try:
			subprocess.Popen(self.action_command % text, shell = True)
		except OSError, e:
			self.c.write_to_log(self, 'Error launching plugin action.', is_error = True)
			self.c.write_to_log(self, e, is_error = True)


