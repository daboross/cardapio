#PANEL_TYPE_NONE  = None (Just use None instead of PANEL_TYPE_NONE)
PANEL_TYPE_GNOME2 = 1
PANEL_TYPE_AWN    = 2
PANEL_TYPE_DOCKY  = None

class CardapioAppletInterface:

	panel_type = None

	def setup(self):
		"""
		This function is called right after Cardapio loads its main variables, but
		before it actually loads plugins and builds its GUI.

		IMPORTANT: Do not modify anything inside the "cardapio" variable! It is
		only passed here directly (instead of using a proxy like in the case of
		plugins) because applets are written by "trusted" coders (since there
		will only be 3 or 4 applets total)
		"""
		pass

	def update_from_user_settings(self, settings):
		pass

	def get_allocation_estimate(self):
		pass

	def get_size_estimate(self):
		pass

	def get_position_estimate(self):
		pass

	def get_allocation(self):
		pass

	def get_size(self):
		pass

	def get_position(self):
		pass


