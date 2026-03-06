import datetime
import types

LEAP_YEAR = 2020 # We use 2020 as a proxy for a random leap year
NON_LEAP_YEAR = 2019 # Whenever we need the non-leap behaviour, we use 2019 as proxy

class ShortDate:
	"""
	This is a class used for bucket definitions, meant to be year-agnostic, defining a partition of the year.
	It must deal with leap years properly, so its default behaviour is non-leap year based.
	"""
	def __init__(self, date):
		"""
		The default constructor for the ShortDate class is designed to take a :class:`datetime.datetime` object and extract the month and day from it.
		"""
		self.month = date.month
		self.day = date.day

	@classmethod
	def from_dict(cls, date_dictionary):
		"""
		Another constructor for the ShortDate class is designed to take a dictionary with keys "month" and "day" and extract the month and day from it.
		Setters ensure these values are valid.

		Args:
			date_dictionary (dict): A dictionary with keys "month" and "day".

		Returns:
			ShortDate: A new :class:`ShortDate` object.
		"""
		date = types.SimpleNamespace()
		date.month = date_dictionary["month"]
		date.day = date_dictionary["day"]

		return cls(date)

	@classmethod
	def from_list(cls, date_list):
		"""
		Another constructor for the ShortDate class is designed to take a list with two elements, the first being the month and the second being the day.
		Setters ensure these values are valid.

		Args:
			date_list (list): A list with two elements, the first being the month and the second being the day.

		Returns:
			ShortDate: A new :class:`ShortDate` object.
		"""
		date = types.SimpleNamespace()
		date.month = date_list[0]
		date.day = date_list[1]

		return cls(date)

	
	@property
	def month(self):
		return self._month

	@month.setter
	def month(self, m):
		if not type(m) == int:
			raise TypeError("The month provided is not an integer")
		if not (m >= 1 and m <= 12):
			raise ValueError("The month provided is not between 1 and 12 inclusive")
		self._month = m

	@property
	def day(self):
		return self._day

	@day.setter
	def day(self, d):
		if not type(d) == int:
			raise TypeError("The day provided is not an integer")
		try:
			datetime.datetime(NON_LEAP_YEAR, self.month, d) # We consider that ShortDate should only hold non-leap days for consistency in partitioning years
		except ValueError:
			raise ValueError("The day provided is not a valid date for the month")
		self._day = d


	# Context years are only passed to the instance of ShortDate we are calling them on:
	def to_datetime(self, context_year):
		"""
		Coverts the :class:`ShortDate` object to a :class:`datetime.datetime` object, using the context year to determine the year of the date.

		Args:
			context_year (int): The year to use as the context for the short date.

		Returns:
			date (datetime.datetime): A new :class:`datetime.datetime` assembling the year with the short date.
		"""
		return datetime.datetime(context_year, self.month, self.day)

	def add_with_context(self, timedelta, context_year):
		"""
		Adds a timedelta to the :class:`ShortDate` object, using the context year to determine the year of the short date.

		Args:
			timedelta (datetime.timedelta): The timedelta (ideally expressed in days) to add to the :class:`ShortDate` object.
			context_year (int): The year to use as the context for the short date.

		Returns:
			addition (datetime.datetime): A new :class:`datetime.datetime` object for ease of comparison.
		"""
		addition = self.to_datetime(context_year) + timedelta # Ideally, "timedelta" is a datetime.timedelta object expressed in integer days
		return addition # We return a datetime.datetime object for ease of comparison around year transitions (for example at bucket_Definition's margins)

	def subtract_with_context(self, timedelta, context_year):
		"""
		Subtracts a timedelta from the :class:`ShortDate` object, using the context year to determine the year of the short date.

		Args:
			timedelta (datetime.timedelta): The timedelta (ideally expressed in days) to subtract from the :class:`ShortDate` object.
			context_year (int): The year to use as the context for the short date.

		Returns:
			subtraction (datetime.datetime): A new :class:`datetime.datetime` object for ease of comparison.
		"""
		subtraction = self.to_datetime(context_year) - timedelta # Here timedelta can also be a datetime.datetime,
		return subtraction # and the end result to be a timedelta object


	# All the comparison behaviour is defined for all dates, including (2, 29), to comply with all datetime.datetime objects that could be passed in a boolean expression:
	def __gt__(self, date):
		"""
		Compares two :class:`ShortDate` objects, using a leap year context for full range of possiblities.

		Args:
			date (ShortDate): The date to compare to.

		Returns:
			bool: Whether the date is greater than the other date.
		"""
		return datetime.datetime(LEAP_YEAR, self.month, self.day) > datetime.datetime(LEAP_YEAR, date.month, date.day)

	def __lt__(self, date):
		"""
		Compares two :class:`ShortDate` objects, using a leap year context for full range of possiblities.

		Args:
			date (ShortDate): The date to compare to.

		Returns:
			bool: Whether the date is less than the other date.
		"""
		return datetime.datetime(LEAP_YEAR, self.month, self.day) < datetime.datetime(LEAP_YEAR, date.month, date.day)
	
	def __ge__(self, date):
		"""
		Compares two :class:`ShortDate` objects, using a leap year context for full range of possiblities.

		Args:
			date (ShortDate): The date to compare to.

		Returns:
			bool: Whether the date is greater than or equal to the other date.
		"""
		return datetime.datetime(LEAP_YEAR, self.month, self.day) >= datetime.datetime(LEAP_YEAR, date.month, date.day)
	
	def __le__(self, date):
		"""
		Compares two :class:`ShortDate` objects, using a leap year context for full range of possiblities.

		Args:
			date (ShortDate): The date to compare to.

		Returns:
			bool: Whether the date is less than or equal to the other date.
		"""
		return datetime.datetime(LEAP_YEAR, self.month, self.day) <= datetime.datetime(LEAP_YEAR, date.month, date.day)
	
	def __eq__(self, date):
		"""
		Compares two :class:`ShortDate` objects, using a leap year context for full range of possiblities.

		Args:
			date (ShortDate): The date to compare to.

		Returns:
			bool: Whether the date is equal to the other date.
		"""
		return datetime.datetime(LEAP_YEAR, self.month, self.day) == datetime.datetime(LEAP_YEAR, date.month, date.day)
	
	# Since subtracting returns an object of this same class, simple arithmetic uses non-leap years:
	def __sub__(self, timedelta):
		if type(timedelta) == datetime.timedelta:
			return ShortDate(self.to_datetime(NON_LEAP_YEAR) - timedelta)
		elif type(timedelta) == ShortDate:
			return (self.to_datetime(NON_LEAP_YEAR) - timedelta.to_datetime(NON_LEAP_YEAR)).days

