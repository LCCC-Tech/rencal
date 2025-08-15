# Utility class to group data (by time interval) and sample (from the relevant interval) date/time indexed collections:
# Bucketer must have support for generating 2 samples that are the same in 2 different runs of the algorithm.
# Bucketer must deal with leap years properly.

import datetime
import random

from ..constants import Constants
from ..weather.Bucketer import Bucketer

class MonthlyBucketer(Bucketer):
	def __init__(self, historical_start_date = datetime.datetime.today(), historical_end_date = datetime.datetime.today()):
		categories = 1
		draw_period = 7
		super().__init__(historical_start_date, historical_end_date, categories, draw_period, bucket_definition = Constants.MONTHLY_BUCKET_DEFINITION)

		# A dictionary of months/buckets, each bucket storing an array of Sundays marking the start of weeks found in that particular month/bucket
		self.buckets = {n: [] for n in range(1, 13)}
		MonthlyBucketer.loop_weekly_between(historical_start_date, historical_end_date, self.populate_Bucket)
		# A list of historical Sundays to patch weekly data from and generate a prediction
		self.sample = []


	@property
	def buckets(self):
		return self._buckets

	@buckets.setter
	def buckets(self, b):
		if not type(b) == dict:
			raise TypeError("The buckets provided are not a dictionary")
		if not list(b.keys()) == [month for month in range(1, 13)]:
			raise ValueError("The bucket keys are not corresponding to the months 1 through 12")
		self._buckets = b

	@property
	def sample(self):
		return self._sample

	@sample.setter
	def sample(self, s):
		if not type(s) == list:
			raise TypeError("The sample provided is not a list")
		if not all(isinstance(sunday, datetime.datetime) for sunday in s):
			raise TypeError("The sample has elements that are not of type datetime.datetime")
		self._sample = s


	# All data pooled in the same category, indiscriminately:
	def assign_Category(self, date):
		return 0

	# This should be a private method, because we should only call this inside the constructor and nowhere else]
	def populate_Bucket(self, month, sunday):
		self._buckets[month].append(sunday)

	def sample_Bucket(self, month):
		self._sample.append(self.buckets[month][random.randint(0, len(self.buckets[month]) - 1)])

	# Updates the internal state of the Bucketer object to contain a new sample:
	def random_Sample(self, future_start_date, future_end_date):
		self.sample = []
		MonthlyBucketer.loop_weekly_between(future_start_date, future_end_date, self.sample_Bucket)
		return(self.sample)


	# Bucketer discards week stubs at the beginning and end of the historical data series that do not fit in a continuous week starting on Sunday and ending on Saturday;
	# The function returns the next Sunday (or current day, if it is a Sunday) so we can commence bucketing/sampling:
	@staticmethod
	def next_sunday_after(start_date):
		days_until_Sunday = 6 - start_date.weekday() # Sunday is the sixth day in the week

		if days_until_Sunday < 0:
			days_until_Sunday += 7

		return start_date + datetime.timedelta(days_until_Sunday)

	# Returns a numbers 1 through 12 to represent the month (bucket) from which to draw or in which to store the next week:
	@staticmethod
	def month_of_week_starting(start_of_week):
		end_of_week = start_of_week + datetime.timedelta(6)

		# Either the end of week is in the same month, or there are fewer days from this week in the next month than there are in this month
		if end_of_week.month == start_of_week.month or (end_of_week - datetime.datetime(end_of_week.year, end_of_week.month, 1)) <= datetime.timedelta(2):
			return start_of_week.month

		return end_of_week.month

	# Runs "function" for every proper (full 7 days) sunday-starting week in the data:
	@staticmethod
	def loop_weekly_between(start_date, end_date, function):
		sunday = MonthlyBucketer.next_sunday_after(start_date)

		while sunday <= end_date - datetime.timedelta(6): # Still historical data for a full week remaining

			month = MonthlyBucketer.month_of_week_starting(sunday)

			# Here we use a proxy for either getting or setting the instance data structures;
			# The functions have a different signature, hence the TypeError try-except block
			try:
				function(month, sunday)
			except TypeError:
				function(month)

			sunday += datetime.timedelta(7)

# random.seed(0)
# b = MonthlyBucketer(historical_start_date = datetime.datetime(2011, 12, 25), historical_end_date = datetime.datetime(2021, 9, 27))
# b.random_Sample(datetime.datetime(2022, 9, 18), datetime.datetime(2023, 3, 4))
# print(b.sample)
