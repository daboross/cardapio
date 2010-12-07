class CardapioPluginInterface:
	# for documentation, see: https://answers.launchpad.net/cardapio/+faq/1172

	author      = ''
	name        = ''
	description = ''

	# not yet used:
	url         = ''
	help_text   = ''
	version     = ''

	plugin_api_version = 1.39

	search_delay_type = 'local'

	default_keyword  = ''

	category_name    = ''
	category_icon    = ''
	category_tooltip = ''

	fallback_icon    = ''

	hide_from_sidebar = True

	def __init__(self, cardapio_proxy):
		"""
		REQUIRED

		This constructor gets called whenever a plugin is activated.
		(Typically once per session, unless the user is turning plugins on/off)

		The constructor *must* set the instance variable self.loaded to True of False.
		For example, the Tracker plugin sets self.loaded to False if Tracker is not
		installed in the system.

		The constructor is given a single parameter, which is an object used to
		communicate with Cardapio. This object has the following members:

		   - write_to_log - this is a function that lets you write to Cardapio's
		     log file, like this: write_to_log(self, 'hi there')

		   - handle_search_result - a function to which you should pass the
		     search results when you have them (see more info below, in the
			 search() method)

		   - handle_search_error - a function to which you should pass an error
		     message if the search fails (see more info below, in the
			 search() method)

		   - ask_for_reload_permission - a function that should be used whenever
			 the plugin wants to reload its database. Not all plugins have
			 internal databases, though, so this is not always applicable. This
			 is used, for example, with the software_center plugin. (see
 		     on_reload_permission_granted below for more info)
		"""
		pass


	def __del__(self):
		"""
		NOT REQUIRED

		This destructor gets called whenever a plugin is deactivated
		(Typically once per session, unless the user is turning plugins on/off)
		"""
		pass


	def search(self, text, result_limit):
		"""
		REQUIRED

		This method gets called when a new text string is entered in the search
		field. It also takes an argument indicating the maximum number of
		results Cardapio's expecting. The plugin should always provide as many
		results as it can but their number cannot exceed the given limit!

		One of the following functions should be called from this method
		(of from a thread spawned by this method):

		   * if all goes well:
		   --> handle_search_result(plugin, results, original_query)

		   * if there is an error
		   --> handle_search_error(plugin, text)

		The arguments to these functions are:

		   * plugin          - this plugin instance (that is, it should always
		                       be "self", without quotes)
		   * text            - some text to be inserted in Cardapio's log.
		   * results         - an array of dict items as described below.
		   * original_query  - the search query that this corresponds to. The
		                       plugin should save the query received by the
							   search() method and pass it back to Cardapio.

		item = {
		  'name'         : _('Music'),
		  'tooltip'      : _('Show your Music folder'),
		  'icon name'    : 'text-x-generic',
		  'type'         : 'xdg',
		  'command'      : '~/Music',
		  'context menu' : None
		  }

		Where setting 'type' to 'xdg' means that 'command' should be opened
		using xdg-open (you should give it a try it in the terminal, first!).
		Meanwhile, setting 'type' to 'callback' means that 'command' is a
		function that should be called when the item is clicked. This function
		will receive as an argument the current search string.

		Note that you can set item['file name'] to None if you want Cardapio
		to guess the icon from the 'command'. This only works for 'xdg' commands,
		though.

		To change what is shown in the context menu for the search results, set
		the 'context menu' field to a list [] of dictionary items exactly like
		the ones above.
		"""
		pass


	def cancel(self):
		"""
		NOT REQUIRED

		This function should cancel the search operation. This is useful if the search is
		done in a separate thread (which it should, as much as possible)
		"""
		pass


	def on_reload_permission_granted(self):
		"""
		NOT REQUIRED

		Whenever a plugin wishes to rebuild some sort of internal database,
		if this takes more than a couple of milliseconds it is advisable to
		first ask Cardapio for permission. This is how this works:

		1) Plugin calls cardapio_proxy.ask_for_reload_permission(self)

		Cardapio then decides at what time it is best to give the plugin the
		reload permission. Usually this can take up to 10s, to allow several
		plugins to reload at the same time. Then, Cardapio shows the "Data has
		changed" window.

		2) Cardapio calls on_reload_permission_granted to tell the plugin that
		it can reload its database

		When done, the "Data has changed" window is hidden.
		"""
		pass




