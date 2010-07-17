import urllib2, os

class CardapioPlugin(CardapioPluginInterface):

	author             = _('Cardapio Team')
	name               = _('Tracker full text search')
	description        = _('Search <b>inside</b> local files and folders indexed with Tracker')

	url                = ''
	help_text          = ''
	version            = '1.3'

	plugin_api_version = 1.3

	search_delay_type  = 'local search update delay'

	category_name      = _('Results within files')
	category_icon      = 'system-search'
	category_tooltip   = _('Results found inside the files in your computer')
	hide_from_sidebar  = True


	def __init__(self, cardapio_proxy): 

		self.c = cardapio_proxy

		self.tracker = None
		bus = dbus.SessionBus()

		if bus.request_name('org.freedesktop.Tracker1') == dbus.bus.REQUEST_NAME_REPLY_IN_QUEUE:
			tracker_object = bus.get_object('org.freedesktop.Tracker1', '/org/freedesktop/Tracker1/Resources')
			self.tracker = dbus.Interface(tracker_object, 'org.freedesktop.Tracker1.Resources') 
		else:
			self.loaded = False
			return 

		self.search_results_limit = self.c.settings['search results limit']

		self.action_command = r'tracker-search-tool %s'
		self.action = {
			'name'         : _('Show additional results'),
			'tooltip'      : _('Show additional search results in the Tracker search tool'),
			'icon name'    : 'system-search',
			'type'         : 'callback',
			'command'      : self.more_results_action,
			'context menu' : None,
			}

		self.loaded = True


	def search(self, text):

		text = urllib2.quote(text).lower()

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
			% (text, self.search_results_limit),
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
			
			dummy, canonical_path = urllib2.splittype(result[0])
			parent_name, child_name = os.path.split(canonical_path)
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

		self.c.handle_search_result(self, formatted_results)


	def more_results_action(self, text):

		try:
			subprocess.Popen(self.action_command % text, shell = True)
		except OSError, e:
			self.c.write_to_log(self, 'Error launching plugin action.', is_error = True)
			self.c.write_to_log(self, e, is_error = True)


