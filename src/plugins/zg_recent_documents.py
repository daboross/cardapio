from commands import getoutput
import urllib2, os

plugin_exception = None

try:
	from zeitgeist.client import ZeitgeistClient
	from zeitgeist import datamodel

except Exception, exception:
	plugin_exception = exception


class CardapioPlugin(CardapioPluginInterface):

	author             = 'Thiago Teixeira'
	name               = _('Recent documents')
	description        = _('Search for your most recently used files.')

	url                = ''
	help_text          = ''
	version            = '0.9b'

	plugin_api_version = 1.2

	search_delay_type  = 'local search update delay'

	category_name      = _('Recent Documents')
	category_icon      = 'document-open-recent'
	category_tooltip   = _('Files that you have used recently')

	hide_from_sidebar  = True

	recency_in_days = 30

	def __init__(self, settings, write_to_log, cardapio_result_handler, cardapio_error_handler):

		self.loaded = False

		self.write_to_log = write_to_log
		self.cardapio_result_handler = cardapio_result_handler
		self.cardapio_error_handler = cardapio_error_handler
		self.num_search_results = settings['search results limit']

		if 'ZeitgeistClient' not in globals():
			self.write_to_log(self, 'Could not import Zeitgeist', is_error = True)
			if plugin_exception: self.write_to_log(self, plugin_exception)
			return

		try:
			self.zg = ZeitgeistClient()
		except Exception, exception:
			self.write_to_log(self, 'Could not start Zeitgeist', is_error = True)
			self.write_to_log(self, exception)
			return 

		bus = dbus.SessionBus()

		if bus.request_name('org.freedesktop.Tracker1') != dbus.bus.REQUEST_NAME_REPLY_IN_QUEUE:
			self.write_to_log(self, 'Could not find Zeitgeist full-text-search', is_error = True)
			return 

		try:
			fts_object = bus.get_object('org.gnome.zeitgeist.Engine', '/org/gnome/zeitgeist/index/activity')
			self.fts = dbus.Interface(fts_object, 'org.gnome.zeitgeist.Index')
		except Exception, exception:
			self.write_to_log(self, 'Could not connect to Zeitgeist full-text-search', is_error = True)
			self.write_to_log(self, exception)
			return 

		self.have_sezen = (len(getoutput('which sezen')) != 0)

		self.action_command = r"sezen '%s'"
		self.action = {
			'name'      : _('Show additional results'),
			'tooltip'   : _('Show additional search results in Sezen'),
			'icon name' : 'system-search',
			'type'      : 'callback',
			'command'   : self.more_results_action,
			}

		self.time_range = datamodel.TimeRange.always()

		self.event_template = datamodel.Event()
		self.loaded = True


	def __del__(self):

		pass


	def search(self, text):

		text = text.lower()
		self.search_query = text

		if text:
			self.event_template.actor = 'application://' + text + '*'
		else:
			self.event_template.actor = ''

		self.zg.find_events_for_templates(
				[self.event_template],
				self.handle_search_result, 
				timerange = self.time_range, 
				num_events = self.num_search_results, 
				result_type = datamodel.ResultType.MostRecentSubjects
				)


	def handle_search_result(self, events):

		fts_results = None
		all_events = []

		# TODO: make this asynchronous somehow! (Need to talk to the developers
		# of the FTS extensions to add this to the API)
		if self.search_query:

			try:
				fts_results, count = self.fts.Search(
						self.search_query + '*', 
						self.time_range, 
						[], 0, self.num_search_results, 2)

			except Exception, exception:
				print exception
				pass

			if fts_results:
				all_events = map(datamodel.Event, fts_results)

		parsed_results = [] 
		all_events += events
		urls_seen = set()

		for event in all_events:

			if len(urls_seen) >= self.num_search_results: break

			for subject in event.get_subjects():

				dummy, canonical_path = urllib2.splittype(subject.uri)
				parent_name, child_name = os.path.split(canonical_path)

				if len(urls_seen) >= self.num_search_results: break
				if canonical_path in urls_seen: continue
				urls_seen.add(canonical_path)

				item = {
					'name'      : subject.text,
					'icon name' : subject.mimetype,
					'tooltip'   : canonical_path,
					'command'   : canonical_path,
					'type'      : 'xdg',
					}

				parsed_results.append(item)


		# TODO: Waiting for Sezen to support command-line arguments...
		#if parsed_results and self.have_sezen:
		#	parsed_results.append(self.action)

		self.cardapio_result_handler(self, parsed_results)


	def more_results_action(self, text):

		try:
			subprocess.Popen(self.action_command % text, shell = True)

		except OSError, e:
			write_to_log(self, 'Error launching plugin action.', is_error = True)
			write_to_log(self, e, is_error = True)


