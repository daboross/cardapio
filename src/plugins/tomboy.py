from dbus.exceptions import DBusException

# TODO: respect result limit (including long_search)
class CardapioPlugin(CardapioPluginInterface):

	"""
	Tomboy plugin based on it's D-Bus interface. Documentation:
	http://arstechnica.com/open-source/news/2007/09/using-the-tomboy-d-bus-interface.ars

	The plugin looks for notes with titles similar to the search string. If it can't
	find any, it provides user with the handy 'Create note with this title' link.
	"""

	# Cardapio's variables
	author = 'Pawel Bara'
	name = _('Tomboy')
	description = _('Search for Tomboy notes')
	version = '0.9b'

	url = ''
	help_text = ''

	default_keyword = 'tomboy'

	plugin_api_version = 1.37

	search_delay_type = 'local search update delay'

	category_name = _('Tomboy Results')
	category_tooltip = _('Your Tomboy notes')

	category_icon = 'system-search'
	fallback_icon = ''

	hide_from_sidebar = True

	def __init__(self, cardapio_proxy):
		cardapio_proxy.write_to_log(self, 'initializing Tomboy plugin')

		self.cardapio = cardapio_proxy

		try:
			# initialization of the Tomboy's D-Bus interface
			bus = dbus.SessionBus()
			bus_object = bus.get_object('org.gnome.Tomboy', '/org/gnome/Tomboy/RemoteControl')
			self.tomboy = dbus.Interface(bus_object, 'org.gnome.Tomboy.RemoteControl')

			self.loaded = True

		except DBusException as ex:
			self.cardapio.write_to_log(self, 'Tomboy plugin initialization error: {0}'.format(str(ex)), is_error = True)

			self.loaded = False

	def search(self, text, long_search = False):
		if len(text) == 0:
			return

		self.cardapio.write_to_log(self, 'searching for Tomboy notes with topic like {0}'.format(text), is_debug = True)

		# TODO: this is not thread-safe but I couldn't find any way to pass the current search text
		# into D-Bus' callback
		self.current_query = text

		# we ask for all notes (it's either that or a single note...)
		self.tomboy.ListAllNotes(reply_handler = self.handle_search_result,
			error_handler = self.handle_search_error)

	def handle_search_result(self ,result):
		"""
		Callback to asynchronous Tomboy's D-Bus call.
		"""

		items = []

		# looking for notes with titles containing (case insensitive) the given
		# query text
		for note in result:
			note_title = self.tomboy.GetNoteTitle(note)

			if note_title.lower().count(self.current_query.lower()) > 0:
				# add 'open this note' search item
				items.append({
					'name'         : note_title,
					'tooltip'      : _('Open this note'),
					'icon name'    : 'tomboy',
					'type'         : 'xdg',
					'command'      : note,
					'context menu' : None
				})

		# if there are no results, we'll add the 'create a note with this
		# title' link
		if len(items) == 0:
			items.append({
				'name'         : _('Create this note'),
				'tooltip'      : _('Create a new note with this title in Tomboy'),
				'icon name'    : 'tomboy',
				'type'         : 'callback',
				'command'      : self.tomboy_create_note,
				'context menu' : None
			})

		# the 'search more' option is always present
		items.append({
			'name'         : _('Show additional notes'),
			'tooltip'      : _('Show additional notes in Tomboy'),
			'icon name'    : 'tomboy',
			'type'         : 'callback',
			'command'      : self.tomboy_find_more,
			'context menu' : None
		})

		self.cardapio.handle_search_result(self, items, self.current_query)

	def handle_search_error(self, error):
		"""
		Error callback to asynchronous Tomboy's D-Bus call.
		"""

		self.cardapio.handle_search_error(self, 'Tomboy search error: {0}'.format(str(error)))

	def tomboy_create_note(self, text):
		"""
		Creates a new note with the given title, then displays it to user.
		"""

		new_note = self.tomboy.CreateNamedNote(text)
		self.tomboy.DisplayNote(new_note)

	def tomboy_find_more(self, text):
		"""
		Opens Tomboy's 'Search more' window.
		"""

		self.tomboy.DisplaySearchWithText(text)
