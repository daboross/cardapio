from dbus.exceptions import DBusException

class CardapioPlugin(CardapioPluginInterface):

	"""
	Pidgin plugin based on it's D-Bus interface. Documentation:
	http://developer.pidgin.im/wiki/DbusHowto

	The plugin looks for online buddies and provides the user with
	possibility to start a conversation with any of them. All active
	accounts are considered. We match buddies by their alias (case
	insensitive).

	Please note that the plugin only works when Pidgin is on. You don't
	need to turn Pidgin on before starting Cardapio or before initializing
	the plugin. You just need to turn it on before performing a Cardapio
	search.
	"""

	# Cardapio's variables
	author = 'Pawel Bara'
	name = _('Pidgin')
	description = _('Search for online Pidgin buddies')
	version = '0.91b'

	url = ''
	help_text = ''

	default_keyword = 'pidgin'

	plugin_api_version = 1.39

	search_delay_type = 'local'

	category_name = _('Pidgin Buddies')
	category_tooltip = _('Your online Pidgin buddies')

	category_icon = 'pidgin'
	fallback_icon = ''

	hide_from_sidebar = True

	def __init__(self, cardapio_proxy):

		self.cardapio = cardapio_proxy

		# Pidgin's D-Bus constants
		self.dpidgin_bus_name = 'im.pidgin.purple.PurpleService'
		self.dpidgin_object_path = '/im/pidgin/purple/PurpleObject'
		self.dpidgin_iface_name = 'im.pidgin.purple.PurpleInterface'

		try:
			self.bus = dbus.SessionBus()
			# we track Pidgin's on / off status
			self.bus.watch_name_owner(self.dpidgin_bus_name, self.on_dbus_name_change)

			self.loaded = True

		except DBusException as ex:
			self.cardapio.write_to_log(self, 'Pidgin plugin initialization error: {0}'.format(str(ex)), is_error = True)
			self.loaded = False

	def on_dbus_name_change(self, connection_name):
		"""
		This method effectively tracks down the events of Pidgin app starting
		and shutting down. When the app shuts down, this callback nullifies our
		Pidgin's proxy and when the app starts, this callback sets the valid
		proxy again.
		"""

		if len(connection_name) == 0:
			self.pidgin = None
		else:
			bus_object = self.bus.get_object(connection_name, self.dpidgin_object_path)
			self.pidgin = dbus.Interface(bus_object, self.dpidgin_iface_name)

	def search(self, text, result_limit):
		if len(text) == 0:
			return

		# send empty results to Cardapio if Pidgin's off
		if self.pidgin is None:
			self.cardapio.handle_search_result(self, [], text)
			return

		self.cardapio.write_to_log(self, 'searching for Pidgin buddies with name like {0}'.format(text), is_debug = True)

		# prepare a parametrized callback that remembers the current search text and
		# the result limit
		callback = DBusGatherBuddiesCallback(self.pidgin, self.finalize_search,
			text, result_limit)

		# let's start by getting all of the user's active accounts
		self.pidgin.PurpleAccountsGetAllActive(reply_handler = callback.handle_search_result,
			error_handler = self.handle_search_error)

	def finalize_search(self, buddies, text):
		"""
		DBusGatherBuddiesCallback invokes this when it finishes gathering
		single search results. This method finalizes the search, then
		passes the result to Cardapio.
		"""

		items = []

		# for every buddy...
		for buddy in buddies:

			# 'start conversation' callback wrapper
			conversation_callback = DBusTalkToBuddyCallback(self.pidgin, buddy[0], buddy[1])

			# add 'talk to this buddy' item
			items.append({
				'name'         : buddy[2] + ' ({0})'.format(buddy[1]),
				'tooltip'      : _('Talk to this buddy'),
				'icon name'    : 'pidgin',
				'type'         : 'callback',
				'command'      : conversation_callback.start_conversation,
				'context menu' : None
			})

		self.cardapio.handle_search_result(self, items, text)

	def handle_search_error(self, error):
		"""
		Error callback to asynchronous Pidgin's D-Bus call.
		"""

		self.cardapio.handle_search_error(self, 'Pidgin search error: {0}'.format(str(error)))

class DBusGatherBuddiesCallback:
	"""
	DBusGatherBuddiesCallback serves as a parametrized wrapper over
	the asynchronous callback to Pidgin's PurpleAccountsGetAllActive
	call.
	"""

	def __init__(self, pidgin, result_callback, text, result_limit):
		self.pidgin = pidgin
		self.result_callback = result_callback

		self.text = text
		self.result_limit = result_limit

	def handle_search_result(self, accounts):
		"""
		Callback to asynchronous Pidgin's PurpleAccountsGetAllActive
		call. It gathers results and then passes those back to the
		main plugin class through the result_callback method.
		"""

		# gather all online buddies
		self.result_callback(self.gather_buddies(accounts), self.text)

	def gather_buddies(self, accounts):
		"""
		Gathers all of the user's online Pidgin buddies in a form of list
		containing tuples.
		"""

		# return empty results if Pidgin's off
		if self.pidgin is None:
			return []

		buddies = []

		# for every active account...
		for account in accounts:

			# and every buddy associated with this active account...
			for buddy in self.pidgin.PurpleFindBuddies(account, ''):

				# obey the result limit!
				if len(buddies) == self.result_limit:
					return buddies

				# we remember only those buddies who are online now
				if self.pidgin.PurpleBuddyIsOnline(buddy):

					buddy_alias = self.pidgin.PurpleBuddyGetAlias(buddy)
					buddy_name = self.pidgin.PurpleBuddyGetName(buddy)

					# if buddies alias contains (case insensitive) the search
					# keyword, add him to the result list
					if buddy_alias.lower().count(self.text.lower()) > 0:
						buddies.append((account, buddy_name, buddy_alias))

		return buddies


class DBusTalkToBuddyCallback:
	"""
	DBusTalkToBuddyCallback serves as a parametrized wrapper over
	the asynchronous callback to Pidgin's PurpleConversationNew
	call.
	"""

	def __init__(self, pidgin, account, buddy):
		self.pidgin = pidgin

		self.account = account
		self.buddy = buddy

	def start_conversation(self, search_text):
		"""
		Starts a conversation for the account and buddy name with which this
		callback was created. Ignores the callback parameter (search_text)
		from Cardapio.
		"""

		# try to avoid errors if Pidgin's off
		if self.pidgin is None:
			return

		# starting a conversation... the number 1 means 'InstantMessage
		# conversation'
		self.pidgin.PurpleConversationNew(1, self.account, self.buddy)
