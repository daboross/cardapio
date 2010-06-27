import urllib2, os

try:
	from zeitgeist.client import ZeitgeistClient
	from zeitgeist import datamodel

except Exception, e:
	print e
	pass


class CardapioPlugin(CardapioPluginInterface):

	author             = 'Thiago Teixeira'
	name               = _('Zeitgeist recently used plugin')
	description        = _('Get information about most recently used apps and files.')

	url                = ''
	help_text          = ''
	version            = '1.0'

	plugin_api_version = 1.2

	search_delay_type  = None

	category_name      = _('Recently used')
	category_icon      = 'document-open-recent'
	hide_from_sidebar  = False

	recency_in_days = 30

	def __init__(self, settings, write_to_log, cardapio_result_handler, cardapio_error_handler):

		self.write_to_log = write_to_log
		self.cardapio_result_handler = cardapio_result_handler
		self.cardapio_error_handler = cardapio_error_handler
		self.num_search_results = settings['search results limit']

		if 'ZeitgeistClient' not in globals():
			write_to_log(self, 'Could not import Zeitgeist')
			self.loaded = False
			return

		try:
			self.client = ZeitgeistClient()
		except:
			write_to_log(self, 'Could not start Zeitgeist')
			self.loaded = False
			return 

		self.search_by_actor = datamodel.Event()
		self.search_by_uri = datamodel.Event()
		self.search_by_uri.subject = datamodel.Subject()
		self.loaded = True


	def __del__(self):

		pass


	def search(self, text):

		time_range = datamodel.TimeRange.always()

		if text:
			self.search_by_actor.actor = 'application://' + text + '*'
			# TODO: if there any way to search for a substring?
			#self.search_by_uri.subject.uri = '*' + text + '*'
		else:
			self.search_by_actor.actor = ''
			#self.search_by_uri.subject.uri = ''

		self.client.find_events_for_templates(
				[self.search_by_actor], #self.search_by_uri], 
				self.handle_search_result, 
				timerange = time_range, 
				num_events = self.num_search_results, 
				result_type = datamodel.ResultType.MostRecentSubjects
				)


	def handle_search_result(self, events):

		parsed_results = [] 

		for event in events:
			for subject in event.get_subjects():

				dummy, canonical_path = urllib2.splittype(subject.uri)
				parent_name, child_name = os.path.split(canonical_path)

				item = {
					'name'      : subject.text,
					'icon name' : subject.mimetype,
					'tooltip'   : canonical_path,
					'command'   : canonical_path,
					'type'      : 'xdg',
					}

				parsed_results.append(item)

		self.cardapio_result_handler(self, parsed_results)


