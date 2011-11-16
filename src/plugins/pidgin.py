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
	Pidgin plugin based on it's D-Bus interface. Documentation:
	http://developer.pidgin.im/wiki/DbusHowto

	The plugin looks for Pidgin buddies and provides the user with
	possibility to start a conversation with any of them. All active
	accounts are considered. We match buddies by their alias (case
	insensitive).

	Each buddy is marked with icon representing his or her current
	status. We try to avoid nonexistent status icons by translating
	the categories of statuses to three standard icons (user-available,
	user-away or user-offline). Results are categorized and sorted
	according to their status too.

	Please note that the plugin only works when Pidgin is on. You don't
	need to turn Pidgin on before starting Cardapio or before initializing
	the plugin. You just need to turn it on before performing a Cardapio
	search.
	"""

	# Cardapio's variables
	author = 'Pawel Bara'
	name = _('Pidgin')
	description = _('Search for online Pidgin buddies')
	version = '0.93'

	url = ''
	help_text = ''

	default_keyword = 'pidgin'

	plugin_api_version = 1.40

	search_delay_type = 'local'

	category_name = _('Pidgin Buddies')
	category_tooltip = _('Your online Pidgin buddies')

	category_icon = 'pidgin'
	icon          = 'pidgin'
	fallback_icon = 'pidgin'

	hide_from_sidebar = True

	def __init__(self, cardapio_proxy, category):

		self.cardapio = cardapio_proxy

		try:
			from operator import itemgetter
			from dbus.exceptions import DBusException

		except Exception, exception:
			self.cardapio.write_to_log(self, 'Could not import certain modules', is_error = True)
			self.cardapio.write_to_log(self, exception, is_error = True)
			self.loaded = False
			return
		
		self.itemgetter    = itemgetter
		self.DBusException = DBusException

		# Pidgin's D-Bus constants
		self.dpidgin_bus_name = 'im.pidgin.purple.PurpleService'
		self.dpidgin_object_path = '/im/pidgin/purple/PurpleObject'
		self.dpidgin_iface_name = 'im.pidgin.purple.PurpleInterface'

		try:
			self.bus = dbus.SessionBus()
			# we track Pidgin's on / off status
			self.watch = self.bus.watch_name_owner(self.dpidgin_bus_name, self.on_dbus_name_change)

			self.loaded = True

		except self.DBusException as ex:
			self.cardapio.write_to_log(self, 'Pidgin plugin initialization error: {0}'.format(str(ex)), is_error = True)
			self.loaded = False

	# Pidgin's status primitives (constants)
	status_primitives = ['offline', 'available', 'unavailable', 'invisible', 'away',
	                     'extended_away', 'mobile', 'tune', 'mood']

	# mappings of Pidgin's status primitives to standard icon names
	status_icons = { 'offline' : 'user-offline', 'available' : 'user-available',
	                 'unavailable' : 'user-offline', 'invisible' : 'user-offline',
			 'away' : 'user-away', 'extended_away' : 'user-away',
			 'mobile' : 'user-available', 'tune' : 'user-available',
			 'mood' : 'user-available' }

	def __del__(self):
		if self.loaded:
			self.watch.cancel()

	def on_dbus_name_change(self, connection_name):
		"""
		This method effectively tracks down the events of Pidgin app starting
		and shutting down. When the app shuts down, this callback nullifies our
		Pidgin's proxy. When the app starts, this callback sets the valid
		proxy, then refreshes the constants that represent possible Pidgin's
		status primitives.
		"""

		if len(connection_name) == 0:
			# clear the state
			self.statuses = {}
			self.pidgin = None
		else:
			bus_object = self.bus.get_object(connection_name, self.dpidgin_object_path)
			pidgin = dbus.Interface(bus_object, self.dpidgin_iface_name)

			# remember the unique id of each status primitive
			self.statuses = {}
			for primitive in self.status_primitives:
				self.statuses[primitive] = pidgin.PurplePrimitiveGetTypeFromId(primitive)

			# ready
			self.pidgin = pidgin

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
		callback = DBusGatherBuddiesCallback(self, text, result_limit)

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
				'icon name'    : buddy[3],
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

	def __init__(self, parent, text, result_limit):
		self.parent = parent
		self.pidgin = parent.pidgin
		self.result_callback = parent.finalize_search

		self.text = text
		self.result_limit = result_limit

	def handle_search_result(self, accounts):
		"""
		Callback to asynchronous Pidgin's PurpleAccountsGetAllActive
		call. It gathers results and then passes those back to the
		main plugin class through the result_callback method.

		Results are prepared in certain way:
		- sorted by status, then alias
		- limited to at most result_limit entries
		"""

		# gather all online buddies
		buddies = self.gather_buddies(accounts)
		# sort (we rely on alphabetical order of icon names) and crop
		# the results before triggering further processing of them
		self.result_callback(sorted(buddies, key=self.itemgetter(3, 2))[:self.result_limit], self.text)

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

				buddy_alias = self.pidgin.PurpleBuddyGetAlias(buddy)

				# if buddy's alias contains (case insensitive) the search
				# keyword, add him to the result list
				if buddy_alias.lower().count(self.text.lower()) > 0:

					# but gather rest of his data first...
					buddy_name = self.pidgin.PurpleBuddyGetName(buddy)
					presence = self.pidgin.PurpleBuddyGetPresence(buddy)

					buddies.append((account, buddy_name, buddy_alias, self.get_icon_name(presence)))
		
		return buddies

	def get_icon_name(self, presence):
		"""
		Returns standard icon name for given presence of user.
		"""

		# look for active status primitive...
		for primitive in self.parent.status_primitives:
			status_const = self.parent.statuses[primitive]
			if(self.pidgin.PurplePresenceIsStatusPrimitiveActive(presence, status_const)):
				return self.parent.status_icons[primitive]

		# couldn't find it - fallback icon...
		return 'user-offline'

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

