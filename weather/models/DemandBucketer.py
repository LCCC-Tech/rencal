# DemandBucketer provides sampling functionality by picking historical draw periods
# from the same "bucket" that also preserve the order of weekdays in the sampled future.

# It is a child of the main Bucketer class.



# The main use case of the class is embodied by calling random_Sample(), as is the case in the main Bucketer.

import datetime
from bisect import bisect_left, bisect_right

from ..weather.Bucketer import Bucketer
from ..constants import Constants

class DemandBucketer(Bucketer):
	"""
	This class provides sampling functionality by picking historical draw periods from the same "bucket" that also preserve the business day profile of the sampled future, important for sampling demand.
	It provides the ``is_Bank_Holiday()``, ``nearest_Preserving_Weekday_Business_Day()``, and ``get_Nearest_Bank_Holiday()`` functionality to be used in the :class:`DemandData` module, where matching bank holidays in the future is important from a forecasting perspective.

	It is a child of the :class:`Bucketer` class, that provides the shared interface for all the :class:`Bucketer` sub-classes.

	The main use case of the class is embodied by calling ``random_Sample()``.
	"""
	def __init__(self, historical_start_date, historical_end_date, draw_period = 7, bucket_definition = Constants.WEEKLY_BUCKET_DEFINITION, bank_holidays = []):
		"""
		Constructing the class pulls a list of bank holidays as :class:`pandas.Timestamp` objects, checks they are sorted, and calls the :class:`Bucketer` constructor.
		It provides the ``is_Bank_Holiday()``, ``nearest_Preserving_Weekday_Business_Day()``, and ``get_Nearest_Bank_Holiday()`` functionality to be used in the DemandData module, where matching bank holidays in the future is important from a forecasting perspective.

		Args:
			historical_start_date (datetime.datetime): The midnight (start) of the start date of the historical data.
			historical_end_date (datetime.datetime): The midnight (start) of the end date (inclusive) of the historical data.
			draw_period (int): The number of days to draw at a time. Defaults to ``7`` days for demand.
			bucket_definition (list): A list of :class:`ShortDate` objects that define the buckets. Defaults to a weekly partition of a calendar year.
			bank_holidays (list): A list of :class:`datetime.datetime` objects that represent the bank holidays in the UK.
		"""
		categories = 7

		if not all(bank_holidays[i] < bank_holidays[i + 1] for i in range(len(bank_holidays) - 1)):
			raise ValueError("The bank holidays are not sorted")
		self.bank_Holidays = bank_holidays

		super().__init__(historical_start_date, historical_end_date, categories, draw_period, bucket_definition)


	def is_Bank_Holiday(self, date):
		"""
		Works for sorted bank holiday lists.
		Uses the extra tabulation spot at position ``1`` in the ``lookup_Structure`` to only compute once and return the result of this check all other times it is called.

		Args:
			date (datetime.datetime): The date to check for bank holiday status.
		"""
		try:
			return self.lookup_Structure[date][1]
		except KeyError:
			i = bisect_left(self.bank_Holidays, date)
			if i != len(self.bank_Holidays) and self.bank_Holidays[i] == date:
				return True
			else:
				return False

	def nearest_Preserving_Weekday_Business_Day(self, date, rng_python):
		"""
		Attempts to find the nearest business day that preserves the weekday of the input date, in the case we found a bank holiday historically where we needed a business day in the future period instead.

		Args:
			date (datetime.datetime): The date to find the nearest business day for.
			rng_python (random.Random): The random number generator to use for the choice between two dates if equally distant from the input date.

		Returns:
			business_day (datetime.datetime): The nearest business day that preserves the weekday of the input.
		"""
		could_be_found_prev = True
		could_be_found_next = True
		next_date = prev_date = date

		while could_be_found_prev or could_be_found_next:
			if could_be_found_next == True:
				next_date = next_date + datetime.timedelta(7)
				# Case where we reached the end of our search in the close future of the initial date in 7 day increments, and we didn't find a non-BH day:
				if next_date > self.historical_End_Date:
					could_be_found_next = False

			if could_be_found_prev == True:
				prev_date = prev_date - datetime.timedelta(7)
				# Case where we reached the end of our search in the recent past of the initial date in 7 day decrements, and we didn't find a non-BH day:
				if prev_date < self.historical_Start_Date:
					could_be_found_prev = False

			# We need to check in conjunction for the flags to be still True, to avoid cases where one of the dates, as they just exited the available range of data we have, becomes a non-BH;
			# The flag will ensure we do not return that particular date:
			if (not self.is_Bank_Holiday(next_date) and could_be_found_next) and (not self.is_Bank_Holiday(prev_date) and could_be_found_prev):
				return next_date if rng_python.choice([True, False]) else prev_date

			if not self.is_Bank_Holiday(next_date) and could_be_found_next:
				return next_date

			if not self.is_Bank_Holiday(prev_date) and could_be_found_prev:
				return prev_date

		raise ValueError("There is no business day that preserves the weekday for the date " + date + " in our available historical data.")

	def get_Nearest_Bank_Holiday(self, date):
		"""
		Attempts to find the nearest bank holiday to the input date, in the case we found a business day historically where we needed a bank holiday in the future period instead.
		As ``get_Scaling_Structure()`` explains, these will get scaled according to the average of the historical bucket for bank holidays, not the future bucket.

		Args:
			date (datetime.datetime): The date to find the nearest bank holiday for.

		Returns:
			bank_holiday (datetime.datetime): The nearest bank holiday to the input date.
		"""
		could_be_found_left = True
		could_be_found_right = True

		left = bisect_left(self.bank_Holidays, date) - 1
		if left < 0:
			could_be_found_left = False
		if left + 1 == len(self.bank_Holidays):
			could_be_found_right = False
		else:
			right = left + 1

		while could_be_found_left or could_be_found_right:
			right_found_bank_holiday = left_found_bank_holiday = None

			if could_be_found_right == True:
				if self.bank_Holidays[right] > self.historical_End_Date:
					could_be_found_right = False
				elif self.bank_Holidays[right] >= self.historical_Start_Date:
					right_found_bank_holiday = self.bank_Holidays[right]

			if could_be_found_left == True:
				if self.bank_Holidays[left] < self.historical_Start_Date:
					could_be_found_left = False
				elif self.bank_Holidays[left] <= self.historical_End_Date:
					left_found_bank_holiday = self.bank_Holidays[left]

			if left_found_bank_holiday is not None and right_found_bank_holiday is not None:
				return left_found_bank_holiday if abs((left_found_bank_holiday - date).days) <= abs((right_found_bank_holiday - date).days) else right_found_bank_holiday
			elif left_found_bank_holiday is not None:
				return left_found_bank_holiday
			elif right_found_bank_holiday is not None:
				return right_found_bank_holiday

			left -= 1
			right += 1

			if left < 0:
				could_be_found_left = False
			if right >= len(self.bank_Holidays):
				could_be_found_right = False

		raise ValueError("There is no bank holiday in our available historical data.")

	def assign_Category(self, date):
		"""
		Assigns a category to a date based on the weekday of the date.

		Args:
			date (datetime.datetime): The date to assign a category to.

		Returns:
			category (int): The category of the date.
		"""
		return date.weekday()

	def tabulate_Date_Info(self, date):
		"""
		Saves date information for faster execution.
		One level of tabulation for each date saves the bucket of each date iterated over at position ``0`` of the lookup_Structure.
		Extra tabulation to save the bank holiday status of a day on the second column of the ``lookup_Structure``.

		Args:
			date (datetime.datetime): The date to tabulate information for.

		Returns:
			lookup_structure_row (list): A list of one :class:`int` and one :class:`bool` for the bucket of the date and whether it is a bank holiday or not.
		"""
		return [self.bucket_of(date), self.is_Bank_Holiday(date)]

	def get_Scaling_Structure(self):
		"""
		Generates a scaling structure that groups bank holidays in a separate category for ease of access and random polling.
		As a result of the bank holidays being unevenly distributed in a calendar year, certain buckets have no bank holidays, while others have many.
		That is fine, as long as scaling any picked bank holiday from a past period is done according to the averages of the bucket it's been picked from, not the bucket in which the future date was found in.

		Returns:
			scaling_structure (dict): A nested dictionary indexed by categories and buckets with bank holidays in a separate category.
		"""
		scaling_structure = {category: {n: [] for n in range(0, len(self.bucket_Definition))} for category in range(self._categories + 1)}

		for category in self.bucket_Structure:
			for bucket in self.bucket_Structure[category]:
				for date_index in range(len(self.bucket_Structure[category][bucket])):
					if not self.is_Bank_Holiday(self.bucket_Structure[category][bucket][date_index]):
						scaling_structure[category][bucket].append(self.bucket_Structure[category][bucket][date_index])
					else:
						scaling_structure[self._categories][bucket].append(self.bucket_Structure[category][bucket][date_index])

		return scaling_structure