# Used as bucket_Definition in most Bucket-type modules
MONTHLY_BUCKET_DEFINITION = [ShortDate.from_list([1, 1]), ShortDate.from_list([2, 1]), ShortDate.from_list([3, 1]), ShortDate.from_list([4, 1]), ShortDate.from_list([5, 1]), ShortDate.from_list([6, 1]), ShortDate.from_list([7, 1]), ShortDate.from_list([8, 1]), ShortDate.from_list([9, 1]), ShortDate.from_list([10, 1]), ShortDate.from_list([11, 1]), ShortDate.from_list([12, 1])]
WEEKLY_BUCKET_DEFINITION = [ShortDate.from_list([1, 1]), ShortDate.from_list([1, 8]), ShortDate.from_list([1, 15]), ShortDate.from_list([1, 22]), ShortDate.from_list([1, 29]), ShortDate.from_list([2, 5]), ShortDate.from_list([2, 12]), ShortDate.from_list([2, 19]), ShortDate.from_list([2, 26]), ShortDate.from_list([3, 5]), ShortDate.from_list([3, 12]), ShortDate.from_list([3, 19]), ShortDate.from_list([3, 26]), ShortDate.from_list([4, 2]), ShortDate.from_list([4, 9]), ShortDate.from_list([4, 16]), ShortDate.from_list([4, 23]), ShortDate.from_list([4, 30]), ShortDate.from_list([5, 7]), ShortDate.from_list([5, 14]), ShortDate.from_list([5, 21]), ShortDate.from_list([5, 28]), ShortDate.from_list([6, 4]), ShortDate.from_list([6, 11]), ShortDate.from_list([6, 18]), ShortDate.from_list([6, 25]), ShortDate.from_list([7, 2]), ShortDate.from_list([7, 9]), ShortDate.from_list([7, 16]), ShortDate.from_list([7, 23]), ShortDate.from_list([7, 30]), ShortDate.from_list([8, 6]), ShortDate.from_list([8, 13]), ShortDate.from_list([8, 20]), ShortDate.from_list([8, 27]), ShortDate.from_list([9, 3]), ShortDate.from_list([9, 10]), ShortDate.from_list([9, 17]), ShortDate.from_list([9, 24]), ShortDate.from_list([10, 1]), ShortDate.from_list([10, 8]), ShortDate.from_list([10, 15]), ShortDate.from_list([10, 22]), ShortDate.from_list([10, 29]), ShortDate.from_list([11, 5]), ShortDate.from_list([11, 12]), ShortDate.from_list([11, 19]), ShortDate.from_list([11, 26]), ShortDate.from_list([12, 3]), ShortDate.from_list([12, 10]), ShortDate.from_list([12, 17]), ShortDate.from_list([12, 24])]